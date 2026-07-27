import type { ReactNode } from "react";

import { CascaDoPainel } from "@/componentes/paineis/shell";
import { ProvedorDeSessao } from "@/lib/sessao";

/**
 * Layout raiz da área de gestão (T1, PCF F9b).
 *
 * Monta `<ProvedorDeSessao>` — o MESMO módulo de sessão que
 * `apps/web/src/app/eu/layout.tsx` (F8) monta, importado de `@/lib/sessao`
 * sem nenhuma cópia nem segundo mecanismo (PCF F9b §2/§4, "Não toca";
 * proibição 3 e 11 da §9). Esta fase não constrói login, não guarda token e
 * não sabe nada sobre `accessToken`/`refreshToken` — isso é inteiramente
 * `apps/web/src/lib/sessao/**`.
 *
 * A guarda de rota (sem sessão válida redireciona para
 * `/?returnTo=<rota-atual>`, nunca renderiza uma tela de gestão sem sessão)
 * vive em `CascaDoPainel`, que também é a navegação da área.
 */
export default function LayoutDoPainel({ children }: { children: ReactNode }) {
  return (
    <ProvedorDeSessao>
      <CascaDoPainel>{children}</CascaDoPainel>
    </ProvedorDeSessao>
  );
}
