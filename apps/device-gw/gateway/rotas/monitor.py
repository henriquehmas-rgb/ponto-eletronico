"""Servico **Monitor** do Control iD: eventos assincronos vindos do terminal.

Diferenca em relacao ao modo Push
---------------------------------

No Push quem pergunta e o terminal, e a resposta e um comando. No Monitor quem
fala primeiro e o terminal, sem ser perguntado: assim que algo acontece no
equipamento — alguem bateu ponto, a catraca girou, a porta foi forcada, uma
credencial foi cadastrada —, ele **notifica** o servidor configurado.

Os dois convivem e servem a proposito diferente. O Monitor da latencia baixa: a
marcacao aparece no espelho em segundos, nao no intervalo do proximo *poll*. O
Push da alcance: funciona mesmo quando o equipamento nao consegue nos alcancar
de forma confiavel, e e o unico jeito de **mandar** trabalho para dentro da LAN.
Nenhum dos dois e suficiente sozinho, e nenhum dos dois garante entrega — por
isso o catch-up de `gateway/rotas/catchup.py` existe e e obrigatorio.

Eventos cobertos (PROJETO.md secao 3.1)
---------------------------------------

============================  ==================================================
novo `access_log`             identificacao concluida: e disto que nasce marcacao
alarme (`alarm_logs`)         porta forcada, porta aberta demais, coacao, tamper
cadastro de credencial        face, cartao ou senha cadastrados no proprio
                              terminal (o enrollment presencial da F2)
giro de catraca               confirmacao de passagem em iDBlock
abertura de porta             portal liberado
============================  ==================================================

Formato da notificacao
----------------------

O equipamento envia `POST` com JSON descrevendo a mudanca na tabela interna::

    {"object": "access_logs",
     "type": "inserted",
     "values": [{"id": 41207, "time": 1785062460, "event": 7,
                 "user_id": 314, "portal_id": 1, "identifier_id": 0}]}

Notas sobre os campos, porque cada uma vira defeito se ignorada:

* `time` e **epoch do relogio do equipamento**. E evidencia, nao verdade: o
  horario oficial da marcacao e o do servidor (PROJETO.md secao 3.1 e ADR-007).
  Guardar os dois e obrigatorio — a divergencia entre eles e o sinal de que o
  relogio do terminal derivou.
* `id` e o identificador do registro **dentro daquele equipamento**. E ele que
  forma a chave de idempotencia `numero_serie + access_log_id` e a marca d'agua
  do catch-up.
* `event` e o codigo do fabricante para o tipo de identificacao (face, cartao,
  senha, recusado). O mapeamento para o vocabulario do dominio e trabalho da F6.
* `user_id` referencia `users` **no terminal**, nao `colaboradores` no banco. A
  traducao vive na tabela de vinculo de dispositivo.

Sobre os caminhos declarados abaixo — leia antes de mexer
---------------------------------------------------------

Como no modo Push, **quem escolhe o caminho e o firmware**: o equipamento e
configurado com um endereco de servidor e concatena o sufixo fixo do fabricante
(`/api/notifications/<assunto>`). Os sufixos usados aqui seguem a documentacao
da Control iD, mas **nao foram verificados contra hardware** — `PROJETO.md`
secao 2 registra a aquisicao de um iDFace fisico como pre-requisito em aberto, e
a confirmacao do protocolo esta dentro da F6, junto com o simulador.

Nenhum destes caminhos aparece em `packages/contracts/openapi.yaml`: eles sao
protocolo de fabricante, nao contrato de produto. Ajusta-los na F6 nao exige RFC.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, status

from gateway.erros import RESPOSTAS_PADRAO, NaoImplementado
from gateway.log import obter_logger

logger = obter_logger("monitor")

roteador = APIRouter(
    prefix="/api/notifications",
    tags=["controlid-monitor"],
    responses=RESPOSTAS_PADRAO,
)

CorpoNotificacao = Annotated[
    dict[str, Any],
    Body(description="Notificacao enviada pelo equipamento, no formato `{object, type, values}`."),
]


@roteador.post(
    "/dao",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    operation_id="monitorDao",
    summary="Mudanca em tabela do terminal (inclui novo access_log)",
)
async def monitor_dao(corpo: CorpoNotificacao) -> dict[str, Any]:
    """Recebe insercao, alteracao ou remocao em uma tabela do equipamento.

    E o endpoint mais importante do servico: e por aqui que chega o
    `access_logs` recem-criado, ou seja, **toda batida feita no terminal**.

    **Requisicao.** `{"object": "<tabela>", "type": "inserted|updated|deleted",
    "values": [ ... ]}`. As tabelas que interessam sao `access_logs` (batidas),
    `alarm_logs` (alarmes), `users`, `templates`, `groups`, `access_rules`,
    `portals` e `time_zones`.

    **Resposta.** 2xx curto. Erro faz o equipamento reenviar — comportamento
    desejado, e a razao de a ingestao precisar ser idempotente por
    `numero_serie + access_log_id`.

    **O que a F6 fara aqui.** Conferir o token, resolver o terminal, gravar o
    evento cru para auditoria, converter `access_logs` em marcacao canonica e
    entregar a `POST /v1/marcacoes` da API — que e quem atribui NSR e grava. O
    gateway **nao** atribui NSR e **nao** escreve marcacao: ele so traduz.

    **Template biometrico nao passa por aqui.** Se `object` for `templates`, o
    conteudo do vetor nao e registrado nem repassado em claro (ADR-006). O que
    interessa e o fato "fulano cadastrou face no terminal X", nao o vetor.
    """
    logger.info(
        "monitor: notificacao dao recebida",
        extra={"objeto": str(corpo.get("object", "")), "tipo": str(corpo.get("type", ""))},
    )
    raise NaoImplementado("monitorDao")


@roteador.post(
    "/door",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    operation_id="monitorPorta",
    summary="Abertura, fechamento ou arrombamento de porta",
)
async def monitor_porta(corpo: CorpoNotificacao) -> dict[str, Any]:
    """Recebe mudanca de estado de um portal (porta).

    Nao gera marcacao de ponto: gera trilha de acesso e, quando o estado for
    anomalo (porta forcada, porta aberta por tempo excessivo), alarme para o
    painel de operacao. Fica registrado porque, num REP-P, "a porta estava
    aberta" e informacao que aparece em contestacao de jornada.
    """
    logger.info("monitor: notificacao de porta recebida", extra={"camposRecebidos": sorted(corpo)})
    raise NaoImplementado("monitorPorta")


@roteador.post(
    "/catra",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    operation_id="monitorCatraca",
    summary="Giro de catraca confirmado (linha iDBlock)",
)
async def monitor_catraca(corpo: CorpoNotificacao) -> dict[str, Any]:
    """Recebe a confirmacao de giro da catraca.

    Distincao que muda o resultado: **liberar** o giro e **girar** sao eventos
    diferentes. Alguem pode ser identificado, a catraca liberar e a pessoa
    desistir de passar. Em catraca, o evento que corrobora a passagem e este; a
    politica de qual dos dois vira marcacao e decisao da F6, por instalacao.
    """
    logger.info(
        "monitor: notificacao de catraca recebida", extra={"camposRecebidos": sorted(corpo)}
    )
    raise NaoImplementado("monitorCatraca")


@roteador.post(
    "/template",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    operation_id="monitorCredencial",
    summary="Credencial cadastrada ou removida no proprio terminal",
)
async def monitor_credencial(corpo: CorpoNotificacao) -> dict[str, Any]:
    """Recebe o aviso de cadastro ou remocao de credencial feita no equipamento.

    E o enrollment presencial: o colaborador cadastra a face no proprio iDFace,
    com o RH ao lado. O que o gateway registra e o **fato** — quem, quando, em
    qual terminal, com qual versao de modelo —, nunca o vetor.

    ADR-006 e taxativo: template e dado pessoal sensivel, so existe cifrado com
    envelope AES-256-GCM e chave fora do banco, e **nunca sai pela API, para
    nenhum perfil**. Um servico de borda como este e o ultimo lugar do sistema
    onde biometria crua poderia passear.
    """
    logger.info(
        "monitor: notificacao de credencial recebida", extra={"camposRecebidos": sorted(corpo)}
    )
    raise NaoImplementado("monitorCredencial")


@roteador.post(
    "/secbox",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    operation_id="monitorAlarme",
    summary="Alarme do modulo de seguranca (tamper, coacao, violacao)",
)
async def monitor_alarme(corpo: CorpoNotificacao) -> dict[str, Any]:
    """Recebe alarme do equipamento: violacao de gabinete, coacao, tamper.

    Nao afeta jornada, mas afeta confianca: um terminal violado e um terminal
    cujas marcacoes precisam ser olhadas com desconfianca. O evento entra na
    trilha de auditoria e alimenta o painel de operacao da F15.
    """
    logger.info("monitor: alarme recebido", extra={"camposRecebidos": sorted(corpo)})
    raise NaoImplementado("monitorAlarme")


@roteador.post(
    "/operation_mode",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    operation_id="monitorModoOperacao",
    summary="Mudanca de modo de operacao do equipamento",
)
async def monitor_modo_operacao(corpo: CorpoNotificacao) -> dict[str, Any]:
    """Recebe a mudanca de modo de operacao (online, offline, bloqueado, manutencao).

    Sinal barato e util: o proprio equipamento avisando que entrou em modo
    degradado chega antes de o `verificar_terminal_offline` do scheduler
    concluir a mesma coisa por ausencia de contato.
    """
    logger.info("monitor: mudanca de modo de operacao", extra={"camposRecebidos": sorted(corpo)})
    raise NaoImplementado("monitorModoOperacao")
