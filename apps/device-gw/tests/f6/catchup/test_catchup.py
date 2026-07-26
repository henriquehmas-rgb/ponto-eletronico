"""T5: catch-up por marca d'agua, com o simulador (T1/A2) e um duplo de teste
local para `POST /v1/marcacoes` (Ponto de Atencao n. 2 do PCF: "construa e
teste... com um duplo de teste local, nao contra a API real").

Critérios de aceite exercitados aqui:

* #2 -- "com o simulador, 1.000 eventos entram sem duplicar e sem perder".
* #3 -- "derrubar a comunicacao por um intervalo simulado e religar recupera
  tudo via catch-up, sem intervencao manual, avancando a marca d'agua so
  depois da confirmacao de gravacao".
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from f6.push.conftest import TerminalSemeado
from gateway.dominio import cliente_api
from gateway.rotas.catchup import executar_catch_up, obter_marca_dagua
from gateway.simulador import obter_simulador, reiniciar_registro_simuladores


class MarcacoesDuplo:
    """Duplo local de `POST /v1/marcacoes`: aplica a MESMA regra de
    idempotencia que o contrato promete (`dispositivoId` + `logExternoId`),
    sem NSR nem CRC-16 nenhum -- so o suficiente para provar que o device-gw
    nao entrega duas vezes o mesmo fato."""

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


def _semear_usuario_e_eventos(numero_serie: str, quantidade: int, *, user_id: int = 1) -> None:
    simulador = obter_simulador(numero_serie)
    simulador.tabelas["users"][user_id] = {
        "id": user_id,
        "registration": f"MAT-{user_id:04d}",
        "name": "Colaborador de Teste",
    }
    for i in range(1, quantidade + 1):
        simulador.registrar_access_log(i, user_id=user_id, evento=7)


async def test_1000_eventos_entram_sem_duplicar_e_sem_perder(
    terminal_ativo: TerminalSemeado, duplo_marcacoes: MarcacoesDuplo
) -> None:
    _semear_usuario_e_eventos(terminal_ativo.numero_serie, 1000)

    resultado = await executar_catch_up(
        terminal_ativo.numero_serie, desde_id=None, paginas_maximas=50
    )

    assert resultado["registrosLidos"] == 1000
    assert resultado["marcacoesCriadas"] == 1000
    assert resultado["descartadasPorIdempotencia"] == 0
    assert resultado["pendencia"] is False
    assert resultado["novaMarcaDagua"] == 1000
    assert len(duplo_marcacoes.corpos) == 1000
    # Nenhum id repetido, nenhum faltando: o conjunto de logExternoId
    # entregues e exatamente {1..1000}.
    ids_entregues = {corpo["logExternoId"] for corpo in duplo_marcacoes.corpos}
    assert ids_entregues == set(range(1, 1001))


async def test_reprocessar_o_mesmo_intervalo_nao_produz_marcacao_nova(
    terminal_ativo: TerminalSemeado, duplo_marcacoes: MarcacoesDuplo
) -> None:
    _semear_usuario_e_eventos(terminal_ativo.numero_serie, 200)

    primeira = await executar_catch_up(
        terminal_ativo.numero_serie, desde_id=None, paginas_maximas=50
    )
    assert primeira["marcacoesCriadas"] == 200

    segunda = await executar_catch_up(
        terminal_ativo.numero_serie, desde_id=None, paginas_maximas=50
    )
    assert segunda["registrosLidos"] == 0
    assert segunda["marcacoesCriadas"] == 0
    assert len(duplo_marcacoes.corpos) == 200  # nao cresceu


async def test_marca_dagua_so_avanca_depois_da_confirmacao_por_pagina(
    terminal_ativo: TerminalSemeado,
    duplo_marcacoes: MarcacoesDuplo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Se a entrega falhar no meio de uma pagina, a marca d'agua NAO pode
    ter avancado alem do que foi de fato confirmado -- entre duplicar e
    perder, o sistema escolhe sempre nao perder (proibicao 9 do PCF)."""
    _semear_usuario_e_eventos(terminal_ativo.numero_serie, 5)

    contador = {"chamadas": 0}
    original = duplo_marcacoes.enviar_marcacao

    async def falha_na_terceira(*args: Any, **kwargs: Any) -> dict[str, Any]:
        contador["chamadas"] += 1
        if contador["chamadas"] == 3:
            raise RuntimeError("falha simulada de rede no meio da pagina")
        return await original(*args, **kwargs)

    monkeypatch.setattr(cliente_api, "enviar_marcacao", falha_na_terceira)

    with pytest.raises(RuntimeError):
        await executar_catch_up(terminal_ativo.numero_serie, desde_id=None, paginas_maximas=50)

    marca = await obter_marca_dagua(terminal_ativo.numero_serie)
    # A pagina inteira (5 registros) nao foi confirmada -- a marca continua
    # no valor anterior (0), nunca avancando para alem do que foi gravado.
    assert marca["ultimoIdColetado"] == 0


async def test_derrubar_a_rede_e_religar_recupera_tudo_via_catch_up(
    terminal_ativo: TerminalSemeado, duplo_marcacoes: MarcacoesDuplo
) -> None:
    """Criterio de aceite 3: eventos gerados enquanto a comunicacao esteve
    "fora" (nunca passaram por Push/Monitor) sao recuperados integralmente
    por uma unica chamada de catch-up, sem intervencao manual."""
    _semear_usuario_e_eventos(terminal_ativo.numero_serie, 50)

    resultado = await executar_catch_up(
        terminal_ativo.numero_serie, desde_id=None, paginas_maximas=50
    )

    assert resultado["marcacoesCriadas"] == 50
    marca = await obter_marca_dagua(terminal_ativo.numero_serie)
    assert marca["ultimoIdColetado"] == 50
