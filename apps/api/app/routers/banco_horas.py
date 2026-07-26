"""Rotas da tag `banco-horas` do contrato. GERADO -- nao editar.

Contas-corrente de horas, extrato imutavel encadeado por hash, quitacoes e politicas de regime.
O limite legal e imposto pelo contrato: acordo individual escrito compensa em ate 6 meses, acordo ou convencao coletiva em ate 12.

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

roteador = APIRouter(tags=["banco-horas"])


@roteador.get(
    "/v1/banco-horas/{colaboradorId}/extrato",
    status_code=200,
    operation_id="obterExtratoBancoHoras",
    summary="Obter extrato de banco de horas",
    responses=RESPOSTAS_PADRAO,
)
async def obter_extrato_banco_horas(
    colaborador_id: Annotated[
        UUID, Path(alias="colaboradorId", description="Identificador do colaborador.")
    ],
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
    cursor: Annotated[
        str | None,
        Query(
            alias="cursor",
            description="Cursor opaco devolvido em paginacao.proximoCursor da pagina anterior. Ausente retorna a primeira pagina. O cursor codifica a ordenacao usada: trocar o…",
        ),
    ] = None,
    limite: Annotated[
        int | None, Query(alias="limite", description="Quantidade de itens por pagina.")
    ] = None,
    vinculo_id: Annotated[
        UUID | None, Query(alias="vinculoId", description="Restringe a um vinculo especifico.")
    ] = None,
    conta_id: Annotated[
        UUID | None, Query(alias="contaId", description="Restringe a uma conta especifica.")
    ] = None,
    conta_codigo: Annotated[
        str | None,
        Query(
            alias="contaCodigo",
            description="Restringe pela conta identificada por codigo, por exemplo normal.",
        ),
    ] = None,
    de: Annotated[date | None, Query(alias="de", description="Primeiro dia do intervalo.")] = None,
    ate: Annotated[date | None, Query(alias="ate", description="Ultimo dia do intervalo.")] = None,
    tipo: Annotated[
        str | None, Query(alias="tipo", description="Filtra pelo tipo de lancamento.")
    ] = None,
) -> contrato.ExtratoBancoHoras:
    """Obter extrato de banco de horas

    Fase 0 entrega andaime: a implementacao entra na fase F4.
    """
    raise NaoImplementado("obterExtratoBancoHoras", fase="F4")


@roteador.get(
    "/v1/banco-horas/{colaboradorId}/saldo",
    status_code=200,
    operation_id="obterSaldoBancoHoras",
    summary="Obter saldo de banco de horas",
    responses=RESPOSTAS_PADRAO,
)
async def obter_saldo_banco_horas(
    colaborador_id: Annotated[
        UUID, Path(alias="colaboradorId", description="Identificador do colaborador.")
    ],
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
    vinculo_id: Annotated[
        UUID | None, Query(alias="vinculoId", description="Restringe a um vinculo especifico.")
    ] = None,
    conta_codigo: Annotated[
        str | None,
        Query(alias="contaCodigo", description="Restringe a uma conta identificada por codigo."),
    ] = None,
    data_referencia: Annotated[
        date | None,
        Query(
            alias="dataReferencia",
            description="Calcula o saldo na data informada. Ausente usa a data corrente.",
        ),
    ] = None,
) -> contrato.SaldoBancoHoras:
    """Obter saldo de banco de horas

    Fase 0 entrega andaime: a implementacao entra na fase F4.
    """
    raise NaoImplementado("obterSaldoBancoHoras", fase="F4")


@roteador.post(
    "/v1/banco-horas/simular",
    status_code=200,
    operation_id="simularBancoHoras",
    summary="Simular impacto no saldo",
    responses=RESPOSTAS_PADRAO,
)
async def simular_banco_horas(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.SimulacaoBancoRequisicao,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
) -> contrato.SimulacaoBancoResposta:
    """Simular impacto no saldo

    Fase 0 entrega andaime: a implementacao entra na fase F4.
    """
    raise NaoImplementado("simularBancoHoras", fase="F4")


@roteador.get(
    "/v1/banco-horas/contas",
    status_code=200,
    operation_id="listarContasBancoHoras",
    summary="Listar contas de banco de horas",
    responses=RESPOSTAS_PADRAO,
)
async def listar_contas_banco_horas(
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
    cursor: Annotated[
        str | None,
        Query(
            alias="cursor",
            description="Cursor opaco devolvido em paginacao.proximoCursor da pagina anterior. Ausente retorna a primeira pagina. O cursor codifica a ordenacao usada: trocar o…",
        ),
    ] = None,
    limite: Annotated[
        int | None, Query(alias="limite", description="Quantidade de itens por pagina.")
    ] = None,
    ordenar: Annotated[
        str | None,
        Query(
            alias="ordenar",
            description="Ordenacao no formato campo:direcao, separando multiplos criterios por virgula. Direcoes aceitas: asc e desc. Campos aceitos sao os documentados em cada…",
        ),
    ] = None,
    colaborador_id: Annotated[
        UUID | None,
        Query(alias="colaboradorId", description="Filtra pelas contas de um colaborador."),
    ] = None,
    vinculo_id: Annotated[
        UUID | None, Query(alias="vinculoId", description="Filtra pelas contas de um vinculo.")
    ] = None,
    empresa_id: Annotated[
        UUID | None, Query(alias="empresaId", description="Filtra pelas contas de uma empresa.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    vence_ate: Annotated[
        date | None,
        Query(
            alias="venceAte", description="Lista contas cujo periodo termina ate a data informada."
        ),
    ] = None,
    com_saldo_negativo: Annotated[
        bool | None,
        Query(alias="comSaldoNegativo", description="Lista apenas contas com saldo devedor."),
    ] = None,
) -> contrato.ListaBhConta:
    """Listar contas de banco de horas

    Fase 0 entrega andaime: a implementacao entra na fase F4.
    """
    raise NaoImplementado("listarContasBancoHoras", fase="F4")


@roteador.post(
    "/v1/banco-horas/contas",
    status_code=201,
    operation_id="criarContaBancoHoras",
    summary="Criar conta de banco de horas",
    responses=RESPOSTAS_PADRAO,
)
async def criar_conta_banco_horas(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.BhContaCriar,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
) -> contrato.BhConta:
    """Criar conta de banco de horas

    Fase 0 entrega andaime: a implementacao entra na fase F4.
    """
    raise NaoImplementado("criarContaBancoHoras", fase="F4")


@roteador.post(
    "/v1/banco-horas/quitacoes",
    status_code=201,
    operation_id="criarQuitacaoBancoHoras",
    summary="Registrar quitacao de banco de horas",
    responses=RESPOSTAS_PADRAO,
)
async def criar_quitacao_banco_horas(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.BhQuitacaoCriar,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
) -> contrato.BhQuitacao:
    """Registrar quitacao de banco de horas

    Fase 0 entrega andaime: a implementacao entra na fase F4.
    """
    raise NaoImplementado("criarQuitacaoBancoHoras", fase="F4")


@roteador.get(
    "/v1/banco-horas/politicas",
    status_code=200,
    operation_id="listarPoliticasBancoHoras",
    summary="Listar politicas de banco de horas",
    responses=RESPOSTAS_PADRAO,
)
async def listar_politicas_banco_horas(
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
    cursor: Annotated[
        str | None,
        Query(
            alias="cursor",
            description="Cursor opaco devolvido em paginacao.proximoCursor da pagina anterior. Ausente retorna a primeira pagina. O cursor codifica a ordenacao usada: trocar o…",
        ),
    ] = None,
    limite: Annotated[
        int | None, Query(alias="limite", description="Quantidade de itens por pagina.")
    ] = None,
    ordenar: Annotated[
        str | None,
        Query(
            alias="ordenar",
            description="Ordenacao no formato campo:direcao, separando multiplos criterios por virgula. Direcoes aceitas: asc e desc. Campos aceitos sao os documentados em cada…",
        ),
    ] = None,
    empresa_id: Annotated[
        UUID | None, Query(alias="empresaId", description="Filtra pelas politicas de uma empresa.")
    ] = None,
    regime: Annotated[str | None, Query(alias="regime", description="Filtra pelo regime.")] = None,
    vigente_em: Annotated[
        date | None,
        Query(
            alias="vigenteEm", description="Considera apenas politicas vigentes na data informada."
        ),
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por politicas ativas.")
    ] = None,
) -> contrato.ListaBhPolitica:
    """Listar politicas de banco de horas

    Fase 0 entrega andaime: a implementacao entra na fase F4.
    """
    raise NaoImplementado("listarPoliticasBancoHoras", fase="F4")


@roteador.post(
    "/v1/banco-horas/politicas",
    status_code=201,
    operation_id="criarPoliticaBancoHoras",
    summary="Criar politica de banco de horas",
    responses=RESPOSTAS_PADRAO,
)
async def criar_politica_banco_horas(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.BhPoliticaCriar,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
) -> contrato.BhPolitica:
    """Criar politica de banco de horas

    Fase 0 entrega andaime: a implementacao entra na fase F4.
    """
    raise NaoImplementado("criarPoliticaBancoHoras", fase="F4")
