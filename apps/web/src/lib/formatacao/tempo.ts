/**
 * Formatação de duração de tempo.
 *
 * O contrato (`packages/contracts/glossario.md`, seção 1, convenção 7) guarda
 * duração SEMPRE em minutos inteiros — nunca `float`, nunca `interval`, nunca
 * "hora decimal". Estas funções são a única conversão de apresentação: elas
 * não fazem parte do cálculo de apuração (isso é F4), só transformam um
 * inteiro de minutos em texto para a tela.
 */

const REGEX_HORA_DO_DIA = /^([01]\d|2[0-3]):([0-5]\d)$/;

/**
 * `90` → `"1:30"`. `-90` → `"-1:30"`. `1500` → `"25:00"` (duração cumulativa,
 * não hora do dia — pode passar de 24h sem problema, ex.: extrato do mês).
 * O sinal aparece uma única vez, na frente do número de horas.
 */
export function minutosParaHHMM(minutos: number): string {
  if (!Number.isFinite(minutos)) {
    throw new Error(`minutosParaHHMM: valor nao finito recebido (${String(minutos)}).`);
  }
  const negativo = minutos < 0;
  const totalAbsoluto = Math.round(Math.abs(minutos));
  const horas = Math.floor(totalAbsoluto / 60);
  const minutosRestantes = totalAbsoluto % 60;
  const minutosTexto = String(minutosRestantes).padStart(2, "0");
  return `${negativo ? "-" : ""}${horas}:${minutosTexto}`;
}

/**
 * `90` → `"1,50"` (pt-BR, vírgula decimal). `100` → `"1,67"` (arredondado).
 * `-90` → `"-1,50"`.
 */
export function minutosParaDecimal(minutos: number, casasDecimais = 2): string {
  if (!Number.isFinite(minutos)) {
    throw new Error(`minutosParaDecimal: valor nao finito recebido (${String(minutos)}).`);
  }
  const horasDecimais = minutos / 60;
  // `toFixed` primeiro para arredondar de verdade; Number(...) remove o -0
  // que `toFixed` pode produzir (ex.: (-0.001).toFixed(2) === "-0.00").
  const arredondado = Number(horasDecimais.toFixed(casasDecimais)) || 0;
  return arredondado.toLocaleString("pt-BR", {
    minimumFractionDigits: casasDecimais,
    maximumFractionDigits: casasDecimais,
  });
}

function paraMinutosDoDia(horaDoDia: string): number {
  const combinacao = REGEX_HORA_DO_DIA.exec(horaDoDia);
  if (!combinacao) {
    throw new Error(
      `paraMinutosDoDia: formato invalido "${horaDoDia}", esperado "HH:MM" (00:00 a 23:59).`,
    );
  }
  const [, horas, minutos] = combinacao as unknown as [string, string, string];
  return Number(horas) * 60 + Number(minutos);
}

/**
 * Duração de um turno dado seu horário de início e fim, ambos em "HH:MM".
 * Quando `fim` é menor ou igual a `inicio`, a jornada **cruza a meia-noite**
 * (ex.: 12x36 noturno das 19:00 às 07:00 → 720 minutos) — a célula da grade
 * de escala pertence ao dia de início, este cálculo só resolve a duração.
 * `inicio === fim` é convencionado como turno de 24h corridas (ex.: 12x36
 * com virada exata), não turno de duração zero.
 */
export function duracaoTurnoMinutos(inicio: string, fim: string): number {
  const inicioMinutos = paraMinutosDoDia(inicio);
  const fimMinutos = paraMinutosDoDia(fim);
  const MINUTOS_POR_DIA = 24 * 60;
  if (fimMinutos > inicioMinutos) return fimMinutos - inicioMinutos;
  if (fimMinutos < inicioMinutos) return MINUTOS_POR_DIA - inicioMinutos + fimMinutos;
  return MINUTOS_POR_DIA;
}

/**
 * Diferença em minutos entre dois instantes. Não corrige nem inverte:
 * se `fim` for anterior a `inicio`, o resultado é negativo — sinal de
 * inconsistência a ser tratada como **ocorrência**, nunca silenciosamente
 * corrigida aqui.
 */
export function calcularDuracaoEmMinutos(inicio: Date, fim: Date): number {
  const diferencaMs = fim.getTime() - inicio.getTime();
  return Math.round(diferencaMs / 60_000);
}
