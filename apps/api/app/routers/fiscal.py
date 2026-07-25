"""Rotas da tag `fiscal` do contrato. GERADO -- nao editar.

Conformidade REP-P: cadastro do REP-P, geracao de AFD e AEJ e assinatura CAdES com certificado ICP-Brasil.
O AFD deriva EXCLUSIVAMENTE das marcacoes; o AEJ e quem enxerga tratamento, ausencia e banco de horas.
Confundir o escopo dos dois arquivos e o erro que invalida o sistema numa fiscalizacao.

Regra de negocio destas operacoes entra na fase F12. Ate la toda chamada
responde 501 com PONTO-INT-005. Regerar com
`python tools/gerar_do_contrato.py`.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query, Response

from app.core.erros import RESPOSTAS_PADRAO, NaoImplementado
from app.schemas import contrato

roteador = APIRouter(tags=["fiscal"])


@roteador.post(
    "/v1/fiscal/afd",
    status_code=202,
    operation_id="gerarAfd",
    summary="Gerar AFD",
    responses=RESPOSTAS_PADRAO,
)
async def gerar_afd(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.AfdCriar,
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
    """Gerar AFD

    Fase 0 entrega andaime: a implementacao entra na fase F12.
    """
    raise NaoImplementado("gerarAfd", fase="F12")


@roteador.get(
    "/v1/fiscal/afd",
    status_code=200,
    operation_id="listarAfd",
    summary="Listar arquivos AFD",
    responses=RESPOSTAS_PADRAO,
)
async def listar_afd(
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
        UUID | None, Query(alias="empresaId", description="Filtra pelos arquivos de uma empresa.")
    ] = None,
    rep_p_id: Annotated[
        UUID | None, Query(alias="repPId", description="Filtra pelos arquivos de um REP-P.")
    ] = None,
    de: Annotated[
        date | None,
        Query(alias="de", description="Arquivos cujo periodo alcanca esta data ou depois."),
    ] = None,
    ate: Annotated[
        date | None,
        Query(alias="ate", description="Arquivos cujo periodo alcanca esta data ou antes."),
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
) -> contrato.ListaAfdArquivo:
    """Listar arquivos AFD

    Fase 0 entrega andaime: a implementacao entra na fase F12.
    """
    raise NaoImplementado("listarAfd", fase="F12")


@roteador.get(
    "/v1/fiscal/afd/{arquivoId}",
    status_code=200,
    operation_id="obterAfd",
    summary="Obter arquivo AFD",
    responses=RESPOSTAS_PADRAO,
)
async def obter_afd(
    arquivo_id: Annotated[UUID, Path(alias="arquivoId", description="Identificador do arquivo.")],
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
) -> contrato.AfdArquivo:
    """Obter arquivo AFD

    Fase 0 entrega andaime: a implementacao entra na fase F12.
    """
    raise NaoImplementado("obterAfd", fase="F12")


@roteador.get(
    "/v1/fiscal/afd/{arquivoId}/download",
    status_code=200,
    operation_id="baixarAfd",
    summary="Baixar arquivo AFD",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def baixar_afd(
    arquivo_id: Annotated[UUID, Path(alias="arquivoId", description="Identificador do arquivo.")],
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
    incluir_assinatura: Annotated[
        bool | None,
        Query(
            alias="incluirAssinatura",
            description="Devolve um pacote com o arquivo e o .p7s destacado, em vez do arquivo isolado.",
        ),
    ] = None,
) -> Response:
    """Baixar arquivo AFD

    Fase 0 entrega andaime: a implementacao entra na fase F12.
    """
    raise NaoImplementado("baixarAfd", fase="F12")


@roteador.post(
    "/v1/fiscal/aej",
    status_code=202,
    operation_id="gerarAej",
    summary="Gerar AEJ",
    responses=RESPOSTAS_PADRAO,
)
async def gerar_aej(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.AejCriar,
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
    """Gerar AEJ

    Fase 0 entrega andaime: a implementacao entra na fase F12.
    """
    raise NaoImplementado("gerarAej", fase="F12")


@roteador.get(
    "/v1/fiscal/aej",
    status_code=200,
    operation_id="listarAej",
    summary="Listar arquivos AEJ",
    responses=RESPOSTAS_PADRAO,
)
async def listar_aej(
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
        UUID | None, Query(alias="empresaId", description="Filtra pelos arquivos de uma empresa.")
    ] = None,
    periodo_id: Annotated[
        UUID | None, Query(alias="periodoId", description="Filtra pelos arquivos de um periodo.")
    ] = None,
    de: Annotated[
        date | None,
        Query(alias="de", description="Arquivos cujo periodo alcanca esta data ou depois."),
    ] = None,
    ate: Annotated[
        date | None,
        Query(alias="ate", description="Arquivos cujo periodo alcanca esta data ou antes."),
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
) -> contrato.ListaAejArquivo:
    """Listar arquivos AEJ

    Fase 0 entrega andaime: a implementacao entra na fase F12.
    """
    raise NaoImplementado("listarAej", fase="F12")


@roteador.get(
    "/v1/fiscal/aej/{arquivoId}",
    status_code=200,
    operation_id="obterAej",
    summary="Obter arquivo AEJ",
    responses=RESPOSTAS_PADRAO,
)
async def obter_aej(
    arquivo_id: Annotated[UUID, Path(alias="arquivoId", description="Identificador do arquivo.")],
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
) -> contrato.AejArquivo:
    """Obter arquivo AEJ

    Fase 0 entrega andaime: a implementacao entra na fase F12.
    """
    raise NaoImplementado("obterAej", fase="F12")


@roteador.post(
    "/v1/fiscal/arquivos/{arquivoId}/assinar",
    status_code=201,
    operation_id="assinarArquivoFiscal",
    summary="Assinar arquivo fiscal",
    responses=RESPOSTAS_PADRAO,
)
async def assinar_arquivo_fiscal(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    arquivo_id: Annotated[
        UUID, Path(alias="arquivoId", description="Identificador do arquivo a assinar.")
    ],
    corpo: contrato.AssinaturaArquivoRequisicao,
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
) -> contrato.ArquivoAssinatura:
    """Assinar arquivo fiscal

    Fase 0 entrega andaime: a implementacao entra na fase F12.
    """
    raise NaoImplementado("assinarArquivoFiscal", fase="F12")


@roteador.get(
    "/v1/fiscal/rep-ps",
    status_code=200,
    operation_id="listarRepPs",
    summary="Listar REP-P",
    responses=RESPOSTAS_PADRAO,
)
async def listar_rep_ps(
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
        UUID | None, Query(alias="empresaId", description="Filtra pelos REP-P de uma empresa.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
) -> contrato.ListaRepP:
    """Listar REP-P

    Fase 0 entrega andaime: a implementacao entra na fase F12.
    """
    raise NaoImplementado("listarRepPs", fase="F12")


@roteador.post(
    "/v1/fiscal/rep-ps",
    status_code=201,
    operation_id="criarRepP",
    summary="Cadastrar REP-P",
    responses=RESPOSTAS_PADRAO,
)
async def criar_rep_p(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.RepPCriar,
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
) -> contrato.RepP:
    """Cadastrar REP-P

    Fase 0 entrega andaime: a implementacao entra na fase F12.
    """
    raise NaoImplementado("criarRepP", fase="F12")
