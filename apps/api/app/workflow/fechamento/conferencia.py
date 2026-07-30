"""Conferência prévia ao fechamento (T6, F10/A2).

`calcular_conferencia` é a função pura de contagem, usada de dois pontos:

* `criarFechamento` (`servico.py`, T5) chama ANTES de gravar `Fechamento`,
  para decidir se recusa com `PONTO-PER-004` quando há pendência bloqueante
  e `forcar` é falso;
* `conferirFechamento` (este módulo, `conferir_fechamento`) chama sobre um
  `Fechamento` já existente, sem travar nada -- só recomputa e atualiza
  `conferido_em`/`conferido_por`/`status` (`em_andamento` -> `conferido`).

**Decisão fixada pelo PCF (§6, T6) sobre quais códigos entram em
`bloqueantes`:** `marcacao_impar`/`sem_marcacao` (código de `ocorrencias`) e
`nao_apurado` (pseudo-código sintético, não um valor de `ocorrencias.codigo`
-- representa `apuracoesPendentes > 0`) são bloqueantes por padrão; os
demais códigos de `ocorrencias` (`jornada_excedida`, `extra_excedida`,
`intrajornada_suprimida`, e qualquer outro do `CHECK`) são fatos já
corretamente apurados, apenas avisos, e não entram em `bloqueantes`.
`solicitacoesPendentes` é contado e devolvido, mas **não** compõe
`bloqueantes` por si só -- o PCF fixa a lista de bloqueantes só em torno de
ocorrência/apuração, nunca menciona solicitação nessa decisão específica.

**`totalDias`** é o denominador do escopo: `total de vínculos × dias do
período` (não só os dias que já têm linha em `apuracoes_dia`) -- é o que dá
sentido a comparar com `apuracoesPendentes` (o numerador do que falta).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import ApuracaoDia, Fechamento, Ocorrencia, Periodo, Solicitacao
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from app.workflow.fechamento.escopo import dias_do_intervalo, resolver_vinculos_do_escopo

CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"

#: Códigos de `ocorrencias.codigo` que bloqueiam o fechamento por padrão.
CODIGOS_OCORRENCIA_BLOQUEANTES = frozenset({"marcacao_impar", "sem_marcacao"})
#: Pseudo-código, não um valor de `ocorrencias.codigo`: representa
#: `apuracoesPendentes > 0` (dias sem apuração feita ou marcados
#: `nao_apurado`).
CODIGO_NAO_APURADO = "nao_apurado"

#: `ocorrencias.status` que ainda contam como "aberta" para a conferência.
_STATUS_OCORRENCIA_ABERTA = ("aberta", "em_tratamento")
#: `solicitacoes.status` que ainda contam como "pendente".
_STATUS_SOLICITACAO_PENDENTE = ("pendente", "em_aprovacao")


@dataclass(frozen=True, slots=True)
class ParametrosConferencia:
    """Escopo e período a conferir -- forma comum entre `criarFechamento`
    (sem `fechamento_id` ainda) e `conferirFechamento` (com)."""

    periodo: Periodo
    escopo: str
    empresa_id: UUID
    unidade_id: UUID | None = None
    departamento_id: UUID | None = None
    equipe_id: UUID | None = None
    colaborador_id: UUID | None = None


async def calcular_conferencia(
    sessao: AsyncSession,
    tenant_id: UUID,
    parametros: ParametrosConferencia,
    *,
    fechamento_id: UUID | None = None,
) -> esquemas.ConferenciaResposta:
    """Conta pendências no escopo/período, sem gravar nada."""
    periodo = parametros.periodo
    vinculos = await resolver_vinculos_do_escopo(
        sessao,
        tenant_id,
        escopo=parametros.escopo,
        empresa_id=parametros.empresa_id,
        unidade_id=parametros.unidade_id,
        departamento_id=parametros.departamento_id,
        equipe_id=parametros.equipe_id,
        colaborador_id=parametros.colaborador_id,
        periodo_inicio=periodo.data_inicio,
        periodo_fim=periodo.data_fim,
    )
    vinculo_ids = [v.id for v in vinculos]
    colaborador_ids = {v.colaborador_id for v in vinculos}
    dias = dias_do_intervalo(periodo.data_inicio, periodo.data_fim)
    total_dias = len(vinculo_ids) * len(dias)

    if not vinculo_ids:
        return esquemas.ConferenciaResposta(
            fechamentoId=fechamento_id,
            totalColaboradores=0,
            totalDias=0,
            ocorrenciasAbertas=0,
            solicitacoesPendentes=0,
            apuracoesPendentes=0,
            bloqueantes=[],
            podeFechar=True,
            conferidoEm=dt.datetime.now(tz=dt.UTC),
        )

    # --- ocorrencias abertas no escopo/periodo -------------------------------
    consulta_ocorrencias = (
        sa.select(Ocorrencia.codigo, sa.func.count())
        .where(
            Ocorrencia.tenant_id == tenant_id,
            Ocorrencia.colaborador_id.in_(colaborador_ids),
            Ocorrencia.status.in_(_STATUS_OCORRENCIA_ABERTA),
            Ocorrencia.data >= periodo.data_inicio,
            Ocorrencia.data <= periodo.data_fim,
        )
        .group_by(Ocorrencia.codigo)
    )
    # Comprehension em vez de dict() direto de proposito (nao e' C416
    # redundante de verdade): `sessao.execute(...).all()` devolve
    # `Sequence[Row[tuple[str, int]]]`, que o mypy --strict nao aceita como
    # argumento de `dict()` sem `# type: ignore` -- a comprehension
    # desempacota a `Row` e tipa limpo dos dois lados.
    contagem_por_codigo: dict[str, int] = {  # noqa: C416
        codigo: total for codigo, total in (await sessao.execute(consulta_ocorrencias)).all()
    }
    ocorrencias_abertas = sum(contagem_por_codigo.values())

    # --- solicitacoes pendentes no escopo/periodo ---------------------------
    consulta_solicitacoes = sa.select(sa.func.count()).where(
        Solicitacao.tenant_id == tenant_id,
        Solicitacao.colaborador_id.in_(colaborador_ids),
        Solicitacao.status.in_(_STATUS_SOLICITACAO_PENDENTE),
        sa.or_(
            sa.and_(
                Solicitacao.data_referencia.is_not(None),
                Solicitacao.data_referencia >= periodo.data_inicio,
                Solicitacao.data_referencia <= periodo.data_fim,
            ),
            sa.and_(
                Solicitacao.data_inicio.is_not(None),
                Solicitacao.data_inicio <= periodo.data_fim,
                sa.or_(
                    Solicitacao.data_fim.is_(None),
                    Solicitacao.data_fim >= periodo.data_inicio,
                ),
            ),
            sa.and_(
                Solicitacao.data_referencia.is_(None),
                Solicitacao.data_inicio.is_(None),
            ),
        ),
    )
    solicitacoes_pendentes = int((await sessao.execute(consulta_solicitacoes)).scalar_one())

    # --- dias ainda nao apurados ---------------------------------------------
    consulta_apuracoes = sa.select(
        sa.func.count(),
        sa.func.count().filter(ApuracaoDia.tipo_dia == "nao_apurado"),
    ).where(
        ApuracaoDia.tenant_id == tenant_id,
        ApuracaoDia.vinculo_id.in_(vinculo_ids),
        ApuracaoDia.data >= periodo.data_inicio,
        ApuracaoDia.data <= periodo.data_fim,
    )
    linhas_existentes, linhas_nao_apuradas = (await sessao.execute(consulta_apuracoes)).one()
    dias_ausentes = max(total_dias - int(linhas_existentes), 0)
    apuracoes_pendentes = int(linhas_nao_apuradas) + dias_ausentes

    # --- bloqueantes -----------------------------------------------------------
    bloqueantes: list[str] = [
        codigo
        for codigo in sorted(CODIGOS_OCORRENCIA_BLOQUEANTES)
        if contagem_por_codigo.get(codigo)
    ]
    if apuracoes_pendentes > 0:
        bloqueantes.append(CODIGO_NAO_APURADO)

    return esquemas.ConferenciaResposta(
        fechamentoId=fechamento_id,
        totalColaboradores=len(colaborador_ids),
        totalDias=total_dias,
        ocorrenciasAbertas=ocorrencias_abertas,
        solicitacoesPendentes=solicitacoes_pendentes,
        apuracoesPendentes=apuracoes_pendentes,
        bloqueantes=bloqueantes,
        podeFechar=not bloqueantes,
        conferidoEm=dt.datetime.now(tz=dt.UTC),
    )


async def obter_fechamento_com_periodo(
    sessao: AsyncSession, tenant_id: UUID, fechamento_id: UUID
) -> tuple[Fechamento, Periodo]:
    fechamento = await sessao.get(Fechamento, fechamento_id)
    if fechamento is None or fechamento.tenant_id != tenant_id:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Fechamento nao encontrado.")
    periodo = await sessao.get(Periodo, fechamento.periodo_id)
    if periodo is None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Periodo nao encontrado.")
    return fechamento, periodo


async def conferir_fechamento(
    sessao: AsyncSession,
    tenant_id: UUID,
    fechamento_id: UUID,
    *,
    usuario_id: UUID | None,
) -> esquemas.ConferenciaResposta:
    """`POST /v1/fechamentos/{fechamentoId}/conferir` (T6): não trava nada,
    só recomputa e devolve `ConferenciaResposta`, avançando
    `em_andamento` -> `conferido` (idempotente: chamar de novo sem mudança
    de estado produz os mesmos totais, sem duplicar contagem nenhuma --
    a função só lê)."""
    fechamento, periodo = await obter_fechamento_com_periodo(sessao, tenant_id, fechamento_id)
    parametros = ParametrosConferencia(
        periodo=periodo,
        escopo=fechamento.escopo,
        empresa_id=fechamento.empresa_id,
        unidade_id=fechamento.unidade_id,
        departamento_id=fechamento.departamento_id,
    )
    resposta = await calcular_conferencia(
        sessao, tenant_id, parametros, fechamento_id=fechamento_id
    )

    fechamento.total_colaboradores = resposta.total_colaboradores or 0
    fechamento.total_ocorrencias = resposta.ocorrencias_abertas or 0
    fechamento.total_pendencias = (resposta.ocorrencias_abertas or 0) + (
        resposta.solicitacoes_pendentes or 0
    )
    fechamento.conferido_em = resposta.conferido_em
    fechamento.conferido_por = usuario_id
    if fechamento.status == "em_andamento":
        fechamento.status = "conferido"
    await sessao.flush()
    return resposta
