import type { Metadata } from "next";

import { PlaceholderDeFase } from "@/componentes/andaime/placeholder-de-fase";

export const metadata: Metadata = { title: "Entrar" };

export default function PaginaDeLogin() {
  return (
    <PlaceholderDeFase
      rota="/ — Entrar"
      fase="F1"
      tituloDaFase="Identidade, Multi-tenant e RBAC"
      destinatario="Todo mundo: colaborador, gestor, RH e administrador."
      descricao="Porta de entrada do sistema. Nesta fase existe so a rota: nao ha formulario, nao ha sessao e nenhuma chamada de autenticacao sai daqui."
      dependeDe={["F0 — Fundacao e Contratos"]}
      entregas={[
        "Login com senha (Argon2id) e JWT RS256 de vida curta.",
        "Refresh rotativo de uso unico, com deteccao de reuso que revoga a familia inteira.",
        "MFA opcional por TOTP e recuperacao de senha.",
        "Resolucao de tenant por subdominio ou cabecalho X-Tenant.",
        "Sessoes listaveis e revogaveis pelo proprio usuario.",
      ]}
    />
  );
}
