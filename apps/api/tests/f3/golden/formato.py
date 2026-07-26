"""Formato do cenario do golden dataset (T1, agente A4).

Este e o "documento" que o PCF da fase (T1) pede: o formato que A1/A2/A3
precisam conseguir ler para saber exatamente o que o resolvedor tem que
produzir. Nao e codigo de calculo -- e dado (mais uma funcao de montagem de
massa, que so faz INSERT, nunca decide nada que o resolvedor deveria
decidir).

Um `Cenario` tem:

* `nome` -- identificador curto e unico (aparece no `pytest -k` e no
  relatorio de cobertura).
* `descricao` -- a massa de dados que o cenario precisa (jornada/escala/
  turno/feriados/afastamentos), em uma frase, para quem le o codigo sem
  executar entender o que esta sendo provado.
* `montar` -- corrotina `(sessao, contexto_f3) -> Montagem`: insere a massa
  (usando os construtores de `_construtores.py`, nunca o ORM dos routers) e
  devolve o vinculo alvo, a data consultada e o resultado esperado campo a
  campo.

`Montagem.esperado` e um `dict[str, Any]` cujas chaves sao exatamente os
nomes de campo (em `snake_case`, populate_by_name) do schema Pydantic
`ResolucaoJornada` gerado em `app/schemas/contrato.py`:
`vinculo_id`, `colaborador_id`, `data`, `tipo_dia`, `jornada_id`,
`jornada_codigo`, `escala_id`, `posicao_ciclo`, `turno_id`, `horario_id`,
`entrada_prevista`, `saida_prevista`, `intervalos_previstos`,
`carga_prevista_minutos`, `cruza_meia_noite`, `feriado_id`, `feriado_nome`,
`afastamento_id`, `fuso_horario`, `origem`.

Um cenario **nao precisa preencher todas as chaves**: `test_cenarios.py`
(T8) so compara os campos presentes em `esperado` contra o atributo
homonimo do `ResolucaoJornada` devolvido pelo resolvedor -- omitir um campo
significa "este cenario nao afirma nada sobre ele" (por exemplo,
`jornada_codigo` e frequentemente omitido nos cenarios de escala pura, onde
o que importa e `escala_id`/`posicao_ciclo`). Os campos que TODO cenario
preenche, por serem o cerne do criterio de aceite 2 do PCF, sao `tipo_dia` e
`origem` (ou, no cenario de `PONTO-APUR-002`, a ausencia de resultado --
ver `Cenario.erro_esperado`).

Exemplo minimo preenchido a mao (o restante dos 40+ vem em `cenarios.py`,
T8): veja `EXEMPLO_JORNADA_FIXA_DIA_UTIL` no fim deste modulo.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from tests.f3.conftest import ContextoF3


@dataclass(frozen=True, slots=True)
class Montagem:
    """O que `Cenario.montar` devolve: o vinculo alvo, a data consultada e o
    resultado esperado campo a campo (ou o codigo de erro esperado, para o
    caso `PONTO-APUR-002`)."""

    vinculo_id: uuid.UUID
    data_consulta: _dt.date
    esperado: dict[str, Any] = field(default_factory=dict)
    #: Preenchido apenas no cenario "sem nenhuma atribuicao vigente": o
    #: resolvedor deve levantar `ErroDeAplicacao` com este `codigo`, nunca
    #: devolver um `ResolucaoJornada` (nem um 500).
    erro_esperado: str | None = None


MontarMassa = Callable[[AsyncSession, "ContextoF3"], Awaitable[Montagem]]


@dataclass(frozen=True, slots=True)
class Cenario:
    """Um cenario trabalhista do golden dataset."""

    nome: str
    descricao: str
    montar: MontarMassa
