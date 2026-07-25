"""**Catch-up**: recuperacao de `access_logs` por marca d'agua.

O problema que isto resolve
---------------------------

Push e Monitor sao entrega de melhor esforco. A rede do cliente cai, o switch e
reiniciado, o servidor e atualizado, o certificado expira — e durante esse
tempo o terminal continua identificando gente e gravando `access_logs`
localmente (PROJETO.md secao 3.1: "se a rede cair, o iDFace armazena
localmente"). Quando a comunicacao volta, alguem precisa ir buscar o que ficou
para tras. Esse alguem e o catch-up.

Sem ele, uma queda de rede de dez minutos vira **marcacao perdida**, e marcacao
perdida num REP-P nao e um numero a menos num grafico: e um dia de jornada que
ninguem consegue provar, com o onus recaindo sobre o empregador.

Como funciona
-------------

Marca d'agua: guardamos, por terminal, o **maior `access_logs.id` ja coletado**.
A coleta pede ao equipamento tudo com `id` maior que essa marca, em paginas
ordenadas por `id`, e avanca a marca conforme grava::

    POST /load_objects.fcgi?session=<sessao>
    {
      "object": "access_logs",
      "where": {"access_logs": {"id": {">": 41207}}},
      "order": ["id"],
      "limit": 1000
    }

Tres propriedades que fazem isso ser seguro:

1. **O `id` do equipamento e monotonico crescente**, o que torna "maior que a
   marca" um filtro completo — nao ha registro antigo aparecendo depois.
2. **Idempotencia por `numero_serie + access_log_id`.** Rodar o catch-up duas
   vezes, ou rodar catch-up e receber a mesma batida pelo Monitor, nao duplica
   nada. E o que permite ser agressivo na recuperacao sem medo.
3. **A marca so avanca depois da gravacao confirmada.** Avancar antes trocaria
   duplicacao (inofensiva, porque a chave de idempotencia trata) por perda
   (irreversivel). Entre os dois erros possiveis, escolhemos sempre o que nao
   perde marcacao.

Sessao no equipamento
---------------------

Toda chamada `*.fcgi` exige sessao obtida em `login.fcgi` com
`CONTROLID_USUARIO` / `CONTROLID_SENHA`, e a sessao vai na query string
(`?session=<token>`). A sessao expira e pode ser invalidada por reinicio do
equipamento: a F6 precisa renovar de forma transparente e **nunca** registrar o
token em log — ele da acesso administrativo ao terminal.

Estas rotas nao sao chamadas pelo terminal
------------------------------------------

Diferente de `push.py` e `monitor.py`, aqui quem chama somos nos: a tarefa
`sincronizar_terminal` do worker (F6) e a rotina `verificar_terminal_offline` do
scheduler, que dispara a recuperacao quando o equipamento volta a dar sinal. Os
caminhos, portanto, sao **nossos** — nao dependem de firmware e nao precisam de
confirmacao contra hardware.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, status

from gateway.erros import RESPOSTAS_PADRAO, NaoImplementado
from gateway.log import obter_logger

logger = obter_logger("catchup")

roteador = APIRouter(
    prefix="/interno/terminais", tags=["controlid-catchup"], responses=RESPOSTAS_PADRAO
)

SerieTerminal = Annotated[
    str,
    Path(
        min_length=1,
        max_length=64,
        description="Numero de serie do equipamento, como gravado em `terminais.numero_serie`.",
    ),
]


@roteador.get(
    "/{numero_serie}/marca-dagua",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    operation_id="obterMarcaDagua",
    summary="Ultimo access_log_id coletado deste terminal",
)
async def obter_marca_dagua(numero_serie: SerieTerminal) -> dict[str, Any]:
    """Devolve a marca d'agua atual e o estado da ultima coleta.

    **Resposta prevista.** `numeroSerie`, `ultimoIdColetado`, `coletadoEm`,
    `ultimoContatoEm` e uma estimativa de pendencia. E o dado que o painel de
    operacao mostra e que o evento `terminal.offline` de `events.yaml` carrega
    no campo `logsPendentesEstimados`.

    Endpoint de leitura pura: nao fala com o equipamento, so consulta o estado
    que o gateway ja mantem. Serve para diagnostico ("de onde ele vai retomar?")
    sem custo nenhum para o terminal.
    """
    logger.info("catch-up: consulta de marca d'agua", extra={"numeroSerie": numero_serie})
    raise NaoImplementado("obterMarcaDagua")


@roteador.post(
    "/{numero_serie}/catch-up",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    operation_id="executarCatchUp",
    summary="Coleta os access_logs pendentes a partir da marca d'agua",
)
async def executar_catch_up(
    numero_serie: SerieTerminal,
    desde_id: Annotated[
        int | None,
        Query(
            ge=0,
            description=(
                "Forca a coleta a partir deste `access_logs.id`, ignorando a marca d'agua. "
                "Uso de excecao: reprocessamento auditado apos incidente."
            ),
        ),
    ] = None,
    paginas_maximas: Annotated[
        int,
        Query(
            ge=1, le=1000, description="Teto de paginas por execucao, para nao segurar o worker."
        ),
    ] = 50,
) -> dict[str, Any]:
    """Executa a recuperacao por marca d'agua e entrega o que achar a API.

    **O que a F6 fara aqui**, na ordem, e a razao de cada passo:

    1. `login.fcgi` para abrir sessao. Falha de credencial e `PONTO-TERM-003`;
       equipamento inalcancavel e `PONTO-TERM-001`; prazo estourado e
       `PONTO-TERM-002`. Os tres sao codigos do catalogo — nenhum e inventado.
    2. `load_objects.fcgi` sobre `access_logs` com `id > marca`, ordenado por
       `id`, em paginas de `CATCHUP_TAMANHO_PAGINA`. Pedir tudo de uma vez em um
       terminal com trinta dias de *backlog* estoura a memoria do equipamento —
       nao a nossa.
    3. Converter cada registro em marcacao canonica e entregar a API, que
       atribui NSR e grava. O gateway nao atribui NSR.
    4. Avancar a marca d'agua **depois** da confirmacao de gravacao, pagina a
       pagina. Ver a propriedade 3 no cabecalho do modulo.
    5. Publicar `terminal.online` (`events.yaml`, `origem: worker`) com quantos
       registros foram recuperados — e assim que o consumidor de webhook fica
       sabendo que houve reposicao retroativa de marcacao.

    `paginas_maximas` existe para que uma recuperacao gigantesca nao segure um
    slot do worker por uma hora: a execucao devolve "ainda ha pendencia" e o
    proximo ciclo continua de onde parou. Retomar e barato justamente porque a
    marca d'agua e persistida.

    **Resposta prevista.** Quantos registros foram lidos, quantos viraram
    marcacao, quantos foram descartados por idempotencia, a nova marca d'agua e
    se restou pendencia.
    """
    logger.info(
        "catch-up: execucao solicitada",
        extra={
            "numeroSerie": numero_serie,
            "desdeId": desde_id,
            "paginasMaximas": paginas_maximas,
        },
    )
    raise NaoImplementado("executarCatchUp")
