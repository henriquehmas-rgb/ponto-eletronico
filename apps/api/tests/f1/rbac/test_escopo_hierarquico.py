"""Criterio de aceite 7: `PONTO-PERM-001` (permissao ausente) e
`PONTO-PERM-002` (permissao presente, alvo fora da arvore) sao erros
distintos e nao devem ser confundidos (T8).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.erros import ErroDeAplicacao
from app.core.seguranca import exigir_alcance, exigir_permissao
from app.identidade.rbac.resolucao import resolver_sujeito
from tests.f1.rbac._apoio import (
    atribuir_perfil,
    criar_empresa,
    criar_unidade,
    criar_usuario,
)
from tests.f1.rbac.conftest import aplicar_tenant


async def test_permissao_ausente_e_perm_001(
    fabrica_sessoes: async_sessionmaker[AsyncSession], tenant_a_id: uuid.UUID
) -> None:
    """`colaborador` nao tem `usuarios.ler`: a dependencia recusa com PERM-001."""
    async with fabrica_sessoes() as sessao:
        await aplicar_tenant(sessao, tenant_a_id)
        usuario_id = await criar_usuario(
            sessao, tenant_id=tenant_a_id, email="escopo.colaborador@f1a3.local", nome="Colaborador"
        )
        await atribuir_perfil(
            sessao,
            tenant_id=tenant_a_id,
            usuario_id=usuario_id,
            perfil_codigo="colaborador",
            escopo_tipo="proprio",
        )
        await sessao.commit()
        # `commit()` fecha a transacao onde `SET LOCAL app.tenant_id` valia;
        # sem reaplicar, a consulta seguinte nesta mesma sessao roda sem
        # tenant publicado e o RLS devolve zero linhas.
        await aplicar_tenant(sessao, tenant_a_id)
        sujeito = await resolver_sujeito(sessao, tenant_id=tenant_a_id, usuario_id=usuario_id)

    verificar = exigir_permissao("usuarios.ler")
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await verificar(sujeito=sujeito)
    assert excinfo.value.codigo == "PONTO-PERM-001"


async def test_alcance_fora_da_arvore_e_perm_002(
    fabrica_sessoes: async_sessionmaker[AsyncSession], tenant_a_id: uuid.UUID
) -> None:
    """Gestor com escopo na unidade X recebe PERM-002 ao alcancar um alvo da unidade Y,
    mesmo tendo a permissao (o que descarta PERM-001 nesse caminho)."""
    async with fabrica_sessoes() as sessao:
        await aplicar_tenant(sessao, tenant_a_id)
        # CNPJ aleatorio (14 digitos, so formato -- o digito verificador nao e
        # validado no banco, ver `schema.sql`): `uq_empresas_cnpj` e por
        # tenant, e este teste roda repetidas vezes contra o mesmo tenant
        # semeado entre execucoes de processo.
        cnpj_aleatorio = f"{uuid.uuid4().int % 10**14:014d}"
        empresa_id = await criar_empresa(
            sessao, tenant_id=tenant_a_id, cnpj=cnpj_aleatorio, razao_social="Empresa escopo F1A3"
        )
        unidade_x = await criar_unidade(
            sessao, tenant_id=tenant_a_id, empresa_id=empresa_id, codigo="UX", nome="Unidade X"
        )
        unidade_y = await criar_unidade(
            sessao, tenant_id=tenant_a_id, empresa_id=empresa_id, codigo="UY", nome="Unidade Y"
        )
        usuario_id = await criar_usuario(
            sessao, tenant_id=tenant_a_id, email="escopo.gestor@f1a3.local", nome="Gestor unidade X"
        )
        # `gestor` nao tem nenhuma das 16 permissoes desta fase (ver
        # test_matriz_perfis.py); usamos `rh` para ter uma permissao real
        # (`auditoria.ler`) e provar PERM-002 sem se confundir com PERM-001.
        await atribuir_perfil(
            sessao,
            tenant_id=tenant_a_id,
            usuario_id=usuario_id,
            perfil_codigo="rh",
            escopo_tipo="unidade",
            unidade_id=unidade_x,
            incluir_subordinados=False,
        )
        await sessao.commit()
        # `commit()` fecha a transacao onde `SET LOCAL app.tenant_id` valia;
        # sem reaplicar, a consulta seguinte nesta mesma sessao roda sem
        # tenant publicado e o RLS devolve zero linhas.
        await aplicar_tenant(sessao, tenant_a_id)
        sujeito = await resolver_sujeito(sessao, tenant_id=tenant_a_id, usuario_id=usuario_id)

    assert sujeito.alcance is not None
    assert sujeito.alcance.amplo_tenant is False
    assert unidade_x in sujeito.alcance.unidades
    assert unidade_y not in sujeito.alcance.unidades

    verificar = exigir_permissao("auditoria.ler")
    sujeito_verificado = await verificar(sujeito=sujeito)

    # Alvo dentro da arvore: passa.
    exigir_alcance(sujeito_verificado, unidade_id=unidade_x)

    # Alvo fora da arvore: PERM-002, nao PERM-001 (a permissao existe).
    with pytest.raises(ErroDeAplicacao) as excinfo:
        exigir_alcance(sujeito_verificado, unidade_id=unidade_y)
    assert excinfo.value.codigo == "PONTO-PERM-002"
