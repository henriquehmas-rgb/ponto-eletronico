"""`app.identidade.sso.oidc.configuracao`: leitura/escrita da allowlist de SSO
em `tenant_configuracoes` (GET/PUT `/v1/admin/sso/provedores`).

Testado na camada de servico (nao pela rota HTTP): `admin.configurar` e uma
permissao NOVA desta RFC (RFC-018/ADR-013 decisao 4) que ainda nao tem linha
no catalogo `permissoes` semeado por `apps/api/migrations/seed_dev.py`
(fora do ownership desta fase/agente -- achado registrado no relatorio final,
nao um bug deste modulo). Testar a camada de servico direto prova a logica
de upsert sem depender dessa lacuna de seed."""

from __future__ import annotations

import pytest

from app.identidade.sso.oidc import configuracao as config_sso

pytestmark = pytest.mark.asyncio


async def test_carregar_configuracao_vazia_devolve_todos_os_campos_none(
    sessao_f13a9, contexto_sso_oidc_f13a9
) -> None:
    """A fixture da fase (`contexto_sso_oidc_f13a9`) ja semeia google/entra_id;
    usa um tenant novo, sem nenhuma linha em `tenant_configuracoes`, para
    provar o caso vazio."""
    import uuid

    from .conftest import aplicar_tenant_teste

    tenant_vazio = uuid.uuid4()
    await aplicar_tenant_teste(sessao_f13a9, tenant_vazio)

    dados = await config_sso.carregar_configuracao(sessao_f13a9, tenant_id=tenant_vazio)

    assert dados == {
        "google_dominios_permitidos": None,
        "entra_id_tenant_id": None,
        "saml_entity_id": None,
        "saml_sso_url": None,
        "saml_certificado_x509": None,
    }


async def test_atualizar_configuracao_cria_e_depois_atualiza(
    sessao_f13a9, contexto_sso_oidc_f13a9
) -> None:
    tenant_id = contexto_sso_oidc_f13a9.tenant_id

    primeiro = await config_sso.atualizar_configuracao(
        sessao_f13a9,
        tenant_id=tenant_id,
        campos={"entra_id_tenant_id": "aaaa-bbbb"},
        usuario_id=contexto_sso_oidc_f13a9.usuario_id,
    )
    assert primeiro["entra_id_tenant_id"] == "aaaa-bbbb"
    # Campo semeado pela fixture da fase permanece intacto -- upsert e por chave.
    assert primeiro["google_dominios_permitidos"] is not None

    segundo = await config_sso.atualizar_configuracao(
        sessao_f13a9,
        tenant_id=tenant_id,
        campos={"entra_id_tenant_id": "cccc-dddd"},
        usuario_id=contexto_sso_oidc_f13a9.usuario_id,
    )
    assert segundo["entra_id_tenant_id"] == "cccc-dddd"


async def test_atualizar_configuracao_campo_ausente_nao_apaga_valor_existente(
    sessao_f13a9, contexto_sso_oidc_f13a9
) -> None:
    tenant_id = contexto_sso_oidc_f13a9.tenant_id
    antes = await config_sso.carregar_configuracao(sessao_f13a9, tenant_id=tenant_id)
    assert antes["google_dominios_permitidos"] is not None

    depois = await config_sso.atualizar_configuracao(
        sessao_f13a9,
        tenant_id=tenant_id,
        campos={"saml_entity_id": "https://idp-teste.exemplo/entity"},
        usuario_id=contexto_sso_oidc_f13a9.usuario_id,
    )

    assert depois["saml_entity_id"] == "https://idp-teste.exemplo/entity"
    assert depois["google_dominios_permitidos"] == antes["google_dominios_permitidos"]


async def test_atualizar_configuracao_campo_desconhecido_e_ignorado(
    sessao_f13a9, contexto_sso_oidc_f13a9
) -> None:
    dados = await config_sso.atualizar_configuracao(
        sessao_f13a9,
        tenant_id=contexto_sso_oidc_f13a9.tenant_id,
        campos={"campo_que_nao_existe": "valor"},
        usuario_id=contexto_sso_oidc_f13a9.usuario_id,
    )
    assert "campo_que_nao_existe" not in dados


async def test_ler_valor_chave_isolada(sessao_f13a9, contexto_sso_oidc_f13a9) -> None:
    valor = await config_sso.ler_valor(
        sessao_f13a9,
        tenant_id=contexto_sso_oidc_f13a9.tenant_id,
        chave=config_sso.CHAVE_ENTRA_TENANT_ID,
    )
    assert valor is not None
