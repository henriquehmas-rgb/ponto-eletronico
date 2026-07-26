"""Testes do servico de hierarquia de gestores, `app.pessoas.colaboradores`
(T7): um unico gestor imediato vigente por colaborador, deteccao de ciclo, e
`subordinados_de`.

Cobre o criterio de aceite 9 ("Um unico gestor imediato vigente por
colaborador em qualquer data, e ciclo na hierarquia e recusado").
"""

from __future__ import annotations

import datetime as dt
import random
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.comum.documentos import cpf_valido
from app.core.erros import ErroDeAplicacao
from app.pessoas import colaboradores as servico
from app.schemas.contrato import ColaboradorCriar, ColaboradorGestorCriar, Tipo6
from tests.f2.conftest import ContextoOrganizacional


def _gerar_cpf_valido() -> str:
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


async def _criar_colaborador(sessao: AsyncSession, contexto: ContextoOrganizacional, nome: str):
    dados = ColaboradorCriar(
        empresaId=contexto.empresa_matriz_id,
        matricula=f"MAT-{uuid.uuid4().hex[:8]}",
        cpf=_gerar_cpf_valido(),
        nomeCompleto=nome,
    )
    return await servico.criar_colaborador(sessao, contexto.tenant_id, dados)


@pytest.mark.asyncio
async def test_segundo_gestor_imediato_vigente_na_mesma_data_e_recusado(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    tenant_id = contexto_organizacional.tenant_id
    colaborador = await _criar_colaborador(sessao_f2, contexto_organizacional, "Colaborador")
    gestor_1 = await _criar_colaborador(sessao_f2, contexto_organizacional, "Gestor Um")
    gestor_2 = await _criar_colaborador(sessao_f2, contexto_organizacional, "Gestor Dois")

    await servico.definir_gestor_colaborador(
        sessao_f2,
        tenant_id,
        colaborador.id,
        ColaboradorGestorCriar(
            gestorColaboradorId=gestor_1.id,
            tipo=Tipo6.imediato,
            vigenciaInicio=dt.date(2026, 1, 1),
        ),
    )

    with pytest.raises(ErroDeAplicacao) as excinfo:
        async with sessao_f2.begin_nested():
            await servico.definir_gestor_colaborador(
                sessao_f2,
                tenant_id,
                colaborador.id,
                ColaboradorGestorCriar(
                    gestorColaboradorId=gestor_2.id,
                    tipo=Tipo6.imediato,
                    vigenciaInicio=dt.date(2026, 3, 1),
                ),
            )
    assert excinfo.value.codigo == "PONTO-VAL-010"


@pytest.mark.asyncio
async def test_gestores_com_vigencias_nao_sobrepostas_sao_aceitos(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    tenant_id = contexto_organizacional.tenant_id
    colaborador = await _criar_colaborador(sessao_f2, contexto_organizacional, "Colaborador")
    gestor_1 = await _criar_colaborador(sessao_f2, contexto_organizacional, "Gestor Um")
    gestor_2 = await _criar_colaborador(sessao_f2, contexto_organizacional, "Gestor Dois")

    await servico.definir_gestor_colaborador(
        sessao_f2,
        tenant_id,
        colaborador.id,
        ColaboradorGestorCriar(
            gestorColaboradorId=gestor_1.id,
            tipo=Tipo6.imediato,
            vigenciaInicio=dt.date(2026, 1, 1),
            vigenciaFim=dt.date(2026, 2, 28),
        ),
    )
    segundo = await servico.definir_gestor_colaborador(
        sessao_f2,
        tenant_id,
        colaborador.id,
        ColaboradorGestorCriar(
            gestorColaboradorId=gestor_2.id,
            tipo=Tipo6.imediato,
            vigenciaInicio=dt.date(2026, 3, 1),
        ),
    )
    assert segundo.gestor_colaborador_id == gestor_2.id


@pytest.mark.asyncio
async def test_colaborador_nao_pode_ser_gestor_de_si_mesmo(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    tenant_id = contexto_organizacional.tenant_id
    colaborador = await _criar_colaborador(sessao_f2, contexto_organizacional, "Colaborador")

    with pytest.raises(ErroDeAplicacao) as excinfo:
        async with sessao_f2.begin_nested():
            await servico.definir_gestor_colaborador(
                sessao_f2,
                tenant_id,
                colaborador.id,
                ColaboradorGestorCriar(
                    gestorColaboradorId=colaborador.id,
                    tipo=Tipo6.imediato,
                    vigenciaInicio=dt.date(2026, 1, 1),
                ),
            )
    assert excinfo.value.codigo == "PONTO-CONF-003"


@pytest.mark.asyncio
async def test_ciclo_a_gerencia_b_que_gerencia_a_e_recusado(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    """A e gestor imediato de B; tentar tornar B gestor imediato de A fecha
    um ciclo de 2 nos e deve ser recusado com PONTO-CONF-003."""
    tenant_id = contexto_organizacional.tenant_id
    colaborador_a = await _criar_colaborador(sessao_f2, contexto_organizacional, "Colaborador A")
    colaborador_b = await _criar_colaborador(sessao_f2, contexto_organizacional, "Colaborador B")

    # A gerencia B.
    await servico.definir_gestor_colaborador(
        sessao_f2,
        tenant_id,
        colaborador_b.id,
        ColaboradorGestorCriar(
            gestorColaboradorId=colaborador_a.id,
            tipo=Tipo6.imediato,
            vigenciaInicio=dt.date(2026, 1, 1),
        ),
    )

    # B gerencia A: fecha o ciclo.
    with pytest.raises(ErroDeAplicacao) as excinfo:
        async with sessao_f2.begin_nested():
            await servico.definir_gestor_colaborador(
                sessao_f2,
                tenant_id,
                colaborador_a.id,
                ColaboradorGestorCriar(
                    gestorColaboradorId=colaborador_b.id,
                    tipo=Tipo6.imediato,
                    vigenciaInicio=dt.date(2026, 1, 1),
                ),
            )
    assert excinfo.value.codigo == "PONTO-CONF-003"


@pytest.mark.asyncio
async def test_subordinados_de_devolve_arvore_de_tres_niveis(
    sessao_f2: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> None:
    """Diretor -> [Gerente 1, Gerente 2]; Gerente 1 -> [Analista 1, Analista
    2]. `subordinados_de(diretor)` deve devolver os 4 subordinados
    (diretos e transitivos); `subordinados_de(gerente_2)` nenhum."""
    tenant_id = contexto_organizacional.tenant_id
    diretor = await _criar_colaborador(sessao_f2, contexto_organizacional, "Diretor")
    gerente_1 = await _criar_colaborador(sessao_f2, contexto_organizacional, "Gerente Um")
    gerente_2 = await _criar_colaborador(sessao_f2, contexto_organizacional, "Gerente Dois")
    analista_1 = await _criar_colaborador(sessao_f2, contexto_organizacional, "Analista Um")
    analista_2 = await _criar_colaborador(sessao_f2, contexto_organizacional, "Analista Dois")

    data_vigencia = dt.date(2026, 1, 1)
    for subordinado, gestor in (
        (gerente_1, diretor),
        (gerente_2, diretor),
        (analista_1, gerente_1),
        (analista_2, gerente_1),
    ):
        await servico.definir_gestor_colaborador(
            sessao_f2,
            tenant_id,
            subordinado.id,
            ColaboradorGestorCriar(
                gestorColaboradorId=gestor.id, tipo=Tipo6.imediato, vigenciaInicio=data_vigencia
            ),
        )

    arvore_diretor = await servico.subordinados_de(sessao_f2, tenant_id, diretor.id, data_vigencia)
    assert arvore_diretor == {gerente_1.id, gerente_2.id, analista_1.id, analista_2.id}

    arvore_gerente_1 = await servico.subordinados_de(
        sessao_f2, tenant_id, gerente_1.id, data_vigencia
    )
    assert arvore_gerente_1 == {analista_1.id, analista_2.id}

    arvore_gerente_2 = await servico.subordinados_de(
        sessao_f2, tenant_id, gerente_2.id, data_vigencia
    )
    assert arvore_gerente_2 == set()

    arvore_antes_da_vigencia = await servico.subordinados_de(
        sessao_f2, tenant_id, diretor.id, dt.date(2025, 12, 31)
    )
    assert arvore_antes_da_vigencia == set()
