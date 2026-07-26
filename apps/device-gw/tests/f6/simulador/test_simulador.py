"""Testes de `gateway/simulador.py` (T1 do PCF da F6, agente A2).

Cobre o criterio de aceite da T1: `descrever_simulador()` reporta as sete
operacoes `*.fcgi`, e existe um teste que cria um usuario simulado, gera dois
`access_logs` para ele e lista ambos por `id` crescente via a implementacao
simulada de `load_objects` -- sem rede, sem banco, sem thread de servidor.
"""

from __future__ import annotations

import pytest

from gateway.simulador import (
    CredenciaisInvalidas,
    ObjetoDesconhecido,
    SessaoInvalida,
    SimuladorTerminal,
    descrever_simulador,
    gerar_access_log,
    obter_simulador,
    reiniciar_registro_simuladores,
    resposta_login,
)


@pytest.fixture(autouse=True)
def _registro_limpo() -> None:
    reiniciar_registro_simuladores()


# ---------------------------------------------------------------------------
# Criterio de aceite da T1
# ---------------------------------------------------------------------------
def test_descrever_simulador_reporta_as_sete_operacoes_fcgi() -> None:
    descricao = descrever_simulador()
    assert descricao["implementado"] is True
    assert descricao["fase"] == "F6"
    assert set(descricao["endpointsCobertos"]) == {
        "login.fcgi",
        "load_objects.fcgi",
        "execute_actions.fcgi",
        "create_objects.fcgi",
        "modify_objects.fcgi",
        "destroy_objects.fcgi",
        "user_set_image.fcgi",
    }
    assert "access_logs" in descricao["tabelas"]
    assert "users" in descricao["tabelas"]


def test_criar_usuario_gerar_dois_access_logs_e_listar_por_id_crescente() -> None:
    simulador = obter_simulador("IDF-TESTE-000001")
    simulador.senha_esperada = "segredo"
    sessao = simulador.login("admin", "segredo")["session"]

    resultado_criacao = simulador.create_objects(
        sessao, "users", [{"id": 314, "registration": "MAT-001", "name": "Fulano de Tal"}]
    )
    assert resultado_criacao == {"changes": 1}

    simulador.registrar_access_log(41208, user_id=314, evento=7)
    simulador.registrar_access_log(41209, user_id=314, evento=2)

    resultado = simulador.load_objects(sessao, "access_logs", ordenar=["id"])
    registros = resultado["access_logs"]
    assert [r["id"] for r in registros] == [41208, 41209]
    assert all(r["user_id"] == 314 for r in registros)


# ---------------------------------------------------------------------------
# Sessao
# ---------------------------------------------------------------------------
def test_login_com_credencial_errada_recusa() -> None:
    simulador = SimuladorTerminal(numero_serie="IDF-X", senha_esperada="correta")
    with pytest.raises(CredenciaisInvalidas):
        simulador.login("admin", "errada")


def test_operacao_sem_sessao_valida_e_recusada() -> None:
    simulador = SimuladorTerminal(numero_serie="IDF-Y")
    with pytest.raises(SessaoInvalida):
        simulador.load_objects("sessao-invalida", "users")


def test_reboot_invalida_a_sessao_corrente() -> None:
    simulador = SimuladorTerminal(numero_serie="IDF-Z", senha_esperada="segredo")
    sessao = simulador.login("admin", "segredo")["session"]
    simulador.reboot(sessao)
    assert simulador.reinicios == 1
    with pytest.raises(SessaoInvalida):
        simulador.load_objects(sessao, "users")


def test_objeto_desconhecido_e_recusado() -> None:
    simulador = SimuladorTerminal(numero_serie="IDF-W", senha_esperada="segredo")
    sessao = simulador.login("admin", "segredo")["session"]
    with pytest.raises(ObjetoDesconhecido):
        simulador.load_objects(sessao, "tabela_que_nao_existe")


# ---------------------------------------------------------------------------
# create_objects / modify_objects roteiam para o mesmo upsert
# ---------------------------------------------------------------------------
def test_create_e_modify_objects_roteiam_para_o_mesmo_upsert() -> None:
    simulador = SimuladorTerminal(numero_serie="IDF-UPSERT", senha_esperada="segredo")
    sessao = simulador.login("admin", "segredo")["session"]

    simulador.create_objects(sessao, "users", [{"id": 1, "registration": "MAT-1", "name": "A"}])
    simulador.modify_objects(sessao, "users", [{"id": 1, "name": "A Atualizado"}])

    registros = simulador.load_objects(sessao, "users")["users"]
    assert len(registros) == 1
    assert registros[0]["name"] == "A Atualizado"
    assert registros[0]["registration"] == "MAT-1"


def test_create_objects_sem_id_atribui_um_novo() -> None:
    simulador = SimuladorTerminal(numero_serie="IDF-AUTOID", senha_esperada="segredo")
    sessao = simulador.login("admin", "segredo")["session"]
    simulador.create_objects(sessao, "users", [{"registration": "MAT-2", "name": "B"}])
    registros = simulador.load_objects(sessao, "users")["users"]
    assert len(registros) == 1
    assert isinstance(registros[0]["id"], int)


def test_destroy_objects_remove_pelo_where() -> None:
    simulador = SimuladorTerminal(numero_serie="IDF-DESTROY", senha_esperada="segredo")
    sessao = simulador.login("admin", "segredo")["session"]
    simulador.create_objects(sessao, "users", [{"id": 1, "registration": "MAT-1", "name": "A"}])
    resultado = simulador.destroy_objects(
        sessao, "users", [{"object": "users", "field": "id", "operator": "=", "value": 1}]
    )
    assert resultado == {"changes": 1}
    assert simulador.load_objects(sessao, "users")["users"] == []


# ---------------------------------------------------------------------------
# execute_actions e user_set_image
# ---------------------------------------------------------------------------
def test_execute_actions_abre_porta() -> None:
    simulador = SimuladorTerminal(numero_serie="IDF-ACAO", senha_esperada="segredo")
    sessao = simulador.login("admin", "segredo")["session"]
    resultado = simulador.execute_actions(sessao, [{"action": "door", "parameters": "door=1"}])
    assert resultado["actions"] == [{"action": "door", "success": True}]


def test_user_set_image_armazena_face_sem_expor_bytes() -> None:
    simulador = SimuladorTerminal(numero_serie="IDF-FACE", senha_esperada="segredo")
    sessao = simulador.login("admin", "segredo")["session"]
    simulador.create_objects(sessao, "users", [{"id": 7, "registration": "MAT-7", "name": "C"}])

    resultado = simulador.user_set_image(sessao, 7, b"bytes-de-imagem-fake")
    assert resultado["success"] is True
    assert simulador.tem_face_cadastrada(7) is True
    assert "templates" in simulador.tabelas
    assert 7 in simulador.tabelas["templates"]


def test_user_set_image_para_usuario_inexistente_e_recusado() -> None:
    simulador = SimuladorTerminal(numero_serie="IDF-FACE-2", senha_esperada="segredo")
    sessao = simulador.login("admin", "segredo")["session"]
    with pytest.raises(ObjetoDesconhecido):
        simulador.user_set_image(sessao, 999, b"bytes")


# ---------------------------------------------------------------------------
# Registro por numero de serie
# ---------------------------------------------------------------------------
def test_obter_simulador_e_idempotente_por_numero_de_serie() -> None:
    primeiro = obter_simulador("IDF-MESMO")
    segundo = obter_simulador("IDF-MESMO")
    assert primeiro is segundo


def test_gerar_access_log_e_puro_nao_grava_estado() -> None:
    simulador = obter_simulador("IDF-PURO")
    registro = gerar_access_log(1, user_id=1)
    assert registro["id"] == 1
    sessao = simulador.login(simulador.usuario_esperado, simulador.senha_esperada)["session"]
    assert resposta_login(sessao) == {"session": sessao}
    assert simulador.load_objects(sessao, "access_logs")["access_logs"] == []
