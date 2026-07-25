"""Rotas da tag `auditoria` do contrato. GERADO -- nao editar.

Trilha de auditoria append-only e encadeada por hash: cada linha carrega o hash da anterior, o que torna remocao silenciosa detectavel e verificavel sob demanda.

Regra de negocio destas operacoes entra na fase F1. Ate la toda chamada
responde 501 com PONTO-INT-005. Regerar com
`python tools/gerar_do_contrato.py`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query

from app.core.erros import RESPOSTAS_PADRAO, NaoImplementado
from app.schemas import contrato

roteador = APIRouter(tags=["auditoria"])


@roteador.get(
    "/v1/auditoria",
    status_code=200,
    operation_id="listarAuditoria",
    summary="Listar trilha de auditoria",
    responses=RESPOSTAS_PADRAO,
)
async def listar_auditoria(
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
    entidade: Annotated[
        str | None,
        Query(alias="entidade", description="Filtra pela entidade afetada, por exemplo marcacoes."),
    ] = None,
    entidade_id: Annotated[
        UUID | None, Query(alias="entidadeId", description="Filtra pelo registro afetado.")
    ] = None,
    usuario_id: Annotated[
        UUID | None, Query(alias="usuarioId", description="Filtra pelo usuario responsavel.")
    ] = None,
    acao: Annotated[
        str | None, Query(alias="acao", description="Filtra pela acao registrada.")
    ] = None,
    resultado: Annotated[
        str | None, Query(alias="resultado", description="Filtra pelo desfecho.")
    ] = None,
    origem: Annotated[
        str | None, Query(alias="origem", description="Filtra pelo canal de origem.")
    ] = None,
    de: Annotated[
        datetime | None, Query(alias="de", description="Eventos a partir deste instante.")
    ] = None,
    ate: Annotated[
        datetime | None, Query(alias="ate", description="Eventos ate este instante.")
    ] = None,
) -> contrato.ListaRegistroAuditoria:
    """Listar trilha de auditoria

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("listarAuditoria", fase="F1")


@roteador.get(
    "/v1/auditoria/{registroId}",
    status_code=200,
    operation_id="obterRegistroAuditoria",
    summary="Obter registro de auditoria",
    responses=RESPOSTAS_PADRAO,
)
async def obter_registro_auditoria(
    registro_id: Annotated[
        UUID, Path(alias="registroId", description="Identificador do registro de auditoria.")
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
) -> contrato.RegistroAuditoria:
    """Obter registro de auditoria

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("obterRegistroAuditoria", fase="F1")


@roteador.post(
    "/v1/auditoria/verificar-cadeia",
    status_code=200,
    operation_id="verificarCadeiaAuditoria",
    summary="Verificar cadeia de auditoria",
    responses=RESPOSTAS_PADRAO,
)
async def verificar_cadeia_auditoria(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.VerificacaoCadeiaRequisicao,
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
) -> contrato.VerificacaoCadeiaResposta:
    """Verificar cadeia de auditoria

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("verificarCadeiaAuditoria", fase="F1")
