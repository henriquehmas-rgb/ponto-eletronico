"""Rotas da tag `fiscal` do contrato. GERADO -- nao editar.

Conformidade REP-P: cadastro do REP-P, geracao de AFD e AEJ e assinatura CAdES com certificado ICP-Brasil.
O AFD deriva EXCLUSIVAMENTE das marcacoes; o AEJ e quem enxerga tratamento, ausencia e banco de horas.
Confundir o escopo dos dois arquivos e o erro que invalida o sistema numa fiscalizacao.

Regra de negocio destas operacoes entra na fase F12. Ate la toda chamada
responde 501 com PONTO-INT-005. Regerar com
`python tools/gerar_do_contrato.py`.

Autenticacao dupla (retrofit de 2026-08-08): o contrato ja declarava os tres
esquemas alternativos por operacao (`bearerAuth`/`oauth2`/`apiKeyAuth`), mas
so sessao humana era aceita ate agora. `Depends(exigir_permissao(...))`
trocado por `Depends(exigir_permissao_ou_escopo(...))` -- sessao humana E'
tentada primeiro (comportamento humano preservado byte a byte), cliente de
integracao (OAuth/API key) so entra quando nao ha sessao humana autenticada.
Mesmo padrao ja provado em `app/routers/empresas.py`/`webhooks.py`. So a
camada de autenticacao mudou: nenhuma regra de negocio de geracao/assinatura
foi tocada.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response

from app.comum.autenticacao_cliente import (
    ContextoAcesso,
    aplicar_limite_taxa_se_cliente,
    exigir_permissao_ou_escopo,
    usuario_id_do_acesso,
)
from app.comum.ip_confiavel import ip_confiavel_do_cliente
from app.comum.limitador_taxa import exigir_limite_taxa_sessao
from app.core.config import obter_configuracao
from app.core.erros import RESPOSTAS_PADRAO
from app.db.sessao import SessaoDb
from app.fiscal.aej import gerador as _aej_gerador
from app.fiscal.afd.gerador import solicitar_geracao_afd as _servico_solicitar_geracao_afd
from app.fiscal.assinatura.servico import assinar_arquivo_fiscal as _servico_assinar_arquivo_fiscal
from app.fiscal.cofre import consulta as _cofre_consulta
from app.fiscal.rep_p.servico import criar_rep_p as _servico_criar_rep_p
from app.fiscal.rep_p.servico import listar_rep_ps as _servico_listar_rep_ps
from app.fiscal.rep_p.servico import rep_p_para_contrato as _rep_p_para_contrato
from app.schemas import contrato

roteador = APIRouter(tags=["fiscal"])

# Uma instancia por par (permissao, escopo) usado no arquivo -- nunca uma
# chamada nova a `exigir_permissao_ou_escopo` dentro do handler (identidade
# estavel do *callable* pro cache de dependencia do FastAPI).
_ACESSO_LER = exigir_permissao_ou_escopo(permissao="fiscal.ler", escopo="fiscal:ler")
_ACESSO_EXPORTAR = exigir_permissao_ou_escopo(permissao="fiscal.exportar", escopo="fiscal:ler")
_ACESSO_EXECUTAR = exigir_permissao_ou_escopo(permissao="fiscal.executar", escopo="fiscal:escrever")
_ACESSO_ASSINAR = exigir_permissao_ou_escopo(permissao="fiscal.assinar", escopo="fiscal:escrever")
_ACESSO_CRIAR = exigir_permissao_ou_escopo(permissao="fiscal.criar", escopo="fiscal:escrever")


def _ip_do_cliente(request: Request) -> str | None:
    """F14/A2, retrofit: delega a `app.comum.ip_confiavel` (honra
    `X-Forwarded-For`/`X-Real-IP` só quando a conexão vem do proxy reverso
    de produção -- ver docstring daquele módulo)."""
    return ip_confiavel_do_cliente(request)


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


@roteador.post(
    "/v1/fiscal/afd",
    status_code=202,
    operation_id="gerarAfd",
    summary="Gerar AFD",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def gerar_afd(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.AfdCriar,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_EXECUTAR)],
    sessao: SessaoDb,
    response: Response,
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
    """Gerar AFD

    Valida sincrono (REP-P existe e tem numeroInpi, periodo coerente,
    nenhuma geracao em andamento) e enfileira `gerar_afd` no worker -- mesmo
    padrao de `criarFechamento` (F10) e de `gerarAej` (F12/A2). Regra de
    negocio em `app.fiscal.afd.gerador.solicitar_geracao_afd` (F12/A1).
    """
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    config = obter_configuracao()
    return await _servico_solicitar_geracao_afd(
        sessao,
        tenant_id,
        corpo,
        usuario_id=usuario_id_do_acesso(acesso),
        redis_url=config.redis_url,
    )


@roteador.get(
    "/v1/fiscal/afd",
    status_code=200,
    operation_id="listarAfd",
    summary="Listar arquivos AFD",
    responses=RESPOSTAS_PADRAO,
)
async def listar_afd(
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER)],
    sessao: SessaoDb,
    response: Response,
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
        UUID | None, Query(alias="empresaId", description="Filtra pelos arquivos de uma empresa.")
    ] = None,
    rep_p_id: Annotated[
        UUID | None, Query(alias="repPId", description="Filtra pelos arquivos de um REP-P.")
    ] = None,
    de: Annotated[
        date | None,
        Query(alias="de", description="Arquivos cujo periodo alcanca esta data ou depois."),
    ] = None,
    ate: Annotated[
        date | None,
        Query(alias="ate", description="Arquivos cujo periodo alcanca esta data ou antes."),
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
) -> contrato.ListaAfdArquivo:
    """Listar arquivos AFD"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    linhas, paginacao = await _cofre_consulta.listar_afd(
        sessao,
        tenant_id,
        empresa_id=empresa_id,
        rep_p_id=rep_p_id,
        de=de,
        ate=ate,
        status=status,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    return contrato.ListaAfdArquivo(
        dados=[contrato.AfdArquivo.model_validate(linha, from_attributes=True) for linha in linhas],
        paginacao=paginacao,
    )


@roteador.get(
    "/v1/fiscal/afd/{arquivoId}",
    status_code=200,
    operation_id="obterAfd",
    summary="Obter arquivo AFD",
    responses=RESPOSTAS_PADRAO,
)
async def obter_afd(
    arquivo_id: Annotated[UUID, Path(alias="arquivoId", description="Identificador do arquivo.")],
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER)],
    sessao: SessaoDb,
    response: Response,
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
) -> contrato.AfdArquivo:
    """Obter arquivo AFD"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    arquivo = await _cofre_consulta.obter_afd(sessao, tenant_id, arquivo_id)
    return contrato.AfdArquivo.model_validate(arquivo, from_attributes=True)


@roteador.get(
    "/v1/fiscal/afd/{arquivoId}/download",
    status_code=200,
    operation_id="baixarAfd",
    summary="Baixar arquivo AFD",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def baixar_afd(
    arquivo_id: Annotated[UUID, Path(alias="arquivoId", description="Identificador do arquivo.")],
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_EXPORTAR)],
    sessao: SessaoDb,
    request: Request,
    response: Response,
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
    incluir_assinatura: Annotated[
        bool | None,
        Query(
            alias="incluirAssinatura",
            description="Devolve um pacote com o arquivo e o .p7s destacado, em vez do arquivo isolado.",
        ),
    ] = None,
) -> Response:
    """Baixar arquivo AFD"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    conteudo, content_type, nome_arquivo = await _cofre_consulta.baixar_afd(
        sessao,
        tenant_id,
        arquivo_id,
        incluir_assinatura=bool(incluir_assinatura),
        usuario_id=usuario_id_do_acesso(acesso),
        ip=_ip_do_cliente(request),
        user_agent=_user_agent(request),
    )
    download = Response(
        content=conteudo,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},
    )
    # Diferente das rotas 204 (que reaproveitam o proprio `response`), aqui o
    # corpo obriga um `Response` novo -- e o FastAPI 0.137 DESCARTA os
    # cabecalhos do `response` injetado quando o handler devolve um `Response`
    # proprio (`fastapi.routing.get_request_handler`: `response =
    # raw_response`, sem merge). Os `RateLimit-*` setados acima sao copiados a
    # mao para nao se perderem no download; para sessao humana o `response`
    # injetado esta vazio e este laco nao faz nada (comportamento preservado).
    for nome, valor in response.headers.items():
        download.headers[nome] = valor
    return download


@roteador.post(
    "/v1/fiscal/aej",
    status_code=202,
    operation_id="gerarAej",
    summary="Gerar AEJ",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def gerar_aej(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.AejCriar,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_EXECUTAR)],
    sessao: SessaoDb,
    response: Response,
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
    """Gerar AEJ

    Valida sincrono (empresa existe, periodo valido, nenhuma geracao em
    andamento), cria a linha de controle em `aej_arquivos` e enfileira
    `gerar_aej` no worker -- mesmo padrao de `criarFechamento` (F10) e de
    `gerarAfd` (F12/A1). Regra de negocio em
    `app.fiscal.aej.gerador.solicitar_geracao_aej` (F12/A2).
    """
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    config = obter_configuracao()
    return await _aej_gerador.solicitar_geracao_aej(
        sessao,
        tenant_id,
        corpo,
        usuario_id=usuario_id_do_acesso(acesso),
        redis_url=config.redis_url,
    )


@roteador.get(
    "/v1/fiscal/aej",
    status_code=200,
    operation_id="listarAej",
    summary="Listar arquivos AEJ",
    responses=RESPOSTAS_PADRAO,
)
async def listar_aej(
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER)],
    sessao: SessaoDb,
    response: Response,
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
        UUID | None, Query(alias="empresaId", description="Filtra pelos arquivos de uma empresa.")
    ] = None,
    periodo_id: Annotated[
        UUID | None, Query(alias="periodoId", description="Filtra pelos arquivos de um periodo.")
    ] = None,
    de: Annotated[
        date | None,
        Query(alias="de", description="Arquivos cujo periodo alcanca esta data ou depois."),
    ] = None,
    ate: Annotated[
        date | None,
        Query(alias="ate", description="Arquivos cujo periodo alcanca esta data ou antes."),
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
) -> contrato.ListaAejArquivo:
    """Listar arquivos AEJ"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    linhas, paginacao = await _cofre_consulta.listar_aej(
        sessao,
        tenant_id,
        empresa_id=empresa_id,
        periodo_id=periodo_id,
        de=de,
        ate=ate,
        status=status,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    return contrato.ListaAejArquivo(
        dados=[contrato.AejArquivo.model_validate(linha, from_attributes=True) for linha in linhas],
        paginacao=paginacao,
    )


@roteador.get(
    "/v1/fiscal/aej/{arquivoId}",
    status_code=200,
    operation_id="obterAej",
    summary="Obter arquivo AEJ",
    responses=RESPOSTAS_PADRAO,
)
async def obter_aej(
    arquivo_id: Annotated[UUID, Path(alias="arquivoId", description="Identificador do arquivo.")],
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER)],
    sessao: SessaoDb,
    response: Response,
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
) -> contrato.AejArquivo:
    """Obter arquivo AEJ"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    arquivo = await _cofre_consulta.obter_aej(sessao, tenant_id, arquivo_id)
    return contrato.AejArquivo.model_validate(arquivo, from_attributes=True)


@roteador.post(
    "/v1/fiscal/arquivos/{arquivoId}/assinar",
    status_code=201,
    operation_id="assinarArquivoFiscal",
    summary="Assinar arquivo fiscal",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def assinar_arquivo_fiscal(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    arquivo_id: Annotated[
        UUID, Path(alias="arquivoId", description="Identificador do arquivo a assinar.")
    ],
    corpo: contrato.AssinaturaArquivoRequisicao,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_ASSINAR)],
    sessao: SessaoDb,
    response: Response,
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
) -> contrato.ArquivoAssinatura:
    """Assinar arquivo fiscal"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    assinatura = await _servico_assinar_arquivo_fiscal(
        sessao, tenant_id, arquivo_id, corpo, usuario_id=usuario_id_do_acesso(acesso)
    )
    tipo_arquivo_bruto = corpo.tipo_arquivo
    # `is not None` (em vez de `hasattr`, usado como padrao em outros pontos
    # de F12 -- `app.fiscal.assinatura.servico._valor`, `app.fiscal.rep_p.
    # servico._valor` -- onde o parametro e tipado `Any`): aqui
    # `tipo_arquivo_bruto` tem o tipo concreto `TipoArquivo1 | None`
    # (StrEnum), e o mypy nao consegue provar, a partir de `hasattr`, que o
    # ramo `None` foi eliminado antes do acesso a `.value` -- achado real
    # desta sessao (T14, fechamento). `TipoArquivo1` sempre tem `.value`
    # quando nao `None` (StrEnum gerado do contrato), entao o comportamento
    # em runtime e identico.
    tipo_arquivo = tipo_arquivo_bruto.value if tipo_arquivo_bruto is not None else None
    if tipo_arquivo == "afd":
        response.headers["Location"] = f"/v1/fiscal/afd/{arquivo_id}"
    elif tipo_arquivo == "aej":
        response.headers["Location"] = f"/v1/fiscal/aej/{arquivo_id}"
    return contrato.ArquivoAssinatura.model_validate(assinatura, from_attributes=True)


@roteador.get(
    "/v1/fiscal/rep-ps",
    status_code=200,
    operation_id="listarRepPs",
    summary="Listar REP-P",
    responses=RESPOSTAS_PADRAO,
)
async def listar_rep_ps(
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER)],
    sessao: SessaoDb,
    response: Response,
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
        UUID | None, Query(alias="empresaId", description="Filtra pelos REP-P de uma empresa.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
) -> contrato.ListaRepP:
    """Listar REP-P"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    linhas, sequencias, paginacao = await _servico_listar_rep_ps(
        sessao,
        tenant_id,
        empresa_id=empresa_id,
        status=status,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [
        _rep_p_para_contrato(
            linha,
            proximo_nsr=(sequencias[linha.id].proximo_nsr if linha.id in sequencias else None),
            ultimo_nsr_emitido=(
                sequencias[linha.id].ultimo_nsr_emitido if linha.id in sequencias else None
            ),
        )
        for linha in linhas
    ]
    return contrato.ListaRepP(dados=dados, paginacao=paginacao)


@roteador.post(
    "/v1/fiscal/rep-ps",
    status_code=201,
    operation_id="criarRepP",
    summary="Cadastrar REP-P",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def criar_rep_p(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.RepPCriar,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_CRIAR)],
    sessao: SessaoDb,
    response: Response,
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
) -> contrato.RepP:
    """Cadastrar REP-P

    Inicializa `nsr_sequencias` (`proximo_nsr=1`) na mesma transacao. Regra
    de negocio em `app.fiscal.rep_p.servico.criar_rep_p` (F12/A1).
    """
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    criado = await _servico_criar_rep_p(
        sessao, tenant_id, corpo, usuario_id=usuario_id_do_acesso(acesso)
    )
    response.headers["Location"] = f"/v1/fiscal/rep-ps/{criado.id}"
    return criado
