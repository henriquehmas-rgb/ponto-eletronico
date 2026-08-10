import type { Esquema } from "@/lib/api";
import { ehErroDaApi } from "@/lib/api";

/**
 * `exactOptionalPropertyTypes` (tsconfig, strict) trata `{ chave: undefined }`
 * como diferente de "chave ausente" — um filtro opcional que ainda não foi
 * preenchido não pode ser passado direto como `query` do `openapi-fetch` sem
 * essa distinção. Copia local do utilitário equivalente de F8
 * (`lib/formatacao-f8/parametros-de-consulta.ts`, fora do ownership desta
 * fase): remove as chaves `undefined` de verdade em vez de mandá-las com
 * valor `undefined`.
 */
type SemUndefined<T> = { [K in keyof T as undefined extends T[K] ? never : K]: T[K] } & {
  [K in keyof T as undefined extends T[K] ? K : never]?: Exclude<T[K], undefined>;
};

export function paramsSemUndefined<T extends Record<string, unknown>>(objeto: T): SemUndefined<T> {
  const resultado: Record<string, unknown> = {};
  for (const [chave, valor] of Object.entries(objeto)) {
    if (valor !== undefined) resultado[chave] = valor;
  }
  return resultado as unknown as SemUndefined<T>;
}

type TipoDia = NonNullable<Esquema<"ApuracaoDia">["tipoDia"]>;
type StatusApuracao = NonNullable<Esquema<"ApuracaoDia">["status"]>;
type SeveridadeOcorrencia = NonNullable<Esquema<"Ocorrencia">["severidade"]>;
type CodigoOcorrencia = NonNullable<Esquema<"Ocorrencia">["codigo"]>;
type StatusTratamento = NonNullable<Esquema<"Tratamento">["status"]>;
type CategoriaTratamento = NonNullable<Esquema<"TipoTratamento">["categoria"]>;

export const ROTULO_TIPO_DIA: Record<TipoDia, string> = {
  util: "Dia útil",
  dsr: "DSR",
  folga: "Folga",
  feriado: "Feriado",
  ponto_facultativo: "Ponto facultativo",
  afastamento: "Afastamento",
  compensado: "Compensado",
  nao_apurado: "Não apurado",
};

/** Marcador de forma (nunca só cor, WCAG 1.4.1) — um caractere por tipo de dia. */
export const MARCADOR_TIPO_DIA: Record<TipoDia, string> = {
  util: "●",
  dsr: "◐",
  folga: "○",
  feriado: "★",
  ponto_facultativo: "☆",
  afastamento: "▲",
  compensado: "◆",
  nao_apurado: "?",
};

export type VarianteDeSelo = "neutro" | "primario" | "sucesso" | "atencao" | "erro" | "info";

export const ROTULO_STATUS_APURACAO: Record<StatusApuracao, string> = {
  pendente: "Pendente",
  apurado: "Apurado",
  com_ocorrencia: "Com ocorrência",
  fechado: "Fechado",
  reaberto: "Reaberto",
};

export const VARIANTE_STATUS_APURACAO: Record<StatusApuracao, VarianteDeSelo> = {
  pendente: "neutro",
  apurado: "sucesso",
  com_ocorrencia: "atencao",
  fechado: "info",
  reaberto: "atencao",
};

/**
 * Par fundo+borda+texto do MESMO grupo semântico (mesma regra do `Selo`
 * congelado da F9a) para colorir a célula da grade — nunca só a cor de fundo
 * isolada.
 */
export const CLASSE_STATUS_APURACAO: Record<StatusApuracao, string> = {
  pendente: "border-borda-sutil bg-fundo-sutil text-texto-secundario",
  apurado: "border-estado-sucesso-borda bg-estado-sucesso-fundo text-estado-sucesso-texto",
  com_ocorrencia: "border-estado-atencao-borda bg-estado-atencao-fundo text-estado-atencao-texto",
  fechado: "border-estado-info-borda bg-estado-info-fundo text-estado-info-texto",
  reaberto: "border-estado-atencao-borda bg-estado-atencao-fundo text-estado-atencao-texto",
};

/**
 * Cor sólida do marcador de legenda (bolinha) por status — usada só na
 * legenda acima da grade, nunca na célula em si (que usa o par
 * fundo+borda+texto de `CLASSE_STATUS_APURACAO`, mais suave). É um canal
 * AUXILIAR: o rótulo textual ao lado da bolinha continua sendo o canal
 * primário (WCAG 1.4.1) — não há legenda só de cor.
 */
export const COR_PONTO_STATUS_APURACAO: Record<StatusApuracao, string> = {
  pendente: "bg-texto-terciario",
  apurado: "bg-estado-sucesso-solido-fundo",
  com_ocorrencia: "bg-estado-atencao-solido-fundo",
  fechado: "bg-estado-info-solido-fundo",
  reaberto: "bg-estado-atencao-solido-fundo",
};

export const ROTULO_SEVERIDADE_OCORRENCIA: Record<SeveridadeOcorrencia, string> = {
  info: "Informativa",
  atencao: "Atenção",
  alta: "Alta",
  critica: "Crítica",
};

export const VARIANTE_SEVERIDADE_OCORRENCIA: Record<SeveridadeOcorrencia, VarianteDeSelo> = {
  info: "info",
  atencao: "atencao",
  alta: "erro",
  critica: "erro",
};

export const ROTULO_CODIGO_OCORRENCIA: Record<CodigoOcorrencia, string> = {
  marcacao_impar: "Marcação ímpar",
  sem_marcacao: "Sem marcação",
  falta: "Falta",
  atraso: "Atraso",
  saida_antecipada: "Saída antecipada",
  extra_excedida: "Extra excedida",
  jornada_excedida: "Jornada excedida",
  intrajornada_suprimida: "Intrajornada suprimida",
  interjornada_violada: "Interjornada violada",
  dsr_violado: "DSR violado",
  pausa_nr17: "Pausa NR-17",
  fora_geocerca: "Fora da geocerca",
  score_baixo: "Score baixo",
  marcacao_duplicada: "Marcação duplicada",
  offline_tardio: "Offline tardio",
  banco_teto: "Teto do banco de horas",
  banco_vencendo: "Banco de horas vencendo",
  terminal_offline: "Terminal offline",
};

export const ROTULO_STATUS_TRATAMENTO: Record<StatusTratamento, string> = {
  rascunho: "Rascunho",
  pendente: "Pendente de aprovação",
  aprovado: "Aprovado",
  reprovado: "Reprovado",
  cancelado: "Cancelado",
  aplicado: "Aplicado",
};

export const VARIANTE_STATUS_TRATAMENTO: Record<StatusTratamento, VarianteDeSelo> = {
  rascunho: "neutro",
  pendente: "atencao",
  aprovado: "sucesso",
  reprovado: "erro",
  cancelado: "neutro",
  aplicado: "sucesso",
};

export const ROTULO_CATEGORIA_TRATAMENTO: Record<CategoriaTratamento, string> = {
  inclusao_marcacao: "Inclusão manual de horário",
  desconsideracao_marcacao: "Desconsideração de marcação",
  ajuste_intervalo: "Ajuste de intervalo",
  abono: "Abono",
  justificativa: "Justificativa",
  afastamento: "Afastamento",
  compensacao: "Compensação",
  ajuste_saldo: "Ajuste de saldo",
};

/**
 * Mensagens de erro amigáveis por `codigo` estável (nunca por `title`/`detail`
 * da resposta — `packages/contracts/openapi.yaml`, seção "Convenções", e
 * `apps/web/src/lib/api/erros.ts`). Cobre os códigos que aparecem em `x-erros`
 * das operações desta fase (`tratamentos`, `apuracoes`, `ocorrencias`,
 * `banco-horas`). Fora daqui, cai no genérico com o código exposto.
 */
const MENSAGEM_POR_CODIGO: Record<string, string> = {
  "PONTO-AUTH-002": "Sessão ausente. Entre novamente.",
  "PONTO-AUTH-003": "Sessão expirada. Entre novamente.",
  "PONTO-AUTH-004": "Sessão inválida. Entre novamente.",
  "PONTO-AUTH-006": "Sessão encerrada ou revogada. Entre novamente.",
  "PONTO-AUTH-013": "Credencial de integração inválida ou revogada.",
  "PONTO-PERM-001": "Você não tem permissão para esta ação.",
  "PONTO-PERM-002": "Este registro está fora do seu alcance hierárquico.",
  "PONTO-PERM-004": "Seu perfil tem acesso somente leitura a este recurso.",
  "PONTO-PERM-005": "Delegação inválida ou expirada.",
  "PONTO-TEN-002": "Sessão de outro tenant. Entre novamente.",
  "PONTO-TEN-003": "Tenant suspenso ou cancelado.",
  "PONTO-TEN-004": "Acesso entre tenants negado.",
  "PONTO-VAL-001": "Dados inválidos no formulário. Revise os campos.",
  "PONTO-VAL-005": "Parâmetro de busca inválido.",
  "PONTO-VAL-006": "A ordenação mudou durante a navegação. Volte ao início da lista.",
  "PONTO-VAL-007": "Intervalo de datas inválido.",
  "PONTO-VAL-011": "Requisição incompleta. Tente novamente.",
  "PONTO-REC-001": "Registro não encontrado — pode ter sido removido nesse meio-tempo.",
  "PONTO-RATE-001": "Muitas requisições em sequência. Aguarde um instante e tente novamente.",
  "PONTO-IDEM-001": "Falha ao identificar a requisição. Tente novamente.",
  "PONTO-IDEM-002": "Essa ação já foi enviada com dados diferentes. Recarregue e tente de novo.",
  "PONTO-IDEM-003": "Uma requisição igual a esta ainda está em processamento.",
  "PONTO-INT-001": "Erro interno. Tente novamente em instantes.",
  "PONTO-INT-003": "Serviço temporariamente indisponível. Tente novamente.",
  "PONTO-INT-005": "Esta operação ainda não está disponível.",
  "PONTO-CONF-003": "Esta transição não é permitida no estado atual do registro.",
  "PONTO-PER-001":
    "O período desta data já está fechado. Peça a reabertura ao RH antes de tratar ou recalcular.",
  "PONTO-APUR-001": "Já existe um recálculo em andamento para este escopo e período.",
  "PONTO-APUR-002":
    "Não há jornada nem escala resolvida para o vínculo nesta data — atribua uma jornada antes de apurar.",
  "PONTO-APUR-003": "Este dia está travado por um fechamento e não pode ser recalculado.",
  "PONTO-BH-001":
    "O lançamento levaria o saldo credor acima do teto da política de banco de horas.",
  "PONTO-BH-002":
    "O lançamento levaria o saldo devedor além do teto da política de banco de horas.",
  "PONTO-MARC-009": "O colaborador não tem vínculo ativo nesta data.",
};

/** Deriva a mensagem exibível de um erro capturado de uma chamada à API. */
export function mensagemDeErroApi(erro: unknown): string {
  if (!ehErroDaApi(erro)) return "Não foi possível concluir a operação. Tente novamente.";
  const mensagem = erro.codigo ? MENSAGEM_POR_CODIGO[erro.codigo] : undefined;
  if (mensagem) return mensagem;
  return `Não foi possível concluir a operação (código ${erro.codigo ?? erro.status}).`;
}

/** `AAAA-MM-DD` a partir dos componentes — evita o fuso do `Date`/`toISOString`. */
function paraIsoData(ano: number, mes: number, dia: number): string {
  return `${String(ano).padStart(4, "0")}-${String(mes).padStart(2, "0")}-${String(dia).padStart(2, "0")}`;
}

/**
 * Lista de dias `AAAA-MM-DD` de `de` até `ate`, inclusive. Usa apenas
 * componentes locais de `Date` (nunca `toISOString`, que converte para UTC e
 * pode deslocar o dia) — mesmo cuidado que `seletor-de-periodo.tsx` (F9a) já
 * toma para o mesmo problema.
 */
export function obterDiasDoIntervalo(de: string, ate: string): string[] {
  const [anoIni = 1970, mesIni = 1, diaIni = 1] = de.split("-").map(Number);
  const [anoFim = 1970, mesFim = 1, diaFim = 1] = ate.split("-").map(Number);
  const dias: string[] = [];
  const cursor = new Date(anoIni, mesIni - 1, diaIni);
  const limite = new Date(anoFim, mesFim - 1, diaFim);
  while (cursor <= limite) {
    dias.push(paraIsoData(cursor.getFullYear(), cursor.getMonth() + 1, cursor.getDate()));
    cursor.setDate(cursor.getDate() + 1);
  }
  return dias;
}

/** Uma linha da grade de apuração: um vínculo, com um `ApuracaoDia` por dia (quando existir). */
export interface LinhaDeApuracaoGrade {
  vinculoId: string;
  colaboradorId: string;
  porDia: Map<string, Esquema<"ApuracaoDia">>;
}

function paraIsoDataDoMes(ano: number, mes: number, dia: number): string {
  return `${String(ano).padStart(4, "0")}-${String(mes).padStart(2, "0")}-${String(dia).padStart(2, "0")}`;
}

/** Data de hoje em ISO (`AAAA-MM-DD`), usando componentes LOCAIS de `Date` (nunca `toISOString`). */
export function hojeIso(agora: Date = new Date()): string {
  return paraIsoDataDoMes(agora.getFullYear(), agora.getMonth() + 1, agora.getDate());
}

/** Primeiro e último dia do mês de `agora`, em ISO — período padrão da grade de apuração (T9). */
export function mesAtualComoPeriodo(agora: Date = new Date()): { inicio: string; fim: string } {
  const ano = agora.getFullYear();
  const mes = agora.getMonth() + 1;
  const ultimoDia = new Date(ano, mes, 0).getDate();
  return { inicio: paraIsoDataDoMes(ano, mes, 1), fim: paraIsoDataDoMes(ano, mes, ultimoDia) };
}

/** Primeiro e último dia do mês ANTERIOR ao de `agora`, em ISO — atalho da grade de apuração (T9). */
export function mesAnteriorComoPeriodo(agora: Date = new Date()): { inicio: string; fim: string } {
  const anterior = new Date(agora.getFullYear(), agora.getMonth() - 1, 1);
  return mesAtualComoPeriodo(anterior);
}

/** Achata `listarApuracoes` (uma linha por vínculo × dia) em uma linha por vínculo, para a `TabelaDeDados` (T9). */
export function agruparApuracoesPorVinculo(
  apuracoes: readonly Esquema<"ApuracaoDia">[],
): LinhaDeApuracaoGrade[] {
  const porVinculo = new Map<string, LinhaDeApuracaoGrade>();
  for (const apuracao of apuracoes) {
    const vinculoId = apuracao.vinculoId;
    if (!vinculoId) continue;
    let linha = porVinculo.get(vinculoId);
    if (!linha) {
      linha = { vinculoId, colaboradorId: apuracao.colaboradorId ?? "", porDia: new Map() };
      porVinculo.set(vinculoId, linha);
    }
    if (apuracao.data) linha.porDia.set(apuracao.data, apuracao);
  }
  return Array.from(porVinculo.values());
}
