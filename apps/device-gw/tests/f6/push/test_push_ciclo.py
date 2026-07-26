"""T4: modo Push -- obtencao e entrega de comando, ciclo completo."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from f6.push.conftest import TerminalSemeado
from gateway.dominio import cliente_api
from gateway.rotas.push import enfileirar_comando, push_enviar_resultado, push_obter_comando
from gateway.simulador import obter_simulador, reiniciar_registro_simuladores


class MarcacoesDuplo:
    def __init__(self) -> None:
        self.vistas: set[tuple[str, int]] = set()
        self.corpos: list[dict[str, Any]] = []

    async def enviar_marcacao(
        self,
        config: Any,
        *,
        tenant_id: UUID | str,
        corpo: dict[str, Any],
        idempotency_key: str,
        request_id: str | None = None,
        cliente: Any = None,
    ) -> dict[str, Any]:
        chave = (corpo["dispositivoId"], corpo["logExternoId"])
        duplicada = chave in self.vistas
        if not duplicada:
            self.vistas.add(chave)
            self.corpos.append(corpo)
        return {"duplicada": duplicada}


@pytest.fixture(autouse=True)
def _simulador_limpo() -> None:
    reiniciar_registro_simuladores()


@pytest.fixture
def duplo_marcacoes(monkeypatch: pytest.MonkeyPatch) -> MarcacoesDuplo:
    duplo = MarcacoesDuplo()
    monkeypatch.setattr(cliente_api, "enviar_marcacao", duplo.enviar_marcacao)
    return duplo


async def test_terminal_pergunta_e_recebe_exatamente_o_comando_enfileirado(
    terminal_ativo: TerminalSemeado,
) -> None:
    # Primeiro contato do terminal (nenhum comando na fila ainda) -- e o que
    # atualiza `ultimo_contato_em` e evita `PONTO-TERM-004` no proximo
    # `enfileirar_comando` (terminal recem-criado, sem NENHUM contato
    # registrado, conta como mudo por design -- T9/`_terminal_esta_mudo`).
    primeiro_pedido = await push_obter_comando(
        {"numeroSerie": terminal_ativo.numero_serie, "token": "token-proprio-do-terminal"}
    )
    assert primeiro_pedido == {}

    resposta_enfileirar = await enfileirar_comando(
        terminal_ativo.numero_serie,
        {"verb": "POST", "endpoint": "load_objects.fcgi", "body": {"object": "users"}},
    )
    assert resposta_enfileirar["status"] == "enfileirado"

    comando = await push_obter_comando(
        {"numeroSerie": terminal_ativo.numero_serie, "token": "token-proprio-do-terminal"}
    )
    assert comando["verb"] == "POST"
    assert comando["endpoint"] == "load_objects.fcgi"
    assert comando["body"] == {"object": "users"}

    # Some da fila: o proximo pedido nao encontra mais nada.
    proximo = await push_obter_comando(
        {"numeroSerie": terminal_ativo.numero_serie, "token": "token-proprio-do-terminal"}
    )
    assert proximo == {}


async def test_credencial_errada_no_ciclo_push_e_term_003(terminal_ativo: TerminalSemeado) -> None:
    from gateway.erros import ErroDeAplicacao

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await push_obter_comando({"numeroSerie": terminal_ativo.numero_serie, "token": "errado"})
    assert excinfo.value.codigo == "PONTO-TERM-003"


async def test_dois_access_logs_identicos_entregues_duas_vezes_nao_geram_duas_marcacoes(
    terminal_ativo: TerminalSemeado, duplo_marcacoes: MarcacoesDuplo
) -> None:
    """Pronto quando (T4): reapresentacao de resultado nao duplica marcacao."""
    simulador = obter_simulador(terminal_ativo.numero_serie)
    simulador.tabelas["users"][7] = {"id": 7, "registration": "MAT-0007"}
    access_logs = [
        {
            "id": 900,
            "time": 1785062460,
            "event": 7,
            "user_id": 7,
            "portal_id": 1,
            "identifier_id": 0,
        }
    ]

    corpo = {
        "numeroSerie": terminal_ativo.numero_serie,
        "token": "token-proprio-do-terminal",
        "accessLogs": access_logs,
    }

    primeira = await push_enviar_resultado(corpo)
    assert primeira["convertidas"] == 1

    # Reapresentacao do MESMO resultado (equipamento reenvia porque nao
    # recebeu confirmacao a tempo, por exemplo).
    segunda = await push_enviar_resultado(corpo)
    assert segunda["convertidas"] == 1  # o duplo processa de novo (idempotencia e da API real)

    assert len(duplo_marcacoes.corpos) == 1  # so uma marcacao de verdade foi criada
    assert duplo_marcacoes.corpos[0]["logExternoId"] == 900
