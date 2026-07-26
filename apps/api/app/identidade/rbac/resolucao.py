"""Resolucao da permissao efetiva e do alcance do sujeito (T8/T9).

`resolver_sujeito` e o unico ponto que decide "o que este usuario, neste
tenant, agora, pode fazer e onde" -- e o corpo real por tras de
`app.core.seguranca.obter_sujeito`. Ele:

1. Carrega as atribuicoes de perfil (`usuario_perfis`) VIGENTES do usuario
   (`vigencia_inicio <= hoje` e `vigencia_fim` nulo ou `>= hoje`), com o
   `perfil` ativo e nao excluido.
2. Para cada atribuicao, carrega `perfil_permissoes` do perfil (join com
   `permissoes` para o codigo e a flag `sensivel`).
3. Uniao das permissoes CONCEDIDAS menos as NEGADAS explicitamente
   (`concedida = false`): a negacao vence, mesmo que outra atribuicao do
   mesmo usuario conceda a mesma permissao -- e a leitura literal de
   "`perfil_permissoes` com `concedida=false` nega explicitamente uma
   permissao herdada de perfil de fabrica" (PCF da fase, secao 2).
4. Agrega o alcance hierarquico das mesmas atribuicoes
   (`app.identidade.rbac.escopo.montar_alcance`).
5. Soma a delegacao vigente (T9): se ha uma delegacao ativa em que o usuario
   e o DELEGADO, herda a permissao efetiva e o alcance do DELEGANTE (que e
   resolvido pela mesma funcao, com `seguir_delegacao=False` para nao
   encadear delegacao de delegacao), respeitando a restricao opcional de
   `delegacoes.escopo`. `Sujeito.delegacao_id` fica preenchido quando isso
   acontece -- e o gatilho para `auditoria.delegacao_id` (T10).
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.seguranca import Sujeito
from app.identidade.rbac import escopo as escopo_mod
from app.identidade.rbac._contrato import contrato
from app.identidade.rbac.delegacao import (
    delegacao_ativa_para,
    permissoes_permitidas_pelo_escopo,
)


async def _atribuicoes_vigentes(
    sessao: AsyncSession, *, tenant_id: UUID, usuario_id: UUID, hoje: _dt.date | None = None
) -> list[Any]:
    dia = hoje or _dt.datetime.now(_dt.UTC).date()
    consulta = (
        sa.select(contrato.UsuarioPerfil)
        .join(contrato.Perfil, contrato.Perfil.id == contrato.UsuarioPerfil.perfil_id)
        .where(
            contrato.UsuarioPerfil.tenant_id == tenant_id,
            contrato.UsuarioPerfil.usuario_id == usuario_id,
            contrato.UsuarioPerfil.vigencia_inicio <= dia,
            sa.or_(
                contrato.UsuarioPerfil.vigencia_fim.is_(None),
                contrato.UsuarioPerfil.vigencia_fim >= dia,
            ),
            contrato.Perfil.ativo.is_(True),
            contrato.Perfil.excluido_em.is_(None),
        )
    )
    return list((await sessao.scalars(consulta)).all())


async def _permissoes_dos_perfis(
    sessao: AsyncSession, *, tenant_id: UUID, perfil_ids: Sequence[UUID]
) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    """Devolve `(concedidas, negadas, sensiveis)` agregadas sobre `perfil_ids`.

    `sensiveis` e o subconjunto das concedidas (ja liquidas de negacao) cuja
    `permissoes.sensivel` e verdadeira.
    """
    if not perfil_ids:
        return frozenset(), frozenset(), frozenset()

    consulta = (
        sa.select(
            contrato.Permissao.codigo,
            contrato.PerfilPermissao.concedida,
            contrato.Permissao.sensivel,
        )
        .join(
            contrato.PerfilPermissao,
            contrato.PerfilPermissao.permissao_id == contrato.Permissao.id,
        )
        .where(
            contrato.PerfilPermissao.tenant_id == tenant_id,
            contrato.PerfilPermissao.perfil_id.in_(perfil_ids),
        )
    )
    concedidas: set[str] = set()
    negadas: set[str] = set()
    sensiveis_brutas: set[str] = set()
    for codigo, concedida, sensivel in await sessao.execute(consulta):
        if concedida:
            concedidas.add(codigo)
        else:
            negadas.add(codigo)
        if sensivel:
            sensiveis_brutas.add(codigo)

    efetivas = frozenset(concedidas - negadas)
    sensiveis = frozenset(sensiveis_brutas & efetivas)
    return efetivas, frozenset(negadas), sensiveis


async def resolver_sujeito(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    usuario_id: UUID,
    hoje: _dt.date | None = None,
    agora: _dt.datetime | None = None,
    seguir_delegacao: bool = True,
) -> Sujeito:
    """Resolve o `Sujeito` completo (permissao efetiva + alcance + delegacao)."""
    usuario = await sessao.get(contrato.Usuario, usuario_id)
    if usuario is None or usuario.tenant_id != tenant_id or usuario.excluido_em is not None:
        return Sujeito()

    atribuicoes = await _atribuicoes_vigentes(
        sessao, tenant_id=tenant_id, usuario_id=usuario_id, hoje=hoje
    )
    perfil_ids = [a.perfil_id for a in atribuicoes]
    concedidas, _negadas, sensiveis = await _permissoes_dos_perfis(
        sessao, tenant_id=tenant_id, perfil_ids=perfil_ids
    )
    alcance = await escopo_mod.montar_alcance(sessao, tenant_id=tenant_id, atribuicoes=atribuicoes)

    # Os models do contrato nao declaram `relationship()` (mapeamento so de
    # colunas -- ver `packages/contracts/models`), entao os codigos e a flag
    # `somente_leitura` do perfil saem de uma segunda consulta direta, e nao
    # de navegacao ORM.
    perfis_codigos: tuple[str, ...] = ()
    perfis_somente_leitura = False
    if perfil_ids:
        linhas = list(
            await sessao.execute(
                sa.select(contrato.Perfil.codigo, contrato.Perfil.somente_leitura).where(
                    contrato.Perfil.id.in_(perfil_ids)
                )
            )
        )
        perfis_codigos = tuple(sorted(codigo for codigo, _somente_leitura in linhas))
        perfis_somente_leitura = bool(linhas) and all(
            somente_leitura for _codigo, somente_leitura in linhas
        )

    delegacao_id: UUID | None = None
    if seguir_delegacao:
        delegacao = await delegacao_ativa_para(
            sessao, tenant_id=tenant_id, delegado_usuario_id=usuario_id, agora=agora
        )
        if delegacao is not None:
            sujeito_delegante = await resolver_sujeito(
                sessao,
                tenant_id=tenant_id,
                usuario_id=delegacao.delegante_usuario_id,
                hoje=hoje,
                agora=agora,
                seguir_delegacao=False,
            )
            herdadas = permissoes_permitidas_pelo_escopo(
                delegacao.escopo, sujeito_delegante.permissoes
            )
            concedidas = frozenset(concedidas | herdadas)
            sensiveis = frozenset(sensiveis | (herdadas & sujeito_delegante.permissoes_sensiveis))
            if sujeito_delegante.alcance is not None:
                alcance = escopo_mod.unir_alcances(alcance, sujeito_delegante.alcance)
            delegacao_id = delegacao.id
            if not sujeito_delegante.perfis_somente_leitura:
                # O delegante nao e somente-leitura: a delegacao concede
                # escrita de verdade, entao o veto generico do delegado
                # (T8) nao pode barrar o que ele herdou por delegacao (T9).
                perfis_somente_leitura = False

    return Sujeito(
        usuario_id=usuario_id,
        tenant_id=tenant_id,
        email=usuario.email,
        perfis=perfis_codigos,
        permissoes=concedidas,
        delegacao_id=delegacao_id,
        autenticado=True,
        permissoes_sensiveis=sensiveis,
        alcance=alcance,
        perfis_somente_leitura=perfis_somente_leitura,
    )
