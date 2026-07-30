"""CRUD/ciclo de vida de `Solicitacao` (F10, T2, agente A1):
`criarSolicitacao`, `listarSolicitacoes`, `obterSolicitacao`,
`cancelarSolicitacao`.

**Achado de contrato, registrado em `docs/backlog.md` (não corrigido em
silêncio): `SolicitacaoCriar.vinculoId` é opcional no contrato, mas a
materialização via `criar_tratamento` (F4) EXIGE um `vinculoId` não nulo
(mesmo achado que o PCF de F4 já documentou para `TratamentoCriar`).**
`apps/web/src/app/eu/solicitacoes/nova/page.tsx` (F8, já concluída) confirma
que nenhum cliente real envia `vinculoId` hoje -- só `tipoSolicitacaoId`,
`colaboradorId`, `descricao` e `dataReferencia` OU `dataInicio`/`dataFim`.
Decisão fixada por este módulo: `criarSolicitacao` RESOLVE o vínculo do lado
do servidor a partir de `colaboradorId` (mesmo padrão de `_vinculo_ativo` de
`app.marcacao.pipeline.ingestao`, F5 -- réplica própria, nunca importada de
outra fase) quando o cliente não informa um, e grava o resultado em
`solicitacoes.vinculo_id` -- assim a materialização (T4) nunca precisa
resolver de novo, ela só lê o campo já preenchido pela criação.

**Segundo achado, mesma natureza:** para a categoria `afastamento`
(retroativo), a tabela do PCF §2.2 exige `Tratamento.tipo_afastamento_id`
preenchido, mas não existe campo dedicado em `SolicitacaoCriar` para isso, e
`payload` é `additionalProperties: true` sem formato fixo. Decisão fixada:
o cliente informa `payload.tipoAfastamentoId` (UUID, como string) para essa
categoria -- documentado aqui e validado na criação (`PONTO-VAL-001` se
ausente), para falhar cedo em vez de falhar tarde na aprovação final.
Nenhum cliente real (F8) envia esse campo ainda -- registrado em
`docs/backlog.md` como impacto concreto do achado.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import Aprovacao, Colaborador, Solicitacao, TipoSolicitacao, Vinculo
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from app.workflow.aprovacoes.resolucao import resolver_aprovador_papel
from app.workflow.solicitacoes import eventos
from app.workflow.solicitacoes.erros_bd import traduzir_integridade
from app.workflow.solicitacoes.paginacao import (
    CampoOrdenacao,
    codificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    montar_paginacao,
    normalizar_limite,
)
from app.workflow.solicitacoes.tipos import obter_tipo_solicitacao, papeis_da_cadeia

CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"
CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"
CODIGO_TRANSICAO_INVALIDA = "PONTO-CONF-003"
#: `PONTO-VAL-007`, "Intervalo de datas invalido ... ou a janela pedida
#: excede o maximo permitido pela operacao" -- descricao literal de
#: `errors.yaml` que cobre tanto `dataFim < dataInicio` quanto retroativo
#: alem de `permite_retroativo_dias` (T2 pede para decidir e documentar
#: entre VAL-010/CONF-001; nenhum dos dois descreve "janela excedida" tao
#: bem quanto VAL-007, entao a escolha e VAL-007 para as duas checagens).
CODIGO_INTERVALO_INVALIDO = "PONTO-VAL-007"

#: Estagios a partir dos quais `cancelarSolicitacao` e aceito -- ja
#: concluida (aprovada/reprovada), ja cancelada ou expirada nao admite
#: cancelamento (idempotencia negativa, mesmo padrao de
#: `app.apuracao.tratamento.servico.cancelar_tratamento`, F4).
_STATUS_CANCELAVEIS = frozenset({"rascunho", "pendente", "em_aprovacao"})

_CAMPOS_ORDENACAO: dict[str, CampoOrdenacao] = {
    "criadoEm": CampoOrdenacao(Solicitacao.criado_em, dt.datetime.fromisoformat),
    "prazoEm": CampoOrdenacao(Solicitacao.prazo_em, dt.datetime.fromisoformat),
    "dataReferencia": CampoOrdenacao(Solicitacao.data_referencia, dt.date.fromisoformat),
}


async def obter_colaborador(sessao: AsyncSession, colaborador_id: UUID) -> Colaborador:
    colaborador = await sessao.get(Colaborador, colaborador_id)
    if colaborador is None or colaborador.excluido_em is not None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Colaborador nao encontrado.")
    return colaborador


async def _resolver_vinculo(
    sessao: AsyncSession, tenant_id: UUID, colaborador_id: UUID, data_referencia: dt.date | None
) -> Vinculo | None:
    """Réplica própria de `app.marcacao.pipeline.ingestao._vinculo_ativo`
    (F5, privada, não importada de outra fase): prefere o vínculo `ativo`
    vigente na data pedida, com `principal=true` como desempate; sem data ou
    sem vínculo vigente naquela data, cai para o vínculo `ativo` mais
    recente do colaborador. `None` quando o colaborador não tem nenhum
    vínculo `ativo` -- quem chama decide se isso é bloqueante."""
    base = sa.select(Vinculo).where(
        Vinculo.tenant_id == tenant_id,
        Vinculo.colaborador_id == colaborador_id,
        Vinculo.excluido_em.is_(None),
        Vinculo.status == "ativo",
    )
    if data_referencia is not None:
        vigente = (
            (
                await sessao.execute(
                    base.where(
                        Vinculo.data_inicio <= data_referencia,
                        sa.or_(Vinculo.data_fim.is_(None), Vinculo.data_fim >= data_referencia),
                    )
                    .order_by(Vinculo.principal.desc(), Vinculo.data_inicio.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if vigente is not None:
            return vigente
    return (
        (
            await sessao.execute(
                base.order_by(Vinculo.principal.desc(), Vinculo.data_inicio.desc()).limit(1)
            )
        )
        .scalars()
        .first()
    )


async def obter_solicitacao(sessao: AsyncSession, solicitacao_id: UUID) -> Solicitacao:
    solicitacao = await sessao.get(Solicitacao, solicitacao_id)
    if solicitacao is None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Solicitacao nao encontrada.")
    return solicitacao


async def listar_aprovacoes_da_solicitacao(
    sessao: AsyncSession, tenant_id: UUID, solicitacao_id: UUID
) -> Sequence[Aprovacao]:
    """Histórico completo das etapas de uma solicitação, na ordem da cadeia
    -- usado por `obterSolicitacao` (a descrição da operação no contrato
    promete "o historico completo das etapas")."""
    consulta = (
        sa.select(Aprovacao)
        .where(Aprovacao.tenant_id == tenant_id, Aprovacao.solicitacao_id == solicitacao_id)
        .order_by(Aprovacao.etapa.asc())
    )
    return (await sessao.execute(consulta)).scalars().all()


async def _proximo_protocolo(sessao: AsyncSession, tenant_id: UUID, ano: int) -> str:
    """Protocolo `AAAA-NNNNNN`, sequencial por tenant/ano. Serializado por um
    `pg_advisory_xact_lock` escopado à transação (mesma primitiva que
    `app.identidade.auditoria.hash_chain` usa para o encadeamento de hash,
    F1 -- técnica comum reaproveitada, não a função em si), com uma chave de
    lock própria (`hashtextextended(..., 1)`, sal diferente de `0` para não
    colidir com o namespace de lock de `hash_chain`) -- evita duas
    solicitações concorrentes do mesmo tenant/ano lerem a mesma contagem e
    colidirem em `uq_solicitacoes_protocolo` (o `IntegrityError` ainda é
    tratado como rede de segurança, nunca a única defesa)."""
    chave = f"solicitacoes:{tenant_id}:{ano}"
    await sessao.execute(
        sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:chave, 1))"), {"chave": chave}
    )
    total = await sessao.scalar(
        sa.select(sa.func.count())
        .select_from(Solicitacao)
        .where(Solicitacao.tenant_id == tenant_id, Solicitacao.protocolo.like(f"{ano}-%"))
    )
    return f"{ano}-{(total or 0) + 1:06d}"


def _valor(bruto: Any) -> Any:
    return bruto.value if hasattr(bruto, "value") else bruto


async def criar_solicitacao(
    sessao: AsyncSession,
    tenant_id: UUID,
    dados: esquemas.SolicitacaoCriar,
    *,
    usuario_id: UUID | None,
) -> Solicitacao:
    if dados.data_referencia is None and (dados.data_inicio is None or dados.data_fim is None):
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO, detalhe="Informe dataReferencia ou dataInicio e dataFim."
        )
    if (
        dados.data_inicio is not None
        and dados.data_fim is not None
        and dados.data_fim < dados.data_inicio
    ):
        raise ErroDeAplicacao(
            CODIGO_INTERVALO_INVALIDO, detalhe="dataFim nao pode ser anterior a dataInicio."
        )

    descricao = (dados.descricao or "").strip()
    if not descricao:
        raise ErroDeAplicacao(CODIGO_CORPO_INVALIDO, detalhe="descricao e obrigatoria.")

    tipo = await obter_tipo_solicitacao(sessao, dados.tipo_solicitacao_id)
    if not tipo.ativo:
        raise ErroDeAplicacao(CODIGO_CORPO_INVALIDO, detalhe="Tipo de solicitacao inativo.")

    papeis = papeis_da_cadeia(tipo.etapas)
    if not papeis:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe="Tipo de solicitacao sem cadeia de aprovacao configurada.",
        )

    colaborador = await obter_colaborador(sessao, dados.colaborador_id)

    data_ancora = dados.data_referencia or dados.data_inicio
    if data_ancora is None:  # defensivo -- ja garantido pela checagem no topo da funcao
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO, detalhe="Informe dataReferencia ou dataInicio e dataFim."
        )

    if tipo.permite_retroativo_dias is not None:
        dias_atras = (dt.date.today() - data_ancora).days
        if dias_atras > tipo.permite_retroativo_dias:
            raise ErroDeAplicacao(
                CODIGO_INTERVALO_INVALIDO,
                detalhe=(
                    f"Pedido retroativo alem do limite de {tipo.permite_retroativo_dias} "
                    "dias deste tipo de solicitacao."
                ),
            )

    payload = dict(dados.payload or {})
    if tipo.categoria == "afastamento" and not payload.get("tipoAfastamentoId"):
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe="payload.tipoAfastamentoId e obrigatorio para a categoria 'afastamento'.",
        )

    vinculo_id = dados.vinculo_id
    if vinculo_id is not None:
        vinculo = await sessao.get(Vinculo, vinculo_id)
        if vinculo is None or vinculo.excluido_em is not None:
            raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Vinculo nao encontrado.")
        if vinculo.colaborador_id != colaborador.id:
            raise ErroDeAplicacao(
                CODIGO_CORPO_INVALIDO, detalhe="vinculoId nao pertence ao colaboradorId informado."
            )
    else:
        resolvido = await _resolver_vinculo(sessao, tenant_id, colaborador.id, data_ancora)
        vinculo_id = resolvido.id if resolvido is not None else None

    ano = dt.datetime.now(tz=dt.UTC).year
    protocolo = await _proximo_protocolo(sessao, tenant_id, ano)

    prazo_em: dt.datetime | None = None
    if tipo.prazo_resposta_horas is not None:
        prazo_em = dt.datetime.now(tz=dt.UTC) + dt.timedelta(hours=tipo.prazo_resposta_horas)

    solicitacao = Solicitacao(
        tenant_id=tenant_id,
        tipo_solicitacao_id=tipo.id,
        colaborador_id=colaborador.id,
        vinculo_id=vinculo_id,
        solicitante_usuario_id=dados.solicitante_usuario_id or usuario_id,
        protocolo=protocolo,
        data_referencia=dados.data_referencia,
        data_inicio=dados.data_inicio,
        data_fim=dados.data_fim,
        descricao=descricao,
        payload=payload,
        status="em_aprovacao",
        etapa_atual=1,
        prazo_em=prazo_em,
        criado_por=usuario_id,
    )
    sessao.add(solicitacao)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc

    aprovador_id = await resolver_aprovador_papel(
        sessao,
        tenant_id,
        colaborador_id=colaborador.id,
        papel=papeis[0],
        data_referencia=data_ancora,
    )
    primeira_etapa = Aprovacao(
        tenant_id=tenant_id,
        solicitacao_id=solicitacao.id,
        etapa=1,
        papel=papeis[0],
        aprovador_usuario_id=aprovador_id,
        decisao="pendente",
        prazo_em=prazo_em,
        criado_por=usuario_id,
    )
    sessao.add(primeira_etapa)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc

    # `ajuste.solicitado` so dispara para `ajuste_ponto` -- literal do
    # contrato (events.yaml, PCF §2.7 item 5), nao ampliado para as demais
    # categorias.
    if tipo.categoria == "ajuste_ponto":
        envelope = eventos.publicar_ajuste_solicitado(
            tenant_id=tenant_id,
            solicitacao_id=solicitacao.id,
            protocolo=protocolo,
            colaborador_id=colaborador.id,
            tipo_solicitacao_codigo=tipo.codigo,
            data_referencia=data_ancora,
            vinculo_id=vinculo_id,
            solicitante_usuario_id=solicitacao.solicitante_usuario_id,
            descricao=descricao,
            prazo_em=prazo_em,
            etapa_atual=1,
        )
        # Achado de integracao consertado ao fechar a fase (T15/T16, nao
        # bug de A1 isolado): o PCF §2.7/`app/notificacao/__init__.py`
        # (docstring de A3) ja fixam que "o proprio codigo de A1/A2/A4
        # chama o motor de notificacoes em processo, logo apos publicar o
        # envelope, no mesmo modulo que ele ja possui" -- essa chamada
        # nunca tinha sido adicionada em nenhum dos publicadores de evento
        # desta fase (nenhum resultado para
        # `grep -rn "processar_evento" apps/api/app/workflow`). Import
        # tardio: `app.notificacao` e ownership de A3 (mesmo padrao ja
        # usado por este pacote para `afastamentos.py`, A4).
        from app.notificacao.motor import processar_evento

        await processar_evento(sessao, tenant_id, envelope)

    return solicitacao


async def listar_solicitacoes(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    colaborador_id: UUID | None = None,
    empresa_id: UUID | None = None,
    tipo_solicitacao_id: UUID | None = None,
    categoria: str | None = None,
    status: str | None = None,
    minhas: bool | None = None,
    usuario_atual_id: UUID | None = None,
    de: dt.date | None = None,
    ate: dt.date | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[Solicitacao], esquemas.Paginacao]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO), padrao="criadoEm"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = sa.select(Solicitacao).where(Solicitacao.tenant_id == tenant_id)
    if colaborador_id is not None:
        consulta = consulta.where(Solicitacao.colaborador_id == colaborador_id)
    if empresa_id is not None:
        consulta = consulta.join(Colaborador, Colaborador.id == Solicitacao.colaborador_id).where(
            Colaborador.empresa_id == empresa_id
        )
    if tipo_solicitacao_id is not None:
        consulta = consulta.where(Solicitacao.tipo_solicitacao_id == tipo_solicitacao_id)
    if categoria is not None:
        consulta = consulta.join(
            TipoSolicitacao, TipoSolicitacao.id == Solicitacao.tipo_solicitacao_id
        ).where(TipoSolicitacao.categoria == categoria)
    if status is not None:
        consulta = consulta.where(Solicitacao.status == status)
    if minhas and usuario_atual_id is not None:
        consulta = consulta.where(Solicitacao.solicitante_usuario_id == usuario_atual_id)
    if de is not None:
        consulta = consulta.where(Solicitacao.data_referencia >= de)
    if ate is not None:
        consulta = consulta.where(Solicitacao.data_referencia <= ate)

    campo = _CAMPOS_ORDENACAO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=Solicitacao.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    atributos_por_campo = {
        "criadoEm": "criado_em",
        "prazoEm": "prazo_em",
        "dataReferencia": "data_referencia",
    }
    atributo = atributos_por_campo[ordenacao.campo]
    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        proximo_cursor = codificar_cursor(ordenacao, getattr(ultimo, atributo), ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao


async def cancelar_solicitacao(
    sessao: AsyncSession,
    tenant_id: UUID,
    solicitacao_id: UUID,
    dados: esquemas.CancelamentoRequisicao,
    *,
    usuario_id: UUID | None,
) -> Solicitacao:
    solicitacao = await obter_solicitacao(sessao, solicitacao_id)
    if solicitacao.status not in _STATUS_CANCELAVEIS:
        raise ErroDeAplicacao(
            CODIGO_TRANSICAO_INVALIDA,
            detalhe=(f"Solicitacao em situacao '{solicitacao.status}' nao pode ser cancelada."),
        )

    agora = dt.datetime.now(tz=dt.UTC)
    motivo = (dados.motivo or "").strip() or "Cancelada pelo solicitante."
    solicitacao.status = "cancelada"
    solicitacao.concluida_em = agora
    solicitacao.resultado = motivo
    solicitacao.atualizado_por = usuario_id

    await sessao.execute(
        sa.update(Aprovacao)
        .where(
            Aprovacao.tenant_id == tenant_id,
            Aprovacao.solicitacao_id == solicitacao.id,
            Aprovacao.decisao == "pendente",
        )
        .values(decisao="cancelada", atualizado_por=usuario_id)
    )
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc
    return solicitacao
