import { ImageResponse } from "next/og";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

// Simbolo isolado sobre fundo solido de marca — nunca a palavra "SEEG PONTO"
// inteira num icone de app (Manual de Marca). iOS arredonda os cantos
// automaticamente no sistema, entao o fundo aqui e quadrado.
export default function AppleIcon() {
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#4C5FCA",
      }}
    >
      <svg width="112" height="112" viewBox="0 0 32 32" fill="none">
        <path
          d="M8.6 18.6 13.6 24.1 24.2 7.6"
          stroke="#FFFFFF"
          strokeWidth={2.6}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path d="M6.4 26 H25.6" stroke="#FFFFFF" strokeWidth={2.6} strokeLinecap="round" />
      </svg>
    </div>,
    { ...size },
  );
}
