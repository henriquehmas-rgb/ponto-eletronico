import { formatarSaldo, type SinalSaldo } from "@/lib/formatacao/saldo";
import { minutosParaHHMM } from "@/lib/formatacao/tempo";
import { cn } from "@/lib/utils";

export interface CartaoDeSaldoDeBancoProps {
  /** Saldo atual em minutos. Positivo é credor, negativo é devedor (nunca "positivo/negativo" no rótulo). */
  saldoMinutos: number;
  /** Código da conta de banco de horas exibida (ex.: "principal", "compensacao"). */
  contaCodigo?: string;
  /** Minutos que vencem nos próximos 30 dias, quando a política tiver prazo de compensação. */
  aVencer30Minutos?: number;
  /** Data ISO da próxima expiração relevante, usada para destacar "vence em breve". */
  proximoVencimentoEm?: string;
  /** Variação do saldo no período consultado (positivo = ganhou saldo, negativo = perdeu). */
  variacaoMinutos?: number;
  /** Referência de "agora" para o cálculo de dias até o vencimento — injetável para teste determinístico. */
  dataReferencia?: Date;
}

const LIMITE_VENCIMENTO_PROXIMO_DIAS = 30;
const MS_POR_DIA = 24 * 60 * 60 * 1000;

const ROTULO_SINAL: Record<SinalSaldo, string> = {
  credor: "Saldo credor",
  devedor: "Saldo devedor",
  neutro: "Saldo zerado",
};

const CLASSE_COR_POR_SINAL: Record<SinalSaldo, string> = {
  credor: "text-estado-sucesso-texto",
  devedor: "text-estado-erro-texto",
  neutro: "text-texto-secundario",
};

const ICONE_POR_SINAL: Record<SinalSaldo, string> = {
  credor: "▲",
  devedor: "▼",
  neutro: "■",
};

function diasAte(dataIso: string, referencia: Date): number {
  const alvo = new Date(dataIso);
  const diffMs = alvo.getTime() - referencia.getTime();
  return Math.ceil(diffMs / MS_POR_DIA);
}

/**
 * Cartão do saldo de banco de horas: saldo credor/devedor com sinal
 * explícito por FORMA (ícone ▲/▼) e por COR — nunca só por cor (WCAG 1.4.1) —
 * mais vencimento próximo destacado e variação no período.
 */
export function CartaoDeSaldoDeBanco({
  saldoMinutos,
  contaCodigo,
  aVencer30Minutos,
  proximoVencimentoEm,
  variacaoMinutos,
  dataReferencia,
}: CartaoDeSaldoDeBancoProps) {
  const saldo = formatarSaldo(saldoMinutos);
  const referencia = dataReferencia ?? new Date();
  const diasParaVencer = proximoVencimentoEm ? diasAte(proximoVencimentoEm, referencia) : null;
  const vencimentoProximo =
    diasParaVencer !== null &&
    diasParaVencer >= 0 &&
    diasParaVencer <= LIMITE_VENCIMENTO_PROXIMO_DIAS &&
    (aVencer30Minutos ?? 0) > 0;

  return (
    <section
      className="flex flex-col gap-3 rounded-medio border border-borda-sutil bg-fundo-superficie p-3 shadow-baixa"
      aria-label={contaCodigo ? `Saldo de banco de horas — conta ${contaCodigo}` : "Saldo de banco de horas"}
    >
      <header className="flex items-center justify-between gap-2">
        <h3 className="estilo-titulo-cartao text-texto-primario">Banco de horas</h3>
        {contaCodigo ? (
          <span className="estilo-legenda text-texto-terciario">{contaCodigo}</span>
        ) : null}
      </header>

      <div className="flex items-baseline gap-2">
        <span aria-hidden="true" className={cn("estilo-titulo-secao", CLASSE_COR_POR_SINAL[saldo.sinal])}>
          {ICONE_POR_SINAL[saldo.sinal]}
        </span>
        <span className={cn("estilo-numero-destaque", CLASSE_COR_POR_SINAL[saldo.sinal])}>
          {saldo.textoComSinal}
        </span>
      </div>
      <p className={cn("estilo-rotulo", CLASSE_COR_POR_SINAL[saldo.sinal])}>{ROTULO_SINAL[saldo.sinal]}</p>

      {variacaoMinutos !== undefined && variacaoMinutos !== 0 ? (
        <p className="estilo-legenda text-texto-secundario">
          {variacaoMinutos > 0 ? "▲" : "▼"} {formatarSaldo(variacaoMinutos).textoComSinal} no período
        </p>
      ) : null}

      {vencimentoProximo && proximoVencimentoEm ? (
        <p
          role="status"
          className="estilo-legenda rounded-pequeno bg-estado-atencao-fundo px-2 py-1 text-estado-atencao-texto"
        >
          ⚠ {minutosParaHHMM(aVencer30Minutos ?? 0)} vencem em {diasParaVencer}{" "}
          {diasParaVencer === 1 ? "dia" : "dias"}
        </p>
      ) : null}
    </section>
  );
}
