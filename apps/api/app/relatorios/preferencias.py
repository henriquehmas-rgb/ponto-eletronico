"""Módulo interno de preferências de colunas (T1, RFC-015, F11/A1).

`salvar_preferencia`/`obter_preferencia`/`listar_preferencias` operam direto
sobre `preferencias_colunas` sob RLS -- consumidas pelos dois handlers HTTP
novos em `app/routers/relatorios.py` (`listarPreferenciasColunas`/
`salvarPreferenciaColunas`, RFC-015 §2.4 do PCF, já decidida pelo
orquestrador em 30/07/2026).

`salvar_preferencia` faz `INSERT ... ON CONFLICT ... DO UPDATE` sobre o
índice único `uq_preferencias_colunas` (`tenant_id`, `usuario_id`,
`COALESCE(relatorio_definicao_id, '00000000-0000-0000-0000-000000000000')`,
`COALESCE(tela, '')`, `nome`) -- **verificado contra o banco real** (a
expressão de `index_elements` precisa bater exatamente com a expressão do
índice para o Postgres aceitar a inferência do `ON CONFLICT`; testado
isoladamente antes de integrar, ver relatório de fechamento da fase). É o
que dá à `PUT /v1/relatorios/preferencias-colunas` sua idempotência sem
`Idempotency-Key` (decisão 2 da RFC-015): reenviar a mesma chamada atualiza
a mesma linha, nunca cria uma duplicata.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from ponto_contracts import PreferenciaColunas
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.relatorios.paginacao import (
    CampoOrdenacao,
    codificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    montar_paginacao,
    normalizar_limite,
)
from app.schemas import contrato as esquemas

CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"
CODIGO_CONSULTA_INVALIDA = "PONTO-VAL-005"

#: `__table__` de uma classe declarativa e tipado de forma ampla
#: (`FromClause`) pelos stubs do SQLAlchemy; `pg_insert` exige `Table`. E
#: sempre um `Table` de verdade em runtime (toda classe mapeada tem uma
#: tabela real por baixo) -- a anotacao so estreita o tipo para o mypy.
_TABELA: sa.Table = PreferenciaColunas.__table__  # type: ignore[assignment]
#: Mesma expressão de `uq_preferencias_colunas` (confirmada contra o schema
#: real, `pg_indexes`) -- ver docstring do módulo.
_ALVO_RELATORIO = sa.func.coalesce(
    _TABELA.c.relatorio_definicao_id,
    sa.literal_column("'00000000-0000-0000-0000-000000000000'::uuid"),
)
_ALVO_TELA = sa.func.coalesce(_TABELA.c.tela, sa.literal(""))

_CAMPOS_ORDENACAO: dict[str, CampoOrdenacao] = {
    "criadoEm": CampoOrdenacao(PreferenciaColunas.criado_em, dt.datetime.fromisoformat),
    "nome": CampoOrdenacao(PreferenciaColunas.nome, str),
}


def _validar_alvo(relatorio_definicao_id: UUID | None, tela: str | None) -> None:
    """`ck_preferencias_colunas_alvo`: exatamente um dos dois, nunca os dois,
    nunca nenhum."""
    if (relatorio_definicao_id is None) == (tela is None):
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe="Informe relatorioDefinicaoId OU tela, nunca os dois nem nenhum.",
        )


async def salvar_preferencia(
    sessao: AsyncSession,
    tenant_id: UUID,
    usuario_id: UUID,
    *,
    relatorio_definicao_id: UUID | None,
    tela: str | None,
    nome: str,
    colunas: Sequence[str],
    ordenacao: dict[str, Any] | None,
    filtros: dict[str, Any] | None,
    larguras: dict[str, Any] | None,
    padrao: bool,
) -> PreferenciaColunas:
    """`PUT /v1/relatorios/preferencias-colunas`. Cria ou substitui a
    preferência do PRÓPRIO `usuario_id` -- nunca aceito de fora, sempre o do
    sujeito autenticado (RFC-015)."""
    _validar_alvo(relatorio_definicao_id, tela)
    if not colunas:
        raise ErroDeAplicacao(CODIGO_CORPO_INVALIDO, detalhe="colunas nao pode ser vazio.")

    agora = dt.datetime.now(tz=dt.UTC)
    insercao = pg_insert(_TABELA).values(
        id=uuid4(),
        tenant_id=tenant_id,
        usuario_id=usuario_id,
        relatorio_definicao_id=relatorio_definicao_id,
        tela=tela,
        nome=nome,
        colunas=list(colunas),
        ordenacao=ordenacao,
        filtros=filtros,
        larguras=larguras,
        padrao=padrao,
        criado_por=usuario_id,
        atualizado_em=agora,
        atualizado_por=usuario_id,
    )
    comando = insercao.on_conflict_do_update(
        index_elements=[
            _TABELA.c.tenant_id,
            _TABELA.c.usuario_id,
            _ALVO_RELATORIO,
            _ALVO_TELA,
            _TABELA.c.nome,
        ],
        set_={
            "colunas": insercao.excluded.colunas,
            "ordenacao": insercao.excluded.ordenacao,
            "filtros": insercao.excluded.filtros,
            "larguras": insercao.excluded.larguras,
            "padrao": insercao.excluded.padrao,
            "atualizado_em": insercao.excluded.atualizado_em,
            "atualizado_por": insercao.excluded.atualizado_por,
        },
    ).returning(_TABELA.c.id)

    try:
        resultado = await sessao.execute(comando)
    except sa.exc.IntegrityError as exc:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO, detalhe="relatorioDefinicaoId nao encontrado."
        ) from exc
    linha_id = resultado.scalar_one()
    await sessao.flush()
    # `populate_existing=True`: sem isto, um `UPDATE` (segunda chamada com o
    # mesmo alvo) devolveria o objeto ANTIGO do identity map da sessao (achado
    # real, testado contra o banco durante o desenvolvimento desta fase) --
    # `INSERT ... ON CONFLICT ... DO UPDATE` muda a linha no banco por fora do
    # ORM, entao a sessao precisa ser instruida a recarregar, nunca confiar
    # no cache.
    preferencia = await sessao.get(PreferenciaColunas, linha_id, populate_existing=True)
    if preferencia is None:  # pragma: no cover - invariante interna, nao entrada de usuario
        raise RuntimeError("preferencia recem gravada nao encontrada na mesma transacao")
    return preferencia


async def obter_preferencia(
    sessao: AsyncSession,
    tenant_id: UUID,
    usuario_id: UUID,
    *,
    relatorio_definicao_id: UUID | None,
    tela: str | None,
    nome: str = "padrao",
) -> PreferenciaColunas | None:
    """Leitura direta de uma preferência específica (alvo + nome). Usado por
    quem já sabe exatamente qual preferência quer (por exemplo, a tela
    genérica carregando o layout `"padrao"` de um relatório)."""
    _validar_alvo(relatorio_definicao_id, tela)
    consulta = sa.select(PreferenciaColunas).where(
        PreferenciaColunas.tenant_id == tenant_id,
        PreferenciaColunas.usuario_id == usuario_id,
        PreferenciaColunas.nome == nome,
    )
    if relatorio_definicao_id is not None:
        consulta = consulta.where(
            PreferenciaColunas.relatorio_definicao_id == relatorio_definicao_id
        )
    else:
        consulta = consulta.where(PreferenciaColunas.tela == tela)
    return (await sessao.execute(consulta)).scalar_one_or_none()


async def listar_preferencias(
    sessao: AsyncSession,
    tenant_id: UUID,
    usuario_id: UUID,
    *,
    relatorio_definicao_id: UUID | None = None,
    tela: str | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[PreferenciaColunas], esquemas.Paginacao]:
    """`GET /v1/relatorios/preferencias-colunas`. Sempre filtrada pelo
    PRÓPRIO `usuario_id` do sujeito autenticado (RFC-015: "nunca aceita
    usuarioId de query"). `relatorioDefinicaoId`/`tela` são opcionais e
    mutuamente exclusivos quando os dois são informados juntos."""
    if relatorio_definicao_id is not None and tela is not None:
        raise ErroDeAplicacao(
            CODIGO_CONSULTA_INVALIDA,
            detalhe="Informe relatorioDefinicaoId OU tela, nao os dois ao mesmo tempo.",
        )
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO), padrao="criadoEm"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = sa.select(PreferenciaColunas).where(
        PreferenciaColunas.tenant_id == tenant_id, PreferenciaColunas.usuario_id == usuario_id
    )
    if relatorio_definicao_id is not None:
        consulta = consulta.where(
            PreferenciaColunas.relatorio_definicao_id == relatorio_definicao_id
        )
    if tela is not None:
        consulta = consulta.where(PreferenciaColunas.tela == tela)

    campo = _CAMPOS_ORDENACAO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=PreferenciaColunas.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    atributo = "criado_em" if ordenacao.campo == "criadoEm" else "nome"
    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        proximo_cursor = codificar_cursor(ordenacao, getattr(ultimo, atributo), ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao
