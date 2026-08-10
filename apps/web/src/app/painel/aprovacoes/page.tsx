import type { Metadata } from "next";

import { ListaDeAprovacoes } from "@/componentes/paineis/aprovacoes/lista-de-aprovacoes";
import { CabecalhoDeAprovacoes } from "@/componentes/paineis/aprovacoes/cabecalho-de-aprovacoes";
import { Alerta, AlertaDescricao, AlertaTitulo } from "@/componentes/ui/alert";
import { PortaoDePermissao } from "@/lib/permissoes";

export const metadata: Metadata = { title: "Aprovações" };

/**
 * Tela cheia de aprovações (`/painel/aprovacoes`) — antes só existia como
 * widget resumido dentro do dashboard (`componentes/paineis/dashboard/fila-de-aprovacoes.tsx`).
 * Gate por `aprovacoes.ler` (contrato, `listarAprovacoesPendentes` §x-permissao),
 * mesmo padrão de `/painel/antifraude`.
 */
export default function PaginaDeAprovacoes() {
  return (
    <div className="flex flex-col gap-6">
      <PortaoDePermissao
        permissao="aprovacoes.ler"
        fallback={
          <Alerta variant="atencao">
            <AlertaTitulo>Permissão necessária</AlertaTitulo>
            <AlertaDescricao>
              Esta tela exige a permissão &quot;aprovacoes.ler&quot; — fale com o administrador
              do seu tenant.
            </AlertaDescricao>
          </Alerta>
        }
      >
        <CabecalhoDeAprovacoes />
        <div className="mt-6">
          <ListaDeAprovacoes />
        </div>
      </PortaoDePermissao>
    </div>
  );
}
