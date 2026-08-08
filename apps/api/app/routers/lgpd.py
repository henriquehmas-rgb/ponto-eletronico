"""Rotas da tag `lgpd` do contrato.

Consentimentos versionados, registro de acesso a dado sensivel e atendimento aos direitos do titular.
O registro do ponto se apoia em obrigacao legal; a biometria exige consentimento especifico.
Pedido de eliminacao nao apaga marcacao: a guarda e obrigatoria.

Implementado na F14 (agente A3). Cada rota so orquestra HTTP <-> `app.lgpd.*`
(consentimentos, solicitacoes, acessos) -- a regra de negocio vive la, nao
aqui. Ver docstring de cada modulo de servico para as decisoes de
interpretacao do contrato tomadas nesta fase.

Autenticacao dupla (retrofit de 2026-08-08): o contrato ja declarava os tres
esquemas alternativos por operacao (`bearerAuth`/`oauth2`/`apiKeyAuth`), mas
so sessao humana era aceita ate agora. `Depends(exigir_permissao(...))`
trocado por `Depends(exigir_permissao_ou_escopo(...))` -- sessao humana E'
tentada primeiro (comportamento humano preservado byte a byte), cliente de
integracao (OAuth/API key) so entra quando nao ha sessao humana autenticada.
Mesmo padrao ja provado em `app/routers/empresas.py`/`webhooks.py`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response

from app.comum.autenticacao_cliente import (
    ContextoAcesso,
    aplicar_limite_taxa_se_cliente,
    exigir_permissao_ou_escopo,
    usuario_id_do_acesso,
)
from app.core.erros import RESPOSTAS_PADRAO
from app.db.sessao import SessaoDb
from app.lgpd import acessos as servico_acessos
from app.lgpd import consentimentos as servico_consentimentos
from app.lgpd import solicitacoes as servico_solicitacoes
from app.schemas import contrato

roteador = APIRouter(tags=["lgpd"])

# Uma instancia por par (permissao, escopo) usado no arquivo -- nunca uma
# chamada nova a `exigir_permissao_ou_escopo` dentro do handler (identidade
# estavel do *callable* pro cache de dependencia do FastAPI).
_ACESSO_LER = exigir_permissao_ou_escopo(permissao="lgpd.ler", escopo="lgpd:ler")
_ACESSO_CRIAR = exigir_permissao_ou_escopo(permissao="lgpd.criar", escopo="lgpd:escrever")
_ACESSO_EXCLUIR = exigir_permissao_ou_escopo(permissao="lgpd.excluir", escopo="lgpd:escrever")


def _ip_do_cliente(request: Request) -> str | None:
    """Mesma receita duplicada em `app/routers/auth.py`/`sso.py`: o
    hardening de IP confiavel ponta a ponta (X-Forwarded-For so aceito da
    origem do proxy reverso) e territorio de A2 nesta fase (PCF secao 5,
    "mecanismo de IP confiavel"), ainda nao aplicado -- este modulo usa o IP
    de conexao direta, mesma limitacao que o resto do sistema tem hoje."""
    if request.client is None:
        return None
    return request.client.host


def _consentimento_para_schema(c: Any) -> contrato.Consentimento:
    return contrato.Consentimento(
        id=c.id,
        tenantId=c.tenant_id,
        colaboradorId=c.colaborador_id,
        finalidade=c.finalidade,
        versaoTermo=c.versao_termo,
        textoTermoRef=c.texto_termo_ref,
        hashTermo=c.hash_termo,
        status=c.status,
        concedidoEm=c.concedido_em,
        revogadoEm=c.revogado_em,
        expiraEm=c.expira_em,
        canal=c.canal,
        ip=c.ip,
        evidenciaRef=c.evidencia_ref,
        criadoEm=c.criado_em,
        criadoPor=c.criado_por,
        atualizadoEm=c.atualizado_em,
        atualizadoPor=c.atualizado_por,
    )


def _solicitacao_para_schema(s: Any) -> contrato.SolicitacaoTitular:
    return contrato.SolicitacaoTitular(
        id=s.id,
        tenantId=s.tenant_id,
        colaboradorId=s.colaborador_id,
        usuarioId=s.usuario_id,
        protocolo=s.protocolo,
        requerenteNome=s.requerente_nome,
        requerenteCpf=s.requerente_cpf,
        requerenteEmail=s.requerente_email,
        tipo=s.tipo,
        descricao=s.descricao,
        status=s.status,
        prazoEm=s.prazo_em,
        resposta=s.resposta,
        respostaRef=s.resposta_ref,
        respondidoEm=s.respondido_em,
        respondidoPor=s.respondido_por,
        criadoEm=s.criado_em,
        criadoPor=s.criado_por,
        atualizadoEm=s.atualizado_em,
        atualizadoPor=s.atualizado_por,
    )


def _acesso_para_schema(a: Any) -> contrato.AcessoDadoSensivel:
    return contrato.AcessoDadoSensivel(
        id=a.id,
        tenantId=a.tenant_id,
        usuarioId=a.usuario_id,
        colaboradorId=a.colaborador_id,
        categoria=a.categoria,
        entidade=a.entidade,
        entidadeId=a.entidade_id,
        finalidade=a.finalidade,
        baseLegal=a.base_legal,
        acao=a.acao,
        quantidadeRegistros=a.quantidade_registros,
        ip=a.ip,
        origem=a.origem,
        ocorridoEm=a.ocorrido_em,
        criadoEm=a.criado_em,
    )


@roteador.get(
    "/v1/lgpd/consentimentos",
    status_code=200,
    operation_id="listarConsentimentos",
    summary="Listar consentimentos",
    responses=RESPOSTAS_PADRAO,
)
async def listar_consentimentos(
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER)],
    response: Response,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    cursor: Annotated[str | None, Query(alias="cursor")] = None,
    limite: Annotated[int | None, Query(alias="limite")] = None,
    ordenar: Annotated[str | None, Query(alias="ordenar")] = None,
    colaborador_id: Annotated[UUID | None, Query(alias="colaboradorId")] = None,
    finalidade: Annotated[str | None, Query(alias="finalidade")] = None,
    status: Annotated[str | None, Query(alias="status")] = None,
) -> contrato.ListaConsentimento:
    """Listar consentimentos"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    linhas, tem_mais, proximo = await servico_consentimentos.listar_consentimentos(
        sessao,
        tenant_id=tenant_id,
        colaborador_id=colaborador_id,
        finalidade=finalidade,
        status=status,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    return contrato.ListaConsentimento(
        dados=[_consentimento_para_schema(linha) for linha in linhas],
        paginacao=contrato.Paginacao(
            proximoCursor=proximo,
            cursorAnterior=None,
            temMais=tem_mais,
            limite=limite or 50,
            totalEstimado=None,
        ),
    )


@roteador.post(
    "/v1/lgpd/consentimentos",
    status_code=201,
    operation_id="criarConsentimento",
    summary="Registrar consentimento",
    responses=RESPOSTAS_PADRAO,
)
async def criar_consentimento(
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    corpo: contrato.ConsentimentoCriar,
    request: Request,
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_CRIAR)],
    response: Response,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.Consentimento:
    """Registrar consentimento"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    dados = servico_consentimentos.DadosConsentimentoCriar(
        colaborador_id=corpo.colaborador_id,
        finalidade=corpo.finalidade.value,
        versao_termo=corpo.versao_termo,
        texto_termo_ref=corpo.texto_termo_ref,
        hash_termo=corpo.hash_termo,
        canal=corpo.canal.value if corpo.canal is not None else None,
        ip=corpo.ip or _ip_do_cliente(request),
        evidencia_ref=corpo.evidencia_ref,
        user_agent=request.headers.get("user-agent"),
    )
    consentimento = await servico_consentimentos.criar_consentimento(
        sessao, tenant_id=tenant_id, dados=dados, usuario_id=usuario_id_do_acesso(acesso)
    )
    response.headers["Location"] = f"/v1/lgpd/consentimentos/{consentimento.id}"
    return _consentimento_para_schema(consentimento)


@roteador.delete(
    "/v1/lgpd/consentimentos/{consentimentoId}",
    status_code=204,
    operation_id="revogarConsentimento",
    summary="Revogar consentimento",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def revogar_consentimento(
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    consentimento_id: Annotated[UUID, Path(alias="consentimentoId")],
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_EXCLUIR)],
    response: Response,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Response:
    """Revogar consentimento"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    await servico_consentimentos.revogar_consentimento(
        sessao,
        tenant_id=acesso.tenant_id,
        consentimento_id=consentimento_id,
        usuario_id=usuario_id_do_acesso(acesso),
    )
    # Reaproveita o `response` injetado (ja carrega os cabecalhos
    # `RateLimit-*` setados acima, quando o acesso e de cliente de
    # integracao) em vez de construir um `Response` novo, que perderia
    # esses cabecalhos -- mesmo padrao de `app/routers/empresas.py`.
    response.status_code = 204
    return response


@roteador.get(
    "/v1/lgpd/solicitacoes-titular",
    status_code=200,
    operation_id="listarSolicitacoesTitular",
    summary="Listar pedidos de titular",
    responses=RESPOSTAS_PADRAO,
)
async def listar_solicitacoes_titular(
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER)],
    response: Response,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    cursor: Annotated[str | None, Query(alias="cursor")] = None,
    limite: Annotated[int | None, Query(alias="limite")] = None,
    ordenar: Annotated[str | None, Query(alias="ordenar")] = None,
    colaborador_id: Annotated[UUID | None, Query(alias="colaboradorId")] = None,
    tipo: Annotated[str | None, Query(alias="tipo")] = None,
    status: Annotated[str | None, Query(alias="status")] = None,
    vencendo: Annotated[bool | None, Query(alias="vencendo")] = None,
) -> contrato.ListaSolicitacaoTitular:
    """Listar pedidos de titular"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    linhas, tem_mais, proximo = await servico_solicitacoes.listar_solicitacoes_titular(
        sessao,
        tenant_id=tenant_id,
        colaborador_id=colaborador_id,
        tipo=tipo,
        status=status,
        vencendo=vencendo,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    return contrato.ListaSolicitacaoTitular(
        dados=[_solicitacao_para_schema(linha) for linha in linhas],
        paginacao=contrato.Paginacao(
            proximoCursor=proximo,
            cursorAnterior=None,
            temMais=tem_mais,
            limite=limite or 50,
            totalEstimado=None,
        ),
    )


@roteador.post(
    "/v1/lgpd/solicitacoes-titular",
    status_code=201,
    operation_id="criarSolicitacaoTitular",
    summary="Registrar pedido de titular",
    responses=RESPOSTAS_PADRAO,
)
async def criar_solicitacao_titular(
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    corpo: contrato.SolicitacaoTitularCriar,
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_CRIAR)],
    response: Response,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.SolicitacaoTitular:
    """Registrar pedido de titular"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    dados = servico_solicitacoes.DadosSolicitacaoCriar(
        colaborador_id=corpo.colaborador_id,
        usuario_id=corpo.usuario_id,
        requerente_nome=corpo.requerente_nome,
        requerente_cpf=corpo.requerente_cpf,
        requerente_email=corpo.requerente_email,
        tipo=corpo.tipo.value,
        descricao=corpo.descricao,
        status_informado=corpo.status.value if corpo.status is not None else None,
        resposta_informada=corpo.resposta,
        resposta_ref_informada=corpo.resposta_ref,
    )
    solicitacao = await servico_solicitacoes.criar_solicitacao_titular(
        sessao, tenant_id=tenant_id, dados=dados, usuario_id=usuario_id_do_acesso(acesso)
    )
    response.headers["Location"] = f"/v1/lgpd/solicitacoes-titular/{solicitacao.id}"
    return _solicitacao_para_schema(solicitacao)


@roteador.get(
    "/v1/lgpd/acessos-sensiveis",
    status_code=200,
    operation_id="listarAcessosSensiveis",
    summary="Listar acessos a dados sensiveis",
    responses=RESPOSTAS_PADRAO,
)
async def listar_acessos_sensiveis(
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER)],
    response: Response,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    cursor: Annotated[str | None, Query(alias="cursor")] = None,
    limite: Annotated[int | None, Query(alias="limite")] = None,
    ordenar: Annotated[str | None, Query(alias="ordenar")] = None,
    usuario_id: Annotated[UUID | None, Query(alias="usuarioId")] = None,
    colaborador_id: Annotated[UUID | None, Query(alias="colaboradorId")] = None,
    categoria: Annotated[str | None, Query(alias="categoria")] = None,
    acao: Annotated[str | None, Query(alias="acao")] = None,
    de: Annotated[datetime | None, Query(alias="de")] = None,
    ate: Annotated[datetime | None, Query(alias="ate")] = None,
) -> contrato.ListaAcessoDadoSensivel:
    """Listar acessos a dados sensiveis"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    linhas, tem_mais, proximo = await servico_acessos.listar_acessos_sensiveis(
        sessao,
        tenant_id=tenant_id,
        usuario_id=usuario_id,
        colaborador_id=colaborador_id,
        categoria=categoria,
        acao=acao,
        de=de,
        ate=ate,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    return contrato.ListaAcessoDadoSensivel(
        dados=[_acesso_para_schema(linha) for linha in linhas],
        paginacao=contrato.Paginacao(
            proximoCursor=proximo,
            cursorAnterior=None,
            temMais=tem_mais,
            limite=limite or 50,
            totalEstimado=None,
        ),
    )
