"""Rotas da tag `apuracoes` do contrato. GERADO -- nao editar.

Resultado do motor de calculo por vinculo e dia, com decomposicao auditavel de cada bloco de minutos, e as ocorrencias detectadas.
A apuracao e deterministica e recalculavel: mesmos insumos produzem exatamente o mesmo resultado.

Regra de negocio destas operacoes entra na fase F4. Ate la toda chamada
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

roteador = APIRouter(tags=["apuracoes"])


@roteador.get(
    "/v1/apuracoes",
    status_code=200,
    operation_id="listarApuracoes",
    summary="Listar apuracoes do dia",
    responses=RESPOSTAS_PADRAO,
)
async def listar_apuracoes(
    de: Annotated[date, Query(alias="de", description="Primeiro dia do intervalo.")],
    ate: Annotated[date, Query(alias="ate", description="Ultimo dia do intervalo.")],
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
        UUID | None, Query(alias="empresaId", description="Filtra pela empresa.")
    ] = None,
    unidade_id: Annotated[
        UUID | None, Query(alias="unidadeId", description="Filtra pela unidade.")
    ] = None,
    departamento_id: Annotated[
        UUID | None, Query(alias="departamentoId", description="Filtra pelo departamento.")
    ] = None,
    equipe_id: Annotated[
        UUID | None, Query(alias="equipeId", description="Filtra pela equipe.")
    ] = None,
    colaborador_id: Annotated[
        UUID | None, Query(alias="colaboradorId", description="Filtra pelo colaborador.")
    ] = None,
    vinculo_id: Annotated[
        UUID | None, Query(alias="vinculoId", description="Filtra pelo vinculo.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    somente_inconsistentes: Annotated[
        bool | None,
        Query(
            alias="somenteInconsistentes",
            description="Lista apenas dias com marcacao impar, ocorrencia aberta ou apuracao pendente.",
        ),
    ] = None,
    incluir_componentes: Annotated[
        bool | None,
        Query(
            alias="incluirComponentes",
            description="Inclui a decomposicao do calculo em cada dia. Aumenta bastante o volume da resposta.",
        ),
    ] = None,
    incluir_marcacoes: Annotated[
        bool | None,
        Query(
            alias="incluirMarcacoes", description="Inclui as marcacoes consideradas em cada dia."
        ),
    ] = None,
) -> contrato.ListaApuracaoDia:
    """Listar apuracoes do dia

    Fase 0 entrega andaime: a implementacao entra na fase F4.
    """
    raise NaoImplementado("listarApuracoes", fase="F4")


@roteador.get(
    "/v1/apuracoes/{apuracaoId}",
    status_code=200,
    operation_id="obterApuracao",
    summary="Obter apuracao do dia",
    responses=RESPOSTAS_PADRAO,
)
async def obter_apuracao(
    apuracao_id: Annotated[
        UUID, Path(alias="apuracaoId", description="Identificador da apuracao.")
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
) -> contrato.ApuracaoDia:
    """Obter apuracao do dia

    Fase 0 entrega andaime: a implementacao entra na fase F4.
    """
    raise NaoImplementado("obterApuracao", fase="F4")


@roteador.post(
    "/v1/apuracoes/recalcular",
    status_code=202,
    operation_id="recalcularApuracoes",
    summary="Recalcular apuracoes",
    responses=RESPOSTAS_PADRAO,
)
async def recalcular_apuracoes(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.RecalculoRequisicao,
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
    """Recalcular apuracoes

    Fase 0 entrega andaime: a implementacao entra na fase F4.
    """
    raise NaoImplementado("recalcularApuracoes", fase="F4")


@roteador.get(
    "/v1/ocorrencias",
    status_code=200,
    operation_id="listarOcorrencias",
    summary="Listar ocorrencias",
    responses=RESPOSTAS_PADRAO,
)
async def listar_ocorrencias(
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
        UUID | None, Query(alias="empresaId", description="Filtra pela empresa.")
    ] = None,
    unidade_id: Annotated[
        UUID | None, Query(alias="unidadeId", description="Filtra pela unidade.")
    ] = None,
    colaborador_id: Annotated[
        UUID | None, Query(alias="colaboradorId", description="Filtra pelo colaborador.")
    ] = None,
    codigo: Annotated[
        str | None, Query(alias="codigo", description="Filtra pelo tipo de ocorrencia.")
    ] = None,
    severidade: Annotated[
        str | None, Query(alias="severidade", description="Filtra pela gravidade.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    de: Annotated[
        date | None, Query(alias="de", description="Ocorrencias a partir desta data.")
    ] = None,
    ate: Annotated[
        date | None, Query(alias="ate", description="Ocorrencias ate esta data.")
    ] = None,
) -> contrato.ListaOcorrencia:
    """Listar ocorrencias

    Fase 0 entrega andaime: a implementacao entra na fase F4.
    """
    raise NaoImplementado("listarOcorrencias", fase="F4")


@roteador.patch(
    "/v1/ocorrencias/{ocorrenciaId}",
    status_code=200,
    operation_id="atualizarOcorrencia",
    summary="Atualizar ocorrencia",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_ocorrencia(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    ocorrencia_id: Annotated[
        UUID, Path(alias="ocorrenciaId", description="Identificador da ocorrencia.")
    ],
    corpo: contrato.OcorrenciaAtualizar,
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
) -> contrato.Ocorrencia:
    """Atualizar ocorrencia

    Fase 0 entrega andaime: a implementacao entra na fase F4.
    """
    raise NaoImplementado("atualizarOcorrencia", fase="F4")
