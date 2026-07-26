"""T4 -- departamentos e centros de custo hierarquicos (com deteccao de
ciclo), cargos (com CBO) e equipes (com sobreposicao de participacao
recusada pela constraint `EXCLUDE`).
"""

from __future__ import annotations

import datetime
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.organizacao import estrutura
from app.organizacao.paginacao import PedidoDePagina
from tests.f2.conftest import ContextoOrganizacional


def _pedido() -> PedidoDePagina:
    return PedidoDePagina(ordenar="criado_em:desc", limite=20, deslocamento=0)


async def _novo_colaborador(
    sessao: AsyncSession, tenant_id: uuid.UUID, empresa_id: uuid.UUID
) -> uuid.UUID:
    """Cria um colaborador minimo via SQL direto (a validacao completa de
    colaborador e da tag `colaboradores`, ownership do agente A2; aqui so
    precisamos de uma FK valida para os testes de equipe/gestor)."""
    from sqlalchemy import text

    colaborador_id = uuid.uuid4()
    sufixo = uuid.uuid4().hex[:8]
    await sessao.execute(
        text(
            "INSERT INTO colaboradores "
            "(id, tenant_id, empresa_id, cpf, nome_completo, matricula, status) "
            "VALUES (:id, :tenant_id, :empresa_id, :cpf, :nome, :matricula, 'ativo')"
        ),
        {
            "id": colaborador_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "cpf": "11144477735",
            "nome": f"Colaborador Teste {sufixo}",
            "matricula": f"MAT-{sufixo}",
        },
    )
    return colaborador_id


class TestDepartamentos:
    @pytest.mark.asyncio
    async def test_criar_departamento_raiz(
        self, sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
    ) -> None:
        depto = await estrutura.criar_departamento(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            usuario_id=None,
            empresa_id=contexto_organizacional.empresa_matriz_id,
            codigo="TI",
            nome="Tecnologia",
        )
        assert depto.departamento_pai_id is None

    @pytest.mark.asyncio
    async def test_departamento_filho_do_proprio_neto_e_recusado(
        self, sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
    ) -> None:
        avo = await estrutura.criar_departamento(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            usuario_id=None,
            empresa_id=contexto_organizacional.empresa_matriz_id,
            codigo="AVO",
            nome="Avo",
        )
        pai = await estrutura.criar_departamento(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            usuario_id=None,
            empresa_id=contexto_organizacional.empresa_matriz_id,
            codigo="PAI",
            nome="Pai",
            departamento_pai_id=avo.id,
        )
        neto = await estrutura.criar_departamento(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            usuario_id=None,
            empresa_id=contexto_organizacional.empresa_matriz_id,
            codigo="NETO",
            nome="Neto",
            departamento_pai_id=pai.id,
        )

        with pytest.raises(ErroDeAplicacao) as excinfo:
            await estrutura.atualizar_departamento(
                sessao_f2,
                tenant_id=contexto_organizacional.tenant_id,
                departamento_id=avo.id,
                usuario_id=None,
                dados={"departamento_pai_id": neto.id},
            )
        assert excinfo.value.codigo == "PONTO-CONF-003"

    @pytest.mark.asyncio
    async def test_departamento_pai_de_si_mesmo_e_recusado(
        self, sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
    ) -> None:
        depto = await estrutura.criar_departamento(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            usuario_id=None,
            empresa_id=contexto_organizacional.empresa_matriz_id,
            codigo="SOLO",
            nome="Solo",
        )
        with pytest.raises(ErroDeAplicacao) as excinfo:
            await estrutura.atualizar_departamento(
                sessao_f2,
                tenant_id=contexto_organizacional.tenant_id,
                departamento_id=depto.id,
                usuario_id=None,
                dados={"departamento_pai_id": depto.id},
            )
        assert excinfo.value.codigo == "PONTO-CONF-003"

    @pytest.mark.asyncio
    async def test_excluir_departamento_com_filho_e_recusado(
        self, sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
    ) -> None:
        pai = await estrutura.criar_departamento(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            usuario_id=None,
            empresa_id=contexto_organizacional.empresa_matriz_id,
            codigo="PAI2",
            nome="Pai2",
        )
        await estrutura.criar_departamento(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            usuario_id=None,
            empresa_id=contexto_organizacional.empresa_matriz_id,
            codigo="FILHO2",
            nome="Filho2",
            departamento_pai_id=pai.id,
        )
        with pytest.raises(ErroDeAplicacao) as excinfo:
            await estrutura.excluir_departamento(
                sessao_f2,
                tenant_id=contexto_organizacional.tenant_id,
                departamento_id=pai.id,
                usuario_id=None,
            )
        assert excinfo.value.codigo == "PONTO-CONF-004"


class TestCentrosCusto:
    @pytest.mark.asyncio
    async def test_centro_de_custo_filho_do_proprio_neto_e_recusado(
        self, sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
    ) -> None:
        avo = await estrutura.criar_centro_custo(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            usuario_id=None,
            empresa_id=contexto_organizacional.empresa_matriz_id,
            codigo="CC-AVO",
            nome="CC Avo",
        )
        pai = await estrutura.criar_centro_custo(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            usuario_id=None,
            empresa_id=contexto_organizacional.empresa_matriz_id,
            codigo="CC-PAI",
            nome="CC Pai",
            centro_custo_pai_id=avo.id,
        )
        with pytest.raises(ErroDeAplicacao) as excinfo:
            await estrutura.atualizar_centro_custo(
                sessao_f2,
                tenant_id=contexto_organizacional.tenant_id,
                centro_custo_id=pai.id,
                usuario_id=None,
                dados={"centro_custo_pai_id": pai.id},
            )
        assert excinfo.value.codigo == "PONTO-CONF-003"

        with pytest.raises(ErroDeAplicacao) as excinfo2:
            await estrutura.atualizar_centro_custo(
                sessao_f2,
                tenant_id=contexto_organizacional.tenant_id,
                centro_custo_id=avo.id,
                usuario_id=None,
                dados={"centro_custo_pai_id": pai.id},
            )
        assert excinfo2.value.codigo == "PONTO-CONF-003"


class TestCargos:
    @pytest.mark.asyncio
    async def test_cargo_com_cbo_valido(
        self, sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
    ) -> None:
        cargo = await estrutura.criar_cargo(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            usuario_id=None,
            empresa_id=contexto_organizacional.empresa_matriz_id,
            codigo="DEV",
            nome="Desenvolvedor",
            cbo="317110",
        )
        assert cargo.cbo == "317110"

    @pytest.mark.asyncio
    async def test_cargo_com_cbo_de_5_digitos_e_recusado(
        self, sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
    ) -> None:
        with pytest.raises(ErroDeAplicacao) as excinfo:
            await estrutura.criar_cargo(
                sessao_f2,
                tenant_id=contexto_organizacional.tenant_id,
                usuario_id=None,
                empresa_id=contexto_organizacional.empresa_matriz_id,
                codigo="DEV2",
                nome="Desenvolvedor 2",
                cbo="31711",
            )
        assert excinfo.value.codigo == "PONTO-VAL-001"


class TestEquipes:
    @pytest.mark.asyncio
    async def test_criar_equipe_e_adicionar_membro(
        self, sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
    ) -> None:
        equipe = await estrutura.criar_equipe(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            usuario_id=None,
            empresa_id=contexto_organizacional.empresa_matriz_id,
            codigo="EQ1",
            nome="Equipe 1",
        )
        colaborador_id = await _novo_colaborador(
            sessao_f2, contexto_organizacional.tenant_id, contexto_organizacional.empresa_matriz_id
        )
        membro = await estrutura.adicionar_membro_equipe(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            equipe_id=equipe.id,
            usuario_id=None,
            colaborador_id=colaborador_id,
        )
        assert membro.equipe_id == equipe.id
        assert membro.colaborador_id == colaborador_id

    @pytest.mark.asyncio
    async def test_mesmo_colaborador_mesma_equipe_periodos_sobrepostos_e_recusado(
        self, sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
    ) -> None:
        equipe = await estrutura.criar_equipe(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            usuario_id=None,
            empresa_id=contexto_organizacional.empresa_matriz_id,
            codigo="EQ2",
            nome="Equipe 2",
        )
        colaborador_id = await _novo_colaborador(
            sessao_f2, contexto_organizacional.tenant_id, contexto_organizacional.empresa_matriz_id
        )
        await estrutura.adicionar_membro_equipe(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            equipe_id=equipe.id,
            usuario_id=None,
            colaborador_id=colaborador_id,
            vigencia_inicio=datetime.date(2026, 1, 1),
            vigencia_fim=datetime.date(2026, 6, 30),
        )
        with pytest.raises(ErroDeAplicacao) as excinfo:
            await estrutura.adicionar_membro_equipe(
                sessao_f2,
                tenant_id=contexto_organizacional.tenant_id,
                equipe_id=equipe.id,
                usuario_id=None,
                colaborador_id=colaborador_id,
                vigencia_inicio=datetime.date(2026, 3, 1),
                vigencia_fim=datetime.date(2026, 9, 30),
            )
        assert excinfo.value.codigo == "PONTO-VAL-010"

    @pytest.mark.asyncio
    async def test_mesmo_colaborador_mesma_equipe_periodos_nao_sobrepostos_e_aceito(
        self, sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
    ) -> None:
        equipe = await estrutura.criar_equipe(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            usuario_id=None,
            empresa_id=contexto_organizacional.empresa_matriz_id,
            codigo="EQ3",
            nome="Equipe 3",
        )
        colaborador_id = await _novo_colaborador(
            sessao_f2, contexto_organizacional.tenant_id, contexto_organizacional.empresa_matriz_id
        )
        await estrutura.adicionar_membro_equipe(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            equipe_id=equipe.id,
            usuario_id=None,
            colaborador_id=colaborador_id,
            vigencia_inicio=datetime.date(2026, 1, 1),
            vigencia_fim=datetime.date(2026, 6, 30),
        )
        membro2 = await estrutura.adicionar_membro_equipe(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            equipe_id=equipe.id,
            usuario_id=None,
            colaborador_id=colaborador_id,
            vigencia_inicio=datetime.date(2026, 7, 1),
            vigencia_fim=None,
        )
        assert membro2.vigencia_inicio == datetime.date(2026, 7, 1)
