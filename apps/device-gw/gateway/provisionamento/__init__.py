"""Provisionamento de cadastro no coletor Control iD (T7/T8 do PCF da F6, A2).

Construcao dos comandos `create_objects.fcgi`, `modify_objects.fcgi`,
`destroy_objects.fcgi`, `user_set_image.fcgi` e `execute_actions.fcgi` no
envelope que o modo Push entrega ao terminal (`gateway/rotas/push.py`, A1).
Ver `gateway.provisionamento.comandos` para as funcoes.
"""

from __future__ import annotations

from gateway.provisionamento.comandos import (
    CONTENT_TYPE_JSON,
    CONTENT_TYPE_OCTET_STREAM,
    ComandoTerminal,
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

__all__ = [
    "CONTENT_TYPE_JSON",
    "CONTENT_TYPE_OCTET_STREAM",
    "ComandoTerminal",
    "montar_comando_abrir_porta",
    "montar_comando_atualizar_usuario",
    "montar_comando_criar_usuario",
    "montar_comando_enviar_imagem",
    "montar_comando_executar_acao",
    "montar_comando_liberar_catraca",
    "montar_comando_reiniciar_terminal",
    "montar_comando_remover_usuario",
    "user_id_do_terminal",
]
