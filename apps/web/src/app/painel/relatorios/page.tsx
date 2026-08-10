import type { Metadata } from "next";

import { Alerta, AlertaDescricao, AlertaTitulo } from "@/componentes/ui/alert";
import { CatalogoDeRelatorios } from "@/componentes/paineis/relatorios";
import { PortaoDePermissao } from "@/lib/permissoes";

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
      <PortaoDePermissao
        permissao="relatorios.ler"
        fallback={
          <Alerta variant="atencao">
            <AlertaTitulo>Permissão necessária</AlertaTitulo>
            <AlertaDescricao>
              Esta tela exige a permissão &quot;relatorios.ler&quot; — fale com o administrador
              do seu tenant.
            </AlertaDescricao>
          </Alerta>
        }
      >
        <CatalogoDeRelatorios />
      </PortaoDePermissao>
    </div>
  );
}
