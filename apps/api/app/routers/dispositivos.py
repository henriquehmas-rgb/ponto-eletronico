"""Rotas da tag `dispositivos` do contrato. GERADO -- nao editar.

Aparelhos capazes de originar marcacao e seu estado antifraude conhecido.
A regra e de um unico dispositivo ativo por colaborador, e a troca exige aprovacao do RH.

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

roteador = APIRouter(tags=["dispositivos"])


@roteador.get(
    "/v1/dispositivos",
    status_code=200,
    operation_id="listarDispositivos",
    summary="Listar dispositivos",
    responses=RESPOSTAS_PADRAO,
)
async def listar_dispositivos(
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
        Query(alias="empresaId", description="Filtra pelos dispositivos de uma empresa."),
    ] = None,
    unidade_id: Annotated[
        UUID | None,
        Query(alias="unidadeId", description="Filtra pelos dispositivos de uma unidade."),
    ] = None,
    colaborador_id: Annotated[
        UUID | None, Query(alias="colaboradorId", description="Filtra pelo colaborador vinculado.")
    ] = None,
    tipo: Annotated[str | None, Query(alias="tipo", description="Filtra pelo tipo.")] = None,
    plataforma: Annotated[
        str | None, Query(alias="plataforma", description="Filtra pela plataforma.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    attestation_status: Annotated[
        str | None,
        Query(alias="attestationStatus", description="Filtra pelo ultimo veredito de attestation."),
    ] = None,
    com_risco: Annotated[
        bool | None,
        Query(
            alias="comRisco",
            description="Quando verdadeiro, lista apenas dispositivos com root, emulador, modo desenvolvedor ou depuracao USB detectados.",
        ),
    ] = None,
) -> contrato.ListaDispositivo:
    """Listar dispositivos

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("listarDispositivos", fase="F2")


@roteador.post(
    "/v1/dispositivos",
    status_code=201,
    operation_id="criarDispositivo",
    summary="Criar dispositivo",
    responses=RESPOSTAS_PADRAO,
)
async def criar_dispositivo(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.DispositivoCriar,
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
) -> contrato.Dispositivo:
    """Criar dispositivo

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("criarDispositivo", fase="F2")


@roteador.get(
    "/v1/dispositivos/{dispositivoId}",
    status_code=200,
    operation_id="obterDispositivo",
    summary="Obter dispositivo",
    responses=RESPOSTAS_PADRAO,
)
async def obter_dispositivo(
    dispositivo_id: Annotated[
        UUID, Path(alias="dispositivoId", description="Identificador do dispositivo.")
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
) -> contrato.Dispositivo:
    """Obter dispositivo

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("obterDispositivo", fase="F2")


@roteador.patch(
    "/v1/dispositivos/{dispositivoId}",
    status_code=200,
    operation_id="atualizarDispositivo",
    summary="Atualizar dispositivo",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_dispositivo(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    dispositivo_id: Annotated[
        UUID, Path(alias="dispositivoId", description="Identificador do dispositivo.")
    ],
    corpo: contrato.DispositivoAtualizar,
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
) -> contrato.Dispositivo:
    """Atualizar dispositivo

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("atualizarDispositivo", fase="F2")


@roteador.delete(
    "/v1/dispositivos/{dispositivoId}",
    status_code=204,
    operation_id="excluirDispositivo",
    summary="Excluir dispositivo",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def excluir_dispositivo(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    dispositivo_id: Annotated[
        UUID, Path(alias="dispositivoId", description="Identificador do dispositivo.")
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
    """Excluir dispositivo

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("excluirDispositivo", fase="F2")


@roteador.post(
    "/v1/dispositivos/{dispositivoId}/vincular",
    status_code=201,
    operation_id="vincularDispositivo",
    summary="Vincular dispositivo a colaborador",
    responses=RESPOSTAS_PADRAO,
)
async def vincular_dispositivo(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    dispositivo_id: Annotated[
        UUID, Path(alias="dispositivoId", description="Identificador do dispositivo.")
    ],
    corpo: contrato.VinculoDispositivoRequisicao,
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
) -> contrato.Dispositivo:
    """Vincular dispositivo a colaborador

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("vincularDispositivo", fase="F2")
