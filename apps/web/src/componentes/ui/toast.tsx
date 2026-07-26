"use client";

import * as React from "react";
import { AlertTriangle, CheckCircle2, Info, XCircle, XIcon } from "lucide-react";
import { Toast as ToastPrimitive } from "radix-ui";

import { cn } from "@/lib/utils";

/**
 * Notificacao (`toast`) — T4.
 *
 * `camada.notificacao` (1200) e o segundo nivel mais alto da escala — so
 * perde para `depuracao`, que nunca aparece em producao — por isso uma
 * notificacao aparece por cima de dialogo, popover e dica.
 *
 * Acessibilidade: cada variante tem um ICONE proprio (nunca so cor) e a
 * urgencia do anuncio para leitor de tela muda com a severidade — erro
 * interrompe (`assertive`), as demais so anunciam quando o leitor de tela
 * estiver ocioso (`polite`). Isso NAO depende do texto que o consumidor
 * escreve.
 *
 * IMPORTANTE: essa urgencia e controlada pela prop `type` do Radix
 * (`"foreground"` = assertive, `"background"` = polite) — NUNCA por um
 * `role`/`aria-live` escrito a mao no `<li>` (`ToastPrimitive.Root`). O
 * Radix ja anuncia o conteudo por conta propria, via uma regiao
 * visualmente oculta separada (`ToastAnnounce`, portada para fora do
 * `<ol>`) que le `type` para decidir a urgencia. Um `role="status"` (ou
 * "alert") direto no `<li>` sobrescreve o papel implicito `listitem` dele
 * — "status"/"alert" nao estao entre os papeis ARIA permitidos num `<li>`
 * — e quebra a estrutura de lista (`<ol>` passaria a ter um filho direto
 * sem papel de item de lista), reprovando o axe na regra `list` mesmo com
 * o DOM visualmente correto. Verificado ao vivo: reproduzido injetando o
 * axe-core no build estatico do Storybook, corrigido removendo o
 * `role`/`aria-live` manual e usando `type`.
 *
 * Composicao obrigatoria: `<Notificacao>` (renderizada como `<li>` pelo
 * Radix) precisa ser FILHO DIRETO de `<NotificacaoViewport>` (um `<ol>`) —
 * Radix Toast nao porta automaticamente uma instancia solta para dentro do
 * viewport. Ver `toast.stories.tsx` para o padrao de composicao correto.
 */

function NotificacaoProvedor({ ...props }: React.ComponentProps<typeof ToastPrimitive.Provider>) {
  return <ToastPrimitive.Provider data-slot="notificacao-provedor" {...props} />;
}

function NotificacaoViewport({
  className,
  ...props
}: React.ComponentProps<typeof ToastPrimitive.Viewport>) {
  return (
    <ToastPrimitive.Viewport
      data-slot="notificacao-viewport"
      className={cn(
        "fixed top-0 right-0 z-[var(--camada-notificacao)] flex max-h-screen w-full flex-col-reverse gap-2 p-[var(--espacamento-2)]",
        "sm:top-auto sm:bottom-0 sm:max-w-sm",
        className,
      )}
      {...props}
    />
  );
}

type VarianteDeNotificacao = "sucesso" | "atencao" | "erro" | "info";

const ICONE_POR_VARIANTE: Record<VarianteDeNotificacao, typeof CheckCircle2> = {
  sucesso: CheckCircle2,
  atencao: AlertTriangle,
  erro: XCircle,
  info: Info,
};

const CLASSE_POR_VARIANTE: Record<VarianteDeNotificacao, string> = {
  sucesso: "border-estado-sucesso-borda bg-estado-sucesso-fundo text-estado-sucesso-texto",
  atencao: "border-estado-atencao-borda bg-estado-atencao-fundo text-estado-atencao-texto",
  erro: "border-estado-erro-borda bg-estado-erro-fundo text-estado-erro-texto",
  info: "border-estado-info-borda bg-estado-info-fundo text-estado-info-texto",
};

const ICONE_CLASSE_POR_VARIANTE: Record<VarianteDeNotificacao, string> = {
  sucesso: "text-estado-sucesso-icone",
  atencao: "text-estado-atencao-icone",
  erro: "text-estado-erro-icone",
  info: "text-estado-info-icone",
};

interface NotificacaoProps extends React.ComponentProps<typeof ToastPrimitive.Root> {
  variante?: VarianteDeNotificacao;
}

function Notificacao({ className, variante = "info", children, ...props }: NotificacaoProps) {
  const Icone = ICONE_POR_VARIANTE[variante];
  return (
    <ToastPrimitive.Root
      data-slot="notificacao"
      data-variante={variante}
      type={variante === "erro" ? "foreground" : "background"}
      className={cn(
        "pointer-events-auto relative flex w-full items-start gap-3 overflow-hidden rounded-medio border p-4 shadow-media",
        "data-[swipe=move]:translate-x-(--radix-toast-swipe-move-x)",
        "data-[swipe=cancel]:translate-x-0 data-[swipe=cancel]:transition-transform",
        "data-[swipe=end]:animate-out data-[state=open]:animate-in data-[state=closed]:animate-out",
        "data-[state=open]:slide-in-from-top-full data-[state=closed]:fade-out-80 sm:data-[state=open]:slide-in-from-bottom-full",
        "duration-padrao",
        CLASSE_POR_VARIANTE[variante],
        className,
      )}
      {...props}
    >
      <Icone
        aria-hidden="true"
        className={cn("mt-0.5 size-5 shrink-0", ICONE_CLASSE_POR_VARIANTE[variante])}
      />
      <div className="flex-1">{children}</div>
    </ToastPrimitive.Root>
  );
}

function NotificacaoTitulo({ className, ...props }: React.ComponentProps<typeof ToastPrimitive.Title>) {
  return (
    <ToastPrimitive.Title
      data-slot="notificacao-titulo"
      className={cn("estilo-rotulo", className)}
      {...props}
    />
  );
}

function NotificacaoDescricao({
  className,
  ...props
}: React.ComponentProps<typeof ToastPrimitive.Description>) {
  return (
    <ToastPrimitive.Description
      data-slot="notificacao-descricao"
      className={cn("estilo-legenda mt-1", className)}
      {...props}
    />
  );
}

function NotificacaoAcao({ className, ...props }: React.ComponentProps<typeof ToastPrimitive.Action>) {
  return (
    <ToastPrimitive.Action
      data-slot="notificacao-acao"
      className={cn(
        "estilo-rotulo mt-2 inline-flex h-[var(--dimensao-altura-controle-compacta)] items-center",
        "rounded-pequeno border border-current bg-transparent px-3",
        "transition-colors duration-imediata ease-padrao hover:underline",
        className,
      )}
      {...props}
    />
  );
}

function NotificacaoFechar({ className, ...props }: React.ComponentProps<typeof ToastPrimitive.Close>) {
  return (
    <ToastPrimitive.Close
      data-slot="notificacao-fechar"
      aria-label="Fechar notificacao"
      className={cn(
        "absolute top-2 right-2 rounded-pequeno p-1 text-current opacity-70",
        "transition-opacity duration-imediata ease-padrao hover:opacity-100",
        className,
      )}
      {...props}
    >
      <XIcon className="size-4" aria-hidden="true" />
    </ToastPrimitive.Close>
  );
}

export {
  NotificacaoProvedor,
  NotificacaoViewport,
  Notificacao,
  NotificacaoTitulo,
  NotificacaoDescricao,
  NotificacaoAcao,
  NotificacaoFechar,
};
export type { VarianteDeNotificacao };
