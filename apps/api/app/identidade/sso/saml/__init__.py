"""Login federado SAML 2.0 (T20-T22, A10). Ver RFC-018/ADR-013.

Cada tenant configura o IdP proprio (`entityId`/`ssoUrl`/certificado X.509,
`GET/PUT /v1/admin/sso/provedores`) -- SAML nao tem app compartilhado, ao
contrario de `..oidc` (Google/Entra ID). Submodulos:

* `estado`     -- assina/valida o RelayState (tenant + correlacao
  InResponseTo + nonce), mesmo espirito de `..oidc.estado` mas com claims
  proprias (o `state` OIDC nao carrega ID de AuthnRequest).
* `protocolo`  -- fala SAML de verdade via `python3-saml` (`onelogin.saml2`):
  monta o AuthnRequest, valida a assinatura da asserção contra o certificado
  do IdP do tenant.
* `resolucao`  -- resolve/vincula `credenciais` (nunca cria `usuarios` novo)
  e emite o mesmo par de tokens de sessao que `autenticar`/`renovarSessao`
  (F1) ja emitem.

A configuracao por tenant (`entityId`/`ssoUrl`/certificado) e lida via
`app.identidade.sso.oidc.configuracao` (A9): aquele modulo já implementa a
leitura/escrita genérica das cinco chaves de `tenant_configuracoes` do
endpoint único `GET/PUT /v1/admin/sso/provedores` (RFC-018 não separa a
configuração por protocolo) -- reaproveitado aqui por leitura, nunca
duplicado nem editado.
"""
