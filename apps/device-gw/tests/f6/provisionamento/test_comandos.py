"""Testes de `gateway/provisionamento/comandos.py` (T8 do PCF da F6, agente A2).

Cobre o criterio de aceite da T8: um comando `user_set_image` montado a
partir de uma imagem de teste nao deixa nenhum arquivo temporario sobreviver
a chamada, e `execute_actions` para abrir porta usa o formato exato de
`parameters` (verificado contra a documentacao publica da Control iD, ver
`gateway/simulador.py`).
"""

from __future__ import annotations

import base64
import builtins
import tempfile
from pathlib import Path

import pytest

from gateway.provisionamento.comandos import (
    CONTENT_TYPE_JSON,
    CONTENT_TYPE_OCTET_STREAM,
    montar_comando_abrir_porta,
    montar_comando_atualizar_usuario,
    montar_comando_criar_usuario,
    montar_comando_enviar_imagem,
    montar_comando_executar_acao,
    montar_comando_liberar_catraca,
    montar_comando_reiniciar_terminal,
    montar_comando_remover_usuario,
    user_id_do_terminal,
)


# ---------------------------------------------------------------------------
# user_set_image -- nunca toca disco
# ---------------------------------------------------------------------------
def test_user_set_image_nunca_abre_arquivo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nenhuma chamada a `open()` (nem via `tempfile`) acontece ao montar o
    comando -- a imagem so existe como `bytes` na memoria do processo."""

    def _open_proibido(*args: object, **kwargs: object) -> object:
        raise AssertionError("montar_comando_enviar_imagem nao deveria abrir nenhum arquivo")

    monkeypatch.setattr(builtins, "open", _open_proibido)
    comando = montar_comando_enviar_imagem(
        user_id=7, imagem=b"bytes-de-foto-fake", timestamp=1785062460
    )
    assert comando["endpoint"] == "user_set_image.fcgi"


def test_user_set_image_nao_deixa_arquivo_temporario_no_diretorio_de_temp() -> None:
    raiz_temp = Path(tempfile.gettempdir())
    antes = set(raiz_temp.iterdir())
    montar_comando_enviar_imagem(user_id=7, imagem=b"bytes-de-foto-fake" * 1000)
    depois = set(raiz_temp.iterdir())
    assert depois == antes, "montar_comando_enviar_imagem deixou arquivo novo em tempdir"


def test_user_set_image_corpo_e_o_base64_da_imagem_com_content_type_octet_stream() -> None:
    imagem = b"\x89PNG-fake-bytes"
    comando = montar_comando_enviar_imagem(user_id=42, imagem=imagem, timestamp=1785062460)
    assert comando["verb"] == "POST"
    assert comando["endpoint"] == "user_set_image.fcgi"
    assert comando["contentType"] == CONTENT_TYPE_OCTET_STREAM
    assert comando["bodyCodificacao"] == "base64"
    assert base64.b64decode(comando["body"]) == imagem
    assert comando["queryString"] == "user_id=42&timestamp=1785062460&match=1"


def test_user_set_image_forcar_duplicata_muda_o_match_na_query_string() -> None:
    comando = montar_comando_enviar_imagem(
        user_id=42, imagem=b"x", timestamp=1785062460, forcar_duplicata=True
    )
    assert "match=0" in comando["queryString"]


# ---------------------------------------------------------------------------
# execute_actions -- formato exato de `parameters`
# ---------------------------------------------------------------------------
def test_abrir_porta_usa_acao_door_e_parametro_door_igual_id() -> None:
    """Verificado contra a documentacao publica da Control iD: a acao chama-se
    `door`, com `parameters` no formato `door=<id>` -- nao `open_door`/
    `door_id` (formato da Fase 0, corrigido nesta tarefa)."""
    comando = montar_comando_abrir_porta(1)
    assert comando["endpoint"] == "execute_actions.fcgi"
    assert comando["contentType"] == CONTENT_TYPE_JSON
    assert comando["body"] == {"actions": [{"action": "door", "parameters": "door=1"}]}


def test_liberar_catraca_usa_acao_catra_e_parametro_allow() -> None:
    comando = montar_comando_liberar_catraca("clockwise")
    assert comando["body"] == {"actions": [{"action": "catra", "parameters": "allow=clockwise"}]}


def test_executar_acao_com_multiplos_parametros_usa_ponto_e_virgula() -> None:
    comando = montar_comando_executar_acao("catra", {"allow": "both", "relay": "1"})
    parametros = comando["body"]["actions"][0]["parameters"]
    assert parametros == "allow=both;relay=1"


def test_reiniciar_terminal_usa_endpoint_proprio_fora_de_execute_actions() -> None:
    """O reinicio real e `POST /reboot.fcgi`, nao uma acao de
    `execute_actions.fcgi` (correcao desta tarefa contra a documentacao
    publica -- ver `gateway/simulador.py`)."""
    comando = montar_comando_reiniciar_terminal()
    assert comando["endpoint"] == "reboot.fcgi"
    assert comando["endpoint"] != "execute_actions.fcgi"


# ---------------------------------------------------------------------------
# create_objects / modify_objects / destroy_objects sobre `users`
# ---------------------------------------------------------------------------
def test_criar_usuario_grava_matricula_em_registration() -> None:
    comando = montar_comando_criar_usuario(user_id=314, matricula="MAT-001", nome="Fulano de Tal")
    assert comando["endpoint"] == "create_objects.fcgi"
    valor = comando["body"]["values"][0]
    assert valor == {"id": 314, "registration": "MAT-001", "name": "Fulano de Tal"}


def test_atualizar_usuario_e_upsert_com_id() -> None:
    comando = montar_comando_atualizar_usuario(user_id=314, matricula="MAT-001", nome="Novo Nome")
    assert comando["endpoint"] == "modify_objects.fcgi"
    assert comando["body"]["values"][0]["id"] == 314


def test_remover_usuario_usa_where_por_id() -> None:
    comando = montar_comando_remover_usuario(user_id=314)
    assert comando["endpoint"] == "destroy_objects.fcgi"
    assert comando["body"]["where"] == [
        {"object": "users", "field": "id", "operator": "=", "value": 314}
    ]


# ---------------------------------------------------------------------------
# user_id_do_terminal -- deterministico e estavel
# ---------------------------------------------------------------------------
def test_user_id_do_terminal_e_deterministico() -> None:
    assert user_id_do_terminal("MAT-001") == user_id_do_terminal("MAT-001")


def test_user_id_do_terminal_difere_entre_matriculas_distintas() -> None:
    assert user_id_do_terminal("MAT-001") != user_id_do_terminal("MAT-002")


def test_user_id_do_terminal_e_sempre_positivo() -> None:
    for matricula in ("MAT-001", "0", "", "colaborador-x-999"):
        assert user_id_do_terminal(matricula) > 0
