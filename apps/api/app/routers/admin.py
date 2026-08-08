"""Rotas da tag `admin` do contrato.

Administracao do tenant: usuarios, perfis, catalogo de permissoes e clientes
de API. Regra de negocio implementada na F1/A3 (T8) -- ver
`app.identidade.rbac.servico`. `GET /v1/admin/saude` NAO vive aqui: e
infraestrutura de F0, registrada em `app/routers/saude.py`.

**F13/A1 (T2, RFC-016).** `listarApiClients`/`criarApiClient` **já estavam
implementados** por F1/A3 (não eram stub, ao contrário do que uma versão
anterior do PCF desta fase presumia -- conferido por leitura direta antes de
tocar neste arquivo) e continuam usando `exigir_permissao` (sessão humana),
sem alteração de autorização. As três operações NOVAS desta fase
(`listarApiKeys`/`criarApiKey`/`revogarApiKey`, ver `app.integracoes.
clientes.servico`) seguem o MESMO mecanismo (`exigir_permissao`, com os
códigos de permissão que a decisão do orquestrador em RFC-016 fixou:
`api_clients.ler`/`criar`/`editar`) -- não `app.comum.autenticacao_cliente.
exigir_escopo` (T1): gestão de clientes/chaves de integração permanece
operação de administração humana, o mesmo padrão que `listarApiClients`/
`criarApiClient` já estabeleceram, e é consistente com nunca reabrir/duplicar
a fiação de `app/core/seguranca.py` só para este subconjunto de rotas.

`criarApiClient` ganhou `Depends(exigir_idempotencia())` nesta fase (T3): o
cabeçalho `Idempotency-Key` já era exigido pelo contrato mas, antes desta
fase, chegava e era descartado (achado do PCF §2.4, que nomeia explicitamente
"admin api-clients/keys" como escopo de retrofit LEGÍTIMO desta fase --
diferente da proibição geral de retrofit nas ~130 rotas de F1-F12). As duas
rotas novas de escrita (`criarApiKey`/`revogarApiKey`) já nascem com o mesmo
mecanismo.

**Autenticação dupla (retrofit de 2026-08-08).** Revertendo a decisão dos
parágrafos acima, por decisão do dono do produto: o contrato já declarava os
três esquemas alternativos por operação (`bearerAuth`/`oauth2`/`apiKeyAuth`)
também para as rotas de `admin`, e agora o código honra os três.
`Depends(exigir_permissao(...))` virou `Depends(exigir_permissao_ou_escopo(
...))` (mesmo combinador provado em `app/routers/empresas.py` e
`app/routers/webhooks.py`) -- sessão humana é tentada primeiro (comportamento
humano preservado byte a byte), cliente de integração (OAuth/API key) só entra
quando não há sessão humana autenticada, com `admin:ler`/`admin:escrever`. Ver
`_sujeito_para_servico` abaixo para como a trilha de auditoria trata o acesso
sem usuário humano.
"""

from __future__ import annotations

from typing import Annotated, Any, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response
from pydantic import BaseModel

from app.comum.autenticacao_cliente import (
    ContextoAcesso,
    aplicar_limite_taxa_se_cliente,
    exigir_permissao_ou_escopo,
)
from app.comum.idempotencia_generica import (
    ChaveIdempotencia,
    abrir_operacao,
    concluir_operacao,
    exigir_idempotencia,
)
from app.core.erros import RESPOSTAS_PADRAO
from app.core.seguranca import Sujeito
from app.db.sessao import SessaoDb
from app.identidade.rbac import servico
from app.integracoes.clientes import servico as clientes_servico
from app.schemas import contrato

roteador = APIRouter(tags=["admin"])

# Uma instancia por par (permissao, escopo) unico -- nunca uma fabrica chamada
# de novo dentro do handler: mesmo motivo documentado em
# `app.comum.limitador_taxa` (identidade estavel do *callable* pro cache de
# dependencia do FastAPI).
_ACESSO_USUARIOS_LER = exigir_permissao_ou_escopo(permissao="usuarios.ler", escopo="admin:ler")
_ACESSO_USUARIOS_CRIAR = exigir_permissao_ou_escopo(
    permissao="usuarios.criar", escopo="admin:escrever"
)
_ACESSO_USUARIOS_EDITAR = exigir_permissao_ou_escopo(
    permissao="usuarios.editar", escopo="admin:escrever"
)
_ACESSO_PERFIS_LER = exigir_permissao_ou_escopo(permissao="perfis.ler", escopo="admin:ler")
_ACESSO_PERFIS_CRIAR = exigir_permissao_ou_escopo(permissao="perfis.criar", escopo="admin:escrever")
_ACESSO_PERMISSOES_LER = exigir_permissao_ou_escopo(permissao="permissoes.ler", escopo="admin:ler")
_ACESSO_API_CLIENTS_LER = exigir_permissao_ou_escopo(
    permissao="api_clients.ler", escopo="admin:ler"
)
_ACESSO_API_CLIENTS_CRIAR = exigir_permissao_ou_escopo(
    permissao="api_clients.criar", escopo="admin:escrever"
)
_ACESSO_API_CLIENTS_EDITAR = exigir_permissao_ou_escopo(
    permissao="api_clients.editar", escopo="admin:escrever"
)

_SchemaT = TypeVar("_SchemaT", bound=BaseModel)


def _sujeito_para_servico(acesso: ContextoAcesso) -> Sujeito:
    """`Sujeito` a repassar para a camada de servico.

    Cinco handlers deste arquivo repassam o `Sujeito` INTEIRO (nao so
    `usuario_id`) para a camada de servico, que o usa para `criado_por` e para
    `registrar_auditoria_de_sujeito` (que le `tenant_id`/`usuario_id`/`email`/
    `perfis`/`delegacao_id`).

    Acesso humano devolve o proprio `Sujeito` resolvido, sem nenhuma alteracao
    (comportamento preservado byte a byte). Acesso de cliente de integracao
    devolve um `Sujeito` sintetico so com o `tenant_id` do cliente: sem
    `usuario_id`, sem perfis, sem delegacao -- nao ha usuario humano a quem
    atribuir a acao, e `registrar_auditoria_de_sujeito` exige apenas
    `tenant_id` nao-nulo. Mesma escolha que `usuario_id_do_acesso` ja faz para
    os campos `criado_por`/`atualizado_por` nos outros routers retrofitados.
    """
    if acesso.sujeito is not None:
        return acesso.sujeito
    return Sujeito(tenant_id=acesso.tenant_id, autenticado=True)


def _para_schema(schema_cls: type[_SchemaT], origem: Any, **extras: Any) -> _SchemaT:
    """Converte um objeto ORM (ou dict) no schema pydantic do contrato.

    Le, para cada campo declarado no schema, o atributo homonimo do objeto
    ORM (os models de `packages/contracts` usam os mesmos nomes de coluna dos
    schemas gerados) e aplica `extras` por cima -- usado para os campos
    computados que nao sao coluna (`Usuario.perfis`, `Perfil.permissoes`).
    """
    dados = {nome: getattr(origem, nome, None) for nome in schema_cls.model_fields}
    dados.update(extras)
    return schema_cls.model_validate(dados)


async def _usuario_para_schema(sessao: SessaoDb, tenant_id: UUID, usuario: Any) -> contrato.Usuario:
    atribuicoes = await servico.perfis_do_usuario(
        sessao, tenant_id=tenant_id, usuario_id=usuario.id
    )
    perfis = [
        _para_schema(contrato.UsuarioPerfil, atribuicao, perfil_codigo=codigo)
        for atribuicao, codigo in atribuicoes
    ]
    return _para_schema(contrato.Usuario, usuario, perfis=perfis)


async def _perfil_para_schema(sessao: SessaoDb, tenant_id: UUID, perfil: Any) -> contrato.Perfil:
    codigos = await servico.permissoes_do_perfil(sessao, tenant_id=tenant_id, perfil_id=perfil.id)
    return _para_schema(contrato.Perfil, perfil, permissoes=codigos)


@roteador.get(
    "/v1/admin/usuarios",
    status_code=200,
    operation_id="listarUsuarios",
    summary="Listar usuarios",
    responses=RESPOSTAS_PADRAO,
)
async def listar_usuarios(
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_USUARIOS_LER)],
    response: Response,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    cursor: Annotated[str | None, Query(alias="cursor")] = None,
    limite: Annotated[int | None, Query(alias="limite")] = None,
    ordenar: Annotated[str | None, Query(alias="ordenar")] = None,
    status: Annotated[str | None, Query(alias="status")] = None,
    tipo: Annotated[str | None, Query(alias="tipo")] = None,
    perfil_codigo: Annotated[str | None, Query(alias="perfilCodigo")] = None,
    empresa_id: Annotated[UUID | None, Query(alias="empresaId")] = None,
    com_colaborador: Annotated[bool | None, Query(alias="comColaborador")] = None,
    busca: Annotated[str | None, Query(alias="busca")] = None,
) -> contrato.ListaUsuario:
    """Listar usuarios."""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    linhas, paginacao = await servico.listar_usuarios(
        sessao,
        tenant_id=tenant_id,
        cursor=cursor,
        limite=limite,
        status=status,
        tipo=tipo,
        empresa_id=empresa_id,
        com_colaborador=com_colaborador,
        busca=busca,
    )
    dados = [await _usuario_para_schema(sessao, tenant_id, linha) for linha in linhas]
    if perfil_codigo:
        dados = [
            u for u in dados if any(p.perfil_codigo == perfil_codigo for p in (u.perfis or []))
        ]
    return contrato.ListaUsuario(
        dados=dados, paginacao=contrato.Paginacao.model_validate(paginacao)
    )


@roteador.post(
    "/v1/admin/usuarios",
    status_code=201,
    operation_id="criarUsuario",
    summary="Criar usuario",
    responses=RESPOSTAS_PADRAO,
)
async def criar_usuario(
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_USUARIOS_CRIAR)],
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    corpo: contrato.UsuarioCriar,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.Usuario:
    """Criar usuario."""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    usuario = await servico.criar_usuario(
        sessao, tenant_id=tenant_id, dados=corpo, sujeito=_sujeito_para_servico(acesso)
    )
    return await _usuario_para_schema(sessao, tenant_id, usuario)


@roteador.patch(
    "/v1/admin/usuarios/{usuarioId}",
    status_code=200,
    operation_id="atualizarUsuario",
    summary="Atualizar usuario",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_usuario(
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_USUARIOS_EDITAR)],
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    usuario_id: Annotated[UUID, Path(alias="usuarioId")],
    corpo: contrato.UsuarioAtualizar,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.Usuario:
    """Atualizar usuario."""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    usuario = await servico.atualizar_usuario(
        sessao,
        tenant_id=tenant_id,
        usuario_id=usuario_id,
        dados=corpo,
        sujeito=_sujeito_para_servico(acesso),
    )
    return await _usuario_para_schema(sessao, tenant_id, usuario)


@roteador.get(
    "/v1/admin/perfis",
    status_code=200,
    operation_id="listarPerfis",
    summary="Listar perfis",
    responses=RESPOSTAS_PADRAO,
)
async def listar_perfis(
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_PERFIS_LER)],
    response: Response,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    cursor: Annotated[str | None, Query(alias="cursor")] = None,
    limite: Annotated[int | None, Query(alias="limite")] = None,
    ordenar: Annotated[str | None, Query(alias="ordenar")] = None,
    sistema: Annotated[bool | None, Query(alias="sistema")] = None,
    somente_leitura: Annotated[bool | None, Query(alias="somenteLeitura")] = None,
    ativo: Annotated[bool | None, Query(alias="ativo")] = None,
) -> contrato.ListaPerfil:
    """Listar perfis."""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    linhas, paginacao = await servico.listar_perfis(
        sessao,
        tenant_id=tenant_id,
        cursor=cursor,
        limite=limite,
        sistema=sistema,
        somente_leitura=somente_leitura,
        ativo=ativo,
    )
    dados = [await _perfil_para_schema(sessao, tenant_id, linha) for linha in linhas]
    return contrato.ListaPerfil(dados=dados, paginacao=contrato.Paginacao.model_validate(paginacao))


@roteador.post(
    "/v1/admin/perfis",
    status_code=201,
    operation_id="criarPerfil",
    summary="Criar perfil",
    responses=RESPOSTAS_PADRAO,
)
async def criar_perfil(
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_PERFIS_CRIAR)],
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    corpo: contrato.PerfilCriar,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.Perfil:
    """Criar perfil."""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    perfil = await servico.criar_perfil(
        sessao, tenant_id=tenant_id, dados=corpo, sujeito=_sujeito_para_servico(acesso)
    )
    return await _perfil_para_schema(sessao, tenant_id, perfil)


@roteador.get(
    "/v1/admin/permissoes",
    status_code=200,
    operation_id="listarPermissoes",
    summary="Listar catalogo de permissoes",
    responses=RESPOSTAS_PADRAO,
)
async def listar_permissoes(
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_PERMISSOES_LER)],
    response: Response,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    cursor: Annotated[str | None, Query(alias="cursor")] = None,
    limite: Annotated[int | None, Query(alias="limite")] = None,
    ordenar: Annotated[str | None, Query(alias="ordenar")] = None,
    modulo: Annotated[str | None, Query(alias="modulo")] = None,
    recurso: Annotated[str | None, Query(alias="recurso")] = None,
    sensivel: Annotated[bool | None, Query(alias="sensivel")] = None,
) -> contrato.ListaPermissao:
    """Listar catalogo de permissoes (somente leitura -- ver `schema.sql` secao 20)."""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    linhas, paginacao = await servico.listar_permissoes(
        sessao,
        cursor=cursor,
        limite=limite,
        modulo=modulo,
        recurso=recurso,
        sensivel=sensivel,
    )
    dados = [_para_schema(contrato.Permissao, linha) for linha in linhas]
    return contrato.ListaPermissao(
        dados=dados, paginacao=contrato.Paginacao.model_validate(paginacao)
    )


@roteador.get(
    "/v1/admin/api-clients",
    status_code=200,
    operation_id="listarApiClients",
    summary="Listar clientes de API",
    responses=RESPOSTAS_PADRAO,
)
async def listar_api_clients(
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_API_CLIENTS_LER)],
    response: Response,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    cursor: Annotated[str | None, Query(alias="cursor")] = None,
    limite: Annotated[int | None, Query(alias="limite")] = None,
    ordenar: Annotated[str | None, Query(alias="ordenar")] = None,
    ambiente: Annotated[str | None, Query(alias="ambiente")] = None,
    status: Annotated[str | None, Query(alias="status")] = None,
    tipo: Annotated[str | None, Query(alias="tipo")] = None,
) -> contrato.ListaApiClient:
    """Listar clientes de API."""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    linhas, paginacao = await servico.listar_api_clients(
        sessao,
        tenant_id=tenant_id,
        cursor=cursor,
        limite=limite,
        ambiente=ambiente,
        status=status,
        tipo=tipo,
    )
    dados = [_para_schema(contrato.ApiClient, linha) for linha in linhas]
    return contrato.ListaApiClient(
        dados=dados, paginacao=contrato.Paginacao.model_validate(paginacao)
    )


@roteador.post(
    "/v1/admin/api-clients",
    status_code=201,
    operation_id="criarApiClient",
    summary="Criar cliente de API",
    responses=RESPOSTAS_PADRAO,
)
async def criar_api_client(
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_API_CLIENTS_CRIAR)],
    chave_idem: Annotated[ChaveIdempotencia, Depends(exigir_idempotencia())],
    response: Response,
    corpo: contrato.ApiClientCriar,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.ApiClientCriado:
    """Criar cliente de API. O segredo (`clientSecret`) sai uma unica vez."""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    resultado = await abrir_operacao(
        sessao, tenant_id=tenant_id, escopo="criarApiClient", chave=chave_idem
    )
    response.headers["Idempotency-Replayed"] = "true" if resultado.ja_concluido else "false"
    if resultado.ja_concluido:
        return contrato.ApiClientCriado.model_validate(resultado.resposta_corpo)

    cliente, segredo = await servico.criar_api_client(
        sessao, tenant_id=tenant_id, dados=corpo, sujeito=_sujeito_para_servico(acesso)
    )
    resposta = contrato.ApiClientCriado.model_validate(
        {"cliente": _para_schema(contrato.ApiClient, cliente), "clientSecret": segredo}
    )
    await concluir_operacao(
        sessao,
        registro_id=resultado.registro_id,
        status_http=201,
        corpo_resposta=resposta.model_dump(mode="json", by_alias=True),
    )
    return resposta


# =============================================================================
# Chaves de API (F13/A1, T2 -- RFC-016)
# =============================================================================


@roteador.get(
    "/v1/admin/api-clients/{apiClientId}/chaves",
    status_code=200,
    operation_id="listarApiKeys",
    summary="Listar chaves de API do cliente",
    responses=RESPOSTAS_PADRAO,
)
async def listar_api_keys(
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_API_CLIENTS_LER)],
    response: Response,
    api_client_id: Annotated[UUID, Path(alias="apiClientId")],
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    cursor: Annotated[str | None, Query(alias="cursor")] = None,
    limite: Annotated[int | None, Query(alias="limite")] = None,
    ordenar: Annotated[str | None, Query(alias="ordenar")] = None,
) -> contrato.ListaApiKey:
    """Listar chaves de API do cliente. Nunca devolve `hash` nem a chave em claro."""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    linhas, paginacao = await clientes_servico.listar_api_keys(
        sessao, tenant_id=tenant_id, api_client_id=api_client_id, cursor=cursor, limite=limite
    )
    dados = [_para_schema(contrato.ApiKey, linha) for linha in linhas]
    return contrato.ListaApiKey(dados=dados, paginacao=contrato.Paginacao.model_validate(paginacao))


@roteador.post(
    "/v1/admin/api-clients/{apiClientId}/chaves",
    status_code=201,
    operation_id="criarApiKey",
    summary="Criar chave de API",
    responses=RESPOSTAS_PADRAO,
)
async def criar_api_key(
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_API_CLIENTS_CRIAR)],
    chave_idem: Annotated[ChaveIdempotencia, Depends(exigir_idempotencia())],
    response: Response,
    api_client_id: Annotated[UUID, Path(alias="apiClientId")],
    corpo: contrato.ApiKeyCriar,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.ApiKeyCriada:
    """Criar chave de API. O valor em claro (`chave`) sai uma unica vez."""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    resultado = await abrir_operacao(
        sessao, tenant_id=tenant_id, escopo="criarApiKey", chave=chave_idem
    )
    response.headers["Idempotency-Replayed"] = "true" if resultado.ja_concluido else "false"
    if resultado.ja_concluido:
        return contrato.ApiKeyCriada.model_validate(resultado.resposta_corpo)

    chave, chave_em_claro = await clientes_servico.criar_api_key(
        sessao,
        tenant_id=tenant_id,
        api_client_id=api_client_id,
        dados=corpo,
        sujeito=_sujeito_para_servico(acesso),
    )
    resposta = contrato.ApiKeyCriada.model_validate(
        {"apiKey": _para_schema(contrato.ApiKey, chave), "chave": chave_em_claro}
    )
    await concluir_operacao(
        sessao,
        registro_id=resultado.registro_id,
        status_http=201,
        corpo_resposta=resposta.model_dump(mode="json", by_alias=True),
    )
    return resposta


@roteador.delete(
    "/v1/admin/api-clients/{apiClientId}/chaves/{chaveId}",
    status_code=204,
    operation_id="revogarApiKey",
    summary="Revogar chave de API",
    responses=RESPOSTAS_PADRAO,
)
async def revogar_api_key(
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_API_CLIENTS_EDITAR)],
    chave_idem: Annotated[ChaveIdempotencia, Depends(exigir_idempotencia())],
    response: Response,
    api_client_id: Annotated[UUID, Path(alias="apiClientId")],
    chave_id: Annotated[UUID, Path(alias="chaveId")],
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Response:
    """Revogar chave de API. Idempotente: revogar de novo continua respondendo 204."""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    tenant_id = acesso.tenant_id
    resultado = await abrir_operacao(
        sessao, tenant_id=tenant_id, escopo="revogarApiKey", chave=chave_idem
    )
    response.headers["Idempotency-Replayed"] = "true" if resultado.ja_concluido else "false"
    if not resultado.ja_concluido:
        await clientes_servico.revogar_api_key(
            sessao, tenant_id=tenant_id, api_client_id=api_client_id, chave_id=chave_id
        )
        await concluir_operacao(
            sessao, registro_id=resultado.registro_id, status_http=204, corpo_resposta=None
        )
    response.status_code = 204
    return response
