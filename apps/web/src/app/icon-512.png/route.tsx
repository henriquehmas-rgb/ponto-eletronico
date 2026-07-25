import { ImageResponse } from "next/og";

export const runtime = "edge";

// Icone do manifesto PWA (512 px) — ver icon-192.png/route.tsx para o porque.
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
        borderRadius: 112,
      }}
    >
      <svg width="320" height="320" viewBox="0 0 32 32" fill="none">
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
    { width: 512, height: 512 },
  );
}
