"""Rotas da tag `marcacoes` do contrato. GERADO -- nao editar.

Registro de ponto: o nucleo legal do sistema.
MARCACAO E IMUTAVEL.
Esta tag expoe deliberadamente apenas criacao e leitura.
NAO existe PUT /v1/marcacoes/{id}, NAO existe PATCH e NAO existe DELETE, e essas operacoes nao serao adicionadas em versao futura.
A vedacao nao e preferencia de engenharia: a Portaria MTP 671/2021 veda ao REP alterar ou apagar marcacoes e veda inserir marcacao que nao cor.

Regra de negocio destas operacoes entra na fase F5. Ate la toda chamada
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

roteador = APIRouter(tags=["marcacoes"])


@roteador.post(
    "/v1/marcacoes",
    status_code=201,
    operation_id="criarMarcacao",
    summary="Registrar marcacao de ponto",
    responses=RESPOSTAS_PADRAO,
)
async def criar_marcacao(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.MarcacaoCriar,
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
) -> contrato.MarcacaoCriada:
    """Registrar marcacao de ponto

    Fase 0 entrega andaime: a implementacao entra na fase F5.
    """
    raise NaoImplementado("criarMarcacao", fase="F5")


@roteador.get(
    "/v1/marcacoes",
    status_code=200,
    operation_id="listarMarcacoes",
    summary="Listar marcacoes",
    responses=RESPOSTAS_PADRAO,
)
async def listar_marcacoes(
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
        Query(alias="colaboradorId", description="Filtra pelas marcacoes de um colaborador."),
    ] = None,
    vinculo_id: Annotated[
        UUID | None, Query(alias="vinculoId", description="Filtra pelas marcacoes de um vinculo.")
    ] = None,
    empresa_id: Annotated[
        UUID | None, Query(alias="empresaId", description="Filtra pelas marcacoes de uma empresa.")
    ] = None,
    unidade_id: Annotated[
        UUID | None, Query(alias="unidadeId", description="Filtra pelas marcacoes de uma unidade.")
    ] = None,
    rep_p_id: Annotated[
        UUID | None, Query(alias="repPId", description="Filtra pelas marcacoes de um REP-P.")
    ] = None,
    cpf: Annotated[
        str | None, Query(alias="cpf", description="Filtra por CPF, somente digitos.")
    ] = None,
    canal: Annotated[
        str | None, Query(alias="canal", description="Filtra pelo canal de origem.")
    ] = None,
    de: Annotated[
        datetime | None,
        Query(alias="de", description="Marcacoes a partir deste instante, no fuso da unidade."),
    ] = None,
    ate: Annotated[
        datetime | None,
        Query(alias="ate", description="Marcacoes ate este instante, no fuso da unidade."),
    ] = None,
    nsr_de: Annotated[
        int | None, Query(alias="nsrDe", description="Faixa de NSR: valor inicial.")
    ] = None,
    nsr_ate: Annotated[
        int | None, Query(alias="nsrAte", description="Faixa de NSR: valor final.")
    ] = None,
    coletada_offline: Annotated[
        bool | None,
        Query(
            alias="coletadaOffline", description="Filtra marcacoes que chegaram por fila offline."
        ),
    ] = None,
    incluir_meta: Annotated[
        bool | None,
        Query(
            alias="incluirMeta",
            description="Inclui o contexto antifraude de cada marcacao. Exige permissao sensivel e gera registro de acesso a dado sensivel.",
        ),
    ] = None,
) -> contrato.ListaMarcacao:
    """Listar marcacoes

    Fase 0 entrega andaime: a implementacao entra na fase F5.
    """
    raise NaoImplementado("listarMarcacoes", fase="F5")


@roteador.get(
    "/v1/marcacoes/{marcacaoId}",
    status_code=200,
    operation_id="obterMarcacao",
    summary="Obter marcacao",
    responses=RESPOSTAS_PADRAO,
)
async def obter_marcacao(
    marcacao_id: Annotated[
        UUID, Path(alias="marcacaoId", description="Identificador da marcacao.")
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
) -> contrato.Marcacao:
    """Obter marcacao

    Fase 0 entrega andaime: a implementacao entra na fase F5.
    """
    raise NaoImplementado("obterMarcacao", fase="F5")


@roteador.get(
    "/v1/marcacoes/{marcacaoId}/meta",
    status_code=200,
    operation_id="obterMetaMarcacao",
    summary="Obter contexto antifraude da marcacao",
    responses=RESPOSTAS_PADRAO,
)
async def obter_meta_marcacao(
    marcacao_id: Annotated[
        UUID, Path(alias="marcacaoId", description="Identificador da marcacao.")
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
) -> contrato.MarcacaoMeta:
    """Obter contexto antifraude da marcacao

    Fase 0 entrega andaime: a implementacao entra na fase F5.
    """
    raise NaoImplementado("obterMetaMarcacao", fase="F5")


@roteador.post(
    "/v1/marcacoes/sincronizar-offline",
    status_code=207,
    operation_id="sincronizarMarcacoesOffline",
    summary="Sincronizar fila offline",
    responses=RESPOSTAS_PADRAO,
)
async def sincronizar_marcacoes_offline(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.SincronizacaoOfflineRequisicao,
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
) -> contrato.SincronizacaoOfflineResposta:
    """Sincronizar fila offline

    Fase 0 entrega andaime: a implementacao entra na fase F5.
    """
    raise NaoImplementado("sincronizarMarcacoesOffline", fase="F5")


@roteador.get(
    "/v1/marcacoes/nsr/verificar",
    status_code=200,
    operation_id="verificarSequenciaNsr",
    summary="Verificar continuidade do NSR",
    responses=RESPOSTAS_PADRAO,
)
async def verificar_sequencia_nsr(
    rep_p_id: Annotated[UUID, Query(alias="repPId", description="REP-P a verificar.")],
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
    nsr_de: Annotated[
        int | None, Query(alias="nsrDe", description="Inicio da faixa. Ausente comeca em 1.")
    ] = None,
    nsr_ate: Annotated[
        int | None,
        Query(alias="nsrAte", description="Fim da faixa. Ausente vai ate o ultimo emitido."),
    ] = None,
    verificar_cadeia_hash: Annotated[
        bool | None,
        Query(
            alias="verificarCadeiaHash",
            description="Alem da continuidade numerica, recalcula a cadeia de hash encadeado. Mais lento.",
        ),
    ] = None,
) -> contrato.VerificacaoNsr:
    """Verificar continuidade do NSR

    Fase 0 entrega andaime: a implementacao entra na fase F5.
    """
    raise NaoImplementado("verificarSequenciaNsr", fase="F5")
