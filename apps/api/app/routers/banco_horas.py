"""Rotas da tag `banco-horas` do contrato.

Contas-corrente de horas, extrato imutavel encadeado por hash, quitacoes e politicas de regime.
O limite legal e imposto pelo contrato: acordo individual escrito compensa em ate 6 meses, acordo ou convencao coletiva em ate 12.

Regra de negocio implementada na fase F4 (agente A2, ownership deste arquivo --
ver `docs/fases/F04-calculo-banco-de-horas.md`, secao 5). A regra em si vive em
`app.apuracao.banco_horas.*`; este modulo so traduz HTTP <-> servico, no mesmo
padrao de `app/routers/contratos.py` (F2).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query

from app.apuracao.banco_horas import consulta as consulta_servico
from app.apuracao.banco_horas import contas as contas_servico
from app.apuracao.banco_horas import politicas as politicas_servico
from app.apuracao.banco_horas import quitacoes as quitacoes_servico
from app.core.erros import RESPOSTAS_PADRAO
from app.core.seguranca import Sujeito, exigir_permissao, tenant_id_ou_erro
from app.db.sessao import SessaoDb
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
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("banco_horas.ler"))],
    sessao: SessaoDb,
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
    tenant_id = tenant_id_ou_erro(sujeito)
    return await consulta_servico.obter_extrato_banco_horas(
        sessao,
        tenant_id,
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
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("banco_horas.ler"))],
    sessao: SessaoDb,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    vinculo_id: Annotated[UUID | None, Query(alias="vinculoId")] = None,
    conta_codigo: Annotated[str | None, Query(alias="contaCodigo")] = None,
    data_referencia: Annotated[date | None, Query(alias="dataReferencia")] = None,
) -> contrato.SaldoBancoHoras:
    """Obter saldo de banco de horas"""
    tenant_id = tenant_id_ou_erro(sujeito)
    return await consulta_servico.obter_saldo_banco_horas(
        sessao,
        tenant_id,
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
)
async def simular_banco_horas(
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    corpo: contrato.SimulacaoBancoRequisicao,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("banco_horas.ler"))],
    sessao: SessaoDb,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.SimulacaoBancoResposta:
    """Simular impacto no saldo"""
    tenant_id = tenant_id_ou_erro(sujeito)
    return await consulta_servico.simular_banco_horas(sessao, tenant_id, corpo)


@roteador.get(
    "/v1/banco-horas/contas",
    status_code=200,
    operation_id="listarContasBancoHoras",
    summary="Listar contas de banco de horas",
    responses=RESPOSTAS_PADRAO,
)
async def listar_contas_banco_horas(
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("banco_horas.ler"))],
    sessao: SessaoDb,
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
    tenant_id = tenant_id_ou_erro(sujeito)
    linhas, paginacao = await contas_servico.listar_contas_banco_horas(
        sessao,
        tenant_id,
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
)
async def criar_conta_banco_horas(
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    corpo: contrato.BhContaCriar,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("banco_horas.criar"))],
    sessao: SessaoDb,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.BhConta:
    """Criar conta de banco de horas"""
    tenant_id = tenant_id_ou_erro(sujeito)
    nova = await contas_servico.criar_conta_banco_horas(sessao, tenant_id, corpo)
    return contrato.BhConta.model_validate(nova, from_attributes=True)


@roteador.post(
    "/v1/banco-horas/quitacoes",
    status_code=201,
    operation_id="criarQuitacaoBancoHoras",
    summary="Registrar quitacao de banco de horas",
    responses=RESPOSTAS_PADRAO,
)
async def criar_quitacao_banco_horas(
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    corpo: contrato.BhQuitacaoCriar,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("banco_horas.criar"))],
    sessao: SessaoDb,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.BhQuitacao:
    """Registrar quitacao de banco de horas"""
    tenant_id = tenant_id_ou_erro(sujeito)
    nova = await quitacoes_servico.criar_quitacao_banco_horas(
        sessao, tenant_id, corpo, criado_por=sujeito.usuario_id
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
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("banco_horas.ler"))],
    sessao: SessaoDb,
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
    tenant_id = tenant_id_ou_erro(sujeito)
    linhas, paginacao = await politicas_servico.listar_politicas_banco_horas(
        sessao,
        tenant_id,
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
)
async def criar_politica_banco_horas(
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    corpo: contrato.BhPoliticaCriar,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("banco_horas.configurar"))],
    sessao: SessaoDb,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.BhPolitica:
    """Criar politica de banco de horas"""
    tenant_id = tenant_id_ou_erro(sujeito)
    nova = await politicas_servico.criar_politica_banco_horas(sessao, tenant_id, corpo)
    return contrato.BhPolitica.model_validate(nova, from_attributes=True)
