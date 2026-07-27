/**
 * Utilitário compartilhado dos ganchos de consulta desta fase (T2..T5).
 *
 * `exactOptionalPropertyTypes` (tsconfig, strict) trata `{ chave: undefined }`
 * como diferente de "chave ausente" — um filtro opcional que ainda não foi
 * preenchido (`de?: string` vindo de uma prop) não pode ser passado direto
 * como `query` do `openapi-fetch` sem essa distinção. Esta função remove as
 * chaves `undefined` de verdade (em vez de mandá-las com valor `undefined`),
 * o que satisfaz tanto o contrato de tipos quanto o serializador de query.
 */
export function paramsSemUndefined<T extends Record<string, unknown>>(
  objeto: T,
): { [K in keyof T]?: Exclude<T[K], undefined> } {
  const resultado: Record<string, unknown> = {};
  for (const [chave, valor] of Object.entries(objeto)) {
    if (valor !== undefined) resultado[chave] = valor;
  }
  return resultado as { [K in keyof T]?: Exclude<T[K], undefined> };
}
