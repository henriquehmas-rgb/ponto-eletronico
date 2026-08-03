import type { Metadata } from "next";

import { ListaDeWebhooks } from "@/componentes/paineis/integracoes";

export const metadata: Metadata = { title: "Integrações" };

export default function PaginaDeIntegracoes() {
  return <ListaDeWebhooks />;
}
