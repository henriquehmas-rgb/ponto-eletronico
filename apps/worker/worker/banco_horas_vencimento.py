"""Suporte de banco e de evento para `verificar_banco_horas_vencendo`
(`worker/scheduler.py`, T7 do PCF da F4, agente A2).

Modulo NOVO, dedicado, para manter o diff de `worker/scheduler.py` restrito
ao corpo da funcao que e minha (a tabela de ownership da F4 so me da
`verificar_banco_horas_vencendo` e o corpo dela, a entrada em
`montar_cron()` ja existe da Fase 0 e nao muda -- mesma razao que
`worker/terminais_saude.py` documenta para `verificar_terminal_offline`,
F6).

Enumeracao cross-tenant via SECURITY DEFINER (RFC-013, decidida)
------------------------------------------------------------------

`verificar_banco_horas_vencendo` roda **antes** de saber qual tenant
verificar: e um cron global, nao uma tarefa enfileirada por requisicao. A
role de aplicacao (`ponto_app`) nao tem `BYPASSRLS` (ADR-001) e toda tabela
de dominio esta sob `FORCE ROW LEVEL SECURITY` -- sem `app.tenant_id`,
`SELECT * FROM bh_contas` devolveria zero linhas, sempre.

RFC-013 decidiu (opcao b, mesmo padrao ja aprovado para
`fn_terminais_para_verificacao_saude`) a funcao
`fn_bh_contas_para_verificacao_vencimento()` (`packages/contracts/
schema.sql`, secao 10, `SECURITY DEFINER`): ela roda com os privilegios de
quem a definiu, entao enumera contas `aberta` de TODOS os tenants numa
unica chamada pela role comum `ponto_app`, sem `app.tenant_id` publicado e
sem segunda credencial de banco. Depois de enumerar, toda leitura de
`bh_politicas` (dias de pre-aviso, acao de vencimento) e toda escrita
(`ocorrencias`) abrem `SET LOCAL app.tenant_id` na MESMA engine, linha a
linha, assim que o `tenant_id` de cada conta ja e conhecido -- nenhuma
segunda credencial de banco e necessaria (RFC-013, decisao do
orquestrador).

Disparo idempotente por construcao
-----------------------------------

Como o cron roda uma vez por dia e a antecedencia e uma data exata
(`periodo_fim - N dias == hoje`), o disparo NAO precisa de marca de "ja
avisado" persistida (diferente de `terminal.offline`, que e uma transicao
de estado): o mesmo par (conta, antecedencia) so bate a condicao de
igualdade em UM dia do calendario. Rodar a rotina duas vezes no mesmo dia
(reexecucao manual, por exemplo) publicaria o aviso duas vezes -- risco
aceito, documentado, igual ao de qualquer cron `max_tries=1` sem
deduplicacao externa.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from worker.config import Configuracao
from worker.log import obter_logger

logger = obter_logger("banco_horas_vencimento")

NOME_BANCO_HORAS_VENCENDO = "banco_horas.vencendo"
VERSAO_BANCO_HORAS_VENCENDO = 1

#: Barramento interno do processo, mesmo padrao de
#: `app.apuracao.banco_horas.eventos`/`worker/terminais_saude.py` -- so
#: para prova por teste ate a F13 substituir por fila de verdade.
BARRAMENTO_INTERNO: list[dict[str, Any]] = []

_engine: AsyncEngine | None = None
_loop: asyncio.AbstractEventLoop | None = None


def limpar_barramento() -> None:
    """Uso exclusivo de teste, entre casos."""
    BARRAMENTO_INTERNO.clear()


def _loop_mudou(loop_guardado: asyncio.AbstractEventLoop | None) -> bool:
    """Mesmo problema (e mesma solucao) de `apps/api/app/db/sessao.py` e de
    `worker/terminais_saude.py`: engine assincrona presa ao event loop em
    que nasceu."""
    if loop_guardado is None:
        return False
    try:
        return asyncio.get_running_loop() is not loop_guardado
    except RuntimeError:
        return False


def _obter_engine(config: Configuracao) -> AsyncEngine:
    global _engine, _loop
    if _engine is not None and _loop_mudou(_loop):
        _engine = None
        _loop = None
    if _engine is None:
        _engine = create_async_engine(config.database_url, pool_pre_ping=True, pool_size=5)
        try:
            _loop = asyncio.get_running_loop()
        except RuntimeError:
            _loop = None
    return _engine


async def reiniciar_engines_para_teste() -> None:
    """Uso exclusivo de teste: descarta a engine entre casos/loops."""
    global _engine, _loop
    if _engine is not None and not _loop_mudou(_loop):
        await _engine.dispose()
    _engine = None
    _loop = None


@dataclass(frozen=True, slots=True)
class ContaAberta:
    """Recorte de `bh_contas` que a rotina de vencimento precisa, de TODOS
    os tenants (por isso vem de
    `fn_bh_contas_para_verificacao_vencimento()`, SECURITY DEFINER --
    RFC-013)."""

    id: UUID
    tenant_id: UUID
    vinculo_id: UUID
    colaborador_id: UUID
    codigo: str
    periodo_fim: dt.date
    saldo_atual_minutos: int
    bh_politica_id: UUID


async def listar_contas_abertas_cross_tenant(config: Configuracao) -> list[ContaAberta]:
    """Enumera contas `aberta` de TODOS os tenants via
    `fn_bh_contas_para_verificacao_vencimento()` (RFC-013): a propria role
    comum `ponto_app`, sem `app.tenant_id` publicado -- a funcao roda com
    os privilegios de quem a definiu, nao os da conexao chamadora."""
    engine = _obter_engine(config)
    async with engine.connect() as conexao:
        resultado = await conexao.execute(
            text("SELECT * FROM fn_bh_contas_para_verificacao_vencimento()")
        )
        linhas = resultado.all()
    return [
        ContaAberta(
            id=linha.id,
            tenant_id=linha.tenant_id,
            vinculo_id=linha.vinculo_id,
            colaborador_id=linha.colaborador_id,
            codigo=linha.codigo,
            periodo_fim=linha.periodo_fim,
            saldo_atual_minutos=linha.saldo_atual_minutos,
            bh_politica_id=linha.bh_politica_id,
        )
        for linha in linhas
    ]


@dataclass(frozen=True, slots=True)
class PoliticaVencimento:
    """Recorte de `bh_politicas` (ja sob `app.tenant_id` publicado) que a
    rotina precisa para decidir se e quando avisar."""

    dias_pre_aviso: list[int]
    acao_vencimento: str


async def obter_politica_vencimento(
    config: Configuracao, tenant_id: UUID, bh_politica_id: UUID
) -> PoliticaVencimento | None:
    """Le `dias_pre_aviso`/`acao_vencimento` da politica da conta, com
    `app.tenant_id` publicado (`SET LOCAL`, escopo da transacao aberta por
    `engine.begin()`) -- leitura comum sob RLS, nenhum privilegio
    especial."""
    engine = _obter_engine(config)
    async with engine.begin() as conexao:
        await conexao.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant_id)}
        )
        linha = (
            await conexao.execute(
                text("SELECT dias_pre_aviso, acao_vencimento FROM bh_politicas WHERE id = :id"),
                {"id": str(bh_politica_id)},
            )
        ).first()
    if linha is None:
        return None
    return PoliticaVencimento(
        dias_pre_aviso=list(linha.dias_pre_aviso), acao_vencimento=linha.acao_vencimento
    )


def dias_ate_o_vencimento(periodo_fim: dt.date, hoje: dt.date) -> int:
    """Antecedencia em dias entre `hoje` e `periodo_fim`. Negativo quando o
    periodo ja venceu."""
    return (periodo_fim - hoje).days


async def abrir_ocorrencia_banco_vencendo(
    config: Configuracao,
    *,
    tenant_id: UUID,
    colaborador_id: UUID,
    vinculo_id: UUID,
    data: dt.date,
    descricao: str,
    detalhes: dict[str, Any],
) -> None:
    """Grava `ocorrencias.codigo='banco_vencendo'` -- "banco_teto/
    banco_vencendo nascem nesta fase (A2)" (PCF, secao 2). So a linha da
    tabela; `ocorrencia.aberta` (events.yaml) e publicado por
    `app.apuracao.dominio` (A1) durante `apurar_dia`, unico produtor deste
    evento nesta fase -- este modulo nao republica."""
    engine = _obter_engine(config)
    async with engine.begin() as conexao:
        await conexao.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant_id)}
        )
        insercao = text(
            "INSERT INTO ocorrencias "
            "(tenant_id, colaborador_id, vinculo_id, data, codigo, severidade, "
            " descricao, detalhes) "
            "VALUES (:tenant_id, :colaborador_id, :vinculo_id, :data, 'banco_vencendo', "
            "        'atencao', :descricao, :detalhes)"
        ).bindparams(bindparam("detalhes", type_=JSONB))
        await conexao.execute(
            insercao,
            {
                "tenant_id": str(tenant_id),
                "colaborador_id": str(colaborador_id),
                "vinculo_id": str(vinculo_id),
                "data": data,
                "descricao": descricao,
                "detalhes": json.dumps(detalhes),
            },
        )


#: `bh_politicas.acao_vencimento` e `snake_case`; `events.yaml` declara o
#: payload `acaoVencimento` em `camelCase` para `quitar_folha` (os demais
#: valores sao identicos nos dois lados) -- mesmo mapa de
#: `app.apuracao.banco_horas.eventos`.
_CAMEL_ACAO_VENCIMENTO: dict[str, str] = {"quitar_folha": "quitarFolha"}


def publicar_banco_horas_vencendo(
    *,
    tenant_id: UUID,
    conta_id: UUID,
    colaborador_id: UUID,
    vinculo_id: UUID,
    conta_codigo: str,
    minutos_a_vencer: int,
    saldo_atual_minutos: int,
    vence_em: dt.date,
    dias_restantes: int,
    acao_vencimento: str,
) -> dict[str, Any]:
    """Publica `banco_horas.vencendo` (`events.yaml`, origem `scheduler`)
    com os `required` preenchidos: contaId, colaboradorId, vinculoId,
    minutosAVencer, venceEm, diasRestantes."""
    agora = dt.datetime.now(tz=dt.UTC)
    dados: dict[str, Any] = {
        "contaId": str(conta_id),
        "colaboradorId": str(colaborador_id),
        "vinculoId": str(vinculo_id),
        "contaCodigo": conta_codigo,
        "minutosAVencer": minutos_a_vencer,
        "saldoAtualMinutos": saldo_atual_minutos,
        "venceEm": vence_em.isoformat(),
        "diasRestantes": dias_restantes,
        "acaoVencimento": _CAMEL_ACAO_VENCIMENTO.get(acao_vencimento, acao_vencimento),
    }
    envelope = {
        "id": str(uuid4()),
        "tipo": NOME_BANCO_HORAS_VENCENDO,
        "versao": VERSAO_BANCO_HORAS_VENCENDO,
        "ocorridoEm": agora.isoformat(),
        "publicadoEm": agora.isoformat(),
        "tenantId": str(tenant_id),
        "dados": dados,
    }
    BARRAMENTO_INTERNO.append(envelope)
    logger.info(
        "evento de dominio publicado",
        extra={"tipo": envelope["tipo"], "id": envelope["id"], "tenantId": envelope["tenantId"]},
    )
    # F13/A3, T11 -- aditivo (nome/comportamento do que ja existia acima
    # inalterados). `publicar_banco_horas_vencendo` nao tem escrita propria
    # associada (e uma notificacao derivada de LEITURA de `bh_contas`, nunca
    # desfeita por rollback) -- nao ha "commit" para esperar aqui, ao
    # contrario de `terminal.offline`. Ver `worker.despacho_webhooks`.
    from worker.despacho_webhooks import publicar_fire_and_forget

    publicar_fire_and_forget(envelope)
    return envelope
