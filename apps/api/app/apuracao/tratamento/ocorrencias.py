"""`atualizarOcorrencia` -- ownership de A3 dentro da tag `apuracoes`
(PCF §5: "compartilhado por operationId" em `app/routers/apuracoes.py`;
`listarOcorrencias`/demais operações de leitura são do A1).

Ocorrência **nunca corrige nada por si só** -- ela só muda de situação
(`aberta -> em_tratamento -> resolvida/ignorada`) e, quando há correção de
verdade, referencia o `tratamento_id` que a resolveu (glossário, verbete
"Ocorrência"). Por isso este módulo aceita apenas os campos de
acompanhamento (`status`, `resolucao`, `tratamentoId`, `severidade`); os
campos que identificam O QUE foi detectado (`codigo`, `data`, `colaboradorId`,
`vinculoId`, `apuracaoDiaId`) são fatos do motor (A1, `apurar_dia`) e não são
editáveis por aqui -- tentar mudá-los responde `PONTO-VAL-001`.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

from ponto_contracts import Ocorrencia
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.tratamento.erros_bd import traduzir_integridade
from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas

CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"
CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"

#: Campos imutáveis por este PATCH: identificam o fato detectado, não o
#: acompanhamento dele.
_CAMPOS_IMUTAVEIS = ("colaborador_id", "vinculo_id", "apuracao_dia_id", "data", "codigo")

#: Situações que encerram o acompanhamento da ocorrência -- a partir daqui
#: `resolvida_em`/`resolvida_por` são preenchidos pelo servidor, nunca pelo
#: cliente.
_STATUS_ENCERRAM = frozenset({"resolvida", "ignorada"})


def _valor(bruto: Any) -> Any:
    return bruto.value if hasattr(bruto, "value") else bruto


async def obter_ocorrencia(sessao: AsyncSession, ocorrencia_id: UUID) -> Ocorrencia:
    ocorrencia = await sessao.get(Ocorrencia, ocorrencia_id)
    if ocorrencia is None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Ocorrencia nao encontrada.")
    return ocorrencia


async def atualizar_ocorrencia(
    sessao: AsyncSession,
    ocorrencia_id: UUID,
    dados: esquemas.OcorrenciaAtualizar,
    *,
    usuario_id: UUID | None,
) -> Ocorrencia:
    ocorrencia = await obter_ocorrencia(sessao, ocorrencia_id)
    campos: dict[str, Any] = dados.model_dump(exclude_unset=True)

    for imutavel in _CAMPOS_IMUTAVEIS:
        if imutavel in campos and campos[imutavel] != getattr(ocorrencia, imutavel):
            raise ErroDeAplicacao(
                CODIGO_CORPO_INVALIDO,
                detalhe=(
                    f"Campo '{imutavel}' identifica o fato detectado pelo motor e nao pode "
                    "ser alterado; edite apenas status, resolucao, tratamentoId ou severidade."
                ),
            )
        campos.pop(imutavel, None)

    # `resolvidaEm`/`resolvidaPor` sao sempre calculados pelo servidor, nunca
    # aceitos do cliente (mesma razao dos campos imutaveis acima: o
    # acompanhamento e humano, o carimbo e' do sistema).
    campos.pop("resolvida_em", None)
    campos.pop("resolvida_por", None)

    if "status" in campos and campos["status"] is not None:
        campos["status"] = _valor(campos["status"])
    if "severidade" in campos and campos["severidade"] is not None:
        campos["severidade"] = _valor(campos["severidade"])

    for campo, valor in campos.items():
        setattr(ocorrencia, campo, valor)

    if ocorrencia.status in _STATUS_ENCERRAM and ocorrencia.resolvida_em is None:
        ocorrencia.resolvida_em = dt.datetime.now(tz=dt.UTC)
        ocorrencia.resolvida_por = usuario_id
    ocorrencia.atualizado_por = usuario_id

    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc
    return ocorrencia
