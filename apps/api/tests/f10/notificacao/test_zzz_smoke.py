"""Teste de fumaça da fixture local (`conftest.py`) -- confirma que a
semente mínima sobe/derruba sem erro antes dos testes de verdade. Prefixo
`zzz_` só para ordenar por último na coleta alfabética durante o
desenvolvimento local; não afeta a suíte final."""

from __future__ import annotations

import pytest

from tests.f10.notificacao.conftest import ContextoNotificacao


@pytest.mark.asyncio
async def test_fixture_semeia_contexto_minimo(contexto_notificacao: ContextoNotificacao) -> None:
    assert contexto_notificacao.tenant_id is not None
    assert contexto_notificacao.usuario_id is not None
    assert contexto_notificacao.aprovador_usuario_id is not None
    assert contexto_notificacao.solicitacao_id is not None
    assert contexto_notificacao.aprovacao_id is not None
