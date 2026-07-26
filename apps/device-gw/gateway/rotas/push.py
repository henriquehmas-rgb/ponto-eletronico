"""Modo **Push** do Control iD: o terminal busca comandos no servidor.

Por que este modo existe
------------------------

O iDFace costuma ficar em LAN sem IP publico, atras de NAT, num cliente que nao
vai abrir porta no firewall para a gente. Nesse cenario o servidor **nao
consegue** iniciar conexao com o equipamento. Quem inicia e o terminal
(PROJETO.md secao 3.1): ele pergunta ao servidor, de tempos em tempos, "tem
comando para mim?", executa localmente o que vier e devolve o resultado.

Consequencia de desenho que atravessa a F6 inteira: **toda operacao sobre o
terminal e assincrona**. "Cadastrar a face do colaborador no equipamento" nao e
uma chamada, e um comando enfileirado que sera entregue no proximo *poll*. E por
isso que existe `PONTO-TERM-004` ("Terminal offline, comando enfileirado"): e
resposta normal, nao falha.

O ciclo, em tres passos
-----------------------

1. **Terminal pede trabalho.** Faz uma requisicao ao servidor identificando-se
   (`numeroSerie` + `token`) e recebe o proximo comando da fila, ou corpo vazio.
2. **Servidor responde com um comando**, no envelope
   `{verb, endpoint, contentType, queryString, body}` (`gateway/dominio/fila.py`).
3. **Terminal devolve o resultado** da execucao local em
   `POST /send_response.fcgi`; quando o comando era `load_objects.fcgi` sobre
   `access_logs`, o gateway converte cada registro em marcacao canonica
   (`gateway/dominio/conversao.py`) e entrega a API (`gateway/dominio/
   cliente_api.py`).

Autenticacao (T2)
-----------------

O equipamento apresenta `numeroSerie` + o segredo de Push (`token`, cadastrado
em `terminais.token_push` ou, na falta, `CONTROLID_PUSH_TOKEN` global -- ver
`gateway/dominio/resolucao.py::autenticar_terminal`). A comparacao e em tempo
constante (`hmac.compare_digest`) e a mensagem de erro nunca revela se o
`numeroSerie` nao existe, esta inativo ou o token esta errado -- os tres casos
respondem `PONTO-TERM-003` sem `detail`.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Body, Path, status

from gateway.config import obter_configuracao
from gateway.dominio import cliente_api, fila
from gateway.dominio.bd import sessao_com_tenant
from gateway.dominio.conversao import converter_access_log, montar_idempotency_key
from gateway.dominio.resolucao import autenticar_terminal, extrair_identificacao, resolver_terminal
from gateway.dominio.terminais import (
    TerminalCarregado,
    atualizar_ultimo_contato,
    carregar_terminal,
    obter_cliente_do_terminal,
)
from gateway.dominio.usuarios import resolver_matricula
from gateway.erros import RESPOSTAS_PADRAO, ErroDeAplicacao
from gateway.log import obter_logger

logger = obter_logger("push")

roteador = APIRouter(tags=["controlid-push"], responses=RESPOSTAS_PADRAO)

SerieTerminal = Annotated[
    str,
    Path(
        min_length=1,
        max_length=64,
        description="Numero de serie do equipamento, como gravado em `terminais.numero_serie`.",
    ),
]


@roteador.post(
    "/new_connection.fcgi",
    status_code=status.HTTP_200_OK,
    operation_id="pushObterComando",
    summary="Terminal pede o proximo comando (passo 1 do ciclo Push)",
)
async def push_obter_comando(
    corpo: Annotated[dict[str, Any], Body(description="Identificacao enviada pelo equipamento.")],
) -> dict[str, Any]:
    """Autentica o terminal (T2), atualiza `ultimo_contato_em` e devolve o
    proximo comando da fila do Redis, ou corpo vazio quando nao ha nenhum."""
    config = obter_configuracao()
    numero_serie, token = extrair_identificacao(corpo)
    resolvido = await autenticar_terminal(numero_serie, token, config=config)

    async with sessao_com_tenant(str(resolvido.tenant_id), config=config) as sessao:
        await atualizar_ultimo_contato(sessao, resolvido.id)

    redis = fila.obter_redis(config)
    comando = await fila.proximo_comando(redis, numero_serie)
    logger.info(
        "push: pedido de comando atendido",
        extra={"numeroSerie": numero_serie, "comandoEntregue": comando is not None},
    )
    return comando or {}


@roteador.post(
    "/send_response.fcgi",
    status_code=status.HTTP_200_OK,
    operation_id="pushEnviarResultado",
    summary="Terminal devolve o resultado do comando executado (passo 3 do ciclo Push)",
)
async def push_enviar_resultado(
    corpo: Annotated[
        dict[str, Any],
        Body(description="Resultado da execucao local do comando, como o equipamento devolve."),
    ],
) -> dict[str, Any]:
    """Fecha o ciclo do comando. Quando o corpo traz `accessLogs` (resultado
    de um `load_objects.fcgi` sobre `access_logs` que o gateway mandou
    executar), converte cada registro em marcacao canonica e entrega a API --
    idempotente por `dispositivoId` + `logExternoId` E por `Idempotency-Key`
    (as duas determinadas por `numero_serie:access_log_id`), entao reapresentar
    o mesmo resultado nunca gera uma segunda marcacao."""
    config = obter_configuracao()
    numero_serie, token = extrair_identificacao(corpo)
    resolvido = await autenticar_terminal(numero_serie, token, config=config)

    access_logs = corpo.get("accessLogs") or []
    convertidas = 0
    if access_logs:
        async with sessao_com_tenant(str(resolvido.tenant_id), config=config) as sessao:
            terminal = await carregar_terminal(sessao, resolvido.id)
        if terminal is None:
            raise ErroDeAplicacao(
                "PONTO-REC-001", detalhe="Terminal removido entre a consulta e o uso."
            )

        cliente = (
            obter_cliente_do_terminal(terminal, config=config)
            if (config.controlid_simulador or terminal.modo_comunicacao in ("polling", "direto"))
            else None
        )
        redis = fila.obter_redis(config)
        cache_local: dict[int, str] = {}
        request_id = str(uuid4())
        for access_log in access_logs:
            matricula = await resolver_matricula(
                redis=redis,
                numero_serie=numero_serie,
                user_id=int(access_log["user_id"]),
                cliente=cliente,
                cache_local=cache_local,
            )
            marcacao_criar = converter_access_log(
                access_log,
                terminal=_terminal_para_conversao(terminal),
                matricula=matricula,
                coletada_offline=False,
            )
            chave = montar_idempotency_key(numero_serie, int(access_log["id"]))
            try:
                await cliente_api.enviar_marcacao(
                    config,
                    tenant_id=resolvido.tenant_id,
                    corpo=marcacao_criar,
                    idempotency_key=chave,
                    request_id=request_id,
                )
                convertidas += 1
            except cliente_api.MarcacaoAindaNaoDisponivel:
                logger.info(
                    "push: marcacao adiada, POST /v1/marcacoes ainda 501 (F5 em andamento)",
                    extra={"numeroSerie": numero_serie, "logExternoId": access_log["id"]},
                )

    logger.info(
        "push: resultado recebido",
        extra={
            "numeroSerie": numero_serie,
            "totalAccessLogs": len(access_logs),
            "convertidas": convertidas,
        },
    )
    return {"recebido": True, "convertidas": convertidas}


def _terminal_para_conversao(terminal: Any) -> Any:
    from gateway.dominio.conversao import TerminalParaConversao

    return TerminalParaConversao(
        id=terminal.id,
        dispositivo_id=terminal.dispositivo_id,
        empresa_id=terminal.empresa_id,
        unidade_id=terminal.unidade_id,
        numero_serie=terminal.numero_serie,
    )


@roteador.post(
    "/interno/terminais/{numero_serie}/comandos",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="enfileirarComando",
    summary="Enfileira um comando para o terminal executar no proximo ciclo",
)
async def enfileirar_comando(
    numero_serie: SerieTerminal,
    corpo: Annotated[
        dict[str, Any],
        Body(description="Comando a executar, no envelope `{verb, endpoint, body}`."),
    ],
) -> dict[str, Any]:
    """Rota **interna**: a API e o worker enfileiram trabalho para o
    terminal. Nao e chamada pelo equipamento.

    Comandos previstos para a F6, todos no vocabulario do fabricante:
    `create_objects.fcgi`, `modify_objects.fcgi`, `destroy_objects.fcgi`,
    `user_set_image.fcgi`, `execute_actions.fcgi`.

    Responde `202` quando o terminal esta em contato dentro do
    `intervalo_push_segundos` esperado; `409 PONTO-TERM-004` quando ele esta
    mudo ha mais que isso -- o comando e enfileirado do mesmo jeito (nunca se
    perde), so o status muda, para o chamador saber que a entrega nao e
    imediata.
    """
    config = obter_configuracao()
    resolvido = await resolver_terminal(numero_serie, config=config)
    async with sessao_com_tenant(str(resolvido.tenant_id), config=config) as sessao:
        terminal = await carregar_terminal(sessao, resolvido.id)
    if terminal is None:
        raise ErroDeAplicacao(
            "PONTO-REC-001", detalhe="Terminal removido entre a consulta e o uso."
        )

    redis = fila.obter_redis(config)
    verb = str(corpo.get("verb") or "POST")
    endpoint = str(corpo.get("endpoint") or "")
    body = corpo.get("body") or {}
    comando_id = await fila.enfileirar_comando(
        redis, numero_serie, verb=verb, endpoint=endpoint, body=body
    )
    logger.info(
        "push: comando enfileirado",
        extra={"numeroSerie": numero_serie, "comandoId": comando_id, "endpoint": endpoint},
    )
    resultado = {"comandoId": comando_id, "status": "enfileirado"}
    if terminal.modo_comunicacao == "push" and _terminal_esta_mudo(terminal):
        raise ErroDeAplicacao(
            "PONTO-TERM-004",
            detalhe="Comando enfileirado; terminal sem contato ha mais que o intervalo esperado.",
            contexto_log={"numeroSerie": numero_serie, "comandoId": comando_id},
        )
    return resultado


def _terminal_esta_mudo(terminal: TerminalCarregado) -> bool:
    """`PONTO-TERM-004`: terminal Push sem contato ha mais que
    `intervalo_push_segundos` (com uma folga de 2x -- um unico ciclo perdido
    nao deveria virar alerta, e o limiar exato do alerta de offline e outro,
    T9). Terminal que nunca fez contato (recem-cadastrado) conta como mudo."""
    if terminal.ultimo_contato_em is None:
        return True
    limite = dt.timedelta(seconds=terminal.intervalo_push_segundos * 2)
    agora = dt.datetime.now(tz=dt.UTC)
    ultimo = terminal.ultimo_contato_em
    if ultimo.tzinfo is None:
        ultimo = ultimo.replace(tzinfo=dt.UTC)
    return bool((agora - ultimo) > limite)
