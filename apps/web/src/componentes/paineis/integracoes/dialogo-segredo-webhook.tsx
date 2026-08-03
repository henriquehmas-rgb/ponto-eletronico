"use client";

import { useState } from "react";

import { Alerta, AlertaDescricao, AlertaTitulo } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import {
  Dialogo,
  DialogoCabecalho,
  DialogoConteudo,
  DialogoDescricao,
  DialogoRodape,
  DialogoTitulo,
} from "@/componentes/ui/dialog";
import type { Esquema } from "@/lib/api";

interface DialogoSegredoWebhookProps {
  webhookCriado: Esquema<"WebhookCriado"> | null;
  aoFechar: () => void;
}

/**
 * Exibição única do segredo HMAC devolvido por `criarWebhook` (T14). O
 * contrato é explícito: o segredo "aparece uma única vez" e não é
 * recuperável depois (`WebhookCriado.segredoHmac`) — este diálogo é a única
 * chance da tela de mostrá-lo, por isso não fecha sozinho e insiste no aviso
 * antes de qualquer ação de cópia.
 */
export function DialogoSegredoWebhook({ webhookCriado, aoFechar }: DialogoSegredoWebhookProps) {
  const [copiado, setCopiado] = useState(false);

  async function copiar() {
    if (!webhookCriado?.segredoHmac) return;
    try {
      await navigator.clipboard.writeText(webhookCriado.segredoHmac);
      setCopiado(true);
    } catch {
      setCopiado(false);
    }
  }

  return (
    <Dialogo
      open={Boolean(webhookCriado)}
      onOpenChange={(aberto) => {
        if (!aberto) {
          setCopiado(false);
          aoFechar();
        }
      }}
    >
      <DialogoConteudo className="sm:max-w-lg">
        <DialogoCabecalho>
          <DialogoTitulo>Webhook criado</DialogoTitulo>
          <DialogoDescricao>
            {webhookCriado?.webhook?.nome ?? "O webhook"} foi criado e já está pronto para receber
            eventos.
          </DialogoDescricao>
        </DialogoCabecalho>

        <Alerta variant="atencao">
          <AlertaTitulo>Guarde este segredo agora</AlertaTitulo>
          <AlertaDescricao>
            O segredo de assinatura HMAC aparece uma única vez nesta tela. Perdendo-o, a única saída
            é criar um novo webhook.
          </AlertaDescricao>
        </Alerta>

        <div className="flex flex-col gap-1">
          <p className="estilo-legenda text-texto-terciario">Segredo HMAC</p>
          <code className="break-all rounded-medio border border-borda-padrao bg-fundo-sutil p-3 estilo-corpo text-texto-primario">
            {webhookCriado?.segredoHmac}
          </code>
        </div>

        <p className="estilo-legenda text-texto-terciario">
          Cabeçalho de assinatura: <strong>{webhookCriado?.cabecalhoAssinatura}</strong>
          {webhookCriado?.formatoAssinatura ? ` — formato: ${webhookCriado.formatoAssinatura}` : ""}
        </p>

        <DialogoRodape>
          <Botao
            type="button"
            variant="secundaria"
            onClick={() => {
              void copiar();
            }}
          >
            {copiado ? "Copiado!" : "Copiar segredo"}
          </Botao>
          <Botao
            type="button"
            onClick={() => {
              setCopiado(false);
              aoFechar();
            }}
          >
            Já guardei, fechar
          </Botao>
        </DialogoRodape>
      </DialogoConteudo>
    </Dialogo>
  );
}
