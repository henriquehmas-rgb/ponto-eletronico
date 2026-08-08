"""Rotas da tag `comprovantes` do contrato.

Comprovantes de registro.
A impressao no momento da marcacao e dispensada porque o sistema garante acesso eletronico permanente e a extracao das ultimas 48 horas em aplicativo e navegador, conforme a Portaria MTP 671/2021.

Implementado na fase F5 (agente A3, T11). `obterComprovante` aceita
`Accept: text/plain` (devolve `conteudoTexto` cru) e `application/json`
(devolve o schema `Comprovante` completo), conforme a descricao da operacao
no contrato.

Autenticacao dupla (retrofit de 2026-08-08, decisao do dono do produto --
ver `docs/backlog.md` e a docstring de `app.comum.autenticacao_cliente`): o
contrato ja declarava os tres esquemas alternativos por operacao
(`bearerAuth`/`oauth2`/`apiKeyAuth`), mas so sessao humana era aceita ate
agora. `Depends(exigir_permissao(...))` trocado por
`Depends(exigir_permissao_ou_escopo(...))` -- sessao humana E' tentada
primeiro (comportamento humano preservado byte a byte), cliente de
integracao (OAuth/API key) so entra quando nao ha sessao humana autenticada.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response
from fastapi.responses import PlainTextResponse

from app.comum.autenticacao_cliente import (
    ContextoAcesso,
    aplicar_limite_taxa_se_cliente,
    exigir_permissao_ou_escopo,
)
from app.core.erros import RESPOSTAS_PADRAO
from app.core.seguranca import Sujeito
from app.db.sessao import SessaoDb
from app.marcacao.comprovantes import consulta as consulta_comprovantes
from app.schemas import contrato

roteador = APIRouter(tags=["comprovantes"])

# Uma unica instancia: as tres operacoes deste arquivo compartilham o mesmo
# par (permissao, escopo). Criada no nivel de modulo (nunca chamada de novo
# dentro do handler) para o cache de dependencia do FastAPI, mesmo motivo
# documentado em `app.comum.limitador_taxa`.
_ACESSO_LER = exigir_permissao_ou_escopo(permissao="comprovantes.ler", escopo="marcacoes:ler")


def _sujeito_para_servico(acesso: ContextoAcesso) -> Sujeito:
    """`Sujeito` a repassar para `listar_comprovantes_recentes`, que o usa
    para o alcance hierarquico (`_verificar_acesso_colaborador`: o proprio
    colaborador sempre acessa os seus; qualquer outro depende do alcance).

    Acesso humano devolve o proprio `Sujeito` resolvido, sem nenhuma alteracao
    (comportamento preservado byte a byte). Acesso de cliente de integracao
    devolve um `Sujeito` sintetico so com o `tenant_id`: sem `usuario_id`
    (logo nunca "o proprio colaborador") e sem `alcance` -- exatamente a
    "conta de maquina sem RBAC hierarquico" que `app.core.seguranca.Sujeito`
    ja documenta, e para a qual `exigir_alcance` e permissivo dentro do
    tenant. Mesmo padrao ja usado em `app/routers/admin.py`.
    """
    if acesso.sujeito is not None:
        return acesso.sujeito
    return Sujeito(tenant_id=acesso.tenant_id, autenticado=True)


@roteador.get(
    "/v1/comprovantes",
    status_code=200,
    operation_id="listarComprovantes",
    summary="Listar comprovantes",
    responses=RESPOSTAS_PADRAO,
)
async def listar_comprovantes(
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER)],
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
    colaborador_id: Annotated[
        UUID | None,
        Query(alias="colaboradorId", description="Filtra pelos comprovantes de um colaborador."),
    ] = None,
    marcacao_id: Annotated[
        UUID | None,
        Query(alias="marcacaoId", description="Filtra pelo comprovante de uma marcacao."),
    ] = None,
    cpf: Annotated[
        str | None, Query(alias="cpf", description="Filtra por CPF, somente digitos.")
    ] = None,
    de: Annotated[
        datetime | None,
        Query(alias="de", description="Comprovantes emitidos a partir deste instante."),
    ] = None,
    ate: Annotated[
        datetime | None, Query(alias="ate", description="Comprovantes emitidos ate este instante.")
    ] = None,
) -> contrato.ListaComprovante:
    """Listar comprovantes."""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    return await consulta_comprovantes.listar_comprovantes(
        sessao,
        tenant_id=acesso.tenant_id,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
        colaborador_id=colaborador_id,
        marcacao_id=marcacao_id,
        cpf=cpf,
        de=de,
        ate=ate,
    )


@roteador.get(
    "/v1/comprovantes/{comprovanteId}",
    status_code=200,
    operation_id="obterComprovante",
    summary="Obter comprovante",
    responses=RESPOSTAS_PADRAO,
    # `response_model=None`: o retorno alterna entre `contrato.Comprovante` e
    # `PlainTextResponse` conforme `Accept` (ver docstring da funcao) -- a
    # uniao dos dois nao e um tipo Pydantic valido para o FastAPI inferir
    # `response_model` automaticamente do retorno anotado.
    response_model=None,
)
async def obter_comprovante(
    comprovante_id: Annotated[
        UUID, Path(alias="comprovanteId", description="Identificador do comprovante.")
    ],
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER)],
    sessao: SessaoDb,
    response: Response,
    accept: Annotated[
        str | None,
        Header(
            alias="Accept",
            description="text/plain devolve o corpo textual congelado do comprovante; "
            "application/json (padrao) devolve o schema completo.",
        ),
    ] = None,
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
) -> contrato.Comprovante | PlainTextResponse:
    """Obter comprovante. `Accept: text/plain` devolve `conteudoTexto` cru;
    `application/json` (ou ausencia do cabecalho) devolve o schema completo."""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    comprovante = await consulta_comprovantes.obter_comprovante(
        sessao, tenant_id=acesso.tenant_id, comprovante_id=comprovante_id
    )
    quer_texto = accept is not None and "text/plain" in accept and "application/json" not in accept
    if quer_texto:
        # Devolver um `Response` proprio nao perde os cabecalhos `RateLimit-*`
        # setados acima no `response` injetado: o FastAPI faz
        # `response.headers.raw.extend(sub_response.headers.raw)` tambem
        # quando o handler devolve um `Response` direto.
        return PlainTextResponse(comprovante.conteudo_texto or "")
    return comprovante


@roteador.get(
    "/v1/colaboradores/{colaboradorId}/comprovantes/recentes",
    status_code=200,
    operation_id="listarComprovantesRecentes",
    summary="Listar comprovantes das ultimas 48 horas",
    responses=RESPOSTAS_PADRAO,
)
async def listar_comprovantes_recentes(
    colaborador_id: Annotated[
        UUID, Path(alias="colaboradorId", description="Identificador do colaborador.")
    ],
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER)],
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
    horas: Annotated[
        int | None,
        Query(
            alias="horas",
            description="Janela em horas. O padrao e 48, que e o minimo legal; valores maiores sao aceitos porque o produto mantem os comprovantes disponiveis de forma permanente.",
        ),
    ] = None,
) -> contrato.ListaComprovante:
    """Listar comprovantes das ultimas 48 horas. O proprio colaborador sempre
    acessa os seus; gestor e RH dependem do alcance hierarquico
    (`PONTO-PERM-002` fora dele)."""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    return await consulta_comprovantes.listar_comprovantes_recentes(
        sessao,
        tenant_id=acesso.tenant_id,
        sujeito=_sujeito_para_servico(acesso),
        colaborador_id=colaborador_id,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
        horas=horas,
    )
