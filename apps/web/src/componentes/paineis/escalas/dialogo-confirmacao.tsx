"use client";

import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import {
  Dialogo,
  DialogoCabecalho,
  DialogoConteudo,
  DialogoDescricao,
  DialogoRodape,
  DialogoTitulo,
} from "@/componentes/ui/dialog";

interface DialogoConfirmacaoProps {
  aberto: boolean;
  aoMudarAberto: (aberto: boolean) => void;
  titulo: string;
  descricao: string;
  rotuloConfirmar?: string;
  confirmando?: boolean;
  erro?: string | undefined;
  aoConfirmar: () => void;
}

/**
 * Confirmação genérica para ações de alto impacto (exclusão lógica de
 * escala). O design system não fixa um `AlertDialog` dedicado (F9a §4/§9) —
 * compõe `Dialogo` (T4) com o botão destrutivo, sem duplicar o primitivo
 * congelado. Cópia local do mesmo padrão independente em
 * `paineis/cadastros/_shared/dialogo-confirmacao.tsx` (A2).
 */
export function DialogoConfirmacao({
  aberto,
  aoMudarAberto,
  titulo,
  descricao,
  rotuloConfirmar = "Confirmar",
  confirmando = false,
  erro,
  aoConfirmar,
}: DialogoConfirmacaoProps) {
  return (
    <Dialogo open={aberto} onOpenChange={aoMudarAberto}>
      <DialogoConteudo>
        <DialogoCabecalho>
          <DialogoTitulo>{titulo}</DialogoTitulo>
          <DialogoDescricao>{descricao}</DialogoDescricao>
        </DialogoCabecalho>
        {erro ? (
          <Alerta variant="erro">
            <AlertaDescricao>{erro}</AlertaDescricao>
          </Alerta>
        ) : null}
        <DialogoRodape>
          <Botao
            variant="secundaria"
            disabled={confirmando}
            onClick={() => {
              aoMudarAberto(false);
            }}
          >
            Cancelar
          </Botao>
          <Botao variant="destrutiva" disabled={confirmando} onClick={aoConfirmar}>
            {confirmando ? "Aguarde…" : rotuloConfirmar}
          </Botao>
        </DialogoRodape>
      </DialogoConteudo>
    </Dialogo>
  );
}
