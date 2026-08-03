"""Smoke test da fixture `contexto_webhooks_f13a3` -- prova que o banco/role
exclusivos sobem e que o tenant/api_client semeados sao visiveis sob RLS."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_contexto_semeado_e_visivel(sessao_f13a3, contexto_webhooks_f13a3):
    from sqlalchemy import text

    linha = (
        await sessao_f13a3.execute(
            text("SELECT nome FROM api_clients WHERE id = :id"),
            {"id": str(contexto_webhooks_f13a3.api_client_id)},
        )
    ).first()
    assert linha is not None
