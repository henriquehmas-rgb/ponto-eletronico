import { ImageResponse } from "next/og";

export const runtime = "edge";

// Icone do manifesto PWA (192 px, "qualquer proposito" no Android/Chrome).
// Mesmo desenho do favicon e do apple-icon: simbolo isolado sobre fundo
// solido de marca, cantos arredondados (a mascara adaptavel de verdade,
// especifica de Android, e assunto do app Flutter na F7 — isto aqui e so o
// icone que o Chrome/Edge usam ao "instalar" o site como PWA).
export async function GET() {
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#4C5FCA",
        borderRadius: 42,
      }}
    >
      <svg width="120" height="120" viewBox="0 0 32 32" fill="none">
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
    { width: 192, height: 192 },
  );
}
