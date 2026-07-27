import type { Metadata } from "next";
import { Suspense } from "react";

import { PaginaDeLogin } from "@/componentes/sessao/pagina-de-login";

export const metadata: Metadata = { title: "Entrar" };

/**
 * Login real (T1) — substitui o `PlaceholderDeFase` da Fase 0.
 *
 * `<Suspense>` é exigido pelo Next.js: `PaginaDeLogin` (Client Component) usa
 * `useSearchParams()` para ler `?returnTo=`, e isso precisa de um limite de
 * suspensão para não forçar a rota inteira a renderização dinâmica sem aviso.
 */
export default function Pagina() {
  return (
    <Suspense fallback={null}>
      <PaginaDeLogin />
    </Suspense>
  );
}
