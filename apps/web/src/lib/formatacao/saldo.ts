import { minutosParaDecimal, minutosParaHHMM } from "./tempo";

/**
 * Sinal do saldo de banco de horas. Vocabulário obrigatório do glossário
 * (seção 6): é **credor** / **devedor** — nunca "positivo" / "negativo".
 */
export type SinalSaldo = "credor" | "devedor" | "neutro";

export function sinalDoSaldo(saldoMinutos: number): SinalSaldo {
  if (saldoMinutos > 0) return "credor";
  if (saldoMinutos < 0) return "devedor";
  return "neutro";
}

export interface SaldoFormatado {
  /** Credor (saldo a favor do colaborador), devedor ou neutro. */
  sinal: SinalSaldo;
  /** Magnitude em HH:MM, sempre sem sinal (o sinal é transmitido por `sinal`). */
  textoHHMM: string;
  /** Magnitude em decimal pt-BR, sempre sem sinal. */
  textoDecimal: string;
  /** HH:MM com o sinal explícito na frente (`+1:30`, `-0:45`, `0:00`). */
  textoComSinal: string;
}

/**
 * Formata um saldo de banco de horas com sinal explícito. O sinal **nunca**
 * é transmitido só pela cor: o chamador usa `sinal` para escolher também um
 * rótulo textual ("Saldo credor" / "Saldo devedor") e, quando aplicável, um
 * ícone de forma distinta (seta para cima / para baixo) — ver
 * `CartaoDeSaldoDeBanco`.
 */
export function formatarSaldo(saldoMinutos: number): SaldoFormatado {
  const sinal = sinalDoSaldo(saldoMinutos);
  const magnitude = Math.abs(saldoMinutos);
  const textoHHMM = minutosParaHHMM(magnitude);
  const textoDecimal = minutosParaDecimal(magnitude);
  const prefixo = sinal === "credor" ? "+" : sinal === "devedor" ? "-" : "";
  return { sinal, textoHHMM, textoDecimal, textoComSinal: `${prefixo}${textoHHMM}` };
}
