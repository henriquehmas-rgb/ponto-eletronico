"""**Catch-up**: recuperacao de `access_logs` por marca d'agua (T5).

O problema que isto resolve
----------------------------

Push e Monitor sao entrega de melhor esforco. A rede do cliente cai, o switch
e reiniciado, o servidor e atualizado -- e durante esse tempo o terminal
continua identificando gente e gravando `access_logs` localmente. Quando a
comunicacao volta, alguem precisa ir buscar o que ficou para tras. Esse
alguem e o catch-up.

Como funciona
-------------

Marca d'agua: guardamos, por terminal, o maior `access_logs.id` ja coletado
(`terminais.ultimo_log_externo_id`). A coleta pede ao equipamento tudo com
`id` maior que essa marca, em paginas ordenadas por `id`, via
`gateway.cliente_controlid` (T1) -- nunca fala HTTP com o terminal por conta
propria.

Tres propriedades que fazem isso ser seguro (secao 2 do PCF):

1. **`id` monotonico crescente**: "maior que a marca" e um filtro completo.
2. **Idempotencia por `numero_serie + access_log_id`**: rodar o catch-up duas
   vezes, ou catch-up e Monitor entregando o mesmo registro, nao duplica.
3. **A marca so avanca depois da gravacao confirmada de cada pagina.** Entre
   duplicar (inofensivo) e perder (irreversivel), a escolha e sempre nao
   perder -- inverter isso e o erro classico desta fase (proibicao 9).

Estas rotas nao sao chamadas pelo terminal
--------------------------------------------

Diferente de `push.py` e `monitor.py`, aqui quem chama somos nos: a tarefa
`sincronizar_terminal` do worker e a rotina `verificar_terminal_offline` do
scheduler (T9), que dispara a recuperacao quando o equipamento volta a dar
sinal.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Path, Query, status

from gateway.config import Configuracao, obter_configuracao
from gateway.dominio import cliente_api
from gateway.dominio.bd import sessao_com_tenant
from gateway.dominio.conversao import (
    TerminalParaConversao,
    converter_access_log,
    montar_idempotency_key,
)
from gateway.dominio.fila import obter_redis
from gateway.dominio.resolucao import TerminalResolvido, resolver_terminal
from gateway.dominio.terminais import (
    TerminalCarregado,
    avancar_marca_dagua,
    carregar_terminal,
    obter_cliente_do_terminal,
)
from gateway.dominio.usuarios import resolver_matricula
from gateway.erros import RESPOSTAS_PADRAO, ErroDeAplicacao
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
    status_code=status.HTTP_200_OK,
    operation_id="obterMarcaDagua",
    summary="Ultimo access_log_id coletado deste terminal",
)
async def obter_marca_dagua(numero_serie: SerieTerminal) -> dict[str, Any]:
    """Leitura pura: nao fala com o equipamento, so consulta o estado que o
    banco ja mantem (`terminais.ultimo_log_externo_id`/`ultima_sincronizacao_em`/
    `ultimo_contato_em`)."""
    config = obter_configuracao()
    resolvido = await resolver_terminal(numero_serie, config=config)
    async with sessao_com_tenant(str(resolvido.tenant_id), config=config) as sessao:
        terminal = await carregar_terminal(sessao, resolvido.id)
    if terminal is None:
        raise ErroDeAplicacao("PONTO-REC-001", detalhe="Terminal nao encontrado.")
    return {
        "numeroSerie": terminal.numero_serie,
        "ultimoIdColetado": terminal.ultimo_log_externo_id,
        "ultimoContatoEm": terminal.ultimo_contato_em.isoformat()
        if terminal.ultimo_contato_em
        else None,
    }


@roteador.post(
    "/{numero_serie}/catch-up",
    status_code=status.HTTP_200_OK,
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

    1. Abre sessao no terminal via `gateway.cliente_controlid.obter_cliente`
       (T1) -- `PONTO-TERM-001/002/003` sao os codigos de falha de conexao,
       ja tratados dentro de `cliente_controlid.py`.
    2. `load_objects` sobre `access_logs` com `id > marca`, ordenado por
       `id`, em paginas de ate `paginas_maximas` x tamanho de pagina do
       equipamento.
    3. Converte cada registro (T6) e entrega a API (`coletadaOffline=true`).
    4. Avanca a marca d'agua **so depois** da confirmacao de gravacao da
       pagina inteira.
    5. Publica `terminal.online` quando a ultima amostra de saude conhecida
       classificava o terminal como offline.
    """
    config = obter_configuracao()
    resolvido = await resolver_terminal(numero_serie, config=config)

    async with sessao_com_tenant(str(resolvido.tenant_id), config=config) as sessao:
        terminal = await carregar_terminal(sessao, resolvido.id)
    if terminal is None:
        raise ErroDeAplicacao("PONTO-REC-001", detalhe="Terminal nao encontrado.")

    marca = desde_id if desde_id is not None else terminal.ultimo_log_externo_id
    cliente = obter_cliente_do_terminal(terminal, config=config)
    redis = obter_redis(config)
    cache_local: dict[int, str] = {}
    request_id = str(uuid4())
    terminal_conversao = TerminalParaConversao(
        id=terminal.id,
        dispositivo_id=terminal.dispositivo_id,
        empresa_id=terminal.empresa_id,
        unidade_id=terminal.unidade_id,
        numero_serie=terminal.numero_serie,
    )

    registros_lidos = 0
    marcacoes_criadas = 0
    duplicadas = 0
    paginas = 0
    pendencia = False

    while paginas < paginas_maximas:
        pagina = await cliente.load_objects(
            "access_logs",
            onde=[{"field": "id", "operator": ">", "value": marca}],
            ordenar=["id"],
            limite=config.catchup_tamanho_pagina,
        )
        if not pagina:
            break
        pagina = sorted(pagina, key=lambda registro: int(registro["id"]))
        maior_id_da_pagina = marca
        for access_log in pagina:
            matricula = await resolver_matricula(
                redis=redis,
                numero_serie=numero_serie,
                user_id=int(access_log["user_id"]),
                cliente=cliente,
                cache_local=cache_local,
            )
            marcacao_criar = converter_access_log(
                access_log, terminal=terminal_conversao, matricula=matricula, coletada_offline=True
            )
            chave = montar_idempotency_key(numero_serie, int(access_log["id"]))
            try:
                resultado = await cliente_api.enviar_marcacao(
                    config,
                    tenant_id=resolvido.tenant_id,
                    corpo=marcacao_criar,
                    idempotency_key=chave,
                    request_id=request_id,
                )
                marcacoes_criadas += 1
                if resultado.get("duplicada"):
                    duplicadas += 1
            except cliente_api.MarcacaoAindaNaoDisponivel:
                logger.info(
                    "catch-up: marcacao adiada, POST /v1/marcacoes ainda 501 (F5 em andamento)",
                    extra={"numeroSerie": numero_serie, "logExternoId": access_log["id"]},
                )
            registros_lidos += 1
            maior_id_da_pagina = max(maior_id_da_pagina, int(access_log["id"]))

        # A marca so avanca DEPOIS que a pagina inteira foi entregue -- nunca
        # antes (proibicao 9 do PCF).
        async with sessao_com_tenant(str(resolvido.tenant_id), config=config) as sessao:
            await avancar_marca_dagua(sessao, terminal.id, maior_id_da_pagina)
        marca = maior_id_da_pagina
        paginas += 1
        if len(pagina) < config.catchup_tamanho_pagina:
            break
    else:
        pendencia = True

    if not pendencia:
        await _publicar_online_se_estava_offline(
            config=config, resolvido=resolvido, terminal=terminal
        )

    logger.info(
        "catch-up: execucao concluida",
        extra={
            "numeroSerie": numero_serie,
            "registrosLidos": registros_lidos,
            "marcacoesCriadas": marcacoes_criadas,
            "novaMarcaDagua": marca,
            "pendencia": pendencia,
        },
    )
    return {
        "numeroSerie": numero_serie,
        "registrosLidos": registros_lidos,
        "marcacoesCriadas": marcacoes_criadas,
        "descartadasPorIdempotencia": duplicadas,
        "novaMarcaDagua": marca,
        "pendencia": pendencia,
    }


async def _publicar_online_se_estava_offline(
    *, config: Configuracao, resolvido: TerminalResolvido, terminal: TerminalCarregado
) -> None:
    """Publica `terminal.online` (`events.yaml`, origem worker) se a ultima
    amostra de `terminal_saude` classificava o terminal como offline."""
    from sqlalchemy import text

    from gateway.dominio.eventos import publicar_terminal_online

    async with sessao_com_tenant(str(resolvido.tenant_id), config=config) as sessao:
        ultima = (
            await sessao.execute(
                text(
                    "SELECT online FROM terminal_saude WHERE terminal_id = :id "
                    "ORDER BY verificado_em DESC LIMIT 1"
                ),
                {"id": str(terminal.id)},
            )
        ).first()
    if ultima is not None and ultima.online is False:
        publicar_terminal_online(
            tenant_id=resolvido.tenant_id,
            terminal_id=terminal.id,
            empresa_id=terminal.empresa_id,
            numero_serie=terminal.numero_serie,
            unidade_id=terminal.unidade_id,
            retorno_em=dt.datetime.now(tz=dt.UTC),
        )
