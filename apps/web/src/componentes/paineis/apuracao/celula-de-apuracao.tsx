"use client";

import { formatarDiaDaSemanaAbreviado } from "@/lib/formatacao";
import { cn } from "@/lib/utils";
import type { Esquema } from "@/lib/api";

import {
  CLASSE_STATUS_APURACAO,
  MARCADOR_TIPO_DIA,
  ROTULO_STATUS_APURACAO,
  ROTULO_TIPO_DIA,
} from "./utilitarios";

/** Abreviação de duas letras do status — cabe na célula compacta da grade (32 px de altura, T9). */
const ABREVIACAO_STATUS: Record<NonNullable<Esquema<"ApuracaoDia">["status"]>, string> = {
  pendente: "Pd",
  apurado: "Ap",
  com_ocorrencia: "Oc",
  fechado: "Fe",
  reaberto: "Rb",
};

export interface CelulaDeApuracaoProps {
  data: string;
  apuracao: Esquema<"ApuracaoDia"> | undefined;
  /** Verdadeiro quando há ao menos uma ocorrência ABERTA (ou em tratamento) neste dia — reforça o destaque visual além do status da apuração. */
  temOcorrenciaAberta: boolean;
  onClick: () => void;
}

/**
 * Uma célula da grade de apuração (T9): colorida E rotulada por `tipoDia`/
 * `status`/presença de ocorrência — NUNCA só cor (WCAG 1.4.1, mesma regra que
 * a F9a já impôs aos componentes de domínio). O marcador de forma
 * (`MARCADOR_TIPO_DIA`) transmite o tipo de dia, o par cor+texto
 * (`CLASSE_STATUS_APURACAO`/`ABREVIACAO_STATUS`) transmite a situação da
 * apuração, e o ícone de atenção transmite ocorrência aberta — três canais
 * independentes de cor.
 *
 * É um `<button>` de verdade (não uma `<div onClick>`): mesmo padrão já
 * usado por outras colunas de `TabelaDeDados` nesta base (ex. a coluna
 * "razaoSocial" de `painel/cadastros/empresas`) para tornar uma célula
 * acionável por mouse E por teclado (Enter/Espaço nativos do elemento
 * `button`), sem depender de `TabelaDeDados` (congelado, F9a) saber lidar
 * com ativação de célula — ela só resolve navegação por seta.
 */
export function CelulaDeApuracao({
  data,
  apuracao,
  temOcorrenciaAberta,
  onClick,
}: CelulaDeApuracaoProps) {
  const diaDoMes = Number(data.slice(8, 10));
  const diaDaSemana = formatarDiaDaSemanaAbreviado(`${data}T12:00:00`);

  if (!apuracao?.status) {
    return (
      <button
        type="button"
        onClick={onClick}
        aria-label={`${diaDoMes} (${diaDaSemana}) — sem apuração. Abrir detalhe do dia.`}
        className={cn(
          "flex h-full w-full flex-col items-center justify-center gap-0 rounded-pequeno border",
          "border-borda-sutil bg-fundo-sutil text-texto-terciario",
          "hover:bg-fundo-enfase",
        )}
      >
        <span aria-hidden="true">{MARCADOR_TIPO_DIA.nao_apurado}</span>
        <span aria-hidden="true" className="estilo-legenda">
          —
        </span>
      </button>
    );
  }

  const tipoDia = apuracao.tipoDia;
  const marcador = tipoDia ? MARCADOR_TIPO_DIA[tipoDia] : "?";
  const rotuloTipoDia = tipoDia ? ROTULO_TIPO_DIA[tipoDia] : "Tipo de dia não classificado";
  const abreviacao = ABREVIACAO_STATUS[apuracao.status];
  const rotuloStatus = ROTULO_STATUS_APURACAO[apuracao.status];

  const rotuloAcessivel = [
    `${diaDoMes} (${diaDaSemana})`,
    rotuloTipoDia,
    rotuloStatus,
    apuracao.marcacoesImpares ? "marcações ímpares" : null,
    temOcorrenciaAberta ? "com ocorrência aberta" : null,
    "Abrir detalhe do dia.",
  ]
    .filter(Boolean)
    .join(" — ");

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={rotuloAcessivel}
      className={cn(
        "flex h-full w-full flex-col items-center justify-center gap-0 rounded-pequeno border",
        "transition-colors duration-imediata ease-padrao hover:brightness-95",
        CLASSE_STATUS_APURACAO[apuracao.status],
      )}
    >
      <span aria-hidden="true" className="leading-none">
        {marcador}
        {temOcorrenciaAberta ? <span className="ml-0.5">⚠</span> : null}
      </span>
      <span aria-hidden="true" className="estilo-legenda leading-none">
        {abreviacao}
      </span>
    </button>
  );
}
