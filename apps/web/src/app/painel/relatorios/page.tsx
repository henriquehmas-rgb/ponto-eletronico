import type { Metadata } from "next";

import { CatalogoDeRelatorios } from "@/componentes/paineis/relatorios";

export const metadata: Metadata = { title: "Relatórios" };

export default function PaginaDeCatalogoDeRelatorios() {
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="estilo-titulo-pagina text-texto-primario">Relatórios</h1>
        <p className="estilo-corpo text-texto-terciario">
          Exportações e documentos exigidos pela Portaria MTP 671/2021
        </p>
      </div>
      <CatalogoDeRelatorios />
    </div>
  );
}
