import type { Esquema } from "@/lib/api";

/**
 * RBAC no cliente (T1, PCF F9b §2/§6/§9): toda tela e toda ação desta fase se
 * habilita checando `sessao.permissoes.includes("<x-permissao exata>")`,
 * NUNCA por nome de papel (`"rh"`/`"gestor"`/`"diretoria"` não existem como
 * enum no contrato — são só rótulos de produto). Este módulo é o único lugar
 * que faz essa checagem; quem consome nunca reimplementa o `.includes(...)`.
 *
 * Aceita `undefined`/`null` de propósito: enquanto `useSessaoCompleta()`
 * ainda está carregando (ou falhou), `sessao` é `undefined` — o padrão seguro
 * é "sem permissão comprovada ainda" (nega), nunca "assume que tem".
 */
export type SessaoComPermissoes = Pick<Esquema<"SessaoAtual">, "permissoes"> | null | undefined;

export function temPermissao(sessao: SessaoComPermissoes, permissao: string): boolean {
  return Boolean(sessao?.permissoes?.includes(permissao));
}

/** Verdadeiro se `sessao` tem QUALQUER uma das permissões informadas (OR). */
export function temAlgumaPermissao(
  sessao: SessaoComPermissoes,
  permissoes: readonly string[],
): boolean {
  return permissoes.some((permissao) => temPermissao(sessao, permissao));
}
