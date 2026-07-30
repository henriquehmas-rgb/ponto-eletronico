"""Suporte de banco e de varredura para `verificar_notificacoes_pendentes`
(`worker/scheduler.py`, T11 do PCF da F10, agente A3).

Módulo NOVO, dedicado -- mesma razão que `worker/terminais_saude.py` (F6) e
`worker/banco_horas_vencimento.py` (F4) já documentam para manter o diff de
`worker/scheduler.py` restrito ao corpo da função que é minha.

Por que este módulo IMPORTA `app.*` (diferente das duas irmãs acima)
------------------------------------------------------------------------
`verificar_terminal_offline`/`verificar_banco_horas_vencendo` publicam um
evento com uma função PRÓPRIA, de poucas linhas, dentro do próprio módulo de
suporte -- não há lógica de negócio para reaproveitar de `apps/api`. Esta
rotina é diferente: para cada achado, ela precisa do MOTOR de notificação
inteiro (`app.notificacao.motor.processar_evento` -- resolução de
destinatário via `usuarios`/`aprovacoes`, preferência por usuário, janela de
silêncio, template de mensagem). Reimplementar tudo isso em SQL cru dentro
do scheduler duplicaria uma lógica que já existe e já é testada em
`app.notificacao.motor` -- MESMA fase, MESMO agente (A3), nunca lógica de
outra fase (o que continua proibido). `apps/worker/Dockerfile` já instala
`apps/api` como biblioteca na MESMA imagem que o `scheduler` usa (ADR-009:
"os serviços worker e scheduler do compose apontam para este mesmo
Dockerfile e para a mesma imagem"), então o import é válido tanto em
produção quanto em teste (que roda a partir do venv de `apps/api`, que
instala `ponto-worker` em modo editável -- mesmo padrão de
`apps/api/tests/f4/banco_horas/test_vencimento.py`). A direção continua a
mesma do resto do sistema: só o worker/scheduler importa `app.*`; `apps/api`
nunca importa `worker.*` (`app/core/filas.py`).

Enumeração cross-tenant via SECURITY DEFINER (RFC-013/RFC-014, decidida)
--------------------------------------------------------------------------
Mesmo problema estrutural que as duas rotinas irmãs: `verificar_
notificacoes_pendentes` roda ANTES de saber qual tenant verificar (cron
global). `fn_tenants_ativos()` (RFC-014, `packages/contracts/schema.sql`,
`SECURITY DEFINER`) enumera `(id, slug)` de todo tenant `status='ativo'`
numa única chamada pela role comum `ponto_app`, sem `app.tenant_id`
publicado e sem segunda credencial de banco -- usa a MESMA fábrica de
sessões de `app.db.sessao` que o restante deste módulo usa para o trabalho
por tenant.

Idempotência
------------
Nunca por marca de estado numa tabela nova: usa a coluna `notificacoes.
entidade`/`entidade_id` já existente no schema (PCF §2.10). Um achado
(ocorrência ou pendência) só vira notificação NOVA quando não existe ainda
uma linha de `notificacoes` com o mesmo par entidade+entidade_id E o mesmo
`evento` -- o filtro por `evento` (não só por entidade+id) evita que a
notificação `ajuste.solicitado` (que também usa `entidade='solicitacoes'`)
suprima para sempre o lembrete `solicitacao.pendente_prazo` sobre a MESMA
solicitação, e vice-versa.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from ponto_contracts import Aprovacao, Notificacao, Ocorrencia, Solicitacao
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from worker.log import obter_logger

logger = obter_logger("notificacoes_verificacao")

#: Códigos de `ocorrencias.codigo` que esta rotina cobre -- os três citados
#: pelo PCF §2.10 (jornada_excedida, sem_marcacao, banco_vencendo). Os
#: demais códigos do CHECK (marcacao_impar, falta, atraso, ...) ficam de
#: fora desta rotina de propósito: não foram listados pelo PCF, e ampliar a
#: lista "porque faria sentido" seria decisão de escopo que não é minha.
CODIGOS_OCORRENCIA_COBERTOS: tuple[str, ...] = (
    "jornada_excedida",
    "sem_marcacao",
    "banco_vencendo",
)

#: Janela de recência da varredura de ocorrências -- sem isto, a cada
#: execução a rotina reconsideraria TODA a história de `ocorrencias` da
#: tabela. 7 dias cobre folgadamente o intervalo de 10 em 10 minutos entre
#: execuções (PCF §2.10) mesmo com o scheduler fora do ar por um fim de
#: semana inteiro.
JANELA_OCORRENCIAS_DIAS = 7

#: Import tardio de `app.*` (ADR-009, ver docstring do módulo). Primeira
#: ocorrência textual do módulo no arquivo carrega o `# type: ignore` (mesmo
#: motivo documentado em `worker/tarefas/apuracao.py`: mypy só avisa uma vez
#: por módulo não encontrado, e um segundo ignore sobraria como
#: "unused-ignore" sob `warn_unused_ignores`).


@dataclass(frozen=True, slots=True)
class TenantAtivo:
    """Recorte de `tenants` que esta rotina precisa, de TODOS os tenants
    (por isso vem de `fn_tenants_ativos()`, SECURITY DEFINER -- RFC-014)."""

    id: UUID
    slug: str


@dataclass(frozen=True, slots=True)
class ResultadoVarredura:
    """Totais de uma execução completa da varredura cross-tenant."""

    tenants_verificados: int
    ocorrencias_notificadas: int
    pendencias_notificadas: int
    tenant_ids: tuple[UUID, ...]


async def listar_tenants_ativos_cross_tenant() -> list[TenantAtivo]:
    """Enumera tenants `status='ativo'` via `fn_tenants_ativos()`
    (RFC-014): a própria role comum `ponto_app`, sem `app.tenant_id`
    publicado -- a função roda com os privilégios de quem a definiu, não os
    da conexão chamadora."""
    from app.db.sessao import fabrica_de_sessoes  # type: ignore[import-not-found]

    fabrica = fabrica_de_sessoes()
    async with fabrica() as sessao:
        resultado = await sessao.execute(text("SELECT id, slug FROM fn_tenants_ativos()"))
        linhas = resultado.all()
    return [TenantAtivo(id=linha.id, slug=linha.slug) for linha in linhas]


async def _ocorrencias_sem_notificacao(
    sessao: AsyncSession, tenant_id: UUID, agora: dt.datetime
) -> list[Ocorrencia]:
    """Ocorrências recentes, de código coberto, sem uma `Notificacao`
    (`entidade='ocorrencias'`, mesmo `evento`) já registrada para elas."""
    from app.notificacao import mensagens  # type: ignore[import-not-found]

    desde = agora - dt.timedelta(days=JANELA_OCORRENCIAS_DIAS)
    ja_notificada = (
        sa.select(sa.literal(1))
        .select_from(Notificacao)
        .where(
            Notificacao.tenant_id == Ocorrencia.tenant_id,
            Notificacao.entidade == "ocorrencias",
            Notificacao.entidade_id == Ocorrencia.id,
            Notificacao.evento == mensagens.NOME_OCORRENCIA_ABERTA,
        )
        .correlate(Ocorrencia)
        .exists()
    )
    linhas = await sessao.execute(
        sa.select(Ocorrencia)
        .where(
            Ocorrencia.tenant_id == tenant_id,
            Ocorrencia.codigo.in_(CODIGOS_OCORRENCIA_COBERTOS),
            Ocorrencia.criado_em >= desde,
            ~ja_notificada,
        )
        .order_by(Ocorrencia.criado_em)
    )
    return list(linhas.scalars().all())


async def _solicitacoes_pendentes_vencidas(
    sessao: AsyncSession, tenant_id: UUID, agora: dt.datetime
) -> list[tuple[Solicitacao, Aprovacao]]:
    """Solicitações cuja etapa CORRENTE está `pendente` com `prazo_em`
    vencido, sem uma `Notificacao` (`entidade='solicitacoes'`,
    `evento='solicitacao.pendente_prazo'`) já registrada para elas."""
    from app.notificacao import mensagens

    ja_notificada = (
        sa.select(sa.literal(1))
        .select_from(Notificacao)
        .where(
            Notificacao.tenant_id == Solicitacao.tenant_id,
            Notificacao.entidade == "solicitacoes",
            Notificacao.entidade_id == Solicitacao.id,
            Notificacao.evento == mensagens.NOME_SOLICITACAO_PENDENTE,
        )
        .correlate(Solicitacao)
        .exists()
    )
    linhas = await sessao.execute(
        sa.select(Solicitacao, Aprovacao)
        .join(
            Aprovacao,
            sa.and_(
                Aprovacao.solicitacao_id == Solicitacao.id,
                Aprovacao.etapa == Solicitacao.etapa_atual,
            ),
        )
        .where(
            Solicitacao.tenant_id == tenant_id,
            Solicitacao.status.in_(("pendente", "em_aprovacao")),
            Aprovacao.decisao == "pendente",
            Aprovacao.prazo_em.is_not(None),
            Aprovacao.prazo_em < agora,
            ~ja_notificada,
        )
        .order_by(Aprovacao.prazo_em)
    )
    return list(linhas.tuples())


def _envelope_ocorrencia_aberta(tenant_id: UUID, ocorrencia: Ocorrencia) -> dict[str, Any]:
    """Reconstrói o envelope `ocorrencia.aberta` (`events.yaml`) a partir da
    linha já gravada -- o evento original, publicado em processo por F4 no
    momento da apuração, não está mais em memória quando este cron roda
    (PCF §2.7)."""
    from app.notificacao import mensagens

    dados: dict[str, Any] = {
        "ocorrenciaId": str(ocorrencia.id),
        "colaboradorId": str(ocorrencia.colaborador_id),
        "data": ocorrencia.data.isoformat(),
        "codigo": ocorrencia.codigo,
        "severidade": ocorrencia.severidade,
    }
    if ocorrencia.vinculo_id is not None:
        dados["vinculoId"] = str(ocorrencia.vinculo_id)
    if ocorrencia.apuracao_dia_id is not None:
        dados["apuracaoDiaId"] = str(ocorrencia.apuracao_dia_id)
    if ocorrencia.descricao:
        dados["descricao"] = ocorrencia.descricao
    agora = dt.datetime.now(tz=dt.UTC)
    return {
        "id": str(uuid4()),
        "tipo": mensagens.NOME_OCORRENCIA_ABERTA,
        "versao": 1,
        "ocorridoEm": (ocorrencia.criado_em or agora).isoformat(),
        "publicadoEm": agora.isoformat(),
        "tenantId": str(tenant_id),
        "dados": dados,
    }


def _envelope_solicitacao_pendente(
    tenant_id: UUID, solicitacao: Solicitacao, aprovacao: Aprovacao
) -> dict[str, Any]:
    """Envelope SINTÉTICO -- `solicitacao.pendente_prazo` não existe em
    `events.yaml` (nenhum evento do catálogo corresponde 1:1 a esta rotina,
    PCF §2.10); o formato de `dados` é o que `app.notificacao.mensagens.
    _solicitacao_pendente`/`motor._resolver_destinatarios` esperam."""
    from app.notificacao import mensagens

    dados: dict[str, Any] = {
        "solicitacaoId": str(solicitacao.id),
        "protocolo": solicitacao.protocolo,
        "colaboradorId": str(solicitacao.colaborador_id),
        "etapa": aprovacao.etapa,
    }
    if aprovacao.prazo_em is not None:
        dados["prazoEm"] = aprovacao.prazo_em.isoformat()
    agora = dt.datetime.now(tz=dt.UTC)
    return {
        "id": str(uuid4()),
        "tipo": mensagens.NOME_SOLICITACAO_PENDENTE,
        "versao": 1,
        "ocorridoEm": agora.isoformat(),
        "publicadoEm": agora.isoformat(),
        "tenantId": str(tenant_id),
        "dados": dados,
    }


async def verificar_notificacoes_pendentes_cross_tenant() -> ResultadoVarredura:
    """Varre todo tenant ativo em busca de ocorrências e pendências ainda
    não notificadas, cria as linhas de `Notificacao` correspondentes (via
    `app.notificacao.motor.processar_evento`, reaproveitado -- nunca
    duplicado) e devolve os totais para o log da rotina de cron.

    `tenant_ids` no resultado é usado por `worker.scheduler.
    verificar_notificacoes_pendentes` para enfileirar `processar_fila_
    notificacoes` uma vez por tenant ATIVO (não só os que tiveram achado
    nesta execução): notificações nascidas em processo, pela chamada direta
    de A1/A2/A4 a `app.notificacao.motor.processar_evento`, também esperam
    por este envio periódico (ver docstring de
    `worker/tarefas/notificacoes.py`).
    """
    from app.db.sessao import aplicar_tenant, fabrica_de_sessoes
    from app.notificacao.motor import processar_evento  # type: ignore[import-not-found]

    tenants = await listar_tenants_ativos_cross_tenant()
    fabrica = fabrica_de_sessoes()
    agora = dt.datetime.now(tz=dt.UTC)

    ocorrencias_notificadas = 0
    pendencias_notificadas = 0

    for tenant in tenants:
        async with fabrica() as sessao:
            await aplicar_tenant(sessao, str(tenant.id))

            ocorrencias = await _ocorrencias_sem_notificacao(sessao, tenant.id, agora)
            for ocorrencia in ocorrencias:
                criadas = await processar_evento(
                    sessao, tenant.id, _envelope_ocorrencia_aberta(tenant.id, ocorrencia)
                )
                ocorrencias_notificadas += criadas

            pendentes = await _solicitacoes_pendentes_vencidas(sessao, tenant.id, agora)
            for solicitacao, aprovacao in pendentes:
                criadas = await processar_evento(
                    sessao,
                    tenant.id,
                    _envelope_solicitacao_pendente(tenant.id, solicitacao, aprovacao),
                )
                pendencias_notificadas += criadas

            await sessao.commit()

    logger.info(
        "varredura cross-tenant de notificacoes concluida",
        extra={
            "tenantsVerificados": len(tenants),
            "ocorrenciasNotificadas": ocorrencias_notificadas,
            "pendenciasNotificadas": pendencias_notificadas,
        },
    )
    return ResultadoVarredura(
        tenants_verificados=len(tenants),
        ocorrencias_notificadas=ocorrencias_notificadas,
        pendencias_notificadas=pendencias_notificadas,
        tenant_ids=tuple(tenant.id for tenant in tenants),
    )


__all__ = [
    "CODIGOS_OCORRENCIA_COBERTOS",
    "JANELA_OCORRENCIAS_DIAS",
    "ResultadoVarredura",
    "TenantAtivo",
    "listar_tenants_ativos_cross_tenant",
    "verificar_notificacoes_pendentes_cross_tenant",
]
