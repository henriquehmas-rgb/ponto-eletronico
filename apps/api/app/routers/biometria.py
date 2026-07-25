"""Rotas da tag `biometria` do contrato. GERADO -- nao editar.

Credenciais biometricas e equivalentes de fallback.
O vetor biometrico e dado pessoal sensivel: fica cifrado com chave externa ao banco, e versionado por modelo e NUNCA e exposto pela API, nem para o super administrador.

Regra de negocio destas operacoes entra na fase F2. Ate la toda chamada
responde 501 com PONTO-INT-005. Regerar com
`python tools/gerar_do_contrato.py`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query, Response

from app.core.erros import RESPOSTAS_PADRAO, NaoImplementado
from app.schemas import contrato

roteador = APIRouter(tags=["biometria"])


@roteador.get(
    "/v1/biometrias",
    status_code=200,
    operation_id="listarBiometrias",
    summary="Listar credenciais biometricas",
    responses=RESPOSTAS_PADRAO,
)
async def listar_biometrias(
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
    colaborador_id: Annotated[
        UUID | None,
        Query(alias="colaboradorId", description="Filtra pelas credenciais de um colaborador."),
    ] = None,
    modalidade: Annotated[
        str | None, Query(alias="modalidade", description="Filtra pela modalidade.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    versao_modelo: Annotated[
        str | None,
        Query(
            alias="versaoModelo", description="Filtra pela versao do modelo que gerou o template."
        ),
    ] = None,
) -> contrato.ListaBiometria:
    """Listar credenciais biometricas

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("listarBiometrias", fase="F2")


@roteador.post(
    "/v1/biometrias",
    status_code=201,
    operation_id="criarBiometria",
    summary="Cadastrar credencial biometrica",
    responses=RESPOSTAS_PADRAO,
)
async def criar_biometria(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.BiometriaCriar,
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
) -> contrato.Biometria:
    """Cadastrar credencial biometrica

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("criarBiometria", fase="F2")


@roteador.get(
    "/v1/biometrias/{biometriaId}",
    status_code=200,
    operation_id="obterBiometria",
    summary="Obter credencial biometrica",
    responses=RESPOSTAS_PADRAO,
)
async def obter_biometria(
    biometria_id: Annotated[
        UUID, Path(alias="biometriaId", description="Identificador da credencial.")
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
) -> contrato.Biometria:
    """Obter credencial biometrica

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("obterBiometria", fase="F2")


@roteador.delete(
    "/v1/biometrias/{biometriaId}",
    status_code=204,
    operation_id="revogarBiometria",
    summary="Revogar credencial biometrica",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def revogar_biometria(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    biometria_id: Annotated[
        UUID, Path(alias="biometriaId", description="Identificador da credencial.")
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
    """Revogar credencial biometrica

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("revogarBiometria", fase="F2")


@roteador.post(
    "/v1/biometrias/{biometriaId}/validar",
    status_code=200,
    operation_id="validarBiometria",
    summary="Validar credencial biometrica",
    responses=RESPOSTAS_PADRAO,
)
async def validar_biometria(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    biometria_id: Annotated[
        UUID, Path(alias="biometriaId", description="Identificador da credencial.")
    ],
    corpo: contrato.DecisaoRequisicao,
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
) -> contrato.Biometria:
    """Validar credencial biometrica

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("validarBiometria", fase="F2")
