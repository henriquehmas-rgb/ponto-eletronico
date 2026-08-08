"""Rotas da tag `terminais` do contrato.

Coletores fisicos, tipicamente Control iD iDFace.
IMPORTANTE: o terminal NAO e o REP-P.
Ele identifica a pessoa e produz um registro de acesso; quem atribui o NSR e grava no AFD e o nosso software.

Regra de negocio implementada na fase F6 (agente A1, ownership deste arquivo --
ver `docs/fases/F06-integracao-control-id.md`, secao 5). A regra em si vive em
`app.terminais.servico`; este modulo so traduz HTTP <-> servico, no mesmo
padrao estrutural de `app/routers/colaboradores.py` (F2).

Autenticacao dupla (retrofit de 2026-08-08, decisao do dono do produto
apesar de F14/A2 ter deixado como "sem valor de produto validado ainda",
ver `docs/backlog.md`): contrato ja declarava os tres esquemas alternativos
por operacao (`bearerAuth`/`oauth2`/`apiKeyAuth`), mas so sessao humana era
aceita ate agora. `Depends(exigir_permissao(...))` trocado por
`Depends(exigir_permissao_ou_escopo(...))` (mesmo combinador ja provado em
`app/routers/webhooks.py`/F13) -- sessao humana E' tentada primeiro
(comportamento humano preservado byte a byte), cliente de integracao (OAuth/
API key) so entra quando nao ha sessao humana autenticada.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response

from app.comum.autenticacao_cliente import (
    ContextoAcesso,
    aplicar_limite_taxa_se_cliente,
    exigir_permissao_ou_escopo,
    usuario_id_do_acesso,
)
from app.comum.limitador_taxa import exigir_limite_taxa_sessao
from app.core.config import obter_configuracao
from app.core.erros import RESPOSTAS_PADRAO
from app.db.sessao import SessaoDb
from app.schemas import contrato
from app.terminais import servico

roteador = APIRouter(tags=["terminais"])

# Uma instancia por par (permissao, escopo) -- nao uma fabrica chamada de novo
# dentro do handler: mesmo motivo documentado em `app.comum.limitador_taxa`
# (identidade estavel do *callable* pro cache de dependencia do FastAPI).
_ACESSO_TERMINAIS_LER = exigir_permissao_ou_escopo(
    permissao="terminais.ler", escopo="dispositivos:ler"
)
_ACESSO_TERMINAIS_CRIAR = exigir_permissao_ou_escopo(
    permissao="terminais.criar", escopo="dispositivos:escrever"
)
_ACESSO_TERMINAIS_EDITAR = exigir_permissao_ou_escopo(
    permissao="terminais.editar", escopo="dispositivos:escrever"
)
_ACESSO_TERMINAIS_EXCLUIR = exigir_permissao_ou_escopo(
    permissao="terminais.excluir", escopo="dispositivos:escrever"
)
_ACESSO_TERMINAIS_EXECUTAR = exigir_permissao_ou_escopo(
    permissao="terminais.executar", escopo="dispositivos:escrever"
)


@roteador.get(
    "/v1/terminais",
    status_code=200,
    operation_id="listarTerminais",
    summary="Listar terminais",
    responses=RESPOSTAS_PADRAO,
)
async def listar_terminais(
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_TERMINAIS_LER)],
    sessao: SessaoDb,
    response: Response,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
    cursor: Annotated[
        str | None,
        Query(
            alias="cursor",
            description="Cursor opaco devolvido em paginacao.proximoCursor da pagina anterior. Ausente retorna a primeira pagina. O cursor codifica a ordenacao usada: trocar o…",
        ),
    ] = None,
    limite: Annotated[
        int | None, Query(alias="limite", description="Quantidade de itens por pagina.")
    ] = None,
    ordenar: Annotated[
        str | None,
        Query(
            alias="ordenar",
            description="Ordenacao no formato campo:direcao, separando multiplos criterios por virgula. Direcoes aceitas: asc e desc. Campos aceitos sao os documentados em cada…",
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
    """Listar terminais"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    linhas, paginacao = await servico.listar_terminais(
        sessao,
        acesso.tenant_id,
        empresa_id=empresa_id,
        unidade_id=unidade_id,
        fabricante=fabricante,
        status=status,
        online=online,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [servico.montar_resposta_terminal(linha) for linha in linhas]
    return contrato.ListaTerminal(dados=dados, paginacao=paginacao)


@roteador.post(
    "/v1/terminais",
    status_code=201,
    operation_id="criarTerminal",
    summary="Criar terminal",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def criar_terminal(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.TerminalCriar,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_TERMINAIS_CRIAR)],
    sessao: SessaoDb,
    response: Response,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
) -> contrato.Terminal:
    """Criar terminal"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    terminal = await servico.criar_terminal(
        sessao, acesso.tenant_id, corpo, usuario_id_do_acesso(acesso)
    )
    return servico.montar_resposta_terminal(terminal)


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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_TERMINAIS_LER)],
    sessao: SessaoDb,
    response: Response,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
) -> contrato.Terminal:
    """Obter terminal"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    terminal = await servico.obter_terminal(sessao, acesso.tenant_id, terminal_id)
    return servico.montar_resposta_terminal(terminal)


@roteador.patch(
    "/v1/terminais/{terminalId}",
    status_code=200,
    operation_id="atualizarTerminal",
    summary="Atualizar terminal",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def atualizar_terminal(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    terminal_id: Annotated[
        UUID, Path(alias="terminalId", description="Identificador do terminal.")
    ],
    corpo: contrato.TerminalAtualizar,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_TERMINAIS_EDITAR)],
    sessao: SessaoDb,
    response: Response,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
) -> contrato.Terminal:
    """Atualizar terminal"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    terminal = await servico.atualizar_terminal(
        sessao, acesso.tenant_id, terminal_id, corpo, usuario_id_do_acesso(acesso)
    )
    return servico.montar_resposta_terminal(terminal)


@roteador.delete(
    "/v1/terminais/{terminalId}",
    status_code=204,
    operation_id="excluirTerminal",
    summary="Excluir terminal",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def excluir_terminal(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    terminal_id: Annotated[
        UUID, Path(alias="terminalId", description="Identificador do terminal.")
    ],
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_TERMINAIS_EXCLUIR)],
    sessao: SessaoDb,
    response: Response,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
) -> Response:
    """Excluir terminal"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    await servico.excluir_terminal(
        sessao, acesso.tenant_id, terminal_id, usuario_id_do_acesso(acesso)
    )
    # Reaproveita o `response` injetado (ja carrega os cabecalhos `RateLimit-*`
    # setados acima, quando o acesso e de cliente de integracao) em vez de
    # construir um `Response` novo, que perderia esses cabecalhos.
    response.status_code = 204
    return response


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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_TERMINAIS_LER)],
    sessao: SessaoDb,
    response: Response,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
    cursor: Annotated[
        str | None,
        Query(
            alias="cursor",
            description="Cursor opaco devolvido em paginacao.proximoCursor da pagina anterior. Ausente retorna a primeira pagina. O cursor codifica a ordenacao usada: trocar o…",
        ),
    ] = None,
    limite: Annotated[
        int | None, Query(alias="limite", description="Quantidade de itens por pagina.")
    ] = None,
    ordenar: Annotated[
        str | None,
        Query(
            alias="ordenar",
            description="Ordenacao no formato campo:direcao, separando multiplos criterios por virgula. Direcoes aceitas: asc e desc. Campos aceitos sao os documentados em cada…",
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
    """Consultar saude do terminal"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    linhas, paginacao = await servico.listar_saude_terminal(
        sessao,
        acesso.tenant_id,
        terminal_id,
        desde=desde,
        somente_offline=somente_offline,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [contrato.TerminalSaude.model_validate(linha, from_attributes=True) for linha in linhas]
    return contrato.ListaTerminalSaude(dados=dados, paginacao=paginacao)


@roteador.post(
    "/v1/terminais/{terminalId}/sincronizar",
    status_code=202,
    operation_id="sincronizarTerminal",
    summary="Sincronizar terminal",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def sincronizar_terminal(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    terminal_id: Annotated[
        UUID, Path(alias="terminalId", description="Identificador do terminal.")
    ],
    corpo: contrato.SincronizacaoTerminalRequisicao,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_TERMINAIS_EXECUTAR)],
    sessao: SessaoDb,
    response: Response,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
) -> contrato.ProcessamentoAssincrono:
    """Sincronizar terminal"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    config = obter_configuracao()
    return await servico.sincronizar_terminal(
        sessao,
        acesso.tenant_id,
        terminal_id,
        corpo,
        usuario_id=usuario_id_do_acesso(acesso),
        redis_url=config.redis_url,
    )
