"""Fixtures locais dos testes de `app.fiscal.aej` (F12/A2).

Independente e complementar a `apps/api/tests/f12/conftest.py` (A1,
compartilhada da fase inteira -- fornece `sessao_f12`/`contexto_f12`/
`gerar_marcacoes_reais`, que este arquivo reaproveita sem editar). Aqui só
vive o que é específico do AEJ e não interessa a A1/A3: semeadura de
horário/jornada (para o bloco tipo "04") e de banco de horas (para a
reconciliação do bloco tipo "07"), sempre por `INSERT` direto para os dados
de CADASTRO (mesmo padrão que `tests/f4/banco_horas/conftest.py` e o
`contexto_f12` de A1 já usam para REP-P/empresa/vínculo) -- os LANÇAMENTOS
de banco de horas, ao contrário, passam pelo `lancar()` real de F4
(`app.apuracao.banco_horas.lancamentos`), nunca `INSERT` direto, para que
`minutos_equivalentes`/`saldo_apos_minutos`/a cadeia de hash sejam
calculados de verdade.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.banco_horas.lancamentos import lancar
from tests.f12.conftest import ContextoF12


async def semear_horario_jornada(
    sessao: AsyncSession,
    contexto: ContextoF12,
    *,
    entrada: dt.time = dt.time(8, 0),
    saida: dt.time = dt.time(17, 0),
    intervalo_inicio: dt.time = dt.time(12, 0),
    intervalo_fim: dt.time = dt.time(13, 0),
    carga_minutos: int = 480,
) -> UUID:
    """Semeia 1 `horarios` + 1 `jornadas` (tipo `fixa`) + `jornada_dias`
    (todo dia da semana com o mesmo horário) + `vinculo_jornadas` vigente
    para `contexto.vinculo_id`. Devolve `horarios.id`.

    Necessário para o bloco tipo "04" do AEJ (`codHorContratual`) resolver
    algo: `app.fiscal.aej.gerador` lê `apuracoes_dia.horario_id` (F4, só
    leitura) -- esta fixture não cria `apuracoes_dia` (isso é uma tarefa de
    F4, fora do ownership desta fase); quem precisa de uma linha de
    `apuracoes_dia` para o teste a insere via `INSERT` direto, coerente com
    `horario_id` devolvido aqui.
    """
    horario_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO horarios "
            "(id, tenant_id, empresa_id, codigo, nome, entrada, saida, "
            " intervalo_inicio, intervalo_fim, duracao_intervalo_minutos, carga_minutos) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'Horario de teste F12/A2', "
            "        :entrada, :saida, :intervalo_inicio, :intervalo_fim, 60, :carga)"
        ),
        {
            "id": horario_id,
            "tenant_id": contexto.tenant_id,
            "empresa_id": contexto.empresa_id,
            "codigo": f"H-{uuid.uuid4().hex[:8]}",
            "entrada": entrada,
            "saida": saida,
            "intervalo_inicio": intervalo_inicio,
            "intervalo_fim": intervalo_fim,
            "carga": carga_minutos,
        },
    )

    jornada_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO jornadas "
            "(id, tenant_id, empresa_id, codigo, nome, tipo, carga_diaria_minutos) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'Jornada de teste F12/A2', "
            "        'fixa', :carga)"
        ),
        {
            "id": jornada_id,
            "tenant_id": contexto.tenant_id,
            "empresa_id": contexto.empresa_id,
            "codigo": f"J-{uuid.uuid4().hex[:8]}",
            "carga": carga_minutos,
        },
    )

    for dia_semana in range(7):
        await sessao.execute(
            text(
                "INSERT INTO jornada_dias "
                "(id, tenant_id, jornada_id, dia_semana, tipo_dia, horario_id, carga_minutos) "
                "VALUES (:id, :tenant_id, :jornada_id, :dia_semana, 'util', :horario_id, :carga)"
            ),
            {
                "id": uuid.uuid4(),
                "tenant_id": contexto.tenant_id,
                "jornada_id": jornada_id,
                "dia_semana": dia_semana,
                "horario_id": horario_id,
                "carga": carga_minutos,
            },
        )

    await sessao.execute(
        text(
            "INSERT INTO vinculo_jornadas "
            "(id, tenant_id, vinculo_id, jornada_id, vigencia_inicio) "
            "VALUES (:id, :tenant_id, :vinculo_id, :jornada_id, :inicio)"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": contexto.tenant_id,
            "vinculo_id": contexto.vinculo_id,
            "jornada_id": jornada_id,
            "inicio": dt.date(2020, 1, 1),
        },
    )

    return horario_id


async def semear_apuracao_dia(
    sessao: AsyncSession,
    contexto: ContextoF12,
    *,
    data: dt.date,
    horario_id: UUID | None = None,
    tipo_dia: str = "util",
    previsto_minutos: int = 480,
    falta_minutos: int = 0,
    abono_minutos: int = 0,
) -> UUID:
    """`apuracoes_dia` é escrita exclusivamente por F4 em produção -- aqui,
    só leitura por `app.fiscal.aej.gerador`, é `INSERT` direto de fixture de
    teste (mesmo espírito de `rep_ps`/`nsr_sequencias` na fixture
    compartilhada de A1: dado de outra fase, semeado sem passar pela rota
    daquela fase, para não duplicar o motor de apuração aqui)."""
    apuracao_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO apuracoes_dia "
            "(id, tenant_id, vinculo_id, colaborador_id, data, empresa_id, horario_id, "
            " tipo_dia, previsto_minutos, falta_minutos, abono_minutos, status) "
            "VALUES (:id, :tenant_id, :vinculo_id, :colaborador_id, :data, :empresa_id, "
            "        :horario_id, :tipo_dia, :previsto, :falta, :abono, 'apurado')"
        ),
        {
            "id": apuracao_id,
            "tenant_id": contexto.tenant_id,
            "vinculo_id": contexto.vinculo_id,
            "colaborador_id": contexto.colaborador_id,
            "data": data,
            "empresa_id": contexto.empresa_id,
            "horario_id": horario_id,
            "tipo_dia": tipo_dia,
            "previsto": previsto_minutos,
            "falta": falta_minutos,
            "abono": abono_minutos,
        },
    )
    return apuracao_id


async def semear_banco_horas(
    sessao: AsyncSession, contexto: ContextoF12, *, periodo_inicio: dt.date, periodo_fim: dt.date
) -> UUID:
    """Semeia 1 `bh_politicas` + 1 `bh_contas` (`codigo='normal'`, `aberta`)
    por `INSERT` direto (dado de CADASTRO, mesmo padrão de
    `tests/f4/banco_horas/conftest.py`). Devolve `bh_contas.id` -- os
    LANÇAMENTOS em si são responsabilidade do teste, via `lancar()` real."""
    bh_politica_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO bh_politicas "
            "(id, tenant_id, empresa_id, codigo, nome, regime, periodo_meses, "
            " metodo_consumo, vigencia_inicio, ativo) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'Politica de teste F12/A2', "
            "        'individual', 6, 'fifo', :vigencia_inicio, TRUE)"
        ),
        {
            "id": bh_politica_id,
            "tenant_id": contexto.tenant_id,
            "empresa_id": contexto.empresa_id,
            "codigo": f"POL-{uuid.uuid4().hex[:8]}",
            "vigencia_inicio": dt.date(2020, 1, 1),
        },
    )

    bh_conta_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO bh_contas "
            "(id, tenant_id, colaborador_id, vinculo_id, bh_politica_id, codigo, nome, "
            " periodo_inicio, periodo_fim, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :vinculo_id, :bh_politica_id, "
            "        'normal', 'Banco de horas normal', :periodo_inicio, :periodo_fim, 'aberta')"
        ),
        {
            "id": bh_conta_id,
            "tenant_id": contexto.tenant_id,
            "colaborador_id": contexto.colaborador_id,
            "vinculo_id": contexto.vinculo_id,
            "bh_politica_id": bh_politica_id,
            "periodo_inicio": periodo_inicio,
            "periodo_fim": periodo_fim,
        },
    )
    return bh_conta_id


async def lancar_banco_horas(
    sessao: AsyncSession,
    contexto: ContextoF12,
    bh_conta_id: UUID,
    *,
    tipo: str,
    minutos: int,
    data_competencia: dt.date,
    descricao: str = "Lancamento de teste F12/A2",
) -> None:
    """Grava um lançamento real via `app.apuracao.banco_horas.lancamentos.
    lancar` (F4, reaproveitado) -- nunca `INSERT` direto em
    `bh_lancamentos`, para que `minutos_equivalentes`/`saldo_apos_minutos`/a
    cadeia de hash sejam calculados de verdade (mesmo espírito do T1 de A1
    para marcações: não mentir sobre como o dado chega ao banco)."""
    await lancar(
        sessao,
        tenant_id=contexto.tenant_id,
        bh_conta_id=bh_conta_id,
        tipo=tipo,
        origem="ajuste_manual",
        minutos=minutos,
        data_competencia=data_competencia,
        descricao=descricao,
        fator=Decimal("1.0"),
    )
    await sessao.flush()


async def semear_tipo_tratamento(
    sessao: AsyncSession, contexto: ContextoF12, *, categoria: str
) -> UUID:
    """`tipos_tratamento` é catálogo/config (F4, seed) -- `INSERT` direto,
    mesmo padrão que `tests/f4/tratamento` usa para este catálogo."""
    tipo_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO tipos_tratamento "
            "(id, tenant_id, codigo, nome, categoria, exige_aprovacao, exige_motivo, "
            " afeta_afd, afeta_aej, ativo) "
            "VALUES (:id, :tenant_id, :codigo, :nome, :categoria, FALSE, TRUE, "
            "        FALSE, TRUE, TRUE)"
        ),
        {
            "id": tipo_id,
            "tenant_id": contexto.tenant_id,
            "codigo": f"TT-{uuid.uuid4().hex[:8]}",
            "nome": f"Tipo de teste ({categoria})",
            "categoria": categoria,
        },
    )
    return tipo_id


async def semear_tratamento_inclusao(
    sessao: AsyncSession,
    contexto: ContextoF12,
    *,
    data_referencia: dt.date,
    datahora_proposta: dt.datetime,
    sentido: str,
    motivo: str = "Inclusao manual de teste",
) -> UUID:
    """Tratamento `categoria='inclusao_marcacao'`, `status='aprovado'` --
    `INSERT` direto (esta fase só LÊ `tratamentos`, nunca escreve via
    `criar_tratamento`/`decidirTratamento` de F4; a fixture de teste precisa
    de uma linha já aprovada, sem exercitar o fluxo de workflow completo de
    F4/F10, que não é o foco desta fase)."""
    tipo_id = await semear_tipo_tratamento(sessao, contexto, categoria="inclusao_marcacao")
    tratamento_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO tratamentos "
            "(id, tenant_id, colaborador_id, vinculo_id, tipo_tratamento_id, data_referencia, "
            " datahora_proposta, sentido, motivo, origem, status, aprovado_em) "
            "VALUES (:id, :tenant_id, :colaborador_id, :vinculo_id, :tipo_tratamento_id, "
            "        :data_referencia, :datahora_proposta, :sentido, :motivo, 'gestor', "
            "        'aprovado', now())"
        ),
        {
            "id": tratamento_id,
            "tenant_id": contexto.tenant_id,
            "colaborador_id": contexto.colaborador_id,
            "vinculo_id": contexto.vinculo_id,
            "tipo_tratamento_id": tipo_id,
            "data_referencia": data_referencia,
            "datahora_proposta": datahora_proposta,
            "sentido": sentido,
            "motivo": motivo,
        },
    )
    return tratamento_id


async def semear_tratamento_desconsideracao(
    sessao: AsyncSession,
    contexto: ContextoF12,
    *,
    data_referencia: dt.date,
    marcacao_id: UUID,
    marcacao_datahora: dt.datetime,
    motivo: str = "Marcacao duplicada, desconsiderada no teste",
) -> UUID:
    """Tratamento `categoria='desconsideracao_marcacao'`, `status='aprovado'`
    -- `INSERT` direto, mesmo motivo de `semear_tratamento_inclusao`."""
    tipo_id = await semear_tipo_tratamento(sessao, contexto, categoria="desconsideracao_marcacao")
    tratamento_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO tratamentos "
            "(id, tenant_id, colaborador_id, vinculo_id, tipo_tratamento_id, data_referencia, "
            " marcacao_id, marcacao_datahora, motivo, origem, status, aprovado_em) "
            "VALUES (:id, :tenant_id, :colaborador_id, :vinculo_id, :tipo_tratamento_id, "
            "        :data_referencia, :marcacao_id, :marcacao_datahora, :motivo, 'gestor', "
            "        'aprovado', now())"
        ),
        {
            "id": tratamento_id,
            "tenant_id": contexto.tenant_id,
            "colaborador_id": contexto.colaborador_id,
            "vinculo_id": contexto.vinculo_id,
            "tipo_tratamento_id": tipo_id,
            "data_referencia": data_referencia,
            "marcacao_id": marcacao_id,
            "marcacao_datahora": marcacao_datahora,
            "motivo": motivo,
        },
    )
    return tratamento_id
