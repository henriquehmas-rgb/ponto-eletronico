import type { SVGProps } from "react";

/**
 * Simbolo oficial da SEEG Ponto (identidade visual, RFC-003): um traco de
 * confirmacao pousando sobre a linha do dia. Nao e relogio, nao e olho — e o
 * gesto de quem confere um registro, no ponto certo.
 *
 * Dois `<path>` apenas, sem preenchimento, cor herdada via `currentColor` —
 * funciona em qualquer cor de texto, tema claro/escuro, monocromatico e
 * negativo sem redesenho. Legivel a partir de 16 px (tamanho de favicon).
 */
export function SimboloSeegPonto(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 32 32" fill="none" aria-hidden="true" {...props}>
      <path
        d="M8.6 18.6 13.6 24.1 24.2 7.6"
        stroke="currentColor"
        strokeWidth={2.6}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M6.4 26 H25.6" stroke="currentColor" strokeWidth={2.6} strokeLinecap="round" />
    </svg>
  );
}
