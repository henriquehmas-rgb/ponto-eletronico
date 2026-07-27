import type { Metadata } from "next";

import { FluxoDeRegistro } from "@/componentes/registro-webcam/fluxo-de-registro";

/**
 * `/eu/registrar` — Registro de ponto por webcam (T9 do PCF F08, A2).
 *
 * A guarda de rota (redirecionar sem sessão) e a casca de navegação do
 * colaborador são de `src/app/eu/layout.tsx` (A1, T1) — esta página só
 * monta o fluxo de registro em si.
 */
export const metadata: Metadata = { title: "Registrar ponto" };

export default function PaginaDeRegistrarPonto() {
  return (
    <div className="mx-auto flex w-full max-w-xl flex-col gap-[var(--espacamento-3)] px-[var(--espacamento-2)] py-[var(--espacamento-4)]">
      <h1 className="estilo-titulo-pagina">Registrar ponto</h1>
      <FluxoDeRegistro />
    </div>
  );
}
