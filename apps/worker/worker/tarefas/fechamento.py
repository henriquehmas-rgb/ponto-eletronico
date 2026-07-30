"""Tarefas assíncronas de fechamento e espelho (T9, F10/A2).

`criarFechamento` já é `202`/`ProcessamentoAssincrono` no contrato: fechar
uma empresa inteira (centenas de vínculos × dias do período) não cabe no
tempo de uma requisição HTTP. `processar_fechamento` é quem de fato marca
`fechamentos.status='fechado'` (o gatilho real da trava -- ver
`app.apuracao.tratamento.fechamento.verificar_periodo_aberto`, F4) e, se
pedido, gera os espelhos oficiais chamando `gerar_espelho_do_vinculo`
**diretamente** (nunca via fila aninhada -- PCF §6, T9). **Não escreve em
`apuracoes_dia`** (proibição 5 do PCF): confirmado lendo
`verificar_periodo_aberto` por inteiro que a trava nunca consulta
`apuracoes_dia.fechamento_id`/`status`, só `Fechamento.status`; escrever
essas colunas seria cosmético, sem necessidade funcional -- achado
registrado em `docs/backlog.md`.

**Achado de arquitetura idêntico ao que F4 já documentou** em
`worker/tarefas/apuracao.py`: a lógica real vive em `apps/api`
(`app.workflow.fechamento.*`), e o worker a importa como biblioteca
(ADR-009, já decidido e implementado por F4 -- `apps/worker/Dockerfile`
instala `apps/api` na imagem `runtime`). Os imports de `app.*` abaixo
carregam um comentário supressor de tipo só na primeira ocorrência textual
de cada módulo por ARQUIVO, não por função (mesma nota de `mypy`/
`warn_unused_ignores` que `worker/tarefas/apuracao.py` já documenta).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import ApuracaoDia, Fechamento, Periodo

from worker.log import obter_logger

logger = obter_logger("tarefas.fechamento")


def _json_canonico_worker(valor: Any) -> str:
    """Mesma fórmula de `app.identidade.auditoria.hash_chain._json_canonico`
    (cópia local: este módulo não importa `app.identidade.*`, só
    `app.workflow.*`/`app.apuracao.*`, para não alargar a superfície de
    import da tarefa além do que ela precisa)."""
    return json.dumps(valor, sort_keys=True, separators=(",", ":"), default=str)


def _hash_conjunto_travado(linhas: list[dict[str, Any]]) -> str:
    """Hash do conjunto de apurações travadas (`fechamentos.hash_conteudo`):
    permite provar que nada mudou depois do fechamento. Mesma
    canonicalização de JSON usada em toda a base (`_json_canonico`); a
    ORDENAÇÃO das linhas (por `vinculoId`, depois `data`) já é feita por
    quem monta `linhas`, para o hash ser determinístico independente da
    ordem de retorno do banco."""
    return hashlib.sha256(_json_canonico_worker(linhas).encode("utf-8")).hexdigest()


async def processar_fechamento(
    ctx: dict[str, Any],
    *,
    tenant_id: str,
    fechamento_id: str,
    gerar_espelhos: bool = False,
    usuario_id: str | None = None,
) -> dict[str, Any]:
    """Trava a apuração do escopo do `Fechamento` e, se `gerar_espelhos`,
    gera os espelhos oficiais no mesmo processamento. Publica exatamente um
    `periodo.fechado` ao final (nunca um por vínculo)."""
    logger.info(
        "processar_fechamento recebida",
        extra={"jobId": ctx.get("job_id"), "tenantId": tenant_id, "fechamentoId": fechamento_id},
    )

    # Mesmo achado de arquitetura documentado em `worker/tarefas/apuracao.py`
    # (ADR-009): `apps/worker` não instala `apps/api` no venv de
    # desenvolvimento isolado, só na imagem `runtime` (Dockerfile). O
    # comentario supressor de tipo abaixo vai so na PRIMEIRA ocorrencia
    # textual de cada modulo neste arquivo -- mypy nao repete o erro para a
    # mesma importacao decorrente noutra funcao, e o supressor ali sobraria
    # como "unused-ignore" (confirmado empiricamente, mesma nota do modulo
    # irmao).
    from app.db.sessao import aplicar_tenant, fabrica_de_sessoes  # type: ignore[import-not-found]
    from app.identidade.auditoria.hash_chain import (  # type: ignore[import-not-found]
        gravar_auditoria,
    )
    from app.workflow.fechamento.escopo import (  # type: ignore[import-not-found]
        resolver_vinculos_do_escopo,
    )
    from app.workflow.fechamento.espelho import (  # type: ignore[import-not-found]
        gerar_espelho_do_vinculo,
    )
    from app.workflow.fechamento.eventos import (  # type: ignore[import-not-found]
        publicar_periodo_fechado,
    )

    tenant_uuid = UUID(tenant_id)
    fechamento_uuid = UUID(fechamento_id)
    usuario_uuid = UUID(usuario_id) if usuario_id else None

    fabrica = fabrica_de_sessoes()
    async with fabrica() as sessao:
        await aplicar_tenant(sessao, tenant_id)

        fechamento = await sessao.get(Fechamento, fechamento_uuid)
        if fechamento is None or fechamento.tenant_id != tenant_uuid:
            logger.error(
                "processar_fechamento: fechamento nao encontrado",
                extra={"jobId": ctx.get("job_id"), "fechamentoId": fechamento_id},
            )
            return {"implementado": True, "encontrado": False, "fechamentoId": fechamento_id}

        periodo = await sessao.get(Periodo, fechamento.periodo_id)
        if periodo is None:
            logger.error(
                "processar_fechamento: periodo nao encontrado",
                extra={"jobId": ctx.get("job_id"), "periodoId": str(fechamento.periodo_id)},
            )
            return {"implementado": True, "encontrado": False, "fechamentoId": fechamento_id}

        vinculos = await resolver_vinculos_do_escopo(
            sessao,
            tenant_uuid,
            escopo=fechamento.escopo,
            empresa_id=fechamento.empresa_id,
            unidade_id=fechamento.unidade_id,
            departamento_id=fechamento.departamento_id,
            periodo_inicio=periodo.data_inicio,
            periodo_fim=periodo.data_fim,
        )
        vinculo_ids = sorted(v.id for v in vinculos)

        # SOMENTE LEITURA em `apuracoes_dia` (proibição 5 do PCF: "Não
        # escreva em apuracoes_dia... a escrita acontece exclusivamente via
        # os módulos de F4"). A trava real (`verificar_periodo_aberto`, F4,
        # `app.apuracao.tratamento.fechamento`) só consulta
        # `Fechamento.status == 'fechado'` cobrindo data/escopo -- ela NUNCA
        # lê `apuracoes_dia.fechamento_id`/`status` (confirmado lendo o
        # módulo inteiro). Marcar essas duas colunas seria, portanto,
        # escrita fora do ownership desta fase para um efeito que já existe
        # sem ela: a linha de `Fechamento` abaixo é o suficiente e o único
        # gatilho real da trava. `hash_conteudo` é calculado só a partir da
        # LEITURA do conjunto de apurações no escopo.
        linhas_travadas: list[dict[str, Any]] = []
        if vinculo_ids:
            apuracoes = (
                (
                    await sessao.execute(
                        sa.select(ApuracaoDia).where(
                            ApuracaoDia.tenant_id == tenant_uuid,
                            ApuracaoDia.vinculo_id.in_(vinculo_ids),
                            ApuracaoDia.data >= periodo.data_inicio,
                            ApuracaoDia.data <= periodo.data_fim,
                        )
                    )
                )
                .scalars()
                .all()
            )
            for apuracao in apuracoes:
                linhas_travadas.append(
                    {
                        "vinculoId": str(apuracao.vinculo_id),
                        "data": apuracao.data.isoformat(),
                        "hashEntrada": apuracao.hash_entrada,
                        "versao": apuracao.versao,
                    }
                )

        linhas_travadas.sort(key=lambda linha: (linha["vinculoId"], linha["data"]))
        hash_conteudo = _hash_conjunto_travado(linhas_travadas)

        status_anterior = fechamento.status
        agora = dt.datetime.now(tz=dt.UTC)
        fechamento.status = "fechado"
        fechamento.fechado_em = agora
        fechamento.fechado_por = usuario_uuid
        fechamento.hash_conteudo = hash_conteudo
        fechamento.atualizado_por = usuario_uuid

        espelhos_gerados = 0
        if gerar_espelhos:
            for vinculo_id in vinculo_ids:
                await gerar_espelho_do_vinculo(
                    sessao,
                    tenant_uuid,
                    periodo,
                    vinculo_id,
                    tipo="oficial",
                    fechamento_id=fechamento.id,
                    gerar_pdf=True,
                    usuario_id=usuario_uuid,
                )
                espelhos_gerados += 1

        await gravar_auditoria(
            sessao,
            tenant_id=tenant_uuid,
            evento="periodo.fechado",
            entidade="fechamentos",
            acao="fechar",
            entidade_id=fechamento.id,
            usuario_id=usuario_uuid,
            valor_anterior={"status": status_anterior},
            valor_novo={"status": "fechado", "hashConteudo": hash_conteudo},
            metadados={
                "escopo": fechamento.escopo,
                "totalVinculos": len(vinculo_ids),
                "espelhosGerados": espelhos_gerados,
            },
        )

        envelope = publicar_periodo_fechado(
            tenant_id=tenant_uuid,
            fechamento_id=fechamento.id,
            periodo_id=periodo.id,
            empresa_id=fechamento.empresa_id,
            escopo=fechamento.escopo,
            data_inicio=periodo.data_inicio,
            data_fim=periodo.data_fim,
            fechado_em=agora,
            competencia_folha=periodo.competencia_folha,
            total_colaboradores=fechamento.total_colaboradores,
            total_pendencias=fechamento.total_pendencias,
            fechado_por=usuario_uuid,
            hash_conteudo=hash_conteudo,
        )
        # Achado de integracao consertado ao fechar a fase (T15/T16): nenhum
        # publicador de evento desta fase chamava
        # `app.notificacao.motor.processar_evento` (A3) -- ver nota igual em
        # `app/workflow/solicitacoes/servico.py::criar_solicitacao`. Aqui a
        # notificacao ainda entra na MESMA transacao/sessao do worker, antes
        # do commit (mesmo padrao que os outros pontos de chamada usam --
        # quem publica o evento tambem processa a notificacao, na mesma
        # unidade de trabalho).
        from app.notificacao.motor import processar_evento  # type: ignore[import-not-found]

        await processar_evento(sessao, tenant_uuid, envelope)

        await sessao.commit()

    resultado = {
        "implementado": True,
        "encontrado": True,
        "tenantId": tenant_id,
        "fechamentoId": fechamento_id,
        "totalVinculos": len(vinculo_ids),
        "totalApuracoesTravadas": len(linhas_travadas),
        "espelhosGerados": espelhos_gerados,
        "hashConteudo": hash_conteudo,
    }
    logger.info("processar_fechamento concluida", extra={"jobId": ctx.get("job_id"), **resultado})
    return resultado


async def gerar_espelhos(
    ctx: dict[str, Any],
    *,
    tenant_id: str,
    periodo_id: str,
    vinculo_ids: list[str],
    tipo: str = "previo",
    gerar_pdf: bool = False,
    fechamento_id: str | None = None,
    usuario_id: str | None = None,
) -> dict[str, Any]:
    """Gera o espelho de cada vínculo do escopo pedido (`gerarEspelhos`,
    T7/T9) -- um espelho por vínculo, todos no mesmo job (o fan-out por
    vínculo já aconteceu na resolução do escopo em `espelho.py::
    resolver_escopo_espelhos`, chamada pelo router antes de enfileirar)."""
    logger.info(
        "gerar_espelhos recebida",
        extra={
            "jobId": ctx.get("job_id"),
            "tenantId": tenant_id,
            "periodoId": periodo_id,
            "totalVinculos": len(vinculo_ids),
        },
    )

    # `app.db.sessao`/`app.workflow.fechamento.espelho` já carregaram o
    # comentario supressor de tipo na primeira ocorrencia do arquivo (dentro
    # de `processar_fechamento`, acima) -- repetir aqui viraria
    # "unused-ignore" (mesma nota da funcao anterior).
    from app.db.sessao import aplicar_tenant, fabrica_de_sessoes
    from app.workflow.fechamento.espelho import gerar_espelho_do_vinculo

    tenant_uuid = UUID(tenant_id)
    periodo_uuid = UUID(periodo_id)
    fechamento_uuid = UUID(fechamento_id) if fechamento_id else None
    usuario_uuid = UUID(usuario_id) if usuario_id else None

    fabrica = fabrica_de_sessoes()
    gerados = 0
    async with fabrica() as sessao:
        await aplicar_tenant(sessao, tenant_id)

        periodo = await sessao.get(Periodo, periodo_uuid)
        if periodo is None or periodo.tenant_id != tenant_uuid:
            logger.error(
                "gerar_espelhos: periodo nao encontrado",
                extra={"jobId": ctx.get("job_id"), "periodoId": periodo_id},
            )
            return {"implementado": True, "encontrado": False, "periodoId": periodo_id}

        for vinculo_id in vinculo_ids:
            await gerar_espelho_do_vinculo(
                sessao,
                tenant_uuid,
                periodo,
                UUID(vinculo_id),
                tipo=tipo,
                fechamento_id=fechamento_uuid,
                gerar_pdf=gerar_pdf,
                usuario_id=usuario_uuid,
            )
            gerados += 1

        await sessao.commit()

    resultado = {
        "implementado": True,
        "encontrado": True,
        "tenantId": tenant_id,
        "periodoId": periodo_id,
        "espelhosGerados": gerados,
    }
    logger.info("gerar_espelhos concluida", extra={"jobId": ctx.get("job_id"), **resultado})
    return resultado
