"""Rotas da tag `espelhos` do contrato (T7/T8, F10/A2).

Espelho de ponto prévio e oficial, com assinatura eletrônica do
colaborador. A assinatura vincula o hash da versão exata que foi lida: se o
espelho mudar, ela deixa de conferir, que é o comportamento desejado.

Regra de negócio implementada na fase F10 (agente A2, ownership deste
arquivo). A regra em si vive em `app.workflow.fechamento.espelho`/
`assinatura`; este módulo só traduz HTTP <-> serviço.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response
from ponto_contracts import AssinaturaEspelho, Espelho

from app.comum.armazenamento import obter_objeto
from app.comum.ip_confiavel import ip_confiavel_do_cliente
from app.comum.limitador_taxa import exigir_limite_taxa_sessao
from app.core.config import obter_configuracao
from app.core.erros import RESPOSTAS_PADRAO
from app.core.seguranca import Sujeito, exigir_permissao, tenant_id_ou_erro
from app.db.sessao import SessaoDb
from app.schemas import contrato
from app.workflow.fechamento import assinatura as assinatura_servico
from app.workflow.fechamento import espelho as espelho_servico
from app.workflow.fechamento.pdf import gerar_pdf_espelho

roteador = APIRouter(tags=["espelhos"])


def _ip_do_cliente(request: Request) -> str | None:
    """F14/A2, retrofit: delega a `app.comum.ip_confiavel` (honra
    `X-Forwarded-For`/`X-Real-IP` só quando a conexão vem do proxy reverso
    de produção -- ver docstring daquele módulo)."""
    return ip_confiavel_do_cliente(request)


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _montar_espelho(linha: Espelho, assinaturas: list[AssinaturaEspelho]) -> contrato.Espelho:
    resposta = contrato.Espelho.model_validate(linha, from_attributes=True)
    resposta.assinaturas = [
        contrato.AssinaturaEspelho.model_validate(a, from_attributes=True) for a in assinaturas
    ]
    return resposta


@roteador.get(
    "/v1/espelhos",
    status_code=200,
    operation_id="listarEspelhos",
    summary="Listar espelhos de ponto",
    responses=RESPOSTAS_PADRAO,
)
async def listar_espelhos(
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("espelhos.ler"))],
    sessao: SessaoDb,
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
    periodo_id: Annotated[
        UUID | None, Query(alias="periodoId", description="Filtra pelos espelhos de um periodo.")
    ] = None,
    colaborador_id: Annotated[
        UUID | None,
        Query(alias="colaboradorId", description="Filtra pelos espelhos de um colaborador."),
    ] = None,
    vinculo_id: Annotated[
        UUID | None, Query(alias="vinculoId", description="Filtra pelos espelhos de um vinculo.")
    ] = None,
    fechamento_id: Annotated[
        UUID | None,
        Query(alias="fechamentoId", description="Filtra pelos espelhos de um fechamento."),
    ] = None,
    tipo: Annotated[
        str | None, Query(alias="tipo", description="Filtra pela natureza do espelho.")
    ] = None,
    assinado: Annotated[
        bool | None,
        Query(
            alias="assinado",
            description="Filtra por espelhos com ou sem assinatura do colaborador.",
        ),
    ] = None,
) -> contrato.ListaEspelho:
    """Listar espelhos de ponto"""
    tenant_id = tenant_id_ou_erro(sujeito)
    linhas, paginacao = await espelho_servico.listar_espelhos(
        sessao,
        tenant_id,
        periodo_id=periodo_id,
        colaborador_id=colaborador_id,
        vinculo_id=vinculo_id,
        fechamento_id=fechamento_id,
        tipo=tipo,
        assinado=assinado,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [contrato.Espelho.model_validate(linha, from_attributes=True) for linha in linhas]
    return contrato.ListaEspelho(dados=dados, paginacao=paginacao)


@roteador.post(
    "/v1/espelhos",
    status_code=202,
    operation_id="gerarEspelhos",
    summary="Gerar espelhos de ponto",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def gerar_espelhos(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.EspelhoCriar,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("espelhos.criar"))],
    sessao: SessaoDb,
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
) -> contrato.ProcessamentoAssincrono:
    """Gerar espelhos de ponto"""
    tenant_id = tenant_id_ou_erro(sujeito)
    config = obter_configuracao()
    return await espelho_servico.criar_espelhos_assincrono(
        sessao,
        tenant_id,
        corpo,
        usuario_id=sujeito.usuario_id,
        redis_url=config.redis_url,
    )


@roteador.get(
    "/v1/espelhos/{espelhoId}",
    status_code=200,
    operation_id="obterEspelho",
    summary="Obter espelho de ponto",
    responses=RESPOSTAS_PADRAO,
)
async def obter_espelho(
    espelho_id: Annotated[UUID, Path(alias="espelhoId", description="Identificador do espelho.")],
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("espelhos.ler"))],
    sessao: SessaoDb,
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
) -> contrato.Espelho:
    """Obter espelho de ponto"""
    tenant_id = tenant_id_ou_erro(sujeito)
    encontrado = await espelho_servico.obter_espelho(sessao, tenant_id, espelho_id)
    assinaturas = (
        (
            await sessao.execute(
                sa.select(AssinaturaEspelho)
                .where(
                    AssinaturaEspelho.tenant_id == tenant_id,
                    AssinaturaEspelho.espelho_id == encontrado.id,
                )
                .order_by(AssinaturaEspelho.criado_em.asc())
            )
        )
        .scalars()
        .all()
    )
    return _montar_espelho(encontrado, list(assinaturas))


@roteador.post(
    "/v1/espelhos/{espelhoId}/assinar",
    status_code=201,
    operation_id="assinarEspelho",
    summary="Assinar espelho de ponto",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def assinar_espelho(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    espelho_id: Annotated[UUID, Path(alias="espelhoId", description="Identificador do espelho.")],
    corpo: contrato.AssinaturaEspelhoRequisicao,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("espelhos.assinar"))],
    sessao: SessaoDb,
    request: Request,
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
) -> contrato.AssinaturaEspelho:
    """Assinar espelho de ponto"""
    tenant_id = tenant_id_ou_erro(sujeito)
    assinado = await assinatura_servico.assinar_espelho(
        sessao,
        tenant_id,
        espelho_id,
        corpo,
        usuario_id=sujeito.usuario_id,
        ip=_ip_do_cliente(request),
        user_agent=_user_agent(request),
    )
    return contrato.AssinaturaEspelho.model_validate(assinado, from_attributes=True)


@roteador.get(
    "/v1/espelhos/{espelhoId}/pdf",
    status_code=200,
    operation_id="baixarEspelhoPdf",
    summary="Baixar espelho em PDF",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def baixar_espelho_pdf(
    espelho_id: Annotated[UUID, Path(alias="espelhoId", description="Identificador do espelho.")],
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("espelhos.exportar"))],
    sessao: SessaoDb,
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
) -> Response:
    """Baixar espelho em PDF

    Decisão fixada (PCF §6, T7): se `conteudoRef` já estiver preenchido, o
    PDF vem do MinIO (`app.comum.armazenamento.obter_objeto`); se estiver
    vazio (espelho gerado sem `gerarPdf=true`), gera sob demanda a partir
    de `conteudo` -- sem gravar nada no armazenamento nesta chamada (GET
    permanece sem efeito colateral; quem quiser o PDF persistido chama
    `gerarEspelhos` com `gerarPdf=true`).
    """
    tenant_id = tenant_id_ou_erro(sujeito)
    espelho = await espelho_servico.obter_espelho(sessao, tenant_id, espelho_id)

    if espelho.conteudo_ref:
        pdf_bytes = await obter_objeto(espelho.conteudo_ref)
    else:
        assinaturas = (
            (
                await sessao.execute(
                    sa.select(AssinaturaEspelho).where(
                        AssinaturaEspelho.tenant_id == tenant_id,
                        AssinaturaEspelho.espelho_id == espelho.id,
                        AssinaturaEspelho.status == "assinado",
                    )
                )
            )
            .scalars()
            .all()
        )
        pdf_bytes = gerar_pdf_espelho(
            espelho.conteudo,
            hash_sha256=espelho.hash_sha256,
            versao=espelho.versao,
            tipo=espelho.tipo,
            assinaturas=[
                {
                    "signatarioTipo": a.signatario_tipo,
                    "metodo": a.metodo,
                    "carimboTempo": a.carimbo_tempo.isoformat(),
                    "hashAssinado": a.hash_assinado,
                }
                for a in assinaturas
            ],
        )

    return Response(content=pdf_bytes, media_type="application/pdf")
