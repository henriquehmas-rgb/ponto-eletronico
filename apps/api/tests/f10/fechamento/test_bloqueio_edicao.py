"""Critério de aceite 2 do PCF (`docs/fases/F10-workflows-aprovacoes-fechamento.md`,
§7): "fechar um período trava a edição dos dias cobertos".

A trava em si é de F4 (`app.apuracao.tratamento.fechamento.
verificar_periodo_aberto`, congelada -- ver docstring de `servico.py`); este
módulo só cria a linha `fechamentos.status='fechado'` que a ativa. Este
arquivo prova, com teste real e committável (o T15/T16 só tinha confirmado
isto com um script ad-hoc, descartável), que `criarTratamento` e
`decidirTratamento` (F4, só importados/chamados, nunca duplicados aqui)
respondem `PONTO-PER-001` para um dia coberto por um fechamento -- e
continuam funcionando normalmente para um dia FORA do período fechado
(prova negativa: não é um teste que só verifica o caminho feliz).

`test_worker_tarefas.py::test_criar_fechamento_para_periodo_ja_fechado_e_per_002_sincrono`
já prova que `criarFechamento` + `processar_fechamento` (pipeline completo,
via worker) produzem uma linha `fechamentos.status='fechado'` de verdade.
Este arquivo insere essa linha diretamente (mesmo padrão que
`test_servico.py::test_criar_fechamento_ja_fechado_e_per_002`/
`test_reabrir_sem_motivo_e_per_003` já usam) para isolar a prova no efeito
que interessa aqui -- a trava de EDIÇÃO em F4 -- sem acoplar de novo ao
worker/Redis/MinIO.
"""

from __future__ import annotations

import datetime as dt

import pytest
from ponto_contracts import Fechamento, Tratamento

from app.apuracao.tratamento import decisao as f4_decisao
from app.apuracao.tratamento import servico as f4_tratamento_servico
from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from tests.f10.conftest import ContextoF10, aplicar_tenant_teste

CODIGO_PERIODO_FECHADO = "PONTO-PER-001"


def _corpo_criar_tratamento(
    contexto: ContextoF10, *, data_referencia: dt.date
) -> esquemas.TratamentoCriar:
    return esquemas.TratamentoCriar(
        colaboradorId=contexto.colaborador_id,
        vinculoId=contexto.vinculo_id,
        tipoTratamentoId=contexto.tipo_tratamento_id,
        dataReferencia=data_referencia,
        motivo="Ajuste de teste do criterio de aceite 2 (F10).",
    )


async def _fechar_periodo_da_fixture(sessao, contexto: ContextoF10) -> Fechamento:
    """Insere `fechamentos.status='fechado'` cobrindo `[periodo_data_inicio,
    periodo_data_fim]` no escopo `empresa` -- exatamente o que
    `verificar_periodo_aberto` (F4) procura para travar."""
    fechamento = Fechamento(
        tenant_id=contexto.tenant_id,
        periodo_id=contexto.periodo_id,
        empresa_id=contexto.empresa_id,
        escopo="empresa",
        status="fechado",
        fechado_em=dt.datetime.now(tz=dt.UTC),
        fechado_por=contexto.rh_usuario_id,
    )
    sessao.add(fechamento)
    await sessao.flush()
    await sessao.commit()
    await aplicar_tenant_teste(sessao, contexto.tenant_id)
    return fechamento


@pytest.mark.asyncio
async def test_criar_tratamento_em_dia_fechado_e_per_001(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    await _fechar_periodo_da_fixture(sessao_f10, contexto_f10)
    dia_travado = contexto_f10.periodo_data_inicio

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await f4_tratamento_servico.criar_tratamento(
            sessao_f10,
            contexto_f10.tenant_id,
            _corpo_criar_tratamento(contexto_f10, data_referencia=dia_travado),
            usuario_id=contexto_f10.rh_usuario_id,
        )
    assert excinfo.value.codigo == CODIGO_PERIODO_FECHADO

    # Nenhum Tratamento foi criado -- a trava recusou ANTES de gravar.
    import sqlalchemy as sa

    total = (
        await sessao_f10.execute(
            sa.select(sa.func.count()).where(
                Tratamento.tenant_id == contexto_f10.tenant_id,
                Tratamento.vinculo_id == contexto_f10.vinculo_id,
                Tratamento.data_referencia == dia_travado,
            )
        )
    ).scalar_one()
    assert total == 0


@pytest.mark.asyncio
async def test_decidir_tratamento_criado_antes_do_fechamento_e_per_001(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    """O tratamento é criado com o período AINDA aberto (criarTratamento
    funciona normalmente); só depois o período é fechado. `decidirTratamento`
    precisa recusar a APROVAÇÃO com `PONTO-PER-001` mesmo assim -- a trava
    de F4 é checada de novo em `decidir_tratamento`/`_aprovar`, não só na
    criação."""
    dia_travado = contexto_f10.periodo_data_inicio

    tratamento = await f4_tratamento_servico.criar_tratamento(
        sessao_f10,
        contexto_f10.tenant_id,
        _corpo_criar_tratamento(contexto_f10, data_referencia=dia_travado),
        usuario_id=contexto_f10.rh_usuario_id,
    )
    assert tratamento.status == "pendente"
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)

    await _fechar_periodo_da_fixture(sessao_f10, contexto_f10)

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await f4_decisao.decidir_tratamento(
            sessao_f10,
            contexto_f10.tenant_id,
            tratamento.id,
            esquemas.DecisaoRequisicao(decisao=esquemas.Decisao1.aprovar),
            usuario_id=contexto_f10.rh_usuario_id,
        )
    assert excinfo.value.codigo == CODIGO_PERIODO_FECHADO

    # O tratamento continua "pendente" -- a decisao recusada nao mudou nada.
    tratamento_relido = await f4_tratamento_servico.obter_tratamento(sessao_f10, tratamento.id)
    assert tratamento_relido.status == "pendente"


@pytest.mark.asyncio
async def test_criar_e_decidir_tratamento_fora_do_periodo_fechado_continua_funcionando(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    """Prova negativa do criterio de aceite 2: o MESMO fechamento fechado
    (cobrindo só `[periodo_data_inicio, periodo_data_fim]`) não trava um dia
    de fora desse intervalo -- criarTratamento/decidirTratamento continuam
    funcionando normalmente para ele."""
    await _fechar_periodo_da_fixture(sessao_f10, contexto_f10)

    dia_fora = contexto_f10.periodo_data_inicio - dt.timedelta(days=90)
    assert not (contexto_f10.periodo_data_inicio <= dia_fora <= contexto_f10.periodo_data_fim)

    tratamento = await f4_tratamento_servico.criar_tratamento(
        sessao_f10,
        contexto_f10.tenant_id,
        _corpo_criar_tratamento(contexto_f10, data_referencia=dia_fora),
        usuario_id=contexto_f10.rh_usuario_id,
    )
    assert tratamento.status == "pendente"
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)

    decidido = await f4_decisao.decidir_tratamento(
        sessao_f10,
        contexto_f10.tenant_id,
        tratamento.id,
        esquemas.DecisaoRequisicao(decisao=esquemas.Decisao1.aprovar),
        usuario_id=contexto_f10.rh_usuario_id,
    )
    assert decidido.status == "aprovado"
    assert decidido.aprovado_por == contexto_f10.rh_usuario_id
