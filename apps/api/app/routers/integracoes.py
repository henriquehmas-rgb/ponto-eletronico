"""Rotas da tag `integracoes` do contrato. GERADO -- nao editar.

Exportadores para sistemas de folha e importadores de planilha, de cadastros e de AFD de terceiros.
Marcacoes importadas de outro fabricante usam namespace de NSR separado e nunca interferem na sequencia do nosso REP-P.

Regra de negocio destas operacoes entra na fase F13. Ate la toda chamada
responde 501 com PONTO-INT-005. Regerar com
`python tools/gerar_do_contrato.py`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query

from app.core.erros import RESPOSTAS_PADRAO, NaoImplementado
from app.schemas import contrato

roteador = APIRouter(tags=["integracoes"])


@roteador.get(
    "/v1/integracoes/folha",
    status_code=200,
    operation_id="listarIntegracoesFolha",
    summary="Listar integracoes de folha",
    responses=RESPOSTAS_PADRAO,
)
async def listar_integracoes_folha(
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
        UUID | None,
        Query(alias="empresaId", description="Filtra pelas integracoes de uma empresa."),
    ] = None,
    parceiro: Annotated[
        str | None, Query(alias="parceiro", description="Filtra pelo sistema de folha de destino.")
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por integracoes ativas.")
    ] = None,
) -> contrato.ListaIntegracaoFolha:
    """Listar integracoes de folha

    Fase 0 entrega andaime: a implementacao entra na fase F13.
    """
    raise NaoImplementado("listarIntegracoesFolha", fase="F13")


@roteador.post(
    "/v1/integracoes/folha",
    status_code=201,
    operation_id="criarIntegracaoFolha",
    summary="Criar integracao de folha",
    responses=RESPOSTAS_PADRAO,
)
async def criar_integracao_folha(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.IntegracaoFolhaCriar,
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
) -> contrato.IntegracaoFolha:
    """Criar integracao de folha

    Fase 0 entrega andaime: a implementacao entra na fase F13.
    """
    raise NaoImplementado("criarIntegracaoFolha", fase="F13")


@roteador.post(
    "/v1/integracoes/folha/{integracaoId}/exportar",
    status_code=202,
    operation_id="exportarFolha",
    summary="Exportar apuracao para a folha",
    responses=RESPOSTAS_PADRAO,
)
async def exportar_folha(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    integracao_id: Annotated[
        UUID, Path(alias="integracaoId", description="Identificador da integracao.")
    ],
    corpo: contrato.ExportacaoFolhaRequisicao,
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
    """Exportar apuracao para a folha

    Fase 0 entrega andaime: a implementacao entra na fase F13.
    """
    raise NaoImplementado("exportarFolha", fase="F13")


@roteador.get(
    "/v1/importacoes",
    status_code=200,
    operation_id="listarImportacoes",
    summary="Listar importacoes",
    responses=RESPOSTAS_PADRAO,
)
async def listar_importacoes(
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
        UUID | None,
        Query(alias="empresaId", description="Filtra pelas importacoes de uma empresa."),
    ] = None,
    tipo: Annotated[
        str | None, Query(alias="tipo", description="Filtra pelo tipo de importacao.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
) -> contrato.ListaImportacao:
    """Listar importacoes

    Fase 0 entrega andaime: a implementacao entra na fase F13.
    """
    raise NaoImplementado("listarImportacoes", fase="F13")


@roteador.post(
    "/v1/importacoes",
    status_code=202,
    operation_id="criarImportacao",
    summary="Criar importacao",
    responses=RESPOSTAS_PADRAO,
)
async def criar_importacao(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.ImportacaoCriar,
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
) -> contrato.Importacao:
    """Criar importacao

    Fase 0 entrega andaime: a implementacao entra na fase F13.
    """
    raise NaoImplementado("criarImportacao", fase="F13")
