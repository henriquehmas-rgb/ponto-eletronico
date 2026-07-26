"""Testes de `worker.tarefas.integracoes.sincronizar_terminal` (T7 do PCF da
F6, agente A2).

Vive em `apps/device-gw/tests/f6/provisionamento/` (ownership de A2, PCF F6
secao 5) porque exercita, na mesma suite, tanto o lado do worker
(`worker.tarefas.integracoes`) quanto o vocabulario Control iD que ele produz
(`gateway.simulador`) -- mesmo padrao de F2, cuja cobertura de
`importar_colaboradores` (worker) vive em `apps/api/tests/f2/importadores/`
(ownership de A3), nao em `apps/worker/tests/`.

Banco real (Postgres 16 via tunel SSH, `ponto_f6_a2`, exclusivo de A2 --
ver `conftest.py`). A entrega ao `device-gw` e interceptada por
`httpx.MockTransport` injetado via o parametro `cliente_http` de
`sincronizar_terminal` (adicionado nesta tarefa so para teste, nao muda a
assinatura publica que a F6 fixou): o handler do mock aplica o comando
recebido DIRETO no terminal simulado (`SimuladorTerminal.create_objects`),
provando de ponta a ponta que o comando monta certo e que aplica-lo produz o
efeito esperado -- sem depender de `apps/device-gw/gateway/rotas/push.py`
(A1, T4) estar pronto no momento em que este teste roda.
"""

from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from worker.tarefas.integracoes import (
    reiniciar_engine_para_testes,
    sincronizar_terminal,
    user_id_do_terminal,
)

from f6.provisionamento.conftest import ContextoTerminal, inserir_colaborador
from gateway.simulador import SimuladorTerminal, obter_simulador, reiniciar_registro_simuladores

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _ambiente(sessao_f6: AsyncSession) -> None:
    """Aponta `worker.config.Configuracao` para o mesmo banco de teste desta
    fixture (role de LOGIN, nunca a role administrativa -- RLS de verdade) e
    descarta a engine cacheada entre testes (evento loop novo por teste,
    mesmo motivo de `worker/tarefas/importacoes.py::reiniciar_engine_para_testes`)."""
    import os

    url = sessao_f6.bind.url  # type: ignore[union-attr]
    os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)

    from worker.config import obter_configuracao

    obter_configuracao.cache_clear()
    await reiniciar_engine_para_testes()
    reiniciar_registro_simuladores()


def _terminal_simulado_como_destino(contexto: ContextoTerminal) -> SimuladorTerminal:
    """Terminal simulado que vai "receber" os comandos entregues -- ja com
    sessao aberta, para o handler do mock so precisar aplicar o comando."""
    simulador = obter_simulador(contexto.numero_serie)
    simulador.senha_esperada = "segredo-de-teste"
    simulador.login("admin", "segredo-de-teste")
    return simulador


def _cliente_http_que_entrega_no_simulador(simulador: SimuladorTerminal) -> httpx.AsyncClient:
    """Constroi um `httpx.AsyncClient` cujo transporte aplica, no
    `SimuladorTerminal`, exatamente o comando que
    `sincronizar_terminal` mandaria para
    `POST /interno/terminais/{numeroSerie}/comandos` -- o mesmo envelope que
    `gateway/rotas/push.py::enfileirar_comando` (A1) receberia."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/comandos")
        comando = json.loads(request.content)
        assert comando["verb"] == "POST"
        if comando["endpoint"] == "create_objects.fcgi":
            corpo = comando["body"]
            simulador.create_objects(simulador.sessao_atual or "", corpo["object"], corpo["values"])
        return httpx.Response(202, json={"comandoId": "cmd-1", "status": "enfileirado"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------------------
# Criterio de aceite da T7
# ---------------------------------------------------------------------------
async def test_escopo_usuarios_chega_ao_simulado_como_create_objects_com_registration_correto(
    sessao_f6: AsyncSession, contexto_terminal: ContextoTerminal
) -> None:
    await inserir_colaborador(
        sessao_f6,
        tenant_id=contexto_terminal.tenant_id,
        empresa_id=contexto_terminal.empresa_id,
        matricula="MAT-9001",
        nome="Colaborador de Teste F6A2",
    )
    await sessao_f6.commit()

    simulador = _terminal_simulado_como_destino(contexto_terminal)

    async with _cliente_http_que_entrega_no_simulador(simulador) as cliente_http:
        resultado = await sincronizar_terminal(
            {"job_id": "teste-1"},
            tenant_id=str(contexto_terminal.tenant_id),
            terminal_id=str(contexto_terminal.terminal_id),
            escopo="usuarios",
            cliente_http=cliente_http,
        )

    assert resultado["implementado"] is True
    assert resultado["encontrado"] is True
    assert resultado["usuarios"] == {"total": 1, "enviados": 1, "falhas": 0}

    user_id_esperado = user_id_do_terminal("MAT-9001")
    registros = simulador.load_objects(simulador.sessao_atual or "", "users")["users"]
    assert registros == [
        {"id": user_id_esperado, "registration": "MAT-9001", "name": "Colaborador de Teste F6A2"}
    ]


async def test_dois_colaboradores_geram_dois_comandos_de_create_objects(
    sessao_f6: AsyncSession, contexto_terminal: ContextoTerminal
) -> None:
    await inserir_colaborador(
        sessao_f6,
        tenant_id=contexto_terminal.tenant_id,
        empresa_id=contexto_terminal.empresa_id,
        matricula="MAT-A",
        nome="Colaborador A",
    )
    await inserir_colaborador(
        sessao_f6,
        tenant_id=contexto_terminal.tenant_id,
        empresa_id=contexto_terminal.empresa_id,
        matricula="MAT-B",
        nome="Colaborador B",
    )
    await sessao_f6.commit()

    simulador = _terminal_simulado_como_destino(contexto_terminal)
    async with _cliente_http_que_entrega_no_simulador(simulador) as cliente_http:
        resultado = await sincronizar_terminal(
            {"job_id": "teste-2"},
            tenant_id=str(contexto_terminal.tenant_id),
            terminal_id=str(contexto_terminal.terminal_id),
            escopo="usuarios",
            cliente_http=cliente_http,
        )

    assert resultado["usuarios"] == {"total": 2, "enviados": 2, "falhas": 0}
    registros = simulador.load_objects(simulador.sessao_atual or "", "users")["users"]
    assert {r["registration"] for r in registros} == {"MAT-A", "MAT-B"}


async def test_resposta_devolve_tipo_de_processamento_esperado_pelo_router(
    sessao_f6: AsyncSession, contexto_terminal: ContextoTerminal
) -> None:
    """Nao testa `POST /v1/terminais/{id}/sincronizar` (router e ownership de
    A1, T3) -- confirma so que esta tarefa, do lado do worker, nao impede o
    router de responder `tipo="sincronizacao_terminal"` (RFC-010): o campo e
    montado pelo router a partir da constante fixa do schema, independente do
    resultado desta tarefa."""
    from app.schemas.contrato import Tipo42

    assert Tipo42.sincronizacao_terminal.value == "sincronizacao_terminal"


async def test_terminal_inexistente_nao_levanta_excecao(
    contexto_terminal: ContextoTerminal,
) -> None:
    import uuid

    resultado = await sincronizar_terminal(
        {"job_id": "teste-3"},
        tenant_id=str(contexto_terminal.tenant_id),
        terminal_id=str(uuid.uuid4()),
        escopo="usuarios",
    )
    assert resultado["implementado"] is True
    assert resultado["encontrado"] is False


async def test_escopo_desconhecido_nao_levanta_excecao(
    contexto_terminal: ContextoTerminal,
) -> None:
    resultado = await sincronizar_terminal(
        {"job_id": "teste-4"},
        tenant_id=str(contexto_terminal.tenant_id),
        terminal_id=str(contexto_terminal.terminal_id),
        escopo="escopo-que-nao-existe",
    )
    assert resultado["implementado"] is True
    assert resultado["encontrado"] is True
    assert "erro" in resultado


async def test_escopo_completo_reporta_categorias_sem_fonte_disponivel(
    contexto_terminal: ContextoTerminal,
) -> None:
    simulador = _terminal_simulado_como_destino(contexto_terminal)
    async with _cliente_http_que_entrega_no_simulador(simulador) as cliente_http:
        resultado = await sincronizar_terminal(
            {"job_id": "teste-5"},
            tenant_id=str(contexto_terminal.tenant_id),
            terminal_id=str(contexto_terminal.terminal_id),
            escopo="completo",
            cliente_http=cliente_http,
        )
    assert resultado["usuarios"] == {"total": 0, "enviados": 0, "falhas": 0}
    assert resultado["templates"] is not None
    assert resultado["templates"]["enviados"] == 0
    assert resultado["grupos"] is not None
    assert resultado["regras"] is not None
    assert resultado["horarios"] is not None


async def test_falha_de_entrega_e_contada_sem_abortar_o_lote(
    sessao_f6: AsyncSession, contexto_terminal: ContextoTerminal
) -> None:
    await inserir_colaborador(
        sessao_f6,
        tenant_id=contexto_terminal.tenant_id,
        empresa_id=contexto_terminal.empresa_id,
        matricula="MAT-FALHA",
        nome="Colaborador Falho",
    )
    await sessao_f6.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as cliente_http:
        resultado = await sincronizar_terminal(
            {"job_id": "teste-6"},
            tenant_id=str(contexto_terminal.tenant_id),
            terminal_id=str(contexto_terminal.terminal_id),
            escopo="usuarios",
            cliente_http=cliente_http,
        )

    assert resultado["usuarios"] == {"total": 1, "enviados": 0, "falhas": 1}


async def test_terminal_offline_409_conta_como_entrega_bem_sucedida(
    sessao_f6: AsyncSession, contexto_terminal: ContextoTerminal
) -> None:
    """`409 PONTO-TERM-004` ("terminal mudo, comando enfileirado do mesmo
    jeito") nao e falha de entrega desta tarefa -- o comando entrou na fila e
    sai no proximo ciclo de Push."""
    await inserir_colaborador(
        sessao_f6,
        tenant_id=contexto_terminal.tenant_id,
        empresa_id=contexto_terminal.empresa_id,
        matricula="MAT-MUDO",
        nome="Colaborador Terminal Mudo",
    )
    await sessao_f6.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"codigo": "PONTO-TERM-004"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as cliente_http:
        resultado = await sincronizar_terminal(
            {"job_id": "teste-7"},
            tenant_id=str(contexto_terminal.tenant_id),
            terminal_id=str(contexto_terminal.terminal_id),
            escopo="usuarios",
            cliente_http=cliente_http,
        )

    assert resultado["usuarios"] == {"total": 1, "enviados": 1, "falhas": 0}
