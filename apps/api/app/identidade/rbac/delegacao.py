"""Delegacao temporaria (T9): efeito na autorizacao.

Esta fase implementa a TABELA `delegacoes` (ja criada por `0001_inicial.py`) e
o efeito da delegacao vigente na resolucao do sujeito
(`app.identidade.rbac.resolucao`): enquanto vigente, o delegado herda o
escopo e as permissoes do delegante, restrito pelo JSON `delegacoes.escopo`
quando presente. Os ENDPOINTS de delegacao (`criarDelegacao`,
`listarDelegacoes`) sao da F10 -- aqui a delegacao e sempre criada direto na
tabela (pelo teste, ou por quem vier a escrever o endpoint em F10).

`delegacoes.escopo` e um JSONB livre no contrato. Nao ha esquema formal
documentado para o seu conteudo alem do exemplo do `schema.sql`
("restringir a delegacao a solicitacoes de ajuste de ponto"). Esta
implementacao interpreta uma chave opcional `"permissoes"` (lista de codigos)
como allow-list: quando presente, a heranca fica restrita a interseccao com
essa lista. Ausente a chave, a heranca e integral. Fases futuras que
precisarem de uma restricao mais rica (por exemplo por entidade) estendem
este contrato via RFC, ja que "escopo" e JSONB de forma livre.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.identidade.rbac._contrato import contrato

#: Estados de uma delegacao que ainda podem estar dentro da janela vigente.
#: `encerrada` e `cancelada` nunca autorizam, mesmo dentro do intervalo de
#: datas -- foram desligadas explicitamente.
_STATUS_POTENCIALMENTE_VIGENTES = ("agendada", "ativa")


def _agora(agora: _dt.datetime | None) -> _dt.datetime:
    return agora or _dt.datetime.now(_dt.UTC)


async def delegacao_ativa_para(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    delegado_usuario_id: UUID,
    agora: _dt.datetime | None = None,
) -> Any | None:
    """Devolve a delegacao vigente mais recente para `delegado_usuario_id`.

    "Vigente" = `status` em (`agendada`,`ativa`) E `agora` dentro de
    `[inicio_em, fim_em)`. Quando o usuario tem mais de uma delegacao vigente
    simultanea (de delegantes diferentes -- a constraint `EXCLUDE` so proibe
    sobreposicao para o MESMO par delegante/delegado), a mais recentemente
    iniciada e a escolhida para estampar `auditoria.delegacao_id`; o escopo de
    todas as vigentes e somado por `resolver_sujeito`.
    """
    instante = _agora(agora)
    consulta = (
        sa.select(contrato.Delegacao)
        .where(
            contrato.Delegacao.tenant_id == tenant_id,
            contrato.Delegacao.delegado_usuario_id == delegado_usuario_id,
            contrato.Delegacao.status.in_(_STATUS_POTENCIALMENTE_VIGENTES),
            contrato.Delegacao.inicio_em <= instante,
            contrato.Delegacao.fim_em > instante,
        )
        .order_by(contrato.Delegacao.inicio_em.desc())
    )
    return (await sessao.scalars(consulta)).first()


async def delegacoes_ativas_para(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    delegado_usuario_id: UUID,
    agora: _dt.datetime | None = None,
) -> list[Any]:
    """Todas as delegacoes vigentes para `delegado_usuario_id` (ver `delegacao_ativa_para`)."""
    instante = _agora(agora)
    consulta = sa.select(contrato.Delegacao).where(
        contrato.Delegacao.tenant_id == tenant_id,
        contrato.Delegacao.delegado_usuario_id == delegado_usuario_id,
        contrato.Delegacao.status.in_(_STATUS_POTENCIALMENTE_VIGENTES),
        contrato.Delegacao.inicio_em <= instante,
        contrato.Delegacao.fim_em > instante,
    )
    return list((await sessao.scalars(consulta)).all())


def verificar_delegacao_vigente(
    delegacao: Any | None, *, agora: _dt.datetime | None = None
) -> None:
    """Levanta `PONTO-PERM-005` quando a delegacao informada nao esta vigente.

    Uso: quando ALGUEM AFIRMA agir por uma delegacao especifica (por
    exemplo, a F10 recebendo um `delegacaoId` explicito num corpo de
    aprovacao) e precisa confirmar que ela ainda vale. A resolucao silenciosa
    do sujeito em `resolver_sujeito` NAO usa esta funcao: ali, ausencia de
    delegacao vigente so significa "sem heranca extra", nunca erro.
    """
    instante = _agora(agora)
    if delegacao is None:
        raise ErroDeAplicacao("PONTO-PERM-005")
    if delegacao.status not in _STATUS_POTENCIALMENTE_VIGENTES:
        raise ErroDeAplicacao("PONTO-PERM-005")
    if not (delegacao.inicio_em <= instante < delegacao.fim_em):
        raise ErroDeAplicacao("PONTO-PERM-005")


def permissoes_permitidas_pelo_escopo(
    escopo: dict[str, Any] | None, permissoes_herdadas: frozenset[str]
) -> frozenset[str]:
    """Aplica a restricao opcional `escopo["permissoes"]` (ver docstring do modulo)."""
    if not escopo:
        return permissoes_herdadas
    lista = escopo.get("permissoes")
    if not lista:
        return permissoes_herdadas
    return permissoes_herdadas & frozenset(lista)
