"""CRUD genérico de `importacoes` (RFC-017, A8): `listarImportacoes`,
`criarImportacao`, `obterImportacao` -- as três operações que `apps/api/app/
routers/integracoes.py` (funções de A8, nunca as de folha, ver aquele
arquivo) delega para cá.

**Escopo genuíno desta fase (T19): só `afd_terceiro` tem processamento real
de ponta a ponta.** `POST /v1/importacoes` é um endpoint GENÉRICO desde a
Fase 0 (`tipo` aceita nove valores: colaboradores, estrutura, escalas,
feriados, marcacoes, afd_terceiro, banco_horas, biometria, afastamentos) --
não é um endpoint novo criado por esta fase, só a implementação é. Este
módulo:

- Para `tipo='afd_terceiro'` (o próprio T19): valida `origem='afd'` e
  `empresaId`/`conteudoRef` obrigatórios, resolve o REP-P alvo
  (`afd_terceiro.servico.resolver_rep_p_alvo`) e enfileira
  `importar_arquivo_generico` (worker, ver `apps/worker/worker/tarefas/
  integracoes.py`).
- Para `tipo='colaboradores'`: reaproveita a tarefa REAL já implementada
  pela F2 (`importar_colaboradores`) em vez de reimplementar -- mesmo
  `importacao_id`, mesmo contrato de fila, only o ponto de entrada HTTP é
  novo (o endpoint dedicado `POST /v1/colaboradores/importar`, de F2/A2,
  continua existindo e intocado; este é só uma segunda porta de entrada para
  o mesmo pipeline).
- Para os seis tipos restantes (`estrutura`, `escalas`, `feriados`,
  `marcacoes`, `banco_horas`, `biometria`): NENHUMA fase até agora
  implementou um pipeline de importação para eles. Implementar cada um está
  fora do escopo de T19 (importador de AFD de terceiro) -- não é uma
  omissão silenciosa: a importação é aceita, registrada em `importacoes`
  (status `recebido`, depois `processando`), e o worker genérico
  (`importar_arquivo_generico`) marca `falhou` com uma mensagem clara de
  "tipo ainda nao suportado por este importador generico", em vez de travar
  a requisição HTTP ou fingir sucesso. Registrado como achado, não decidido
  como RFC nenhuma -- é só honestidade de escopo (mesmo padrão de ADR-011/
  012), não uma lacuna de contrato: o contrato já promete um comportamento
  assíncrono (202 + acompanhamento via `GET /v1/importacoes/{id}`), que este
  desenho cumpre à risca mesmo quando o resultado final é "não suportado".
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from arq import create_pool
from arq.connections import RedisSettings
from ponto_contracts import Importacao
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.core.filas import FILA_PADRAO
from app.integracoes.importadores.afd_terceiro.servico import resolver_rep_p_alvo
from app.integracoes.importadores.paginacao import (
    CampoOrdenacao,
    Ordenacao,
    codificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    montar_paginacao,
    normalizar_limite,
)
from app.schemas import contrato as esquemas

__all__ = ["criar_importacao", "listar_importacoes", "obter_importacao"]

#: Status que significam "ainda em voo" para o par tenant+empresa+tipo --
#: mesmo critério que `app.importadores.servico` (F2) já usa para
#: `colaboradores`.
_STATUS_EM_ANDAMENTO = ("recebido", "validando", "processando")

#: Nome da tarefa do worker por `tipo`. `afd_terceiro` é o único pipeline
#: novo desta fase; `colaboradores` reaproveita a tarefa já real da F2 (ver
#: docstring do módulo). Os demais caem no dispatcher genérico, que
#: responde "nao suportado" de forma limpa (nunca crasha, nunca finge
#: sucesso).
NOME_TAREFA_IMPORTAR_ARQUIVO_GENERICO = "importar_arquivo_generico"
NOME_TAREFA_IMPORTAR_COLABORADORES = "importar_colaboradores"
_TAREFA_POR_TIPO: dict[str, str] = {
    "colaboradores": NOME_TAREFA_IMPORTAR_COLABORADORES,
}

_CAMPOS_ORDENACAO: frozenset[str] = frozenset({"criadoEm", "concluidoEm"})


def _tarefa_para_tipo(tipo: str) -> str:
    return _TAREFA_POR_TIPO.get(tipo, NOME_TAREFA_IMPORTAR_ARQUIVO_GENERICO)


async def _falha_se_em_andamento(
    sessao: AsyncSession, *, tenant_id: UUID, empresa_id: UUID | None, tipo: str
) -> None:
    em_andamento = (
        (
            await sessao.execute(
                sa.select(Importacao.id).where(
                    Importacao.tenant_id == tenant_id,
                    Importacao.tipo == tipo,
                    Importacao.empresa_id == empresa_id,
                    Importacao.status.in_(_STATUS_EM_ANDAMENTO),
                )
            )
        )
        .scalars()
        .first()
    )
    if em_andamento is not None:
        raise ErroDeAplicacao(
            "PONTO-IMP-002", detalhe=f"Ja existe importacao do tipo '{tipo}' em andamento."
        )


async def _preparar_parametros_afd_terceiro(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    corpo: esquemas.ImportacaoCriar,
) -> dict[str, Any]:
    """Validações e resolução SÍNCRONAS específicas de `afd_terceiro`, antes
    de gravar `importacoes` e enfileirar. Ver `afd_terceiro/servico.py` para
    a resolução do REP-P e a decisão documentada sobre `rep_p_id`."""
    if corpo.origem != esquemas.Origem8.afd:
        raise ErroDeAplicacao(
            "PONTO-VAL-009",
            detalhe="Importacao do tipo afd_terceiro exige origem='afd'.",
        )
    if corpo.empresa_id is None:
        raise ErroDeAplicacao(
            "PONTO-VAL-001", detalhe="empresaId e obrigatorio para importacao afd_terceiro."
        )
    if not corpo.conteudo_ref:
        raise ErroDeAplicacao(
            "PONTO-VAL-001", detalhe="conteudoRef e obrigatorio para importacao afd_terceiro."
        )

    parametros = dict(corpo.parametros or {})
    rep_p_id_informado_bruto = parametros.get("repPId")
    rep_p_id_informado = UUID(str(rep_p_id_informado_bruto)) if rep_p_id_informado_bruto else None

    rep_p_id = await resolver_rep_p_alvo(
        sessao,
        tenant_id=tenant_id,
        empresa_id=corpo.empresa_id,
        rep_p_id_informado=rep_p_id_informado,
    )
    parametros["repPId"] = str(rep_p_id)
    return parametros


async def criar_importacao(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    corpo: esquemas.ImportacaoCriar,
    usuario_id: UUID | None,
    redis_url: str,
) -> esquemas.Importacao:
    # `Tipo33`/`Origem8` sao `enum.StrEnum` (contrato.py): ja sao `str` de
    # verdade (`isinstance(corpo.tipo, str)` e `True`), entao comparar e
    # persistir usa o proprio membro do enum, sem `.value`/`str()` extra.
    tipo = corpo.tipo

    await _falha_se_em_andamento(
        sessao, tenant_id=tenant_id, empresa_id=corpo.empresa_id, tipo=tipo
    )

    parametros: dict[str, Any] | None = dict(corpo.parametros or {}) if corpo.parametros else None
    if tipo == "afd_terceiro":
        parametros = await _preparar_parametros_afd_terceiro(
            sessao, tenant_id=tenant_id, corpo=corpo
        )

    importacao = Importacao(
        tenant_id=tenant_id,
        empresa_id=corpo.empresa_id,
        tipo=tipo,
        origem=corpo.origem,
        nome_arquivo=corpo.nome_arquivo,
        conteudo_ref=corpo.conteudo_ref,
        parametros=parametros,
        status="recebido",
        criado_por=usuario_id,
    )
    sessao.add(importacao)
    await sessao.flush()

    tarefa = _tarefa_para_tipo(tipo)
    pool = await create_pool(RedisSettings.from_dsn(redis_url), default_queue_name=FILA_PADRAO)
    try:
        await pool.enqueue_job(tarefa, tenant_id=str(tenant_id), importacao_id=str(importacao.id))
    finally:
        await pool.aclose()

    return esquemas.Importacao.model_validate(importacao, from_attributes=True)


async def obter_importacao(
    sessao: AsyncSession, *, tenant_id: UUID, importacao_id: UUID
) -> esquemas.Importacao:
    importacao = await sessao.get(Importacao, importacao_id)
    if importacao is None or importacao.tenant_id != tenant_id:
        raise ErroDeAplicacao("PONTO-REC-001", contexto_log={"importacaoId": str(importacao_id)})
    return esquemas.Importacao.model_validate(importacao, from_attributes=True)


async def listar_importacoes(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    empresa_id: UUID | None,
    tipo: str | None,
    status: str | None,
    cursor: str | None,
    limite: int | None,
    ordenar: str | None,
) -> esquemas.ListaImportacao:
    ordenacao: Ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=_CAMPOS_ORDENACAO, padrao="criadoEm"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = sa.select(Importacao).where(Importacao.tenant_id == tenant_id)
    if empresa_id is not None:
        consulta = consulta.where(Importacao.empresa_id == empresa_id)
    if tipo is not None:
        consulta = consulta.where(Importacao.tipo == tipo)
    if status is not None:
        consulta = consulta.where(Importacao.status == status)

    campo = (
        CampoOrdenacao(coluna=Importacao.concluido_em, conversor=str)
        if ordenacao.campo == "concluidoEm"
        else CampoOrdenacao(coluna=Importacao.criado_em, conversor=str)
    )
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=Importacao.id,
        cursor=cursor,
        limite=limite_efetivo,
    )

    proximo_cursor = None
    if tem_mais and linhas:
        ultima = linhas[-1]
        valor_ordenacao = (
            ultima.concluido_em if ordenacao.campo == "concluidoEm" else ultima.criado_em
        )
        proximo_cursor = codificar_cursor(ordenacao, valor_ordenacao, ultima.id)

    return esquemas.ListaImportacao(
        dados=[esquemas.Importacao.model_validate(linha, from_attributes=True) for linha in linhas],
        paginacao=montar_paginacao(
            proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
        ),
    )
