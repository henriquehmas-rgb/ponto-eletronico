"""`app.identidade.sso.oidc.resolucao`: allowlist por tenant, vinculo de
`credenciais` (nunca cria `usuarios` novo) e emissao de sessao -- contra o
banco real (`ponto_f13_a9`, ver `conftest.py`).

Cobre o criterio de aceite 11/T21 do PCF: login end-to-end resulta em sessao
valida com `credenciais.tipo='sso'` gravada corretamente."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from ponto_contracts import Credencial, Sessao, Usuario

from app.core.erros import ErroDeAplicacao
from app.identidade.sso.oidc import resolucao
from app.identidade.sso.oidc.protocolo import ClaimsIdToken

from .conftest import (
    DOMINIO_GOOGLE_PERMITIDO,
    ENTRA_TENANT_ID_PERMITIDO,
    ContextoSsoOidcF13,
    aplicar_tenant_teste,
)

pytestmark = pytest.mark.asyncio


def _claims(**overrides: object) -> ClaimsIdToken:
    base = {
        "sub": "sub-google-1",
        "email": None,
        "email_verificado": True,
        "tid": None,
        "hd": None,
    }
    base.update(overrides)
    return ClaimsIdToken(**base)  # type: ignore[arg-type]


async def test_primeiro_login_vincula_usuario_existente_sem_criar_novo(
    sessao_f13a9, contexto_sso_oidc_f13a9: ContextoSsoOidcF13
) -> None:
    claims = _claims(sub="sub-google-1", email=contexto_sso_oidc_f13a9.usuario_email)

    resultado = await resolucao.resolver_e_emitir_sessao(
        sessao_f13a9,
        tenant_id=contexto_sso_oidc_f13a9.tenant_id,
        provedor="google",
        claims=claims,
        ip="203.0.113.10",
        user_agent="pytest",
    )

    assert resultado.usuario.id == contexto_sso_oidc_f13a9.usuario_id
    assert resultado.access_token
    assert resultado.refresh_token

    total_usuarios = (
        await sessao_f13a9.execute(
            sa.select(sa.func.count())
            .select_from(Usuario)
            .where(Usuario.tenant_id == contexto_sso_oidc_f13a9.tenant_id)
        )
    ).scalar_one()
    assert total_usuarios == 1  # nenhum usuario novo foi criado

    credencial = (
        await sessao_f13a9.execute(
            sa.select(Credencial).where(
                Credencial.tenant_id == contexto_sso_oidc_f13a9.tenant_id,
                Credencial.usuario_id == contexto_sso_oidc_f13a9.usuario_id,
                Credencial.tipo == "sso",
            )
        )
    ).scalar_one()
    assert credencial.provedor_sso == "google"
    assert credencial.identificador_externo == "sub-google-1"
    assert credencial.algoritmo == "nenhum"
    assert credencial.ativo is True
    assert credencial.hash  # nunca vazio, nunca o sub em claro
    assert credencial.hash != "sub-google-1"

    sessao_criada = await sessao_f13a9.get(Sessao, resultado.sessao_id)
    assert sessao_criada is not None
    assert sessao_criada.canal == "web"


async def test_segundo_login_mesmo_provedor_reusa_credencial_existente(
    sessao_f13a9, contexto_sso_oidc_f13a9: ContextoSsoOidcF13
) -> None:
    claims = _claims(sub="sub-google-1", email=contexto_sso_oidc_f13a9.usuario_email)
    await resolucao.resolver_e_emitir_sessao(
        sessao_f13a9,
        tenant_id=contexto_sso_oidc_f13a9.tenant_id,
        provedor="google",
        claims=claims,
        ip=None,
        user_agent=None,
    )
    await resolucao.resolver_e_emitir_sessao(
        sessao_f13a9,
        tenant_id=contexto_sso_oidc_f13a9.tenant_id,
        provedor="google",
        claims=claims,
        ip=None,
        user_agent=None,
    )

    total_credenciais_sso = (
        await sessao_f13a9.execute(
            sa.select(sa.func.count())
            .select_from(Credencial)
            .where(
                Credencial.tenant_id == contexto_sso_oidc_f13a9.tenant_id,
                Credencial.usuario_id == contexto_sso_oidc_f13a9.usuario_id,
                Credencial.tipo == "sso",
            )
        )
    ).scalar_one()
    assert total_credenciais_sso == 1  # uq_credenciais_ativa: no maximo uma linha


async def test_sem_usuario_correspondente_nunca_cria_novo(
    sessao_f13a9, contexto_sso_oidc_f13a9: ContextoSsoOidcF13
) -> None:
    claims = _claims(sub="sub-desconhecido", email=f"ninguem@{DOMINIO_GOOGLE_PERMITIDO}")

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await resolucao.resolver_e_emitir_sessao(
            sessao_f13a9,
            tenant_id=contexto_sso_oidc_f13a9.tenant_id,
            provedor="google",
            claims=claims,
            ip=None,
            user_agent=None,
        )
    assert excinfo.value.codigo == "PONTO-AUTH-001"

    total_usuarios = (
        await sessao_f13a9.execute(
            sa.select(sa.func.count())
            .select_from(Usuario)
            .where(Usuario.tenant_id == contexto_sso_oidc_f13a9.tenant_id)
        )
    ).scalar_one()
    assert total_usuarios == 1  # continua so o usuario semeado pela fixture


async def test_dominio_de_email_fora_da_allowlist_rejeita(
    sessao_f13a9, contexto_sso_oidc_f13a9: ContextoSsoOidcF13
) -> None:
    claims = _claims(sub="sub-google-2", email="pessoa@dominio-nao-autorizado.com.br")

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await resolucao.resolver_e_emitir_sessao(
            sessao_f13a9,
            tenant_id=contexto_sso_oidc_f13a9.tenant_id,
            provedor="google",
            claims=claims,
            ip=None,
            user_agent=None,
        )
    assert excinfo.value.codigo == "PONTO-TEN-001"


async def test_entra_tenant_id_fora_da_allowlist_rejeita(
    sessao_f13a9, contexto_sso_oidc_f13a9: ContextoSsoOidcF13
) -> None:
    claims = _claims(
        sub="sub-entra-1",
        email=contexto_sso_oidc_f13a9.usuario_email,
        tid="00000000-0000-0000-0000-000000000000",
    )

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await resolucao.resolver_e_emitir_sessao(
            sessao_f13a9,
            tenant_id=contexto_sso_oidc_f13a9.tenant_id,
            provedor="entra_id",
            claims=claims,
            ip=None,
            user_agent=None,
        )
    assert excinfo.value.codigo == "PONTO-TEN-001"


async def test_entra_tenant_id_na_allowlist_aceita(
    sessao_f13a9, contexto_sso_oidc_f13a9: ContextoSsoOidcF13
) -> None:
    claims = _claims(
        sub="sub-entra-2",
        email=contexto_sso_oidc_f13a9.usuario_email,
        tid=ENTRA_TENANT_ID_PERMITIDO,
    )

    resultado = await resolucao.resolver_e_emitir_sessao(
        sessao_f13a9,
        tenant_id=contexto_sso_oidc_f13a9.tenant_id,
        provedor="entra_id",
        claims=claims,
        ip=None,
        user_agent=None,
    )
    assert resultado.usuario.id == contexto_sso_oidc_f13a9.usuario_id


async def test_troca_de_provedor_revincula_credencial_ativa_unica(
    sessao_f13a9, contexto_sso_oidc_f13a9: ContextoSsoOidcF13
) -> None:
    """Usuario ja logado por `google`; loga por `entra_id` -- a credencial
    `sso` ativa e RE-VINCULADA (decisao documentada em `resolucao.py`), nunca
    duas linhas simultaneas (o schema so permite uma, `uq_credenciais_ativa`)."""
    claims_google = _claims(sub="sub-google-3", email=contexto_sso_oidc_f13a9.usuario_email)
    await resolucao.resolver_e_emitir_sessao(
        sessao_f13a9,
        tenant_id=contexto_sso_oidc_f13a9.tenant_id,
        provedor="google",
        claims=claims_google,
        ip=None,
        user_agent=None,
    )

    claims_entra = _claims(
        sub="sub-entra-3",
        email=contexto_sso_oidc_f13a9.usuario_email,
        tid=ENTRA_TENANT_ID_PERMITIDO,
    )
    await resolucao.resolver_e_emitir_sessao(
        sessao_f13a9,
        tenant_id=contexto_sso_oidc_f13a9.tenant_id,
        provedor="entra_id",
        claims=claims_entra,
        ip=None,
        user_agent=None,
    )

    credenciais_sso = (
        (
            await sessao_f13a9.execute(
                sa.select(Credencial).where(
                    Credencial.tenant_id == contexto_sso_oidc_f13a9.tenant_id,
                    Credencial.usuario_id == contexto_sso_oidc_f13a9.usuario_id,
                    Credencial.tipo == "sso",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(credenciais_sso) == 1
    assert credenciais_sso[0].provedor_sso == "entra_id"
    assert credenciais_sso[0].identificador_externo == "sub-entra-3"


async def test_usuario_bloqueado_rejeita_mesmo_com_credencial_valida(
    sessao_f13a9, contexto_sso_oidc_f13a9: ContextoSsoOidcF13
) -> None:
    usuario = await sessao_f13a9.get(Usuario, contexto_sso_oidc_f13a9.usuario_id)
    assert usuario is not None
    usuario.status = "bloqueado"
    await sessao_f13a9.flush()

    claims = _claims(sub="sub-google-4", email=contexto_sso_oidc_f13a9.usuario_email)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await resolucao.resolver_e_emitir_sessao(
            sessao_f13a9,
            tenant_id=contexto_sso_oidc_f13a9.tenant_id,
            provedor="google",
            claims=claims,
            ip=None,
            user_agent=None,
        )
    assert excinfo.value.codigo == "PONTO-AUTH-010"


async def test_verificar_provedor_habilitado_sem_configuracao_falha_fechado(
    sessao_f13a9,
) -> None:
    tenant_sem_configuracao = uuid.uuid4()
    await aplicar_tenant_teste(sessao_f13a9, tenant_sem_configuracao)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await resolucao.verificar_provedor_habilitado(
            sessao_f13a9, tenant_id=tenant_sem_configuracao, provedor="google"
        )
    assert excinfo.value.codigo == "PONTO-TEN-001"


async def test_verificar_provedor_habilitado_com_configuracao_passa(
    sessao_f13a9, contexto_sso_oidc_f13a9: ContextoSsoOidcF13
) -> None:
    await resolucao.verificar_provedor_habilitado(
        sessao_f13a9, tenant_id=contexto_sso_oidc_f13a9.tenant_id, provedor="google"
    )
    await resolucao.verificar_provedor_habilitado(
        sessao_f13a9, tenant_id=contexto_sso_oidc_f13a9.tenant_id, provedor="entra_id"
    )
