"""Acesso CROSS-tenant do suporte da SEEG: `GET /v1/tenants` e
`POST /v1/tenants` (migration `0005_role_suporte_bypassrls`).

Estes testes existem para provar quatro coisas contra PostgreSQL REAL, nesta
ordem de importancia:

1. **O portao fecha.** Um usuario autenticado SEM `tenants.suporte` recebe
   `403 PONTO-PERM-001` nas duas rotas -- inclusive um usuario que tem
   `tenants.ler`/`tenants.criar` (os codigos que o proprio `openapi.yaml`
   declara), porque todo `admin_empresa` de todo tenant cliente ja tem esses
   dois pelo curinga de `MATRIZ_PERFIS`.
2. **O bypass funciona.** Com `tenants.suporte`, UMA chamada devolve tenants
   de MAIS DE UM tenant -- impossivel sob RLS -- e a criacao de um tenant
   novo (linha que nasce fora de qualquer `app.tenant_id`) conclui.
3. **A RLS continua intacta para todo o resto.** A role de login comum dos
   testes nao tem `BYPASSRLS` e continua enxergando exatamente um tenant; e a
   credencial de suporte, apesar do bypass, NAO tem privilegio de tabela fora
   de `tenants`/`auditoria` (um `SELECT` em `usuarios` responde
   `permission denied`).
4. **A trilha registra o bypass.** Cada chamada bem-sucedida grava uma linha
   de `auditoria` cujo `evento` e cujo `valor_novo` -- os dois DENTRO da
   formula do hash da cadeia -- dizem que aquilo foi acesso cross-tenant.

Mesma receita de par RS256 descartavel de
`tests/f1/tenancy/test_endpoints_tenants.py` (nenhum arquivo compartilhado e
editado por este modulo).
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from ponto_contracts import PerfilPermissao, Permissao, UsuarioPerfil
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.sessao_suporte import ROLE_SUPORTE, SENHA_PADRAO_DEV
from app.identidade.tenancy import servico_suporte
from app.identidade.tokens import chaves as jwt_chaves
from tests.f1.conftest import (
    AbrirSessaoTenant,
    ContextoF1,
    IdentidadeDeTeste,
    cabecalhos,
)

PERMISSAO_SUPORTE = "tenants.suporte"

#: Os codigos que o contrato declara em `x-permissao` para as duas rotas. O
#: teste do portao concede os DOIS ao usuario sem suporte, de proposito: e
#: exatamente essa a configuracao de qualquer `admin_empresa` de cliente.
PERMISSOES_DO_CONTRATO = ("tenants.ler", "tenants.criar")


@pytest.fixture(scope="module", autouse=True)
def _chaves_rs256(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Par RS256 descartavel, so para este modulo poder chamar `/v1/auth/login`."""
    diretorio = tmp_path_factory.mktemp("jwt-suporte")
    chave_privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    caminho_privada = diretorio / "private.pem"
    caminho_publica = diretorio / "public.pem"
    caminho_privada.write_bytes(
        chave_privada.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    caminho_publica.write_bytes(
        chave_privada.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    antigos = (os.environ.get("JWT_PRIVATE_KEY_PATH"), os.environ.get("JWT_PUBLIC_KEY_PATH"))
    os.environ["JWT_PRIVATE_KEY_PATH"] = str(caminho_privada)
    os.environ["JWT_PUBLIC_KEY_PATH"] = str(caminho_publica)
    jwt_chaves.limpar_cache()
    try:
        yield
    finally:
        for nome, valor in zip(
            ("JWT_PRIVATE_KEY_PATH", "JWT_PUBLIC_KEY_PATH"), antigos, strict=True
        ):
            if valor is None:
                os.environ.pop(nome, None)
            else:
                os.environ[nome] = valor
        jwt_chaves.limpar_cache()


# =============================================================================
# Apoio
# =============================================================================
async def _republicar_tenant(sessao_db: AsyncSession, identidade: IdentidadeDeTeste) -> None:
    """Republica `app.tenant_id` na sessao de teste.

    A fixture `sessao_db` (tests/f1/conftest.py) aplica `SET LOCAL` uma unica
    vez, e `SET LOCAL` morre no `COMMIT`. Todo helper daqui que commita
    precisa republicar antes da proxima consulta -- caso contrario a proxima
    leitura roda com `app.tenant_id` vazio e a RLS devolve zero linha (que e
    exatamente o comportamento correto do banco, e foi como este arquivo
    descobriu o detalhe).
    """
    await sessao_db.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"),
        {"t": str(identidade.tenant_id)},
    )


async def _perfil_do_admin(sessao_db: AsyncSession, identidade: IdentidadeDeTeste) -> Any:
    await _republicar_tenant(sessao_db, identidade)
    return (
        await sessao_db.execute(
            sa.select(UsuarioPerfil.perfil_id).where(
                UsuarioPerfil.tenant_id == identidade.tenant_id,
                UsuarioPerfil.usuario_id == identidade.usuario_id,
            )
        )
    ).scalar_one()


async def _conceder(
    sessao_db: AsyncSession, identidade: IdentidadeDeTeste, codigos: tuple[str, ...]
) -> None:
    perfil_id = await _perfil_do_admin(sessao_db, identidade)
    for codigo in codigos:
        permissao_id = (
            await sessao_db.execute(sa.select(Permissao.id).where(Permissao.codigo == codigo))
        ).scalar_one()
        existente = (
            await sessao_db.execute(
                sa.select(PerfilPermissao.id).where(
                    PerfilPermissao.tenant_id == identidade.tenant_id,
                    PerfilPermissao.perfil_id == perfil_id,
                    PerfilPermissao.permissao_id == permissao_id,
                )
            )
        ).scalar_one_or_none()
        if existente is None:
            sessao_db.add(
                PerfilPermissao(
                    tenant_id=identidade.tenant_id,
                    perfil_id=perfil_id,
                    permissao_id=permissao_id,
                    concedida=True,
                )
            )
    await sessao_db.commit()


async def _revogar(
    sessao_db: AsyncSession, identidade: IdentidadeDeTeste, codigos: tuple[str, ...]
) -> None:
    perfil_id = await _perfil_do_admin(sessao_db, identidade)
    await sessao_db.execute(
        sa.delete(PerfilPermissao).where(
            PerfilPermissao.tenant_id == identidade.tenant_id,
            PerfilPermissao.perfil_id == perfil_id,
            PerfilPermissao.permissao_id.in_(
                sa.select(Permissao.id).where(Permissao.codigo.in_(codigos))
            ),
        )
    )
    await sessao_db.commit()


def _autenticar(cliente: TestClient, identidade: IdentidadeDeTeste) -> str:
    resposta = cliente.post(
        "/v1/auth/login",
        json={"email": identidade.email, "senha": identidade.senha},
        headers=cabecalhos(identidade.tenant_slug),
    )
    assert resposta.status_code == 200, resposta.text
    return str(resposta.json()["accessToken"])


def _cabecalhos(identidade: IdentidadeDeTeste, token: str) -> dict[str, str]:
    return {**cabecalhos(identidade.tenant_slug), "Authorization": f"Bearer {token}"}


def _corpo_tenant_novo() -> dict[str, str]:
    sufixo = secrets.token_hex(4)
    return {
        "slug": f"suporte-teste-{sufixo}",
        "razaoSocial": f"Tenant criado pelo suporte {sufixo}",
        "nomeExibicao": f"Suporte {sufixo}",
    }


# =============================================================================
# 1. O portao fecha
# =============================================================================
async def test_sem_permissao_de_suporte_listar_e_criar_respondem_403(
    cliente: TestClient, identidade: IdentidadeDeTeste, sessao_db: AsyncSession
) -> None:
    """Com `tenants.ler`/`tenants.criar` (o que todo admin de tenant tem) e SEM
    `tenants.suporte`, as duas rotas recusam."""
    await _revogar(sessao_db, identidade, (PERMISSAO_SUPORTE,))
    await _conceder(sessao_db, identidade, PERMISSOES_DO_CONTRATO)

    token = _autenticar(cliente, identidade)

    listagem = cliente.get("/v1/tenants", headers=_cabecalhos(identidade, token))
    assert listagem.status_code == 403, listagem.text
    assert listagem.json()["codigo"] == "PONTO-PERM-001"

    criacao = cliente.post(
        "/v1/tenants", json=_corpo_tenant_novo(), headers=_cabecalhos(identidade, token)
    )
    assert criacao.status_code == 403, criacao.text
    assert criacao.json()["codigo"] == "PONTO-PERM-001"


def test_sem_credencial_nenhuma_responde_401(cliente: TestClient, contexto_f1: ContextoF1) -> None:
    resposta = cliente.get("/v1/tenants", headers=cabecalhos(contexto_f1.tenant_a.slug))
    assert resposta.status_code == 401, resposta.text
    assert resposta.json()["codigo"] == "PONTO-AUTH-002"


# =============================================================================
# 2. O bypass funciona
# =============================================================================
async def test_com_permissao_de_suporte_lista_tenants_de_multiplos_tenants(
    cliente: TestClient,
    contexto_f1: ContextoF1,
    identidade: IdentidadeDeTeste,
    sessao_db: AsyncSession,
) -> None:
    """A prova do bypass: UMA chamada devolve `tenant-a` E `tenant-b`.

    Sob RLS (qualquer outra sessao do sistema) a mesma consulta devolveria no
    maximo a linha do tenant corrente -- ver o teste de nao-regressao abaixo.
    """
    await _conceder(sessao_db, identidade, (PERMISSAO_SUPORTE,))
    token = _autenticar(cliente, identidade)

    vistos: set[str] = set()
    cursor: str | None = None
    for _ in range(20):  # teto defensivo: o banco de teste tem poucas dezenas
        url = "/v1/tenants?limite=100" + (f"&cursor={cursor}" if cursor else "")
        resposta = cliente.get(url, headers=_cabecalhos(identidade, token))
        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        vistos.update(item["id"] for item in corpo["dados"])
        cursor = corpo["paginacao"].get("proximoCursor")
        if not cursor:
            break

    assert str(contexto_f1.tenant_a.id) in vistos
    assert (
        str(contexto_f1.tenant_b.id) in vistos
    ), "listagem de suporte nao atravessou a fronteira de tenant: o bypass de RLS nao funcionou"


async def test_com_permissao_de_suporte_cria_tenant_e_ele_aparece_na_listagem(
    cliente: TestClient, identidade: IdentidadeDeTeste, sessao_db: AsyncSession
) -> None:
    await _conceder(sessao_db, identidade, (PERMISSAO_SUPORTE,))
    token = _autenticar(cliente, identidade)
    corpo_novo = _corpo_tenant_novo()

    criacao = cliente.post("/v1/tenants", json=corpo_novo, headers=_cabecalhos(identidade, token))
    assert criacao.status_code == 201, criacao.text
    criado = criacao.json()
    assert criado["slug"] == corpo_novo["slug"]
    assert criado["id"]

    busca = cliente.get(
        f"/v1/tenants?busca={corpo_novo['slug']}", headers=_cabecalhos(identidade, token)
    )
    assert busca.status_code == 200, busca.text
    assert [item["id"] for item in busca.json()["dados"]] == [criado["id"]]

    # Slug duplicado falha fechado, com o codigo do catalogo.
    repetido = cliente.post("/v1/tenants", json=corpo_novo, headers=_cabecalhos(identidade, token))
    assert repetido.status_code == 409, repetido.text
    assert repetido.json()["codigo"] == "PONTO-CONF-001"


# =============================================================================
# 3. RLS intacta para todo o resto
# =============================================================================
async def test_sessao_normal_continua_vendo_um_unico_tenant(
    contexto_f1: ContextoF1,
    abrir_sessao_tenant: AbrirSessaoTenant,
    fabrica_f1: async_sessionmaker[AsyncSession],
) -> None:
    """Nao-regressao do isolamento: a role de login comum nao ganhou bypass."""
    async with abrir_sessao_tenant(contexto_f1.tenant_a.id) as sessao:
        ids = set((await sessao.execute(text("SELECT id FROM tenants"))).scalars().all())
    assert ids == {contexto_f1.tenant_a.id}

    async with fabrica_f1() as sessao:
        bypass = (
            await sessao.execute(
                text(
                    "SELECT COALESCE((SELECT rolbypassrls FROM pg_roles "
                    "WHERE rolname = current_user), FALSE)"
                )
            )
        ).scalar_one()
    assert bypass is False, "a role de requisicao normal NAO pode ter BYPASSRLS"


async def test_credencial_de_suporte_tem_bypass_mas_alcance_de_duas_tabelas(
    contexto_f1: ContextoF1,
) -> None:
    """`BYPASSRLS` sim; `SELECT` em qualquer outra tabela, nao."""
    url = make_url(contexto_f1.url_login_async).set(
        username=ROLE_SUPORTE,
        password=os.environ.get("POSTGRES_SUPORTE_PASSWORD", SENHA_PADRAO_DEV),
    )
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as conexao:
            bypass = (
                await conexao.execute(
                    text(
                        "SELECT COALESCE((SELECT rolbypassrls FROM pg_roles "
                        "WHERE rolname = current_user), FALSE)"
                    )
                )
            ).scalar_one()
            assert bypass is True

            # Sem `app.tenant_id` publicado e sem filtro: enxerga todos.
            total = (await conexao.execute(text("SELECT count(*) FROM tenants"))).scalar_one()
            assert total >= 2

            with pytest.raises(ProgrammingError) as excecao:
                await conexao.execute(text("SELECT count(*) FROM usuarios"))
            assert "permission denied" in str(excecao.value).lower()
    finally:
        await engine.dispose()


# =============================================================================
# 4. A trilha registra o bypass
# =============================================================================
async def test_chamada_de_suporte_grava_auditoria_marcada_como_cross_tenant(
    cliente: TestClient,
    contexto_f1: ContextoF1,
    identidade: IdentidadeDeTeste,
    sessao_db: AsyncSession,
) -> None:
    await _conceder(sessao_db, identidade, (PERMISSAO_SUPORTE,))
    token = _autenticar(cliente, identidade)

    await _republicar_tenant(sessao_db, identidade)
    anterior = (
        await sessao_db.execute(
            text(
                "SELECT COALESCE(MAX(sequencia), 0) FROM auditoria "
                "WHERE tenant_id = :t AND evento = :e"
            ),
            {"t": str(contexto_f1.tenant_a.id), "e": servico_suporte.EVENTO_LISTAGEM},
        )
    ).scalar_one()

    resposta = cliente.get("/v1/tenants?limite=100", headers=_cabecalhos(identidade, token))
    assert resposta.status_code == 200, resposta.text

    await _republicar_tenant(sessao_db, identidade)
    linha = (
        await sessao_db.execute(
            text(
                "SELECT evento, acao, entidade, usuario_id, valor_novo, metadados, mensagem "
                "FROM auditoria WHERE tenant_id = :t AND evento = :e AND sequencia > :s "
                "ORDER BY sequencia DESC LIMIT 1"
            ),
            {
                "t": str(contexto_f1.tenant_a.id),
                "e": servico_suporte.EVENTO_LISTAGEM,
                "s": anterior,
            },
        )
    ).first()
    assert linha is not None, "a listagem de suporte nao gravou auditoria"
    assert linha.acao == "ler"
    assert linha.entidade == "tenants"
    assert linha.usuario_id == identidade.usuario_id
    # A marca do bypass esta DENTRO da formula do hash (`evento`/`valor_novo`),
    # nao so em `metadados` -- adultera-la quebra a cadeia.
    assert linha.valor_novo["bypass_rls"] is True
    assert linha.valor_novo["operacao"] == "listarTenants"
    assert linha.metadados["cross_tenant"] is True
    assert linha.metadados["role_banco"] == ROLE_SUPORTE
    # O que o suporte viu fica registrado, tenant a tenant.
    assert str(contexto_f1.tenant_b.id) in linha.metadados["tenants_retornados"]


async def test_criacao_de_tenant_grava_auditoria_com_o_tenant_criado(
    cliente: TestClient,
    contexto_f1: ContextoF1,
    identidade: IdentidadeDeTeste,
    sessao_db: AsyncSession,
) -> None:
    await _conceder(sessao_db, identidade, (PERMISSAO_SUPORTE,))
    token = _autenticar(cliente, identidade)

    criacao = cliente.post(
        "/v1/tenants", json=_corpo_tenant_novo(), headers=_cabecalhos(identidade, token)
    )
    assert criacao.status_code == 201, criacao.text
    id_criado = criacao.json()["id"]

    await _republicar_tenant(sessao_db, identidade)
    linha = (
        await sessao_db.execute(
            text(
                "SELECT acao, entidade_id, valor_novo, metadados FROM auditoria "
                "WHERE tenant_id = :t AND evento = :e AND entidade_id = :alvo"
            ),
            {
                "t": str(contexto_f1.tenant_a.id),
                "e": servico_suporte.EVENTO_CRIACAO,
                "alvo": id_criado,
            },
        )
    ).first()
    assert linha is not None, "a criacao de tenant pelo suporte nao gravou auditoria"
    assert linha.acao == "criar"
    assert linha.valor_novo["bypass_rls"] is True
    assert linha.metadados["tenant_criado"] == id_criado
