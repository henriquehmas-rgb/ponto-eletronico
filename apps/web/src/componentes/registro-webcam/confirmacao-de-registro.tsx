import { Alerta, AlertaDescricao, AlertaTitulo } from "@/componentes/ui/alert";

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
  /** Mensagem do dicionário de erros (T13, A3) — só para "recusado". */
  mensagem?: string;
}

export function ConfirmacaoDeRegistro({
  variante,
  numeroDoComprovante,
  nsr,
  horario,
  mensagem,
}: ConfirmacaoDeRegistroProps) {
  if (variante === "recusado") {
    return (
      <Alerta variant="erro" aria-live="polite">
        <AlertaTitulo>Não foi possível confirmar o registro</AlertaTitulo>
        <AlertaDescricao>{mensagem}</AlertaDescricao>
      </Alerta>
    );
  }

  return (
    <Alerta variant="sucesso" aria-live="polite">
      <AlertaTitulo>Ponto registrado</AlertaTitulo>
      <AlertaDescricao>
        <span className="block">
          Comprovante {numeroDoComprovante} · NSR {nsr} · {horario}
        </span>
        {variante === "sucesso_com_revisao" && (
          <span className="mt-[var(--espacamento-1)] block text-texto-secundario">
            Seu gestor vai revisar este registro. Isso não impede o registro nem indica um erro.
          </span>
        )}
      </AlertaDescricao>
    </Alerta>
  );
}
