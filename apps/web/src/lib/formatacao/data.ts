/**
 * Formatação de data e hora em pt-BR, sempre no fuso da unidade (nunca o
 * fuso do navegador de quem está olhando a tela — um gestor em outro estado
 * precisa ver o horário local da unidade, não o seu).
 */

const FUSO_PADRAO = "America/Sao_Paulo";

function paraData(valor: Date | string): Date {
  return typeof valor === "string" ? new Date(valor) : valor;
}

/** `2026-07-25` (ou instante ISO completo) → `"25/07/2026"`. */
export function formatarData(valor: Date | string, fusoHorario: string = FUSO_PADRAO): string {
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: fusoHorario,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(paraData(valor));
}

/** Instante ISO → `"14:05"`, sempre 24h, no fuso informado. */
export function formatarHora(valor: Date | string, fusoHorario: string = FUSO_PADRAO): string {
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: fusoHorario,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(paraData(valor));
}

/** Instante ISO → `"25/07/2026 14:05"`. */
export function formatarDataHora(valor: Date | string, fusoHorario: string = FUSO_PADRAO): string {
  const data = paraData(valor);
  return `${formatarData(data, fusoHorario)} ${formatarHora(data, fusoHorario)}`;
}

/** Nome do dia da semana abreviado em pt-BR: `"seg"`, `"ter"`, ... */
export function formatarDiaDaSemanaAbreviado(
  valor: Date | string,
  fusoHorario: string = FUSO_PADRAO,
): string {
  const texto = new Intl.DateTimeFormat("pt-BR", { timeZone: fusoHorario, weekday: "short" }).format(
    paraData(valor),
  );
  // Intl devolve "seg." com ponto; a grade de escala quer o rotulo curto sem pontuacao.
  return texto.replace(/\.$/, "");
}
