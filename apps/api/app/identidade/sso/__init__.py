"""Login federado (SSO): OIDC (`oidc/`, A9) e SAML 2.0 (`saml/`, A10).

RFC-018/ADR-013 (03/08/2026): tag `sso` no contrato, app OIDC compartilhado de
aplicacao para Google Workspace/Microsoft Entra ID (client id/secret de
AMBIENTE, nunca por tenant), IdP proprio por tenant para SAML. Nenhuma tabela
nova: a configuracao por tenant vive em `tenant_configuracoes`
(`sso.google.*`/`sso.entra_id.*`/`sso.saml.*`), o vinculo usuario x identidade
externa em `credenciais` (`tipo='sso'`, ja existente desde F1).

Este pacote (`app.identidade.sso`) e o unico ponto de `app.identidade` fora
de `tokens`/`autenticacao`/`mfa`/`rbac`/`tenancy` autorizado nesta fase — os
dois subpacotes `oidc/` e `saml/` sao exclusivos de A9/A10 (PCF da F13, secao
5.2), o resto de `app.identidade` continua travado.
"""

from __future__ import annotations
