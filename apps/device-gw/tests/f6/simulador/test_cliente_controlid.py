"""Testes de `gateway/cliente_controlid.py` (T1 do PCF da F6, agente A2).

Cobre as duas implementacoes da interface `ClienteControlID`: a simulada
(delega a `SimuladorTerminal`, sem rede) e a HTTP real (contra
`httpx.MockTransport`, sem porta de rede nenhuma) -- e a fabrica
`obter_cliente`, que escolhe entre as duas.
"""

from __future__ import annotations

import json

import httpx
import pytest

from gateway.cliente_controlid import (
    ClienteControlIDHttp,
    ClienteControlIDSimulado,
    ConexaoTerminal,
    obter_cliente,
)
from gateway.erros import ErroDeAplicacao
from gateway.simulador import obter_simulador, reiniciar_registro_simuladores


@pytest.fixture(autouse=True)
def _registro_limpo() -> None:
    reiniciar_registro_simuladores()


def _conexao(**overrides: object) -> ConexaoTerminal:
    base = {
        "numero_serie": "IDF-CLIENTE-001",
        "endereco_ip": "10.0.0.5",
        "porta": 80,
        "usuario": "admin",
        "senha": "segredo",
        "timeout_s": 5.0,
    }
    base.update(overrides)
    return ConexaoTerminal(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Fabrica
# ---------------------------------------------------------------------------
def test_obter_cliente_simulador_devolve_implementacao_simulada() -> None:
    cliente = obter_cliente(conexao=_conexao(), simulador=True)
    assert isinstance(cliente, ClienteControlIDSimulado)


def test_obter_cliente_real_devolve_implementacao_http() -> None:
    cliente = obter_cliente(conexao=_conexao(), simulador=False)
    assert isinstance(cliente, ClienteControlIDHttp)


# ---------------------------------------------------------------------------
# Implementacao simulada
# ---------------------------------------------------------------------------
async def test_simulado_login_implicito_e_ciclo_completo_de_usuario() -> None:
    cliente = obter_cliente(conexao=_conexao(), simulador=True)
    mudancas = await cliente.create_objects(
        "users", [{"id": 1, "registration": "MAT-001", "name": "Fulano"}]
    )
    assert mudancas == 1

    registros = await cliente.load_objects("users")
    assert registros == [{"id": 1, "registration": "MAT-001", "name": "Fulano"}]

    await cliente.modify_objects("users", [{"id": 1, "name": "Fulano Atualizado"}])
    registros = await cliente.load_objects("users")
    assert registros[0]["name"] == "Fulano Atualizado"

    removidos = await cliente.destroy_objects(
        "users", [{"object": "users", "field": "id", "operator": "=", "value": 1}]
    )
    assert removidos == 1
    assert await cliente.load_objects("users") == []


async def test_simulado_credencial_errada_vira_ponto_term_003() -> None:
    simulador = obter_simulador("IDF-ERRADO")
    cliente = ClienteControlIDSimulado(simulador, usuario="admin", senha="senha-certa")
    simulador.senha_esperada = "senha-diferente"
    with pytest.raises(ErroDeAplicacao) as exc_info:
        await cliente.login()
    assert exc_info.value.codigo == "PONTO-TERM-003"


async def test_simulado_execute_actions_abre_porta() -> None:
    cliente = obter_cliente(conexao=_conexao(numero_serie="IDF-ACAO-CLI"), simulador=True)
    resultado = await cliente.execute_actions([{"action": "door", "parameters": "door=1"}])
    assert resultado == [{"action": "door", "success": True}]


async def test_simulado_user_set_image_end_to_end() -> None:
    cliente = obter_cliente(conexao=_conexao(numero_serie="IDF-FACE-CLI"), simulador=True)
    await cliente.create_objects("users", [{"id": 9, "registration": "MAT-009", "name": "G"}])
    resultado = await cliente.user_set_image(9, b"bytes-de-foto")
    assert resultado["success"] is True


async def test_simulado_renova_sessao_apos_reiniciar() -> None:
    cliente = obter_cliente(conexao=_conexao(numero_serie="IDF-REBOOT-CLI"), simulador=True)
    await cliente.create_objects("users", [{"id": 1, "registration": "M", "name": "N"}])
    await cliente.reiniciar()
    # A proxima chamada deve renovar a sessao sozinha, sem o chamador perceber.
    registros = await cliente.load_objects("users")
    assert registros == [{"id": 1, "registration": "M", "name": "N"}]


# ---------------------------------------------------------------------------
# Implementacao HTTP real, contra MockTransport (sem rede nenhuma)
# ---------------------------------------------------------------------------
def _handler_feliz(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/login.fcgi":
        return httpx.Response(200, json={"session": "sessao-mock"})
    if request.url.path == "/load_objects.fcgi":
        corpo = json.loads(request.content)
        assert corpo["object"] == "users"
        return httpx.Response(200, json={"users": [{"id": 1, "registration": "MAT-1"}]})
    if request.url.path == "/create_or_modify_objects.fcgi":
        return httpx.Response(200, json={"changes": 1})
    if request.url.path == "/destroy_objects.fcgi":
        return httpx.Response(200, json={"changes": 2})
    if request.url.path == "/execute_actions.fcgi":
        return httpx.Response(200, json={"actions": [{"action": "door", "success": True}]})
    if request.url.path == "/user_set_image.fcgi":
        assert request.headers["content-type"] == "application/octet-stream"
        assert request.content == b"bytes-de-foto"
        return httpx.Response(200, json={"user_id": 7, "success": True})
    if request.url.path == "/reboot.fcgi":
        return httpx.Response(200)
    raise AssertionError(f"caminho inesperado: {request.url.path}")


@pytest.fixture
def cliente_http_mock() -> ClienteControlIDHttp:
    transporte = httpx.MockTransport(_handler_feliz)
    return ClienteControlIDHttp(_conexao(), transporte=transporte)


async def test_http_login_devolve_sessao_do_mock(cliente_http_mock: ClienteControlIDHttp) -> None:
    sessao = await cliente_http_mock.login()
    assert sessao == "sessao-mock"


async def test_http_load_objects_desembrulha_a_chave_do_objeto(
    cliente_http_mock: ClienteControlIDHttp,
) -> None:
    registros = await cliente_http_mock.load_objects("users")
    assert registros == [{"id": 1, "registration": "MAT-1"}]


async def test_http_create_e_modify_objects_falam_com_create_or_modify(
    cliente_http_mock: ClienteControlIDHttp,
) -> None:
    assert await cliente_http_mock.create_objects("users", [{"registration": "MAT-1"}]) == 1
    assert await cliente_http_mock.modify_objects("users", [{"id": 1}]) == 1


async def test_http_destroy_objects(cliente_http_mock: ClienteControlIDHttp) -> None:
    onde = [{"object": "users", "field": "id", "operator": "=", "value": 1}]
    assert await cliente_http_mock.destroy_objects("users", onde) == 2


async def test_http_execute_actions(cliente_http_mock: ClienteControlIDHttp) -> None:
    resultado = await cliente_http_mock.execute_actions(
        [{"action": "door", "parameters": "door=1"}]
    )
    assert resultado == [{"action": "door", "success": True}]


async def test_http_user_set_image_envia_bytes_crus_com_content_type_octet_stream(
    cliente_http_mock: ClienteControlIDHttp,
) -> None:
    resultado = await cliente_http_mock.user_set_image(7, b"bytes-de-foto")
    assert resultado["success"] is True


async def test_http_reiniciar_chama_reboot_fcgi(cliente_http_mock: ClienteControlIDHttp) -> None:
    await cliente_http_mock.reiniciar()


# ---------------------------------------------------------------------------
# Erros de rede/protocolo traduzidos para o catalogo PONTO-TERM-*
# ---------------------------------------------------------------------------
async def test_http_credenciais_recusadas_vira_ponto_term_003() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    cliente = ClienteControlIDHttp(_conexao(), transporte=httpx.MockTransport(handler))
    with pytest.raises(ErroDeAplicacao) as exc_info:
        await cliente.login()
    assert exc_info.value.codigo == "PONTO-TERM-003"


async def test_http_terminal_inacessivel_vira_ponto_term_001() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("recusado", request=request)

    cliente = ClienteControlIDHttp(_conexao(), transporte=httpx.MockTransport(handler))
    with pytest.raises(ErroDeAplicacao) as exc_info:
        await cliente.login()
    assert exc_info.value.codigo == "PONTO-TERM-001"


async def test_http_tempo_esgotado_vira_ponto_term_002() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("tempo esgotado", request=request)

    cliente = ClienteControlIDHttp(_conexao(), transporte=httpx.MockTransport(handler))
    with pytest.raises(ErroDeAplicacao) as exc_info:
        await cliente.login()
    assert exc_info.value.codigo == "PONTO-TERM-002"


async def test_http_resposta_sem_session_vira_ponto_term_005() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"algo": "errado"})

    cliente = ClienteControlIDHttp(_conexao(), transporte=httpx.MockTransport(handler))
    with pytest.raises(ErroDeAplicacao) as exc_info:
        await cliente.login()
    assert exc_info.value.codigo == "PONTO-TERM-005"


async def test_http_sessao_expirada_renova_uma_vez_transparentemente() -> None:
    chamadas: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(request.url.path)
        if request.url.path == "/login.fcgi":
            return httpx.Response(200, json={"session": f"sessao-{len(chamadas)}"})
        if request.url.path == "/load_objects.fcgi" and chamadas.count("/load_objects.fcgi") == 1:
            return httpx.Response(401)
        return httpx.Response(200, json={"users": []})

    cliente = ClienteControlIDHttp(_conexao(), transporte=httpx.MockTransport(handler))
    registros = await cliente.load_objects("users")
    assert registros == []
    # login.fcgi chamado duas vezes: a sessao inicial e a renovacao apos 401.
    assert chamadas.count("/login.fcgi") == 2


def test_conexao_sem_endereco_ip_vira_ponto_term_001() -> None:
    conexao = _conexao(endereco_ip=None)
    cliente = ClienteControlIDHttp(conexao)
    with pytest.raises(ErroDeAplicacao) as exc_info:
        cliente._url("login.fcgi")
    assert exc_info.value.codigo == "PONTO-TERM-001"
