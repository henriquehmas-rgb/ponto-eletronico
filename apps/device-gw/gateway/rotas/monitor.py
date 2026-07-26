"""Servico **Monitor** do Control iD: eventos assincronos vindos do terminal.

Diferenca em relacao ao modo Push
---------------------------------

No Push quem pergunta e o terminal, e a resposta e um comando. No Monitor quem
fala primeiro e o terminal, sem ser perguntado: assim que algo acontece no
equipamento -- alguem bateu ponto, a catraca girou, a porta foi forcada, uma
credencial foi cadastrada --, ele **notifica** o servidor configurado.

Os dois convivem e servem a proposito diferente. O Monitor da latencia baixa: a
marcacao aparece no espelho em segundos, nao no intervalo do proximo *poll*. O
Push da alcance: funciona mesmo quando o equipamento nao consegue nos alcancar
de forma confiavel, e e o unico jeito de **mandar** trabalho para dentro da LAN.
Nenhum dos dois e suficiente sozinho, e nenhum dos dois garante entrega -- por
isso o catch-up de `gateway/rotas/catchup.py` existe e e obrigatorio.

Autenticacao (T2)
------------------

Mesma identificacao do modo Push (`numeroSerie` + `token`, ver
`gateway/dominio/resolucao.py`): sem `X-Tenant`, porque o firmware nao sabe o
que e um tenant. Toda notificacao conta como contato valido -- atualiza
`terminais.ultimo_contato_em`, a mesma base do alerta de T9, esteja o
equipamento em modo Push ou Monitor.

Eventos cobertos (PROJETO.md secao 3.1)
---------------------------------------

============================  ==================================================
novo `access_log` (`dao`)      identificacao concluida: e disto que nasce marcacao
alarme (`secbox`)              porta forcada, coacao, tamper
cadastro de credencial          face, cartao ou senha cadastrados no proprio
(`template`)                    terminal (o enrollment presencial da F2)
giro de catraca (`catra`)       confirmacao de passagem em iDBlock
abertura de porta (`door`)      portal liberado
modo de operacao                 online, offline, bloqueado, manutencao
============================  ==================================================
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Body, status

from gateway.config import obter_configuracao
from gateway.dominio import cliente_api, fila
from gateway.dominio.bd import sessao_com_tenant
from gateway.dominio.conversao import (
    TerminalParaConversao,
    converter_access_log,
    montar_idempotency_key,
)
from gateway.dominio.resolucao import TerminalResolvido, autenticar_terminal, extrair_identificacao
from gateway.dominio.terminais import (
    atualizar_ultimo_contato,
    carregar_terminal,
    obter_cliente_do_terminal,
)
from gateway.dominio.usuarios import resolver_matricula
from gateway.erros import RESPOSTAS_PADRAO, ErroDeAplicacao
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


async def _autenticar_e_registrar_contato(corpo: dict[str, Any]) -> TerminalResolvido:
    """T2: identifica o terminal e marca o contato -- toda notificacao do
    Monitor, de qualquer assunto, conta para `verificar_terminal_offline`."""
    config = obter_configuracao()
    numero_serie, token = extrair_identificacao(corpo)
    resolvido = await autenticar_terminal(numero_serie, token, config=config)
    async with sessao_com_tenant(str(resolvido.tenant_id), config=config) as sessao:
        await atualizar_ultimo_contato(sessao, resolvido.id)
    return resolvido


@roteador.post(
    "/dao",
    status_code=status.HTTP_200_OK,
    operation_id="monitorDao",
    summary="Mudanca em tabela do terminal (inclui novo access_log)",
)
async def monitor_dao(corpo: CorpoNotificacao) -> dict[str, Any]:
    """Recebe insercao, alteracao ou remocao em uma tabela do equipamento.

    E o endpoint mais importante do servico: e por aqui que chega o
    `access_logs` recem-criado, ou seja, **toda batida feita no terminal**.

    Quando `object == "access_logs"`, cada `value` vira `MarcacaoCriar` (T6) e
    e entregue a API -- que e quem atribui NSR e grava. O gateway **nao**
    atribui NSR e **nao** escreve marcacao: ele so traduz.

    **Template biometrico nao passa por aqui.** Quando `object == "templates"`,
    nenhum campo de conteudo do vetor e lido, gravado ou repassado (ADR-006):
    so o fato "houve mudanca de credencial" e registrado no log.
    """
    config = obter_configuracao()
    resolvido = await _autenticar_e_registrar_contato(corpo)
    objeto = str(corpo.get("object") or "")
    tipo = str(corpo.get("type") or "")
    valores = corpo.get("values") or []

    if objeto == "templates":
        # ADR-006: nunca ler/gravar/repassar o conteudo do vetor. So o fato.
        logger.info(
            "monitor: notificacao de credencial via dao (fato apenas)",
            extra={"tipo": tipo, "quantidade": len(valores)},
        )
        return {"recebido": True, "convertidas": 0}

    convertidas = 0
    if objeto == "access_logs" and tipo in ("inserted", "updated"):
        numero_serie, _ = extrair_identificacao(corpo)
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
        terminal_conversao = TerminalParaConversao(
            id=terminal.id,
            dispositivo_id=terminal.dispositivo_id,
            empresa_id=terminal.empresa_id,
            unidade_id=terminal.unidade_id,
            numero_serie=terminal.numero_serie,
        )
        for valor in valores:
            matricula = await resolver_matricula(
                redis=redis,
                numero_serie=numero_serie,
                user_id=int(valor["user_id"]),
                cliente=cliente,
                cache_local=cache_local,
            )
            marcacao_criar = converter_access_log(
                valor, terminal=terminal_conversao, matricula=matricula, coletada_offline=False
            )
            chave = montar_idempotency_key(numero_serie, int(valor["id"]))
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
                    "monitor: marcacao adiada, POST /v1/marcacoes ainda 501 (F5 em andamento)",
                    extra={"logExternoId": valor["id"]},
                )
    else:
        logger.info(
            "monitor: notificacao dao recebida (sem conversao)",
            extra={"objeto": objeto, "tipo": tipo, "quantidade": len(valores)},
        )
    return {"recebido": True, "convertidas": convertidas}


@roteador.post(
    "/door",
    status_code=status.HTTP_200_OK,
    operation_id="monitorPorta",
    summary="Abertura, fechamento ou arrombamento de porta",
)
async def monitor_porta(corpo: CorpoNotificacao) -> dict[str, Any]:
    """Recebe mudanca de estado de um portal (porta). Nao gera marcacao de
    ponto: gera trilha de acesso e alarme quando o estado for anomalo."""
    await _autenticar_e_registrar_contato(corpo)
    logger.info("monitor: notificacao de porta recebida", extra={"camposRecebidos": sorted(corpo)})
    return {"recebido": True}


@roteador.post(
    "/catra",
    status_code=status.HTTP_200_OK,
    operation_id="monitorCatraca",
    summary="Giro de catraca confirmado (linha iDBlock)",
)
async def monitor_catraca(corpo: CorpoNotificacao) -> dict[str, Any]:
    """Recebe a confirmacao de giro da catraca. Distincao que muda o
    resultado: liberar o giro e girar sao eventos diferentes; este e o
    evento que corrobora a passagem."""
    await _autenticar_e_registrar_contato(corpo)
    logger.info(
        "monitor: notificacao de catraca recebida", extra={"camposRecebidos": sorted(corpo)}
    )
    return {"recebido": True}


@roteador.post(
    "/template",
    status_code=status.HTTP_200_OK,
    operation_id="monitorCredencial",
    summary="Credencial cadastrada ou removida no proprio terminal",
)
async def monitor_credencial(corpo: CorpoNotificacao) -> dict[str, Any]:
    """Recebe o aviso de cadastro ou remocao de credencial feita no
    equipamento -- o enrollment presencial. Registra so o FATO (quem, quando,
    em qual terminal); ADR-006 e taxativo: o conteudo do vetor nunca passa
    por este servico. Nenhum campo do corpo que pareca conteudo (`data`,
    `template`, `vetor`, `image`, `blob`) e lido ou logado."""
    await _autenticar_e_registrar_contato(corpo)
    campos_seguros = sorted(
        campo
        for campo in corpo
        if campo.lower() not in {"data", "template", "vetor", "image", "blob", "token"}
    )
    logger.info(
        "monitor: notificacao de credencial recebida", extra={"camposRecebidos": campos_seguros}
    )
    return {"recebido": True}


@roteador.post(
    "/secbox",
    status_code=status.HTTP_200_OK,
    operation_id="monitorAlarme",
    summary="Alarme do modulo de seguranca (tamper, coacao, violacao)",
)
async def monitor_alarme(corpo: CorpoNotificacao) -> dict[str, Any]:
    """Recebe alarme do equipamento: violacao de gabinete, coacao, tamper.
    Nao afeta jornada, mas afeta confianca na trilha de auditoria."""
    await _autenticar_e_registrar_contato(corpo)
    logger.info("monitor: alarme recebido", extra={"camposRecebidos": sorted(corpo)})
    return {"recebido": True}


@roteador.post(
    "/operation_mode",
    status_code=status.HTTP_200_OK,
    operation_id="monitorModoOperacao",
    summary="Mudanca de modo de operacao do equipamento",
)
async def monitor_modo_operacao(corpo: CorpoNotificacao) -> dict[str, Any]:
    """Recebe a mudanca de modo de operacao (online, offline, bloqueado,
    manutencao) -- sinal barato de que o equipamento entrou em modo
    degradado, mais rapido que o scheduler concluir a mesma coisa por
    ausencia de contato."""
    await _autenticar_e_registrar_contato(corpo)
    logger.info("monitor: mudanca de modo de operacao", extra={"camposRecebidos": sorted(corpo)})
    return {"recebido": True}
