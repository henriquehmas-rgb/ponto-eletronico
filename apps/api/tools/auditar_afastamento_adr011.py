"""Auditoria e correcao dos dados ja materializados pelo bug do ADR-011.

Por que existe: ate 2026-08-07, `tipo_dia == 'afastamento'` nunca teve efeito
numerico em `apuracoes_dia` -- a formula `falta_minutos = max(0, previsto -
trabalhado - abono)` rodava igual para todo `tipo_dia` e nada preenchia
`abono_minutos` num dia de afastamento. Qualquer colaborador com afastamento
aprovado (ferias, licenca medica etc.) ficou com falta NAO abonada, desde a
Fase 0. A correcao (`app/apuracao/dominio/servico.py`, commit `2b44875`) vale
para apuracoes NOVAS/reprocessadas -- as linhas ja gravadas continuam erradas
ate serem reprocessadas. Este script encontra essas linhas e, so quando
mandado explicitamente, manda reprocessa-las.

Criterio de identificacao (uniao de tres, ver `detectar`)
--------------------------------------------------------
Uma linha de `apuracoes_dia` e candidata quando `falta_minutos > 0` **e** ao
menos uma das tres condicoes vale:

A. `tipo_dia = 'afastamento'` -- o sintoma exato do bug no caminho "de
   fabrica" (F3: `afastamentos` -> `_afastamento_vigente` -> `tipo_dia`). Esse
   caminho JA gravava o rotulo `'afastamento'` desde a Fase 0; so o numero
   estava errado.
B. Existe `Afastamento` aprovado, integral e nao excluido do MESMO
   colaborador cobrindo a data (exatamente o predicado de
   `app.jornada.resolvedor.servico._afastamento_vigente`, inclusive o casamento
   por `colaborador_id` e nao por `vinculo_id`). Pega o caso em que o
   afastamento foi cadastrado DEPOIS da apuracao do dia e a linha nem chegou a
   receber o rotulo.
C. Existe `Tratamento` de categoria `afastamento` em status
   `aprovado`/`aplicado` para `(tenant, vinculo, data)` -- o caso retroativo
   de F10, o gap original do ADR-011.

**Por que os tres, e nao so o sintoma (A)**: antes da correcao, o `Tratamento`
retroativo (C) nao forcava `tipo_dia` nenhum -- a linha ficava `tipo_dia =
'util'` com a falta cheia. Auditar so por `tipo_dia = 'afastamento'` deixaria
justamente o caso que o ADR-011 documentou de fora. (B) e o complemento
defensivo do mesmo raciocinio para o caminho de F3. Nenhum dos tres produz
falso positivo depois da correcao: com o fix, um dia de afastamento sempre sai
com `abono_minutos = previsto_minutos` e portanto `falta_minutos = 0` -- se
ainda ha falta, a linha e antiga.

Como corrige (`--aplicar`)
--------------------------
Nunca escreve em `apuracoes_dia` diretamente: reaproveita
`app.apuracao.tratamento.recalculo.recalcular_periodo` (que por sua vez chama
`apurar_dia`, grava o diff em `auditoria` via a hash chain de F1, publica
`apuracao.recalculada` e usa o `CacheResolucao` do ADR-010). Os dias
identificados de cada vinculo sao agrupados em BLOCOS CONTIGUOS de datas e
cada bloco vira uma chamada de `recalcular_periodo` -- assim nenhum dia fora
do escopo identificado e tocado e o cache de resolucao do ADR-010 continua
valendo dentro do bloco. Uma transacao (commit) por tenant.

Dia em periodo fechado e pulado pelo proprio `recalcular_periodo`
(`PONTO-APUR-003`); o relatorio final marca essas linhas como NAO CORRIGIDAS.

**Por que o log de antes/depois e deste script, e nao lido de
`ResultadoRecalculo`** (achado real, confirmado contra a VPS em 2026-08-08):
`recalcular_periodo` devolve `dias_alterados = 0` e NAO grava a linha de
`auditoria` do dia, mesmo quando a linha de `apuracoes_dia` mudou de verdade no
banco. Causa: `_estado_anterior` carrega a `ApuracaoDia` na identity map da
sessao ANTES do upsert; o `SELECT` de re-leitura de `_upsert_apuracao_dia`
devolve essa MESMA instancia sem reler as colunas (upsert e Core/DML), entao
`apuracao.hash_entrada` volta com o hash ANTIGO e a comparacao `mudou` da
falso negativo. E o achado ja registrado em `docs/backlog.md` (2026-08-08,
"`_upsert_apuracao_dia` pode devolver um objeto ORM desatualizado", fix
sugerido e nao aplicado: `.execution_options(populate_existing=True)`) --
medido aqui pela primeira vez com `apurar_dia` REAL (os testes de
`tests/f4/tratamento/test_recalculo.py` usam um `apurar_dia` falso e por isso
nunca exercitaram esse caminho). Consequencia pratica: a correcao no dado
acontece, o rastro na hash chain nao. Por isso este script le o antes/depois
por SQL cru direto de `apuracoes_dia` (`_SQL_ESTADO_ATUAL`) e imprime o proprio
log de auditoria linha a linha -- nunca confia no agregado devolvido.

RLS
---
As tabelas tem `FORCE ROW LEVEL SECURITY`. A varredura cross-tenant precisa de
uma conexao que ignore RLS (superusuario/`BYPASSRLS`) OU de `--tenant`
explicito -- com `--tenant`, o script publica `app.tenant_id` e funciona com a
role comum `ponto_app`.

Uso (a partir de `apps/api/`)::

    python tools/auditar_afastamento_adr011.py --dry-run
    python tools/auditar_afastamento_adr011.py --tenant <uuid> --dry-run
    python tools/auditar_afastamento_adr011.py --inicio 2026-01-01 --fim 2026-08-08
    python tools/auditar_afastamento_adr011.py --aplicar --tenant <uuid>

`--dry-run` e o padrao: sem `--aplicar` o script NAO escreve nada. Saida 0
quando nada foi encontrado, 2 quando ha candidatos em modo dry-run (para o
script servir de gate em CI/cron), 1 em erro, 0 depois de `--aplicar` com todas
as linhas corrigidas.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import os
import pathlib
import sys
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

RAIZ_API = pathlib.Path(__file__).resolve().parents[1]
if str(RAIZ_API) not in sys.path:  # pragma: no cover - so no uso como script
    sys.path.insert(0, str(RAIZ_API))

#: Motivo gravado nos metadados de `auditoria` de cada dia recalculado.
MOTIVO_PADRAO = "correcao_adr011_afastamento"

#: Corpo da consulta de deteccao. Ver o bloco "Criterio de identificacao" no
#: docstring do modulo -- as tres condicoes estao aqui, na ordem A, B, C, e
#: cada linha devolvida diz por QUAIS delas entrou (importante para o
#: relatorio: o caminho C e' o que o ADR-011 documentou, o A/B sao o achado
#: maior). `{filtro_tenant}` e o unico trecho montado em Python, e so entre
#: duas alternativas fixas -- nunca recebe valor de usuario (os UUIDs vao como
#: bind param `expanding`). As datas usam `CAST(:x AS date)` e nao `:x::date`
#: de proposito: o regex de bind param de `sqlalchemy.text` e
#: `(?<![:\w$]):([\w$]+)(?![:\w$])` -- um `:` logo depois do nome ANULA o
#: casamento, e `:inicio::date` chegaria literal ao Postgres (erro de sintaxe
#: real, visto na primeira execucao contra a VPS).
_SQL_DETECCAO_MODELO = """
    SELECT
        a.tenant_id,
        a.vinculo_id,
        a.colaborador_id,
        a.data,
        a.tipo_dia,
        a.previsto_minutos,
        a.falta_minutos,
        a.abono_minutos,
        (a.tipo_dia = 'afastamento') AS por_tipo_dia,
        EXISTS (
            SELECT 1 FROM afastamentos af
             WHERE af.tenant_id = a.tenant_id
               AND af.colaborador_id = a.colaborador_id
               AND af.status = 'aprovado'
               AND af.periodo_parcial IS FALSE
               AND af.excluido_em IS NULL
               AND af.data_inicio <= a.data
               AND (af.data_fim IS NULL OR af.data_fim >= a.data)
        ) AS por_afastamento,
        EXISTS (
            SELECT 1 FROM tratamentos t
             JOIN tipos_tratamento tt ON tt.id = t.tipo_tratamento_id
             WHERE t.tenant_id = a.tenant_id
               AND t.vinculo_id = a.vinculo_id
               AND t.data_referencia = a.data
               AND t.status IN ('aprovado', 'aplicado')
               AND tt.categoria = 'afastamento'
        ) AS por_tratamento
      FROM apuracoes_dia a
     WHERE a.falta_minutos > 0
       {filtro_tenant}
       AND (CAST(:inicio AS date) IS NULL OR a.data >= CAST(:inicio AS date))
       AND (CAST(:fim AS date) IS NULL OR a.data <= CAST(:fim AS date))
       AND (
            a.tipo_dia = 'afastamento'
            OR EXISTS (
                SELECT 1 FROM afastamentos af
                 WHERE af.tenant_id = a.tenant_id
                   AND af.colaborador_id = a.colaborador_id
                   AND af.status = 'aprovado'
                   AND af.periodo_parcial IS FALSE
                   AND af.excluido_em IS NULL
                   AND af.data_inicio <= a.data
                   AND (af.data_fim IS NULL OR af.data_fim >= a.data)
            )
            OR EXISTS (
                SELECT 1 FROM tratamentos t
                 JOIN tipos_tratamento tt ON tt.id = t.tipo_tratamento_id
                 WHERE t.tenant_id = a.tenant_id
                   AND t.vinculo_id = a.vinculo_id
                   AND t.data_referencia = a.data
                   AND t.status IN ('aprovado', 'aplicado')
                   AND tt.categoria = 'afastamento'
            )
       )
     ORDER BY a.tenant_id, a.vinculo_id, a.data
"""


def _sql_deteccao(com_tenants: bool) -> sa.TextClause:
    consulta = sa.text(
        _SQL_DETECCAO_MODELO.format(
            filtro_tenant="AND a.tenant_id IN :tenants" if com_tenants else ""
        )
    )
    if com_tenants:
        consulta = consulta.bindparams(sa.bindparam("tenants", expanding=True))
    return consulta


_SQL_ESTADO_ATUAL = sa.text(
    """
    SELECT tipo_dia, falta_minutos, abono_minutos
      FROM apuracoes_dia
     WHERE tenant_id = :tenant_id AND vinculo_id = :vinculo_id AND data = :data
    """
)


@dataclass(frozen=True, slots=True)
class LinhaAfetada:
    """Uma linha de `apuracoes_dia` candidata a reprocessamento."""

    tenant_id: UUID
    vinculo_id: UUID
    colaborador_id: UUID
    data: dt.date
    tipo_dia: str
    previsto_minutos: int
    falta_minutos: int
    abono_minutos: int
    por_tipo_dia: bool
    por_afastamento: bool
    por_tratamento: bool

    @property
    def criterios(self) -> str:
        marcas = [
            "A" if self.por_tipo_dia else "-",
            "B" if self.por_afastamento else "-",
            "C" if self.por_tratamento else "-",
        ]
        return "".join(marcas)


@dataclass(frozen=True, slots=True)
class CorrecaoAplicada:
    """Antes/depois de uma linha efetivamente reprocessada (log de auditoria
    do proprio script -- o diff formal fica em `auditoria`, gravado por
    `recalcular_periodo`)."""

    tenant_id: UUID
    vinculo_id: UUID
    data: dt.date
    tipo_dia_antes: str
    falta_antes: int
    abono_antes: int
    tipo_dia_depois: str
    falta_depois: int
    abono_depois: int

    @property
    def corrigida(self) -> bool:
        return self.falta_depois == 0 and self.falta_antes > 0


@dataclass(slots=True)
class Relatorio:
    """Agregado devolvido por `executar` -- o que o CLI imprime e o que os
    testes inspecionam."""

    linhas: list[LinhaAfetada] = field(default_factory=list)
    correcoes: list[CorrecaoAplicada] = field(default_factory=list)
    dias_ignorados_fechados: int = 0
    aplicado: bool = False

    @property
    def total_falta_minutos(self) -> int:
        return sum(linha.falta_minutos for linha in self.linhas)

    @property
    def tenants(self) -> list[UUID]:
        return sorted({linha.tenant_id for linha in self.linhas}, key=str)

    @property
    def colaboradores(self) -> list[UUID]:
        return sorted({linha.colaborador_id for linha in self.linhas}, key=str)


async def _publicar_tenant(sessao: AsyncSession, tenant_id: UUID | None) -> None:
    """Publica (ou limpa) `app.tenant_id` na SESSAO -- `is_local = false` de
    proposito: `--aplicar` commita uma vez por tenant, e um `SET LOCAL`
    morreria no primeiro commit, deixando o restante do lote sem tenant
    publicado (RLS negaria tudo)."""
    await sessao.execute(
        sa.text("SELECT set_config('app.tenant_id', :tenant, false)"),
        {"tenant": str(tenant_id) if tenant_id is not None else ""},
    )


async def detectar(
    sessao: AsyncSession,
    *,
    tenants: Sequence[UUID] | None = None,
    inicio: dt.date | None = None,
    fim: dt.date | None = None,
) -> list[LinhaAfetada]:
    """Le as linhas candidatas. Somente leitura -- nao escreve nada."""
    parametros: dict[str, object] = {"inicio": inicio, "fim": fim}
    if tenants:
        parametros["tenants"] = list(tenants)
    linhas = (await sessao.execute(_sql_deteccao(bool(tenants)), parametros)).all()
    return [
        LinhaAfetada(
            tenant_id=linha.tenant_id,
            vinculo_id=linha.vinculo_id,
            colaborador_id=linha.colaborador_id,
            data=linha.data,
            tipo_dia=linha.tipo_dia,
            previsto_minutos=linha.previsto_minutos or 0,
            falta_minutos=linha.falta_minutos or 0,
            abono_minutos=linha.abono_minutos or 0,
            por_tipo_dia=linha.por_tipo_dia,
            por_afastamento=linha.por_afastamento,
            por_tratamento=linha.por_tratamento,
        )
        for linha in linhas
    ]


def blocos_contiguos(dias: Iterable[dt.date]) -> list[tuple[dt.date, dt.date]]:
    """Agrupa datas em intervalos `[inicio, fim]` de dias CONSECUTIVOS.

    E o que permite chamar `recalcular_periodo` (que processa o intervalo
    inteiro) sem tocar nenhum dia fora do conjunto identificado, e ainda
    reaproveitando o `CacheResolucao` do ADR-010 dentro de cada bloco."""
    ordenados = sorted(set(dias))
    if not ordenados:
        return []
    blocos: list[tuple[dt.date, dt.date]] = []
    inicio = anterior = ordenados[0]
    for dia in ordenados[1:]:
        if dia == anterior + dt.timedelta(days=1):
            anterior = dia
            continue
        blocos.append((inicio, anterior))
        inicio = anterior = dia
    blocos.append((inicio, anterior))
    return blocos


async def aplicar_correcoes(
    sessao: AsyncSession,
    linhas: Sequence[LinhaAfetada],
    *,
    motivo: str = MOTIVO_PADRAO,
) -> tuple[list[CorrecaoAplicada], int]:
    """Reprocessa APENAS os `(vinculo, dia)` de `linhas`, uma transacao
    (commit) por tenant. Devolve `(correcoes, dias_ignorados_fechados)`."""
    from app.apuracao.tratamento.recalculo import recalcular_periodo

    por_tenant: dict[UUID, dict[UUID, list[LinhaAfetada]]] = defaultdict(lambda: defaultdict(list))
    for linha in linhas:
        por_tenant[linha.tenant_id][linha.vinculo_id].append(linha)

    correcoes: list[CorrecaoAplicada] = []
    ignorados_fechados = 0

    for tenant_id, por_vinculo in por_tenant.items():
        await _publicar_tenant(sessao, tenant_id)
        try:
            for vinculo_id, linhas_do_vinculo in por_vinculo.items():
                for bloco_inicio, bloco_fim in blocos_contiguos(
                    linha.data for linha in linhas_do_vinculo
                ):
                    resultado = await recalcular_periodo(
                        sessao,
                        tenant_id,
                        vinculo_id=vinculo_id,
                        inicio=bloco_inicio,
                        fim=bloco_fim,
                        motivo=motivo,
                    )
                    ignorados_fechados += resultado.dias_ignorados_fechados

                for linha in linhas_do_vinculo:
                    depois = (
                        await sessao.execute(
                            _SQL_ESTADO_ATUAL,
                            {
                                "tenant_id": tenant_id,
                                "vinculo_id": vinculo_id,
                                "data": linha.data,
                            },
                        )
                    ).one()
                    correcoes.append(
                        CorrecaoAplicada(
                            tenant_id=tenant_id,
                            vinculo_id=vinculo_id,
                            data=linha.data,
                            tipo_dia_antes=linha.tipo_dia,
                            falta_antes=linha.falta_minutos,
                            abono_antes=linha.abono_minutos,
                            tipo_dia_depois=depois.tipo_dia,
                            falta_depois=depois.falta_minutos or 0,
                            abono_depois=depois.abono_minutos or 0,
                        )
                    )
            await sessao.commit()
        except Exception:
            await sessao.rollback()
            raise
        await _publicar_tenant(sessao, tenant_id)

    return correcoes, ignorados_fechados


async def executar(
    sessao: AsyncSession,
    *,
    aplicar: bool = False,
    tenants: Sequence[UUID] | None = None,
    inicio: dt.date | None = None,
    fim: dt.date | None = None,
    motivo: str = MOTIVO_PADRAO,
) -> Relatorio:
    """Ponto de entrada unico (usado pelo CLI e pelos testes). Com
    `aplicar=False` (padrao) nao escreve nada."""
    if tenants and len(tenants) == 1:
        # Com um tenant explicito o script funciona sob a role comum
        # `ponto_app` (RLS): publica o tenant antes de qualquer leitura.
        await _publicar_tenant(sessao, tenants[0])

    linhas = await detectar(sessao, tenants=tenants, inicio=inicio, fim=fim)
    relatorio = Relatorio(linhas=linhas)
    if not aplicar or not linhas:
        return relatorio

    correcoes, ignorados = await aplicar_correcoes(sessao, linhas, motivo=motivo)
    relatorio.correcoes = correcoes
    relatorio.dias_ignorados_fechados = ignorados
    relatorio.aplicado = True
    return relatorio


def _mes(data: dt.date) -> str:
    return f"{data.year:04d}-{data.month:02d}"


def imprimir_relatorio(relatorio: Relatorio) -> None:
    linhas = relatorio.linhas
    print(f"linhas candidatas : {len(linhas)}")
    print(f"tenants afetados  : {len(relatorio.tenants)}")
    print(f"colaboradores     : {len(relatorio.colaboradores)}")
    print(f"falta indevida    : {relatorio.total_falta_minutos} minutos")
    if not linhas:
        print("\nNenhuma linha afetada pelo bug do ADR-011 neste banco.")
        return

    por_tenant: dict[UUID, list[LinhaAfetada]] = defaultdict(list)
    for linha in linhas:
        por_tenant[linha.tenant_id].append(linha)

    print("\n-- por tenant --")
    for tenant_id, itens in sorted(por_tenant.items(), key=lambda par: str(par[0])):
        colaboradores = {item.colaborador_id for item in itens}
        minutos = sum(item.falta_minutos for item in itens)
        print(
            f"{tenant_id}  dias={len(itens):6}  "
            f"colaboradores={len(colaboradores):5}  falta={minutos}min"
        )

    print("\n-- por competencia (AAAA-MM) --")
    por_mes: dict[str, list[LinhaAfetada]] = defaultdict(list)
    for linha in linhas:
        por_mes[_mes(linha.data)].append(linha)
    for competencia, itens in sorted(por_mes.items()):
        minutos = sum(item.falta_minutos for item in itens)
        print(f"{competencia}  dias={len(itens):6}  falta={minutos}min")

    print("\n-- por criterio (A=tipo_dia, B=afastamento vigente, C=tratamento retroativo) --")
    por_criterio: dict[str, int] = defaultdict(int)
    for linha in linhas:
        por_criterio[linha.criterios] += 1
    for criterio, quantidade in sorted(por_criterio.items()):
        print(f"{criterio}  dias={quantidade}")

    print("\n-- colaboradores afetados --")
    por_colaborador: dict[UUID, list[LinhaAfetada]] = defaultdict(list)
    for linha in linhas:
        por_colaborador[linha.colaborador_id].append(linha)
    for colaborador_id, itens in sorted(por_colaborador.items(), key=lambda par: str(par[0])):
        minutos = sum(item.falta_minutos for item in itens)
        primeira = min(item.data for item in itens)
        ultima = max(item.data for item in itens)
        print(
            f"{colaborador_id}  dias={len(itens):5}  falta={minutos:7}min  "
            f"periodo={primeira}..{ultima}"
        )

    if not relatorio.aplicado:
        print("\nMODO DRY-RUN: nada foi alterado. Use --aplicar para reprocessar.")
        return

    print("\n-- linhas recalculadas (antes -> depois) --")
    for correcao in relatorio.correcoes:
        marca = "OK " if correcao.corrigida else "NAO"
        print(
            f"{marca} {correcao.tenant_id} {correcao.vinculo_id} {correcao.data} "
            f"tipo_dia={correcao.tipo_dia_antes}->{correcao.tipo_dia_depois} "
            f"falta={correcao.falta_antes}->{correcao.falta_depois} "
            f"abono={correcao.abono_antes}->{correcao.abono_depois}"
        )
    corrigidas = sum(1 for c in relatorio.correcoes if c.corrigida)
    print(
        f"\ncorrigidas: {corrigidas}/{len(relatorio.correcoes)}  "
        f"(dias em periodo fechado, pulados: {relatorio.dias_ignorados_fechados})"
    )


def _analisar_argumentos(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audita (e opcionalmente corrige) apuracoes afetadas pelo bug do ADR-011.",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="DSN SQLAlchemy async (default: variavel de ambiente DATABASE_URL).",
    )
    parser.add_argument(
        "--tenant",
        action="append",
        default=[],
        metavar="UUID",
        help="Restringe a um tenant (repetivel). Sem isto, varre todos -- exige "
        "conexao com BYPASSRLS.",
    )
    parser.add_argument("--inicio", type=dt.date.fromisoformat, help="Data inicial (AAAA-MM-DD).")
    parser.add_argument("--fim", type=dt.date.fromisoformat, help="Data final (AAAA-MM-DD).")
    parser.add_argument("--motivo", default=MOTIVO_PADRAO, help="Motivo gravado na auditoria.")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Somente relata (PADRAO, nao altera nada).",
    )
    grupo.add_argument(
        "--aplicar",
        action="store_true",
        help="Reprocessa de verdade os dias identificados (escreve no banco).",
    )
    return parser.parse_args(argv)


async def _executar_cli(args: argparse.Namespace) -> int:
    if not args.database_url:
        print("Informe --database-url ou defina DATABASE_URL.", file=sys.stderr)
        return 1
    tenants = [UUID(valor) for valor in args.tenant]
    if args.aplicar and not tenants:
        print(
            "--aplicar exige --tenant explicito: correcao em lote cross-tenant "
            "nao e permitida sem delimitar o escopo.",
            file=sys.stderr,
        )
        return 1

    motor = create_async_engine(args.database_url, pool_pre_ping=True)
    fabrica = async_sessionmaker(motor, expire_on_commit=False, autoflush=False)
    try:
        async with fabrica() as sessao:
            relatorio = await executar(
                sessao,
                aplicar=args.aplicar,
                tenants=tenants or None,
                inicio=args.inicio,
                fim=args.fim,
                motivo=args.motivo,
            )
            if not args.aplicar:
                await sessao.rollback()
    finally:
        await motor.dispose()

    imprimir_relatorio(relatorio)
    if not relatorio.linhas:
        return 0
    if not relatorio.aplicado:
        return 2
    return 0 if all(c.corrigida for c in relatorio.correcoes) else 1


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_executar_cli(_analisar_argumentos(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
