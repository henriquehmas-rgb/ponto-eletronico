"""T11: os 47 cenarios do golden dataset da F3 executados contra a
apuracao REAL desta fase (`app.apuracao.dominio.servico.apurar_dia`), nunca
contra um duplo/mock (criterio de aceite 2 do PCF).

`CENARIOS` (`tests.f3.golden.cenarios`, 47 >= 40 exigidos) e `Cenario`/
`Montagem` (`tests.f3.golden.formato`) sao IMPORTADOS, nunca recriados nem
editados -- ownership exclusivo e ja concluido da F3. Cada cenario grava
jornada/escala/turno/horario/feriado/afastamento (nunca marcacao: os
cenarios da F3 nao inserem nenhuma linha em `marcacoes`) e devolve o vinculo
e a data alvo mais o resultado esperado do RESOLVEDOR
(`ResolucaoJornada`) -- o que este teste prova e que `apurar_dia` propaga
corretamente os campos DERIVADOS da resolucao de jornada (tipo de dia,
jornada/escala/turno/horario/feriado/afastamento vigentes e a carga
prevista), com ZERO marcacoes inseridas; nao e um teste de pareamento nem
de calculo de horas trabalhadas (isso e T2/T3/T4, `tests/f4/dominio/**`,
ownership de A1).

Mapeamento de campos (PCF, T11) -- exatamente estes oito, nunca a lista
inteira de `Montagem.esperado` (que tambem carrega campos que soh existem em
`ResolucaoJornada`, como `jornada_codigo`/`posicao_ciclo`/`entrada_prevista`/
`intervalos_previstos`/`cruza_meia_noite`/`feriado_nome`/`fuso_horario`/
`origem` -- nenhum deles tem correspondente em `apuracoes_dia`, e por isso
sao ignorados aqui, nunca comparados por engano contra um atributo
inexistente):

| `Montagem.esperado` (`ResolucaoJornada`) | `contrato.ApuracaoDia`   |
|-------------------------------------------|--------------------------|
| `tipo_dia`                                | `tipo_dia`               |
| `jornada_id`                              | `jornada_id`             |
| `escala_id`                                | `escala_id`              |
| `turno_id`                                 | `turno_id`               |
| `horario_id`                               | `horario_id`             |
| `feriado_id`                               | `feriado_id`             |
| `afastamento_id`                           | `afastamento_id`         |
| `carga_prevista_minutos`                   | `previsto_minutos`       |

Caso `PONTO-APUR-002` (exatamente um cenario do golden dataset,
`sem_regra_vigente`): a F3 documenta que o resolvedor LEVANTA
`ErroDeAplicacao("PONTO-APUR-002", ...)` para este cenario -- mas a decisao
fixada no PCF desta fase (secao 2) e que `apurar_dia` NUNCA propaga essa
excecao ao chamador de lote; em vez disso grava `apuracoes_dia.
tipo_dia == "nao_apurado"`, minutos zerados, `status == "com_ocorrencia"` e
abre uma ocorrencia. Este teste afirma exatamente isso: `apurar_dia` nao
levanta, e o `tipo_dia` devolvido e `"nao_apurado"`.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.dominio.servico import apurar_dia
from app.jornada.resolvedor.servico import CODIGO_SEM_REGRA
from tests.f3.conftest import ContextoF3, aplicar_tenant_teste
from tests.f3.golden.cenarios import CENARIOS
from tests.f3.golden.formato import Cenario

#: Mapeamento campo-a-campo exigido pelo PCF, T11 -- ver docstring do modulo.
#: Chave: nome do campo em `Montagem.esperado` (== atributo de
#: `ResolucaoJornada`). Valor: atributo correspondente em `contrato.
#: ApuracaoDia`. Qualquer chave de `esperado` fora deste mapa e ignorada
#: (nao afirma nada sobre `apuracoes_dia`, por nao ter campo correspondente).
_MAPA_CAMPOS: dict[str, str] = {
    "tipo_dia": "tipo_dia",
    "jornada_id": "jornada_id",
    "escala_id": "escala_id",
    "turno_id": "turno_id",
    "horario_id": "horario_id",
    "feriado_id": "feriado_id",
    "afastamento_id": "afastamento_id",
    "carga_prevista_minutos": "previsto_minutos",
}

assert len(CENARIOS) >= 40, (
    f"golden dataset da F3 encolheu para {len(CENARIOS)} cenarios "
    "(criterio de aceite 2 do PCF exige >= 40); tests/f3/golden/cenarios.py "
    "nao e editado por esta fase -- se isto falhar, o arquivo mudou fora da F3."
)

pytestmark = pytest.mark.parametrize("cenario", CENARIOS, ids=[c.nome for c in CENARIOS])


async def test_cenario_do_golden_dataset_contra_apurar_dia(
    cenario: Cenario, sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    montagem = await cenario.montar(sessao_f3, contexto_f3)
    # A massa foi inserida nesta mesma transacao (sem commit) -- reafirma
    # `app.tenant_id` por seguranca antes de chamar `apurar_dia`, mesma
    # cautela documentada por `tests/f3/golden/test_cenarios.py`.
    await aplicar_tenant_teste(sessao_f3, contexto_f3.tenant_id)

    # Confirma o pre-requisito do enunciado da T11: nenhum cenario do golden
    # dataset insere marcacao -- se algum passar a inserir no futuro, este
    # teste para de provar o que promete provar (propagacao dos campos
    # derivados da jornada, nao do pareamento de marcacoes).
    total_marcacoes = (
        await sessao_f3.execute(
            text(
                "SELECT count(*) FROM marcacoes "
                "WHERE tenant_id = :tenant_id AND vinculo_id = :vinculo_id"
            ),
            {"tenant_id": contexto_f3.tenant_id, "vinculo_id": montagem.vinculo_id},
        )
    ).scalar_one()
    assert total_marcacoes == 0, (
        f"{cenario.nome}: cenario do golden dataset inseriu marcacao "
        "-- violaria a premissa de 'zero marcacoes' da T11."
    )

    if montagem.erro_esperado is not None:
        assert montagem.erro_esperado == CODIGO_SEM_REGRA, (
            f"{cenario.nome}: unico erro_esperado tratado especialmente por "
            f"esta fase e {CODIGO_SEM_REGRA} (PONTO-APUR-002); o golden "
            f"dataset da F3 nao deveria ter outro sem que a T11 seja revista."
        )
        resultado = await apurar_dia(
            sessao_f3, contexto_f3.tenant_id, montagem.vinculo_id, montagem.data_consulta
        )
        assert resultado.tipo_dia == "nao_apurado", (
            f"{cenario.nome}: vinculo sem jornada/escala vigente deveria "
            f"produzir tipo_dia='nao_apurado', obtido {resultado.tipo_dia!r}."
        )
        return

    resultado = await apurar_dia(
        sessao_f3, contexto_f3.tenant_id, montagem.vinculo_id, montagem.data_consulta
    )
    assert resultado.vinculo_id == montagem.vinculo_id, cenario.nome
    assert resultado.data == montagem.data_consulta, cenario.nome

    for campo_resolucao, esperado in montagem.esperado.items():
        campo_apuracao = _MAPA_CAMPOS.get(campo_resolucao)
        if campo_apuracao is None:
            # Campo sem correspondente em `apuracoes_dia` (ver tabela na
            # docstring do modulo) -- este cenario nao afirma nada sobre
            # `apurar_dia` para este campo especifico.
            continue
        obtido: Any = getattr(resultado, campo_apuracao)
        assert obtido == esperado, (
            f"{cenario.nome}: campo '{campo_resolucao}' (ResolucaoJornada) / "
            f"'{campo_apuracao}' (ApuracaoDia) esperado {esperado!r}, "
            f"obtido {obtido!r}"
        )
