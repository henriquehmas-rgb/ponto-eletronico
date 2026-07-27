"""T2 -- CRUD de empresas, validacao de CNPJ, coerencia matriz/filial,
unicidade de CNPJ por tenant e soft delete com recusa de dependente.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.organizacao import empresas
from app.organizacao.paginacao import PedidoDePagina
from tests.f2.conftest import ContextoOrganizacional


def _pedido() -> PedidoDePagina:
    # camelCase de proposito -- `empresas.CAMPOS_ORDENAVEIS` usa as mesmas
    # chaves do contrato (`ordenar`), nao os nomes de coluna do banco (achado
    # real da F9b, corrigido pelo orquestrador; ver comentario no dicionario).
    return PedidoDePagina(ordenar="criadoEm:desc", limite=20, deslocamento=0)


@pytest.mark.asyncio
async def test_criar_empresa_matriz_com_cnpj_valido(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    empresa = await empresas.criar_empresa(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        usuario_id=None,
        matriz_id=None,
        tipo="matriz",
        cnpj="07.653.576/0001-05",
        razao_social="Nova Matriz Ltda",
    )
    assert empresa.cnpj == "07653576000105"
    assert empresa.tipo == "matriz"
    assert empresa.matriz_id is None


@pytest.mark.asyncio
async def test_criar_empresa_com_cnpj_invalido_e_recusada(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await empresas.criar_empresa(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            usuario_id=None,
            matriz_id=None,
            tipo="matriz",
            cnpj="11222333000180",  # digito verificador errado (correto e 81)
            razao_social="Empresa Invalida",
        )
    assert excinfo.value.codigo == "PONTO-VAL-003"


@pytest.mark.asyncio
async def test_filial_sem_matriz_id_e_recusada(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await empresas.criar_empresa(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            usuario_id=None,
            matriz_id=None,
            tipo="filial",
            cnpj="12345678000195",
            razao_social="Filial Sem Matriz",
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_matriz_com_matriz_id_e_recusada(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await empresas.criar_empresa(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            usuario_id=None,
            matriz_id=contexto_organizacional.empresa_matriz_id,
            tipo="matriz",
            cnpj="12345678000195",
            razao_social="Matriz com matrizId",
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_cnpj_duplicado_no_mesmo_tenant_e_conflito(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await empresas.criar_empresa(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            usuario_id=None,
            matriz_id=None,
            tipo="matriz",
            cnpj=contexto_organizacional.empresa_matriz_cnpj,
            razao_social="Empresa Duplicada",
        )
    assert excinfo.value.codigo == "PONTO-CONF-001"


@pytest.mark.asyncio
async def test_criar_filial_valida_aponta_para_matriz(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    filial = await empresas.criar_empresa(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        usuario_id=None,
        matriz_id=contexto_organizacional.empresa_matriz_id,
        tipo="filial",
        cnpj="12345678000195",
        razao_social="Segunda Filial",
    )
    assert filial.matriz_id == contexto_organizacional.empresa_matriz_id


@pytest.mark.asyncio
async def test_obter_empresa_inexistente_e_404(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    import uuid

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await empresas.obter_empresa(
            sessao_f2, tenant_id=contexto_organizacional.tenant_id, empresa_id=uuid.uuid4()
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


@pytest.mark.asyncio
async def test_listar_empresas_filtra_por_tipo(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    linhas = await empresas.listar_empresas(
        sessao_f2, tenant_id=contexto_organizacional.tenant_id, pedido=_pedido(), tipo="filial"
    )
    assert len(linhas) >= 1
    assert all(linha.tipo == "filial" for linha in linhas)


@pytest.mark.asyncio
async def test_excluir_matriz_com_filial_ativa_e_recusada(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await empresas.excluir_empresa(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            empresa_id=contexto_organizacional.empresa_matriz_id,
            usuario_id=None,
        )
    assert excinfo.value.codigo == "PONTO-CONF-004"


@pytest.mark.asyncio
async def test_excluir_filial_sem_dependente_funciona(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    filial = await empresas.criar_empresa(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        usuario_id=None,
        matriz_id=contexto_organizacional.empresa_matriz_id,
        tipo="filial",
        cnpj="12345678000195",
        razao_social="Filial Descartavel",
    )
    await empresas.excluir_empresa(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        empresa_id=filial.id,
        usuario_id=None,
    )

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await empresas.obter_empresa(
            sessao_f2, tenant_id=contexto_organizacional.tenant_id, empresa_id=filial.id
        )
    assert excinfo.value.codigo == "PONTO-REC-001"

    linhas = await empresas.listar_empresas(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        pedido=_pedido(),
        incluir_excluidos=True,
    )
    assert any(linha.id == filial.id and linha.excluido_em is not None for linha in linhas)


@pytest.mark.asyncio
async def test_atualizar_empresa_altera_campo_simples(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    atualizada = await empresas.atualizar_empresa(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        empresa_id=contexto_organizacional.empresa_matriz_id,
        usuario_id=None,
        dados={"nome_fantasia": "Novo Nome Fantasia"},
    )
    assert atualizada.nome_fantasia == "Novo Nome Fantasia"
