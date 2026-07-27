/**
 * Ponto único de entrada do módulo de sessão.
 *
 * Importe daqui (`@/lib/sessao`) — inclusive a F9b, que reusa `ProvedorDeSessao`/
 * `useSessao` sem recriar login próprio (contrato fixado, §2 do PCF F8).
 */

export { ProvedorDeSessao, useSessao, type ContextoDeSessao } from "./contexto-de-sessao";
export { validarRetornoSeguro } from "./retorno-seguro";
export type {
  CredenciaisDeEntrada,
  RespostaDeAutenticacao,
  RespostaDeLogin,
  RespostaDeMfaRequerido,
  TenantResumido,
  UsuarioAutenticado,
} from "./tipos";
