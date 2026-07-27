"""Testes de `app.apuracao.banco_horas.politicas` (T5).

Cobre os tres "pronto quando" do T5 relativos a `bh_politicas`: periodo
acima do limite legal por regime (`PONTO-BH-003`), documento de acordo
ausente (`PONTO-BH-006`) e o caminho feliz.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.banco_horas import politicas as servico
from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from tests.f4.banco_horas.conftest import ContextoBancoHoras


def _dados_politica(
    contexto: ContextoBancoHoras,
    *,
    regime: esquemas.Regime,
    periodo_meses: int,
    documento_acordo_id=None,
    codigo: str = "POL-TESTE",
) -> esquemas.BhPoliticaCriar:
    return esquemas.BhPoliticaCriar(
        empresaId=contexto.empresa_id,
        codigo=codigo,
        nome="Politica de teste",
        regime=regime,
        periodoMeses=periodo_meses,
        vigenciaInicio=dt.date(2026, 1, 1),
        documentoAcordoId=documento_acordo_id,
    )


@pytest.mark.asyncio
async def test_individual_acima_de_6_meses_e_recusado(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    dados = _dados_politica(
        contexto_banco_horas, regime=esquemas.Regime.individual, periodo_meses=12
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_politica_banco_horas(
            sessao_banco_horas, contexto_banco_horas.tenant_id, dados
        )
    assert excinfo.value.codigo == "PONTO-BH-003"


@pytest.mark.asyncio
async def test_coletivo_ate_12_meses_e_aceito(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    from ponto_contracts import Documento

    documento = Documento(
        tenant_id=contexto_banco_horas.tenant_id,
        empresa_id=contexto_banco_horas.empresa_id,
        tipo="acordo_banco_horas",
        nome_arquivo="acordo.pdf",
        conteudo_ref="s3://bucket/acordo.pdf",
    )
    sessao_banco_horas.add(documento)
    await sessao_banco_horas.flush()

    dados = _dados_politica(
        contexto_banco_horas,
        regime=esquemas.Regime.coletivo,
        periodo_meses=12,
        documento_acordo_id=documento.id,
        codigo="POL-COLETIVA",
    )
    politica = await servico.criar_politica_banco_horas(
        sessao_banco_horas, contexto_banco_horas.tenant_id, dados
    )
    assert politica.periodo_meses == 12
    assert politica.regime == "coletivo"


@pytest.mark.asyncio
async def test_documento_acordo_ausente_e_recusado(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    dados = _dados_politica(
        contexto_banco_horas,
        regime=esquemas.Regime.coletivo,
        periodo_meses=12,
        documento_acordo_id=None,
        codigo="POL-SEM-ACORDO",
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_politica_banco_horas(
            sessao_banco_horas, contexto_banco_horas.tenant_id, dados
        )
    assert excinfo.value.codigo == "PONTO-BH-006"


@pytest.mark.asyncio
async def test_regime_especial_dispensa_documento_de_acordo(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    dados = _dados_politica(
        contexto_banco_horas,
        regime=esquemas.Regime.especial,
        periodo_meses=12,
        documento_acordo_id=None,
        codigo="POL-ESPECIAL",
    )
    politica = await servico.criar_politica_banco_horas(
        sessao_banco_horas, contexto_banco_horas.tenant_id, dados
    )
    assert politica.regime == "especial"
    assert politica.documento_acordo_id is None


@pytest.mark.asyncio
async def test_criar_politica_normaliza_enums_e_fatores(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    dados = esquemas.BhPoliticaCriar(
        empresaId=contexto_banco_horas.empresa_id,
        codigo="POL-LIFO-EXPIRA",
        nome="Politica lifo/expirar",
        regime=esquemas.Regime.especial,
        periodoMeses=6,
        vigenciaInicio=dt.date(2026, 1, 1),
        metodoConsumo=esquemas.MetodoConsumo.lifo,
        acaoVencimento=esquemas.AcaoVencimento.expirar,
        fatorCreditoPadrao=1.5,
        fatorDebitoPadrao=1.0,
    )
    politica = await servico.criar_politica_banco_horas(
        sessao_banco_horas, contexto_banco_horas.tenant_id, dados
    )
    assert politica.metodo_consumo == "lifo"
    assert politica.acao_vencimento == "expirar"
    assert float(politica.fator_credito_padrao) == 1.5


@pytest.mark.asyncio
async def test_obter_politica_banco_horas_inexistente_e_rec_001(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    import uuid

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.obter_politica_banco_horas(
            sessao_banco_horas, contexto_banco_horas.tenant_id, uuid.uuid4()
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


@pytest.mark.asyncio
async def test_listar_politicas_com_filtros_e_paginacao(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    await servico.criar_politica_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        _dados_politica(
            contexto_banco_horas,
            regime=esquemas.Regime.especial,
            periodo_meses=3,
            codigo="POL-FILTRO",
        ),
    )
    await sessao_banco_horas.flush()

    por_empresa, _ = await servico.listar_politicas_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        empresa_id=contexto_banco_horas.empresa_id,
    )
    assert len(por_empresa) >= 2

    por_regime, _ = await servico.listar_politicas_banco_horas(
        sessao_banco_horas, contexto_banco_horas.tenant_id, regime="especial"
    )
    assert len(por_regime) >= 1

    ativas, _ = await servico.listar_politicas_banco_horas(
        sessao_banco_horas, contexto_banco_horas.tenant_id, ativo=True
    )
    assert len(ativas) >= 2

    vigentes, _ = await servico.listar_politicas_banco_horas(
        sessao_banco_horas, contexto_banco_horas.tenant_id, vigente_em=dt.date(2026, 3, 1)
    )
    assert len(vigentes) >= 2

    primeira, paginacao_1 = await servico.listar_politicas_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        empresa_id=contexto_banco_horas.empresa_id,
        limite=1,
        ordenar="codigo:asc",
    )
    assert len(primeira) == 1
    assert paginacao_1.tem_mais is True

    segunda, _ = await servico.listar_politicas_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        empresa_id=contexto_banco_horas.empresa_id,
        limite=1,
        ordenar="codigo:asc",
        cursor=paginacao_1.proximo_cursor,
    )
    assert len(segunda) == 1
    assert segunda[0].id != primeira[0].id
