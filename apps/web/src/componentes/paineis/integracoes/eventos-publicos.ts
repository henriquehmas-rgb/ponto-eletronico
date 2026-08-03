/**
 * Catálogo de eventos públicos assináveis por webhook (T14, F13/A4).
 *
 * Espelha os 19 eventos com `webhook_publico: true` de
 * `packages/contracts/events.yaml` (22 eventos no catálogo total; os outros
 * 3 — `ocorrencia.aberta`, `comprovante.emitido`, `webhook.desabilitado` —
 * são internos e não assináveis, por isso ficam de fora desta lista, mesma
 * regra que `PONTO-WEBH-003` aplica no servidor). Não existe endpoint HTTP
 * que devolva este catálogo (abrir um está fora do escopo desta fase — o
 * portal de documentação de A2 é quem renderiza `events.yaml` por inteiro);
 * lista fixa aqui, com o mesmo precedente de cópia local documentada já
 * usado por outras seções do painel (ex. `paineis/escalas/campos.tsx`, F9a).
 * Se o catálogo publicado mudar, este arquivo precisa ser atualizado à mão.
 */
export interface EventoPublico {
  codigo: string;
  rotulo: string;
  grupo: string;
}

export const EVENTOS_PUBLICOS: EventoPublico[] = [
  { codigo: "marcacao.criada", rotulo: "Marcação criada", grupo: "Marcações" },
  { codigo: "marcacao.suspeita", rotulo: "Marcação suspeita", grupo: "Marcações" },
  {
    codigo: "marcacao.sincronizada_offline",
    rotulo: "Marcação sincronizada (offline)",
    grupo: "Marcações",
  },
  { codigo: "ajuste.solicitado", rotulo: "Ajuste solicitado", grupo: "Workflow" },
  { codigo: "ajuste.aprovado", rotulo: "Ajuste aprovado", grupo: "Workflow" },
  { codigo: "ajuste.reprovado", rotulo: "Ajuste reprovado", grupo: "Workflow" },
  { codigo: "apuracao.recalculada", rotulo: "Apuração recalculada", grupo: "Apuração" },
  { codigo: "periodo.fechado", rotulo: "Período fechado", grupo: "Workflow" },
  { codigo: "periodo.reaberto", rotulo: "Período reaberto", grupo: "Workflow" },
  { codigo: "banco_horas.vencendo", rotulo: "Banco de horas vencendo", grupo: "Banco de horas" },
  { codigo: "banco_horas.quitado", rotulo: "Banco de horas quitado", grupo: "Banco de horas" },
  { codigo: "colaborador.admitido", rotulo: "Colaborador admitido", grupo: "Pessoas" },
  { codigo: "colaborador.demitido", rotulo: "Colaborador demitido", grupo: "Pessoas" },
  { codigo: "terminal.offline", rotulo: "Terminal ficou offline", grupo: "Terminais" },
  { codigo: "terminal.online", rotulo: "Terminal voltou online", grupo: "Terminais" },
  { codigo: "afd.gerado", rotulo: "AFD gerado", grupo: "Conformidade" },
  { codigo: "aej.gerado", rotulo: "AEJ gerado", grupo: "Conformidade" },
  { codigo: "espelho.assinado", rotulo: "Espelho de ponto assinado", grupo: "Conformidade" },
  { codigo: "importacao.concluida", rotulo: "Importação concluída", grupo: "Integrações" },
];
