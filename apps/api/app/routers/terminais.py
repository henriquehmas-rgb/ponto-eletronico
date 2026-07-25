"""Rotas da tag `terminais` do contrato. GERADO -- nao editar.

Coletores fisicos, tipicamente Control iD iDFace.
IMPORTANTE: o terminal NAO e o REP-P.
Ele identifica a pessoa e produz um registro de acesso; quem atribui o NSR e grava no AFD e o nosso software.
Em modo push quem inicia a conexao e o equipamento, e o catch-up por marca dagua garante que nada se perca na queda de rede.

Regra de negocio destas operacoes entra na fase F6. Ate la toda chamada
responde 501 com PONTO-INT-005. Regerar com
`python tools/gerar_do_contrato.py`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query, Response

from app.core.erros import RESPOSTAS_PADRAO, NaoImplementado
from app.schemas import contrato

roteador = APIRouter(tags=["terminais"])


@roteador.get(
    "/v1/terminais",
    status_code=200,
    operation_id="listarTerminais",
    summary="Listar terminais",
    responses=RESPOSTAS_PADRAO,
)
async def listar_terminais(
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
    cursor: Annotated[
        str | None,
        Query(
            alias="cursor",
            description="Cursor opaco devolvido em paginacao.proximoCursor da pagina anterior. Ausente retorna a primeira pagina. O cursor codifica a ordenacao usada: trocar o parame...",
        ),
    ] = None,
    limite: Annotated[
        int | None, Query(alias="limite", description="Quantidade de itens por pagina.")
    ] = None,
    ordenar: Annotated[
        str | None,
        Query(
            alias="ordenar",
            description="Ordenacao no formato campo:direcao, separando multiplos criterios por virgula. Direcoes aceitas: asc e desc. Campos aceitos sao os documentados em cada opera...",
        ),
    ] = None,
    empresa_id: Annotated[
        UUID | None, Query(alias="empresaId", description="Filtra pelos terminais de uma empresa.")
    ] = None,
    unidade_id: Annotated[
        UUID | None, Query(alias="unidadeId", description="Filtra pelos terminais de uma unidade.")
    ] = None,
    fabricante: Annotated[
        str | None, Query(alias="fabricante", description="Filtra pelo fabricante.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    online: Annotated[
        bool | None,
        Query(
            alias="online", description="Filtra pelo estado de conexao derivado do ultimo contato."
        ),
    ] = None,
) -> contrato.ListaTerminal:
    """Listar terminais

    Fase 0 entrega andaime: a implementacao entra na fase F6.
    """
    raise NaoImplementado("listarTerminais", fase="F6")


@roteador.post(
    "/v1/terminais",
    status_code=201,
    operation_id="criarTerminal",
    summary="Criar terminal",
    responses=RESPOSTAS_PADRAO,
)
async def criar_terminal(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.TerminalCriar,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> contrato.Terminal:
    """Criar terminal

    Fase 0 entrega andaime: a implementacao entra na fase F6.
    """
    raise NaoImplementado("criarTerminal", fase="F6")


@roteador.get(
    "/v1/terminais/{terminalId}",
    status_code=200,
    operation_id="obterTerminal",
    summary="Obter terminal",
    responses=RESPOSTAS_PADRAO,
)
async def obter_terminal(
    terminal_id: Annotated[
        UUID, Path(alias="terminalId", description="Identificador do terminal.")
    ],
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> contrato.Terminal:
    """Obter terminal

    Fase 0 entrega andaime: a implementacao entra na fase F6.
    """
    raise NaoImplementado("obterTerminal", fase="F6")


@roteador.patch(
    "/v1/terminais/{terminalId}",
    status_code=200,
    operation_id="atualizarTerminal",
    summary="Atualizar terminal",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_terminal(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    terminal_id: Annotated[
        UUID, Path(alias="terminalId", description="Identificador do terminal.")
    ],
    corpo: contrato.TerminalAtualizar,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> contrato.Terminal:
    """Atualizar terminal

    Fase 0 entrega andaime: a implementacao entra na fase F6.
    """
    raise NaoImplementado("atualizarTerminal", fase="F6")


@roteador.delete(
    "/v1/terminais/{terminalId}",
    status_code=204,
    operation_id="excluirTerminal",
    summary="Excluir terminal",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def excluir_terminal(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    terminal_id: Annotated[
        UUID, Path(alias="terminalId", description="Identificador do terminal.")
    ],
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> Response:
    """Excluir terminal

    Fase 0 entrega andaime: a implementacao entra na fase F6.
    """
    raise NaoImplementado("excluirTerminal", fase="F6")


@roteador.get(
    "/v1/terminais/{terminalId}/saude",
    status_code=200,
    operation_id="listarSaudeTerminal",
    summary="Consultar saude do terminal",
    responses=RESPOSTAS_PADRAO,
)
async def listar_saude_terminal(
    terminal_id: Annotated[
        UUID, Path(alias="terminalId", description="Identificador do terminal.")
    ],
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
    cursor: Annotated[
        str | None,
        Query(
            alias="cursor",
            description="Cursor opaco devolvido em paginacao.proximoCursor da pagina anterior. Ausente retorna a primeira pagina. O cursor codifica a ordenacao usada: trocar o parame...",
        ),
    ] = None,
    limite: Annotated[
        int | None, Query(alias="limite", description="Quantidade de itens por pagina.")
    ] = None,
    ordenar: Annotated[
        str | None,
        Query(
            alias="ordenar",
            description="Ordenacao no formato campo:direcao, separando multiplos criterios por virgula. Direcoes aceitas: asc e desc. Campos aceitos sao os documentados em cada opera...",
        ),
    ] = None,
    desde: Annotated[
        datetime | None,
        Query(alias="desde", description="Considera apenas verificacoes a partir deste instante."),
    ] = None,
    somente_offline: Annotated[
        bool | None,
        Query(
            alias="somenteOffline",
            description="Lista apenas as verificacoes em que o terminal estava offline.",
        ),
    ] = None,
) -> contrato.ListaTerminalSaude:
    """Consultar saude do terminal

    Fase 0 entrega andaime: a implementacao entra na fase F6.
    """
    raise NaoImplementado("listarSaudeTerminal", fase="F6")


@roteador.post(
    "/v1/terminais/{terminalId}/sincronizar",
    status_code=202,
    operation_id="sincronizarTerminal",
    summary="Sincronizar terminal",
    responses=RESPOSTAS_PADRAO,
)
async def sincronizar_terminal(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    terminal_id: Annotated[
        UUID, Path(alias="terminalId", description="Identificador do terminal.")
    ],
    corpo: contrato.SincronizacaoTerminalRequisicao,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> contrato.ProcessamentoAssincrono:
    """Sincronizar terminal

    Fase 0 entrega andaime: a implementacao entra na fase F6.
    """
    raise NaoImplementado("sincronizarTerminal", fase="F6")
