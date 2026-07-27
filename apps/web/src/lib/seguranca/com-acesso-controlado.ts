import { ehErroDaApi } from "@/lib/api";

/**
 * `comAcessoControlado` — T13 do PCF F08.
 *
 * Função de ordem superior que envolve qualquer chamada de escrita sensível
 * (nesta fase, `POST /v1/marcacoes`, T9 de A2) e, quando o servidor recusa
 * com `PONTO-AUTH-011` ("reautenticação necessária" — o backend já impõe
 * isso para `canal='web'`, ver §2 do PCF), dispara o fluxo de reautenticação
 * (T12) e reexecuta a MESMA chamada uma única vez após ela ser aceita.
 *
 * Não é um laço: a reexecução não está dentro do `catch`, então se a segunda
 * tentativa também falhar com `PONTO-AUTH-011` (ou qualquer outro erro), ela
 * simplesmente propaga — nunca há uma terceira tentativa automática.
 *
 * A ligação com a UI (o modal de reautenticação, T12) é feita pelo mesmo
 * padrão já usado por `src/lib/api/cliente.ts`
 * (`definirProvedorDeToken`/`definirTenant`): um gancho de módulo, mutável,
 * registrado por quem monta o componente (`useReautenticacao`, via
 * `useEffect`), nunca importado ao contrário (este módulo não conhece React).
 */

const CODIGO_REAUTENTICACAO_NECESSARIA = "PONTO-AUTH-011";

/** Abre o fluxo de reautenticação e resolve quando ela é aceita; rejeita
 *  quando o colaborador cancela. */
export type SolicitadorDeReautenticacao = () => Promise<void>;

let solicitadorDeReautenticacao: SolicitadorDeReautenticacao | undefined;

/**
 * Registra de onde `comAcessoControlado` pede reautenticação. Chamado por
 * `useReautenticacao` (T12) ao montar o `ModalDeReautenticacao`; chamado de
 * novo com `undefined` ao desmontar, para não reter uma promessa de um
 * componente que já saiu de tela.
 */
export function definirSolicitadorDeReautenticacao(
  solicitador: SolicitadorDeReautenticacao | undefined,
): void {
  solicitadorDeReautenticacao = solicitador;
}

/**
 * Executa `chamada`. Se ela falhar com `PONTO-AUTH-011` e houver um modal de
 * reautenticação montado, pede a reautenticação e, aceita, repete `chamada`
 * exatamente uma vez. Qualquer outro erro — ou a ausência de um solicitador
 * registrado — é relançado como está, para quem chamou decidir a UI usando
 * `dicionario-de-erros.ts`.
 */
export async function comAcessoControlado<T>(chamada: () => Promise<T>): Promise<T> {
  try {
    return await chamada();
  } catch (erro) {
    const exigeReautenticacao =
      ehErroDaApi(erro) && erro.codigo === CODIGO_REAUTENTICACAO_NECESSARIA;
    if (!exigeReautenticacao || !solicitadorDeReautenticacao) {
      throw erro;
    }
    await solicitadorDeReautenticacao();
    // Reexecução única, fora do `catch`: uma segunda falha propaga direto.
    return await chamada();
  }
}
