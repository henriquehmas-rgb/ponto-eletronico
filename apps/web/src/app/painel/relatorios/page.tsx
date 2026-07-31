import type { Metadata } from "next";

import { CatalogoDeRelatorios } from "@/componentes/paineis/relatorios";

export const metadata: Metadata = { title: "Relatórios" };

export default function PaginaDeCatalogoDeRelatorios() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="estilo-titulo-pagina text-texto-primario">Relatórios</h1>
      <CatalogoDeRelatorios />
    </div>
  );
}
