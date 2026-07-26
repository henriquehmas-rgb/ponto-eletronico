"""Testes dos servicos `app.pessoas.contratos` (T6): contratos, vinculos e a
distincao entre eles.

Cobre o criterio de aceite 8 ("vinculos simultaneos em empresas diferentes
do mesmo tenant sao aceitos; sobrepostos na mesma empresa sao recusados com
PONTO-VAL-010") e o `ck_contratos_dispensa` (art. 62 da CLT).
"""

from __future__ import annotations

import datetime as dt
import random
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.comum.documentos import cpf_valido
from app.core.erros import ErroDeAplicacao
from app.pessoas import colaboradores as colaboradores_servico
from app.pessoas import contratos as servico
from app.schemas.contrato import (
    ColaboradorCriar,
    ContratoCriar,
    DispensaControleMotivo,
    EncerramentoVinculoRequisicao,
    Tipo8,
    VinculoCriar,
)
from tests.f2.conftest import ContextoOrganizacional


def _gerar_cpf_valido() -> str:
    """CPF valido (digito verificador correto), gerado a partir de 9 digitos
    aleatorios distintos -- cada chamada de teste que precisa de mais de um
    colaborador na mesma empresa precisa de um CPF diferente (`uq_colaboradores_cpf`
    e por tenant+empresa)."""
    while True:
        base = "".join(str(random.randint(0, 9)) for _ in range(9))  # noqa: S311
        if len(set(base)) == 1:
            continue
        pesos1 = [10, 9, 8, 7, 6, 5, 4, 3, 2]
        dv1 = 11 - (sum(int(d) * p for d, p in zip(base, pesos1, strict=True)) % 11)
        dv1 = 0 if dv1 >= 10 else dv1
        base10 = base + str(dv1)
        pesos2 = [11, 10, 9, 8, 7, 6, 5, 4, 3, 2]
        dv2 = 11 - (sum(int(d) * p for d, p in zip(base10, pesos2, strict=True)) % 11)
        dv2 = 0 if dv2 >= 10 else dv2
        candidato = base10 + str(dv2)
        if cpf_valido(candidato):
            return candidato


async def _criar_colaborador(
    sessao: AsyncSession, contexto: ContextoOrganizacional, *, empresa_id: uuid.UUID | None = None
):
    sufixo = uuid.uuid4().hex[:8]
    dados = ColaboradorCriar(
        empresaId=empresa_id or contexto.empresa_matriz_id,
        matricula=f"MAT-{sufixo}",
        cpf=_gerar_cpf_valido(),
        nomeCompleto="Colaborador de Teste",
    )
    return await colaboradores_servico.criar_colaborador(sessao, contexto.tenant_id, dados)


# ---------------------------------------------------------------------------
# Contratos: ck_contratos_dispensa (art. 62 da CLT)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dispensa_falsa_sem_motivo_e_recusada(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    colaborador = await _criar_colaborador(sessao_f2, contexto_organizacional)
    dados = ContratoCriar(
        colaboradorId=colaborador.id,
        empresaId=contexto_organizacional.empresa_matriz_id,
        tipo=Tipo8.clt,
        dataInicio=dt.date(2026, 1, 1),
        controleJornada=False,
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_contrato(sessao_f2, contexto_organizacional.tenant_id, dados)
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_motivo_sem_dispensa_e_recusado(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    colaborador = await _criar_colaborador(sessao_f2, contexto_organizacional)
    dados = ContratoCriar(
        colaboradorId=colaborador.id,
        empresaId=contexto_organizacional.empresa_matriz_id,
        tipo=Tipo8.clt,
        dataInicio=dt.date(2026, 1, 1),
        controleJornada=True,
        dispensaControleMotivo=DispensaControleMotivo.art62_i_externo,
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_contrato(sessao_f2, contexto_organizacional.tenant_id, dados)
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_dispensa_com_motivo_e_aceita(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    colaborador = await _criar_colaborador(sessao_f2, contexto_organizacional)
    dados = ContratoCriar(
        colaboradorId=colaborador.id,
        empresaId=contexto_organizacional.empresa_matriz_id,
        tipo=Tipo8.clt,
        dataInicio=dt.date(2026, 1, 1),
        controleJornada=False,
        dispensaControleMotivo=DispensaControleMotivo.art62_ii_gestao,
    )
    contrato = await servico.criar_contrato(sessao_f2, contexto_organizacional.tenant_id, dados)
    assert contrato.controle_jornada is False
    assert contrato.dispensa_controle_motivo == "art62_ii_gestao"


@pytest.mark.asyncio
async def test_contrato_sem_dispensa_e_aceito(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    colaborador = await _criar_colaborador(sessao_f2, contexto_organizacional)
    dados = ContratoCriar(
        colaboradorId=colaborador.id,
        empresaId=contexto_organizacional.empresa_matriz_id,
        tipo=Tipo8.clt,
        dataInicio=dt.date(2026, 1, 1),
        salario=3500.55,
    )
    contrato = await servico.criar_contrato(sessao_f2, contexto_organizacional.tenant_id, dados)
    assert contrato.controle_jornada is True
    assert contrato.dispensa_controle_motivo is None
    assert float(contrato.salario) == 3500.55


# ---------------------------------------------------------------------------
# Vinculos: EXCLUDE de sobreposicao (PONTO-VAL-010), nos dois lados
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_vinculos_sobrepostos_na_mesma_empresa_sao_recusados(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    tenant_id = contexto_organizacional.tenant_id
    colaborador = await _criar_colaborador(sessao_f2, contexto_organizacional)

    primeiro = VinculoCriar(
        colaboradorId=colaborador.id,
        empresaId=contexto_organizacional.empresa_matriz_id,
        matriculaEsocial=f"ESO-{uuid.uuid4().hex[:10]}",
        dataInicio=dt.date(2026, 1, 1),
    )
    await servico.criar_vinculo(sessao_f2, tenant_id, primeiro)

    segundo = VinculoCriar(
        colaboradorId=colaborador.id,
        empresaId=contexto_organizacional.empresa_matriz_id,
        matriculaEsocial=f"ESO-{uuid.uuid4().hex[:10]}",
        dataInicio=dt.date(2026, 6, 1),
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        async with sessao_f2.begin_nested():
            await servico.criar_vinculo(sessao_f2, tenant_id, segundo)
    assert excinfo.value.codigo == "PONTO-VAL-010"


@pytest.mark.asyncio
async def test_vinculos_simultaneos_em_empresas_diferentes_sao_aceitos(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    tenant_id = contexto_organizacional.tenant_id
    colaborador = await _criar_colaborador(sessao_f2, contexto_organizacional)

    na_matriz = VinculoCriar(
        colaboradorId=colaborador.id,
        empresaId=contexto_organizacional.empresa_matriz_id,
        matriculaEsocial=f"ESO-{uuid.uuid4().hex[:10]}",
        dataInicio=dt.date(2026, 1, 1),
    )
    na_filial = VinculoCriar(
        colaboradorId=colaborador.id,
        empresaId=contexto_organizacional.empresa_filial_id,
        matriculaEsocial=f"ESO-{uuid.uuid4().hex[:10]}",
        dataInicio=dt.date(2026, 1, 1),
    )
    vinculo_matriz = await servico.criar_vinculo(sessao_f2, tenant_id, na_matriz)
    vinculo_filial = await servico.criar_vinculo(sessao_f2, tenant_id, na_filial)

    assert vinculo_matriz.status == "ativo"
    assert vinculo_filial.status == "ativo"
    assert vinculo_matriz.empresa_id != vinculo_filial.empresa_id


@pytest.mark.asyncio
async def test_matricula_esocial_unica_por_empresa(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    tenant_id = contexto_organizacional.tenant_id
    colaborador_1 = await _criar_colaborador(sessao_f2, contexto_organizacional)
    colaborador_2 = await _criar_colaborador(sessao_f2, contexto_organizacional)
    matricula_esocial = f"ESO-{uuid.uuid4().hex[:10]}"

    await servico.criar_vinculo(
        sessao_f2,
        tenant_id,
        VinculoCriar(
            colaboradorId=colaborador_1.id,
            empresaId=contexto_organizacional.empresa_matriz_id,
            matriculaEsocial=matricula_esocial,
            dataInicio=dt.date(2026, 1, 1),
        ),
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        async with sessao_f2.begin_nested():
            await servico.criar_vinculo(
                sessao_f2,
                tenant_id,
                VinculoCriar(
                    colaboradorId=colaborador_2.id,
                    empresaId=contexto_organizacional.empresa_matriz_id,
                    matriculaEsocial=matricula_esocial,
                    dataInicio=dt.date(2026, 2, 1),
                ),
            )
    assert excinfo.value.codigo == "PONTO-CONF-001"


@pytest.mark.asyncio
async def test_encerrar_vinculo_grava_data_fim_motivo_e_status(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    tenant_id = contexto_organizacional.tenant_id
    colaborador = await _criar_colaborador(sessao_f2, contexto_organizacional)
    vinculo = await servico.criar_vinculo(
        sessao_f2,
        tenant_id,
        VinculoCriar(
            colaboradorId=colaborador.id,
            empresaId=contexto_organizacional.empresa_matriz_id,
            matriculaEsocial=f"ESO-{uuid.uuid4().hex[:10]}",
            dataInicio=dt.date(2026, 1, 1),
        ),
    )

    encerrado = await servico.encerrar_vinculo(
        sessao_f2,
        tenant_id,
        vinculo.id,
        EncerramentoVinculoRequisicao(
            dataFim=dt.date(2026, 9, 30), motivoDesligamento="Pedido de demissao"
        ),
    )
    assert encerrado.status == "encerrado"
    assert encerrado.data_fim == dt.date(2026, 9, 30)
    assert encerrado.motivo_desligamento == "Pedido de demissao"


@pytest.mark.asyncio
async def test_encerrar_vinculo_ja_encerrado_e_recusado(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    tenant_id = contexto_organizacional.tenant_id
    colaborador = await _criar_colaborador(sessao_f2, contexto_organizacional)
    vinculo = await servico.criar_vinculo(
        sessao_f2,
        tenant_id,
        VinculoCriar(
            colaboradorId=colaborador.id,
            empresaId=contexto_organizacional.empresa_matriz_id,
            matriculaEsocial=f"ESO-{uuid.uuid4().hex[:10]}",
            dataInicio=dt.date(2026, 1, 1),
        ),
    )
    await servico.encerrar_vinculo(
        sessao_f2, tenant_id, vinculo.id, EncerramentoVinculoRequisicao(dataFim=dt.date(2026, 3, 1))
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        async with sessao_f2.begin_nested():
            await servico.encerrar_vinculo(
                sessao_f2,
                tenant_id,
                vinculo.id,
                EncerramentoVinculoRequisicao(dataFim=dt.date(2026, 4, 1)),
            )
    assert excinfo.value.codigo == "PONTO-CONF-003"
