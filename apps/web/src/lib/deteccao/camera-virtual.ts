/**
 * Detecção de câmera virtual — T8 do PCF F08.
 *
 * Defesa em profundidade: três sinais independentes, nenhum sozinho é a
 * prova final, mas QUALQUER UM positivo já marca `flagsIntegridade.
 * cameraVirtual = true` e impede o envio da marcação no cliente (T9) — o
 * motor de confiança do servidor é um *stub* permissivo hoje (F14 ainda não
 * rodou, ver §2 do PCF), então o bloqueio real só existe aqui.
 *
 * As funções puras (`rotuloIndicaCameraVirtual`, `capacidadesIndicamSuspeita`,
 * `calcularHashPerceptual`, `amostraIndicaRepeticaoDeQuadro`,
 * `avaliarSinaisDeCameraVirtual`) não tocam DOM nem temporizador — são
 * testadas com dados sintéticos. `monitorarCameraVirtual`, no fim do
 * arquivo, é a única função impura (lê a trilha de vídeo real e amostra o
 * `<video>` em um `<canvas>`) e não é testada por teste unitário — é
 * coberta pelo teste de integração (Playwright, T9/T10) com o rótulo do
 * dispositivo simulado.
 */

// -----------------------------------------------------------------------------
// Sinal 1 — rótulo do dispositivo (primário, alta precisão).
// -----------------------------------------------------------------------------

/**
 * Lista mantida no próprio módulo, documentada e revisável, de substrings
 * conhecidas de câmeras virtuais (comparação sem diferenciar maiúsculas/
 * minúsculas). Mínimo exigido pelo PCF — adicione mais aqui se um novo
 * software de câmera virtual for identificado em produção (não é preciso
 * RFC para isto: é uma lista de dados, não um contrato entre fases).
 */
export const ROTULOS_DE_CAMERA_VIRTUAL_CONHECIDOS: readonly string[] = [
  "obs virtual camera",
  "obs-camera",
  "droidcam",
  "manycam",
  "snap camera",
  "camtwist",
  "xsplit vcam",
  "iriun",
  "epoccam",
];

export function rotuloIndicaCameraVirtual(rotulo: string): boolean {
  const normalizado = rotulo.toLowerCase();
  return ROTULOS_DE_CAMERA_VIRTUAL_CONHECIDOS.some((conhecido) => normalizado.includes(conhecido));
}

// -----------------------------------------------------------------------------
// Sinal 2 — capacidades da trilha (secundário).
// -----------------------------------------------------------------------------

export interface CapacidadesDaTrilha {
  frameRateMin?: number;
  frameRateMax?: number;
}

/**
 * Padrões de `frameRate` tipicamente anunciados por webcams físicas —
 * documentado aqui de propósito (critério do PCF: "documente os padrões
 * considerados normais no módulo").
 */
const FRAME_RATES_TIPICOS_DE_WEBCAM_FISICA: readonly number[] = [24, 25, 30, 50, 60];
const TOLERANCIA_FRAME_RATE = 0.5;

/**
 * Suspeito quando a trilha anuncia um `frameRate` EXATO fixo (min === max —
 * webcam física normalmente reporta uma FAIXA) fora dos padrões típicos
 * listados acima.
 */
export function capacidadesIndicamSuspeita(capacidades: CapacidadesDaTrilha): boolean {
  const { frameRateMin, frameRateMax } = capacidades;
  if (frameRateMin === undefined || frameRateMax === undefined) return false;
  if (frameRateMin !== frameRateMax) return false;
  return !FRAME_RATES_TIPICOS_DE_WEBCAM_FISICA.some(
    (tipico) => Math.abs(tipico - frameRateMin) <= TOLERANCIA_FRAME_RATE,
  );
}

// -----------------------------------------------------------------------------
// Sinal 3 — repetição de quadro (secundário, contra vídeo em loop).
// -----------------------------------------------------------------------------

export interface DadosDeImagemRgba {
  largura: number;
  altura: number;
  /** RGBA, 4 bytes por pixel, linha a linha — mesmo formato de `ImageData.data`. */
  dados: Uint8ClampedArray | number[];
}

const LADO_DO_HASH = 16;

function tonalidadeDeCinza(r: number, g: number, b: number): number {
  return 0.299 * r + 0.587 * g + 0.114 * b;
}

function reamostrarParaCinza(
  imagem: DadosDeImagemRgba,
  larguraAlvo: number,
  alturaAlvo: number,
): number[] {
  const saida: number[] = new Array(larguraAlvo * alturaAlvo).fill(0);
  for (let y = 0; y < alturaAlvo; y++) {
    for (let x = 0; x < larguraAlvo; x++) {
      const origemX = Math.min(Math.floor((x / larguraAlvo) * imagem.largura), imagem.largura - 1);
      const origemY = Math.min(Math.floor((y / alturaAlvo) * imagem.altura), imagem.altura - 1);
      const indiceOrigem = (origemY * imagem.largura + origemX) * 4;
      const r = imagem.dados[indiceOrigem] ?? 0;
      const g = imagem.dados[indiceOrigem + 1] ?? 0;
      const b = imagem.dados[indiceOrigem + 2] ?? 0;
      saida[y * larguraAlvo + x] = tonalidadeDeCinza(r, g, b);
    }
  }
  return saida;
}

/**
 * Hash de diferença (dHash): reduz a imagem a 17×16 em tons de cinza,
 * compara cada pixel com o vizinho à direita e produz 256 bits (64 dígitos
 * hexadecimais). Dois quadros visualmente idênticos produzem o mesmo hash;
 * pequenas variações naturais (micro-movimento, ruído de sensor, piscar)
 * mudam pelo menos alguns bits.
 *
 * Resolução 16×16 (não 8×8): a resolução mais baixa, testada contra a
 * câmera falsa do Chromium (`--use-fake-device-for-media-stream`, usada no
 * E2E de T10) mostrou falso positivo — o padrão sintético do dispositivo
 * fabricado é, em grande parte, estático o bastante para produzir o MESMO
 * hash grosseiro em amostras sucessivas, mesmo sem ser um vídeo em loop de
 * verdade. Mais bits reduzem esse risco de falso positivo (inclusive contra
 * um colaborador real muito parado) sem abrir mão de detectar repetição
 * EXATA de verdade (vídeo em loop clássico continua batendo 100% do tempo).
 */
export function calcularHashPerceptual(imagem: DadosDeImagemRgba): string {
  const largura = LADO_DO_HASH + 1;
  const altura = LADO_DO_HASH;
  const cinza = reamostrarParaCinza(imagem, largura, altura);

  let bits = "";
  for (let linha = 0; linha < altura; linha++) {
    for (let coluna = 0; coluna < LADO_DO_HASH; coluna++) {
      const atual = cinza[linha * largura + coluna] ?? 0;
      const proximo = cinza[linha * largura + coluna + 1] ?? 0;
      bits += atual > proximo ? "1" : "0";
    }
  }

  let hex = "";
  for (let i = 0; i < bits.length; i += 4) {
    hex += parseInt(bits.slice(i, i + 4), 2).toString(16);
  }
  return hex;
}

/** Amostra mínima para tentar inferir periodicidade (amostras curtas demais não provam nada). */
const AMOSTRAS_MINIMAS_PARA_INFERIR_REPETICAO = 6;
/** Fração mínima de coincidências, para um dado período, que caracteriza repetição regular. */
const PROPORCAO_MINIMA_DE_COINCIDENCIA = 0.75;
/** Comparações mínimas naquele período, para não inferir de uma amostra rasa demais. */
const COMPARACOES_MINIMAS = 3;

/**
 * Sinaliza suspeita quando o MESMO hash se repete em um período regular
 * (assinatura de vídeo em *loop*). Amostras de um rosto vivo variam quadro a
 * quadro (respiração, micro-expressão, ruído); um vídeo em loop repete
 * exatamente o mesmo quadro a cada N amostras.
 */
export function amostraIndicaRepeticaoDeQuadro(hashes: readonly string[]): boolean {
  const n = hashes.length;
  if (n < AMOSTRAS_MINIMAS_PARA_INFERIR_REPETICAO) return false;

  for (let periodo = 1; periodo <= Math.floor(n / 2); periodo++) {
    let coincidencias = 0;
    let comparacoes = 0;
    for (let i = 0; i + periodo < n; i++) {
      comparacoes += 1;
      if (hashes[i] === hashes[i + periodo]) coincidencias += 1;
    }
    if (
      comparacoes >= COMPARACOES_MINIMAS &&
      coincidencias / comparacoes >= PROPORCAO_MINIMA_DE_COINCIDENCIA
    ) {
      return true;
    }
  }
  return false;
}

// -----------------------------------------------------------------------------
// Combinador puro dos três sinais.
// -----------------------------------------------------------------------------

export type SinalDeCameraVirtual =
  "rotulo_do_dispositivo" | "capacidades_da_trilha" | "repeticao_de_quadro";

export interface ResultadoDaDeteccaoDeCameraVirtual {
  suspeita: boolean;
  sinais: SinalDeCameraVirtual[];
}

export function avaliarSinaisDeCameraVirtual(entrada: {
  rotuloDoDispositivo?: string;
  capacidadesDaTrilha?: CapacidadesDaTrilha;
  hashesDeQuadro?: readonly string[];
}): ResultadoDaDeteccaoDeCameraVirtual {
  const sinais: SinalDeCameraVirtual[] = [];

  if (
    entrada.rotuloDoDispositivo !== undefined &&
    rotuloIndicaCameraVirtual(entrada.rotuloDoDispositivo)
  ) {
    sinais.push("rotulo_do_dispositivo");
  }
  if (
    entrada.capacidadesDaTrilha !== undefined &&
    capacidadesIndicamSuspeita(entrada.capacidadesDaTrilha)
  ) {
    sinais.push("capacidades_da_trilha");
  }
  if (
    entrada.hashesDeQuadro !== undefined &&
    amostraIndicaRepeticaoDeQuadro(entrada.hashesDeQuadro)
  ) {
    sinais.push("repeticao_de_quadro");
  }

  return { suspeita: sinais.length > 0, sinais };
}

// -----------------------------------------------------------------------------
// Orquestração real (impura — lê câmera e DOM). Não é unitariamente testada;
// coberta pelo teste de integração (Playwright, T9/T10).
// -----------------------------------------------------------------------------

const INTERVALO_DE_AMOSTRAGEM_MS = 300;
const DURACAO_DE_AMOSTRAGEM_MS = 3_000;
const LADO_DO_CANVAS_DE_AMOSTRAGEM = 64;

function esperar(ms: number): Promise<void> {
  return new Promise((resolver) => setTimeout(resolver, ms));
}

async function amostrarHashesDeQuadro(video: HTMLVideoElement): Promise<string[]> {
  const canvas = document.createElement("canvas");
  canvas.width = LADO_DO_CANVAS_DE_AMOSTRAGEM;
  canvas.height = LADO_DO_CANVAS_DE_AMOSTRAGEM;
  const contexto = canvas.getContext("2d", { willReadFrequently: true });
  if (!contexto) return [];

  const hashes: string[] = [];
  const totalDeAmostras = Math.floor(DURACAO_DE_AMOSTRAGEM_MS / INTERVALO_DE_AMOSTRAGEM_MS);
  for (let i = 0; i < totalDeAmostras; i++) {
    contexto.drawImage(video, 0, 0, canvas.width, canvas.height);
    const imagem = contexto.getImageData(0, 0, canvas.width, canvas.height);
    hashes.push(
      calcularHashPerceptual({ largura: imagem.width, altura: imagem.height, dados: imagem.data }),
    );
    if (i < totalDeAmostras - 1) {
      await esperar(INTERVALO_DE_AMOSTRAGEM_MS);
    }
  }
  return hashes;
}

/**
 * Roda os três sinais contra a trilha de vídeo ativa. Chamado uma vez, em
 * paralelo com o desafio de prova de vida (T7), a partir do momento em que a
 * captura (T6) está pronta — 3 segundos de amostragem cabem folgados dentro
 * da janela de até 12 s (3 tentativas × 4 s) do desafio.
 */
export async function monitorarCameraVirtual(
  video: HTMLVideoElement,
  trilha: MediaStreamTrack,
): Promise<ResultadoDaDeteccaoDeCameraVirtual> {
  const capacidades =
    typeof trilha.getCapabilities === "function" ? trilha.getCapabilities() : undefined;
  const configuracoes = typeof trilha.getSettings === "function" ? trilha.getSettings() : undefined;
  const frameRateDaCapacidade = capacidades?.frameRate;
  const frameRateMin = frameRateDaCapacidade?.min ?? configuracoes?.frameRate;
  const frameRateMax = frameRateDaCapacidade?.max ?? configuracoes?.frameRate;
  const capacidadesDaTrilha: CapacidadesDaTrilha = {
    ...(frameRateMin !== undefined ? { frameRateMin } : {}),
    ...(frameRateMax !== undefined ? { frameRateMax } : {}),
  };

  const hashesDeQuadro = await amostrarHashesDeQuadro(video);

  return avaliarSinaisDeCameraVirtual({
    rotuloDoDispositivo: trilha.label,
    capacidadesDaTrilha,
    hashesDeQuadro,
  });
}
