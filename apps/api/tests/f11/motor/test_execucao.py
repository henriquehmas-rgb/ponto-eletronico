"""Testes de `app.relatorios.execucao` (T3, critério de aceite oficial):

* um relatório pequeno (um vínculo, um mês) responde `200` síncrono;
* pedir um relatório `assincrono=true` (ou `RelatorioDefinicao.assincrono=
  true`, ou intervalo acima do limiar) responde com
  `RelatorioExecucao(status='enfileirado')`;
* `obterExecucaoRelatorio` de uma execução inexistente responde
  `PONTO-REC-001` e de uma expirada responde `PONTO-REC-002`.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from ponto_contracts import ApuracaoDia, RelatorioDefinicao, RelatorioExecucao
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.relatorios import execucao as execucao_servico
from app.relatorios import motor
from app.relatorios.catalogo import (
    ColunaCatalogo,
    montar_agrupamentos,
    montar_colunas_disponiveis,
    montar_filtros_disponiveis,
    registrar_dataset,
)
from tests.f11.conftest import ContextoF11

_NOME_DATASET = "teste_execucao_apuracao"


def _construtor(
    sessao: AsyncSession, tenant_id: uuid.UUID, contexto: motor.ContextoConsulta
) -> Select[Any]:
    consulta = sa.select(
        ApuracaoDia.colaborador_id.label("colaboradorId"),
        ApuracaoDia.data.label("data"),
        ApuracaoDia.extras_minutos.label("extrasMinutos"),
    ).where(ApuracaoDia.tenant_id == tenant_id)
    if contexto.de is not None:
        consulta = consulta.where(ApuracaoDia.data >= contexto.de)
    if contexto.ate is not None:
        consulta = consulta.where(ApuracaoDia.data <= contexto.ate)
    if contexto.colaborador_id is not None:
        consulta = consulta.where(ApuracaoDia.colaborador_id == contexto.colaborador_id)
    return consulta


registrar_dataset(_NOME_DATASET, _construtor)

_COLUNAS = [
    ColunaCatalogo("colaboradorId", "Colaborador", "uuid"),
    ColunaCatalogo("data", "Data", "data"),
    ColunaCatalogo("extrasMinutos", "Extras", "numero", True),
]


@pytest.fixture
async def definicao_leve(contexto_f11: ContextoF11, sessao_f11: AsyncSession) -> RelatorioDefinicao:
    definicao = RelatorioDefinicao(
        id=uuid.uuid4(),
        tenant_id=contexto_f11.tenant_id,
        codigo="teste-execucao-leve",
        nome="Dataset leve de teste de execucao",
        categoria="operacional",
        sistema=False,
        dataset=_NOME_DATASET,
        colunas_disponiveis=montar_colunas_disponiveis(_COLUNAS),
        filtros_disponiveis=montar_filtros_disponiveis([]),
        agrupamentos=montar_agrupamentos([]),
        formatos=["csv", "xlsx", "pdf"],
        permissao_codigo="relatorios.executar",
        assincrono=False,
        ativo=True,
    )
    sessao_f11.add(definicao)
    await sessao_f11.flush()
    return definicao


def _parametros(**overrides: Any) -> execucao_servico.ParametrosExecucao:
    base: dict[str, Any] = {
        "formato": None,
        "periodo_id": None,
        "de": None,
        "ate": None,
        "empresa_id": None,
        "unidade_id": None,
        "departamento_id": None,
        "colaborador_id": None,
        "agrupamento": None,
        "colunas": None,
        "filtros": None,
        "converter_decimal": None,
        "incluir_inativos": None,
        "assincrono": None,
    }
    base.update(overrides)
    return execucao_servico.ParametrosExecucao(**base)


async def test_relatorio_pequeno_responde_sincrono_concluido(
    contexto_f11: ContextoF11, sessao_f11: AsyncSession, definicao_leve: RelatorioDefinicao
) -> None:
    colaborador_a = contexto_f11.colaboradores[0]
    parametros = _parametros(
        de=contexto_f11.dias_uteis[0],
        ate=contexto_f11.dias_uteis[-1],
        colaborador_id=colaborador_a.colaborador_id,
    )
    execucao = await execucao_servico.executar_relatorio_pedido(
        sessao_f11,
        contexto_f11.tenant_id,
        "teste-execucao-leve",
        parametros,
        usuario_id=contexto_f11.usuario_rh_id,
        redis_url="redis://unused-nao-deve-ser-chamado/0",
    )
    assert execucao.status == "concluido"
    assert execucao.progresso == 100
    assert execucao.total_linhas == 3
    assert execucao.conteudo_ref is not None
    assert execucao.hash_sha256 is not None
    assert execucao.formato == "json"

    resposta = await execucao_servico.montar_execucao_resposta(
        execucao, codigo="teste-execucao-leve"
    )
    assert resposta.status == "concluido"
    assert resposta.url_download is not None


async def test_assincrono_pedido_explicitamente_enfileira(
    contexto_f11: ContextoF11,
    sessao_f11: AsyncSession,
    definicao_leve: RelatorioDefinicao,
) -> None:
    parametros = _parametros(assincrono=True)
    execucao = await execucao_servico.executar_relatorio_pedido(
        sessao_f11,
        contexto_f11.tenant_id,
        "teste-execucao-leve",
        parametros,
        usuario_id=contexto_f11.usuario_rh_id,
        redis_url="redis://:18286d9fc9bc1b4979f081871c11f878632be6db6d6ad1b8@127.0.0.1:16379/0",
    )
    assert execucao.status == "enfileirado"
    assert execucao.progresso == 0
    assert execucao.conteudo_ref is None


async def test_relatorio_definicao_assincrono_true_nunca_toca_o_dataset(
    contexto_f11: ContextoF11, sessao_f11: AsyncSession
) -> None:
    """`espelho-jornada` (fixture) e `assincrono=true` mas nenhum dataset
    `apuracao_dia` esta registrado ainda (A2 constroi em T7) -- a decisao de
    ir assincrono acontece ANTES do motor tentar resolver o dataset, entao
    isto nao explode com `PONTO-INT-005`."""
    parametros = _parametros()
    execucao = await execucao_servico.executar_relatorio_pedido(
        sessao_f11,
        contexto_f11.tenant_id,
        "espelho-jornada",
        parametros,
        usuario_id=contexto_f11.usuario_rh_id,
        redis_url="redis://:18286d9fc9bc1b4979f081871c11f878632be6db6d6ad1b8@127.0.0.1:16379/0",
    )
    assert execucao.status == "enfileirado"


def test_decidir_execucao_assincrona_pelo_limiar_de_dias() -> None:
    definicao = RelatorioDefinicao(assincrono=False)
    de = dt.date(2026, 1, 1)
    dentro_do_limiar = de + dt.timedelta(days=execucao_servico.LIMIAR_DIAS_ASSINCRONO)
    acima_do_limiar = de + dt.timedelta(days=execucao_servico.LIMIAR_DIAS_ASSINCRONO + 1)

    assert (
        execucao_servico.decidir_execucao_assincrona(
            definicao, assincrono_pedido=None, de=de, ate=dentro_do_limiar
        )
        is False
    )
    assert (
        execucao_servico.decidir_execucao_assincrona(
            definicao, assincrono_pedido=None, de=de, ate=acima_do_limiar
        )
        is True
    )


async def test_obter_execucao_inexistente_responde_rec_001(
    contexto_f11: ContextoF11, sessao_f11: AsyncSession
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await execucao_servico.obter_execucao(sessao_f11, contexto_f11.tenant_id, uuid.uuid4())
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_obter_execucao_expirada_responde_rec_002(
    contexto_f11: ContextoF11,
    sessao_f11: AsyncSession,
    definicao_leve: RelatorioDefinicao,
) -> None:
    execucao = RelatorioExecucao(
        id=uuid.uuid4(),
        tenant_id=contexto_f11.tenant_id,
        relatorio_definicao_id=definicao_leve.id,
        usuario_id=contexto_f11.usuario_rh_id,
        formato="json",
        status="concluido",
        progresso=100,
        conteudo_ref="relatorios/x/y.json",
        expira_em=dt.datetime.now(tz=dt.UTC) - dt.timedelta(days=1),
    )
    sessao_f11.add(execucao)
    await sessao_f11.flush()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await execucao_servico.obter_execucao(sessao_f11, contexto_f11.tenant_id, execucao.id)
    assert excinfo.value.codigo == "PONTO-REC-002"


async def test_colunas_invalidas_no_caminho_sincrono_respondem_val_005(
    contexto_f11: ContextoF11, sessao_f11: AsyncSession, definicao_leve: RelatorioDefinicao
) -> None:
    parametros = _parametros(colunas="campoInexistente")
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await execucao_servico.executar_relatorio_pedido(
            sessao_f11,
            contexto_f11.tenant_id,
            "teste-execucao-leve",
            parametros,
            usuario_id=contexto_f11.usuario_rh_id,
            redis_url="redis://unused/0",
        )
    assert excinfo.value.codigo == "PONTO-VAL-005"
