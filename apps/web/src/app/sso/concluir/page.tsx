import type { Metadata } from "next";

import { PaginaDeConclusaoSaml } from "./pagina-de-conclusao";

export const metadata: Metadata = { title: "Entrando…" };

/**
 * Destino fixo do login federado SAML (T22, F13/A10, RFC-018/ADR-013) — ver
 * a nota completa em `pagina-de-conclusao.tsx`. Sem `useSearchParams()`
 * (os tokens vêm no fragmento, não na query string), então sem necessidade
 * do limite de `<Suspense>` que `/` e `/sso/callback/[provedor]` exigem.
 */
export default function Pagina() {
  return <PaginaDeConclusaoSaml />;
}
