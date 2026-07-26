"""Construcao dos comandos Control iD do modo Push (T7/T8 do PCF da F6, A2).

Cada `montar_comando_*` monta o ENVELOPE que `POST
/interno/terminais/{numeroSerie}/comandos` espera --
`{verb, endpoint, contentType, queryString, body}`, formato documentado em
`gateway/rotas/push.py::enfileirar_comando` (A1) -- pronto para ser
enfileirado e entregue ao equipamento no proximo ciclo de Push.

**Este modulo e PURO.** Nenhuma funcao aqui fala HTTP, abre sessao, toca
Redis ou grava arquivo -- sao traducoes de uma intencao de dominio (criar
usuario, enviar face, abrir porta) para o vocabulario `*.fcgi` do fabricante.
Quem entrega de fato ao `device-gw` e `apps/worker/worker/tarefas/
integracoes.py::sincronizar_terminal` (T7); quem entrega de verdade ao
equipamento fica em `gateway/rotas/push.py` (A1).

Sobre `user_set_image` e corpo binario
----------------------------------------

O protocolo real usa corpo binario (`application/octet-stream`) com
`user_id`/`timestamp`/`match` na query string -- nunca JSON com base64 no
corpo (ver a nota de correcao no cabecalho de `gateway/simulador.py`). Como o
envelope do modo Push trafega inteiro como JSON (a fila do Redis serializa
com `json.dumps`, ver `gateway/dominio/fila.py`), o campo `body` aqui carrega
o base64 da imagem como STRING, e o campo extra `bodyCodificacao: "base64"`
sinaliza isso explicitamente para quem entrega ao equipamento de verdade --
convencao desta tarefa (T8), registrada em `docs/backlog.md` para o agente
que fechar a entrega real do Push (A1) confirmar o formato final antes de
falar com hardware real.

Sobre o `id` do usuario no terminal
--------------------------------------

O `id` de `users` no equipamento e um inteiro pequeno, local aquele
terminal -- nao ha coluna no nosso schema que guarde essa correspondencia
(nenhuma migration nova nesta fase, PCF F6 secao 5). `user_id_do_terminal`
deriva um inteiro deterministico a partir da matricula (CRC-32, nunca
confundir com o CRC-16 do AFD -- glossario.md, "CRC-16"): a mesma matricula
sempre produz o mesmo `user_id`, o que torna a sincronizacao naturalmente
idempotente (recriar equivale a atualizar). Colisao e teoricamente possivel
mas improvavel na escala de colaboradores por terminal; registrado em
`docs/backlog.md` como candidato a uma tabela de correspondencia persistida
se a F14 (ou uma fase futura) observar colisao real.
"""

from __future__ import annotations

import base64
import time
import zlib
from typing import Any, Final, Literal, TypedDict

CONTENT_TYPE_JSON: Final[str] = "application/json"
CONTENT_TYPE_OCTET_STREAM: Final[str] = "application/octet-stream"

_TABELA_USERS: Final[str] = "users"


class ComandoTerminal(TypedDict, total=False):
    """Envelope entregue a `POST /interno/terminais/{numeroSerie}/comandos`."""

    verb: str
    endpoint: str
    contentType: str
    queryString: str
    body: Any
    #: Presente e igual a `"base64"` somente quando `body` e uma string
    #: base64 de bytes crus (hoje, so `user_set_image.fcgi`). Ausente para
    #: comandos cujo `body` e o objeto JSON literal.
    bodyCodificacao: str


def user_id_do_terminal(matricula: str) -> int:
    """`users.id` deterministico para esta matricula, estavel entre
    sincronizacoes (o mesmo colaborador sempre cai no mesmo `id`)."""
    return zlib.crc32(matricula.encode("utf-8")) + 1


def _envelope_json(endpoint: str, corpo: dict[str, Any]) -> ComandoTerminal:
    return {
        "verb": "POST",
        "endpoint": endpoint,
        "contentType": CONTENT_TYPE_JSON,
        "queryString": "",
        "body": corpo,
    }


def montar_comando_criar_usuario(*, user_id: int, matricula: str, nome: str) -> ComandoTerminal:
    """`create_objects.fcgi` sobre `users`. `registration` recebe a
    matricula do colaborador -- a traducao de que a conversao
    `access_log -> MarcacaoCriar` (T6, A1) depende para resolver
    `access_logs.user_id -> colaborador`."""
    return _envelope_json(
        "create_objects.fcgi",
        {
            "object": _TABELA_USERS,
            "values": [{"id": user_id, "registration": matricula, "name": nome}],
        },
    )


def montar_comando_atualizar_usuario(*, user_id: int, matricula: str, nome: str) -> ComandoTerminal:
    """`modify_objects.fcgi` sobre `users`. Mesmo upsert do equipamento real
    por baixo de `create_objects` (ver nota de correcao em
    `gateway/simulador.py`) -- os dois comandos so existem como nomes
    distintos porque e o vocabulario que o PCF da F6 fixa."""
    return _envelope_json(
        "modify_objects.fcgi",
        {
            "object": _TABELA_USERS,
            "values": [{"id": user_id, "registration": matricula, "name": nome}],
        },
    )


def montar_comando_remover_usuario(*, user_id: int) -> ComandoTerminal:
    """`destroy_objects.fcgi` sobre `users` -- colaborador desligado ou
    excluido."""
    return _envelope_json(
        "destroy_objects.fcgi",
        {
            "object": _TABELA_USERS,
            "where": [{"object": _TABELA_USERS, "field": "id", "operator": "=", "value": user_id}],
        },
    )


def montar_comando_enviar_imagem(
    *,
    user_id: int,
    imagem: bytes,
    timestamp: int | None = None,
    forcar_duplicata: bool = False,
) -> ComandoTerminal:
    """`user_set_image.fcgi`. `imagem` so existe como `bytes` em memoria ate
    aqui -- esta funcao NUNCA grava em disco, nem temporariamente (ADR-006 +
    proibicao 6 do PCF da F6); o base64 devolvido vive so no dict Python que
    o chamador enfileira em seguida, nunca em arquivo."""
    instante = timestamp if timestamp is not None else int(time.time())
    query = f"user_id={user_id}&timestamp={instante}&match={0 if forcar_duplicata else 1}"
    return {
        "verb": "POST",
        "endpoint": "user_set_image.fcgi",
        "contentType": CONTENT_TYPE_OCTET_STREAM,
        "queryString": query,
        "body": base64.b64encode(imagem).decode("ascii"),
        "bodyCodificacao": "base64",
    }


def montar_comando_executar_acao(acao: str, parametros: dict[str, str]) -> ComandoTerminal:
    """`execute_actions.fcgi`. `parametros` chega como dict Python; esta
    funcao monta a string `chave=valor` (ou `chave1=v1;chave2=v2`, separados
    por `;`) que o fabricante exige -- nunca um objeto JSON."""
    texto_parametros = ";".join(f"{chave}={valor}" for chave, valor in parametros.items())
    return _envelope_json(
        "execute_actions.fcgi", {"actions": [{"action": acao, "parameters": texto_parametros}]}
    )


def montar_comando_abrir_porta(door_id: int) -> ComandoTerminal:
    """Acao `door` verificada contra a documentacao publica da Control iD:
    `{"action": "door", "parameters": "door=<id>"}` -- nao `open_door`/
    `door_id` (formato da Fase 0, corrigido nesta tarefa)."""
    return montar_comando_executar_acao("door", {"door": str(door_id)})


def montar_comando_liberar_catraca(
    sentido: Literal["clockwise", "anticlockwise", "both"] = "both",
) -> ComandoTerminal:
    """Acao `catra` verificada contra a documentacao publica:
    `{"action": "catra", "parameters": "allow=<sentido>"}`."""
    return montar_comando_executar_acao("catra", {"allow": sentido})


def montar_comando_reiniciar_terminal() -> ComandoTerminal:
    """O reinicio real e `POST /reboot.fcgi`, um endpoint proprio, **fora**
    de `execute_actions.fcgi` (ver nota de correcao em
    `gateway/simulador.py`) -- por isso o `endpoint` aqui difere dos demais
    comandos deste modulo."""
    return {
        "verb": "POST",
        "endpoint": "reboot.fcgi",
        "contentType": CONTENT_TYPE_JSON,
        "queryString": "",
        "body": {},
    }
