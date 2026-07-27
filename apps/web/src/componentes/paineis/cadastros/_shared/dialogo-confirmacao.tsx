"use client";

import { Botao } from "@/componentes/ui/button";
import {
  Dialogo,
  DialogoCabecalho,
  DialogoConteudo,
  DialogoDescricao,
  DialogoRodape,
  DialogoTitulo,
} from "@/componentes/ui/dialog";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";

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
 * Confirmação genérica para ações irreversíveis ou de alto impacto (exclusão
 * lógica, revogação, encerramento). O design system não fixa um `AlertDialog`
 * dedicado (§4/§9 F9a) — este componente compõe `Dialogo` (T4) com o botão
 * destrutivo, mesma linguagem visual, sem duplicar o primitivo congelado.
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
          <Botao variant="secundaria" onClick={() => aoMudarAberto(false)} disabled={confirmando}>
            Cancelar
          </Botao>
          <Botao variant="destrutiva" onClick={aoConfirmar} disabled={confirmando}>
            {confirmando ? "Aguarde…" : rotuloConfirmar}
          </Botao>
        </DialogoRodape>
      </DialogoConteudo>
    </Dialogo>
  );
}
