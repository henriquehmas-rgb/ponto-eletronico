"""Testes de `app/biometria/dispositivos.py` (T9 do PCF da F2).

Cobre o criterio de aceite 6 da secao 7 (um dispositivo ativo por
colaborador) e a exclusao logica com revogacao em cascata dos vinculos
ativos.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.biometria import dispositivos as servico
from app.core.erros import ErroDeAplicacao
from tests.f2.conftest import ContextoOrganizacional

pytestmark = pytest.mark.asyncio


def _dados_dispositivo(
    identificador: str, *, tipo: str = "celular"
) -> servico.DadosDispositivoCriar:
    return servico.DadosDispositivoCriar(
        empresa_id=None,
        unidade_id=None,
        tipo=tipo,
        plataforma="android",
        identificador=identificador,
        nome="Celular de teste",
        fabricante="Motorola",
        modelo="XT2335-1",
        versao_so="14",
        versao_app="1.0.0",
        status=None,
        root_detectado=False,
        emulador_detectado=False,
        modo_desenvolvedor=False,
        depuracao_usb=False,
        observacoes=None,
    )


async def test_criar_dispositivo_nasce_pendente(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    dispositivo = await servico.criar_dispositivo(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        dados=_dados_dispositivo(f"id-{uuid4()}"),
        usuario_id=None,
    )
    assert dispositivo.status == "pendente"
    assert dispositivo.root_detectado is False


async def test_vincular_dispositivo_aprovado_fica_ativo_e_e_encontrado(
    sessao_f2: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
) -> None:
    colaborador_id = await criar_colaborador()
    dispositivo = await servico.criar_dispositivo(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        dados=_dados_dispositivo(f"id-{uuid4()}"),
        usuario_id=None,
    )

    await servico.vincular_dispositivo(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        dispositivo_id=dispositivo.id,
        colaborador_id=colaborador_id,
        aprovar_imediatamente=True,
        revogar_anterior=False,
        motivo=None,
        usuario_id=None,
    )

    vinculado = await servico.colaborador_vinculado_atual(
        sessao_f2, tenant_id=contexto_organizacional.tenant_id, dispositivo_id=dispositivo.id
    )
    assert vinculado == colaborador_id


async def test_segundo_dispositivo_ativo_do_mesmo_colaborador_e_disp_006(
    sessao_f2: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
) -> None:
    """Criterio 6: um unico dispositivo ativo por colaborador
    (`uq_dispositivo_vinculos_ativo` -> PONTO-DISP-006)."""
    colaborador_id = await criar_colaborador()

    dispositivo_1 = await servico.criar_dispositivo(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        dados=_dados_dispositivo(f"id-{uuid4()}"),
        usuario_id=None,
    )
    await servico.vincular_dispositivo(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        dispositivo_id=dispositivo_1.id,
        colaborador_id=colaborador_id,
        aprovar_imediatamente=True,
        revogar_anterior=False,
        motivo=None,
        usuario_id=None,
    )

    dispositivo_2 = await servico.criar_dispositivo(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        dados=_dados_dispositivo(f"id-{uuid4()}"),
        usuario_id=None,
    )

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.vincular_dispositivo(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            dispositivo_id=dispositivo_2.id,
            colaborador_id=colaborador_id,
            aprovar_imediatamente=True,
            revogar_anterior=False,
            motivo=None,
            usuario_id=None,
        )
    assert excinfo.value.codigo == "PONTO-DISP-006"


async def test_vincular_com_revogar_anterior_troca_o_dispositivo_ativo(
    sessao_f2: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
) -> None:
    """A troca de aparelho e permitida quando pedida explicitamente
    (`revogarAnterior=True`), e fica registrada (PCF secao 2)."""
    colaborador_id = await criar_colaborador()

    dispositivo_1 = await servico.criar_dispositivo(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        dados=_dados_dispositivo(f"id-{uuid4()}"),
        usuario_id=None,
    )
    await servico.vincular_dispositivo(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        dispositivo_id=dispositivo_1.id,
        colaborador_id=colaborador_id,
        aprovar_imediatamente=True,
        revogar_anterior=False,
        motivo=None,
        usuario_id=None,
    )

    dispositivo_2 = await servico.criar_dispositivo(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        dados=_dados_dispositivo(f"id-{uuid4()}"),
        usuario_id=None,
    )
    await servico.vincular_dispositivo(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        dispositivo_id=dispositivo_2.id,
        colaborador_id=colaborador_id,
        aprovar_imediatamente=True,
        revogar_anterior=True,
        motivo="Troca de aparelho",
        usuario_id=None,
    )

    vinculado_1 = await servico.colaborador_vinculado_atual(
        sessao_f2, tenant_id=contexto_organizacional.tenant_id, dispositivo_id=dispositivo_1.id
    )
    vinculado_2 = await servico.colaborador_vinculado_atual(
        sessao_f2, tenant_id=contexto_organizacional.tenant_id, dispositivo_id=dispositivo_2.id
    )
    assert vinculado_1 is None
    assert vinculado_2 == colaborador_id


async def test_excluir_dispositivo_revoga_vinculos_ativos(
    sessao_f2: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
) -> None:
    colaborador_id = await criar_colaborador()
    dispositivo = await servico.criar_dispositivo(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        dados=_dados_dispositivo(f"id-{uuid4()}"),
        usuario_id=None,
    )
    await servico.vincular_dispositivo(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        dispositivo_id=dispositivo.id,
        colaborador_id=colaborador_id,
        aprovar_imediatamente=True,
        revogar_anterior=False,
        motivo=None,
        usuario_id=None,
    )

    await servico.excluir_dispositivo(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        dispositivo_id=dispositivo.id,
        usuario_id=None,
    )

    excluido = await servico.obter_dispositivo(
        sessao_f2, tenant_id=contexto_organizacional.tenant_id, dispositivo_id=dispositivo.id
    )
    assert excluido.excluido_em is not None

    vinculado = await servico.colaborador_vinculado_atual(
        sessao_f2, tenant_id=contexto_organizacional.tenant_id, dispositivo_id=dispositivo.id
    )
    assert vinculado is None


async def test_identificador_duplicado_no_mesmo_tenant_e_conf_001(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    identificador = f"id-{uuid4()}"
    await servico.criar_dispositivo(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        dados=_dados_dispositivo(identificador),
        usuario_id=None,
    )

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_dispositivo(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            dados=_dados_dispositivo(identificador),
            usuario_id=None,
        )
    assert excinfo.value.codigo == "PONTO-CONF-001"
