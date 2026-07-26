"""Testes de `app.terminais.servico` (T3 do PCF da F6, agente A1) contra o
banco real (RLS), conectado como a role restrita `ponto_teste_f6_a1`.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from app.terminais import cifra, servico
from tests.f6.conftest import TenantSemeado

pytestmark = pytest.mark.asyncio


def _dados_criar(
    tenant: TenantSemeado, *, numero_serie: str | None = None, senha_api: str | None = None
) -> esquemas.TerminalCriar:
    return esquemas.TerminalCriar(
        empresaId=tenant.empresa_id,
        unidadeId=tenant.unidade_id,
        fabricante=esquemas.Fabricante.control_id,
        numeroSerie=numero_serie or f"IDF-TESTE-{uuid4().hex[:10]}",
        modoComunicacao=esquemas.ModoComunicacao.push,
        senhaApi=senha_api,
    )


async def test_criar_terminal_sem_dispositivo_id_cria_dispositivo(
    sessao_tenant: AsyncSession, tenant_f6: TenantSemeado
) -> None:
    dados = _dados_criar(tenant_f6)
    terminal = await servico.criar_terminal(sessao_tenant, tenant_f6.id, dados, None)
    assert terminal.dispositivo_id is not None

    linha = (
        await sessao_tenant.execute(
            text("SELECT tipo, identificador FROM dispositivos WHERE id = :id"),
            {"id": str(terminal.dispositivo_id)},
        )
    ).first()
    assert linha is not None
    assert linha.tipo == "terminal"
    assert linha.identificador == dados.numero_serie


async def test_criar_dois_terminais_mesmo_numero_serie_e_conf_001(
    sessao_tenant: AsyncSession, tenant_f6: TenantSemeado
) -> None:
    numero_serie = f"IDF-DUP-{uuid4().hex[:10]}"
    await servico.criar_terminal(
        sessao_tenant, tenant_f6.id, _dados_criar(tenant_f6, numero_serie=numero_serie), None
    )
    await sessao_tenant.flush()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_terminal(
            sessao_tenant, tenant_f6.id, _dados_criar(tenant_f6, numero_serie=numero_serie), None
        )
    assert excinfo.value.codigo == "PONTO-CONF-001"


async def test_senha_api_nunca_em_claro_e_nunca_na_leitura(
    sessao_tenant: AsyncSession, tenant_f6: TenantSemeado
) -> None:
    dados = _dados_criar(tenant_f6, senha_api="senha-do-equipamento-em-claro")
    terminal = await servico.criar_terminal(sessao_tenant, tenant_f6.id, dados, None)
    await sessao_tenant.flush()

    linha = (
        await sessao_tenant.execute(
            text("SELECT senha_api_cifrada FROM terminais WHERE id = :id"), {"id": str(terminal.id)}
        )
    ).first()
    assert linha is not None
    blob = bytes(linha.senha_api_cifrada)
    assert b"senha-do-equipamento-em-claro" not in blob
    assert cifra.decifrar_senha(blob) == "senha-do-equipamento-em-claro"

    resposta = servico.montar_resposta_terminal(terminal)
    assert not hasattr(resposta, "senha_api")
    assert "senhaApi" not in resposta.model_dump(by_alias=True)


async def test_atualizar_e_excluir_terminal(
    sessao_tenant: AsyncSession, tenant_f6: TenantSemeado
) -> None:
    terminal = await servico.criar_terminal(
        sessao_tenant, tenant_f6.id, _dados_criar(tenant_f6), None
    )
    await sessao_tenant.flush()

    atualizado = await servico.atualizar_terminal(
        sessao_tenant,
        tenant_f6.id,
        terminal.id,
        esquemas.TerminalAtualizar(modelo="iDFace Max"),
        None,
    )
    assert atualizado.modelo == "iDFace Max"

    await servico.excluir_terminal(sessao_tenant, tenant_f6.id, terminal.id, None)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.obter_terminal(sessao_tenant, tenant_f6.id, terminal.id)
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_terminal_saude_e_append_only_para_ponto_app(
    sessao_tenant: AsyncSession, tenant_f6: TenantSemeado, engine_app_role: AsyncEngine
) -> None:
    """Criterio de aceite 5: a role `ponto_app` nao consegue UPDATE/DELETE em
    `terminal_saude`."""
    terminal = await servico.criar_terminal(
        sessao_tenant, tenant_f6.id, _dados_criar(tenant_f6), None
    )
    await sessao_tenant.commit()

    async with engine_app_role.begin() as conexao:
        await conexao.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant_f6.id)}
        )
        await conexao.execute(
            text(
                "INSERT INTO terminal_saude (tenant_id, terminal_id, online) "
                "VALUES (:tenant_id, :terminal_id, TRUE)"
            ),
            {"tenant_id": str(tenant_f6.id), "terminal_id": str(terminal.id)},
        )

    with pytest.raises(sa.exc.DBAPIError):
        async with engine_app_role.begin() as conexao:
            await conexao.execute(
                text("SELECT set_config('app.tenant_id', :tenant, true)"),
                {"tenant": str(tenant_f6.id)},
            )
            await conexao.execute(
                text("UPDATE terminal_saude SET online = FALSE WHERE terminal_id = :id"),
                {"id": str(terminal.id)},
            )
