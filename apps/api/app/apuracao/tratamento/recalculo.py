"""Recálculo determinístico e idempotente da apuração, com diff auditado (T10).

`recalcular_periodo` é a implementação de ADR-004 (leia o ADR por inteiro
antes de mexer aqui): para cada `(vínculo, dia)` do escopo pedido, chama
`app.apuracao.dominio.servico.apurar_dia` (A1) -- nunca duplica a lógica de
pareamento/cálculo -- e decide, comparando `apuracoes_dia.hash_entrada`
*antes* e *depois* da chamada, se o dia mudou:

* **Sem mudança** (mesmo hash): *no-op* -- nenhuma linha nova em `auditoria`,
  nenhum evento publicado. É o que garante "recalcular duas vezes o mesmo
  período sem mudança de insumo produz exatamente o mesmo resultado"
  (critério de aceite 3 do PCF).
* **Com mudança**: grava o diff (`valor_anterior`/`valor_novo` dos
  componentes) via `app.identidade.auditoria.hash_chain.gravar_auditoria`
  (F1, reusada, nunca reimplementada) e acumula no total do vínculo para
  publicar **um único** `apuracao.recalculada` por vínculo ao final (o
  payload de `events.yaml` carrega `dataInicio`/`dataFim`/`diasAlterados`
  agregados do intervalo, não um evento por dia).

**Dia em período fechado é pulado e contado, nunca aborta o restante do
intervalo** (`verificar_periodo_aberto`, T9, levanta `PONTO-PER-001`; este
módulo captura e reclassifica como `PONTO-APUR-003` no resultado agregado --
ver PCF, T10, "pronto quando").

**Expansão de intervalo por dependência (ADR-004, ponto 5) é responsabilidade
de quem CHAMA esta função, não dela.** `recalcular_periodo` processa
exatamente `[inicio, fim]` por fidelidade ao escopo pedido -- é
`decidirTratamento` (T9, `decisao.py`) quem alarga a chamada para
`data_referencia - 1` .. `data_referencia + 1` ao agendar o recálculo de uma
aprovação, para honrar a dependência de interjornada (olha o dia anterior) e
de jornada que cruza a meia-noite (olha o dia seguinte). Documentado aqui
porque é uma decisão de design deste PCF sem teste dedicado que a torne
óbvia por si só.

**Limitação conhecida de `forcar`** (documentada no relatório da fase, não
resolvida silenciosamente): `RecalculoRequisicao.forcar` pede para "ignorar
o hash de entrada e reprocessar mesmo sem mudança de insumo". A assinatura
FIXADA de `apurar_dia` (`sessao, tenant_id, vinculo_id, data`) não recebe
nenhum parâmetro de bypass -- o próprio `apurar_dia` decide, internamente,
não reescrever quando o hash não muda (T4, A1). Este módulo não tem como
forçar `apurar_dia` a reescrever sem o parâmetro correspondente na função
que ele chama: `forcar` é aceito, propagado aos metadados de auditoria de
qualquer dia que MUDE por conta própria, mas não produz reescrita de um dia
cujo hash de insumos genuinamente não mudou. Ver relatório da fase para o
achado formal (candidato a RFC caso o diagnóstico com bypass seja
realmente necessário).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from arq import create_pool
from arq.connections import RedisSettings
from ponto_contracts import ApuracaoComponente, ApuracaoDia, Vinculo
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.tratamento import eventos
from app.apuracao.tratamento.fechamento import verificar_periodo_aberto
from app.core.erros import ErroDeAplicacao
from app.core.filas import FILA_PADRAO
from app.identidade.auditoria.hash_chain import CacheCadeiaAuditoria, gravar_auditoria

if TYPE_CHECKING:
    from app.schemas import contrato as esquemas

CODIGO_PERIODO_FECHADO = "PONTO-PER-001"
CODIGO_APURACAO_TRAVADA = "PONTO-APUR-003"
CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"

#: Nome de fila e de tarefa: contrato com `apps/worker/worker/filas.py` e
#: `apps/worker/worker/tarefas/__init__.py` (mesmo padrao de
#: `app.importadores.servico.criar_importacao_colaboradores`, F2). Renomear
#: um dos lados sem o outro faz o job cair num buraco.
NOME_TAREFA_RECALCULAR_PERIODO = "recalcular_periodo"


@dataclass(slots=True)
class DetalheDiaIgnorado:
    """Um dia pulado por período fechado, para o detalhamento do resultado."""

    vinculo_id: UUID
    data: dt.date
    codigo: str = CODIGO_APURACAO_TRAVADA


@dataclass(slots=True)
class ResultadoRecalculo:
    """Agregado devolvido por `recalcular_periodo` (dataclass própria do
    módulo, não um schema do contrato -- PCF §4)."""

    dias_processados: int = 0
    dias_alterados: int = 0
    dias_ignorados_fechados: int = 0
    vinculos_processados: int = 0
    dias_ignorados_detalhe: list[DetalheDiaIgnorado] = field(default_factory=list)


def _serializar_componente(componente: Any) -> dict[str, Any]:
    """Achata um `ApuracaoComponente` (schema Pydantic devolvido por
    `apurar_dia`, ou linha ORM lida diretamente) para o dicionário JSON
    canônico gravado em `auditoria.valor_anterior`/`valor_novo`."""
    if hasattr(componente, "model_dump"):
        dump: dict[str, Any] = componente.model_dump(mode="json", by_alias=True, exclude_none=True)
        return dump
    return {
        "codigo": componente.codigo,
        "categoria": componente.categoria,
        "minutos": componente.minutos,
        "fator": str(componente.fator),
        "minutosEquivalentes": componente.minutos_equivalentes,
        "origem": componente.origem,
    }


async def _estado_anterior(
    sessao: AsyncSession, tenant_id: UUID, vinculo_id: UUID, dia: dt.date
) -> tuple[ApuracaoDia | None, str | None, int | None, int, list[dict[str, Any]]]:
    """Lê o estado de `apuracoes_dia`/`apuracao_componentes` ANTES de chamar
    `apurar_dia`, para servir de base de comparação e de `valor_anterior`
    do diff. Devolve `(linha, hash, versao, saldo_minutos, componentes)`."""
    linha = (
        await sessao.execute(
            sa.select(ApuracaoDia).where(
                ApuracaoDia.tenant_id == tenant_id,
                ApuracaoDia.vinculo_id == vinculo_id,
                ApuracaoDia.data == dia,
            )
        )
    ).scalar_one_or_none()
    if linha is None:
        return None, None, None, 0, []
    componentes = list(
        (
            await sessao.execute(
                sa.select(ApuracaoComponente).where(ApuracaoComponente.apuracao_dia_id == linha.id)
            )
        )
        .scalars()
        .all()
    )
    return (
        linha,
        linha.hash_entrada,
        linha.versao,
        linha.saldo_minutos or 0,
        [_serializar_componente(c) for c in componentes],
    )


async def _resolver_vinculos(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    vinculo_id: UUID | None,
    empresa_id: UUID | None,
    unidade_id: UUID | None,
    departamento_id: UUID | None,
    colaborador_ids: Sequence[UUID] | None,
) -> list[Vinculo]:
    """Resolve o escopo de vínculos a reprocessar. Só vínculos sujeitos a
    apuração (`apura_ponto = true`), não excluídos logicamente."""
    consulta = sa.select(Vinculo).where(
        Vinculo.tenant_id == tenant_id,
        Vinculo.excluido_em.is_(None),
        Vinculo.apura_ponto.is_(True),
    )
    if vinculo_id is not None:
        consulta = consulta.where(Vinculo.id == vinculo_id)
    else:
        if colaborador_ids:
            consulta = consulta.where(Vinculo.colaborador_id.in_(colaborador_ids))
        if empresa_id is not None:
            consulta = consulta.where(Vinculo.empresa_id == empresa_id)
        if unidade_id is not None:
            consulta = consulta.where(Vinculo.unidade_id == unidade_id)
        if departamento_id is not None:
            consulta = consulta.where(Vinculo.departamento_id == departamento_id)
    return list((await sessao.execute(consulta)).scalars().all())


async def recalcular_periodo(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    vinculo_id: UUID | None = None,
    empresa_id: UUID | None = None,
    unidade_id: UUID | None = None,
    departamento_id: UUID | None = None,
    colaborador_ids: Sequence[UUID] | None = None,
    inicio: dt.date,
    fim: dt.date,
    motivo: str,
    forcar: bool = False,
) -> ResultadoRecalculo:
    """Assinatura fixada pelo PCF da fase (§4) -- mudar exige atualizar rota,
    worker e testes no mesmo commit. Reprocessa `[inicio, fim]` (inclusive)
    para cada vínculo do escopo resolvido, pulando dias em período fechado
    (contados, nunca abortam o restante) e publicando `apuracao.recalculada`
    uma vez por vínculo quando ao menos um dia mudou de fato.

    **Por que continua estritamente sequencial** (ADR-010, rodada 2 -- foi
    tentado, medido e revertido, não esquecido): distribuir os vínculos em
    sessões paralelas com `asyncio.gather` deixou o recálculo **1,5× MAIS
    LENTO** (98s → 150s para 100 vínculos × 31 dias). A causa não é
    afinável: `gravar_auditoria` toma um `pg_advisory_xact_lock` **por
    tenant**, escopado à transação -- ou seja, impossível de liberar antes do
    commit. A primeira sessão que grava auditoria segura o lock do tenant até
    terminar tudo; as outras ficam bloqueadas exatamente nesse ponto. Medido:
    4 execuções de `pg_advisory_xact_lock` somaram **166,6s de espera** num
    recálculo de 150s de parede. Vínculos são independentes entre si, mas a
    trilha de auditoria do tenant é um recurso serializado por desenho -- e é
    ela, não o vínculo, que define o teto de concorrência.
    """
    if fim < inicio:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO, detalhe="dataFim nao pode ser anterior a dataInicio."
        )
    if (
        vinculo_id is None
        and empresa_id is None
        and unidade_id is None
        and departamento_id is None
        and not colaborador_ids
    ):
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe="Escopo do recalculo nao informado: informe vinculoId, colaboradorIds ou "
            "empresaId/unidadeId/departamentoId.",
        )

    # Import tardio: `apurar_dia` e' de A1 (`app.apuracao.dominio.servico`),
    # que roda em paralelo com esta tarefa. Se o modulo ainda nao existir, o
    # import falha aqui -- exatamente onde e' usado -- em vez de quebrar o
    # import de todo o pacote `app.apuracao.tratamento` para quem so precisa
    # do CRUD (T8) ou da decisao (T9) sem recalculo de fato.
    from app.apuracao.dominio.servico import apurar_dia
    from app.jornada.resolvedor.servico import CacheResolucao

    dias = [inicio + dt.timedelta(days=n) for n in range((fim - inicio).days + 1)]

    async def processar_lote(
        sessao_lote: AsyncSession, lote: Sequence[Vinculo], resultado: ResultadoRecalculo
    ) -> None:
        """O laço `vínculo × dia` propriamente dito. Função aninhada só para
        dar aos três caches abaixo um escopo explícito: cada um guarda linhas
        ORM ligadas a UMA sessão e a UMA transação, e nenhum deles pode
        sobreviver à chamada de `recalcular_periodo` que os criou."""
        # ADR-010: cache de vida curta das leituras que NAO mudam de um dia para
        # o seguinte do mesmo vinculo (escala/jornada vigente, `jornada_dias`,
        # horario, fuso da unidade, afastamentos do colaborador, conjunto de
        # feriados da unidade). Criado UMA vez por chamada e descartado com ela
        # -- nunca guardado entre chamadas/transacoes, porque nao enxerga escrita
        # concorrente. Entidades compartilhadas (jornada, horario, feriados)
        # tambem sao reaproveitadas ENTRE vinculos do mesmo escopo, por isso o
        # cache e' desta funcao e nao do laco interno de dias.
        cache_resolucao = CacheResolucao()

        # ADR-010 (rodada 2): memoiza `(sequencia, hash)` da ultima linha da
        # trilha de auditoria deste tenant DENTRO desta transacao. Enquanto o
        # `pg_advisory_xact_lock` desta transacao esta em pe -- e ele fica em pe
        # da primeira gravacao ate o commit -- ninguem mais pode escrever na
        # cadeia deste tenant, entao reler `MAX(sequencia)`/hash a cada dia
        # alterado so paga round-trip para receber de volta o que acabamos de
        # escrever. Ver `CacheCadeiaAuditoria` para o argumento completo.
        cache_auditoria = CacheCadeiaAuditoria()

        # ADR-010 (rodada 2): `verificar_periodo_aberto` e' funcao pura de
        # `(tenant, empresa, unidade, departamento, dia)` -- e' uma LEITURA de
        # `fechamentos`, que este laco nunca escreve. Com 100 vinculos da mesma
        # unidade x 31 dias, a consulta era refeita 3.100 vezes para 31 respostas
        # distintas. O cache e' local a esta chamada (nunca sobrevive a ela), pela
        # mesma razao do `CacheResolucao`: entre uma chamada e outra um fechamento
        # pode ter sido criado, e a resposta tem de voltar a ser lida do banco.
        cache_periodo: dict[tuple[UUID | None, UUID | None, UUID | None, dt.date], bool] = {}

        async def periodo_aberto(vinc: Vinculo, dia: dt.date) -> bool:
            chave = (vinc.empresa_id, vinc.unidade_id, vinc.departamento_id, dia)
            memorizado = cache_periodo.get(chave)
            if memorizado is not None:
                return memorizado
            try:
                await verificar_periodo_aberto(
                    sessao_lote,
                    tenant_id,
                    empresa_id=vinc.empresa_id,
                    data=dia,
                    unidade_id=vinc.unidade_id,
                    departamento_id=vinc.departamento_id,
                )
            except ErroDeAplicacao as exc:
                if exc.codigo != CODIGO_PERIODO_FECHADO:
                    raise
                cache_periodo[chave] = False
                return False
            cache_periodo[chave] = True
            return True

        # `_resolver_vinculos` ja aplicou `excluido_em IS NULL`, o mesmo filtro de
        # `app.jornada.modelagem.vinculo_jornadas.obter_vinculo` -- semear o cache
        # com estas linhas evita reler `vinculos` uma vez por vinculo la dentro.
        for vinc in lote:
            cache_resolucao.vinculos[vinc.id] = vinc

        for vinc in lote:
            resultado.vinculos_processados += 1
            dias_alterados_vinculo = 0
            saldo_antes_total = 0
            saldo_depois_total = 0

            for dia in dias:
                if not await periodo_aberto(vinc, dia):
                    resultado.dias_ignorados_fechados += 1
                    resultado.dias_ignorados_detalhe.append(
                        DetalheDiaIgnorado(vinculo_id=vinc.id, data=dia)
                    )
                    continue

                (
                    _antes_linha,
                    hash_antes,
                    versao_antes,
                    saldo_antes,
                    componentes_antes,
                ) = await _estado_anterior(sessao_lote, tenant_id, vinc.id, dia)

                apuracao = await apurar_dia(
                    sessao_lote, tenant_id, vinc.id, dia, cache_resolucao=cache_resolucao
                )
                await sessao_lote.flush()

                resultado.dias_processados += 1
                saldo_antes_total += saldo_antes
                saldo_depois_total += apuracao.saldo_minutos or 0

                mudou = apuracao.hash_entrada != hash_antes
                if not mudou:
                    continue

                dias_alterados_vinculo += 1
                resultado.dias_alterados += 1
                componentes_depois = [
                    _serializar_componente(c) for c in (apuracao.componentes or [])
                ]
                await gravar_auditoria(
                    sessao_lote,
                    tenant_id=tenant_id,
                    evento="apuracao.recalculada",
                    entidade="apuracoes_dia",
                    acao="recalcular",
                    entidade_id=apuracao.id,
                    valor_anterior=(
                        {
                            "versao": versao_antes,
                            "hashEntrada": hash_antes,
                            "componentes": componentes_antes,
                        }
                        if _antes_linha is not None
                        else None
                    ),
                    valor_novo={
                        "versao": apuracao.versao,
                        "hashEntrada": apuracao.hash_entrada,
                        "componentes": componentes_depois,
                    },
                    metadados={"motivo": motivo, "forcar": forcar, "data": dia.isoformat()},
                    cache_cadeia=cache_auditoria,
                )

            if dias_alterados_vinculo > 0:
                eventos.publicar_apuracao_recalculada(
                    tenant_id=tenant_id,
                    vinculo_id=vinc.id,
                    colaborador_id=vinc.colaborador_id,
                    data_inicio=inicio,
                    data_fim=fim,
                    dias_alterados=dias_alterados_vinculo,
                    motivo=motivo,
                    saldo_anterior_minutos=saldo_antes_total,
                    saldo_novo_minutos=saldo_depois_total,
                )

    vinculos = await _resolver_vinculos(
        sessao,
        tenant_id,
        vinculo_id=vinculo_id,
        empresa_id=empresa_id,
        unidade_id=unidade_id,
        departamento_id=departamento_id,
        colaborador_ids=colaborador_ids,
    )
    resultado = ResultadoRecalculo()
    await processar_lote(sessao, vinculos, resultado)
    return resultado


async def _resolver_vinculos_do_pedido(
    sessao: AsyncSession, tenant_id: UUID, corpo: esquemas.RecalculoRequisicao
) -> list[Vinculo]:
    """Resolve `RecalculoRequisicao` (vínculos explícitos OU escopo por
    empresa/unidade/departamento/colaboradores) em linhas de `Vinculo`
    concretas, para o `POST /v1/apuracoes/recalcular` enfileirar um job por
    vínculo (ver `enfileirar_recalculo`)."""
    condicoes = [
        Vinculo.tenant_id == tenant_id,
        Vinculo.excluido_em.is_(None),
        Vinculo.apura_ponto.is_(True),
    ]
    if corpo.vinculo_ids:
        condicoes.append(Vinculo.id.in_(corpo.vinculo_ids))
    else:
        if corpo.colaborador_ids:
            condicoes.append(Vinculo.colaborador_id.in_(corpo.colaborador_ids))
        if corpo.empresa_id is not None:
            condicoes.append(Vinculo.empresa_id == corpo.empresa_id)
        if corpo.unidade_id is not None:
            condicoes.append(Vinculo.unidade_id == corpo.unidade_id)
        if corpo.departamento_id is not None:
            condicoes.append(Vinculo.departamento_id == corpo.departamento_id)
    consulta = sa.select(Vinculo).where(*condicoes)
    return list((await sessao.execute(consulta)).scalars().all())


async def enfileirar_recalculo(
    sessao: AsyncSession,
    tenant_id: UUID,
    corpo: esquemas.RecalculoRequisicao,
    *,
    redis_url: str,
) -> tuple[UUID, int]:
    """Lado HTTP de `POST /v1/apuracoes/recalcular` (T10): resolve o escopo
    do pedido em vínculos concretos e enfileira **um job por vínculo**
    (`ctx["redis"].enqueue_job("recalcular_periodo", ...)`, mesmo padrão de
    `app.importadores.servico.criar_importacao_colaboradores`, F2).

    **Por que fan-out no momento do enfileiramento, e não dentro da
    tarefa:** a assinatura fixada do glue do worker
    (`apps/worker/worker/tarefas/apuracao.py::recalcular_periodo`) aceita
    só um `vinculo_id` singular opcional -- ela não carrega
    `empresaId`/`unidadeId`/`departamentoId`/`colaboradorIds` do pedido
    HTTP. Resolver o escopo aqui, antes de enfileirar, evita precisar mudar
    essa assinatura (fixada pela Fase 0) só para carregar um filtro que ela
    não tem como aceitar. Achado de design registrado no relatório da fase.

    Devolve `(job_id, total_vinculos)`. `job_id` é gerado localmente (não é
    o id de nenhum job do ARQ em particular) porque a tag `apuracoes` não
    declara nenhuma operação de consulta de status por identificador de
    recálculo nem tabela para persistir o handle (achado de contrato,
    `docs/backlog.md`) -- o identificador serve só para preencher
    `ProcessamentoAssincrono.id` da resposta `202`; a conclusão observável é
    `GET /v1/apuracoes` e o evento `apuracao.recalculada`.
    """
    if corpo.data_inicio is None or corpo.data_fim is None:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO, detalhe="dataInicio e dataFim sao obrigatorios."
        )
    if corpo.data_fim < corpo.data_inicio:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO, detalhe="dataFim nao pode ser anterior a dataInicio."
        )
    if not corpo.vinculo_ids and not corpo.colaborador_ids and corpo.empresa_id is None:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe="Informe vinculoIds, colaboradorIds ou empresaId (com unidadeId/"
            "departamentoId opcionais) para delimitar o escopo do recalculo.",
        )

    vinculos = await _resolver_vinculos_do_pedido(sessao, tenant_id, corpo)
    motivo = corpo.motivo.value if corpo.motivo is not None else "manual"

    pool = await create_pool(RedisSettings.from_dsn(redis_url), default_queue_name=FILA_PADRAO)
    try:
        for vinc in vinculos:
            await pool.enqueue_job(
                NOME_TAREFA_RECALCULAR_PERIODO,
                tenant_id=str(tenant_id),
                vinculo_id=str(vinc.id),
                inicio=corpo.data_inicio.isoformat(),
                fim=corpo.data_fim.isoformat(),
                motivo=motivo,
            )
    finally:
        await pool.aclose()

    return uuid4(), len(vinculos)
