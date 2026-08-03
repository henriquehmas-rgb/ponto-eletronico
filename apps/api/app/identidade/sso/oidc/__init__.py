"""Login federado via OIDC (Google Workspace, Microsoft Entra ID) -- F13/A9, T20/T21.

`provedores.py`   -- registro dos dois provedores suportados (endpoints fixos,
                      client id/secret do app compartilhado, ADR-013).
`estado.py`       -- assinatura/validacao do `state` anti-CSRF que carrega o
                      tenant entre `iniciar` e `callback` (redirect_uri e fixo
                      e compartilhado por todos os tenants -- nao ha subdominio
                      nem cabecalho para resolver o tenant na volta do IdP).
`protocolo.py`    -- chamadas HTTP: troca de `code` por tokens, validacao do
                      `id_token` (assinatura via JWKS, emissor, audiencia, nonce).
`configuracao.py` -- leitura/escrita da allowlist por tenant em
                      `tenant_configuracoes` (GET/PUT /v1/admin/sso/provedores).
`resolucao.py`    -- resolve/vincula `credenciais` (nunca cria `usuarios` novo)
                      e emite a MESMA sessao que `autenticar`/`renovarSessao` (F1).
"""

from __future__ import annotations
