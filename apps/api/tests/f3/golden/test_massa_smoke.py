"""Prova de vida da MASSA DE DADOS de cada cenario do golden dataset (T1/T8).

Isto NAO e o teste de aceite do resolvedor (esse e `test_cenarios.py`, que so
roda depois que `app.jornada.resolvedor` existir, T7/A3). Este arquivo prova
uma coisa mais simples e totalmente independente do cronograma dos outros
agentes: que a funcao `montar` de cada cenario consegue inserir sua massa de
dados (jornada/escala/turno/feriados/afastamentos) contra o schema real sem
violar nenhuma constraint -- ou seja, que o golden dataset em si esta bem
formado, campo a campo, antes mesmo de existir codigo para consumi-lo.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.f3.conftest import ContextoF3
from tests.f3.golden.cenarios import CENARIOS
from tests.f3.golden.formato import Cenario

pytestmark = pytest.mark.parametrize("cenario", CENARIOS, ids=[c.nome for c in CENARIOS])


async def test_massa_do_cenario_nao_viola_constraint(
    cenario: Cenario, sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    montagem = await cenario.montar(sessao_f3, contexto_f3)
    assert montagem.vinculo_id in (
        contexto_f3.vinculo_sp_id,
        contexto_f3.vinculo_ba_id,
        contexto_f3.vinculo_sem_unidade_id,
    )
    assert montagem.data_consulta is not None
    assert montagem.erro_esperado is not None or montagem.esperado
