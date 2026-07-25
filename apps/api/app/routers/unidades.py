"""Rotas da tag `unidades` do contrato. GERADO -- nao editar.

Locais fisicos de trabalho.
A unidade carrega o fuso efetivo da apuracao, a geocerca do registro por aplicativo, a allowlist de faixas CIDR do registro por navegador e os conjuntos de feriados aplicaveis.

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

roteador = APIRouter(tags=["unidades"])


@roteador.get(
    "/v1/unidades",
    status_code=200,
    operation_id="listarUnidades",
    summary="Listar unidades",
    responses=RESPOSTAS_PADRAO,
)
async def listar_unidades(
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
        UUID | None, Query(alias="empresaId", description="Filtra pelas unidades de uma empresa.")
    ] = None,
    tipo: Annotated[
        str | None, Query(alias="tipo", description="Filtra pelo tipo de local.")
    ] = None,
    uf: Annotated[
        str | None, Query(alias="uf", description="Filtra pela unidade federativa.")
    ] = None,
    com_geocerca: Annotated[
        bool | None,
        Query(alias="comGeocerca", description="Filtra unidades com ou sem geocerca configurada."),
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por unidades ativas ou inativas.")
    ] = None,
    busca: Annotated[
        str | None,
        Query(
            alias="busca", description="Busca textual livre sobre os campos indexados do recurso."
        ),
    ] = None,
    incluir_excluidos: Annotated[
        bool | None,
        Query(
            alias="incluirExcluidos",
            description="Inclui registros com exclusao logica (excluidoEm preenchido) no resultado.",
        ),
    ] = None,
) -> contrato.ListaUnidade:
    """Listar unidades

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("listarUnidades", fase="F2")


@roteador.post(
    "/v1/unidades",
    status_code=201,
    operation_id="criarUnidade",
    summary="Criar unidade",
    responses=RESPOSTAS_PADRAO,
)
async def criar_unidade(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.UnidadeCriar,
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
) -> contrato.Unidade:
    """Criar unidade

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("criarUnidade", fase="F2")


@roteador.get(
    "/v1/unidades/{unidadeId}",
    status_code=200,
    operation_id="obterUnidade",
    summary="Obter unidade",
    responses=RESPOSTAS_PADRAO,
)
async def obter_unidade(
    unidade_id: Annotated[UUID, Path(alias="unidadeId", description="Identificador da unidade.")],
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
) -> contrato.Unidade:
    """Obter unidade

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("obterUnidade", fase="F2")


@roteador.patch(
    "/v1/unidades/{unidadeId}",
    status_code=200,
    operation_id="atualizarUnidade",
    summary="Atualizar unidade",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_unidade(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    unidade_id: Annotated[UUID, Path(alias="unidadeId", description="Identificador da unidade.")],
    corpo: contrato.UnidadeAtualizar,
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
) -> contrato.Unidade:
    """Atualizar unidade

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("atualizarUnidade", fase="F2")


@roteador.delete(
    "/v1/unidades/{unidadeId}",
    status_code=204,
    operation_id="excluirUnidade",
    summary="Excluir unidade",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def excluir_unidade(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    unidade_id: Annotated[UUID, Path(alias="unidadeId", description="Identificador da unidade.")],
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
    """Excluir unidade

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("excluirUnidade", fase="F2")


@roteador.get(
    "/v1/unidades/{unidadeId}/redes-permitidas",
    status_code=200,
    operation_id="listarRedesPermitidas",
    summary="Listar faixas de rede permitidas",
    responses=RESPOSTAS_PADRAO,
)
async def listar_redes_permitidas(
    unidade_id: Annotated[UUID, Path(alias="unidadeId", description="Identificador da unidade.")],
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
    canal: Annotated[
        str | None, Query(alias="canal", description="Filtra pelo canal restrito.")
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por faixas ativas.")
    ] = None,
) -> contrato.ListaRedePermitida:
    """Listar faixas de rede permitidas

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("listarRedesPermitidas", fase="F2")


@roteador.post(
    "/v1/unidades/{unidadeId}/redes-permitidas",
    status_code=201,
    operation_id="criarRedePermitida",
    summary="Adicionar faixa de rede permitida",
    responses=RESPOSTAS_PADRAO,
)
async def criar_rede_permitida(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    unidade_id: Annotated[UUID, Path(alias="unidadeId", description="Identificador da unidade.")],
    corpo: contrato.RedePermitidaCriar,
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
) -> contrato.RedePermitida:
    """Adicionar faixa de rede permitida

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("criarRedePermitida", fase="F2")


@roteador.delete(
    "/v1/unidades/{unidadeId}/redes-permitidas/{redeId}",
    status_code=204,
    operation_id="excluirRedePermitida",
    summary="Remover faixa de rede permitida",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def excluir_rede_permitida(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    unidade_id: Annotated[UUID, Path(alias="unidadeId", description="Identificador da unidade.")],
    rede_id: Annotated[UUID, Path(alias="redeId", description="Identificador da faixa.")],
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
    """Remover faixa de rede permitida

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("excluirRedePermitida", fase="F2")
