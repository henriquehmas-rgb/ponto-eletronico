import type { Metadata } from "next";

import { ListaDeEscalas } from "@/componentes/paineis/escalas/lista-escalas";

export const metadata: Metadata = { title: "Padrões de escala" };

export default function PaginaDePadroesDeEscala() {
  return <ListaDeEscalas />;
}
