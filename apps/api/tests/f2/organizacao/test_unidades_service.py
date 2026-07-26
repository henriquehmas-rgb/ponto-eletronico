"""T3 -- CRUD de unidades (fuso, geocerca nas duas formas) e das tres
operacoes de `redes-permitidas`, incluindo IPv6.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.organizacao import unidades
from app.organizacao.paginacao import PedidoDePagina
from app.organizacao.redes import ip_autorizado
from tests.f2.conftest import ContextoOrganizacional


def _pedido() -> PedidoDePagina:
    return PedidoDePagina(ordenar="criado_em:desc", limite=20, deslocamento=0)


@pytest.mark.asyncio
async def test_criar_unidade_ponto_mais_raio(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    unidade = await unidades.criar_unidade(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        usuario_id=None,
        empresa_id=contexto_organizacional.empresa_matriz_id,
        codigo="NOVA-01",
        nome="Nova Unidade",
        geocerca_latitude=-23.5,
        geocerca_longitude=-46.6,
        geocerca_raio_metros=200,
    )
    assert unidade.geocerca_raio_metros == 200
    assert unidade.geocerca_poligono is None


@pytest.mark.asyncio
async def test_criar_unidade_geocerca_parcial_e_recusada(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await unidades.criar_unidade(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            usuario_id=None,
            empresa_id=contexto_organizacional.empresa_matriz_id,
            codigo="PARCIAL-01",
            nome="Unidade Parcial",
            geocerca_latitude=-23.5,
            # falta longitude e raio
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_criar_unidade_empresa_inexistente_e_404(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await unidades.criar_unidade(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            usuario_id=None,
            empresa_id=uuid.uuid4(),
            codigo="X",
            nome="X",
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


@pytest.mark.asyncio
async def test_obter_unidade_ponto_raio_e_poligono(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    ponto_raio = await unidades.obter_unidade(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        unidade_id=contexto_organizacional.unidade_ponto_raio_id,
    )
    assert ponto_raio.geocerca_latitude is not None
    assert ponto_raio.geocerca_poligono is None

    poligono = await unidades.obter_unidade(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        unidade_id=contexto_organizacional.unidade_poligono_id,
    )
    assert poligono.geocerca_poligono is not None
    assert poligono.geocerca_latitude is None


@pytest.mark.asyncio
async def test_geocerca_da_unidade_converte_para_estrutura_pura(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    from app.organizacao.geocerca import dentro_da_geocerca

    unidade = await unidades.obter_unidade(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        unidade_id=contexto_organizacional.unidade_ponto_raio_id,
    )
    estrutura = unidades.geocerca_da_unidade(unidade)
    assert estrutura.geocerca_latitude is not None
    assert estrutura.geocerca_longitude is not None
    resultado = dentro_da_geocerca(
        estrutura, estrutura.geocerca_latitude, estrutura.geocerca_longitude
    )
    assert resultado.dentro is True


@pytest.mark.asyncio
async def test_excluir_unidade_sem_dependente(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    unidade = await unidades.criar_unidade(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        usuario_id=None,
        empresa_id=contexto_organizacional.empresa_matriz_id,
        codigo="DESCARTAVEL",
        nome="Descartavel",
    )
    await unidades.excluir_unidade(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        unidade_id=unidade.id,
        usuario_id=None,
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await unidades.obter_unidade(
            sessao_f2, tenant_id=contexto_organizacional.tenant_id, unidade_id=unidade.id
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


class TestRedesPermitidas:
    @pytest.mark.asyncio
    async def test_criar_rede_ipv4(
        self, sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
    ) -> None:
        rede = await unidades.criar_rede_permitida(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            usuario_id=None,
            unidade_id=contexto_organizacional.unidade_ponto_raio_id,
            empresa_id=None,
            cidr="200.150.10.0/24",
        )
        assert str(rede.cidr).startswith("200.150.10.0")

    @pytest.mark.asyncio
    async def test_criar_rede_ipv6(
        self, sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
    ) -> None:
        rede = await unidades.criar_rede_permitida(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            usuario_id=None,
            unidade_id=contexto_organizacional.unidade_ponto_raio_id,
            empresa_id=None,
            cidr="2001:db8::/32",
            canal="web",
        )
        assert "2001:db8" in str(rede.cidr)

    @pytest.mark.asyncio
    async def test_cidr_invalido_e_recusado(
        self, sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
    ) -> None:
        with pytest.raises(ErroDeAplicacao) as excinfo:
            await unidades.criar_rede_permitida(
                sessao_f2,
                tenant_id=contexto_organizacional.tenant_id,
                usuario_id=None,
                unidade_id=contexto_organizacional.unidade_ponto_raio_id,
                empresa_id=None,
                cidr="nao-e-cidr",
            )
        assert excinfo.value.codigo == "PONTO-VAL-001"

    @pytest.mark.asyncio
    async def test_listar_e_excluir_rede(
        self, sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
    ) -> None:
        rede = await unidades.criar_rede_permitida(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            usuario_id=None,
            unidade_id=contexto_organizacional.unidade_ponto_raio_id,
            empresa_id=None,
            cidr="10.0.0.0/8",
        )
        listadas = await unidades.listar_redes_permitidas(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            unidade_id=contexto_organizacional.unidade_ponto_raio_id,
            pedido=_pedido(),
        )
        assert any(linha.id == rede.id for linha in listadas)

        await unidades.excluir_rede_permitida(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            unidade_id=contexto_organizacional.unidade_ponto_raio_id,
            rede_id=rede.id,
        )
        listadas_depois = await unidades.listar_redes_permitidas(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            unidade_id=contexto_organizacional.unidade_ponto_raio_id,
            pedido=_pedido(),
        )
        assert all(linha.id != rede.id for linha in listadas_depois)

    @pytest.mark.asyncio
    async def test_ip_autorizado_ponta_a_ponta_com_banco(
        self, sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
    ) -> None:
        await unidades.criar_rede_permitida(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            usuario_id=None,
            unidade_id=contexto_organizacional.unidade_ponto_raio_id,
            empresa_id=None,
            cidr="2001:db8::/32",
        )
        faixas = await unidades.redes_autorizadas_para(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            empresa_id=contexto_organizacional.empresa_matriz_id,
            unidade_id=contexto_organizacional.unidade_ponto_raio_id,
        )
        assert ip_autorizado(faixas, "2001:db8:1::1") is True
        assert ip_autorizado(faixas, "8.8.8.8") is False
