"""Motor genérico de execução de relatórios (T2, F11/A1).

`executar_dataset` é o coração do motor: resolve `RelatorioDefinicao.dataset`
para a função de consulta registrada (`catalogo.obter_dataset`), aplica
filtros compostos (período, escopo empresa/unidade/departamento/colaborador,
mais os filtros extras específicos do relatório), projeta só as colunas
pedidas e aplica agrupamento quando pedido -- **sempre em SQL, nunca em
Python** (PCF §6/T2). É chamado tanto pelo caminho síncrono da API
(`execucao.py`) quanto, futuramente, pela tarefa assíncrona do worker (T6,
fora do escopo de A1 nesta leva -- ver nota no fim deste docstring).

## Como o agrupamento genérico funciona

Uma função de dataset (`catalogo.ConstrutorDataset`) devolve sempre um
`Select` **linha a linha** (nunca `GROUP BY` dentro da própria função -- ver
docstring de `catalogo.py`). Quando o cliente pede `agrupamento`, o motor:

1. Envolve o `Select` bruto como subconsulta (`.subquery()`).
2. Agrupa por essa subconsulta usando a coluna cuja label é a `chave` do
   agrupamento pedido (a função de dataset é responsável por expor essa
   coluna com esse nome -- é o único acoplamento entre dataset e motor no
   modo agrupado).
3. Soma (`SUM`) toda coluna do catálogo marcada `duracao=true` (as únicas
   que fazem sentido agregar automaticamente sem o motor precisar conhecer a
   semântica de cada relatório) e acrescenta `COUNT(*)` como
   `quantidadeRegistros` (`catalogo.COLUNA_QUANTIDADE`).
4. Colunas de texto/uuid não-agrupadas são **omitidas** da saída agrupada --
   comportamento esperado e documentado, não bug: agrupar por natureza
   descarta granularidade que não faz sentido re-exibir por grupo.

## Paginação: cursor por deslocamento, não por chave

Ao contrário de `paginacao.py` (usada pelas listagens reais do catálogo,
`RelatorioDefinicao`/`PreferenciaColunas`, contra tabelas com PK estável), o
resultado de um dataset pode ser uma agregação sem chave primária própria
(o `GROUP BY` acima não tem `id`). Por isso o motor pagina por deslocamento
simples (cursor opaco = deslocamento inteiro), com ordenação determinística
por **todas** as colunas projetadas -- decisão de A1, documentada como
julgamento (ver relatório de fechamento da fase): é o mecanismo mais simples
que funciona uniformemente para dataset agrupado ou não, sem exigir que cada
dataset exponha uma coluna de desempate estável.

**Por que isso não compromete o critério de <60s (PCF §2.3):** o caminho
síncrono só atende relatórios pequenos por construção (PCF §2.3 item 3 --
qualquer intervalo maior força o caminho assíncrono), e o deslocamento nunca
cresce o bastante para o custo de `OFFSET` importar nesse caminho. O caminho
pesado (worker, T6, ownership conjunto de A1+A3, **fora desta leva de T1-T4**)
não deve chamar `executar_dataset` em loop paginando por deslocamento sobre
372 mil linhas -- deve iterar a `Select` bruta devolvida pela função de
dataset diretamente, em streaming (`AsyncSession.stream`/cursor do lado do
servidor, PCF §2.3 item 2), sem paginação HTTP nenhuma. Este módulo não
implementa essa via de streaming: é combinada e escrita em T6, junto com o
exportador de A3, quando ambos os agentes estiverem prontos (ver PCF §5,
linha "compartilhado dentro da fase" para `tarefas/relatorios.py`).

## Proibição 1 (PCF §9)

Nenhuma função deste módulo, nem nenhuma função de dataset registrada,
chama `app.apuracao.dominio.servico.apurar_dia` nem `app.apuracao.
tratamento.recalculo.recalcular_periodo`. Um dia sem linha em
`apuracoes_dia` aparece como está -- vazio, ou com o que houver -- nunca é
calculado sob demanda (mesmo padrão que `app.workflow.fechamento.espelho.
_montar_conteudo`, F10, já usa para `"tipoDia": "nao_apurado"`).
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import func

from app.core.erros import ErroDeAplicacao
from app.relatorios.catalogo import (
    COLUNA_QUANTIDADE,
    ColunaCatalogo,
    agrupamentos_do_catalogo,
    colunas_do_catalogo,
    obter_dataset,
)

if TYPE_CHECKING:
    from ponto_contracts import RelatorioDefinicao
    from sqlalchemy.ext.asyncio import AsyncSession

CODIGO_CONSULTA_INVALIDA: Final[str] = "PONTO-VAL-005"
CODIGO_INTERVALO_INVALIDO: Final[str] = "PONTO-VAL-007"
CODIGO_CURSOR_INCOMPATIVEL: Final[str] = "PONTO-VAL-006"

#: Página do resultado de um dataset quando o cliente não pede `limite`
#: explícito, e teto aceito -- números deliberadamente menores que
#: `paginacao.LIMITE_MAXIMO` (200): um relatório devolve muito mais colunas
#: por linha que uma listagem de recurso simples.
LIMITE_PADRAO: Final[int] = 500
LIMITE_MAXIMO: Final[int] = 5000


@dataclass(frozen=True, slots=True)
class ContextoConsulta:
    """Filtros compostos já normalizados, passados a toda função de dataset.

    **Não inclui `agrupamento`**: o agrupamento é responsabilidade só do
    motor (ver docstring do módulo), a função de dataset nunca precisa saber
    se o resultado dela vai ser agrupado depois.
    """

    tenant_id: UUID
    periodo_id: UUID | None = None
    de: date | None = None
    ate: date | None = None
    empresa_id: UUID | None = None
    unidade_id: UUID | None = None
    departamento_id: UUID | None = None
    colaborador_id: UUID | None = None
    incluir_inativos: bool = False
    filtros: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResultadoRelatorio:
    """Devolvido por `executar_dataset`: uma página do resultado."""

    colunas: list[ColunaCatalogo]
    linhas: list[dict[str, Any]]
    tem_mais: bool
    proximo_cursor: str | None
    total_linhas: int | None = None


def montar_contexto_consulta(
    tenant_id: UUID,
    *,
    periodo_id: UUID | None = None,
    de: date | None = None,
    ate: date | None = None,
    empresa_id: UUID | None = None,
    unidade_id: UUID | None = None,
    departamento_id: UUID | None = None,
    colaborador_id: UUID | None = None,
    incluir_inativos: bool = False,
    filtros_json: str | None = None,
) -> ContextoConsulta:
    """Normaliza os parâmetros crus de `executarRelatorio` num
    `ContextoConsulta`. `PONTO-VAL-007` quando `de > ate`; `PONTO-VAL-005`
    quando `filtros` não é um objeto JSON válido."""
    if de is not None and ate is not None and de > ate:
        raise ErroDeAplicacao(
            CODIGO_INTERVALO_INVALIDO, detalhe="O intervalo 'de' nao pode ser posterior a 'ate'."
        )
    filtros: dict[str, Any] = {}
    if filtros_json:
        try:
            decodificado = json.loads(filtros_json)
        except (ValueError, TypeError) as exc:
            raise ErroDeAplicacao(
                CODIGO_CONSULTA_INVALIDA, detalhe="filtros deve ser um objeto JSON valido."
            ) from exc
        if not isinstance(decodificado, dict):
            raise ErroDeAplicacao(
                CODIGO_CONSULTA_INVALIDA, detalhe="filtros deve ser um objeto JSON valido."
            )
        filtros = decodificado
    return ContextoConsulta(
        tenant_id=tenant_id,
        periodo_id=periodo_id,
        de=de,
        ate=ate,
        empresa_id=empresa_id,
        unidade_id=unidade_id,
        departamento_id=departamento_id,
        colaborador_id=colaborador_id,
        incluir_inativos=incluir_inativos,
        filtros=filtros,
    )


def validar_agrupamento(definicao: RelatorioDefinicao, agrupamento: str | None) -> None:
    """`PONTO-VAL-005` quando `agrupamento` não está entre os declarados em
    `RelatorioDefinicao.agrupamentos`."""
    if agrupamento is None:
        return
    chaves = {a.chave for a in agrupamentos_do_catalogo(definicao)}
    if agrupamento not in chaves:
        raise ErroDeAplicacao(
            CODIGO_CONSULTA_INVALIDA,
            detalhe=f"Agrupamento '{agrupamento}' nao e aceito por este relatorio.",
        )


def _resolver_colunas_pedidas(
    catalogo: Sequence[ColunaCatalogo], colunas_pedidas: Sequence[str] | None
) -> list[ColunaCatalogo]:
    """`PONTO-VAL-005` quando uma chave pedida não está em
    `colunas_disponiveis` (critério de aceite T2)."""
    por_chave = {c.chave: c for c in catalogo}
    if not colunas_pedidas:
        return list(catalogo)
    resolvidas: list[ColunaCatalogo] = []
    for chave in colunas_pedidas:
        coluna = por_chave.get(chave)
        if coluna is None:
            raise ErroDeAplicacao(
                CODIGO_CONSULTA_INVALIDA,
                detalhe=f"Coluna '{chave}' nao esta em colunasDisponiveis deste relatorio.",
            )
        resolvidas.append(coluna)
    return resolvidas


def normalizar_limite(limite: int | None) -> int:
    if limite is None:
        return LIMITE_PADRAO
    if not (1 <= limite <= LIMITE_MAXIMO):
        raise ErroDeAplicacao(
            CODIGO_CONSULTA_INVALIDA, detalhe=f"limite deve estar entre 1 e {LIMITE_MAXIMO}."
        )
    return limite


def _codificar_cursor(deslocamento: int) -> str:
    bruto = json.dumps({"o": deslocamento}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(bruto).decode("ascii").rstrip("=")


def _decodificar_cursor(cursor: str) -> int:
    try:
        preenchido = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(preenchido.encode("ascii")))
        deslocamento = int(payload["o"])
    except (binascii.Error, ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
        raise ErroDeAplicacao(CODIGO_CURSOR_INCOMPATIVEL, detalhe="Cursor ilegivel.") from exc
    if deslocamento < 0:
        raise ErroDeAplicacao(CODIGO_CURSOR_INCOMPATIVEL, detalhe="Cursor ilegivel.")
    return deslocamento


async def executar_dataset(
    sessao: AsyncSession,
    tenant_id: UUID,
    definicao: RelatorioDefinicao,
    *,
    filtros: ContextoConsulta,
    colunas: Sequence[str] | None = None,
    agrupamento: str | None = None,
    cursor: str | None = None,
    limite: int | None = None,
) -> ResultadoRelatorio:
    """Assinatura fixada pelo PCF F11 §4. Resolve `definicao.dataset` no
    catálogo, aplica projeção de colunas e agrupamento (sempre em SQL) e
    devolve uma página do resultado."""
    validar_agrupamento(definicao, agrupamento)
    catalogo = colunas_do_catalogo(definicao)
    limite_efetivo = normalizar_limite(limite)
    deslocamento = _decodificar_cursor(cursor) if cursor else 0

    construtor = obter_dataset(definicao.dataset)
    bruta = construtor(sessao, tenant_id, filtros)
    sub = bruta.subquery()

    if agrupamento is not None:
        colunas_saida, consulta = _montar_consulta_agrupada(sub, catalogo, colunas, agrupamento)
    else:
        colunas_resolvidas = _resolver_colunas_pedidas(catalogo, colunas)
        colunas_saida = colunas_resolvidas
        projecao = [sub.c[c.chave] for c in colunas_resolvidas]
        consulta = sa.select(*projecao).select_from(sub)

    # Ordenação determinística por todas as colunas projetadas -- ver
    # docstring do módulo ("Paginação: cursor por deslocamento").
    consulta = consulta.order_by(*[sa.asc(coluna) for coluna in consulta.selected_columns])
    consulta = consulta.offset(deslocamento).limit(limite_efetivo + 1)

    resultado = await sessao.execute(consulta)
    linhas_brutas = resultado.mappings().all()
    tem_mais = len(linhas_brutas) > limite_efetivo
    linhas = [dict(linha) for linha in linhas_brutas[:limite_efetivo]]

    proximo_cursor = _codificar_cursor(deslocamento + limite_efetivo) if tem_mais else None
    total_linhas = None if tem_mais else deslocamento + len(linhas)

    return ResultadoRelatorio(
        colunas=colunas_saida,
        linhas=linhas,
        tem_mais=tem_mais,
        proximo_cursor=proximo_cursor,
        total_linhas=total_linhas,
    )


def _montar_consulta_agrupada(
    sub: Any,
    catalogo: Sequence[ColunaCatalogo],
    colunas_pedidas: Sequence[str] | None,
    agrupamento: str,
) -> tuple[list[ColunaCatalogo], Any]:
    """Constrói a consulta `GROUP BY` genérica -- ver docstring do módulo."""
    coluna_grupo = sub.c[agrupamento]
    colunas_duracao = [c for c in catalogo if c.duracao]
    if colunas_pedidas:
        pedidas = set(colunas_pedidas)
        colunas_duracao = [c for c in colunas_duracao if c.chave in pedidas]

    projecao: list[Any] = [coluna_grupo.label(agrupamento)]
    colunas_saida = [
        next(
            (c for c in catalogo if c.chave == agrupamento),
            ColunaCatalogo(chave=agrupamento, rotulo=agrupamento, tipo="texto", duracao=False),
        )
    ]
    for coluna in colunas_duracao:
        projecao.append(func.sum(sub.c[coluna.chave]).label(coluna.chave))
        colunas_saida.append(coluna)

    projecao.append(func.count().label(COLUNA_QUANTIDADE))
    colunas_saida.append(
        ColunaCatalogo(chave=COLUNA_QUANTIDADE, rotulo="Quantidade de registros", tipo="numero")
    )

    consulta = sa.select(*projecao).select_from(sub).group_by(coluna_grupo)
    return colunas_saida, consulta
