"""Rotas da tag `contratos` do contrato. GERADO -- nao editar.

Contratos e vinculos.
O VINCULO, e nao o colaborador, e a chave da apuracao: jornada vigente, escala, apuracao do dia e conta de banco de horas penduram nele.
Um colaborador pode ter mais de um vinculo simultaneo.

Regra de negocio destas operacoes entra na fase F2. Ate la toda chamada
responde 501 com PONTO-INT-005. Regerar com
`python tools/gerar_do_contrato.py`.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query

from app.core.erros import RESPOSTAS_PADRAO, NaoImplementado
from app.schemas import contrato

roteador = APIRouter(tags=["contratos"])


@roteador.get(
    "/v1/contratos",
    status_code=200,
    operation_id="listarContratos",
    summary="Listar contratos",
    responses=RESPOSTAS_PADRAO,
)
async def listar_contratos(
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
        Query(alias="colaboradorId", description="Filtra pelos contratos de um colaborador."),
    ] = None,
    empresa_id: Annotated[
        UUID | None, Query(alias="empresaId", description="Filtra pelos contratos de uma empresa.")
    ] = None,
    tipo: Annotated[
        str | None, Query(alias="tipo", description="Filtra pela modalidade de contratacao.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    vigente_em: Annotated[
        date | None,
        Query(
            alias="vigenteEm", description="Considera apenas contratos vigentes na data informada."
        ),
    ] = None,
) -> contrato.ListaContrato:
    """Listar contratos

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("listarContratos", fase="F2")


@roteador.post(
    "/v1/contratos",
    status_code=201,
    operation_id="criarContrato",
    summary="Criar contrato",
    responses=RESPOSTAS_PADRAO,
)
async def criar_contrato(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.ContratoCriar,
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
) -> contrato.Contrato:
    """Criar contrato

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("criarContrato", fase="F2")


@roteador.get(
    "/v1/contratos/{contratoId}",
    status_code=200,
    operation_id="obterContrato",
    summary="Obter contrato",
    responses=RESPOSTAS_PADRAO,
)
async def obter_contrato(
    contrato_id: Annotated[
        UUID, Path(alias="contratoId", description="Identificador do contrato.")
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
) -> contrato.Contrato:
    """Obter contrato

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("obterContrato", fase="F2")


@roteador.patch(
    "/v1/contratos/{contratoId}",
    status_code=200,
    operation_id="atualizarContrato",
    summary="Atualizar contrato",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_contrato(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    contrato_id: Annotated[
        UUID, Path(alias="contratoId", description="Identificador do contrato.")
    ],
    corpo: contrato.ContratoAtualizar,
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
) -> contrato.Contrato:
    """Atualizar contrato

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("atualizarContrato", fase="F2")


@roteador.get(
    "/v1/vinculos",
    status_code=200,
    operation_id="listarVinculos",
    summary="Listar vinculos",
    responses=RESPOSTAS_PADRAO,
)
async def listar_vinculos(
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
        Query(alias="colaboradorId", description="Filtra pelos vinculos de um colaborador."),
    ] = None,
    empresa_id: Annotated[
        UUID | None, Query(alias="empresaId", description="Filtra pelos vinculos de uma empresa.")
    ] = None,
    unidade_id: Annotated[
        UUID | None, Query(alias="unidadeId", description="Filtra pela unidade de lotacao.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    apura_ponto: Annotated[
        bool | None,
        Query(alias="apuraPonto", description="Filtra vinculos sujeitos ou nao a apuracao."),
    ] = None,
    vigente_em: Annotated[
        date | None,
        Query(
            alias="vigenteEm", description="Considera apenas vinculos vigentes na data informada."
        ),
    ] = None,
) -> contrato.ListaVinculo:
    """Listar vinculos

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("listarVinculos", fase="F2")


@roteador.post(
    "/v1/vinculos",
    status_code=201,
    operation_id="criarVinculo",
    summary="Criar vinculo",
    responses=RESPOSTAS_PADRAO,
)
async def criar_vinculo(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.VinculoCriar,
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
) -> contrato.Vinculo:
    """Criar vinculo

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("criarVinculo", fase="F2")


@roteador.get(
    "/v1/vinculos/{vinculoId}",
    status_code=200,
    operation_id="obterVinculo",
    summary="Obter vinculo",
    responses=RESPOSTAS_PADRAO,
)
async def obter_vinculo(
    vinculo_id: Annotated[UUID, Path(alias="vinculoId", description="Identificador do vinculo.")],
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
) -> contrato.Vinculo:
    """Obter vinculo

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("obterVinculo", fase="F2")


@roteador.post(
    "/v1/vinculos/{vinculoId}/encerrar",
    status_code=200,
    operation_id="encerrarVinculo",
    summary="Encerrar vinculo",
    responses=RESPOSTAS_PADRAO,
)
async def encerrar_vinculo(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    vinculo_id: Annotated[UUID, Path(alias="vinculoId", description="Identificador do vinculo.")],
    corpo: contrato.EncerramentoVinculoRequisicao,
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
) -> contrato.Vinculo:
    """Encerrar vinculo

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("encerrarVinculo", fase="F2")
