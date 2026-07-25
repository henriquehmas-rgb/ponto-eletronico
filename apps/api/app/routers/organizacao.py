"""Rotas da tag `organizacao` do contrato. GERADO -- nao editar.

Estrutura interna da empresa: departamentos, centros de custo, cargos e equipes.
Sustenta escopo de perfil, agrupamento de relatorio e roteamento de aprovacao.

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

roteador = APIRouter(tags=["organizacao"])


@roteador.get(
    "/v1/departamentos",
    status_code=200,
    operation_id="listarDepartamentos",
    summary="Listar departamentos",
    responses=RESPOSTAS_PADRAO,
)
async def listar_departamentos(
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
        UUID | None,
        Query(alias="empresaId", description="Filtra pelos departamentos de uma empresa."),
    ] = None,
    departamento_pai_id: Annotated[
        UUID | None,
        Query(alias="departamentoPaiId", description="Lista os filhos diretos de um departamento."),
    ] = None,
    raiz: Annotated[
        bool | None,
        Query(
            alias="raiz", description="Quando verdadeiro, lista apenas os departamentos sem pai."
        ),
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por departamentos ativos.")
    ] = None,
    busca: Annotated[
        str | None,
        Query(
            alias="busca", description="Busca textual livre sobre os campos indexados do recurso."
        ),
    ] = None,
) -> contrato.ListaDepartamento:
    """Listar departamentos

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("listarDepartamentos", fase="F2")


@roteador.post(
    "/v1/departamentos",
    status_code=201,
    operation_id="criarDepartamento",
    summary="Criar departamento",
    responses=RESPOSTAS_PADRAO,
)
async def criar_departamento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.DepartamentoCriar,
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
) -> contrato.Departamento:
    """Criar departamento

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("criarDepartamento", fase="F2")


@roteador.get(
    "/v1/departamentos/{departamentoId}",
    status_code=200,
    operation_id="obterDepartamento",
    summary="Obter departamento",
    responses=RESPOSTAS_PADRAO,
)
async def obter_departamento(
    departamento_id: Annotated[
        UUID, Path(alias="departamentoId", description="Identificador do departamento.")
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
) -> contrato.Departamento:
    """Obter departamento

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("obterDepartamento", fase="F2")


@roteador.patch(
    "/v1/departamentos/{departamentoId}",
    status_code=200,
    operation_id="atualizarDepartamento",
    summary="Atualizar departamento",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_departamento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    departamento_id: Annotated[
        UUID, Path(alias="departamentoId", description="Identificador do departamento.")
    ],
    corpo: contrato.DepartamentoAtualizar,
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
) -> contrato.Departamento:
    """Atualizar departamento

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("atualizarDepartamento", fase="F2")


@roteador.delete(
    "/v1/departamentos/{departamentoId}",
    status_code=204,
    operation_id="excluirDepartamento",
    summary="Excluir departamento",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def excluir_departamento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    departamento_id: Annotated[
        UUID, Path(alias="departamentoId", description="Identificador do departamento.")
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
    """Excluir departamento

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("excluirDepartamento", fase="F2")


@roteador.get(
    "/v1/centros-custo",
    status_code=200,
    operation_id="listarCentrosCusto",
    summary="Listar centros de custo",
    responses=RESPOSTAS_PADRAO,
)
async def listar_centros_custo(
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
        UUID | None,
        Query(alias="empresaId", description="Filtra pelos centros de custo de uma empresa."),
    ] = None,
    centro_custo_pai_id: Annotated[
        UUID | None, Query(alias="centroCustoPaiId", description="Lista os filhos diretos.")
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por centros de custo ativos.")
    ] = None,
    busca: Annotated[
        str | None,
        Query(
            alias="busca", description="Busca textual livre sobre os campos indexados do recurso."
        ),
    ] = None,
) -> contrato.ListaCentroCusto:
    """Listar centros de custo

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("listarCentrosCusto", fase="F2")


@roteador.post(
    "/v1/centros-custo",
    status_code=201,
    operation_id="criarCentroCusto",
    summary="Criar centro de custo",
    responses=RESPOSTAS_PADRAO,
)
async def criar_centro_custo(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.CentroCustoCriar,
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
) -> contrato.CentroCusto:
    """Criar centro de custo

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("criarCentroCusto", fase="F2")


@roteador.get(
    "/v1/centros-custo/{centroCustoId}",
    status_code=200,
    operation_id="obterCentroCusto",
    summary="Obter centro de custo",
    responses=RESPOSTAS_PADRAO,
)
async def obter_centro_custo(
    centro_custo_id: Annotated[
        UUID, Path(alias="centroCustoId", description="Identificador do centro de custo.")
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
) -> contrato.CentroCusto:
    """Obter centro de custo

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("obterCentroCusto", fase="F2")


@roteador.patch(
    "/v1/centros-custo/{centroCustoId}",
    status_code=200,
    operation_id="atualizarCentroCusto",
    summary="Atualizar centro de custo",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_centro_custo(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    centro_custo_id: Annotated[
        UUID, Path(alias="centroCustoId", description="Identificador do centro de custo.")
    ],
    corpo: contrato.CentroCustoAtualizar,
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
) -> contrato.CentroCusto:
    """Atualizar centro de custo

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("atualizarCentroCusto", fase="F2")


@roteador.get(
    "/v1/cargos",
    status_code=200,
    operation_id="listarCargos",
    summary="Listar cargos",
    responses=RESPOSTAS_PADRAO,
)
async def listar_cargos(
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
        UUID | None, Query(alias="empresaId", description="Filtra pelos cargos de uma empresa.")
    ] = None,
    cbo: Annotated[str | None, Query(alias="cbo", description="Filtra pelo codigo CBO.")] = None,
    nivel: Annotated[
        str | None, Query(alias="nivel", description="Filtra pelo nivel hierarquico.")
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por cargos ativos.")
    ] = None,
    busca: Annotated[
        str | None,
        Query(
            alias="busca", description="Busca textual livre sobre os campos indexados do recurso."
        ),
    ] = None,
) -> contrato.ListaCargo:
    """Listar cargos

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("listarCargos", fase="F2")


@roteador.post(
    "/v1/cargos",
    status_code=201,
    operation_id="criarCargo",
    summary="Criar cargo",
    responses=RESPOSTAS_PADRAO,
)
async def criar_cargo(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.CargoCriar,
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
) -> contrato.Cargo:
    """Criar cargo

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("criarCargo", fase="F2")


@roteador.get(
    "/v1/cargos/{cargoId}",
    status_code=200,
    operation_id="obterCargo",
    summary="Obter cargo",
    responses=RESPOSTAS_PADRAO,
)
async def obter_cargo(
    cargo_id: Annotated[UUID, Path(alias="cargoId", description="Identificador do cargo.")],
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
) -> contrato.Cargo:
    """Obter cargo

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("obterCargo", fase="F2")


@roteador.patch(
    "/v1/cargos/{cargoId}",
    status_code=200,
    operation_id="atualizarCargo",
    summary="Atualizar cargo",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_cargo(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    cargo_id: Annotated[UUID, Path(alias="cargoId", description="Identificador do cargo.")],
    corpo: contrato.CargoAtualizar,
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
) -> contrato.Cargo:
    """Atualizar cargo

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("atualizarCargo", fase="F2")


@roteador.get(
    "/v1/equipes",
    status_code=200,
    operation_id="listarEquipes",
    summary="Listar equipes",
    responses=RESPOSTAS_PADRAO,
)
async def listar_equipes(
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
        UUID | None, Query(alias="empresaId", description="Filtra pelas equipes de uma empresa.")
    ] = None,
    unidade_id: Annotated[
        UUID | None, Query(alias="unidadeId", description="Filtra pelas equipes de uma unidade.")
    ] = None,
    gestor_colaborador_id: Annotated[
        UUID | None,
        Query(alias="gestorColaboradorId", description="Lista as equipes de um gestor."),
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por equipes ativas.")
    ] = None,
    busca: Annotated[
        str | None,
        Query(
            alias="busca", description="Busca textual livre sobre os campos indexados do recurso."
        ),
    ] = None,
) -> contrato.ListaEquipe:
    """Listar equipes

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("listarEquipes", fase="F2")


@roteador.post(
    "/v1/equipes",
    status_code=201,
    operation_id="criarEquipe",
    summary="Criar equipe",
    responses=RESPOSTAS_PADRAO,
)
async def criar_equipe(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.EquipeCriar,
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
) -> contrato.Equipe:
    """Criar equipe

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("criarEquipe", fase="F2")


@roteador.get(
    "/v1/equipes/{equipeId}",
    status_code=200,
    operation_id="obterEquipe",
    summary="Obter equipe",
    responses=RESPOSTAS_PADRAO,
)
async def obter_equipe(
    equipe_id: Annotated[UUID, Path(alias="equipeId", description="Identificador da equipe.")],
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
) -> contrato.Equipe:
    """Obter equipe

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("obterEquipe", fase="F2")


@roteador.patch(
    "/v1/equipes/{equipeId}",
    status_code=200,
    operation_id="atualizarEquipe",
    summary="Atualizar equipe",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_equipe(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    equipe_id: Annotated[UUID, Path(alias="equipeId", description="Identificador da equipe.")],
    corpo: contrato.EquipeAtualizar,
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
) -> contrato.Equipe:
    """Atualizar equipe

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("atualizarEquipe", fase="F2")


@roteador.post(
    "/v1/equipes/{equipeId}/membros",
    status_code=201,
    operation_id="adicionarMembroEquipe",
    summary="Adicionar membro a equipe",
    responses=RESPOSTAS_PADRAO,
)
async def adicionar_membro_equipe(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    equipe_id: Annotated[UUID, Path(alias="equipeId", description="Identificador da equipe.")],
    corpo: contrato.EquipeMembroCriar,
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
) -> contrato.EquipeMembro:
    """Adicionar membro a equipe

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("adicionarMembroEquipe", fase="F2")
