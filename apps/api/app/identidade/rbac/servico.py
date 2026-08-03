"""Regras de negocio de `listarPermissoes`, `listarPerfis`/`criarPerfil` e
`listarUsuarios`/`criarUsuario`/`atualizarUsuario` (T8).

Cada funcao publica devolve dados prontos para o schema pydantic do
contrato (`app.schemas.contrato`), deixando o router (`app/routers/admin.py`)
magro: so extrai parametros da requisicao e converte para `Problema` em caso
de erro.
"""

from __future__ import annotations

import datetime as _dt
import secrets
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.core.seguranca import Sujeito
from app.identidade.auditoria.hash_chain import registrar_auditoria_de_sujeito
from app.identidade.rbac import paginacao
from app.identidade.rbac._contrato import contrato
from app.identidade.tokens import oauth

# ===========================================================================
# Permissoes (catalogo global, somente leitura)
# ===========================================================================


async def listar_permissoes(
    sessao: AsyncSession,
    *,
    cursor: str | None,
    limite: int | None,
    modulo: str | None,
    recurso: str | None,
    sensivel: bool | None,
) -> tuple[list[Any], dict[str, Any]]:
    consulta = sa.select(contrato.Permissao)
    if modulo:
        consulta = consulta.where(contrato.Permissao.modulo == modulo)
    if recurso:
        consulta = consulta.where(contrato.Permissao.recurso == recurso)
    if sensivel is not None:
        consulta = consulta.where(contrato.Permissao.sensivel.is_(sensivel))
    return await paginacao.paginar(
        sessao,
        consulta,
        coluna_criado_em=contrato.Permissao.criado_em,
        coluna_id=contrato.Permissao.id,
        cursor=cursor,
        limite=limite,
    )


# ===========================================================================
# Perfis
# ===========================================================================


async def listar_perfis(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    cursor: str | None,
    limite: int | None,
    sistema: bool | None,
    somente_leitura: bool | None,
    ativo: bool | None,
) -> tuple[list[Any], dict[str, Any]]:
    consulta = sa.select(contrato.Perfil).where(
        contrato.Perfil.tenant_id == tenant_id, contrato.Perfil.excluido_em.is_(None)
    )
    if sistema is not None:
        consulta = consulta.where(contrato.Perfil.sistema.is_(sistema))
    if somente_leitura is not None:
        consulta = consulta.where(contrato.Perfil.somente_leitura.is_(somente_leitura))
    if ativo is not None:
        consulta = consulta.where(contrato.Perfil.ativo.is_(ativo))
    return await paginacao.paginar(
        sessao,
        consulta,
        coluna_criado_em=contrato.Perfil.criado_em,
        coluna_id=contrato.Perfil.id,
        cursor=cursor,
        limite=limite,
    )


async def permissoes_do_perfil(
    sessao: AsyncSession, *, tenant_id: UUID, perfil_id: UUID
) -> list[str]:
    consulta = (
        sa.select(contrato.Permissao.codigo)
        .join(
            contrato.PerfilPermissao, contrato.PerfilPermissao.permissao_id == contrato.Permissao.id
        )
        .where(
            contrato.PerfilPermissao.tenant_id == tenant_id,
            contrato.PerfilPermissao.perfil_id == perfil_id,
            contrato.PerfilPermissao.concedida.is_(True),
        )
    )
    return sorted(codigo for (codigo,) in await sessao.execute(consulta))


async def criar_perfil(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    dados: Any,
    sujeito: Sujeito,
) -> Any:
    """Cria um perfil do TENANT (nunca `sistema=True`: perfil de fabrica so
    nasce pela semeadura, nunca por esta API -- e assim que "perfil de
    fabrica nao e excluivel" fica trivialmente verdade aqui: nao ha caminho
    para criar OU remover um `sistema=True` por este endpoint)."""
    existe = await sessao.scalars(
        sa.select(contrato.Perfil).where(
            contrato.Perfil.tenant_id == tenant_id,
            contrato.Perfil.codigo == dados.codigo,
            contrato.Perfil.excluido_em.is_(None),
        )
    )
    if existe.first() is not None:
        raise ErroDeAplicacao("PONTO-CONF-001", detalhe="Ja existe um perfil com este codigo.")

    perfil = contrato.Perfil(
        tenant_id=tenant_id,
        codigo=dados.codigo,
        nome=dados.nome,
        descricao=dados.descricao,
        sistema=False,
        escopo_padrao=(dados.escopo_padrao.value if dados.escopo_padrao else "tenant"),
        somente_leitura=bool(dados.somente_leitura),
        ativo=dados.ativo if dados.ativo is not None else True,
        criado_por=sujeito.usuario_id,
    )
    sessao.add(perfil)
    await sessao.flush()

    codigos_permissao = list(dados.permissoes or [])
    if codigos_permissao:
        linhas_permissao = await sessao.execute(
            sa.select(contrato.Permissao.id, contrato.Permissao.codigo).where(
                contrato.Permissao.codigo.in_(codigos_permissao)
            )
        )
        for permissao_id, _codigo in linhas_permissao:
            sessao.add(
                contrato.PerfilPermissao(
                    tenant_id=tenant_id,
                    perfil_id=perfil.id,
                    permissao_id=permissao_id,
                    concedida=True,
                    criado_por=sujeito.usuario_id,
                )
            )
        await sessao.flush()

    await registrar_auditoria_de_sujeito(
        sessao,
        sujeito,
        evento="identidade.perfil.criado",
        entidade="perfis",
        entidade_id=perfil.id,
        acao="criar",
        valor_novo={"codigo": perfil.codigo, "nome": perfil.nome, "permissoes": codigos_permissao},
    )
    return perfil


# ===========================================================================
# Usuarios
# ===========================================================================


async def listar_usuarios(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    cursor: str | None,
    limite: int | None,
    status: str | None,
    tipo: str | None,
    empresa_id: UUID | None,
    com_colaborador: bool | None,
    busca: str | None,
) -> tuple[list[Any], dict[str, Any]]:
    consulta = sa.select(contrato.Usuario).where(
        contrato.Usuario.tenant_id == tenant_id, contrato.Usuario.excluido_em.is_(None)
    )
    if status:
        consulta = consulta.where(contrato.Usuario.status == status)
    if tipo:
        consulta = consulta.where(contrato.Usuario.tipo == tipo)
    if com_colaborador is True:
        consulta = consulta.where(contrato.Usuario.colaborador_id.is_not(None))
    elif com_colaborador is False:
        consulta = consulta.where(contrato.Usuario.colaborador_id.is_(None))
    if busca:
        padrao = f"%{busca.lower()}%"
        consulta = consulta.where(
            sa.or_(
                sa.func.lower(contrato.Usuario.nome_completo).like(padrao),
                sa.func.lower(contrato.Usuario.email).like(padrao),
            )
        )
    if empresa_id is not None:
        consulta = consulta.where(
            contrato.Usuario.id.in_(
                sa.select(contrato.UsuarioPerfil.usuario_id).where(
                    contrato.UsuarioPerfil.tenant_id == tenant_id,
                    contrato.UsuarioPerfil.empresa_id == empresa_id,
                )
            )
        )
    return await paginacao.paginar(
        sessao,
        consulta,
        coluna_criado_em=contrato.Usuario.criado_em,
        coluna_id=contrato.Usuario.id,
        cursor=cursor,
        limite=limite,
    )


async def perfis_do_usuario(
    sessao: AsyncSession, *, tenant_id: UUID, usuario_id: UUID
) -> list[Any]:
    """Atribuicoes de perfil do usuario, com o `codigo` do perfil ja resolvido
    (os models do contrato nao tem `relationship()`, ver `resolucao.py`)."""
    consulta = (
        sa.select(contrato.UsuarioPerfil, contrato.Perfil.codigo)
        .join(contrato.Perfil, contrato.Perfil.id == contrato.UsuarioPerfil.perfil_id)
        .where(
            contrato.UsuarioPerfil.tenant_id == tenant_id,
            contrato.UsuarioPerfil.usuario_id == usuario_id,
        )
    )
    saida = []
    for atribuicao, perfil_codigo in await sessao.execute(consulta):
        saida.append((atribuicao, perfil_codigo))
    return saida


async def criar_usuario(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    dados: Any,
    sujeito: Sujeito,
) -> Any:
    existe = await sessao.scalars(
        sa.select(contrato.Usuario).where(
            contrato.Usuario.tenant_id == tenant_id,
            sa.func.lower(contrato.Usuario.email) == dados.email.lower(),
            contrato.Usuario.excluido_em.is_(None),
        )
    )
    if existe.first() is not None:
        raise ErroDeAplicacao("PONTO-CONF-001", detalhe="Ja existe um usuario com este e-mail.")

    usuario = contrato.Usuario(
        tenant_id=tenant_id,
        colaborador_id=dados.colaborador_id,
        email=dados.email,
        nome_completo=dados.nome_completo,
        telefone=dados.telefone,
        avatar_ref=dados.avatar_ref,
        tipo=(dados.tipo.value if dados.tipo else "humano"),
        status=(dados.status.value if dados.status else "convidado"),
        idioma=dados.idioma or "pt-BR",
        fuso_horario=dados.fuso_horario or "America/Sao_Paulo",
        mfa_obrigatorio=bool(dados.mfa_obrigatorio),
        criado_por=sujeito.usuario_id,
    )
    sessao.add(usuario)
    await sessao.flush()

    for atribuicao in dados.perfis or []:
        perfil_id = atribuicao.perfil_id
        if perfil_id is None and atribuicao.perfil_codigo:
            perfil_id = await sessao.scalar(
                sa.select(contrato.Perfil.id).where(
                    contrato.Perfil.tenant_id == tenant_id,
                    contrato.Perfil.codigo == atribuicao.perfil_codigo,
                    contrato.Perfil.excluido_em.is_(None),
                )
            )
        if perfil_id is None:
            continue
        sessao.add(
            contrato.UsuarioPerfil(
                tenant_id=tenant_id,
                usuario_id=usuario.id,
                perfil_id=perfil_id,
                escopo_tipo=(atribuicao.escopo_tipo.value if atribuicao.escopo_tipo else "tenant"),
                empresa_id=atribuicao.empresa_id,
                unidade_id=atribuicao.unidade_id,
                departamento_id=atribuicao.departamento_id,
                equipe_id=atribuicao.equipe_id,
                incluir_subordinados=(
                    atribuicao.incluir_subordinados
                    if atribuicao.incluir_subordinados is not None
                    else True
                ),
                vigencia_inicio=atribuicao.vigencia_inicio or _dt.datetime.now(_dt.UTC).date(),
                vigencia_fim=atribuicao.vigencia_fim,
                criado_por=sujeito.usuario_id,
            )
        )
    await sessao.flush()

    await registrar_auditoria_de_sujeito(
        sessao,
        sujeito,
        evento="identidade.usuario.criado",
        entidade="usuarios",
        entidade_id=usuario.id,
        acao="criar",
        valor_novo={"email": usuario.email, "nome_completo": usuario.nome_completo},
    )
    return usuario


async def atualizar_usuario(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    usuario_id: UUID,
    dados: Any,
    sujeito: Sujeito,
) -> Any:
    usuario = await sessao.get(contrato.Usuario, usuario_id)
    if usuario is None or usuario.tenant_id != tenant_id or usuario.excluido_em is not None:
        raise ErroDeAplicacao("PONTO-REC-001")

    valor_anterior = {
        "email": usuario.email,
        "nome_completo": usuario.nome_completo,
        "status": usuario.status,
    }

    campos_enviados = dados.model_dump(exclude_unset=True, by_alias=False)
    for campo, valor in campos_enviados.items():
        if campo == "perfis":
            continue
        if hasattr(valor, "value"):  # StrEnum
            valor = valor.value
        setattr(usuario, campo, valor)

    await sessao.flush()

    await registrar_auditoria_de_sujeito(
        sessao,
        sujeito,
        evento="identidade.usuario.atualizado",
        entidade="usuarios",
        entidade_id=usuario.id,
        acao="atualizar",
        valor_anterior=valor_anterior,
        valor_novo={
            "email": usuario.email,
            "nome_completo": usuario.nome_completo,
            "status": usuario.status,
        },
    )
    return usuario


# ===========================================================================
# API clients (T8 -- criacao e listagem; a emissao de token OAuth e a F1/A1/T7)
# ===========================================================================


async def listar_api_clients(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    cursor: str | None,
    limite: int | None,
    ambiente: str | None,
    status: str | None,
    tipo: str | None,
) -> tuple[list[Any], dict[str, Any]]:
    consulta = sa.select(contrato.ApiClient).where(
        contrato.ApiClient.tenant_id == tenant_id, contrato.ApiClient.excluido_em.is_(None)
    )
    if ambiente:
        consulta = consulta.where(contrato.ApiClient.ambiente == ambiente)
    if status:
        consulta = consulta.where(contrato.ApiClient.status == status)
    if tipo:
        consulta = consulta.where(contrato.ApiClient.tipo == tipo)
    return await paginacao.paginar(
        sessao,
        consulta,
        coluna_criado_em=contrato.ApiClient.criado_em,
        coluna_id=contrato.ApiClient.id,
        cursor=cursor,
        limite=limite,
    )


async def criar_api_client(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    dados: Any,
    sujeito: Sujeito,
) -> tuple[Any, str]:
    """Cria o `ApiClient`. Devolve `(cliente, client_secret_em_claro)`.

    O segredo aparece so aqui, uma unica vez -- o que fica gravado e o hash
    Argon2id (`client_secret_hash`), gerado por
    `app.identidade.tokens.oauth.gerar_client_secret` -- a mesma funcao que
    `autenticar_client` usa para verificar (`verificar_hash`, Argon2id).
    Um hash SHA-256 aqui faria `verificar_hash` rejeitar sempre (nao e um
    hash Argon2id valido), impedindo qualquer cliente novo de autenticar.
    `client_id` e um identificador publico, gerado aqui (nao e segredo).
    """
    client_id = f"client_{secrets.token_hex(12)}"
    segredo, hash_segredo = oauth.gerar_client_secret()

    cliente = contrato.ApiClient(
        tenant_id=tenant_id,
        nome=dados.nome,
        descricao=dados.descricao,
        client_id=client_id,
        client_secret_hash=hash_segredo,
        tipo=(dados.tipo.value if dados.tipo else "confidencial"),
        ambiente=(dados.ambiente.value if dados.ambiente else "sandbox"),
        escopos=list(dados.escopos or []),
        redirect_uris=dados.redirect_uris,
        ips_permitidos=dados.ips_permitidos,
        rate_limit_por_minuto=dados.rate_limit_por_minuto or 600,
        contato_email=dados.contato_email,
        status=(dados.status.value if dados.status else "ativo"),
        criado_por=sujeito.usuario_id,
    )
    sessao.add(cliente)
    await sessao.flush()

    await registrar_auditoria_de_sujeito(
        sessao,
        sujeito,
        evento="identidade.api_client.criado",
        entidade="api_clients",
        entidade_id=cliente.id,
        acao="criar",
        valor_novo={
            "nome": cliente.nome,
            "client_id": cliente.client_id,
            "escopos": cliente.escopos,
        },
    )
    return cliente, segredo
