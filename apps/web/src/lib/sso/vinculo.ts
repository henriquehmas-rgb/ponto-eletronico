/**
 * Chaves de `sessionStorage` compartilhadas entre o início do login federado
 * OIDC (`componentes/sso/oidc/botao-login-oidc.tsx`) e a página que recebe
 * a volta do IdP (`app/sso/callback/[provedor]/pagina-de-conclusao.tsx`) —
 * RFC-019 (vínculo de navegador anti-login-CSRF) e o `returnTo` que o
 * acompanha. `sessionStorage`, não cookie: sobrevive à navegação de página
 * inteira até o IdP e de volta (mesma origem, mesma aba), sem depender de
 * `api_base_url`/`web_base_url` compartilharem domínio.
 *
 * Nomes isolados (`ponto_sso_*`) para nunca colidir com nenhuma outra chave
 * de `sessionStorage`/`localStorage` que o produto já use.
 */
export const CHAVE_SESSION_STORAGE_VINCULO = "ponto_sso_vinculo";
export const CHAVE_SESSION_STORAGE_RETURN_TO = "ponto_sso_return_to";
