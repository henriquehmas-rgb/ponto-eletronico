"""Motor de expurgo automatico por politica de retencao (F14/A3, PCF secao 5).

Le `politicas_retencao` (`prazo_dias`/`base_legal`/`acao`/`ativo`/
`proxima_execucao_em`, todas ja existentes desde a Fase 0) e aplica
`anonimizar`/`eliminar`/`arquivar` por entidade vencida. Chamado pela tarefa
de worker `expurgo_lgpd` (`apps/worker/worker/tarefas/lgpd.py`), nunca
diretamente pela API -- este e o motor, nao a rota.

**Regra inegociavel: `marcacao` nunca antes do prazo legal (5 anos), e nesta
fase nunca automaticamente nem depois.** Duas camadas de protecao,
deliberadamente redundantes:

1. `PRAZO_MINIMO_MARCACAO_DIAS` (1825 dias = 5 anos, CLT art. 74 e ADR-002)
   e aplicado como PISO mesmo que a politica configurada tenha
   `prazo_dias` menor -- uma politica mal configurada (por engano ou por
   ma-fe de alguem com acesso de admin) jamais antecipa o expurgo.
2. Mesmo apos o prazo minimo cumprido, `_expurgar_marcacao` nunca emite
   UPDATE/DELETE: `marcacoes` e append-only com gatilho de banco que aborta
   as duas operacoes (`trg_marcacoes_bloqueia_update`/`_delete`,
   `packages/contracts/schema.sql`) -- mesmo a role da aplicacao, sem
   superusuario, nao consegue burlar. O expurgo real (drop de particao
   antiga sob supervisao) fica documentado como pendencia (ver
   `docs/backlog.md`), nunca simulado aqui.

`auditoria` recebe a MESMA blindagem (tambem append-only, cadeia de hash,
gatilho bloqueia UPDATE/DELETE/TRUNCATE) pelo mesmo motivo.

Entidades com implementacao REAL nesta fase: `biometria` (expurgo direto do
template cifrado -- rede de seguranca para credencial ja `revogada`/
`reprovada`/`expirada` cujo template nao foi limpo antes, complementar a
`app.lgpd.consentimentos.expurgar_templates_biometricos`, que age no
MOMENTO da revogacao sobre credencial ainda `pendente`/`ativa`), `sessao` e
`notificacao` (delecao generica por coluna de tempo). As demais entidades do
CHECK de
`politicas_retencao.entidade` (`foto_registro`, `documento`, `espelho`,
`afd`, `aej`, `log_acesso`, `fila_offline`, `relatorio_execucao`) sao
reconhecidas mas devolvem `executado=False` com motivo explicito -- nunca
um `KeyError` nem um "sucesso" silencioso sobre nada.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import Biometria, BiometriaTemplate, Notificacao, PoliticaRetencao, Sessao
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "INTERVALO_REEXECUCAO",
    "PRAZO_MINIMO_MARCACAO_DIAS",
    "ResultadoExpurgoPolitica",
    "aplicar_politicas_vencidas",
]

#: 5 anos, CLT art. 74 / ADR-002. Piso absoluto para qualquer politica que
#: mire `entidade='marcacao'`, independente do `prazo_dias` configurado.
PRAZO_MINIMO_MARCACAO_DIAS: Final[int] = 1825

#: Cada politica vencida e reexecutada no dia seguinte -- mesma cadencia de
#: rotina diaria que `worker.scheduler.verificar_banco_horas_vencendo` ja usa
#: para varredura cross-tenant, nunca "so uma vez".
INTERVALO_REEXECUCAO: Final[dt.timedelta] = dt.timedelta(days=1)

#: Entidades append-only protegidas por gatilho de banco -- nunca tocadas
#: por este motor, mesmo com `acao='eliminar'` e prazo vencido.
_ENTIDADES_IMUTAVEIS: Final[frozenset[str]] = frozenset({"marcacao", "auditoria"})

#: Entidades reconhecidas pelo CHECK de `politicas_retencao.entidade` sem
#: implementacao real nesta fase (nenhuma fonte de dado persistida ainda, ou
#: fora do orcamento desta fase -- ver `docs/backlog.md`).
_ENTIDADES_NAO_IMPLEMENTADAS: Final[frozenset[str]] = frozenset(
    {
        "foto_registro",
        "documento",
        "espelho",
        "afd",
        "aej",
        "log_acesso",
        "fila_offline",
        "relatorio_execucao",
    }
)


@dataclass(frozen=True, slots=True)
class ResultadoExpurgoPolitica:
    politica_id: UUID
    entidade: str
    acao: str
    executado: bool
    registros_afetados: int
    motivo: str


async def _expurgar_marcacao_ou_auditoria(
    *, entidade: str, prazo_dias: int
) -> tuple[int, bool, str]:
    """Nunca age sobre `marcacao`/`auditoria`, independente de `agora`: a
    decisao depende so do `prazo_dias` CONFIGURADO na politica (estatico),
    nunca do relogio -- nenhuma quantidade de tempo passado faz este motor
    tocar nessas duas tabelas nesta fase (ver docstring do modulo)."""
    if prazo_dias < PRAZO_MINIMO_MARCACAO_DIAS:
        return (
            0,
            False,
            f"politica com prazo_dias={prazo_dias}, abaixo da guarda legal minima de "
            f"{PRAZO_MINIMO_MARCACAO_DIAS} dias (5 anos, CLT art. 74 / ADR-002) -- ignorada "
            "mesmo que o prazo configurado ja tenha vencido. Nunca antes do prazo legal.",
        )
    return (
        0,
        False,
        f"prazo_dias={prazo_dias} cumpre a guarda legal minima, mas '{entidade}' e append-only "
        "(gatilho de banco bloqueia UPDATE/DELETE/TRUNCATE, ADR-002) -- expurgo automatico nao "
        "implementado nesta fase; exige procedimento manual supervisionado (registrado em "
        "docs/backlog.md).",
    )


async def _expurgar_biometria(
    sessao: AsyncSession, *, tenant_id: UUID, acao: str, cutoff: dt.datetime, agora: dt.datetime
) -> tuple[int, bool, str]:
    if acao == "arquivar":
        return (
            0,
            False,
            "acao 'arquivar' nao suportada para biometria: o vetor cifrado nao pode ser "
            "reduzido a armazenamento frio sem antes decifra-lo (contrario a ADR-006).",
        )

    candidatas = (
        (
            await sessao.execute(
                sa.select(Biometria).where(
                    Biometria.tenant_id == tenant_id,
                    Biometria.status.in_(("revogada", "reprovada", "expirada")),
                    sa.func.coalesce(
                        Biometria.revogada_em, Biometria.atualizado_em, Biometria.criado_em
                    )
                    <= cutoff,
                )
            )
        )
        .scalars()
        .all()
    )
    # Cadastro ATIVO com expurgo programado explicito (`expira_em`, coluna
    # alimentada pela politica de retencao segundo o proprio comentario do
    # schema) tambem entra, independente do "vencido por status".
    programadas = (
        (
            await sessao.execute(
                sa.select(Biometria).where(
                    Biometria.tenant_id == tenant_id,
                    Biometria.expira_em.is_not(None),
                    Biometria.expira_em <= agora,
                )
            )
        )
        .scalars()
        .all()
    )
    vistos: dict[UUID, Biometria] = {b.id: b for b in candidatas}
    for b in programadas:
        vistos.setdefault(b.id, b)

    if not vistos:
        return 0, True, "nenhuma credencial biometrica vencida encontrada."

    total_templates = 0
    afetadas = 0
    for biometria in vistos.values():
        # Delecao DIRETA (nunca via `expurgar_templates_biometricos`, que so
        # atua sobre biometria `pendente`/`ativa` -- aqui a credencial JA
        # esta `revogada`/`reprovada`/`expirada`, ou tem `expira_em`
        # programado: a rotina de retencao e a rede de seguranca para o
        # template que ficou para tras, nao a revogacao em si).
        resultado = await sessao.execute(
            sa.delete(BiometriaTemplate)
            .where(
                BiometriaTemplate.tenant_id == tenant_id,
                BiometriaTemplate.biometria_id == biometria.id,
            )
            .returning(BiometriaTemplate.id)
        )
        removidos = len(resultado.all())
        mudou_status = biometria.status != "expirada"
        if mudou_status:
            biometria.status = "expirada"
        if removidos or mudou_status:
            total_templates += removidos
            afetadas += 1

    verbo = "anonimizada(s)" if acao == "anonimizar" else "eliminada(s)"
    return (
        afetadas,
        True,
        f"{afetadas} credencial(is) biometrica(s) {verbo} ({total_templates} template(s) "
        "removido(s) -- vetor biometrico nao tem forma anonimizada parcial, entao "
        "'anonimizar' e 'eliminar' produzem o mesmo resultado para esta entidade).",
    )


async def _eliminar_por_timestamp(
    sessao: AsyncSession,
    modelo: type[Sessao] | type[Notificacao],
    coluna_tempo: Any,
    *,
    tenant_id: UUID,
    cutoff: dt.datetime,
) -> int:
    resultado = await sessao.execute(
        sa.delete(modelo)
        .where(modelo.tenant_id == tenant_id, coluna_tempo <= cutoff)
        .returning(modelo.id)
    )
    return len(resultado.all())


async def _expurgar_sessao(
    sessao: AsyncSession, *, tenant_id: UUID, acao: str, cutoff: dt.datetime
) -> tuple[int, bool, str]:
    if acao != "eliminar":
        return 0, False, f"acao '{acao}' nao implementada para sessao nesta fase (so 'eliminar')."
    coluna = sa.func.coalesce(Sessao.encerrada_em, Sessao.expira_em)
    removidas = await _eliminar_por_timestamp(
        sessao, Sessao, coluna, tenant_id=tenant_id, cutoff=cutoff
    )
    return removidas, True, f"{removidas} sessao(oes) encerrada(s)/expirada(s) removida(s)."


async def _expurgar_notificacao(
    sessao: AsyncSession, *, tenant_id: UUID, acao: str, cutoff: dt.datetime
) -> tuple[int, bool, str]:
    if acao != "eliminar":
        return (
            0,
            False,
            f"acao '{acao}' nao implementada para notificacao nesta fase (so 'eliminar').",
        )
    removidas = await _eliminar_por_timestamp(
        sessao, Notificacao, Notificacao.criado_em, tenant_id=tenant_id, cutoff=cutoff
    )
    return removidas, True, f"{removidas} notificacao(oes) removida(s)."


async def _despachar(
    sessao: AsyncSession, politica: PoliticaRetencao, *, tenant_id: UUID, agora: dt.datetime
) -> tuple[int, bool, str]:
    cutoff = agora - dt.timedelta(days=politica.prazo_dias)

    if politica.entidade in _ENTIDADES_IMUTAVEIS:
        return await _expurgar_marcacao_ou_auditoria(
            entidade=politica.entidade, prazo_dias=politica.prazo_dias
        )
    if politica.entidade == "biometria":
        return await _expurgar_biometria(
            sessao, tenant_id=tenant_id, acao=politica.acao, cutoff=cutoff, agora=agora
        )
    if politica.entidade == "sessao":
        return await _expurgar_sessao(
            sessao, tenant_id=tenant_id, acao=politica.acao, cutoff=cutoff
        )
    if politica.entidade == "notificacao":
        return await _expurgar_notificacao(
            sessao, tenant_id=tenant_id, acao=politica.acao, cutoff=cutoff
        )
    if politica.entidade in _ENTIDADES_NAO_IMPLEMENTADAS:
        return (
            0,
            False,
            f"entidade '{politica.entidade}' reconhecida pelo catalogo mas sem implementacao "
            "nesta fase (ver docs/backlog.md).",
        )
    return 0, False, f"entidade '{politica.entidade}' desconhecida pelo motor de expurgo."


async def aplicar_politicas_vencidas(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    agora: dt.datetime | None = None,
    politica_id: UUID | None = None,
) -> list[ResultadoExpurgoPolitica]:
    """Aplica toda politica ATIVA e VENCIDA do tenant. `politica_id` restringe
    a uma unica politica (uso de teste/depuracao); por padrao aplica todas as
    vencidas. Sempre atualiza `ultima_execucao_em`/`proxima_execucao_em`/
    `registros_ultima_execucao`, mesmo quando `executado=False` -- a rotina
    RODOU e decidiu nao agir, o que e diferente de nunca ter rodado."""
    momento = agora or dt.datetime.now(tz=dt.UTC)

    consulta = sa.select(PoliticaRetencao).where(
        PoliticaRetencao.tenant_id == tenant_id,
        PoliticaRetencao.ativo.is_(True),
        sa.or_(
            PoliticaRetencao.proxima_execucao_em.is_(None),
            PoliticaRetencao.proxima_execucao_em <= momento,
        ),
    )
    if politica_id is not None:
        consulta = consulta.where(PoliticaRetencao.id == politica_id)

    politicas = (await sessao.execute(consulta)).scalars().all()
    resultados: list[ResultadoExpurgoPolitica] = []
    for politica in politicas:
        afetados, executado, motivo = await _despachar(
            sessao, politica, tenant_id=tenant_id, agora=momento
        )
        politica.ultima_execucao_em = momento
        politica.proxima_execucao_em = momento + INTERVALO_REEXECUCAO
        politica.registros_ultima_execucao = afetados
        await sessao.flush()
        resultados.append(
            ResultadoExpurgoPolitica(
                politica_id=politica.id,
                entidade=politica.entidade,
                acao=politica.acao,
                executado=executado,
                registros_afetados=afetados,
                motivo=motivo,
            )
        )
    return resultados
