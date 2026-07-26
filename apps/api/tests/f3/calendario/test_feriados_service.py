"""Testes de `app.jornada.calendario.feriados` contra o banco real (T5).

Cobre os criterios de aceite 5 (feriado municipal so na unidade certa) e 6
(feriados moveis calculados corretamente, agora ponta a ponta via listagem),
alem das validacoes de `ck_feriado_conjuntos_abrangencia`,
`ck_feriados_definicao`, `ck_feriados_parcial` e da unicidade de codigo.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.jornada.calendario import feriados as servico
from app.schemas import contrato as esquemas
from tests.f3.conftest import ContextoF3

pytestmark = pytest.mark.asyncio


def _conjunto_criar(
    *,
    codigo: str,
    nome: str = "Conjunto de teste",
    abrangencia: esquemas.Abrangencia = esquemas.Abrangencia.nacional,
    uf: str | None = None,
    codigo_ibge_municipio: str | None = None,
    unidade_ids: list | None = None,
) -> esquemas.FeriadoConjuntoCriar:
    return esquemas.FeriadoConjuntoCriar(
        codigo=codigo,
        nome=nome,
        abrangencia=abrangencia,
        uf=uf,
        codigo_ibge_municipio=codigo_ibge_municipio,
        unidade_ids=unidade_ids,
        ativo=True,
    )


# ---------------------------------------------------------------------------
# feriado_conjuntos: validacao e CRUD
# ---------------------------------------------------------------------------
async def test_conjunto_estadual_sem_uf_e_val_001(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    dados = _conjunto_criar(codigo="EST-SEM-UF", abrangencia=esquemas.Abrangencia.estadual)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_feriado_conjunto(sessao_f3, contexto_f3.tenant_id, dados)
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_conjunto_municipal_sem_ibge_e_val_001(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    dados = _conjunto_criar(codigo="MUN-SEM-IBGE", abrangencia=esquemas.Abrangencia.municipal)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_feriado_conjunto(sessao_f3, contexto_f3.tenant_id, dados)
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_conjunto_codigo_duplicado_e_conf_001(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    dados = _conjunto_criar(codigo="NACIONAL-DUP")
    await servico.criar_feriado_conjunto(sessao_f3, contexto_f3.tenant_id, dados)
    await sessao_f3.flush()
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_feriado_conjunto(
            sessao_f3, contexto_f3.tenant_id, _conjunto_criar(codigo="NACIONAL-DUP")
        )
    assert excinfo.value.codigo == "PONTO-CONF-001"


async def test_sincronizar_unidades_insere_e_remove(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    dados = _conjunto_criar(
        codigo="SYNC-UNI", unidade_ids=[contexto_f3.unidade_sp_id, contexto_f3.unidade_ba_id]
    )
    conjunto = await servico.criar_feriado_conjunto(sessao_f3, contexto_f3.tenant_id, dados)
    assert set(conjunto.unidade_ids) == {contexto_f3.unidade_sp_id, contexto_f3.unidade_ba_id}

    atualizado = await servico.atualizar_feriado_conjunto(
        sessao_f3,
        contexto_f3.tenant_id,
        conjunto.id,
        esquemas.FeriadoConjuntoAtualizar(unidade_ids=[contexto_f3.unidade_sp_id]),
    )
    assert atualizado.unidade_ids == [contexto_f3.unidade_sp_id]


async def test_omitir_unidade_ids_na_atualizacao_preserva_associacao(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    dados = _conjunto_criar(codigo="PRESERVA-UNI", unidade_ids=[contexto_f3.unidade_sp_id])
    conjunto = await servico.criar_feriado_conjunto(sessao_f3, contexto_f3.tenant_id, dados)

    atualizado = await servico.atualizar_feriado_conjunto(
        sessao_f3,
        contexto_f3.tenant_id,
        conjunto.id,
        esquemas.FeriadoConjuntoAtualizar(nome="Novo nome"),
    )
    assert atualizado.nome == "Novo nome"
    assert atualizado.unidade_ids == [contexto_f3.unidade_sp_id]


async def test_excluir_conjunto_com_feriados_e_conf_004(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    conjunto = await servico.criar_feriado_conjunto(
        sessao_f3, contexto_f3.tenant_id, _conjunto_criar(codigo="COM-FERIADO")
    )
    await servico.criar_feriado(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.FeriadoCriar(
            feriado_conjunto_id=conjunto.id,
            nome="Feriado fixo",
            data=dt.date(2024, 1, 1),
            tipo=esquemas.Tipo23.feriado,
            movel=False,
            integral=True,
        ),
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.excluir_feriado_conjunto(sessao_f3, contexto_f3.tenant_id, conjunto.id)
    assert excinfo.value.codigo == "PONTO-CONF-004"


async def test_excluir_conjunto_sem_feriados_funciona(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    conjunto = await servico.criar_feriado_conjunto(
        sessao_f3, contexto_f3.tenant_id, _conjunto_criar(codigo="SEM-FERIADO")
    )
    await servico.excluir_feriado_conjunto(sessao_f3, contexto_f3.tenant_id, conjunto.id)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.atualizar_feriado_conjunto(
            sessao_f3,
            contexto_f3.tenant_id,
            conjunto.id,
            esquemas.FeriadoConjuntoAtualizar(nome="Nao deveria existir mais"),
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


# ---------------------------------------------------------------------------
# feriados: validacao de definicao e listagem efetiva
# ---------------------------------------------------------------------------
async def _criar_conjunto_nacional(
    sessao: AsyncSession, contexto: ContextoF3, codigo: str, unidade_ids: list
) -> esquemas.FeriadoConjunto:
    return await servico.criar_feriado_conjunto(
        sessao, contexto.tenant_id, _conjunto_criar(codigo=codigo, unidade_ids=unidade_ids)
    )


async def test_feriado_movel_sem_regra_e_val_001(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    conjunto = await _criar_conjunto_nacional(sessao_f3, contexto_f3, "VAL-MOVEL", [])
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_feriado(
            sessao_f3,
            contexto_f3.tenant_id,
            esquemas.FeriadoCriar(
                feriado_conjunto_id=conjunto.id, nome="Movel sem regra", movel=True
            ),
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_feriado_custom_sem_offset_e_val_001(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    conjunto = await _criar_conjunto_nacional(sessao_f3, contexto_f3, "VAL-CUSTOM", [])
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_feriado(
            sessao_f3,
            contexto_f3.tenant_id,
            esquemas.FeriadoCriar(
                feriado_conjunto_id=conjunto.id,
                nome="Custom sem offset",
                movel=True,
                regra_movel=esquemas.RegraMovel.custom,
            ),
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_feriado_fixo_sem_data_e_val_001(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    conjunto = await _criar_conjunto_nacional(sessao_f3, contexto_f3, "VAL-FIXO", [])
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_feriado(
            sessao_f3,
            contexto_f3.tenant_id,
            esquemas.FeriadoCriar(
                feriado_conjunto_id=conjunto.id, nome="Fixo sem data", movel=False
            ),
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_feriado_reduzido_sem_carga_e_val_001(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    conjunto = await _criar_conjunto_nacional(sessao_f3, contexto_f3, "VAL-PARCIAL", [])
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_feriado(
            sessao_f3,
            contexto_f3.tenant_id,
            esquemas.FeriadoCriar(
                feriado_conjunto_id=conjunto.id,
                nome="Reduzido sem carga",
                data=dt.date(2024, 12, 24),
                movel=False,
                integral=False,
            ),
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_feriado_municipal_aplica_so_na_unidade_certa(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    """Criterio de aceite 5: um feriado municipal associado so a unidade SP
    aparece em `listarFeriados?unidadeId=<SP>` mas nao em `<BA>`."""
    conjunto_municipal = await servico.criar_feriado_conjunto(
        sessao_f3,
        contexto_f3.tenant_id,
        _conjunto_criar(
            codigo="MUN-SP",
            abrangencia=esquemas.Abrangencia.municipal,
            codigo_ibge_municipio=contexto_f3.unidade_sp_codigo_ibge,
            unidade_ids=[contexto_f3.unidade_sp_id],
        ),
    )
    await servico.criar_feriado(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.FeriadoCriar(
            feriado_conjunto_id=conjunto_municipal.id,
            nome="Aniversario da cidade de Sao Paulo",
            data=dt.date(2024, 1, 25),
            tipo=esquemas.Tipo23.feriado,
            movel=False,
            integral=True,
        ),
    )

    feriados_sp, _ = await servico.listar_feriados(
        sessao_f3, contexto_f3.tenant_id, unidade_id=contexto_f3.unidade_sp_id, ano=2024
    )
    feriados_ba, _ = await servico.listar_feriados(
        sessao_f3, contexto_f3.tenant_id, unidade_id=contexto_f3.unidade_ba_id, ano=2024
    )
    assert any(f.nome == "Aniversario da cidade de Sao Paulo" for f in feriados_sp)
    assert not any(f.nome == "Aniversario da cidade de Sao Paulo" for f in feriados_ba)


async def test_feriado_nacional_precisa_de_associacao_explicita(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    """Mesmo um conjunto `nacional` so vale para uma unidade que tenha a
    associacao explicita em `unidade_feriado_conjuntos` (PCF, secao 2) --
    sem associar a NENHUMA unidade, o feriado nao aparece em lugar algum."""
    conjunto_nacional = await servico.criar_feriado_conjunto(
        sessao_f3, contexto_f3.tenant_id, _conjunto_criar(codigo="NAC-ORFAO", unidade_ids=[])
    )
    await servico.criar_feriado(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.FeriadoCriar(
            feriado_conjunto_id=conjunto_nacional.id,
            nome="Feriado nacional orfao",
            data=dt.date(2024, 9, 7),
            tipo=esquemas.Tipo23.feriado,
            movel=False,
            integral=True,
        ),
    )
    feriados_sp, _ = await servico.listar_feriados(
        sessao_f3, contexto_f3.tenant_id, unidade_id=contexto_f3.unidade_sp_id, ano=2024
    )
    assert not any(f.nome == "Feriado nacional orfao" for f in feriados_sp)


@pytest.mark.parametrize(
    ("regra", "ano", "esperado"),
    [
        ("pascoa", 2024, dt.date(2024, 3, 31)),
        ("pascoa", 2025, dt.date(2025, 4, 20)),
        ("carnaval", 2024, dt.date(2024, 2, 13)),
        ("corpus_christi", 2025, dt.date(2025, 6, 19)),
    ],
)
async def test_listagem_resolve_feriados_moveis_por_ano(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3, regra: str, ano: int, esperado: dt.date
) -> None:
    conjunto = await _criar_conjunto_nacional(
        sessao_f3, contexto_f3, f"MOVEL-{regra}-{ano}", [contexto_f3.unidade_sp_id]
    )
    await servico.criar_feriado(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.FeriadoCriar(
            feriado_conjunto_id=conjunto.id,
            nome=f"Feriado movel {regra}",
            movel=True,
            regra_movel=esquemas.RegraMovel(regra),
        ),
    )
    feriados, _ = await servico.listar_feriados(
        sessao_f3, contexto_f3.tenant_id, unidade_id=contexto_f3.unidade_sp_id, ano=ano
    )
    encontrado = next(f for f in feriados if f.nome == f"Feriado movel {regra}")
    assert encontrado.data_resolvida == esperado


async def test_excluir_feriado_e_fisico(sessao_f3: AsyncSession, contexto_f3: ContextoF3) -> None:
    conjunto = await _criar_conjunto_nacional(sessao_f3, contexto_f3, "EXCLUIR-FERIADO", [])
    feriado = await servico.criar_feriado(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.FeriadoCriar(
            feriado_conjunto_id=conjunto.id,
            nome="Feriado a excluir",
            data=dt.date(2024, 6, 1),
            movel=False,
            integral=True,
        ),
    )
    await servico.excluir_feriado(sessao_f3, contexto_f3.tenant_id, feriado.id)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.excluir_feriado(sessao_f3, contexto_f3.tenant_id, feriado.id)
    assert excinfo.value.codigo == "PONTO-REC-001"
