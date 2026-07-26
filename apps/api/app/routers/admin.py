"""Rotas da tag `admin` do contrato.

Administracao do tenant: usuarios, perfis, catalogo de permissoes e clientes
de API. Regra de negocio implementada na F1/A3 (T8) -- ver
`app.identidade.rbac.servico`. `GET /v1/admin/saude` NAO vive aqui: e
infraestrutura de F0, registrada em `app/routers/saude.py`.
"""

from __future__ import annotations

from typing import Annotated, Any, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query
from pydantic import BaseModel

from app.core.erros import RESPOSTAS_PADRAO
from app.core.seguranca import Sujeito, exigir_permissao, tenant_id_ou_erro
from app.db.sessao import SessaoDb
from app.identidade.rbac import servico
from app.schemas import contrato

roteador = APIRouter(tags=["admin"])

_SchemaT = TypeVar("_SchemaT", bound=BaseModel)


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
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("usuarios.ler"))],
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
    tenant_id = tenant_id_ou_erro(sujeito)
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
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("usuarios.criar"))],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    corpo: contrato.UsuarioCriar,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.Usuario:
    """Criar usuario."""
    tenant_id = tenant_id_ou_erro(sujeito)
    usuario = await servico.criar_usuario(sessao, tenant_id=tenant_id, dados=corpo, sujeito=sujeito)
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
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("usuarios.editar"))],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    usuario_id: Annotated[UUID, Path(alias="usuarioId")],
    corpo: contrato.UsuarioAtualizar,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.Usuario:
    """Atualizar usuario."""
    tenant_id = tenant_id_ou_erro(sujeito)
    usuario = await servico.atualizar_usuario(
        sessao, tenant_id=tenant_id, usuario_id=usuario_id, dados=corpo, sujeito=sujeito
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
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("perfis.ler"))],
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
    tenant_id = tenant_id_ou_erro(sujeito)
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
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("perfis.criar"))],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    corpo: contrato.PerfilCriar,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.Perfil:
    """Criar perfil."""
    tenant_id = tenant_id_ou_erro(sujeito)
    perfil = await servico.criar_perfil(sessao, tenant_id=tenant_id, dados=corpo, sujeito=sujeito)
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
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("permissoes.ler"))],
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
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("api_clients.ler"))],
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
    tenant_id = tenant_id_ou_erro(sujeito)
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
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("api_clients.criar"))],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    corpo: contrato.ApiClientCriar,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.ApiClientCriado:
    """Criar cliente de API. O segredo (`clientSecret`) sai uma unica vez."""
    tenant_id = tenant_id_ou_erro(sujeito)
    cliente, segredo = await servico.criar_api_client(
        sessao, tenant_id=tenant_id, dados=corpo, sujeito=sujeito
    )
    return contrato.ApiClientCriado.model_validate(
        {"cliente": _para_schema(contrato.ApiClient, cliente), "clientSecret": segredo}
    )
