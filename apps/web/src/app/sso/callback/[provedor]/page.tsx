import type { Metadata } from "next";
import { Suspense } from "react";

import { PaginaDeConclusaoOidc } from "./pagina-de-conclusao";

export const metadata: Metadata = { title: "Entrando…" };

interface PaginaProps {
  params: Promise<{ provedor: string }>;
}

/**
 * `redirect_uri` do login federado OIDC (T21, F13/A9, RFC-018/ADR-013) —
 * ver a nota completa em `pagina-de-conclusao.tsx`.
 */
export default async function Pagina({ params }: PaginaProps) {
  const { provedor } = await params;
  return (
    <Suspense fallback={null}>
      <PaginaDeConclusaoOidc provedor={provedor} />
    </Suspense>
  );
}
