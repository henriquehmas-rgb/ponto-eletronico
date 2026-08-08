"""Rotas da tag `banco-horas` do contrato.

Contas-corrente de horas, extrato imutavel encadeado por hash, quitacoes e politicas de regime.
O limite legal e imposto pelo contrato: acordo individual escrito compensa em ate 6 meses, acordo ou convencao coletiva em ate 12.

Regra de negocio implementada na fase F4 (agente A2, ownership deste arquivo --
ver `docs/fases/F04-calculo-banco-de-horas.md`, secao 5). A regra em si vive em
`app.apuracao.banco_horas.*`; este modulo so traduz HTTP <-> servico, no mesmo
padrao de `app/routers/contratos.py` (F2).

Autenticacao dupla (retrofit de 2026-08-08, decisao do dono do produto): o
contrato ja declarava os tres esquemas alternativos por operacao
(`bearerAuth`/`oauth2`/`apiKeyAuth`), mas so sessao humana era aceita ate
agora. `Depends(exigir_permissao(...))` trocado por
`Depends(exigir_permissao_ou_escopo(...))` (mesmo combinador ja provado em
`app/routers/empresas.py`/`webhooks.py`) -- sessao humana E' tentada primeiro
(comportamento humano preservado byte a byte), cliente de integracao (OAuth/
API key) so entra quando nao ha sessao humana autenticada.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response

from app.apuracao.banco_horas import consulta as consulta_servico
from app.apuracao.banco_horas import contas as contas_servico
from app.apuracao.banco_horas import politicas as politicas_servico
from app.apuracao.banco_horas import quitacoes as quitacoes_servico
from app.comum.autenticacao_cliente import (
    ContextoAcesso,
    aplicar_limite_taxa_se_cliente,
    exigir_permissao_ou_escopo,
    usuario_id_do_acesso,
)
from app.comum.limitador_taxa import exigir_limite_taxa_sessao
from app.core.erros import RESPOSTAS_PADRAO
from app.db.sessao import SessaoDb
from app.schemas import contrato

roteador = APIRouter(tags=["banco-horas"])

# Uma instancia por par (permissao, escopo) unico deste arquivo -- nunca
# `exigir_permissao_ou_escopo(...)` chamado de novo dentro de um handler
# (identidade estavel do *callable* pro cache de dependencia do FastAPI).
_ACESSO_LER = exigir_permissao_ou_escopo(permissao="banco_horas.ler", escopo="banco-horas:ler")
_ACESSO_CRIAR = exigir_permissao_ou_escopo(
    permissao="banco_horas.criar", escopo="banco-horas:escrever"
)
_ACESSO_CONFIGURAR = exigir_permissao_ou_escopo(
    permissao="banco_horas.configurar", escopo="banco-horas:escrever"
)


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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER)],
    sessao: SessaoDb,
    response: Response,
    x_tenant: Annotated[
        str | None,
        Header(alias="X-Tenant", description="Slug ou UUID do tenant alvo."),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(alias="X-Request-Id", description="Identificador de correlacao."),
    ] = None,
    cursor: Annotated[str | None, Query(alias="cursor")] = None,
    limite: Annotated[int | None, Query(alias="limite")] = None,
    vinculo_id: Annotated[UUID | None, Query(alias="vinculoId")] = None,
    conta_id: Annotated[UUID | None, Query(alias="contaId")] = None,
    conta_codigo: Annotated[str | None, Query(alias="contaCodigo")] = None,
    de: Annotated[date | None, Query(alias="de")] = None,
    ate: Annotated[date | None, Query(alias="ate")] = None,
    tipo: Annotated[str | None, Query(alias="tipo")] = None,
) -> contrato.ExtratoBancoHoras:
    """Obter extrato de banco de horas"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    return await consulta_servico.obter_extrato_banco_horas(
        sessao,
        acesso.tenant_id,
        colaborador_id,
        vinculo_id=vinculo_id,
        conta_id=conta_id,
        conta_codigo=conta_codigo,
        de=de,
        ate=ate,
        tipo=tipo,
        cursor=cursor,
        limite=limite,
    )


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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER)],
    sessao: SessaoDb,
    response: Response,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    vinculo_id: Annotated[UUID | None, Query(alias="vinculoId")] = None,
    conta_codigo: Annotated[str | None, Query(alias="contaCodigo")] = None,
    data_referencia: Annotated[date | None, Query(alias="dataReferencia")] = None,
) -> contrato.SaldoBancoHoras:
    """Obter saldo de banco de horas"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    return await consulta_servico.obter_saldo_banco_horas(
        sessao,
        acesso.tenant_id,
        colaborador_id,
        vinculo_id=vinculo_id,
        conta_codigo=conta_codigo,
        data_referencia=data_referencia,
    )


@roteador.post(
    "/v1/banco-horas/simular",
    status_code=200,
    operation_id="simularBancoHoras",
    summary="Simular impacto no saldo",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def simular_banco_horas(
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    corpo: contrato.SimulacaoBancoRequisicao,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER)],
    sessao: SessaoDb,
    response: Response,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.SimulacaoBancoResposta:
    """Simular impacto no saldo"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    return await consulta_servico.simular_banco_horas(sessao, acesso.tenant_id, corpo)


@roteador.get(
    "/v1/banco-horas/contas",
    status_code=200,
    operation_id="listarContasBancoHoras",
    summary="Listar contas de banco de horas",
    responses=RESPOSTAS_PADRAO,
)
async def listar_contas_banco_horas(
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER)],
    sessao: SessaoDb,
    response: Response,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    cursor: Annotated[str | None, Query(alias="cursor")] = None,
    limite: Annotated[int | None, Query(alias="limite")] = None,
    ordenar: Annotated[str | None, Query(alias="ordenar")] = None,
    colaborador_id: Annotated[UUID | None, Query(alias="colaboradorId")] = None,
    vinculo_id: Annotated[UUID | None, Query(alias="vinculoId")] = None,
    empresa_id: Annotated[UUID | None, Query(alias="empresaId")] = None,
    status: Annotated[str | None, Query(alias="status")] = None,
    vence_ate: Annotated[date | None, Query(alias="venceAte")] = None,
    com_saldo_negativo: Annotated[bool | None, Query(alias="comSaldoNegativo")] = None,
) -> contrato.ListaBhConta:
    """Listar contas de banco de horas"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    linhas, paginacao = await contas_servico.listar_contas_banco_horas(
        sessao,
        acesso.tenant_id,
        colaborador_id=colaborador_id,
        vinculo_id=vinculo_id,
        empresa_id=empresa_id,
        status=status,
        vence_ate=vence_ate,
        com_saldo_negativo=com_saldo_negativo,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [contrato.BhConta.model_validate(linha, from_attributes=True) for linha in linhas]
    return contrato.ListaBhConta(dados=dados, paginacao=paginacao)


@roteador.post(
    "/v1/banco-horas/contas",
    status_code=201,
    operation_id="criarContaBancoHoras",
    summary="Criar conta de banco de horas",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def criar_conta_banco_horas(
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    corpo: contrato.BhContaCriar,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_CRIAR)],
    sessao: SessaoDb,
    response: Response,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.BhConta:
    """Criar conta de banco de horas"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    nova = await contas_servico.criar_conta_banco_horas(sessao, acesso.tenant_id, corpo)
    return contrato.BhConta.model_validate(nova, from_attributes=True)


@roteador.post(
    "/v1/banco-horas/quitacoes",
    status_code=201,
    operation_id="criarQuitacaoBancoHoras",
    summary="Registrar quitacao de banco de horas",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def criar_quitacao_banco_horas(
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    corpo: contrato.BhQuitacaoCriar,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_CRIAR)],
    sessao: SessaoDb,
    response: Response,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.BhQuitacao:
    """Registrar quitacao de banco de horas"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    nova = await quitacoes_servico.criar_quitacao_banco_horas(
        sessao, acesso.tenant_id, corpo, criado_por=usuario_id_do_acesso(acesso)
    )
    return contrato.BhQuitacao.model_validate(nova, from_attributes=True)


@roteador.get(
    "/v1/banco-horas/politicas",
    status_code=200,
    operation_id="listarPoliticasBancoHoras",
    summary="Listar politicas de banco de horas",
    responses=RESPOSTAS_PADRAO,
)
async def listar_politicas_banco_horas(
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER)],
    sessao: SessaoDb,
    response: Response,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    cursor: Annotated[str | None, Query(alias="cursor")] = None,
    limite: Annotated[int | None, Query(alias="limite")] = None,
    ordenar: Annotated[str | None, Query(alias="ordenar")] = None,
    empresa_id: Annotated[UUID | None, Query(alias="empresaId")] = None,
    regime: Annotated[str | None, Query(alias="regime")] = None,
    vigente_em: Annotated[date | None, Query(alias="vigenteEm")] = None,
    ativo: Annotated[bool | None, Query(alias="ativo")] = None,
) -> contrato.ListaBhPolitica:
    """Listar politicas de banco de horas"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    linhas, paginacao = await politicas_servico.listar_politicas_banco_horas(
        sessao,
        acesso.tenant_id,
        empresa_id=empresa_id,
        regime=regime,
        vigente_em=vigente_em,
        ativo=ativo,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [contrato.BhPolitica.model_validate(linha, from_attributes=True) for linha in linhas]
    return contrato.ListaBhPolitica(dados=dados, paginacao=paginacao)


@roteador.post(
    "/v1/banco-horas/politicas",
    status_code=201,
    operation_id="criarPoliticaBancoHoras",
    summary="Criar politica de banco de horas",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def criar_politica_banco_horas(
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    corpo: contrato.BhPoliticaCriar,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_CONFIGURAR)],
    sessao: SessaoDb,
    response: Response,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.BhPolitica:
    """Criar politica de banco de horas"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    nova = await politicas_servico.criar_politica_banco_horas(sessao, acesso.tenant_id, corpo)
    return contrato.BhPolitica.model_validate(nova, from_attributes=True)
