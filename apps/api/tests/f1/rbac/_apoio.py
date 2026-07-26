"""Helpers de dados compartilhados entre os testes de `tests/f1/rbac/**`.

Deliberadamente em SQL direto (nao ORM do pacote de contratos): mantem estes
testes independentes de qualquer import alem do que `conftest.py` ja usa (via
`seed_dev`), e segue o mesmo estilo ja adotado por
`test_catalogo_permissoes.py`/`test_fixture_smoke.py`. Cada funcao assume que
`aplicar_tenant` (de `conftest.py`) ja rodou na mesma sessao/transacao.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def perfil_id_por_codigo(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, codigo: str
) -> uuid.UUID:
    linha = await sessao.execute(
        text("SELECT id FROM perfis WHERE tenant_id = :tenant AND codigo = :codigo"),
        {"tenant": str(tenant_id), "codigo": codigo},
    )
    encontrado: uuid.UUID = linha.scalar_one()
    return encontrado


async def criar_usuario(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, email: str, nome: str
) -> uuid.UUID:
    """Cria um usuario com um e-mail garantidamente unico.

    `email` e usado como PREFIXO legivel; um sufixo aleatorio e inserido antes
    do `@` para que reexecutar a suite (ou rodar em paralelo com outro
    processo pytest contra o mesmo tenant semeado) nunca esbarre em
    `uq_usuarios_email` -- a fixture de RBAC reusa o mesmo tenant entre
    execucoes de processo (`seed_dev.semeia` e idempotente por slug), mas os
    dados criados pelos TESTES aqui nao sao limpos entre execucoes.
    """
    novo_id = uuid.uuid4()
    local, _, dominio = email.partition("@")
    email_unico = f"{local}.{uuid.uuid4().hex[:10]}@{dominio}"
    await sessao.execute(
        text(
            "INSERT INTO usuarios (id, tenant_id, email, nome_completo, tipo, status) "
            "VALUES (:id, :tenant, :email, :nome, 'humano', 'ativo')"
        ),
        {"id": str(novo_id), "tenant": str(tenant_id), "email": email_unico, "nome": nome},
    )
    return novo_id


async def atribuir_perfil(
    sessao: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    usuario_id: uuid.UUID,
    perfil_codigo: str,
    escopo_tipo: str = "tenant",
    empresa_id: uuid.UUID | None = None,
    unidade_id: uuid.UUID | None = None,
    departamento_id: uuid.UUID | None = None,
    equipe_id: uuid.UUID | None = None,
    incluir_subordinados: bool = True,
    vigencia_inicio: str | None = None,
    vigencia_fim: str | None = None,
) -> uuid.UUID:
    pid = await perfil_id_por_codigo(sessao, tenant_id=tenant_id, codigo=perfil_codigo)
    atribuicao_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO usuario_perfis "
            "(id, tenant_id, usuario_id, perfil_id, escopo_tipo, empresa_id, unidade_id, "
            " departamento_id, equipe_id, incluir_subordinados, vigencia_inicio, vigencia_fim) "
            "VALUES (:id, :tenant, :usuario, :perfil, :escopo, :empresa, :unidade, "
            " :departamento, :equipe, :incluir, "
            " COALESCE(:vigencia_inicio, CURRENT_DATE), :vigencia_fim)"
        ),
        {
            "id": str(atribuicao_id),
            "tenant": str(tenant_id),
            "usuario": str(usuario_id),
            "perfil": str(pid),
            "escopo": escopo_tipo,
            "empresa": str(empresa_id) if empresa_id else None,
            "unidade": str(unidade_id) if unidade_id else None,
            "departamento": str(departamento_id) if departamento_id else None,
            "equipe": str(equipe_id) if equipe_id else None,
            "incluir": incluir_subordinados,
            "vigencia_inicio": vigencia_inicio,
            "vigencia_fim": vigencia_fim,
        },
    )
    return atribuicao_id


async def criar_empresa(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, cnpj: str, razao_social: str
) -> uuid.UUID:
    novo_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO empresas (id, tenant_id, cnpj, razao_social) "
            "VALUES (:id, :tenant, :cnpj, :razao)"
        ),
        {"id": str(novo_id), "tenant": str(tenant_id), "cnpj": cnpj, "razao": razao_social},
    )
    return novo_id


async def criar_unidade(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, empresa_id: uuid.UUID, codigo: str, nome: str
) -> uuid.UUID:
    novo_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO unidades (id, tenant_id, empresa_id, codigo, nome) "
            "VALUES (:id, :tenant, :empresa, :codigo, :nome)"
        ),
        {
            "id": str(novo_id),
            "tenant": str(tenant_id),
            "empresa": str(empresa_id),
            "codigo": codigo,
            "nome": nome,
        },
    )
    return novo_id
