"""Rotas da tag `lgpd` do contrato. GERADO -- nao editar.

Consentimentos versionados, registro de acesso a dado sensivel e atendimento aos direitos do titular.
O registro do ponto se apoia em obrigacao legal; a biometria exige consentimento especifico.
Pedido de eliminacao nao apaga marcacao: a guarda e obrigatoria.

Regra de negocio destas operacoes entra na fase F14. Ate la toda chamada
responde 501 com PONTO-INT-005. Regerar com
`python tools/gerar_do_contrato.py`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query, Response

from app.core.erros import RESPOSTAS_PADRAO, NaoImplementado
from app.schemas import contrato

roteador = APIRouter(tags=["lgpd"])


@roteador.get(
    "/v1/lgpd/consentimentos",
    status_code=200,
    operation_id="listarConsentimentos",
    summary="Listar consentimentos",
    responses=RESPOSTAS_PADRAO,
)
async def listar_consentimentos(
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
        Query(alias="colaboradorId", description="Filtra pelos consentimentos de um colaborador."),
    ] = None,
    finalidade: Annotated[
        str | None, Query(alias="finalidade", description="Filtra pela finalidade autorizada.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
) -> contrato.ListaConsentimento:
    """Listar consentimentos

    Fase 0 entrega andaime: a implementacao entra na fase F14.
    """
    raise NaoImplementado("listarConsentimentos", fase="F14")


@roteador.post(
    "/v1/lgpd/consentimentos",
    status_code=201,
    operation_id="criarConsentimento",
    summary="Registrar consentimento",
    responses=RESPOSTAS_PADRAO,
)
async def criar_consentimento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.ConsentimentoCriar,
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
) -> contrato.Consentimento:
    """Registrar consentimento

    Fase 0 entrega andaime: a implementacao entra na fase F14.
    """
    raise NaoImplementado("criarConsentimento", fase="F14")


@roteador.delete(
    "/v1/lgpd/consentimentos/{consentimentoId}",
    status_code=204,
    operation_id="revogarConsentimento",
    summary="Revogar consentimento",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def revogar_consentimento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    consentimento_id: Annotated[
        UUID, Path(alias="consentimentoId", description="Identificador do consentimento.")
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
    """Revogar consentimento

    Fase 0 entrega andaime: a implementacao entra na fase F14.
    """
    raise NaoImplementado("revogarConsentimento", fase="F14")


@roteador.get(
    "/v1/lgpd/solicitacoes-titular",
    status_code=200,
    operation_id="listarSolicitacoesTitular",
    summary="Listar pedidos de titular",
    responses=RESPOSTAS_PADRAO,
)
async def listar_solicitacoes_titular(
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
        UUID | None, Query(alias="colaboradorId", description="Filtra pelos pedidos de um titular.")
    ] = None,
    tipo: Annotated[
        str | None, Query(alias="tipo", description="Filtra pelo direito exercido.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    vencendo: Annotated[
        bool | None,
        Query(
            alias="vencendo", description="Lista apenas pedidos com prazo proximo do vencimento."
        ),
    ] = None,
) -> contrato.ListaSolicitacaoTitular:
    """Listar pedidos de titular

    Fase 0 entrega andaime: a implementacao entra na fase F14.
    """
    raise NaoImplementado("listarSolicitacoesTitular", fase="F14")


@roteador.post(
    "/v1/lgpd/solicitacoes-titular",
    status_code=201,
    operation_id="criarSolicitacaoTitular",
    summary="Registrar pedido de titular",
    responses=RESPOSTAS_PADRAO,
)
async def criar_solicitacao_titular(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.SolicitacaoTitularCriar,
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
) -> contrato.SolicitacaoTitular:
    """Registrar pedido de titular

    Fase 0 entrega andaime: a implementacao entra na fase F14.
    """
    raise NaoImplementado("criarSolicitacaoTitular", fase="F14")


@roteador.get(
    "/v1/lgpd/acessos-sensiveis",
    status_code=200,
    operation_id="listarAcessosSensiveis",
    summary="Listar acessos a dados sensiveis",
    responses=RESPOSTAS_PADRAO,
)
async def listar_acessos_sensiveis(
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
    usuario_id: Annotated[
        UUID | None, Query(alias="usuarioId", description="Filtra pelos acessos de um usuario.")
    ] = None,
    colaborador_id: Annotated[
        UUID | None,
        Query(alias="colaboradorId", description="Filtra pelos acessos ao dado de um titular."),
    ] = None,
    categoria: Annotated[
        str | None, Query(alias="categoria", description="Filtra pela categoria do dado.")
    ] = None,
    acao: Annotated[
        str | None, Query(alias="acao", description="Filtra pela operacao realizada.")
    ] = None,
    de: Annotated[
        datetime | None, Query(alias="de", description="Acessos a partir deste instante.")
    ] = None,
    ate: Annotated[
        datetime | None, Query(alias="ate", description="Acessos ate este instante.")
    ] = None,
) -> contrato.ListaAcessoDadoSensivel:
    """Listar acessos a dados sensiveis

    Fase 0 entrega andaime: a implementacao entra na fase F14.
    """
    raise NaoImplementado("listarAcessosSensiveis", fase="F14")
