"""Ciclo de vida do fechamento: criar, listar, obter e reabrir (T5, F10/A2).

`criarFechamento` cria a linha `Fechamento(status='em_andamento')` **de
forma síncrona** dentro da própria requisição (decisão fixada pelo PCF: o
`202`/`ProcessamentoAssincrono` do contrato é sobre o *processamento
pesado* -- travar centenas de vínculos × dias e, opcionalmente, gerar os
espelhos --, não sobre a criação do registro; mesma distinção que F4 fez
entre criar um `Tratamento` síncrono e enfileirar `recalcular_periodo`), roda
a conferência (`conferencia.calcular_conferencia`) **na mesma transação**: se
houver pendência bloqueante e `forcar` for falso, recusa com
`PONTO-PER-004` e **não** cria a linha; caso contrário, enfileira
`processar_fechamento` (worker) passando `fechamento.id`, devolve `202` com
`ProcessamentoAssincrono(id=fechamento.id, status="enfileirado")` -- **sem
preencher `tipo`** (achado de contrato §2.7 item 3 do PCF: o enum de
`ProcessamentoAssincrono.tipo` não tem o valor `fechamento`; `tipo` não é
`required` no schema, então a resposta é válida sem ele).

**A trava em si já existe e já funciona** (F4,
`app.apuracao.tratamento.fechamento.verificar_periodo_aberto`) assim que
existir uma linha `fechamentos.status='fechado'` cobrindo a data e o
escopo -- este módulo só cria essa linha corretamente, nunca reimplementa a
trava.

**Achado de contrato, registrado (não corrigido silenciosamente):**
`fechamentos` (schema.sql seção 12) não tem coluna `equipe_id` nem
`colaborador_id`, embora `fechamentos.escopo`/`FechamentoCriar.escopo`
aceitem os valores `equipe`/`colaborador` no `CHECK`/enum, e
`verificar_periodo_aberto` (F4, congelado) só monta condição de escopo para
`empresa`/`unidade`/`departamento` -- um `Fechamento` com
`escopo='equipe'`/`'colaborador'` seria criado mas a trava NUNCA o
encontraria (a cláusula `OR` de `verificar_periodo_aberto` não tem ramo para
esses dois escopos). `criarFechamento` recusa esses dois valores com
`PONTO-VAL-001` em vez de criar um fechamento que não trava nada -- ver
`docs/backlog.md`.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from arq import create_pool
from arq.connections import RedisSettings
from ponto_contracts import Fechamento, Periodo
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.core.filas import FILA_PADRAO
from app.identidade.auditoria.hash_chain import gravar_auditoria
from app.schemas import contrato as esquemas
from app.workflow.fechamento.conferencia import ParametrosConferencia, calcular_conferencia
from app.workflow.fechamento.erros_bd import traduzir_integridade
from app.workflow.fechamento.eventos import publicar_periodo_reaberto
from app.workflow.fechamento.paginacao import (
    CampoOrdenacao,
    codificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    montar_paginacao,
    normalizar_limite,
)

CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"
CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"
CODIGO_JA_FECHADO = "PONTO-PER-002"
CODIGO_REABERTURA_SEM_JUSTIFICATIVA = "PONTO-PER-003"
CODIGO_PENDENCIA_BLOQUEANTE = "PONTO-PER-004"
CODIGO_TRANSICAO_INVALIDA = "PONTO-CONF-003"

#: Nome de fila/tarefa: contrato com `apps/worker/worker/filas.py` e
#: `apps/worker/worker/tarefas/__init__.py` (mesmo padrão de
#: `app.apuracao.tratamento.recalculo.NOME_TAREFA_RECALCULAR_PERIODO`, F4).
#: Renomear um dos lados sem o outro faz o job cair num buraco.
NOME_TAREFA_PROCESSAR_FECHAMENTO = "processar_fechamento"

#: Escopos que a trava real (`verificar_periodo_aberto`, F4) sabe reconhecer.
#: Ver docstring do módulo -- `equipe`/`colaborador` são achado de contrato.
_ESCOPOS_SUPORTADOS_PELA_TRAVA = frozenset({"empresa", "unidade", "departamento"})

_CAMPOS_ORDENACAO_FECHAMENTO: dict[str, CampoOrdenacao] = {
    "fechadoEm": CampoOrdenacao(Fechamento.fechado_em, dt.datetime.fromisoformat),
    "criadoEm": CampoOrdenacao(Fechamento.criado_em, dt.datetime.fromisoformat),
}


def _valor(bruto: Any) -> Any:
    return bruto.value if hasattr(bruto, "value") else bruto


async def obter_periodo_do_tenant(
    sessao: AsyncSession, tenant_id: UUID, periodo_id: UUID
) -> Periodo:
    periodo = await sessao.get(Periodo, periodo_id)
    if periodo is None or periodo.tenant_id != tenant_id:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Periodo nao encontrado.")
    return periodo


async def obter_fechamento(
    sessao: AsyncSession, tenant_id: UUID, fechamento_id: UUID
) -> Fechamento:
    fechamento = await sessao.get(Fechamento, fechamento_id)
    if fechamento is None or fechamento.tenant_id != tenant_id:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Fechamento nao encontrado.")
    return fechamento


def _condicao_igual_ou_nula(coluna: Any, valor: UUID | None) -> Any:
    return coluna.is_(None) if valor is None else coluna == valor


async def _fechamento_ja_fechado(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    periodo_id: UUID,
    escopo: str,
    empresa_id: UUID,
    unidade_id: UUID | None,
    departamento_id: UUID | None,
) -> bool:
    consulta = (
        sa.select(Fechamento.id)
        .where(
            Fechamento.tenant_id == tenant_id,
            Fechamento.periodo_id == periodo_id,
            Fechamento.escopo == escopo,
            Fechamento.empresa_id == empresa_id,
            _condicao_igual_ou_nula(Fechamento.unidade_id, unidade_id),
            _condicao_igual_ou_nula(Fechamento.departamento_id, departamento_id),
            Fechamento.status == "fechado",
        )
        .limit(1)
    )
    resultado = await sessao.execute(consulta)
    return resultado.scalar_one_or_none() is not None


async def criar_fechamento(
    sessao: AsyncSession,
    tenant_id: UUID,
    dados: esquemas.FechamentoCriar,
    *,
    usuario_id: UUID | None,
    redis_url: str,
) -> esquemas.ProcessamentoAssincrono:
    if dados.periodo_id is None:
        raise ErroDeAplicacao(CODIGO_CORPO_INVALIDO, detalhe="periodoId e obrigatorio.")
    if dados.empresa_id is None:
        raise ErroDeAplicacao(CODIGO_CORPO_INVALIDO, detalhe="empresaId e obrigatorio.")

    periodo = await obter_periodo_do_tenant(sessao, tenant_id, dados.periodo_id)
    if periodo.empresa_id != dados.empresa_id:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO, detalhe="empresaId nao corresponde a empresa do periodo."
        )

    escopo = _valor(dados.escopo) or "empresa"
    if escopo not in _ESCOPOS_SUPORTADOS_PELA_TRAVA:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe=(
                f"escopo '{escopo}' ainda nao e suportado por criarFechamento: a trava de "
                "periodo (F4) so reconhece empresa/unidade/departamento. Ver docs/backlog.md."
            ),
        )
    unidade_id = dados.unidade_id if escopo == "unidade" else None
    departamento_id = dados.departamento_id if escopo == "departamento" else None
    if escopo == "unidade" and unidade_id is None:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO, detalhe="unidadeId e obrigatorio quando escopo e unidade."
        )
    if escopo == "departamento" and departamento_id is None:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe="departamentoId e obrigatorio quando escopo e departamento.",
        )

    if await _fechamento_ja_fechado(
        sessao,
        tenant_id,
        periodo_id=periodo.id,
        escopo=escopo,
        empresa_id=dados.empresa_id,
        unidade_id=unidade_id,
        departamento_id=departamento_id,
    ):
        raise ErroDeAplicacao(
            CODIGO_JA_FECHADO,
            detalhe="Ja existe um fechamento concluido para este periodo e escopo.",
        )

    parametros = ParametrosConferencia(
        periodo=periodo,
        escopo=escopo,
        empresa_id=dados.empresa_id,
        unidade_id=unidade_id,
        departamento_id=departamento_id,
    )
    conferencia = await calcular_conferencia(sessao, tenant_id, parametros)

    forcar = bool(dados.forcar)
    if not conferencia.pode_fechar and not forcar:
        bloqueantes = conferencia.bloqueantes or []
        raise ErroDeAplicacao(
            CODIGO_PENDENCIA_BLOQUEANTE,
            detalhe=(
                f"{len(bloqueantes)} pendencia(s) bloqueante(s) ({', '.join(bloqueantes)}): "
                f"{conferencia.ocorrencias_abertas or 0} ocorrencia(s) aberta(s), "
                f"{conferencia.apuracoes_pendentes or 0} dia(s) nao apurado(s). "
                "Use forcar=true para fechar mesmo assim (o total pendente fica registrado)."
            ),
        )

    total_pendencias = (conferencia.ocorrencias_abertas or 0) + (
        conferencia.solicitacoes_pendentes or 0
    )
    fechamento = Fechamento(
        tenant_id=tenant_id,
        periodo_id=periodo.id,
        empresa_id=dados.empresa_id,
        unidade_id=unidade_id,
        departamento_id=departamento_id,
        escopo=escopo,
        status="em_andamento",
        total_colaboradores=conferencia.total_colaboradores or 0,
        total_ocorrencias=conferencia.ocorrencias_abertas or 0,
        total_pendencias=total_pendencias,
        criado_por=usuario_id,
    )
    sessao.add(fechamento)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc

    await _enfileirar_processar_fechamento(
        fechamento_id=fechamento.id,
        tenant_id=tenant_id,
        gerar_espelhos=bool(dados.gerar_espelhos),
        redis_url=redis_url,
    )

    # `.model_validate({...})` em vez do construtor por *keyword* direto:
    # mesmo padrão já usado por `app/routers/apuracoes.py` para este mesmo
    # schema -- o plugin do mypy para Pydantic sintetiza o `__init__` pelos
    # ALIASES (camelCase), não pelos nomes de campo em snake_case, então
    # construir por dicionário evita a ambiguidade nos dois sentidos.
    return esquemas.ProcessamentoAssincrono.model_validate(
        {"id": fechamento.id, "status": "enfileirado"}
    )


async def _enfileirar_processar_fechamento(
    *, fechamento_id: UUID, tenant_id: UUID, gerar_espelhos: bool, redis_url: str
) -> None:
    pool = await create_pool(RedisSettings.from_dsn(redis_url), default_queue_name=FILA_PADRAO)
    try:
        await pool.enqueue_job(
            NOME_TAREFA_PROCESSAR_FECHAMENTO,
            tenant_id=str(tenant_id),
            fechamento_id=str(fechamento_id),
            gerar_espelhos=gerar_espelhos,
        )
    finally:
        await pool.aclose()


async def listar_fechamentos(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    periodo_id: UUID | None = None,
    empresa_id: UUID | None = None,
    unidade_id: UUID | None = None,
    escopo: str | None = None,
    status: str | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[Fechamento], esquemas.Paginacao]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO_FECHAMENTO), padrao="criadoEm"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = sa.select(Fechamento).where(Fechamento.tenant_id == tenant_id)
    if periodo_id is not None:
        consulta = consulta.where(Fechamento.periodo_id == periodo_id)
    if empresa_id is not None:
        consulta = consulta.where(Fechamento.empresa_id == empresa_id)
    if unidade_id is not None:
        consulta = consulta.where(Fechamento.unidade_id == unidade_id)
    if escopo is not None:
        consulta = consulta.where(Fechamento.escopo == escopo)
    if status is not None:
        consulta = consulta.where(Fechamento.status == status)

    campo = _CAMPOS_ORDENACAO_FECHAMENTO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=Fechamento.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    atributo = "fechado_em" if ordenacao.campo == "fechadoEm" else "criado_em"
    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        valor_cursor = getattr(ultimo, atributo)
        if valor_cursor is not None:
            proximo_cursor = codificar_cursor(ordenacao, valor_cursor, ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao


async def reabrir_fechamento(
    sessao: AsyncSession,
    tenant_id: UUID,
    fechamento_id: UUID,
    dados: esquemas.ReaberturaRequisicao,
    *,
    usuario_id: UUID | None,
) -> Fechamento:
    """`PONTO-PER-003` (validado antes do `CHECK` do banco, para uma
    mensagem clara em vez do erro cru); `PONTO-CONF-003` quando o
    fechamento não está `fechado`. Reabertura é sempre do fechamento
    inteiro -- `ReaberturaRequisicao.dataInicio`/`dataFim`, quando
    informados, só restringem o texto gravado em `auditoria.metadados`
    (achado: `fechamentos` não tem coluna para uma reabertura parcial de
    sub-intervalo; a trava (F4) só sabe checar `status='fechado'` do
    fechamento inteiro -- ver docstring do módulo)."""
    motivo = (dados.motivo or "").strip()
    if len(motivo) < 10:
        raise ErroDeAplicacao(
            CODIGO_REABERTURA_SEM_JUSTIFICATIVA,
            detalhe="motivo e obrigatorio na reabertura (minimo 10 caracteres).",
        )

    fechamento = await obter_fechamento(sessao, tenant_id, fechamento_id)
    if fechamento.status != "fechado":
        raise ErroDeAplicacao(
            CODIGO_TRANSICAO_INVALIDA,
            detalhe=f"Fechamento em situacao '{fechamento.status}' nao pode ser reaberto.",
        )

    status_anterior = fechamento.status
    agora = dt.datetime.now(tz=dt.UTC)
    fechamento.status = "reaberto"
    fechamento.reaberto_em = agora
    fechamento.reaberto_por = usuario_id
    fechamento.motivo_reabertura = motivo
    fechamento.atualizado_por = usuario_id
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc

    metadados: dict[str, Any] | None = None
    if dados.data_inicio is not None or dados.data_fim is not None:
        metadados = {
            "dataInicio": dados.data_inicio.isoformat() if dados.data_inicio else None,
            "dataFim": dados.data_fim.isoformat() if dados.data_fim else None,
        }
    await gravar_auditoria(
        sessao,
        tenant_id=tenant_id,
        evento="periodo.reaberto",
        entidade="fechamentos",
        acao="reabrir",
        entidade_id=fechamento.id,
        usuario_id=usuario_id,
        valor_anterior={"status": status_anterior},
        valor_novo={"status": "reaberto", "motivo": motivo},
        metadados=metadados,
    )

    # Espelhos oficiais desta fechamento que ficam "desatualizados" -- nenhum
    # e apagado nem alterado, so contados (PCF §5, T5).
    from ponto_contracts import Espelho

    total_espelhos = (
        await sessao.execute(
            sa.select(sa.func.count()).where(
                Espelho.tenant_id == tenant_id,
                Espelho.fechamento_id == fechamento.id,
                Espelho.tipo == "oficial",
            )
        )
    ).scalar_one()

    envelope = publicar_periodo_reaberto(
        tenant_id=tenant_id,
        fechamento_id=fechamento.id,
        periodo_id=fechamento.periodo_id,
        empresa_id=fechamento.empresa_id,
        reaberto_por=usuario_id or uuid4(),
        reaberto_em=agora,
        motivo=motivo,
        data_inicio=dados.data_inicio,
        data_fim=dados.data_fim,
        espelhos_invalidados=int(total_espelhos),
    )
    # Achado de integracao consertado ao fechar a fase (T15/T16) -- mesma
    # nota de `app/workflow/solicitacoes/servico.py::criar_solicitacao`.
    # Import tardio: `app.notificacao` e ownership de A3.
    from app.notificacao.motor import processar_evento

    await processar_evento(sessao, tenant_id, envelope)
    return fechamento
