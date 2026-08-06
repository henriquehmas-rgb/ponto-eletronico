"""Fila de revisao do gestor (PCF F14 sec 5, A1): marcacoes com
`marcacoes_meta.revisao_status = 'pendente'`.

**Por que nao reaproveita `app.workflow.aprovacoes` (F10).** O PCF pede para
verificar isso primeiro, e a resposta e nao, por tres motivos concretos
verificados por leitura de `packages/contracts/schema.sql`:

1. `aprovacoes` referencia `solicitacoes.id` (`NOT NULL`), e `solicitacoes` e
   SEMPRE iniciada pelo COLABORADOR (`solicitante_usuario_id`, um pedido que
   ele abre) -- o fluxo de score e o oposto: o SISTEMA sinaliza a marcacao
   automaticamente, sem nenhuma acao do colaborador.
2. `tipos_solicitacao.categoria` tem `CHECK` fechado (`ajuste_ponto`, `abono`,
   `justificativa`, `ferias`, `folga`, `compensacao`, `afastamento`,
   `troca_escala`, `hora_extra`, `desbloqueio_dispositivo`, `outro`) sem
   nenhum valor para "revisao antifraude" -- adicionar um exigiria mudar o
   `CHECK` de uma tabela fora do ownership de A1 (so `politicas_registro` foi
   pre-autorizado, PCF F14 secao 6).
3. `marcacoes_meta` JA TEM seu proprio mecanismo de fila, construido pela F5
   desde a Fase 0: `revisao_status`
   (`nao_requer`/`pendente`/`aprovada`/`rejeitada`), `revisado_por`,
   `revisado_em`, `revisao_observacao`, com indice parcial dedicado
   (`ix_marcacoes_meta_revisao ... WHERE revisao_status = 'pendente'`). Nao
   ha mecanismo de fila para construir do zero nem para importar de F10 --
   so falta a camada de servico que LE e DECIDE sobre essas colunas, que e
   este modulo.

**Por que este modulo nao tem rota HTTP ainda.** Ver RFC (`docs/rfc/`,
numero no relatorio da fase): nao existe hoje em `packages/contracts/
openapi.yaml` filtro de `revisaoStatus` em `listarMarcacoes` nem operacao de
escrita para decidir uma revisao -- lacuna de contrato genuina, RFC aberta
como Proposta (protocolo `docs/rfc/README.md` -- so o orquestrador decide).
Enquanto isso, este modulo e funcional e testado por chamada direta (mesmo
padrao de toda a suite de F5 -- `tests/f5/pipeline/test_ingestao.py` chama
`registrar_marcacao` direto, nao via `TestClient`), pronto para virar rota
assim que a decisao sair, sem redesenho.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import Marcacao, MarcacaoMeta
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao

DECISOES_VALIDAS = ("aprovada", "rejeitada")


@dataclass(frozen=True, slots=True)
class ItemFilaRevisao:
    """Uma marcacao pendente de revisao, com o minimo de contexto para o
    gestor decidir sem precisar de uma segunda consulta."""

    marcacao_id: UUID
    colaborador_id: UUID | None
    empresa_id: UUID
    canal: str
    datahora_marcacao: dt.datetime
    nsr: int
    score_confianca: int | None
    classificacao_confianca: str | None
    flags_integridade: dict[str, object]


async def listar_pendentes(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    empresa_id: UUID | None = None,
    limite: int = 50,
    cursor_datahora: dt.datetime | None = None,
) -> list[ItemFilaRevisao]:
    """Marcacoes com `revisao_status='pendente'`, mais recentes primeiro.

    `cursor_datahora`: pagina simples por "antes deste instante" (o indice
    parcial `ix_marcacoes_meta_revisao` cobre `(tenant_id, revisao_status)`,
    a ordenacao por `marcacao_datahora` usa a mesma coluna que a FK composta
    de `marcacoes_meta` ja carrega, sem `JOIN` extra so para ordenar).
    """
    limite = max(1, min(limite, 200))
    consulta = (
        sa.select(
            MarcacaoMeta, Marcacao.canal, Marcacao.nsr, Marcacao.empresa_id, Marcacao.colaborador_id
        )
        .join(
            Marcacao,
            sa.and_(Marcacao.id == MarcacaoMeta.marcacao_id, Marcacao.tenant_id == tenant_id),
        )
        .where(
            MarcacaoMeta.tenant_id == tenant_id,
            MarcacaoMeta.revisao_status == "pendente",
        )
        .order_by(MarcacaoMeta.marcacao_datahora.desc())
        .limit(limite)
    )
    if empresa_id is not None:
        consulta = consulta.where(Marcacao.empresa_id == empresa_id)
    if cursor_datahora is not None:
        consulta = consulta.where(MarcacaoMeta.marcacao_datahora < cursor_datahora)

    linhas = (await sessao.execute(consulta)).all()
    return [
        ItemFilaRevisao(
            marcacao_id=meta.marcacao_id,
            colaborador_id=colaborador_id,
            empresa_id=empresa_id_linha,
            canal=canal,
            datahora_marcacao=meta.marcacao_datahora,
            nsr=nsr,
            score_confianca=meta.score_confianca,
            classificacao_confianca=meta.classificacao_confianca,
            flags_integridade=meta.flags_integridade or {},
        )
        for meta, canal, nsr, empresa_id_linha, colaborador_id in linhas
    ]


async def decidir_revisao(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    marcacao_id: UUID,
    decisao: str,
    observacao: str | None,
    usuario_id: UUID | None,
) -> MarcacaoMeta:
    """Registra a decisao do gestor. NUNCA altera a marcacao em si (ADR-002)
    -- so os campos de revisao de `marcacoes_meta`, que existem exatamente
    para mudar ao longo do tempo (docstring de `obterMetaMarcacao` no
    contrato). Decisao fora de `DECISOES_VALIDAS` ou marcacao sem revisao
    pendente e erro de uso, nao de dado -- levanta `PONTO-VAL-001`/
    `PONTO-CONF-003` (mesmo padrao de `apuracao.tratamento.decisao` para
    "decisao invalida"/"nao esta mais pendente")."""
    if decisao not in DECISOES_VALIDAS:
        raise ErroDeAplicacao(
            "PONTO-VAL-001", detalhe=f"decisao deve ser uma de {DECISOES_VALIDAS}."
        )

    meta = (
        await sessao.execute(
            sa.select(MarcacaoMeta).where(
                MarcacaoMeta.tenant_id == tenant_id, MarcacaoMeta.marcacao_id == marcacao_id
            )
        )
    ).scalar_one_or_none()
    if meta is None:
        raise ErroDeAplicacao("PONTO-REC-001", detalhe="Contexto da marcacao nao encontrado.")
    if meta.revisao_status != "pendente":
        raise ErroDeAplicacao(
            "PONTO-CONF-003",
            detalhe=f"Revisao em status '{meta.revisao_status}' nao pode ser decidida novamente.",
        )

    meta.revisao_status = decisao
    meta.revisado_por = usuario_id
    meta.revisado_em = dt.datetime.now(tz=dt.UTC)
    meta.revisao_observacao = observacao
    meta.atualizado_por = usuario_id
    await sessao.flush()
    return meta
