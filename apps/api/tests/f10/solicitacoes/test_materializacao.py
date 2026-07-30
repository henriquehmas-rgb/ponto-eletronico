"""Teste de mesa do despachante genérico de materialização (T4, A1) --
cobre as sete linhas da tabela do PCF §2.2: `ajuste_ponto`, `abono`,
`justificativa`, `compensacao`, `afastamento` (retroativo) via
`criar_tratamento`/`decidir_tratamento` (F4); `ferias`/`folga` via
`app.workflow.solicitacoes.afastamentos` (A4); e uma categoria SEM
`tipo_tratamento_id` e fora de `ferias`/`folga` (`troca_escala`) sem efeito
automático. Mais um caso extra provando que o despachante é genérico (uma
categoria configurada pelo tenant, fora do seed de fábrica, também
materializa via tratamento).
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator
from uuid import UUID

import pytest
import sqlalchemy as sa
from ponto_contracts import Afastamento, Solicitacao, Tratamento
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.workflow.solicitacoes import eventos, servico
from app.workflow.solicitacoes.materializacao import (
    materializar_solicitacao_aprovada,
)
from tests.f10.conftest import ContextoF10

#: `decidir_tratamento` (F4) aprova e imediatamente agenda `recalcular_periodo`
#: (T10 de F4) -- quando o recalculo consegue apurar o dia de verdade (jornada
#: resolvivel, dia dentro do periodo), o tratamento é CONSUMIDO e vira
#: `aplicado` na mesma transação; quando não (ex.: apuração do dia não roda
#: por algum motivo fora do controle deste despachante), fica `aprovado`. As
#: duas são o resultado CORRETO de uma aprovação bem-sucedida (nunca
#: `pendente`/`reprovado`/`cancelado`) -- este módulo só reaproveita F4, nunca
#: decide o resultado final da apuração.
_STATUS_MATERIALIZADO = frozenset({"aprovado", "aplicado"})


@pytest.fixture(autouse=True)
def _barramento_limpo() -> Iterator[None]:
    eventos.limpar_barramento()
    yield
    eventos.limpar_barramento()


async def _criar_tipo_tratamento(
    sessao: AsyncSession, tenant_id: UUID, *, categoria: str, sufixo: str
) -> UUID:
    tipo_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO tipos_tratamento "
            "(id, tenant_id, codigo, nome, categoria, exige_aprovacao, ativo) "
            "VALUES (:id, :tenant_id, :codigo, :nome, :categoria, TRUE, TRUE)"
        ),
        {
            "id": tipo_id,
            "tenant_id": tenant_id,
            "codigo": f"TT-{sufixo}",
            "nome": f"Tipo de tratamento {sufixo}",
            "categoria": categoria,
        },
    )
    return tipo_id


async def _criar_tipo_solicitacao(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    categoria: str,
    sufixo: str,
    tipo_tratamento_id: UUID | None,
    papeis: str = '[{"etapa": 1, "papel": "gestor"}]',
) -> UUID:
    tipo_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO tipos_solicitacao "
            "(id, tenant_id, codigo, nome, categoria, etapas, exige_justificativa, "
            " tipo_tratamento_id, ativo) "
            "VALUES (:id, :tenant_id, :codigo, :nome, :categoria, :etapas, TRUE, "
            "        :tipo_tratamento_id, TRUE)"
        ),
        {
            "id": tipo_id,
            "tenant_id": tenant_id,
            "codigo": f"TS-{sufixo}",
            "nome": f"Tipo de solicitacao {sufixo}",
            "categoria": categoria,
            "etapas": papeis,
            "tipo_tratamento_id": tipo_tratamento_id,
        },
    )
    return tipo_id


async def _criar_solicitacao_direta(
    sessao: AsyncSession,
    contexto: ContextoF10,
    *,
    tipo_solicitacao_id: UUID,
    payload: dict[str, object] | None = None,
    data_referencia: dt.date | None = None,
    data_inicio: dt.date | None = None,
    data_fim: dt.date | None = None,
) -> Solicitacao:
    """Cria a `Solicitacao` (e a primeira etapa, exigida por FK de
    `tratamentos.solicitacao_id` em nenhum lugar, mas coerente com o
    restante do sistema) via `criar_solicitacao` real (T2) -- não faz
    `INSERT` cru na tabela de negócio (só nos catálogos de tipo, que são
    dado de configuração, não fluxo de solicitação)."""
    import app.schemas.contrato as esquemas

    corpo: dict[str, object] = {
        "tipoSolicitacaoId": str(tipo_solicitacao_id),
        "colaboradorId": str(contexto.colaborador_id),
        "descricao": "Solicitacao de teste do despachante (T4).",
    }
    if payload:
        corpo["payload"] = payload
    if data_referencia is not None:
        corpo["dataReferencia"] = data_referencia.isoformat()
    else:
        corpo["dataInicio"] = (data_inicio or dt.date.today()).isoformat()
        corpo["dataFim"] = (data_fim or data_inicio or dt.date.today()).isoformat()

    dados = esquemas.SolicitacaoCriar.model_validate(corpo)
    return await servico.criar_solicitacao(sessao, contexto.tenant_id, dados, usuario_id=None)


async def _tratamentos_da_solicitacao(
    sessao: AsyncSession, tenant_id: UUID, solicitacao_id: UUID
) -> list[Tratamento]:
    consulta = sa.select(Tratamento).where(
        Tratamento.tenant_id == tenant_id, Tratamento.solicitacao_id == solicitacao_id
    )
    return list((await sessao.execute(consulta)).scalars().all())


async def test_ajuste_ponto_materializa_tratamento_aprovado(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    solicitacao = await _criar_solicitacao_direta(
        sessao_f10,
        contexto_f10,
        tipo_solicitacao_id=contexto_f10.tipo_solicitacao_id,
        data_referencia=dt.date.today() - dt.timedelta(days=1),
    )
    await materializar_solicitacao_aprovada(
        sessao_f10, contexto_f10.tenant_id, solicitacao, aprovador_usuario_id=None
    )
    tratamentos = await _tratamentos_da_solicitacao(
        sessao_f10, contexto_f10.tenant_id, solicitacao.id
    )
    assert len(tratamentos) == 1
    assert tratamentos[0].status in _STATUS_MATERIALIZADO
    assert tratamentos[0].tipo_tratamento_id == contexto_f10.tipo_tratamento_id


async def test_abono_materializa_tratamento_aprovado(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    tipo_tratamento_id = await _criar_tipo_tratamento(
        sessao_f10, contexto_f10.tenant_id, categoria="abono", sufixo="abono"
    )
    tipo_solicitacao_id = await _criar_tipo_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        categoria="abono",
        sufixo="abono",
        tipo_tratamento_id=tipo_tratamento_id,
    )
    solicitacao = await _criar_solicitacao_direta(
        sessao_f10, contexto_f10, tipo_solicitacao_id=tipo_solicitacao_id
    )
    await materializar_solicitacao_aprovada(
        sessao_f10, contexto_f10.tenant_id, solicitacao, aprovador_usuario_id=None
    )
    tratamentos = await _tratamentos_da_solicitacao(
        sessao_f10, contexto_f10.tenant_id, solicitacao.id
    )
    assert len(tratamentos) == 1
    assert tratamentos[0].status in _STATUS_MATERIALIZADO


async def test_justificativa_materializa_tratamento_aprovado(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    tipo_tratamento_id = await _criar_tipo_tratamento(
        sessao_f10, contexto_f10.tenant_id, categoria="justificativa", sufixo="just"
    )
    tipo_solicitacao_id = await _criar_tipo_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        categoria="justificativa",
        sufixo="just",
        tipo_tratamento_id=tipo_tratamento_id,
    )
    solicitacao = await _criar_solicitacao_direta(
        sessao_f10, contexto_f10, tipo_solicitacao_id=tipo_solicitacao_id
    )
    await materializar_solicitacao_aprovada(
        sessao_f10, contexto_f10.tenant_id, solicitacao, aprovador_usuario_id=None
    )
    tratamentos = await _tratamentos_da_solicitacao(
        sessao_f10, contexto_f10.tenant_id, solicitacao.id
    )
    assert len(tratamentos) == 1
    assert tratamentos[0].status in _STATUS_MATERIALIZADO


async def test_compensacao_materializa_um_tratamento_por_dia_do_intervalo(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    tipo_tratamento_id = await _criar_tipo_tratamento(
        sessao_f10, contexto_f10.tenant_id, categoria="compensacao", sufixo="comp"
    )
    tipo_solicitacao_id = await _criar_tipo_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        categoria="compensacao",
        sufixo="comp",
        tipo_tratamento_id=tipo_tratamento_id,
    )
    inicio = dt.date.today() - dt.timedelta(days=3)
    fim = dt.date.today() - dt.timedelta(days=1)
    solicitacao = await _criar_solicitacao_direta(
        sessao_f10,
        contexto_f10,
        tipo_solicitacao_id=tipo_solicitacao_id,
        data_inicio=inicio,
        data_fim=fim,
        payload={"minutosAjuste": 60},
    )
    await materializar_solicitacao_aprovada(
        sessao_f10, contexto_f10.tenant_id, solicitacao, aprovador_usuario_id=None
    )
    tratamentos = await _tratamentos_da_solicitacao(
        sessao_f10, contexto_f10.tenant_id, solicitacao.id
    )
    assert len(tratamentos) == 3  # um por dia do intervalo, inclusive
    assert all(t.status in _STATUS_MATERIALIZADO for t in tratamentos)
    assert all(t.minutos_ajuste == 60 for t in tratamentos)


async def test_afastamento_retroativo_materializa_tratamento_com_tipo_afastamento(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    tipo_tratamento_id = await _criar_tipo_tratamento(
        sessao_f10, contexto_f10.tenant_id, categoria="afastamento", sufixo="afast"
    )
    tipo_solicitacao_id = await _criar_tipo_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        categoria="afastamento",
        sufixo="afast",
        tipo_tratamento_id=tipo_tratamento_id,
        papeis='[{"etapa": 1, "papel": "rh"}]',
    )
    solicitacao = await _criar_solicitacao_direta(
        sessao_f10,
        contexto_f10,
        tipo_solicitacao_id=tipo_solicitacao_id,
        data_referencia=dt.date.today() - dt.timedelta(days=5),
        payload={"tipoAfastamentoId": str(contexto_f10.tipo_afastamento_ferias_id)},
    )
    await materializar_solicitacao_aprovada(
        sessao_f10, contexto_f10.tenant_id, solicitacao, aprovador_usuario_id=None
    )
    tratamentos = await _tratamentos_da_solicitacao(
        sessao_f10, contexto_f10.tenant_id, solicitacao.id
    )
    assert len(tratamentos) == 1
    assert tratamentos[0].status in _STATUS_MATERIALIZADO
    assert tratamentos[0].tipo_afastamento_id == contexto_f10.tipo_afastamento_ferias_id


async def test_ferias_materializa_afastamento_aprovado(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    tipo_solicitacao_id = await _criar_tipo_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        categoria="ferias",
        sufixo="ferias",
        tipo_tratamento_id=None,
        papeis='[{"etapa": 1, "papel": "gestor"}, {"etapa": 2, "papel": "rh"}]',
    )
    inicio = dt.date.today() + dt.timedelta(days=10)
    fim = dt.date.today() + dt.timedelta(days=20)
    solicitacao = await _criar_solicitacao_direta(
        sessao_f10,
        contexto_f10,
        tipo_solicitacao_id=tipo_solicitacao_id,
        data_inicio=inicio,
        data_fim=fim,
    )
    await materializar_solicitacao_aprovada(
        sessao_f10, contexto_f10.tenant_id, solicitacao, aprovador_usuario_id=None
    )

    consulta = sa.select(Afastamento).where(
        Afastamento.tenant_id == contexto_f10.tenant_id,
        Afastamento.solicitacao_id == solicitacao.id,
    )
    afastamentos = list((await sessao_f10.execute(consulta)).scalars().all())
    assert len(afastamentos) == 1
    assert afastamentos[0].status == "aprovado"
    assert afastamentos[0].tipo_afastamento_id == contexto_f10.tipo_afastamento_ferias_id

    publicados = [e for e in eventos.BARRAMENTO_INTERNO if e["tipo"] == "ajuste.aprovado"]
    assert len(publicados) == 1
    assert "tratamentoId" not in publicados[0]["dados"]


async def test_folga_debita_banco_de_horas(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    politica_id = uuid.uuid4()
    await sessao_f10.execute(
        text(
            "INSERT INTO bh_politicas "
            "(id, tenant_id, empresa_id, codigo, nome, regime, periodo_meses, vigencia_inicio) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'Politica de teste', 'individual', "
            "        1, :vigencia_inicio)"
        ),
        {
            "id": politica_id,
            "tenant_id": contexto_f10.tenant_id,
            "empresa_id": contexto_f10.empresa_id,
            "codigo": f"POL-{uuid.uuid4().hex[:8]}",
            "vigencia_inicio": dt.date(2020, 1, 1),
        },
    )
    conta_id = uuid.uuid4()
    await sessao_f10.execute(
        text(
            "INSERT INTO bh_contas "
            "(id, tenant_id, colaborador_id, vinculo_id, bh_politica_id, codigo, nome, "
            " periodo_inicio, periodo_fim, saldo_atual_minutos) "
            "VALUES (:id, :tenant_id, :colaborador_id, :vinculo_id, :politica_id, 'normal', "
            "        'Conta de teste', :inicio, :fim, 600)"
        ),
        {
            "id": conta_id,
            "tenant_id": contexto_f10.tenant_id,
            "colaborador_id": contexto_f10.colaborador_id,
            "vinculo_id": contexto_f10.vinculo_id,
            "politica_id": politica_id,
            "inicio": contexto_f10.periodo_data_inicio,
            "fim": contexto_f10.periodo_data_fim,
        },
    )

    tipo_solicitacao_id = await _criar_tipo_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        categoria="folga",
        sufixo="folga",
        tipo_tratamento_id=None,
    )
    # Uma segunda-feira futura (dia util na jornada semeada pela fixture).
    dia_util = dt.date.today() + dt.timedelta(days=14)
    while dia_util.weekday() != 0:  # 0 = segunda-feira
        dia_util += dt.timedelta(days=1)

    solicitacao = await _criar_solicitacao_direta(
        sessao_f10,
        contexto_f10,
        tipo_solicitacao_id=tipo_solicitacao_id,
        data_inicio=dia_util,
        data_fim=dia_util,
    )
    await materializar_solicitacao_aprovada(
        sessao_f10, contexto_f10.tenant_id, solicitacao, aprovador_usuario_id=None
    )

    saldo = await sessao_f10.scalar(
        text("SELECT saldo_atual_minutos FROM bh_contas WHERE id = :id"), {"id": conta_id}
    )
    assert saldo == 600 - 480  # 480 min = carga do dia util da jornada semeada

    publicados = [e for e in eventos.BARRAMENTO_INTERNO if e["tipo"] == "ajuste.aprovado"]
    assert len(publicados) == 1


async def test_troca_escala_nao_materializa_nada(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    tipo_solicitacao_id = await _criar_tipo_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        categoria="troca_escala",
        sufixo="troca",
        tipo_tratamento_id=None,
    )
    solicitacao = await _criar_solicitacao_direta(
        sessao_f10, contexto_f10, tipo_solicitacao_id=tipo_solicitacao_id
    )
    await materializar_solicitacao_aprovada(
        sessao_f10, contexto_f10.tenant_id, solicitacao, aprovador_usuario_id=None
    )
    tratamentos = await _tratamentos_da_solicitacao(
        sessao_f10, contexto_f10.tenant_id, solicitacao.id
    )
    assert tratamentos == []
    assert eventos.BARRAMENTO_INTERNO == []


async def test_categoria_configurada_pelo_tenant_tambem_materializa_via_tratamento(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    """Prova de que o despachante é genérico: uma categoria FORA do seed de
    fábrica (`outro`), configurada pelo tenant com um `tipo_tratamento_id`
    próprio, materializa exatamente como as categorias conhecidas -- não é
    uma lista fixa de `if categoria == ...`."""
    tipo_tratamento_id = await _criar_tipo_tratamento(
        sessao_f10, contexto_f10.tenant_id, categoria="ajuste_saldo", sufixo="tenant"
    )
    tipo_solicitacao_id = await _criar_tipo_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        categoria="outro",
        sufixo="tenant",
        tipo_tratamento_id=tipo_tratamento_id,
    )
    solicitacao = await _criar_solicitacao_direta(
        sessao_f10, contexto_f10, tipo_solicitacao_id=tipo_solicitacao_id
    )
    await materializar_solicitacao_aprovada(
        sessao_f10, contexto_f10.tenant_id, solicitacao, aprovador_usuario_id=None
    )
    tratamentos = await _tratamentos_da_solicitacao(
        sessao_f10, contexto_f10.tenant_id, solicitacao.id
    )
    assert len(tratamentos) == 1
    assert tratamentos[0].status in _STATUS_MATERIALIZADO
