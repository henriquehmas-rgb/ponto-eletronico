"""T1/T7 -- `criarRepP`/`listarRepPs` (`app.fiscal.rep_p.servico`)."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from ponto_contracts import NsrSequencia
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.fiscal.rep_p.servico import criar_rep_p, listar_rep_ps
from app.schemas import contrato as esquemas
from tests.f12.conftest import ContextoF12, aplicar_tenant_teste


def _dados_rep_p_criar(**sobrescreve: object) -> esquemas.RepPCriar:
    base: dict[str, object] = {
        "empresa_id": uuid.uuid4(),
        "identificador": f"REPP-{uuid.uuid4().hex[:8]}",
        "numero_inpi": "512026000123999",
        "cnpj_empregador": "60258502000230",
        "razao_social_empregador": "Empresa de Teste F12 Ltda - Filial",
        "versao_programa": "1.0.0",
        "data_inicio_operacao": dt.date(2026, 1, 1),
    }
    base.update(sobrescreve)
    return esquemas.RepPCriar.model_validate(base)


@pytest.mark.asyncio
async def test_criar_rep_p_inicializa_nsr_sequencias_corretamente(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12
) -> None:
    """Pronto quando (T1): "teste prova que criarRepP cria a linha em
    nsr_sequencias corretamente inicializada"."""
    dados = _dados_rep_p_criar(empresa_id=contexto_f12.empresa_id)

    criado = await criar_rep_p(sessao_f12, contexto_f12.tenant_id, dados, usuario_id=None)

    assert criado.id is not None
    assert criado.proximo_nsr == 1
    assert criado.ultimo_nsr_emitido == 0
    assert criado.numero_inpi == dados.numero_inpi
    assert criado.status == esquemas.Status22.ativo

    await aplicar_tenant_teste(sessao_f12, contexto_f12.tenant_id)
    sequencia = (
        await sessao_f12.execute(
            sa.select(NsrSequencia).where(
                NsrSequencia.tenant_id == contexto_f12.tenant_id,
                NsrSequencia.rep_p_id == criado.id,
            )
        )
    ).scalar_one()
    assert sequencia.proximo_nsr == 1
    assert sequencia.ultimo_nsr_emitido == 0


@pytest.mark.asyncio
async def test_criar_rep_p_sem_cnpj_desenvolvedor_usa_identidade_fixa_da_seeg(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12
) -> None:
    """Achado de contrato documentado em `app.fiscal.rep_p.servico`:
    `RepPCriar.cnpjDesenvolvedor`/`razaoSocialDesenvolvedor` não são
    `required`, mas `rep_ps.cnpj_desenvolvedor`/`razao_social_desenvolvedor`
    são `NOT NULL` -- este serviço preenche com a identidade fixa da SEEG
    quando ausentes, igual ao `ExemploRepP` do próprio contrato."""
    dados = _dados_rep_p_criar(empresa_id=contexto_f12.empresa_id)
    assert dados.cnpj_desenvolvedor is None

    criado = await criar_rep_p(sessao_f12, contexto_f12.tenant_id, dados, usuario_id=None)

    assert criado.cnpj_desenvolvedor == "60258502000149"
    assert criado.razao_social_desenvolvedor == "SEEG Servicos de Tecnologia da Informacao LTDA"


@pytest.mark.asyncio
async def test_criar_rep_p_identificador_duplicado_responde_conf_001(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12
) -> None:
    dados = _dados_rep_p_criar(empresa_id=contexto_f12.empresa_id, identificador="REPP-DUP")
    await criar_rep_p(sessao_f12, contexto_f12.tenant_id, dados, usuario_id=None)

    dados_repetidos = _dados_rep_p_criar(
        empresa_id=contexto_f12.empresa_id,
        identificador="REPP-DUP",
        numero_inpi="512026000124000",
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await criar_rep_p(sessao_f12, contexto_f12.tenant_id, dados_repetidos, usuario_id=None)
    assert excinfo.value.codigo == "PONTO-CONF-001"


@pytest.mark.asyncio
async def test_listar_rep_ps_filtra_por_empresa_e_status(
    sessao_f12: AsyncSession, contexto_f12: ContextoF12
) -> None:
    outra_empresa_id = uuid.uuid4()
    await sessao_f12.execute(
        sa.text(
            "INSERT INTO empresas "
            "(id, tenant_id, tipo, cnpj, razao_social, nome_fantasia, uf, "
            " codigo_ibge_municipio) "
            "VALUES (:id, :tenant_id, 'matriz', :cnpj, 'Outra Empresa Ltda', 'Outra', 'GO', "
            "        '5208707')"
        ),
        {
            "id": outra_empresa_id,
            "tenant_id": contexto_f12.tenant_id,
            "cnpj": str(uuid.uuid4().int)[:14].zfill(14),
        },
    )
    await sessao_f12.commit()
    await aplicar_tenant_teste(sessao_f12, contexto_f12.tenant_id)

    dados_ativo = _dados_rep_p_criar(empresa_id=contexto_f12.empresa_id, identificador="REPP-ATV")
    ativo = await criar_rep_p(sessao_f12, contexto_f12.tenant_id, dados_ativo, usuario_id=None)

    dados_outra_empresa = _dados_rep_p_criar(
        empresa_id=outra_empresa_id, identificador="REPP-OUTRA", numero_inpi="512026000124111"
    )
    await criar_rep_p(sessao_f12, contexto_f12.tenant_id, dados_outra_empresa, usuario_id=None)

    linhas, sequencias, paginacao = await listar_rep_ps(
        sessao_f12, contexto_f12.tenant_id, empresa_id=contexto_f12.empresa_id
    )

    ids_listados = {linha.id for linha in linhas}
    assert ativo.id in ids_listados
    assert all(linha.empresa_id == contexto_f12.empresa_id for linha in linhas)
    assert ativo.id in sequencias
    assert sequencias[ativo.id].proximo_nsr == 1
    assert paginacao.limite == 50
