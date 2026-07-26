"""Criterio de aceite 6: matriz perfil x permissao dos 7 perfis de fabrica,
contra pelo menos uma operacao de cada permissao exigida pelas 29 operacoes
desta fase (T8).

O resultado esperado de cada celula vem da leitura literal de
`apps/api/migrations/seed_dev.py` (`MATRIZ_PERFIS`, `CATALOGO_PERMISSOES`):
cada permissao pertence a um `modulo`, e um perfil a possui quando (a) tem
`"*"` no seu bloco do `MATRIZ_PERFIS` com a acao dentro do conjunto, OU (b) tem
o `modulo` da permissao listado explicitamente com a acao dentro do conjunto.
Nao reimplementamos essa logica aqui -- fixamos o resultado esperado como dado
de teste, porque e exatamente esse contrato (visivel apenas via
`resolver_sujeito`) que este teste prova.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.identidade.rbac.resolucao import resolver_sujeito
from tests.f1.rbac._apoio import atribuir_perfil, criar_usuario
from tests.f1.rbac.conftest import aplicar_tenant

#: As 16 permissoes com `x-permissao` nao-publico exigidas pelas 29 operacoes
#: desta fase (tabela da secao 4 do PCF F01).
_PERMISSOES_DA_FASE: tuple[str, ...] = (
    "sessoes.ler",
    "sessoes.excluir",
    "tenants.ler",
    "tenants.criar",
    "tenants.editar",
    "tenants.configurar",
    "usuarios.ler",
    "usuarios.criar",
    "usuarios.editar",
    "perfis.ler",
    "perfis.criar",
    "permissoes.ler",
    "api_clients.ler",
    "api_clients.criar",
    "auditoria.ler",
    "auditoria.executar",
)

#: `True`/`False` explicito por (perfil, permissao). Ver docstring do modulo
#: para a derivacao a partir de `seed_dev.MATRIZ_PERFIS`.
_MATRIZ_ESPERADA: dict[str, dict[str, bool]] = {
    "super_admin": dict.fromkeys(_PERMISSOES_DA_FASE, True),
    "admin_empresa": dict.fromkeys(_PERMISSOES_DA_FASE, True),
    "rh": {p: False for p in _PERMISSOES_DA_FASE} | {"auditoria.ler": True},
    "gestor": dict.fromkeys(_PERMISSOES_DA_FASE, False),
    "colaborador": dict.fromkeys(_PERMISSOES_DA_FASE, False),
    "auditor": {p: False for p in _PERMISSOES_DA_FASE}
    | {
        "sessoes.ler": True,
        "tenants.ler": True,
        "usuarios.ler": True,
        "perfis.ler": True,
        "permissoes.ler": True,
        "api_clients.ler": True,
        "auditoria.ler": True,
    },
    "integracao": dict.fromkeys(_PERMISSOES_DA_FASE, False),
}


@pytest.mark.parametrize("perfil_codigo", sorted(_MATRIZ_ESPERADA.keys()))
async def test_matriz_perfil_permissao(
    fabrica_sessoes: async_sessionmaker[AsyncSession],
    tenant_a_id: uuid.UUID,
    perfil_codigo: str,
) -> None:
    async with fabrica_sessoes() as sessao:
        await aplicar_tenant(sessao, tenant_a_id)
        usuario_id = await criar_usuario(
            sessao,
            tenant_id=tenant_a_id,
            email=f"matriz.{perfil_codigo}@f1a3.local",
            nome=f"Matriz {perfil_codigo}",
        )
        await atribuir_perfil(
            sessao,
            tenant_id=tenant_a_id,
            usuario_id=usuario_id,
            perfil_codigo=perfil_codigo,
            escopo_tipo="tenant",
        )
        await sessao.commit()
        # `commit()` encerra a transacao em que `SET LOCAL app.tenant_id`
        # valia (e' por transacao, ver `aplicar_tenant`/`app/db/sessao.py`):
        # sem reaplicar, a proxima consulta nesta MESMA sessao roda sem
        # tenant publicado e o RLS devolve zero linhas (falha fechada).
        await aplicar_tenant(sessao, tenant_a_id)

        sujeito = await resolver_sujeito(sessao, tenant_id=tenant_a_id, usuario_id=usuario_id)

    assert sujeito.autenticado is True
    esperado = _MATRIZ_ESPERADA[perfil_codigo]
    obtido = {codigo: (codigo in sujeito.permissoes) for codigo in _PERMISSOES_DA_FASE}
    assert obtido == esperado, f"perfil={perfil_codigo}: esperado {esperado}, obtido {obtido}"


async def test_auditor_e_somente_leitura(
    fabrica_sessoes: async_sessionmaker[AsyncSession], tenant_a_id: uuid.UUID
) -> None:
    """`perfis.somente_leitura=True` do auditor reflete em `Sujeito.perfis_somente_leitura`."""
    async with fabrica_sessoes() as sessao:
        await aplicar_tenant(sessao, tenant_a_id)
        usuario_id = await criar_usuario(
            sessao,
            tenant_id=tenant_a_id,
            email="matriz.auditor.flag@f1a3.local",
            nome="Auditor flag",
        )
        await atribuir_perfil(
            sessao,
            tenant_id=tenant_a_id,
            usuario_id=usuario_id,
            perfil_codigo="auditor",
            escopo_tipo="tenant",
        )
        await sessao.commit()
        # `commit()` encerra a transacao em que `SET LOCAL app.tenant_id`
        # valia (e' por transacao, ver `aplicar_tenant`/`app/db/sessao.py`):
        # sem reaplicar, a proxima consulta nesta MESMA sessao roda sem
        # tenant publicado e o RLS devolve zero linhas (falha fechada).
        await aplicar_tenant(sessao, tenant_a_id)

        sujeito = await resolver_sujeito(sessao, tenant_id=tenant_a_id, usuario_id=usuario_id)

    assert sujeito.perfis_somente_leitura is True
