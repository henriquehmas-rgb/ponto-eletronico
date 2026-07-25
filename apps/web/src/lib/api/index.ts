/**
 * Ponto unico de entrada do cliente da API.
 *
 * Importe daqui (`@/lib/api`), nunca de `tipos.gerado` direto: se a geracao
 * mudar de ferramenta, so este arquivo muda.
 */

export { AMBIENTE, URL_API_INTERNA, URL_API_PUBLICA, URL_BASE_API } from "./config";
export {
  api,
  definirProvedorDeToken,
  definirTenant,
  DELETE,
  GET,
  PATCH,
  POST,
  PUT,
  type ProvedorDeToken,
} from "./cliente";
export { ehErroDaApi, ErroDaApi, type Problema } from "./erros";
export type { components, operations, paths } from "./tipos.gerado";

import type { components } from "./tipos.gerado";

/**
 * Atalho para o schema de qualquer entidade do contrato, pelo nome.
 *
 * @example
 * type Colaborador = Esquema<"Colaborador">;
 */
export type Esquema<N extends keyof components["schemas"]> = components["schemas"][N];
