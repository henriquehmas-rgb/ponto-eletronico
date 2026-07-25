/**
 * Origem da API, resolvida por ambiente.
 *
 * Os nomes das variaveis nao sao escolha desta aplicacao: sao exatamente os que
 * `infra/docker-compose.yml` (servico `web`) e `infra/.env.example` definem.
 *
 * | Variavel              | Quem le    | Para que |
 * |-----------------------|------------|----------|
 * | `NEXT_PUBLIC_API_URL` | navegador  | chamada do cliente; entra no bundle |
 * | `API_INTERNAL_URL`    | servidor   | Server Component / Route Handler falando com a API pela rede interna do compose (`http://api:8000`), sem sair para a internet |
 *
 * `process.env.NEXT_PUBLIC_*` precisa ser escrito com acesso literal por ponto:
 * e assim que o Next substitui o valor em tempo de build.
 */

const NO_SERVIDOR = typeof window === "undefined";

/** URL publica da API, visivel ao navegador. */
export const URL_API_PUBLICA = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** URL usada em chamadas servidor -> servidor; cai na publica quando ausente. */
export const URL_API_INTERNA = process.env.API_INTERNAL_URL ?? URL_API_PUBLICA;

/** A origem correta para o lado em que este modulo esta rodando. */
export const URL_BASE_API = NO_SERVIDOR ? URL_API_INTERNA : URL_API_PUBLICA;

/** Ambiente declarado pelo compose (`dev`, `hml`, `prd`). */
export const AMBIENTE = process.env.NEXT_PUBLIC_AMBIENTE ?? "dev";

/**
 * NAO existe constante de prefixo `/v1` aqui de proposito: os 140 caminhos do
 * `openapi.yaml` ja comecam com `/v1`, e os tipos gerados preservam isso.
 * Concatenar o prefixo na `baseUrl` produziria `/v1/v1/...`.
 */
