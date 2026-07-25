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
   (numero de serie / `deviceId`) e fica aguardando ate ter comando ou estourar
   o prazo.
2. **Servidor responde com um comando**, no envelope que o firmware espera::

       {
         "verb": "POST",                     # metodo que o terminal deve usar
         "endpoint": "load_objects.fcgi",    # rota *.fcgi local do equipamento
         "contentType": "application/json",
         "queryString": "",
         "body": { "object": "users", "limit": 100 }
       }

   Corpo vazio (ou resposta sem comando) significa "nada a fazer, volte depois".
3. **Terminal devolve o resultado** da execucao local, referenciando o comando,
   e o gateway conclui o ciclo: marca o comando como concluido, converte o que
   veio (se for `access_logs`) e entrega a API.

Sobre os caminhos declarados abaixo — leia antes de mexer
---------------------------------------------------------

Quem escolhe o caminho **e o firmware do equipamento**, nao nos: o terminal e
configurado com um endereco de servidor e concatena o sufixo fixo que o
fabricante definiu. Os nomes usados aqui (`new_connection.fcgi` e
`send_response.fcgi`) sao os que a documentacao da Control iD descreve para o
modo Push, mas **nao foram verificados contra hardware**: `PROJETO.md` secao 2
registra que a aquisicao de um iDFace fisico e pre-requisito ainda em aberto, e
`FASES-E-AGENTES.md` (F6) coloca a confirmacao do protocolo dentro da propria
fase, junto com o simulador.

Trocar o caminho depois custa quase nada e nao quebra contrato: o device-gw
**nao aparece** em `packages/contracts/openapi.yaml` — ele fala o protocolo do
fabricante de um lado e chama a API interna do outro. O que nao pode mudar sem
RFC e o codigo de erro devolvido e o formato da marcacao entregue a API.

Autenticacao
------------

O equipamento apresenta `CONTROLID_PUSH_TOKEN` (segredo compartilhado, gerado
por instalacao e cadastrado no terminal). Na Fase 0 nada e conferido — os stubs
respondem 501 antes de qualquer verificacao. A F6 implementa a conferencia em
tempo constante e responde `PONTO-AUTH-013` sem `detail` (o codigo tem
`expoe_regra: false`): dizer *por que* a credencial foi recusada, numa rota
publica que qualquer um alcanca, e entregar meio caminho a quem forja terminal.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Path, status

from gateway.erros import RESPOSTAS_PADRAO, NaoImplementado
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
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    operation_id="pushObterComando",
    summary="Terminal pede o proximo comando (passo 1 do ciclo Push)",
)
async def push_obter_comando(
    corpo: Annotated[dict[str, Any], Body(description="Identificacao enviada pelo equipamento.")],
) -> dict[str, Any]:
    """Entrega ao terminal o proximo comando da fila, ou nada.

    **Requisicao (terminal -> gateway).** Corpo JSON com a identificacao do
    equipamento. O campo que importa e o identificador do aparelho
    (`deviceId` / numero de serie); o firmware costuma acrescentar versao e
    estado. O gateway trata o corpo como dado nao confiavel: ele vem da borda da
    rede e o unico campo em que se pode confiar e o que casa com um terminal
    cadastrado e com o token apresentado.

    **Resposta (gateway -> terminal).** Um envelope de comando::

        {"verb": "POST", "endpoint": "load_objects.fcgi",
         "contentType": "application/json", "queryString": "",
         "body": {"object": "access_logs", "where": {...}}}

    Sem comando na fila, resposta vazia: o terminal volta a perguntar no
    intervalo configurado nele.

    **O que a F6 fara aqui.** Conferir o token, resolver o terminal pelo numero
    de serie, atualizar `ultimo_contato_em` (e o que faz o
    `verificar_terminal_offline` do scheduler parar de alarmar), tirar o proximo
    comando da fila no Redis com trava por terminal e devolve-lo. O relogio do
    servidor tambem viaja nesta resposta: o terminal precisa estar sincronizado,
    e o horario do equipamento e evidencia, nunca fonte de verdade.
    """
    logger.info("push: pedido de comando recebido", extra={"camposRecebidos": sorted(corpo)})
    raise NaoImplementado("pushObterComando")


@roteador.post(
    "/send_response.fcgi",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    operation_id="pushEnviarResultado",
    summary="Terminal devolve o resultado do comando executado (passo 3 do ciclo Push)",
)
async def push_enviar_resultado(
    corpo: Annotated[
        dict[str, Any],
        Body(description="Resultado da execucao local do comando, como o equipamento devolve."),
    ],
) -> dict[str, Any]:
    """Recebe o resultado da execucao local e fecha o ciclo do comando.

    **Requisicao (terminal -> gateway).** O corpo carrega a resposta que o
    equipamento produziu ao executar o `endpoint` que lhe foi mandado. Para um
    comando de `load_objects.fcgi` sobre `access_logs`, e a propria lista de
    registros; para `execute_actions.fcgi`, o estado da acao.

    **Resposta (gateway -> terminal).** Confirmacao curta. O terminal so
    considera o comando entregue quando recebe 2xx: responder erro faz o
    equipamento reapresentar o mesmo resultado no proximo ciclo — que e
    exatamente o comportamento desejado, e a razao de a ingestao ter de ser
    **idempotente**.

    **Idempotencia.** A chave e `numero_serie + access_log_id` (PROJETO.md secao
    3.1). O mesmo `access_log` reapresentado nao pode virar duas marcacoes: no
    ponto, marcacao duplicada e problema trabalhista, nao inconveniencia. Quando
    a chave repete, a resposta correta e sucesso (o terminal ja fez a parte
    dele), e o log registra o descarte.
    """
    logger.info("push: resultado recebido", extra={"camposRecebidos": sorted(corpo)})
    raise NaoImplementado("pushEnviarResultado")


@roteador.post(
    "/interno/terminais/{numero_serie}/comandos",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
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
    """Rota **interna**: a API enfileira trabalho para o terminal.

    Chamada por `apps/api` e por `apps/worker` (tarefa `sincronizar_terminal`)
    quando um colaborador e cadastrado, tem a face atualizada, muda de regra de
    acesso ou e desligado. Nao e chamada pelo equipamento.

    Comandos previstos para a F6, todos no vocabulario do fabricante:

    ==========================  =================================================
    `create_objects.fcgi`       cria `users`, `groups`, `access_rules`, `portals`
    `modify_objects.fcgi`       altera cadastro ja existente
    `destroy_objects.fcgi`      remove usuario desligado
    `user_set_image.fcgi`       envia a foto para o terminal extrair o template
    `execute_actions.fcgi`      abre porta, libera giro de catraca, reinicia
    ==========================  =================================================

    **Resposta.** `202` com o identificador do comando enfileirado quando o
    terminal esta em contato; `409 PONTO-TERM-004` quando ele esta mudo — o
    comando fica na fila e sai no proximo *poll*, e o chamador precisa saber
    disso para nao prometer ao usuario que ja esta feito.

    **Seguranca.** Esta rota nao pode ficar acessivel a partir da internet com o
    mesmo token do terminal: quem a alcanca abre porta. A F6 deve exigir
    credencial de servico (a mesma da API) e, de preferencia, mante-la fora do
    roteador publicado em `dev.ponto.<dominio>`.
    """
    logger.info(
        "push: comando enfileirado (stub)",
        extra={"numeroSerie": numero_serie, "camposRecebidos": sorted(corpo)},
    )
    raise NaoImplementado("enfileirarComando")
