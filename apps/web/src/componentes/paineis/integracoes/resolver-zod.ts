import type { Resolver } from "react-hook-form";
import type { z } from "zod";

/**
 * Resolver mínimo de `zod` para `react-hook-form` — `@hookform/resolvers` não
 * é dependência do projeto (não listado no PCF). Mesmo padrão já usado por
 * `apps/web/src/app/eu/solicitacoes/nova/page.tsx` (F8) e replicado de forma
 * independente por `paineis/escalas/resolver-zod.ts` (F9a/A3); cópia local
 * nova aqui porque `apps/web/src/componentes/paineis/integracoes/**` não é
 * ownership desta seção importar de nenhuma das duas.
 */
export function resolverZod<T extends Record<string, unknown>>(esquema: z.ZodType<T>): Resolver<T> {
  const resolver = async (valores: T) => {
    const resultado = esquema.safeParse(valores);
    if (resultado.success) return { values: resultado.data, errors: {} };
    const erros: Record<string, { type: string; message: string }> = {};
    for (const problema of resultado.error.issues) {
      const campo = problema.path.join(".");
      if (campo && !erros[campo]) erros[campo] = { type: problema.code, message: problema.message };
    }
    return { values: {}, errors: erros };
  };
  return resolver as unknown as Resolver<T>;
}
