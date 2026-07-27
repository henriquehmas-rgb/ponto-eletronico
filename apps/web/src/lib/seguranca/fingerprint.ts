/**
 * Fingerprint de dispositivo — T11 do PCF F08.
 *
 * Só Web Crypto (`crypto.subtle.digest`), sem biblioteca de terceiros de
 * fingerprinting (proibição explícita do PCF): concatena sinais estáveis do
 * navegador — `userAgent`, resolução/profundidade de cor da tela, fuso
 * horário, idioma(s), núcleos de CPU e um hash de *canvas rendering* — e
 * aplica SHA-256 sobre a concatenação.
 *
 * O resultado é persistido em `localStorage` sob a chave `ponto:fingerprint`
 * para ser ESTÁVEL entre chamadas e entre sessões do mesmo navegador — não é
 * recalculado a cada chamada. Usado em dois lugares (fora deste módulo):
 * `LoginRequisicao.fingerprint` (T1, A1) e `flagsIntegridade.fingerprint` de
 * `MarcacaoCriar` (T9, A2).
 */

/** Chave de persistência em `localStorage`. Documentada aqui de propósito:
 *  é a única fonte da verdade sobre onde o valor estável mora. */
export const CHAVE_FINGERPRINT_NO_ARMAZENAMENTO = "ponto:fingerprint";

async function sha256Hex(entrada: string): Promise<string> {
  const bytes = new TextEncoder().encode(entrada);
  const digestBuffer = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digestBuffer))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * Desenha uma forma FIXA e documentada (não varia entre chamadas) e lê
 * `toDataURL()`. Pequenas diferenças de renderização de fonte/GPU entre
 * máquinas produzem hashes de canvas diferentes — é exatamente o sinal
 * antifraude que este passo contribui.
 */
function hashDeCanvas(): string {
  try {
    const tela = document.createElement("canvas");
    tela.width = 220;
    tela.height = 30;
    const contexto = tela.getContext("2d");
    if (!contexto) return "sem-contexto-canvas";
    contexto.textBaseline = "top";
    contexto.font = "14px Arial";
    contexto.fillStyle = "#f60";
    contexto.fillRect(0, 0, 100, 20);
    contexto.fillStyle = "#069";
    contexto.fillText("ponto-eletronico-fingerprint", 2, 2);
    return tela.toDataURL();
  } catch {
    return "sem-canvas";
  }
}

/** Concatena os insumos documentados pelo PCF, na ordem fixada aqui. */
function insumosDoAmbiente(): string {
  const agente = navigator.userAgent;
  const tela =
    typeof screen !== "undefined"
      ? `${screen.width}x${screen.height}x${screen.colorDepth}`
      : "sem-tela";
  const fuso = Intl.DateTimeFormat().resolvedOptions().timeZone || "sem-fuso";
  const idiomas = navigator.languages?.join(",") || navigator.language || "sem-idioma";
  const nucleos = navigator.hardwareConcurrency ?? 0;
  const canvas = hashDeCanvas();
  return [agente, tela, fuso, idiomas, String(nucleos), canvas].join("|");
}

/**
 * Calcula (ou recupera, se já estável neste navegador) o fingerprint.
 *
 * Só roda no navegador: usa `localStorage`, `screen`, `document` e
 * `navigator`, indisponíveis em Server Components.
 */
export async function calcularFingerprint(): Promise<string> {
  if (typeof window === "undefined") {
    throw new Error("calcularFingerprint só pode ser chamado no navegador");
  }

  const existente = window.localStorage.getItem(CHAVE_FINGERPRINT_NO_ARMAZENAMENTO);
  if (existente) return existente;

  const hash = await sha256Hex(insumosDoAmbiente());
  try {
    window.localStorage.setItem(CHAVE_FINGERPRINT_NO_ARMAZENAMENTO, hash);
  } catch {
    // Quota excedida ou modo privado sem persistência: o valor ainda é
    // devolvido para esta chamada, só não fica estável entre sessões.
  }
  return hash;
}
