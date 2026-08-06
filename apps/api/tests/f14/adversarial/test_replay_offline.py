"""F14/A4 -- vetor 1: replica de payload de marcacao offline ja processado.

Pergunta do mandato: "a idempotencia de F5 segura isso?" (PCF F14 secao "A4 --
Verificacao adversarial"). Ataca `POST /v1/marcacoes/sincronizar-offline`
(`app.marcacao.pipeline.offline`) de duas formas:

1. **Replay puro**: reenviar EXATAMENTE o mesmo item (mesmo `contadorMonotonico`,
   mesmo HMAC, mesmo payload) num lote NOVO (`Idempotency-Key` de lote
   diferente -- um atacante que capturou uma requisicao antiga e a reenvia
   nao teria a chave de idempotencia original). Esperado: dedup por
   `(dispositivo_id, contador_monotonico)`, `status="duplicado"`, nenhuma
   marcacao nova, nenhum NSR novo emitido.
2. **Replay com payload TROCADO no mesmo contador**: um atacante que descobre
   que o contador N ja foi consumido tenta reaproveitar o MESMO N com um
   payload diferente (por exemplo, mudando `sentidoInformado` ou o horario),
   na esperanca de que a checagem seja pelo conteudo, nao pelo contador.
   Esperado: tambem `duplicado` -- `_processar_item` (`offline.py`) checa
   `(dispositivo_id, contador_monotonico)` ANTES de sequer olhar o payload
   (nunca teria como devolver um resultado tao diferente).
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.seguranca import Sujeito
from app.marcacao.pipeline import offline
from app.schemas import contrato
from tests.f14.adversarial.conftest import (
    GEOCERCA_LATITUDE,
    GEOCERCA_LONGITUDE,
    ContextoDoisTenants,
    ContextoTenant,
    gerar_idempotency_key,
)


def _sujeito(contexto: ContextoTenant) -> Sujeito:
    return Sujeito(
        usuario_id=contexto.usuario_id,
        tenant_id=contexto.tenant_id,
        autenticado=True,
        permissoes=frozenset({"marcacoes.criar", "marcacoes.ler"}),
    )


def _payload_base64(contexto: ContextoTenant, *, sentido: str = "entrada") -> str:
    corpo = {
        "colaboradorId": str(contexto.colaborador_id),
        "empresaId": str(contexto.empresa_id),
        "unidadeId": str(contexto.unidade_id),
        "canal": "mobile",
        "dispositivoId": str(contexto.dispositivo_id),
        "sentidoInformado": sentido,
        "latitude": GEOCERCA_LATITUDE,
        "longitude": GEOCERCA_LONGITUDE,
        "precisaoMetros": 5.0,
    }
    return base64.b64encode(json.dumps(corpo).encode("utf-8")).decode("ascii")


def _item_offline(
    contexto: ContextoTenant,
    *,
    contador: int,
    sentido: str = "entrada",
    datahora_dispositivo: str | None = None,
) -> contrato.ItemFilaOffline:
    """Monta um item ja com o HMAC "valido" segundo o STUB documentado de
    `offline.calcular_hmac_item` (RFC-012: `chave_publica` como material --
    QUALQUER pessoa que conheca a chave publica do dispositivo, por definicao
    nao secreta, produz um HMAC aceito). Isto e o proprio atacante fazendo o
    calculo que um app real faria, exatamente como o modulo de producao
    calcularia -- nao e um atalho de teste, e o ataque em si."""
    payload_cifrado = _payload_base64(contexto, sentido=sentido)
    item_sem_hmac = contrato.ItemFilaOffline.model_validate(
        {
            "contadorMonotonico": contador,
            "payloadCifrado": payload_cifrado,
            "iv": base64.b64encode(b"iv-fixo-teste-16").decode("ascii"),
            "datahoraDispositivo": datahora_dispositivo or dt.datetime.now(dt.UTC).isoformat(),
            "tempoMonotonicoMs": 1_000_000 + contador,
        }
    )
    hmac_calculado = offline.calcular_hmac_item(contexto.dispositivo_chave_publica, item_sem_hmac)
    return item_sem_hmac.model_copy(update={"hmac": hmac_calculado})


async def _sincronizar(
    sessao: AsyncSession, contexto: ContextoTenant, itens: list[contrato.ItemFilaOffline]
) -> contrato.SincronizacaoOfflineResposta:
    corpo = contrato.SincronizacaoOfflineRequisicao.model_validate(
        {"dispositivoId": str(contexto.dispositivo_id), "itens": itens}
    )
    return await offline.sincronizar_lote(
        sessao,
        tenant_id=contexto.tenant_id,
        corpo=corpo,
        idempotency_key=gerar_idempotency_key(),
        sujeito=_sujeito(contexto),
        ip_origem="203.0.113.20",
    )


async def _contagem_marcacoes(
    sessao: AsyncSession, tenant_id: uuid.UUID, colaborador_id: uuid.UUID
) -> int:
    resultado = await sessao.execute(
        text(
            "SELECT count(*) FROM marcacoes "
            "WHERE tenant_id = :tenant AND colaborador_id = :colaborador"
        ),
        {"tenant": str(tenant_id), "colaborador": str(colaborador_id)},
    )
    return int(resultado.scalar_one())


async def test_replay_puro_do_mesmo_item_offline_e_deduplicado(
    sessao_f14a4: AsyncSession, contexto_dois_tenants: ContextoDoisTenants
) -> None:
    """DEFENDIDO esperado: primeira submissao processa; a SEGUNDA submissao,
    em um lote NOVO (Idempotency-Key de lote diferente), do MESMO item
    (mesmo contador, mesmo HMAC, mesmo payload) e recusada como duplicata --
    nao gera segunda marcacao nem segundo NSR."""
    tenant = contexto_dois_tenants.tenant_a
    item = _item_offline(tenant, contador=1001)

    primeira = await _sincronizar(sessao_f14a4, tenant, [item])
    assert primeira.processados == 1
    assert primeira.resultados[0].status == contrato.Status61.processado
    marcacao_id_original = primeira.resultados[0].marcacao_id
    nsr_original = primeira.resultados[0].nsr
    assert marcacao_id_original is not None
    assert nsr_original is not None

    total_apos_primeira = await _contagem_marcacoes(
        sessao_f14a4, tenant.tenant_id, tenant.colaborador_id
    )
    assert total_apos_primeira == 1

    # Replay: MESMO item (contador + HMAC + payload identicos), lote novo.
    segunda = await _sincronizar(sessao_f14a4, tenant, [item])
    assert segunda.duplicados == 1
    assert segunda.processados == 0
    assert segunda.resultados[0].status == contrato.Status61.duplicado
    assert segunda.resultados[0].marcacao_id == marcacao_id_original

    total_apos_replay = await _contagem_marcacoes(
        sessao_f14a4, tenant.tenant_id, tenant.colaborador_id
    )
    assert total_apos_replay == 1, (
        "VULNERAVEL se este assert falhar: replay do mesmo item offline "
        "criou uma segunda marcacao/NSR."
    )


async def test_replay_com_payload_trocado_no_mesmo_contador_tambem_e_recusado(
    sessao_f14a4: AsyncSession, contexto_dois_tenants: ContextoDoisTenants
) -> None:
    """Ataque mais sofisticado: o mesmo `contadorMonotonico` (ja consumido),
    mas um payload DIFERENTE (sentido trocado de entrada->saida, tentando
    fabricar uma segunda marcacao "grudada" no slot ja gasto). Esperado:
    `_processar_item` (offline.py) checa `(dispositivo_id, contador)` ANTES
    de decodificar o payload -- recusa como duplicata sem nem olhar o
    conteudo novo, entao o payload trocado nunca chega a virar marcacao."""
    tenant = contexto_dois_tenants.tenant_a
    item_original = _item_offline(tenant, contador=2002, sentido="entrada")

    primeira = await _sincronizar(sessao_f14a4, tenant, [item_original])
    assert primeira.processados == 1
    marcacao_id_original = primeira.resultados[0].marcacao_id

    # Mesmo contador (2002), payload trocado (saida em vez de entrada) e HMAC
    # recalculado para o NOVO payload (o "atacante" tem a chave publica e
    # consegue produzir um HMAC valido para qualquer payload que quiser).
    item_forjado = _item_offline(tenant, contador=2002, sentido="saida")

    segunda = await _sincronizar(sessao_f14a4, tenant, [item_forjado])
    assert segunda.resultados[0].status == contrato.Status61.duplicado, (
        "VULNERAVEL se nao for 'duplicado': o contador ja consumido aceitou "
        "um payload DIFERENTE do original -- reaproveitamento de contador."
    )
    assert segunda.resultados[0].marcacao_id == marcacao_id_original

    total = await _contagem_marcacoes(sessao_f14a4, tenant.tenant_id, tenant.colaborador_id)
    assert total == 1, "VULNERAVEL: contador reaproveitado com payload trocado criou marcacao nova."


async def test_replay_entre_tenants_diferentes_nao_e_possivel(
    sessao_f14a4: AsyncSession, contexto_dois_tenants: ContextoDoisTenants
) -> None:
    """A chave de dedup do item offline (`FilaOffline.dispositivo_id` +
    `contador_monotonico`) e escopada por `tenant_id` na consulta
    (`_processar_item`, `WHERE tenant_id = :tenant_id AND dispositivo_id =
    ... AND contador_monotonico = ...`). Confirma que um item processado no
    tenant A com um determinado dispositivo/contador nao e "reconhecido" no
    tenant B mesmo se (por coincidencia ou ataque deliberado) o mesmo par
    dispositivo/contador aparecesse la -- o dispositivo do tenant B e outro
    registro fisico (FK diferente), entao isto tambem prova isolamento
    cross-tenant da fila offline."""
    tenant_a = contexto_dois_tenants.tenant_a
    tenant_b = contexto_dois_tenants.tenant_b

    item_a = _item_offline(tenant_a, contador=42)
    resultado_a = await _sincronizar(sessao_f14a4, tenant_a, [item_a])
    assert resultado_a.processados == 1

    from tests.f14.adversarial.conftest import aplicar_tenant_teste

    await aplicar_tenant_teste(sessao_f14a4, tenant_b.tenant_id)
    item_b = _item_offline(tenant_b, contador=42)
    resultado_b = await _sincronizar(sessao_f14a4, tenant_b, [item_b])
    assert resultado_b.processados == 1, (
        "O mesmo numero de contador (42) usado em OUTRO tenant/dispositivo "
        "deveria processar normalmente -- nao ha colisao de dedup entre "
        "tenants distintos."
    )
    assert resultado_b.resultados[0].marcacao_id != resultado_a.resultados[0].marcacao_id


async def test_hmac_invalido_e_rejeitado_nao_apenas_deduplicado(
    sessao_f14a4: AsyncSession, contexto_dois_tenants: ContextoDoisTenants
) -> None:
    """Controle negativo: um item com HMAC que NAO bate com o calculo
    esperado (nem mesmo com o stub) e rejeitado com `PONTO-MARC-006`, nunca
    silenciosamente aceito. Prova que o dedup dos dois testes acima nao
    esconde uma falta de verificacao de HMAC."""
    tenant = contexto_dois_tenants.tenant_a
    item = _item_offline(tenant, contador=99)
    item_hmac_forjado_errado = item.model_copy(update={"hmac": "0" * 64})

    resultado = await _sincronizar(sessao_f14a4, tenant, [item_hmac_forjado_errado])
    assert resultado.resultados[0].status == contrato.Status61.rejeitado
    assert resultado.resultados[0].codigo_erro == "PONTO-MARC-006"

    total = await _contagem_marcacoes(sessao_f14a4, tenant.tenant_id, tenant.colaborador_id)
    assert total == 0
