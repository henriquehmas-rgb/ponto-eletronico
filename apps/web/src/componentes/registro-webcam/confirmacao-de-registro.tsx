import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import Link from "next/link";

import { Botao } from "@/componentes/ui/button";
import { Cartao } from "@/componentes/ui/card";
import { cn } from "@/lib/utils";

/**
 * Confirmação de registro — T9 do PCF F08.
 *
 * Os TRÊS desfechos do fluxo de registro, visualmente distintos e cada um
 * anunciado por `aria-live="polite"` — nunca atrasado por animação (mesma
 * regra de produto do token de movimento da F9a, §9 proibição 13):
 * "sucesso" (`revisaoRequerida === false`), "sucesso com revisão"
 * (`revisaoRequerida === true`, nota neutra — nunca alarmante, não é erro) e
 * "recusado" (mensagem do dicionário de erros de A3, mapeada do `codigo` do
 * `Problema` — inclusive quando a recusa aconteceu no CLIENTE, antes de
 * qualquer chamada de rede, como na detecção de câmera virtual, T8).
 *
 * Ao contrário da tela de captura (`FluxoDeRegistro`), esta tela segue o
 * tema claro/escuro normal do produto — os tokens aqui são `texto-*`/
 * `estado-*`, nunca `primitivo-*` fixo.
 */
export type VarianteDeConfirmacao = "sucesso" | "sucesso_com_revisao" | "recusado";

export interface ConfirmacaoDeRegistroProps {
  variante: VarianteDeConfirmacao;
  /** Número do comprovante — só para "sucesso"/"sucesso_com_revisao". */
  numeroDoComprovante?: string;
  /** NSR da marcação — só para "sucesso"/"sucesso_com_revisao". */
  nsr?: number;
  /** Horário já formatado (`HH:MM`) — só para "sucesso"/"sucesso_com_revisao". */
  horario?: string;
  /** A marcação chegou pela fila offline — mostra a nota de sincronização. */
  coletadaOffline?: boolean;
  /** Mensagem do dicionário de erros (T13, A3) — só para "recusado". */
  mensagem?: string;
}

const APRESENTACAO_POR_VARIANTE = {
  sucesso: {
    Icone: CheckCircle2,
    fundo: "bg-estado-sucesso-fundo",
    icone: "text-estado-sucesso-icone",
    titulo: "Ponto registrado",
  },
  sucesso_com_revisao: {
    Icone: AlertTriangle,
    fundo: "bg-estado-atencao-fundo",
    icone: "text-estado-atencao-icone",
    titulo: "Ponto registrado",
  },
  recusado: {
    Icone: XCircle,
    fundo: "bg-estado-erro-fundo",
    icone: "text-estado-erro-icone",
    titulo: "Não foi possível confirmar o registro",
  },
} as const;

function LinhaDeResumo({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-xs text-texto-terciario">{rotulo}</span>
      <span className="text-xs font-semibold text-texto-primario">{valor}</span>
    </div>
  );
}

export function ConfirmacaoDeRegistro({
  variante,
  numeroDoComprovante,
  nsr,
  horario,
  coletadaOffline,
  mensagem,
}: ConfirmacaoDeRegistroProps) {
  const apresentacao = APRESENTACAO_POR_VARIANTE[variante];
  const Icone = apresentacao.Icone;
  const mostrarResumo = variante !== "recusado";

  return (
    <div
      role="alert"
      aria-live="polite"
      className="flex flex-col items-center gap-[var(--espacamento-4)] px-[var(--espacamento-2)] py-[var(--espacamento-6)] text-center"
    >
      <span
        className={cn(
          "flex size-32 shrink-0 items-center justify-center rounded-pleno",
          apresentacao.fundo,
        )}
      >
        <Icone aria-hidden="true" className={cn("size-14", apresentacao.icone)} />
      </span>

      <div className="flex flex-col gap-1">
        <h2 className="font-display text-3xl font-bold text-texto-primario">
          {apresentacao.titulo}
        </h2>
        {variante === "recusado" && (
          <p className="max-w-xs text-sm leading-relaxed text-texto-secundario">
            {mensagem}
          </p>
        )}
      </div>

      {mostrarResumo && (
        <p
          className="font-mono leading-none font-semibold tracking-tight tabular-nums text-texto-primario"
          style={{ fontSize: 56 }}
        >
          {horario}
        </p>
      )}

      {mostrarResumo && (
        <Cartao className="w-full max-w-sm gap-[var(--espacamento-2)] rounded-suave p-[var(--espacamento-4)] text-left shadow-flutuante-cartao">
          <LinhaDeResumo
            rotulo="Comprovante"
            valor={`${numeroDoComprovante ?? ""} · NSR ${nsr ?? ""}`}
          />
          <LinhaDeResumo rotulo="Método" valor="Reconhecimento facial · webcam" />
        </Cartao>
      )}

      {variante === "sucesso_com_revisao" && (
        <p className="max-w-sm text-xs leading-relaxed text-texto-secundario">
          Seu gestor vai revisar este registro. Isso não impede o registro nem indica um erro.
        </p>
      )}

      {mostrarResumo && coletadaOffline && (
        <p
          className="font-mono text-2xs text-texto-terciario"
          style={{ letterSpacing: "0.04em" }}
        >
          Registrado offline — sincroniza automaticamente quando a conexão voltar.
        </p>
      )}

      <Botao
        asChild
        variant="primaria"
        tamanho="toque"
        className="mt-[var(--espacamento-2)] w-full max-w-sm rounded-grande"
      >
        <Link href="/eu">Voltar para o início</Link>
      </Botao>
    </div>
  );
}
