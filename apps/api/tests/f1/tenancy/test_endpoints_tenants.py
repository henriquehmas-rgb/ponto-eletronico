"""T2 -- caminho feliz (mesmo tenant, permissao concedida) dos endpoints de
`app/routers/tenants.py` que `test_isolamento.py`/`test_resolucao_tenant.py`
nao exercitam (eles cobrem deliberadamente so os caminhos publicos e as
recusas cross-tenant, que nao exigem sujeito autenticado).

Login de verdade via `POST /v1/auth/login` (F1/A1) exige um par RS256: gerado
aqui, descartavel, isolado deste modulo (nao mexe em
`tests/f1/conftest.py`, ownership exclusivo do agente A2, nem em
`tests/f1/autenticacao/conftest.py`, ownership exclusivo do agente A1) --
mesma receita de `tests/f1/autenticacao/conftest.py:_chaves_rs256`.

A fixture `identidade` (`tests/f1/conftest.py`) so concede
`teste_f1_a2.ler` ao admin de `tenant-a`. As permissoes `tenants.ler`,
`tenants.editar` e `tenants.configurar` sao concedidas aqui, por este modulo,
inserindo diretamente na `perfil_permissoes` do perfil que a fixture ja
atribuiu ao admin -- sem alterar nenhum arquivo compartilhado.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from ponto_contracts import PerfilPermissao, Permissao, UsuarioPerfil
from sqlalchemy.ext.asyncio import AsyncSession

from app.identidade.tokens import chaves as jwt_chaves
from tests.f1.conftest import ContextoF1, IdentidadeDeTeste, cabecalhos

CODIGOS_PERMISSAO_NECESSARIOS = ("tenants.ler", "tenants.editar", "tenants.configurar")


@pytest.fixture(scope="module", autouse=True)
def _chaves_rs256(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Par RS256 descartavel, so para este modulo poder chamar `/v1/auth/login`.

    Mesma receita de `tests/f1/autenticacao/conftest.py:_chaves_rs256` --
    duplicada de proposito (esse arquivo e ownership exclusivo do agente A1;
    este modulo nao depende dele para poder rodar sozinho).
    """
    diretorio = tmp_path_factory.mktemp("jwt-tenants")
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


@pytest.fixture
async def _conceder_permissoes_tenants(
    identidade: IdentidadeDeTeste, sessao_db: AsyncSession
) -> None:
    """Concede `tenants.{ler,editar,configurar}` ao perfil do admin de teste."""
    perfil_id = (
        await sessao_db.execute(
            sa.select(UsuarioPerfil.perfil_id).where(
                UsuarioPerfil.tenant_id == identidade.tenant_id,
                UsuarioPerfil.usuario_id == identidade.usuario_id,
            )
        )
    ).scalar_one()
    for codigo in CODIGOS_PERMISSAO_NECESSARIOS:
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


def _autenticar(cliente: TestClient, identidade: IdentidadeDeTeste) -> str:
    resposta = cliente.post(
        "/v1/auth/login",
        json={"email": identidade.email, "senha": identidade.senha},
        headers=cabecalhos(identidade.tenant_slug),
    )
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["mfaRequerido"] is False
    assert corpo["accessToken"]
    return str(corpo["accessToken"])


def _cabecalhos_autenticados(identidade: IdentidadeDeTeste, token: str) -> dict[str, str]:
    return {**cabecalhos(identidade.tenant_slug), "Authorization": f"Bearer {token}"}


@pytest.mark.usefixtures("_conceder_permissoes_tenants")
def test_obter_tenant_do_proprio_tenant_com_permissao_devolve_200(
    cliente: TestClient, contexto_f1: ContextoF1, identidade: IdentidadeDeTeste
) -> None:
    token = _autenticar(cliente, identidade)
    resposta = cliente.get(
        f"/v1/tenants/{contexto_f1.tenant_a.id}",
        headers=_cabecalhos_autenticados(identidade, token),
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["id"] == str(contexto_f1.tenant_a.id)
    assert resposta.json()["slug"] == "tenant-a"


@pytest.mark.usefixtures("_conceder_permissoes_tenants")
def test_atualizar_tenant_do_proprio_tenant_persiste_e_e_lido_de_volta(
    cliente: TestClient, contexto_f1: ContextoF1, identidade: IdentidadeDeTeste
) -> None:
    token = _autenticar(cliente, identidade)
    novo_nome = f"Tenant A renomeado {secrets.token_hex(4)}"

    resposta = cliente.patch(
        f"/v1/tenants/{contexto_f1.tenant_a.id}",
        json={"nomeExibicao": novo_nome},
        headers={
            **_cabecalhos_autenticados(identidade, token),
            "Idempotency-Key": f"teste-atualizar-tenant-{secrets.token_hex(8)}",
        },
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["nomeExibicao"] == novo_nome

    conferencia = cliente.get("/v1/tenants/atual", headers=cabecalhos(contexto_f1.tenant_a.slug))
    assert conferencia.json()["nomeExibicao"] == novo_nome


@pytest.mark.usefixtures("_conceder_permissoes_tenants")
def test_definir_e_listar_configuracao_do_tenant(
    cliente: TestClient, contexto_f1: ContextoF1, identidade: IdentidadeDeTeste
) -> None:
    token = _autenticar(cliente, identidade)
    chave = f"teste.f1a2.endpoint.{secrets.token_hex(4)}"

    criacao = cliente.put(
        f"/v1/tenants/{contexto_f1.tenant_a.id}/configuracoes/{chave}",
        json={"categoria": "geral", "chave": chave, "valor": {"ligado": True}},
        headers={
            **_cabecalhos_autenticados(identidade, token),
            "Idempotency-Key": f"teste-definir-config-{secrets.token_hex(8)}",
        },
    )
    assert criacao.status_code == 200, criacao.text
    assert criacao.json()["chave"] == chave
    assert criacao.json()["valor"] == {"ligado": True}

    atualizacao = cliente.put(
        f"/v1/tenants/{contexto_f1.tenant_a.id}/configuracoes/{chave}",
        json={"categoria": "geral", "chave": chave, "valor": {"ligado": False}},
        headers={
            **_cabecalhos_autenticados(identidade, token),
            "Idempotency-Key": f"teste-definir-config-{secrets.token_hex(8)}",
        },
    )
    assert atualizacao.status_code == 200, atualizacao.text
    assert atualizacao.json()["valor"] == {"ligado": False}
    # Upsert: mesma linha (mesmo id), nao uma segunda.
    assert atualizacao.json()["id"] == criacao.json()["id"]

    listagem = cliente.get(
        f"/v1/tenants/{contexto_f1.tenant_a.id}/configuracoes",
        headers=_cabecalhos_autenticados(identidade, token),
    )
    assert listagem.status_code == 200, listagem.text
    chaves_vistas = {item["chave"] for item in listagem.json()["dados"]}
    assert chave in chaves_vistas


async def test_obter_tenant_do_proprio_tenant_sem_permissao_e_perm_001(
    cliente: TestClient,
    contexto_f1: ContextoF1,
    identidade: IdentidadeDeTeste,
    sessao_db: AsyncSession,
) -> None:
    """Por padrao (fora do fixture `_conceder_permissoes_tenants`) o admin de
    teste so tem `teste_f1_a2.ler`, nao `tenants.ler`. Revoga explicitamente
    aqui em vez de so confiar em "nenhum outro teste deste modulo rodou
    antes": os testes anteriores COMMITAM a concessao (perfil compartilhado
    entre todos os testes do modulo), entao a ordem de execucao do pytest
    nao pode ser premissa -- revogar deixa este teste correto nas duas ordens.
    """
    perfil_id = (
        await sessao_db.execute(
            sa.select(UsuarioPerfil.perfil_id).where(
                UsuarioPerfil.tenant_id == identidade.tenant_id,
                UsuarioPerfil.usuario_id == identidade.usuario_id,
            )
        )
    ).scalar_one()
    await sessao_db.execute(
        sa.delete(PerfilPermissao).where(
            PerfilPermissao.tenant_id == identidade.tenant_id,
            PerfilPermissao.perfil_id == perfil_id,
            PerfilPermissao.permissao_id.in_(
                sa.select(Permissao.id).where(Permissao.codigo.in_(CODIGOS_PERMISSAO_NECESSARIOS))
            ),
        )
    )
    await sessao_db.commit()

    token = _autenticar(cliente, identidade)
    resposta = cliente.get(
        f"/v1/tenants/{contexto_f1.tenant_a.id}",
        headers=_cabecalhos_autenticados(identidade, token),
    )
    assert resposta.status_code == 403
    assert resposta.json()["codigo"] == "PONTO-PERM-001"
