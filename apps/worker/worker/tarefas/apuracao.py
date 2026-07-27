"""Tarefas de apuracao de jornada. Implementacao na F4 (Calculo e Banco de Horas).

Sequencia canonica do dominio (ver PROJETO.md secao 4.4), que estas tarefas
executarao::

    marcacoes imutaveis
      -> regras da jornada do dia
      -> tratamentos aplicaveis (ajuste aprovado, abono, afastamento)
      -> apuracao do dia
      -> lancamentos de banco de horas
      -> fechamento

Duas invariantes que a F4 tera de honrar e que ja moldam a assinatura daqui:

* **Determinismo.** Recalcular duas vezes o mesmo periodo produz exatamente o
  mesmo resultado. Por isso a tarefa recebe a data, e nao "hoje".
* **Marcacao nunca e tocada.** A apuracao le marcacao e escreve apuracao;
  correcao vive na camada de tratamento.

**Ordem das duas funcoes abaixo (reparo do agente A1).** `recalcular_periodo`
vem ANTES de `apurar_dia` no arquivo de proposito, nao por acaso: as duas
fazem o MESMO import tardio de `app.db.sessao` (`aplicar_tenant`/
`fabrica_de_sessoes`, ver achado de arquitetura no docstring de
`recalcular_periodo`), e o mypy deste projeto (`warn_unused_ignores`, parte
de `strict = true`) so emite `import-not-found` na PRIMEIRA ocorrencia
textual de um modulo nao encontrado por arquivo -- a segunda ocorrencia do
MESMO modulo nao gera erro novo, e um `# type: ignore` ali sobraria como
"unused-ignore" (confirmado empiricamente ao rodar `mypy` com e sem cada
ignore). Por isso so a ocorrencia de `app.db.sessao` em `recalcular_periodo`
(a primeira do arquivo) carrega o `# type: ignore[import-not-found]`; a de
`apurar_dia` (a segunda) nao precisa dele. Nenhuma linha do CORPO de
`recalcular_periodo` foi tocada por este reparo -- so a posicao das duas
funcoes no arquivo.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import Vinculo

from worker.log import obter_logger

logger = obter_logger("tarefas.apuracao")


async def recalcular_periodo(
    ctx: dict[str, Any],
    *,
    tenant_id: str,
    vinculo_id: str | None = None,
    inicio: dt.date | str,
    fim: dt.date | str,
    motivo: str = "regra alterada",
) -> dict[str, Any]:
    """Reprocessa um intervalo afetado por mudanca retroativa (T10, F4/A3).

    Dispara quando entra atestado retroativo, quando uma regra muda ou quando um
    tratamento e aprovado. A F4 registra o *diff* na auditoria e recusa
    reprocessar periodo fechado sem reabertura autorizada (contado, nunca
    aborta o restante do intervalo).

    Args:
        ctx: contexto do ARQ (`redis`, `job_id`, `job_try`).
        tenant_id: tenant dono do dado. Alimenta o RLS.
        vinculo_id: vinculo alvo, ou `None` para todos os vinculos do tenant
            sujeitos a apuracao (`apura_ponto = true`) -- ver nota abaixo.
        inicio: primeiro dia do intervalo, inclusive.
        fim: ultimo dia do intervalo, inclusive.
        motivo: causa do recalculo, obrigatoria na trilha de auditoria.

    **Achado de arquitetura RESOLVIDO (historico, ver ADR-009).** A logica de
    negocio real vive em `app.apuracao.tratamento.recalculo.recalcular_periodo`
    (`apps/api`), e o PCF desta fase (F04, secao 4) fixa exatamente esta
    chamada. Isto colidia, a principio, com o padrao estabelecido pela F2
    (`worker/tarefas/importacoes.py`, topo do arquivo: "o worker nao pode
    importar codigo de apps/api -- sao imagens Docker separadas"), porque
    `apps/worker/Dockerfile` (alvo `runtime`) so instalava `apps/worker` +
    `packages/contracts`. O dono do produto decidiu (ver
    `docs/adr/ADR-009-worker-instala-apps-api-como-biblioteca.md`) instalar
    `apps/api` tambem como biblioteca na imagem do worker (nunca serve HTTP,
    so importa `app.core.*`/`app.jornada.*`/`app.apuracao.*`) -- o import
    abaixo funciona tanto em desenvolvimento/CI quanto na imagem `runtime` de
    producao. `apps/worker/pyproject.toml` continua sem declarar `apps/api`
    como dependencia formal (a instalacao acontece so no Dockerfile), por isso
    o `# type: ignore[import-not-found]` abaixo permanece: o `mypy` do worker,
    rodado isoladamente do venv de `apps/api`, nao resolve o modulo.
    """
    logger.info(
        "recalcular_periodo recebida",
        extra={
            "jobId": ctx.get("job_id"),
            "tenantId": tenant_id,
            "vinculoId": vinculo_id,
            "inicio": str(inicio),
            "fim": str(fim),
            "motivo": motivo,
        },
    )

    # Ver docstring acima ("ACHADO DE ARQUITETURA"): `apps/worker` nao
    # instala `apps/api` em producao, entao mypy (rodando no venv proprio
    # do worker, sem `apps/api` instalado) nunca encontra estes dois
    # modulos -- exatamente o sintoma do achado, suprimido aqui de forma
    # documentada em vez de escondido.
    from app.apuracao.tratamento.recalculo import (  # type: ignore[import-not-found]
        recalcular_periodo as _recalcular_periodo,
    )
    from app.db.sessao import aplicar_tenant, fabrica_de_sessoes  # type: ignore[import-not-found]

    tenant_uuid = UUID(tenant_id)
    data_inicio = inicio if isinstance(inicio, dt.date) else dt.date.fromisoformat(str(inicio))
    data_fim = fim if isinstance(fim, dt.date) else dt.date.fromisoformat(str(fim))

    fabrica = fabrica_de_sessoes()
    async with fabrica() as sessao:
        await aplicar_tenant(sessao, tenant_id)

        if vinculo_id is not None:
            vinculos_alvo = [UUID(vinculo_id)]
        else:
            # Sem escopo adicional disponivel na assinatura fixada desta
            # tarefa (nao carrega empresaId/unidadeId/departamentoId): "None"
            # e' interpretado como todos os vinculos do tenant sujeitos a
            # apuracao.
            linhas = await sessao.execute(
                sa.select(Vinculo.id).where(
                    Vinculo.tenant_id == tenant_uuid,
                    Vinculo.excluido_em.is_(None),
                    Vinculo.apura_ponto.is_(True),
                )
            )
            vinculos_alvo = [row[0] for row in linhas.all()]

        dias_processados = 0
        dias_alterados = 0
        dias_ignorados_fechados = 0
        vinculos_processados = 0
        for vid in vinculos_alvo:
            parcial = await _recalcular_periodo(
                sessao,
                tenant_uuid,
                vinculo_id=vid,
                inicio=data_inicio,
                fim=data_fim,
                motivo=motivo,
            )
            dias_processados += parcial.dias_processados
            dias_alterados += parcial.dias_alterados
            dias_ignorados_fechados += parcial.dias_ignorados_fechados
            vinculos_processados += parcial.vinculos_processados
        await sessao.commit()

    resultado = {
        "implementado": True,
        "tenantId": tenant_id,
        "vinculoId": vinculo_id,
        "inicio": str(inicio),
        "fim": str(fim),
        "motivo": motivo,
        "diasProcessados": dias_processados,
        "diasAlterados": dias_alterados,
        "diasIgnoradosFechados": dias_ignorados_fechados,
        "vinculosProcessados": vinculos_processados,
    }
    logger.info("recalcular_periodo concluida", extra={"jobId": ctx.get("job_id"), **resultado})
    return resultado


async def apurar_dia(
    ctx: dict[str, Any],
    *,
    tenant_id: str,
    vinculo_id: str,
    data: dt.date | str,
    motivo: str = "agendado",
) -> dict[str, Any]:
    """Apura um dia de um vinculo: pareia marcacoes e calcula os componentes.

    Args:
        ctx: contexto do ARQ (`redis`, `job_id`, `job_try`).
        tenant_id: tenant dono do dado. Alimenta o RLS na F4.
        vinculo_id: vinculo (contrato) apurado.
        data: dia civil apurado, em `AAAA-MM-DD`.
        motivo: por que a apuracao foi disparada, para a trilha de auditoria.
    """
    logger.info(
        "apurar_dia recebida",
        extra={
            "jobId": ctx.get("job_id"),
            "tenantId": tenant_id,
            "vinculoId": vinculo_id,
            "data": str(data),
            "motivo": motivo,
        },
    )

    # Mesmo achado de arquitetura documentado em `recalcular_periodo` logo
    # acima (import tardio): a assinatura fixada pelo PCF desta fase (secao
    # 4) manda este worker chamar `app.apuracao.dominio.servico.apurar_dia`
    # diretamente, e `apps/api` so entra na imagem `runtime` do worker apos
    # o Fix-Docker-ADR (decisao do dono do produto, ver relatorio da fase).
    # `app.db.sessao` (a segunda linha abaixo) NAO carrega `# type: ignore`:
    # e a MESMA importacao que `recalcular_periodo` ja faz acima (primeira
    # ocorrencia do modulo no arquivo) -- ver nota no docstring do modulo.
    from app.apuracao.dominio.servico import (  # type: ignore[import-not-found]
        apurar_dia as _apurar_dia,
    )
    from app.db.sessao import aplicar_tenant, fabrica_de_sessoes

    tenant_uuid = UUID(tenant_id)
    vinculo_uuid = UUID(vinculo_id)
    data_apurada = data if isinstance(data, dt.date) else dt.date.fromisoformat(str(data))

    fabrica = fabrica_de_sessoes()
    async with fabrica() as sessao:
        await aplicar_tenant(sessao, tenant_id)
        apuracao = await _apurar_dia(sessao, tenant_uuid, vinculo_uuid, data_apurada)
        await sessao.commit()

    resultado = {
        "implementado": True,
        "tenantId": tenant_id,
        "vinculoId": vinculo_id,
        "data": str(data_apurada),
        "motivo": motivo,
        "apuracaoId": str(apuracao.id) if apuracao.id is not None else None,
        "tipoDia": apuracao.tipo_dia,
        "status": apuracao.status,
    }
    logger.info("apurar_dia concluida", extra={"jobId": ctx.get("job_id"), **resultado})
    return resultado
