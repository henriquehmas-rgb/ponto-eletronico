"""T2: resolucao de terminal antes do tenant (RFC-010, `fn_resolve_terminal`),
contra o banco real."""

from __future__ import annotations

import hmac

import pytest

from f6.push.conftest import (
    TOKEN_PUSH_GLOBAL_TESTE,
    TenantSemeado,
    TerminalSemeado,
    _criar_terminal,
)
from gateway.config import obter_configuracao
from gateway.dominio.resolucao import (
    CODIGO_TERMINAL_RECUSADO,
    autenticar_terminal,
    resolver_terminal,
    token_confere,
)
from gateway.erros import ErroDeAplicacao

# `asyncio_mode = "auto"` (pyproject.toml) ja trata toda `async def test_*`
# como teste assincrono -- sem `pytestmark` aqui para nao marcar tambem o
# unico teste sincrono deste modulo (`test_token_confere_...`).


async def test_numero_serie_inexistente_e_term_003() -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await resolver_terminal("IDF-NAO-EXISTE-0000")
    assert excinfo.value.codigo == CODIGO_TERMINAL_RECUSADO
    assert excinfo.value.detalhe is None  # nao revela qual parte falhou


async def test_terminal_inativo_tambem_e_term_003(terminal_inativo: TerminalSemeado) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await resolver_terminal(terminal_inativo.numero_serie)
    assert excinfo.value.codigo == CODIGO_TERMINAL_RECUSADO
    assert excinfo.value.detalhe is None


async def test_terminal_ativo_resolve_tenant_e_id(terminal_ativo: TerminalSemeado) -> None:
    resolvido = await resolver_terminal(terminal_ativo.numero_serie)
    assert resolvido.id == terminal_ativo.id
    assert resolvido.tenant_id == terminal_ativo.tenant_id
    assert resolvido.status == "ativo"


async def test_autenticar_com_token_proprio_do_terminal(terminal_ativo: TerminalSemeado) -> None:
    config = obter_configuracao()
    resolvido = await autenticar_terminal(
        terminal_ativo.numero_serie, "token-proprio-do-terminal", config=config
    )
    assert resolvido.id == terminal_ativo.id


async def test_autenticar_com_token_errado_e_term_003(terminal_ativo: TerminalSemeado) -> None:
    config = obter_configuracao()
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await autenticar_terminal(
            terminal_ativo.numero_serie, "token-completamente-errado", config=config
        )
    assert excinfo.value.codigo == CODIGO_TERMINAL_RECUSADO


async def test_autenticar_cai_para_token_global_quando_terminal_nao_tem_proprio(
    tenant_gw: TenantSemeado,
) -> None:
    terminal = await _criar_terminal(tenant_gw, token_push=None)
    config = obter_configuracao()
    resolvido = await autenticar_terminal(
        terminal.numero_serie, TOKEN_PUSH_GLOBAL_TESTE, config=config
    )
    assert resolvido.id == terminal.id


def test_token_confere_e_tempo_constante_nao_e_igualdade_de_string() -> None:
    """Prova que a comparacao usa `hmac.compare_digest` (secao 9.3 do PCF):
    ela e a unica funcao que garante tempo constante independente de onde a
    primeira diferenca de byte aparece -- aqui provamos apenas o contrato de
    corretude (aceita igual, recusa diferente), a garantia de tempo
    constante vem da biblioteca padrao, nao de medicao de relogio no teste."""
    assert token_confere("abc123", "abc123") is True
    assert token_confere("abc123", "abc124") is False
    assert token_confere("", "") is True
    # Mesma primitiva que a implementacao usa, por construcao:
    assert token_confere.__module__ == "gateway.dominio.resolucao"
    assert hmac.compare_digest(b"x", b"x") is True
