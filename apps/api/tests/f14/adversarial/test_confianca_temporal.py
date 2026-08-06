"""F14/A4 -- vetor 2: manipulacao de relogio do cliente (confianca temporal,
ADR-007 -- a parte que NAO depende do app movel).

ADR-007 regra 4 e explicita: "A marcacao recebe um nivel de confianca
temporal -- alta (deriva pequena e coerente entre os tres relogios), media
(deriva relevante, mas monotonico consistente) ou baixa (relogio retrocedeu,
boot no meio do caminho, ou divergencia inexplicavel). **O nivel alimenta o
score de confianca (ADR-008)** e aparece no espelho."

Este arquivo prova, contra o codigo real (`app.marcacao.pipeline.offline`),
que NENHUMA das duas metades desta regra esta implementada hoje:

1. **Classificacao naive.** `confianca_temporal` (offline.py, linha ~356) e
   `"alta" if item.tempo_monotonico_ms is not None else "media"` -- um mero
   teste de presenca do campo, nunca uma comparacao real entre os tres
   relogios (relogio de parede declarado x monotonico x ultima sincronizacao
   conhecida do servidor, a formula que o proprio ADR-007 descreve). Um
   atacante que CONTROLA o payload (offline e, por natureza, um payload
   assinado no APARELHO, nunca verificado contra um relogio de referencia
   externo) sempre consegue "alta" so por preencher `tempoMonotonicoMs` com
   qualquer numero -- nunca "baixa", nao importa quao incoerente o relogio de
   parede declarado seja.
2. **Sinal descartado.** O valor computado NUNCA chega a `ContextoDecisao`/
   `SinaisRegistro` (`app.marcacao.confianca.motor`) -- so alimenta o evento
   de webhook `marcacao.sincronizada_offline` (`eventos_marcacao.
   publicar_marcacao_sincronizada_offline`) e nunca e persistido em
   `marcacoes_meta` (confirmado por grep no schema: `confiancaTemporal` so
   aparece no schema do EVENTO webhook, nunca em `MarcacaoMeta`/
   `marcacoes_meta`). Resultado pratico: uma marcacao com relogio de parede
   grosseiramente incoerente (por exemplo, retrocedendo 40 horas em relacao a
   ultima marcacao do MESMO dispositivo) e aceita com o MESMO score/
   classificacao/revisaoRequerida de uma marcacao com relogio impecavel --
   nada no `scoreConfianca` devolvido, nada em `marcacoes_meta`, reflete a
   incoerencia.

Isto NAO depende de F7 (ADR-014): o ataque e feito chamando
`sincronizar_lote` com um payload construido a mao, exatamente como um
integrador ou um dispositivo comprometido (nao um SDK nativo real) faria --
a mesma classe de acesso que qualquer cliente HTTP tem hoje.
"""

from __future__ import annotations

import base64
import datetime as dt
import json

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


def _payload_base64(contexto: ContextoTenant) -> str:
    corpo = {
        "colaboradorId": str(contexto.colaborador_id),
        "empresaId": str(contexto.empresa_id),
        "unidadeId": str(contexto.unidade_id),
        "canal": "mobile",
        "dispositivoId": str(contexto.dispositivo_id),
        "latitude": GEOCERCA_LATITUDE,
        "longitude": GEOCERCA_LONGITUDE,
        "precisaoMetros": 5.0,
    }
    return base64.b64encode(json.dumps(corpo).encode("utf-8")).decode("ascii")


def _item_offline_forjado(
    contexto: ContextoTenant,
    *,
    contador: int,
    datahora_dispositivo: dt.datetime,
    tempo_monotonico_ms: int | None,
) -> contrato.ItemFilaOffline:
    payload_cifrado = _payload_base64(contexto)
    item_sem_hmac = contrato.ItemFilaOffline.model_validate(
        {
            "contadorMonotonico": contador,
            "payloadCifrado": payload_cifrado,
            "iv": base64.b64encode(b"iv-fixo-teste-16").decode("ascii"),
            "datahoraDispositivo": datahora_dispositivo.isoformat(),
            "tempoMonotonicoMs": tempo_monotonico_ms,
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
        ip_origem="203.0.113.30",
    )


async def test_relogio_retrocedido_48h_dispara_revisao(
    sessao_f14a4: AsyncSession, contexto_dois_tenants: ContextoDoisTenants
) -> None:
    """Regressao do achado original (F14/A4, corrigido no mesmo fechamento):
    um item cujo relogio de parede declarado (`datahoraDispositivo`) esta 48
    horas no passado -- dentro do TTL padrao de 72h, mas uma deriva ENORME
    para uma unica captura -- agora pontua como `confianca_temporal_baixa`
    (`app.marcacao.pipeline.offline._LIMIAR_ATRASO_SUSPEITO_MINUTOS`, 24h) e
    o sinal alimenta o motor de score (`app.antifraude.motor`), disparando
    revisao do gestor.

    Nota de honestidade (preservada do achado original): isto E UM PROXY
    HEURISTICO por magnitude do atraso, NAO a reconciliacao completa dos tres
    relogios que ADR-007 regra 4 descreve (servidor + monotonico +
    sincronizacao) -- essa reconciliacao completa continua pendente,
    registrada em docs/backlog.md. Preenchendo `tempoMonotonicoMs` com
    QUALQUER valor (o atacante controla 100% do payload) nao muda o
    resultado: e a MAGNITUDE do atraso declarado, nao a presenca do campo,
    que agora decide."""
    tenant = contexto_dois_tenants.tenant_a
    agora = dt.datetime.now(dt.UTC)
    relogio_retrocedido = agora - dt.timedelta(hours=48)

    item = _item_offline_forjado(
        tenant,
        contador=5001,
        datahora_dispositivo=relogio_retrocedido,
        tempo_monotonico_ms=123456,  # qualquer valor: o atacante escolhe.
    )

    resultado = await _sincronizar(sessao_f14a4, tenant, [item])
    assert resultado.processados == 1, resultado.resultados

    # A marcacao foi gravada com o horario FORJADO (o servidor confia no
    # relogio de parede do item offline para `datahora_marcacao`, ver
    # `offline._processar_item`: `datahora_marcacao_forcada=datahora_captura`).
    linha = (
        (
            await sessao_f14a4.execute(
                text(
                    "SELECT datahora_marcacao, coletada_offline FROM marcacoes "
                    "WHERE tenant_id = :tenant AND colaborador_id = :colaborador "
                    "ORDER BY criado_em DESC LIMIT 1"
                ),
                {"tenant": str(tenant.tenant_id), "colaborador": str(tenant.colaborador_id)},
            )
        )
        .mappings()
        .one()
    )
    assert linha["coletada_offline"] is True
    diferenca = abs((linha["datahora_marcacao"] - relogio_retrocedido).total_seconds())
    assert diferenca < 5, (
        "a marcacao deveria ter sido gravada com o horario FORJADO pelo "
        "atacante (comportamento documentado do offline-first, ADR-007) -- "
        "se isto falhar, o comportamento mudou e o resto deste teste nao se "
        "aplica mais."
    )

    # CORRIGIDO: a deriva de 48h agora dispara revisao e reduz o score --
    # confirmado tanto pelo status quanto pelo rastro na explicabilidade.
    marcacao_id = resultado.resultados[0].marcacao_id
    meta = (
        (
            await sessao_f14a4.execute(
                text(
                    "SELECT score_confianca, classificacao_confianca, revisao_status, "
                    "       flags_integridade "
                    "FROM marcacoes_meta WHERE tenant_id = :tenant AND marcacao_id = :marcacao"
                ),
                {"tenant": str(tenant.tenant_id), "marcacao": str(marcacao_id)},
            )
        )
        .mappings()
        .one()
    )
    assert meta["revisao_status"] == "pendente", (
        "uma marcacao com relogio retrocedido 48h deveria disparar revisao "
        "do gestor -- se isto falhar, o fix de confianca_temporal_baixa "
        "regrediu."
    )
    assert meta["score_confianca"] < 70
    # Rastro explicito de "confianca_temporal" no bloco de explicabilidade
    # que o proprio motor de score grava.
    bloco = meta["flags_integridade"].get("_antifraude", {})
    texto_bloco = json.dumps(bloco)
    assert "confianca_temporal" in texto_bloco or "confiancaTemporal" in texto_bloco, (
        "o sinal de confianca temporal deveria aparecer na explicabilidade "
        "gravada em marcacoes_meta.flags_integridade."
    )


async def test_nivel_de_confianca_temporal_nunca_persiste_em_marcacoes_meta(
    sessao_f14a4: AsyncSession, contexto_dois_tenants: ContextoDoisTenants
) -> None:
    """Confirma a segunda metade do achado por uma via independente: mesmo
    numa marcacao "limpa" (relogio coerente, sem tentativa de fraude), o
    nivel de confianca temporal que `offline.py` calcula localmente
    (`confianca_temporal = "alta" if ... else "media"`) nao tem NENHUMA
    coluna em `marcacoes_meta` para ser gravado -- e descartado depois de
    alimentar so o evento de webhook. Isto significa que nem o gestor (via
    fila de revisao) nem uma auditoria futura (LGPD/backlog) conseguem saber,
    a posteriori, qual foi o nivel de confianca temporal atribuido a uma
    marcacao offline especifica."""
    tenant = contexto_dois_tenants.tenant_a
    agora = dt.datetime.now(dt.UTC)

    item = _item_offline_forjado(
        tenant,
        contador=5002,
        datahora_dispositivo=agora - dt.timedelta(minutes=5),
        tempo_monotonico_ms=None,  # confianca_temporal="media" no calculo do modulo.
    )
    resultado = await _sincronizar(sessao_f14a4, tenant, [item])
    assert resultado.processados == 1

    colunas = (
        (
            await sessao_f14a4.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'marcacoes_meta'"
                )
            )
        )
        .scalars()
        .all()
    )
    colunas_lower = {c.lower() for c in colunas}
    assert not ({"confianca_temporal", "confiancatemporal"} & colunas_lower), (
        "Se este assert falhar, uma coluna foi adicionada e este achado "
        "esta resolvido -- atualize a documentacao."
    )
