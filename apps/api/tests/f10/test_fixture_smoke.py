"""Prova de fumaça da fixture compartilhada (T1, "pronto quando": `pytest
apps/api/tests/f10 -q` coleta e a fixture sobe/derruba o banco sem erro)."""

from __future__ import annotations

from tests.f10.conftest import ContextoF10


async def test_contexto_f10_semeia_o_minimo_esperado(contexto_f10: ContextoF10) -> None:
    assert contexto_f10.tenant_id is not None
    assert contexto_f10.vinculo_id is not None
    assert contexto_f10.tipo_solicitacao_codigo.startswith("AJUSTE-")
    assert contexto_f10.periodo_data_fim >= contexto_f10.periodo_data_inicio
