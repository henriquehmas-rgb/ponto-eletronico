import type { components } from "./tipos.gerado";

/**
 * Envelope de erro do contrato: RFC 9457 em `application/problem+json`.
 * O tipo vem do OpenAPI — nao ha redeclaracao a mao.
 */
export type Problema = components["schemas"]["Problema"];

/**
 * Erro lancado quando a API responde fora da faixa 2xx.
 *
 * REGRA DO CONTRATO (openapi.yaml, secao "Convencoes"): a mensagem mostrada ao
 * usuario deriva de `codigo`, que e estavel e vive em `errors.yaml`. NUNCA
 * derive de `title` ou `detail` — esses textos podem mudar sem quebrar contrato.
 */
export class ErroDaApi extends Error {
  readonly status: number;
  readonly codigo: string | undefined;
  readonly problema: Problema | undefined;
  readonly requestId: string | undefined;

  constructor(status: number, problema?: Problema) {
    const codigo = problema?.codigo;
    super(codigo ?? `HTTP ${status}`);
    this.name = "ErroDaApi";
    this.status = status;
    this.codigo = codigo;
    this.problema = problema;
    this.requestId = problema?.requestId;
  }
}

/** Estreitamento de tipo para uso em `catch`. */
export function ehErroDaApi(valor: unknown): valor is ErroDaApi {
  return valor instanceof ErroDaApi;
}
