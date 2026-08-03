import type { Metadata } from "next";
import { Suspense } from "react";

import { PaginaDeLogin } from "@/componentes/sessao/pagina-de-login";
import { BotoesLoginOidc } from "@/componentes/sso/oidc/botao-login-oidc";
import { BotaoLoginSaml } from "@/componentes/sso/saml/botao-login-saml";

export const metadata: Metadata = { title: "Entrar" };

/**
 * Login real (T1) — substitui o `PlaceholderDeFase` da Fase 0.
 *
 * `<Suspense>` é exigido pelo Next.js: `PaginaDeLogin` (Client Component) usa
 * `useSearchParams()` para ler `?returnTo=`, e isso precisa de um limite de
 * suspensão para não forçar a rota inteira a renderização dinâmica sem aviso.
 *
 * Login federado (T21/T22, F13/A9 e A10, RFC-018/ADR-013): cada agente
 * acrescenta o próprio botão/link, usando os componentes isolados de
 * `@/componentes/sso/oidc/**` e `@/componentes/sso/saml/**` respectivamente,
 * sem alterar o formulário de senha (`PaginaDeLogin`, fora de ownership
 * desta fase) nem o botão do outro (PCF da fase, §5.3).
 */
export default function Pagina() {
  return (
    <Suspense fallback={null}>
      <PaginaDeLogin />
      <div className="mx-auto flex w-full max-w-sm flex-col gap-2 px-6 pb-16">
        <BotoesLoginOidc />
        <BotaoLoginSaml />
      </div>
    </Suspense>
  );
}
