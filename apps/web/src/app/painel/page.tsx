import type { Metadata } from "next";

import { PlaceholderDeFase } from "@/componentes/andaime/placeholder-de-fase";

export const metadata: Metadata = { title: "Painel" };

export default function PaginaDoPainel() {
  return (
    <PlaceholderDeFase
      rota="/painel — RH e gestor"
      fase="F9b"
      tituloDaFase="Painel RH e Gestor"
      destinatario="RH, gestores de equipe e diretoria."
      descricao="Area de gestao: dashboards, cadastros, grade de apuracao e escalas. Nesta fase e so a rota — nenhum dado real e lido, porque as 215 operacoes da API ainda respondem 501."
      dependeDe={[
        "F2 — Cadastros organizacionais",
        "F3 — Jornadas e escalas",
        "F4 — Apuracao",
        "F9a — Design System",
      ]}
      entregas={[
        "Dashboards de RH, gestor e diretoria, com quem esta trabalhando em tempo real.",
        "Telas de cadastro: empresas, unidades com geocerca em mapa, departamentos, cargos, colaboradores, contratos, dispositivos.",
        "Grade de apuracao mes x colaborador, com acoes em lote e recalculo sob demanda.",
        "Montagem de escala, copia de periodo e previsto x realizado.",
      ]}
      extra={
        <p className="estilo-corpo mt-8 rounded-medio border border-estado-atencao-borda bg-estado-atencao-fundo p-4 text-estado-atencao-texto">
          Vedacao legal do REP-P: nenhuma tela desta area edita marcacao. Correcao de jornada e
          sempre um tratamento (<code className="estilo-identificador">POST /v1/tratamentos</code>),
          numa camada separada e auditada. A regra e imposta em tres lugares — ausencia de rota no
          contrato, gatilho no banco e revogacao de privilegio da role da aplicacao.
        </p>
      }
    />
  );
}
