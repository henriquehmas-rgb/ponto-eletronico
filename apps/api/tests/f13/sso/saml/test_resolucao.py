"""Resolve/vincula `credenciais` (T22, A10): nunca cria `usuarios` novo
(proibicao 11 do PCF), repontar de provedor quando ja existe uma credencial
`sso` ativa para outro provedor, e rejeicao de usuario bloqueado/inativo.

Contra banco real (`ponto_f13_a10`) -- `tests/f13/sso/saml/conftest.py`
fornece `tenant_com_usuario`/`sessao_db` com `app.tenant_id` ja publicado.
"""

from __future__ import annotations

import datetime as _dt
import uuid

import pytest
import sqlalchemy as sa
from ponto_contracts import Credencial, Usuario
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.identidade.sso.saml import resolucao
from tests.f13.sso.saml.conftest import TenantComUsuario

AGORA = _dt.datetime.now(_dt.UTC)


async def test_vincula_usuario_existente_pelo_email(
    sessao_db: AsyncSession, tenant_com_usuario: TenantComUsuario
) -> None:
    usuario = await resolucao.resolver_ou_vincular_usuario(
        sessao_db,
        tenant_id=tenant_com_usuario.tenant_id,
        identificador_externo=tenant_com_usuario.email,
        agora=AGORA,
    )

    assert usuario.id == tenant_com_usuario.usuario_id

    credencial = (
        await sessao_db.execute(
            sa.select(Credencial).where(
                Credencial.tenant_id == tenant_com_usuario.tenant_id,
                Credencial.usuario_id == tenant_com_usuario.usuario_id,
                Credencial.tipo == "sso",
            )
        )
    ).scalar_one()
    assert credencial.provedor_sso == "saml"
    assert credencial.identificador_externo == tenant_com_usuario.email
    assert credencial.ativo is True
    assert credencial.algoritmo == "nenhum"


async def test_segundo_login_reaproveita_a_mesma_credencial(
    sessao_db: AsyncSession, tenant_com_usuario: TenantComUsuario
) -> None:
    await resolucao.resolver_ou_vincular_usuario(
        sessao_db,
        tenant_id=tenant_com_usuario.tenant_id,
        identificador_externo=tenant_com_usuario.email,
        agora=AGORA,
    )
    await resolucao.resolver_ou_vincular_usuario(
        sessao_db,
        tenant_id=tenant_com_usuario.tenant_id,
        identificador_externo=tenant_com_usuario.email,
        agora=AGORA,
    )

    total = (
        await sessao_db.execute(
            sa.select(sa.func.count())
            .select_from(Credencial)
            .where(
                Credencial.tenant_id == tenant_com_usuario.tenant_id,
                Credencial.usuario_id == tenant_com_usuario.usuario_id,
                Credencial.tipo == "sso",
            )
        )
    ).scalar_one()
    assert total == 1


async def test_email_sem_usuario_correspondente_nunca_cria_usuario_novo(
    sessao_db: AsyncSession, tenant_com_usuario: TenantComUsuario
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await resolucao.resolver_ou_vincular_usuario(
            sessao_db,
            tenant_id=tenant_com_usuario.tenant_id,
            identificador_externo="nao-cadastrado@f13-a10.teste",
            agora=AGORA,
        )
    assert excinfo.value.codigo == "PONTO-AUTH-001"

    total_usuarios = (
        await sessao_db.execute(
            sa.select(sa.func.count())
            .select_from(Usuario)
            .where(Usuario.tenant_id == tenant_com_usuario.tenant_id)
        )
    ).scalar_one()
    assert total_usuarios == 1  # so o usuario semeado pela fixture, nenhum novo


async def test_repontar_credencial_sso_de_outro_provedor(
    sessao_db: AsyncSession, tenant_com_usuario: TenantComUsuario
) -> None:
    """Usuario ja tinha uma credencial sso ativa via 'google' (vinculada por
    A9/OIDC) -- o primeiro login SAML repontou a MESMA linha, nunca duas
    ativas (uq_credenciais_ativa nao aceitaria)."""
    sessao_db.add(
        Credencial(
            tenant_id=tenant_com_usuario.tenant_id,
            usuario_id=tenant_com_usuario.usuario_id,
            tipo="sso",
            provedor_sso="google",
            identificador_externo="sub-google-123",
            hash="x" * 16,
            algoritmo="nenhum",
            ativo=True,
        )
    )
    await sessao_db.flush()

    usuario = await resolucao.resolver_ou_vincular_usuario(
        sessao_db,
        tenant_id=tenant_com_usuario.tenant_id,
        identificador_externo=tenant_com_usuario.email,
        agora=AGORA,
    )
    assert usuario.id == tenant_com_usuario.usuario_id

    credenciais = (
        (
            await sessao_db.execute(
                sa.select(Credencial).where(
                    Credencial.tenant_id == tenant_com_usuario.tenant_id,
                    Credencial.usuario_id == tenant_com_usuario.usuario_id,
                    Credencial.tipo == "sso",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(credenciais) == 1
    assert credenciais[0].provedor_sso == "saml"
    assert credenciais[0].identificador_externo == tenant_com_usuario.email


async def test_emitir_sessao_rejeita_usuario_bloqueado(
    sessao_db: AsyncSession, tenant_com_usuario: TenantComUsuario
) -> None:
    usuario = (
        await sessao_db.execute(
            sa.select(Usuario).where(Usuario.id == tenant_com_usuario.usuario_id)
        )
    ).scalar_one()
    usuario.status = "bloqueado"
    await sessao_db.flush()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await resolucao.emitir_sessao(
            sessao_db,
            tenant_id=tenant_com_usuario.tenant_id,
            usuario=usuario,
            ip=None,
            user_agent=None,
            agora=AGORA,
        )
    assert excinfo.value.codigo == "PONTO-AUTH-010"


async def test_emitir_sessao_gera_tokens_e_sessao_real(
    sessao_db: AsyncSession, tenant_com_usuario: TenantComUsuario
) -> None:
    usuario = (
        await sessao_db.execute(
            sa.select(Usuario).where(Usuario.id == tenant_com_usuario.usuario_id)
        )
    ).scalar_one()

    resultado = await resolucao.emitir_sessao(
        sessao_db,
        tenant_id=tenant_com_usuario.tenant_id,
        usuario=usuario,
        ip="203.0.113.10",
        user_agent="pytest",
        agora=AGORA,
    )

    assert resultado.access_token
    assert resultado.refresh_token
    assert resultado.expires_in > 0
    assert isinstance(resultado.sessao_id, uuid.UUID)

    linha = (
        (
            await sessao_db.execute(
                sa.text("SELECT canal FROM sessoes WHERE id = :id"),
                {"id": str(resultado.sessao_id)},
            )
        )
        .mappings()
        .one()
    )
    assert linha["canal"] == "web"
