import type { Metadata } from "next";

import { PlaceholderDeFase } from "@/componentes/andaime/placeholder-de-fase";

export const metadata: Metadata = { title: "Eu" };

export default function PaginaDoColaborador() {
  return (
    <PlaceholderDeFase
      rota="/eu — Portal do colaborador"
      fase="F8"
      tituloDaFase="Web colaborador e registro por webcam"
      destinatario="Colaborador, no proprio navegador."
      descricao="Espelho de ponto, saldo de banco de horas, solicitacoes e comprovantes. Nesta fase e so a rota: nao ha camera, nao ha registro e nada e enviado a API."
      dependeDe={["F1 — Identidade", "F5 — Marcacao e NSR", "F9a — Design System"]}
      entregas={[
        "Espelho de ponto, extrato de banco de horas e comprovantes assinados.",
        "Solicitacoes de ajuste, abono e ferias, com acompanhamento do fluxo.",
        "Registro por webcam ao vivo via getUserMedia — upload de arquivo e recusado.",
        "Prova de vida com desafio aleatorio e deteccao de camera virtual.",
        "Allowlist CIDR por empresa ou unidade e reautenticacao para bater ponto.",
        "PWA instalavel, com Lighthouse acima de 90 em desempenho e acessibilidade.",
      ]}
    />
  );
}
