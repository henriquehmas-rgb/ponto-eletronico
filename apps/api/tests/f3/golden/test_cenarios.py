"""T8: executa os 40+ cenarios do golden dataset contra o resolvedor REAL.

Gate por `pytest.importorskip`: enquanto `app.jornada.resolvedor.servico`
(A3, T7) nao existir, este arquivo e coletado sem erro e todos os testes
aparecem como `SKIPPED` com o motivo abaixo -- nunca como falha, e nunca
como um teste que passa contra um duplo/mock (isso violaria a proibicao 11
do PCF: "nao escreva o golden dataset depois do resolvedor", que aqui vale
ao contrario tambem -- nao finja que o resolvedor passa antes dele existir).
Assim que A1/A2/A3 terminarem, rodar `pytest tests/f3/golden` de novo passa
a executar de verdade, sem precisar editar este arquivo.

Cada cenario chama `resolver_jornada_do_dia` DIRETAMENTE (nunca via HTTP,
conforme T8) e compara, campo a campo, contra `Montagem.esperado`.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from tests.f3.conftest import ContextoF3, aplicar_tenant_teste
from tests.f3.golden.cenarios import CENARIOS
from tests.f3.golden.formato import Cenario

resolvedor = pytest.importorskip(
    "app.jornada.resolvedor.servico",
    reason=(
        "app.jornada.resolvedor.servico ainda nao existe (T7, agente A3). "
        "Os 40+ cenarios do golden dataset (tests/f3/golden/cenarios.py) ja "
        "estao escritos e a massa de dados de cada um ja e validada por "
        "tests/f3/golden/test_massa_smoke.py; falta so o resolvedor para "
        "este arquivo comparar o resultado real campo a campo."
    ),
)

pytestmark = pytest.mark.parametrize("cenario", CENARIOS, ids=[c.nome for c in CENARIOS])


async def test_cenario_do_golden_dataset(
    cenario: Cenario, sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    montagem = await cenario.montar(sessao_f3, contexto_f3)
    # A massa foi inserida nesta mesma transacao (sem commit) -- reafirma
    # `app.tenant_id` por seguranca antes de chamar o resolvedor, do mesmo
    # jeito que `tests/f2/conftest.py` recomenda apos qualquer commit
    # intermediario que um `montar` especifico venha a fazer no futuro.
    await aplicar_tenant_teste(sessao_f3, contexto_f3.tenant_id)

    if montagem.erro_esperado is not None:
        with pytest.raises(ErroDeAplicacao) as excinfo:
            await resolvedor.resolver_jornada_do_dia(
                sessao_f3, contexto_f3.tenant_id, montagem.vinculo_id, montagem.data_consulta
            )
        assert excinfo.value.codigo == montagem.erro_esperado, (
            f"{cenario.nome}: esperava {montagem.erro_esperado}, "
            f"resolvedor levantou {excinfo.value.codigo}"
        )
        return

    resultado = await resolvedor.resolver_jornada_do_dia(
        sessao_f3, contexto_f3.tenant_id, montagem.vinculo_id, montagem.data_consulta
    )
    assert resultado.vinculo_id == montagem.vinculo_id, cenario.nome
    assert resultado.data == montagem.data_consulta, cenario.nome
    for campo, esperado in montagem.esperado.items():
        obtido: Any = getattr(resultado, campo)
        assert (
            obtido == esperado
        ), f"{cenario.nome}: campo '{campo}' esperado {esperado!r}, obtido {obtido!r}"
