"""T7 -- sincronizacao de fila offline (`app.marcacao.pipeline.offline`).

Lote de 20 itens com 5 propositalmente quebrados (2 HMAC invalido, 2 contador
repetido, 1 fora do TTL): prova que os 15 restantes processam, os 5 reportam
o codigo correto, e que o lote nunca aborta por causa de um item ruim.
Reenviar o lote inteiro uma segunda vez nao duplica nenhuma marcacao.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import uuid
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.seguranca import Sujeito
from app.marcacao.pipeline import offline
from app.schemas import contrato
from tests.f5.conftest import ContextoF5

_CHAVE_MATERIAL = ""  # dispositivos.chave_publica da fixture (nao cadastrada)


def _payload_b64(contexto: ContextoF5) -> str:
    campos = {
        "colaboradorId": str(contexto.colaborador_id),
        "empresaId": str(contexto.empresa_id),
        "unidadeId": str(contexto.unidade_id),
        "canal": "mobile",
        "dispositivoId": str(contexto.dispositivo_id),
    }
    return base64.b64encode(json.dumps(campos).encode("utf-8")).decode("ascii")


def _iv_b64(semente: int) -> str:
    # Bytes seguros para UTF-8 (ver docs/backlog.md, F5/A2): `Base64Str` do
    # Pydantic exige que o conteudo decodificado seja UTF-8 valido, o que um
    # IV binario de verdade nao garante. Placeholder documentado (RFC-012).
    return base64.b64encode(f"iv-placeholder-{semente:06d}".encode("ascii")).decode("ascii")


def _item(
    contexto: ContextoF5,
    *,
    contador: int,
    datahora_dispositivo: dt.datetime,
    hmac_valido: bool = True,
) -> contrato.ItemFilaOffline:
    payload = _payload_b64(contexto)
    iv = _iv_b64(contador)
    rascunho = contrato.ItemFilaOffline.model_validate(
        {
            "contadorMonotonico": contador,
            "payloadCifrado": payload,
            "iv": iv,
            "hmac": "",
            "datahoraDispositivo": datahora_dispositivo.isoformat(),
            "tempoMonotonicoMs": contador * 1000,
        }
    )
    hmac_correto = offline.calcular_hmac_item(_CHAVE_MATERIAL, rascunho)
    hmac_final = (
        hmac_correto if hmac_valido else ("0" if hmac_correto[0] != "0" else "1") + hmac_correto[1:]
    )
    return contrato.ItemFilaOffline.model_validate(
        {
            "contadorMonotonico": contador,
            "payloadCifrado": payload,
            "iv": iv,
            "hmac": hmac_final,
            "datahoraDispositivo": datahora_dispositivo.isoformat(),
            "tempoMonotonicoMs": contador * 1000,
        }
    )


def _sujeito(contexto: ContextoF5) -> Sujeito:
    return Sujeito(
        usuario_id=uuid.uuid4(),
        tenant_id=contexto.tenant_id,
        autenticado=True,
        permissoes=frozenset({"marcacoes.criar"}),
    )


def _montar_lote(contexto: ContextoF5, agora: dt.datetime) -> list[contrato.ItemFilaOffline]:
    recente = agora - dt.timedelta(hours=1)
    antigo = agora - dt.timedelta(hours=100)  # alem do TTL padrao de 72h
    itens = [_item(contexto, contador=c, datahora_dispositivo=recente) for c in range(1, 16)]
    # 2 contadores repetidos (ja usados pelos itens 1 e 2 acima).
    itens.append(_item(contexto, contador=1, datahora_dispositivo=recente))
    itens.append(_item(contexto, contador=2, datahora_dispositivo=recente))
    # 2 HMAC invalido (contadores novos, nunca usados).
    itens.append(_item(contexto, contador=16, datahora_dispositivo=recente, hmac_valido=False))
    itens.append(_item(contexto, contador=17, datahora_dispositivo=recente, hmac_valido=False))
    # 1 fora do TTL (contador novo, dentro do range, mas capturado ha 100h).
    itens.append(_item(contexto, contador=18, datahora_dispositivo=antigo))
    return itens


async def _contar_marcacoes(sessao: AsyncSession, tenant_id: UUID) -> int:
    resultado = await sessao.execute(
        text("SELECT count(*) FROM marcacoes WHERE tenant_id = :tenant_id"),
        {"tenant_id": tenant_id},
    )
    return int(resultado.scalar_one())


async def test_lote_de_20_com_5_quebrados_processa_os_15_restantes(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    agora = dt.datetime.now(dt.UTC)
    itens = _montar_lote(contexto_f5, agora)
    corpo = contrato.SincronizacaoOfflineRequisicao(
        dispositivoId=contexto_f5.dispositivo_id, itens=itens
    )
    sujeito = _sujeito(contexto_f5)

    resposta = await offline.sincronizar_lote(
        sessao_f5,
        tenant_id=contexto_f5.tenant_id,
        corpo=corpo,
        idempotency_key=f"lote-{uuid.uuid4()}",
        sujeito=sujeito,
    )

    assert resposta.processados == 15
    assert resposta.duplicados == 2
    assert resposta.rejeitados == 2
    assert resposta.expirados == 1
    assert resposta.resultados is not None
    assert len(resposta.resultados) == 20

    # Os 15 primeiros resultados (posicoes 0..14) sao os itens originais com
    # contadores 1..15, todos processados -- olhar por posicao, nao por um
    # dict chave=contador, porque o contador 1 e o 2 aparecem DUAS vezes no
    # lote (original + reenviado) e um dict ingenuo perderia a primeira
    # ocorrencia.
    for indice in range(15):
        assert resposta.resultados[indice].status == contrato.Status61.processado
        assert resposta.resultados[indice].contador_monotonico == indice + 1
        assert resposta.resultados[indice].nsr is not None
    # Os dois reenviados repetem contador 1 e 2, na ordem em que foram
    # anexados ao lote (posicoes 16 e 17, ambos com valor 1 e 2).
    repetidos = [r for r in resposta.resultados if r.codigo_erro == "PONTO-MARC-007"]
    assert len(repetidos) == 2
    assert {r.status for r in repetidos} == {contrato.Status61.duplicado}

    invalidos = [r for r in resposta.resultados if r.codigo_erro == "PONTO-MARC-006"]
    assert len(invalidos) == 2
    assert {r.status for r in invalidos} == {contrato.Status61.rejeitado}

    expirados = [r for r in resposta.resultados if r.codigo_erro == "PONTO-MARC-005"]
    assert len(expirados) == 1
    assert expirados[0].status == contrato.Status61.expirado

    total_marcacoes = await _contar_marcacoes(sessao_f5, contexto_f5.tenant_id)
    assert total_marcacoes == 15


async def test_reenviar_o_lote_inteiro_nao_duplica_nenhuma_marcacao(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    agora = dt.datetime.now(dt.UTC)
    itens = _montar_lote(contexto_f5, agora)
    corpo = contrato.SincronizacaoOfflineRequisicao(
        dispositivoId=contexto_f5.dispositivo_id, itens=itens
    )
    sujeito = _sujeito(contexto_f5)

    primeira = await offline.sincronizar_lote(
        sessao_f5,
        tenant_id=contexto_f5.tenant_id,
        corpo=corpo,
        idempotency_key=f"lote-primeiro-{uuid.uuid4()}",
        sujeito=sujeito,
    )
    assert primeira.processados == 15
    total_apos_primeira = await _contar_marcacoes(sessao_f5, contexto_f5.tenant_id)
    assert total_apos_primeira == 15

    # Mesmo lote (mesmos itens, mesmos contadores), Idempotency-Key diferente
    # (o cabecalho e por chamada; a protecao contra duplicar MARCACAO vem do
    # contador monotonico por dispositivo em `fila_offline`, nao da chave).
    segunda = await offline.sincronizar_lote(
        sessao_f5,
        tenant_id=contexto_f5.tenant_id,
        corpo=corpo,
        idempotency_key=f"lote-segundo-{uuid.uuid4()}",
        sujeito=sujeito,
    )

    assert segunda.processados == 0
    assert segunda.duplicados == 20
    total_apos_segunda = await _contar_marcacoes(sessao_f5, contexto_f5.tenant_id)
    assert total_apos_segunda == 15
