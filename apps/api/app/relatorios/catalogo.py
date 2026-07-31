"""Registro de datasets e formato interno do catálogo de relatórios (T2, F11/A1).

Os 24 relatórios do produto são **linhas de dado** em `relatorio_definicoes`
(`schema.sql` §16), nunca 24 rotas HTTP (PCF §2.1). Cada linha aponta para um
`dataset` (string estável, por exemplo `apuracao_dia`) que este módulo resolve
para uma função Python de consulta -- o "dicionário interno" citado pelo PCF.
`app/relatorios/motor.py::executar_dataset` é o único chamador de
`obter_dataset`; `A2`/`A3`/`A4` só chamam `registrar_dataset(...)` dos
próprios módulos (`datasets/operacionais.py`, `datasets/gerenciais.py`,
`datasets/espelho_oficial.py`) -- ninguém além de A1 edita este arquivo
(PCF §5, tabela "compartilhado dentro da fase").

## Contrato de uma função de dataset

```python
def meu_dataset(sessao: AsyncSession, tenant_id: UUID, contexto: ContextoConsulta) -> Select[Any]:
    ...
```

* Recebe a sessão (sob RLS, `app.tenant_id` já publicado por `obter_sessao`),
  o `tenant_id` resolvido e o `ContextoConsulta` (período, escopo
  empresa/unidade/departamento/colaborador, `incluir_inativos`, e os
  `filtros` extras específicos do relatório, já decodificados do JSON da
  query -- ver `motor.py::montar_contexto_consulta`).
* Devolve um `sqlalchemy.Select` **linha a linha** (nunca agrupado): o motor
  genérico (`motor.py`) é quem aplica projeção de colunas e agrupamento em
  cima do que a função devolve -- a função só filtra e junta tabelas, nunca
  faz `GROUP BY` ela mesma (isso duplicaria a responsabilidade do motor e
  quebraria a garantia de "GROUP BY sempre em SQL, nunca em Python" quando um
  cliente pedir agrupamento sobre um relatório que a função já agregou
  sozinha).
* Toda coluna que aparece em `RelatorioDefinicao.colunas_disponiveis`
  **precisa** estar `.label(chave)` no `Select` devolvido, com a `chave`
  IDÊNTICA à declarada no catálogo (é assim que o motor projeta/agrupa por
  nome, sem precisar conhecer o dataset).
* A função aplica ela mesma os filtros de `contexto` que fizerem sentido para
  as tabelas que está lendo (mesmo padrão que `app.workflow.fechamento.
  espelho._montar_conteudo`, F10, já usa para ler `apuracoes_dia` por
  `periodo.data_inicio`/`data_fim`) -- o motor não sabe o nome de coluna de
  período/escopo de cada tabela de domínio, só a função sabe.
* **Toda consulta é SQLAlchemy Core/`select()` parametrizado** -- nunca SQL
  cru montado por concatenação de string (PCF §6/T2), mesmo que `dataset` já
  garanta que o valor não vem do usuário.
* A função **nunca** chama `apurar_dia`/`recalcular_periodo` nem qualquer
  código que dispare o resolvedor de jornada de F3 (proibição 1, PCF §9) --
  só lê o que já foi materializado.

## Formato interno de `colunas_disponiveis` / `filtros_disponiveis` / `agrupamentos`

Decisão de A1 (PCF §2.1 autoriza: "você define o formato interno dessas três
estruturas nesta fase"). O schema do contrato só exige `type: object` -- o
conteúdo é livre. Formato fixado:

```json
{"colunas": [{"chave": "nomeCompleto", "rotulo": "Nome completo", "tipo": "texto",
              "duracao": false}, ...]}
{"filtros":  [{"chave": "departamentoId", "rotulo": "Departamento", "tipo": "uuid"}, ...]}
{"agrupamentos": [{"chave": "departamento", "rotulo": "Departamento"}, ...]}
```

`tipo` de coluna/filtro é um rótulo de apresentação (`texto`, `numero`,
`data`, `booleano`, `uuid`) -- o motor não usa `tipo` para decidir SQL, só a
interface (T4) usa para escolher o widget de filtro certo. `duracao: true` é
o único campo que o motor E os exportadores (A3) tratam com significado
especial: marca uma coluna cujo valor é minutos inteiros, elegível para
`SUM()` no modo agrupado (`motor.py`) e para a conversão para hora decimal em
`converterDecimal=true` (A3, `app/relatorios/exportadores/decimal.py`) --
nunca alterado no dado bruto (PCF §2.5).

`ExemploListaRelatorioDefinicao`/`ExemploRelatorioDefinicao` (frozen desde a
Fase 0 em `openapi.yaml`) ilustram `colunasDisponiveis`/`filtrosDisponiveis`
com listas de strings soltas (sem `rotulo`/`tipo`/`duracao`) -- são exemplos
ILUSTRATIVOS não vinculantes (o próprio PCF §2.1 confirma que o formato "não
é um contrato fixado no openapi.yaml"); o formato mais rico acima é
necessário para o motor genérico decidir o que somar no modo agrupado e para
a conversão decimal saber quais colunas são duração, então A1 optou por ele
em vez do formato mais pobre do exemplo ilustrativo. Registrado como decisão
de julgamento no relatório de fechamento da fase.

`quantidadeRegistros` é uma chave RESERVADA: o motor a acrescenta
automaticamente como `COUNT(*)` no modo agrupado (ver `motor.py`). Nenhum
dataset deve declarar uma coluna com essa chave em `colunas_disponiveis`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from app.core.erros import ErroDeAplicacao

if TYPE_CHECKING:
    from ponto_contracts import RelatorioDefinicao
    from sqlalchemy import Select
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.relatorios.motor import ContextoConsulta

#: Reaproveita o mesmo código do andaime (`worker.filas.CODIGO_NAO_
#: IMPLEMENTADO`/`app.core.erros.CODIGO_NAO_IMPLEMENTADO`): um `dataset`
#: semeado no catálogo mas ainda sem função registrada é, na prática, "esta
#: operação existe e ainda não foi implementada" -- não inventamos código
#: novo (proibição 5, PCF §9).
CODIGO_NAO_IMPLEMENTADO: Final[str] = "PONTO-INT-005"

#: Chave reservada para a contagem sintética que o motor acrescenta no modo
#: agrupado -- ver docstring do módulo.
COLUNA_QUANTIDADE: Final[str] = "quantidadeRegistros"

ConstrutorDataset = Callable[["AsyncSession", UUID, "ContextoConsulta"], "Select[Any]"]

_REGISTRO: dict[str, ConstrutorDataset] = {}


def registrar_dataset(nome: str, funcao: ConstrutorDataset) -> None:
    """Registra a função de consulta de um `dataset`. Chamado uma vez, na
    importação do módulo de datasets de cada agente (`datasets/
    operacionais.py`, `datasets/gerenciais.py`, `datasets/espelho_
    oficial.py`) -- essa importação acontece em `app/routers/relatorios.py`
    (ver comentário no topo do arquivo), para todo dataset estar registrado
    antes da primeira requisição."""
    _REGISTRO[nome] = funcao


def obter_dataset(nome: str) -> ConstrutorDataset:
    """Resolve `dataset` -> função de consulta. `PONTO-INT-005` quando o
    catálogo tem uma linha `relatorio_definicoes.dataset=nome` mas nenhum
    agente registrou a função ainda (esperado durante o desenvolvimento em
    paralelo desta fase; não deveria acontecer depois que A2/A3/A4
    terminarem de registrar os 24)."""
    try:
        return _REGISTRO[nome]
    except KeyError as exc:
        raise ErroDeAplicacao(
            CODIGO_NAO_IMPLEMENTADO,
            detalhe=(
                f"O dataset '{nome}' esta semeado no catalogo mas ainda nao tem funcao de "
                "consulta registrada."
            ),
            contexto_log={"dataset": nome},
        ) from exc


def datasets_registrados() -> frozenset[str]:
    """Nomes de dataset com função registrada -- usado por diagnóstico/teste."""
    return frozenset(_REGISTRO)


def _resetar_registro_para_teste() -> None:
    """Uso exclusivo de teste: isola o registro global entre módulos de teste
    que registram datasets sintéticos. Nunca chamado em código de produção."""
    _REGISTRO.clear()


@dataclass(frozen=True, slots=True)
class ColunaCatalogo:
    """Uma coluna declarada em `RelatorioDefinicao.colunas_disponiveis`."""

    chave: str
    rotulo: str
    tipo: str = "texto"
    duracao: bool = False


@dataclass(frozen=True, slots=True)
class FiltroCatalogo:
    """Um filtro declarado em `RelatorioDefinicao.filtros_disponiveis`."""

    chave: str
    rotulo: str
    tipo: str = "texto"


@dataclass(frozen=True, slots=True)
class AgrupamentoCatalogo:
    """Um agrupamento declarado em `RelatorioDefinicao.agrupamentos`."""

    chave: str
    rotulo: str


def _lista_de(bruto: dict[str, Any] | None, chave_bloco: str) -> list[dict[str, Any]]:
    if not bruto:
        return []
    itens = bruto.get(chave_bloco)
    if not isinstance(itens, list):
        return []
    return [item for item in itens if isinstance(item, dict)]


def colunas_do_catalogo(definicao: RelatorioDefinicao) -> list[ColunaCatalogo]:
    """Lê `colunas_disponiveis` no formato fixado por este módulo."""
    return [
        ColunaCatalogo(
            chave=str(item["chave"]),
            rotulo=str(item.get("rotulo", item["chave"])),
            tipo=str(item.get("tipo", "texto")),
            duracao=bool(item.get("duracao", False)),
        )
        for item in _lista_de(definicao.colunas_disponiveis, "colunas")
        if "chave" in item
    ]


def filtros_do_catalogo(definicao: RelatorioDefinicao) -> list[FiltroCatalogo]:
    """Lê `filtros_disponiveis` no formato fixado por este módulo."""
    return [
        FiltroCatalogo(
            chave=str(item["chave"]),
            rotulo=str(item.get("rotulo", item["chave"])),
            tipo=str(item.get("tipo", "texto")),
        )
        for item in _lista_de(definicao.filtros_disponiveis, "filtros")
        if "chave" in item
    ]


def agrupamentos_do_catalogo(definicao: RelatorioDefinicao) -> list[AgrupamentoCatalogo]:
    """Lê `agrupamentos` no formato fixado por este módulo."""
    return [
        AgrupamentoCatalogo(chave=str(item["chave"]), rotulo=str(item.get("rotulo", item["chave"])))
        for item in _lista_de(definicao.agrupamentos, "agrupamentos")
        if "chave" in item
    ]


def montar_colunas_disponiveis(colunas: Sequence[ColunaCatalogo]) -> dict[str, Any]:
    """Constrói o JSON de `colunas_disponiveis` a partir de `ColunaCatalogo` --
    usado por quem semeia `relatorio_definicoes` (fixture de T1, e o futuro
    mecanismo de provisionamento de tenant, PCF §4)."""
    return {
        "colunas": [
            {"chave": c.chave, "rotulo": c.rotulo, "tipo": c.tipo, "duracao": c.duracao}
            for c in colunas
        ]
    }


def montar_filtros_disponiveis(filtros: Sequence[FiltroCatalogo]) -> dict[str, Any]:
    """Constrói o JSON de `filtros_disponiveis` a partir de `FiltroCatalogo`."""
    return {"filtros": [{"chave": f.chave, "rotulo": f.rotulo, "tipo": f.tipo} for f in filtros]}


def montar_agrupamentos(agrupamentos: Sequence[AgrupamentoCatalogo]) -> dict[str, Any]:
    """Constrói o JSON de `agrupamentos` a partir de `AgrupamentoCatalogo`."""
    return {"agrupamentos": [{"chave": a.chave, "rotulo": a.rotulo} for a in agrupamentos]}
