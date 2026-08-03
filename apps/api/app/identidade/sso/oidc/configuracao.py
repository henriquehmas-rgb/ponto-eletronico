"""Allowlist de SSO por tenant, guardada em `tenant_configuracoes` (RFC-018/
ADR-013 secao 5, GET/PUT `/v1/admin/sso/provedores`).

Cinco chaves fixas (nenhuma tabela nova, decisao do ADR-013): duas para OIDC
(`sso.google.dominios_permitidos`, `sso.entra_id.tenant_id`, usadas por este
pacote) e tres para SAML (`sso.saml.entity_id`/`sso.saml.sso_url`/
`sso.saml.certificado_x509`, consumidas por `app.identidade.sso.saml`,
exclusivo de A10). O endpoint `/v1/admin/sso/provedores` e uma superficie
UNICA para as cinco (RFC-018 nao separa a configuracao por protocolo), por
isso este modulo le/escreve as cinco -- inclusive as tres de SAML, que ele
nunca interpreta, so armazena. Nenhuma delas e segredo: certificado X.509 e
chave publica, e client id/secret do app OIDC compartilhado vivem em
`Configuracao` (variavel de ambiente), nunca aqui.

Nao reaproveita `app.identidade.tenancy.servico.definir_configuracao_tenant`
(ownership de F1/A2, fora do pacote exclusivo desta fase): aquela funcao
grava UMA chave por chamada e espera um schema com
`categoria`/`valor`/`descricao`/`somente_leitura`, forma que nao encaixa bem
num upsert de cinco chaves relacionadas em uma unica chamada HTTP. Este
modulo escreve direto no modelo ORM `TenantConfiguracao` (mesma tabela,
mesmo padrao de UPSERT por `(tenant_id, chave)` -- `uq_tenant_configuracoes`
-- so que para as cinco chaves de uma vez).
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from ponto_contracts import TenantConfiguracao
from sqlalchemy.ext.asyncio import AsyncSession

CATEGORIA = "integracao"

CHAVE_GOOGLE_DOMINIOS = "sso.google.dominios_permitidos"
CHAVE_ENTRA_TENANT_ID = "sso.entra_id.tenant_id"
CHAVE_SAML_ENTITY_ID = "sso.saml.entity_id"
CHAVE_SAML_SSO_URL = "sso.saml.sso_url"
CHAVE_SAML_CERTIFICADO_X509 = "sso.saml.certificado_x509"

#: campo do schema `ConfiguracaoSso` -> chave em `tenant_configuracoes`.
_CAMPO_PARA_CHAVE: dict[str, str] = {
    "google_dominios_permitidos": CHAVE_GOOGLE_DOMINIOS,
    "entra_id_tenant_id": CHAVE_ENTRA_TENANT_ID,
    "saml_entity_id": CHAVE_SAML_ENTITY_ID,
    "saml_sso_url": CHAVE_SAML_SSO_URL,
    "saml_certificado_x509": CHAVE_SAML_CERTIFICADO_X509,
}


async def ler_valor(sessao_db: AsyncSession, *, tenant_id: uuid.UUID, chave: str) -> Any | None:
    """Le uma chave isolada (usada em tempo de login por `resolucao.py`)."""
    return (
        await sessao_db.execute(
            sa.select(TenantConfiguracao.valor).where(
                TenantConfiguracao.tenant_id == tenant_id,
                TenantConfiguracao.chave == chave,
            )
        )
    ).scalar_one_or_none()


async def carregar_configuracao(sessao_db: AsyncSession, *, tenant_id: uuid.UUID) -> dict[str, Any]:
    """Le as cinco chaves de uma vez. Devolve `{campo_do_schema: valor | None}`."""
    chaves = list(_CAMPO_PARA_CHAVE.values())
    linhas = (
        await sessao_db.execute(
            sa.select(TenantConfiguracao.chave, TenantConfiguracao.valor).where(
                TenantConfiguracao.tenant_id == tenant_id,
                TenantConfiguracao.chave.in_(chaves),
            )
        )
    ).all()
    por_chave: dict[str, Any] = {chave: valor for chave, valor in linhas}  # noqa: C416
    return {campo: por_chave.get(chave) for campo, chave in _CAMPO_PARA_CHAVE.items()}


async def atualizar_configuracao(
    sessao_db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    campos: dict[str, Any],
    usuario_id: uuid.UUID | None,
) -> dict[str, Any]:
    """Upsert parcial: só grava as chaves presentes (nao-`None`) em `campos`.

    Campo ausente ou `None` no corpo da requisicao NAO apaga o valor
    existente -- mesma semantica de "atualizacao parcial" documentada na
    operacao (`atualizarConfiguracaoSso`, `openapi.yaml`). Para apagar uma
    chave explicitamente, o chamador manda lista vazia (`[]`) para os
    dominios do Google, unico campo em que "vazio" tem significado
    distinto de "nao informado".
    """
    for campo, valor in campos.items():
        if campo not in _CAMPO_PARA_CHAVE or valor is None:
            continue
        chave = _CAMPO_PARA_CHAVE[campo]
        existente = (
            await sessao_db.execute(
                sa.select(TenantConfiguracao).where(
                    TenantConfiguracao.tenant_id == tenant_id,
                    TenantConfiguracao.chave == chave,
                )
            )
        ).scalar_one_or_none()
        if existente is None:
            sessao_db.add(
                TenantConfiguracao(
                    tenant_id=tenant_id,
                    chave=chave,
                    categoria=CATEGORIA,
                    valor=valor,
                    criado_por=usuario_id,
                )
            )
        else:
            existente.valor = valor
            existente.atualizado_por = usuario_id
    await sessao_db.flush()
    return await carregar_configuracao(sessao_db, tenant_id=tenant_id)
