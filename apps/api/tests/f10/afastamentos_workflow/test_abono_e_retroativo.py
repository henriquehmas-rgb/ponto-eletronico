"""T13 (F10, agente A4) — prova de reaproveitamento para `abono` e
`afastamento` (retroativo).

Não há código novo aqui (T13, "pronto quando" do PCF §6): o despachante
genérico que materializa estas duas categorias é `app.workflow.solicitacoes.
materializacao.materializar_solicitacao_aprovada` (A1, T4), que por sua vez
chama `app.apuracao.tratamento.servico.criar_tratamento`/`app.apuracao.
tratamento.decisao.decidir_tratamento` (F4, já implementados e testados) —
este módulo só exercita, ponta a ponta, o caminho HTTP-equivalente completo
(`criar_solicitacao` → `decidir_aprovacao`, ambos de A1) até a apuração do
dia mudar, chamando `apurar_dia` (F4, A1) apenas como leitura/observação do
efeito, nunca reimplementando cálculo.

**Achado original (28/07/2026), corrigido em 07/08/2026 (ADR-011)**:
`app.apuracao.dominio.servico::apurar_dia` não dava efeito numérico a
`Tratamento` de categoria `afastamento` — o `Tratamento` era criado e
aprovado corretamente, mas `falta_minutos`/`tipo_dia` ficavam inalterados.
Corrigido: um `Tratamento` de categoria `afastamento` aprovado/aplicado
agora abona o dia inteiro (mesmo efeito de um `abono` sem `minutos_ajuste`)
e força `tipo_dia = 'afastamento'` na gravação, mesma precedência que
`_afastamento_vigente` já tem no resolvedor de F3 para o caso futuro/vigente
(que, achado adicional da mesma investigação, também nunca tinha esse
efeito numérico — corrigido junto). O teste
`test_afastamento_retroativo...` abaixo agora prova os dois: criação/
aprovação do `Tratamento` (como antes) E o efeito na apuração (novo).
"""

from __future__ import annotations

import datetime as dt
import secrets

from ponto_contracts import TipoAfastamento, TipoTratamento, Tratamento
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.dominio.servico import apurar_dia
from app.apuracao.tratamento import eventos as eventos_tratamento
from app.schemas import contrato as esquemas
from app.workflow.aprovacoes.servico import decidir_aprovacao
from app.workflow.solicitacoes.servico import criar_solicitacao
from tests.f10.afastamentos_workflow.test_materializar_ferias_ou_folga import (
    _criar_tipo_solicitacao,
)
from tests.f10.conftest import ContextoF10

# Segunda-feira, util na jornada de `contexto_f10` (480 min/dia). Data
# diferente das usadas em `test_materializar_ferias_ou_folga.py` só por
# clareza de leitura do relatório -- cada teste tem seu próprio tenant via
# `contexto_f10`, não há risco real de colisão entre os dois arquivos.
_SEGUNDA = dt.date(2026, 8, 10)


def _limpar_barramento_f4():
    eventos_tratamento.limpar_barramento()


async def test_abono_falta_aprovado_zera_a_falta_da_apuracao(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    _limpar_barramento_f4()

    # Apura o dia ANTES de qualquer tratamento: sem marcacoes, a jornada
    # util de 480 min vira falta integral (`falta_minutos = max(0, previsto
    # - trabalhado - abono)`, `app/apuracao/dominio/calculo.py`).
    apuracao_antes = await apurar_dia(
        sessao_f10, contexto_f10.tenant_id, contexto_f10.vinculo_id, _SEGUNDA
    )
    assert apuracao_antes.falta_minutos == 480
    await sessao_f10.flush()

    tipo_tratamento = TipoTratamento(
        tenant_id=contexto_f10.tenant_id,
        codigo=f"ABONO-{secrets.token_hex(5)}",
        nome="Abono de falta (teste T13)",
        categoria="abono",
        exige_aprovacao=True,
        ativo=True,
    )
    sessao_f10.add(tipo_tratamento)
    await sessao_f10.flush()

    tipo_solicitacao = await _criar_tipo_solicitacao(
        sessao_f10, contexto_f10.tenant_id, categoria="abono"
    )
    # `_criar_tipo_solicitacao` (do módulo T12) não fixa `tipo_tratamento_id`
    # -- ajuste local, direto no objeto ORM já persistido, sem tocar em
    # nenhum arquivo de ownership de A1.
    tipo_solicitacao.tipo_tratamento_id = tipo_tratamento.id
    await sessao_f10.flush()

    solicitacao = await criar_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        esquemas.SolicitacaoCriar.model_validate(
            {
                "tipoSolicitacaoId": tipo_solicitacao.id,
                "colaboradorId": contexto_f10.colaborador_id,
                "vinculoId": contexto_f10.vinculo_id,
                "dataReferencia": _SEGUNDA,
                "descricao": "Abono de falta (teste T13, prova de reaproveitamento).",
            }
        ),
        usuario_id=contexto_f10.colaborador_usuario_id,
    )
    assert solicitacao.etapa_atual == 1

    from ponto_contracts import Aprovacao

    aprovacao = (
        await sessao_f10.execute(
            select(Aprovacao).where(
                Aprovacao.solicitacao_id == solicitacao.id, Aprovacao.etapa == 1
            )
        )
    ).scalar_one()

    await decidir_aprovacao(
        sessao_f10,
        contexto_f10.tenant_id,
        aprovacao.id,
        esquemas.DecisaoRequisicao.model_validate({"decisao": "aprovar"}),
        usuario_id=contexto_f10.gestor_usuario_id,
    )

    tratamento = (
        await sessao_f10.execute(
            select(Tratamento).where(Tratamento.solicitacao_id == solicitacao.id)
        )
    ).scalar_one()
    # 'aplicado' (nao so 'aprovado'): o recalculo disparado por
    # `decidir_tratamento` (F4) ja consumiu o tratamento na apuracao do dia
    # ANTES desta consulta -- prova mais forte de reaproveitamento real do
    # que apenas "aprovado" ficaria (F4, `apurar_dia`, promove o status
    # quando o hash muda e o tratamento entra em `tratamentos_consumidos`).
    assert tratamento.status in ("aprovado", "aplicado")
    assert tratamento.tipo_tratamento_id == tipo_tratamento.id
    assert tratamento.data_referencia == _SEGUNDA
    assert tratamento.origem == "sistema"

    # `decidir_tratamento` (F4) ja agenda `recalcular_periodo` -- a falta
    # que existia antes do abono deve ter sumido da apuracao.
    apuracao_depois = await apurar_dia(
        sessao_f10, contexto_f10.tenant_id, contexto_f10.vinculo_id, _SEGUNDA
    )
    assert apuracao_depois.falta_minutos == 0
    assert apuracao_depois.abono_minutos == 480

    # `ajuste.aprovado` publicado por F4 (nao pelo modulo de eventos de A1
    # nem de A4 -- prova de que o caminho de tratamento reaproveita o
    # mecanismo de publicacao ja existente, PCF §2.1), com `tratamentoId`
    # PRESENTE (diferente de ferias/folga, T12).
    eventos_ajuste = [
        e for e in eventos_tratamento.BARRAMENTO_INTERNO if e["tipo"] == "ajuste.aprovado"
    ]
    assert len(eventos_ajuste) == 1
    assert eventos_ajuste[0]["dados"]["solicitacaoId"] == str(solicitacao.id)
    assert eventos_ajuste[0]["dados"]["tratamentoId"] == str(tratamento.id)


async def test_afastamento_retroativo_cria_e_aprova_tratamento_via_despachante_de_a1(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    """Ver docstring do módulo (ADR-011, corrigido em 07/08/2026): prova que
    o `Tratamento` retroativo é criado e aprovado corretamente pelo
    despachante genérico de A1 + F4 (reaproveitamento, critério de aceite 7)
    E que a apuração do dia reflete o afastamento (falta zerada, `tipo_dia`
    forçado para `'afastamento'`) -- mesmo padrão de
    `test_abono_falta_aprovado_zera_a_falta_da_apuracao` acima."""
    _limpar_barramento_f4()

    # Apura o dia ANTES de qualquer tratamento: sem marcacoes, a jornada
    # util de 480 min vira falta integral -- mesma logica do teste de abono
    # acima, prova que o dia comeca "normal" antes da correcao retroativa.
    apuracao_antes = await apurar_dia(
        sessao_f10, contexto_f10.tenant_id, contexto_f10.vinculo_id, _SEGUNDA
    )
    assert apuracao_antes.falta_minutos == 480
    assert apuracao_antes.tipo_dia == "util"
    await sessao_f10.flush()

    tipo_afastamento_retroativo = TipoAfastamento(
        tenant_id=contexto_f10.tenant_id,
        codigo=f"ATESTADO-{secrets.token_hex(5)}",
        nome="Atestado (teste T13)",
        categoria="atestado",
        ativo=True,
    )
    sessao_f10.add(tipo_afastamento_retroativo)
    await sessao_f10.flush()

    tipo_tratamento = TipoTratamento(
        tenant_id=contexto_f10.tenant_id,
        codigo=f"AFRETRO-{secrets.token_hex(5)}",
        nome="Afastamento retroativo (teste T13)",
        categoria="afastamento",
        exige_aprovacao=True,
        ativo=True,
    )
    sessao_f10.add(tipo_tratamento)
    await sessao_f10.flush()

    tipo_solicitacao = await _criar_tipo_solicitacao(
        sessao_f10, contexto_f10.tenant_id, categoria="afastamento"
    )
    tipo_solicitacao.tipo_tratamento_id = tipo_tratamento.id
    await sessao_f10.flush()

    solicitacao = await criar_solicitacao(
        sessao_f10,
        contexto_f10.tenant_id,
        esquemas.SolicitacaoCriar.model_validate(
            {
                "tipoSolicitacaoId": tipo_solicitacao.id,
                "colaboradorId": contexto_f10.colaborador_id,
                "vinculoId": contexto_f10.vinculo_id,
                "dataReferencia": _SEGUNDA,
                "descricao": "Atestado medico (teste T13, afastamento retroativo).",
                "payload": {"tipoAfastamentoId": str(tipo_afastamento_retroativo.id)},
            }
        ),
        usuario_id=contexto_f10.colaborador_usuario_id,
    )

    from ponto_contracts import Aprovacao

    aprovacao = (
        await sessao_f10.execute(
            select(Aprovacao).where(
                Aprovacao.solicitacao_id == solicitacao.id, Aprovacao.etapa == 1
            )
        )
    ).scalar_one()

    await decidir_aprovacao(
        sessao_f10,
        contexto_f10.tenant_id,
        aprovacao.id,
        esquemas.DecisaoRequisicao.model_validate({"decisao": "aprovar"}),
        usuario_id=contexto_f10.rh_usuario_id,
    )

    tratamento = (
        await sessao_f10.execute(
            select(Tratamento).where(Tratamento.solicitacao_id == solicitacao.id)
        )
    ).scalar_one()
    # 'aplicado' (nao so 'aprovado'): com o fix do ADR-011, o Tratamento
    # passa a ter efeito numerico e entra em `tratamentos_consumidos` --
    # `apurar_dia` promove o status quando o hash muda, mesmo padrao ja
    # visto no teste de abono acima. Antes do fix, `afastamento` nunca era
    # consumido e ficava preso em 'aprovado' (o que o achado original
    # documentava).
    assert tratamento.status in ("aprovado", "aplicado")
    assert tratamento.tipo_afastamento_id == tipo_afastamento_retroativo.id
    assert tratamento.tipo_tratamento_id == tipo_tratamento.id

    # `decidir_tratamento` (F4) ja agenda `recalcular_periodo` -- a falta
    # que existia antes do afastamento deve ter sumido, e o dia passa a ser
    # rotulado como afastamento (ADR-011).
    apuracao_depois = await apurar_dia(
        sessao_f10, contexto_f10.tenant_id, contexto_f10.vinculo_id, _SEGUNDA
    )
    assert apuracao_depois.falta_minutos == 0
    assert apuracao_depois.abono_minutos == 480
    assert apuracao_depois.tipo_dia == "afastamento"

    eventos_ajuste = [
        e for e in eventos_tratamento.BARRAMENTO_INTERNO if e["tipo"] == "ajuste.aprovado"
    ]
    assert len(eventos_ajuste) == 1
    assert eventos_ajuste[0]["dados"]["tratamentoId"] == str(tratamento.id)


async def test_afastamento_vigente_via_tabela_afastamentos_tambem_zera_a_falta(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    """Achado adicional da mesma investigação (ADR-011, 07/08/2026): o
    caminho "de fábrica" (afastamento futuro/vigente, resolvido por
    `app.jornada.resolvedor.servico::_afastamento_vigente` via a tabela
    `afastamentos` -- SEM passar por `Tratamento` nenhum) já rotulava
    `tipoDia = 'afastamento'` desde a Fase 0, mas também nunca zerava a
    falta -- nenhum teste de F3/F4 exercitava esse caminho até `apurar_dia`.
    Corrigido junto com o caso retroativo acima (mesmo `if` em
    `apurar_dia`). Diferente dos dois testes acima, este não passa por
    `Tratamento`/workflow de aprovação nenhum -- `Afastamento` é inserido
    direto, exatamente como uma fase futura (F9b/painel RH) já faz hoje."""
    _limpar_barramento_f4()

    from ponto_contracts import Afastamento

    tipo_afastamento = TipoAfastamento(
        tenant_id=contexto_f10.tenant_id,
        codigo=f"FERIAS-{secrets.token_hex(5)}",
        nome="Ferias (teste T13, afastamento vigente)",
        categoria="ferias",
        ativo=True,
    )
    sessao_f10.add(tipo_afastamento)
    await sessao_f10.flush()

    afastamento = Afastamento(
        tenant_id=contexto_f10.tenant_id,
        colaborador_id=contexto_f10.colaborador_id,
        vinculo_id=contexto_f10.vinculo_id,
        tipo_afastamento_id=tipo_afastamento.id,
        data_inicio=_SEGUNDA,
        data_fim=_SEGUNDA,
        periodo_parcial=False,
        status="aprovado",
        origem="manual",
    )
    sessao_f10.add(afastamento)
    # flush(), nao commit(): SET LOCAL app.tenant_id (RLS) vale so pra
    # transacao corrente -- um commit() aqui encerraria a transacao e a
    # chamada a apurar_dia logo abaixo, na MESMA sessao, rodaria sem tenant
    # nenhum publicado (achado real, ja documentado nesta sessao para
    # apps/worker/worker/tarefas/relatorios.py: mesmo padrao de bug).
    await sessao_f10.flush()

    apuracao = await apurar_dia(
        sessao_f10, contexto_f10.tenant_id, contexto_f10.vinculo_id, _SEGUNDA
    )
    assert apuracao.tipo_dia == "afastamento"
    assert apuracao.falta_minutos == 0
    assert apuracao.abono_minutos == 480
