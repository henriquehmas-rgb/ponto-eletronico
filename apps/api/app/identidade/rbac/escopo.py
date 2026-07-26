"""Resolucao do alcance hierarquico (escopo) do RBAC.

`usuario_perfis.escopo_tipo` + a coluna correspondente (`empresa_id`,
`unidade_id`, `departamento_id`, `equipe_id`) definem o "chao" do alcance de
uma atribuicao; `incluir_subordinados` faz o escopo descer pela arvore de
departamentos (`departamentos.departamento_pai_id`, auto-referencia).

Unidade e equipe NAO tem hierarquia declarada no contrato (`schema.sql`,
secao 3): o alcance nessas duas dimensoes e sempre a atribuicao literal,
`incluir_subordinados` ou nao -- nao ha arvore para descer.

A hierarquia de gestores (`colaborador_gestores`) resolve alcance por
COLABORADOR, uma dimensao que `app.core.seguranca.exigir_alcance` nao recebe
(seu contrato so tem `empresa_id`/`unidade_id`/`departamento_id`/`equipe_id`).
Fases que precisarem checar "este colaborador esta na minha cadeia de
subordinados" (F2 em diante, ao autorizar aprovacao de solicitacao por
exemplo) consultam `colaborador_gestores` diretamente; nao e reproduzido
aqui porque extrapolaria o ownership desta fase sobre regra de negocio de
colaborador.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.seguranca import AlcanceEfetivo


class _AtribuicaoEscopo(Protocol):
    """Forma minima de uma linha `usuario_perfis` vigente, para agregacao."""

    escopo_tipo: str
    empresa_id: UUID | None
    unidade_id: UUID | None
    departamento_id: UUID | None
    equipe_id: UUID | None
    incluir_subordinados: bool


async def descendentes_departamento(
    sessao: AsyncSession, *, tenant_id: UUID, raiz_id: UUID
) -> frozenset[UUID]:
    """`raiz_id` e todos os seus descendentes, via CTE recursiva em `departamentos`.

    A recursao e limitada ao `tenant_id`: mesmo que `departamento_pai_id`
    aponte para fora (o que a FK ja impede), a clausula garante que a arvore
    nunca atravessa tenant.
    """
    consulta = sa.text(
        """
        WITH RECURSIVE arvore AS (
            SELECT id FROM departamentos
             WHERE id = :raiz AND tenant_id = :tenant AND excluido_em IS NULL
            UNION ALL
            SELECT d.id
              FROM departamentos d
              JOIN arvore a ON d.departamento_pai_id = a.id
             WHERE d.tenant_id = :tenant AND d.excluido_em IS NULL
        )
        SELECT id FROM arvore
        """
    )
    resultado = await sessao.execute(consulta, {"raiz": raiz_id, "tenant": tenant_id})
    return frozenset(UUID(str(linha[0])) for linha in resultado)


async def montar_alcance(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    atribuicoes: Sequence[Any],
) -> AlcanceEfetivo:
    """Agrega o alcance de todas as atribuicoes vigentes de um usuario.

    Qualquer atribuicao com `escopo_tipo='tenant'` torna o alcance amplo
    (alcanca tudo dentro do tenant) e encerra a agregacao: nao ha uniao mais
    ampla que essa dentro de um tenant.
    """
    if any(getattr(a, "escopo_tipo", None) == "tenant" for a in atribuicoes):
        return AlcanceEfetivo(amplo_tenant=True)

    empresas: set[UUID] = set()
    unidades: set[UUID] = set()
    departamentos: set[UUID] = set()
    equipes: set[UUID] = set()

    for atribuicao in atribuicoes:
        tipo = atribuicao.escopo_tipo
        if tipo == "empresa" and atribuicao.empresa_id is not None:
            empresas.add(atribuicao.empresa_id)
        elif tipo == "unidade" and atribuicao.unidade_id is not None:
            unidades.add(atribuicao.unidade_id)
        elif tipo == "departamento" and atribuicao.departamento_id is not None:
            departamentos.add(atribuicao.departamento_id)
            if atribuicao.incluir_subordinados:
                departamentos |= await descendentes_departamento(
                    sessao, tenant_id=tenant_id, raiz_id=atribuicao.departamento_id
                )
        elif tipo == "equipe" and atribuicao.equipe_id is not None:
            equipes.add(atribuicao.equipe_id)
        # 'proprio' nao contribui a nenhuma das quatro dimensoes de
        # `exigir_alcance`: restringe ao proprio colaborador, verificado por
        # quem le o recurso (fora do escopo desta fase).

    return AlcanceEfetivo(
        amplo_tenant=False,
        empresas=frozenset(empresas),
        unidades=frozenset(unidades),
        departamentos=frozenset(departamentos),
        equipes=frozenset(equipes),
    )


def unir_alcances(a: AlcanceEfetivo, b: AlcanceEfetivo) -> AlcanceEfetivo:
    """Uniao de dois alcances (usada para somar o alcance herdado por delegacao)."""
    if a.amplo_tenant or b.amplo_tenant:
        return AlcanceEfetivo(amplo_tenant=True)
    return AlcanceEfetivo(
        amplo_tenant=False,
        empresas=a.empresas | b.empresas,
        unidades=a.unidades | b.unidades,
        departamentos=a.departamentos | b.departamentos,
        equipes=a.equipes | b.equipes,
    )
