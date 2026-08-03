"""IdP SAML configurado por tenant: leitura via `app.identidade.sso.oidc.
configuracao` (A9), que ja implementa a superficie UNICA de `GET/PUT
/v1/admin/sso/provedores` para as cinco chaves de `tenant_configuracoes`
(RFC-018 nao separa a configuracao por protocolo -- ver docstring daquele
modulo). Este arquivo so extrai as tres chaves de SAML e as devolve num tipo
proprio, sem duplicar leitura nem escrita.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.identidade.sso.oidc import configuracao as configuracao_oidc


@dataclass(frozen=True, slots=True)
class ConfigIdpSaml:
    entity_id: str | None
    sso_url: str | None
    certificado_x509: str | None

    @property
    def configurado(self) -> bool:
        return bool(self.entity_id and self.sso_url and self.certificado_x509)


async def ler_config_idp(sessao_db: AsyncSession, *, tenant_id: uuid.UUID) -> ConfigIdpSaml:
    campos = await configuracao_oidc.carregar_configuracao(sessao_db, tenant_id=tenant_id)
    return ConfigIdpSaml(
        entity_id=campos.get("saml_entity_id"),
        sso_url=campos.get("saml_sso_url"),
        certificado_x509=campos.get("saml_certificado_x509"),
    )
