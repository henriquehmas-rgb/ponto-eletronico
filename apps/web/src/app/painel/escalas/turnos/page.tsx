import type { Metadata } from "next";

import { ListaDeTurnos } from "@/componentes/paineis/escalas/lista-turnos";

export const metadata: Metadata = { title: "Turnos — Escalas" };

export default function PaginaDeTurnos() {
  return <ListaDeTurnos />;
}
