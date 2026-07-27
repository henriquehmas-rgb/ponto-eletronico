import type { MatrizDeTransformacao, PontoDeMarco, QuadroDeDeteccaoFacial } from "./tipos";

/**
 * Prova de vida com desafio aleatório — T7 do PCF F08.
 *
 * Módulo PURO: recebe uma sequência de leituras do `FaceLandmarker` (já
 * extraídas pelo gancho `use-prova-de-vida.ts`, que fala com a câmera e o
 * WASM) e devolve se o desafio foi cumprido — nenhuma chamada de rede aqui
 * (a chamada de rede só acontece quando o colaborador confirma o registro,
 * T9). Critérios de aprovação FIXADOS pelo PCF, não decisão deste módulo:
 * ver `LIMIAR_EAR`, `LIMIAR_GUINADA_GRAUS` e as janelas abaixo.
 */

export type TipoDeDesafio = "piscar_duas_vezes" | "virar_esquerda" | "virar_direita";

/** As três opções fixadas pelo PCF, nesta ordem para `sortearDesafio`. */
export const DESAFIOS_DISPONIVEIS: readonly TipoDeDesafio[] = [
  "piscar_duas_vezes",
  "virar_esquerda",
  "virar_direita",
];

/** Janela do desafio: 4 segundos a partir do instante em que aparece na tela. */
export const JANELA_DO_DESAFIO_MS = 4_000;

/** No máximo 3 tentativas no total (não existe fallback por PIN nesta fase). */
export const MAXIMO_DE_TENTATIVAS = 3;

/** Eye Aspect Ratio abaixo deste limiar conta como "olho fechado". */
export const LIMIAR_EAR = 0.2;

/** Quadros consecutivos com EAR abaixo do limiar para contar uma piscada. */
export const QUADROS_MINIMOS_PARA_PISCADA = 2;

/** "Piscar duas vezes" exige duas piscadas dentro da janela. */
export const PISCADAS_NECESSARIAS = 2;

/** Ângulo de guinada (graus) que caracteriza "virar o rosto". */
export const LIMIAR_GUINADA_GRAUS = 15;

/** Quadros consecutivos sustentando o ângulo para aprovar o giro. */
export const QUADROS_MINIMOS_PARA_GUINADA = 3;

/**
 * Índices dos marcos de cada olho no modelo de 478 pontos do `FaceLandmarker`
 * (mesma topologia do FaceMesh de 468 pontos + íris), na ordem clássica do
 * Eye Aspect Ratio de Soukupová & Čech (2016): [canto-externo,
 * pálpebra-superior-1, pálpebra-superior-2, canto-interno,
 * pálpebra-inferior-2, pálpebra-inferior-1].
 */
const MARCOS_OLHO_DIREITO = [33, 160, 158, 133, 153, 144] as const;
const MARCOS_OLHO_ESQUERDO = [362, 385, 387, 263, 373, 380] as const;

function distancia(a: PontoDeMarco, b: PontoDeMarco): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function earDeUmOlho(pontos: readonly (PontoDeMarco | undefined)[]): number {
  const [p1, p2, p3, p4, p5, p6] = pontos;
  // Dados incompletos: nunca aprova piscada por engano (olho "aberto" por padrão).
  if (!p1 || !p2 || !p3 || !p4 || !p5 || !p6) return 1;
  const horizontal = distancia(p1, p4);
  if (horizontal === 0) return 1;
  return (distancia(p2, p6) + distancia(p3, p5)) / (2 * horizontal);
}

/** Eye Aspect Ratio médio dos dois olhos, a partir dos 478 marcos do quadro. */
export function calcularEar(landmarks: readonly PontoDeMarco[]): number {
  const olhoDireito = MARCOS_OLHO_DIREITO.map((indice) => landmarks[indice]);
  const olhoEsquerdo = MARCOS_OLHO_ESQUERDO.map((indice) => landmarks[indice]);
  return (earDeUmOlho(olhoDireito) + earDeUmOlho(olhoEsquerdo)) / 2;
}

/**
 * Ângulo de guinada (yaw), em graus, extraído da matriz de transformação
 * facial.
 *
 * CONVENÇÃO ASSUMIDA (documentar para QA manual com câmera real — este
 * ambiente de desenvolvimento é headless e não tem como validar
 * empiricamente contra uma câmera de verdade, ver relatório da fase): `data`
 * em ordem de coluna (column-major, o padrão `COLUMN_MAJOR` do proto
 * `MatrixData` do MediaPipe). A terceira coluna da submatriz de rotação
 * (índices 8, 9, 10 do array achatado) é o eixo Z do modelo facial canônico
 * — o vetor "para onde o rosto aponta" — expresso no espaço da câmera. O
 * ângulo horizontal desse vetor em relação ao Z neutro (`atan2(x, z)`) é a
 * guinada. Guinada POSITIVA = rosto virado para a DIREITA do colaborador,
 * assumindo captura NÃO espelhada antes da inferência (um espelhamento do
 * `<video>` em tela, se houver, é só CSS e não afeta os pixels analisados
 * pelo `FaceLandmarker`). Se o QA manual mostrar o sinal invertido, a
 * correção é trocar o sinal aqui — a lógica de desafio abaixo não muda.
 */
export function calcularAnguloDeGuinadaGraus(matriz: MatrizDeTransformacao): number {
  const x = matriz.data[8] ?? 0;
  const z = matriz.data[10] ?? 1;
  return (Math.atan2(x, z) * 180) / Math.PI;
}

/** Sorteia um dos três desafios. Injeção de `gerador` só para teste determinístico. */
export function sortearDesafio(gerador: () => number = Math.random): TipoDeDesafio {
  const indiceBruto = Math.floor(gerador() * DESAFIOS_DISPONIVEIS.length);
  const indice = Math.min(Math.max(indiceBruto, 0), DESAFIOS_DISPONIVEIS.length - 1);
  return DESAFIOS_DISPONIVEIS[indice] ?? "piscar_duas_vezes";
}

export interface EvidenciaDoDesafio {
  desafio: TipoDeDesafio;
  quadrosAnalisados: number;
  duracaoMs: number;
  piscadasDetectadas?: number;
  anguloMaximoGraus?: number;
}

export interface ResultadoDaProvaDeVida {
  aprovado: boolean;
  metodo: "desafio_ativo";
  motivoReprovacao?: "tempo_esgotado" | "movimento_insuficiente";
  evidencia: EvidenciaDoDesafio;
}

/**
 * Avalia uma sequência completa de quadros contra um desafio.
 *
 * Puro e determinístico: a mesma sequência sempre devolve o mesmo resultado
 * — é isto que torna o teste unitário possível sem capturar webcam real.
 * `quadros` deve cobrir, no máximo, `janelaMs` a partir do primeiro quadro;
 * quadros além da janela são ignorados (o gancho que alimenta este módulo em
 * tempo real já para de empurrar quadros quando a janela expira).
 */
export function avaliarSequenciaDeQuadros(
  desafio: TipoDeDesafio,
  quadros: readonly QuadroDeDeteccaoFacial[],
  janelaMs: number = JANELA_DO_DESAFIO_MS,
): ResultadoDaProvaDeVida {
  const primeiroQuadro = quadros[0];
  if (!primeiroQuadro) {
    return {
      aprovado: false,
      metodo: "desafio_ativo",
      motivoReprovacao: "movimento_insuficiente",
      evidencia: { desafio, quadrosAnalisados: 0, duracaoMs: 0 },
    };
  }
  const inicioMs = primeiroQuadro.timestampMs;

  let quadrosFechado = 0;
  let emFechamento = false;
  let piscadasDetectadas = 0;
  let progressoDePiscadaDetectado = false;

  let quadrosNoAlvo = 0;
  let anguloMaximoNaDirecao = 0;
  let progressoDeGuinadaDetectado = false;

  let aprovado = false;
  let ultimoTimestamp = inicioMs;
  let quadrosAnalisados = 0;

  for (const quadro of quadros) {
    if (quadro.timestampMs - inicioMs > janelaMs) break;
    ultimoTimestamp = quadro.timestampMs;
    quadrosAnalisados += 1;

    if (desafio === "piscar_duas_vezes") {
      const ear = quadro.landmarks ? calcularEar(quadro.landmarks) : 1;
      if (ear < LIMIAR_EAR) {
        quadrosFechado += 1;
        progressoDePiscadaDetectado = true;
        if (quadrosFechado >= QUADROS_MINIMOS_PARA_PISCADA) emFechamento = true;
      } else {
        if (emFechamento) piscadasDetectadas += 1;
        quadrosFechado = 0;
        emFechamento = false;
      }
      if (piscadasDetectadas >= PISCADAS_NECESSARIAS) {
        aprovado = true;
        break;
      }
    } else {
      const naDirecaoDireita = desafio === "virar_direita";
      const guinada = quadro.matrizTransformacaoFacial
        ? calcularAnguloDeGuinadaGraus(quadro.matrizTransformacaoFacial)
        : 0;
      anguloMaximoNaDirecao = naDirecaoDireita
        ? Math.max(anguloMaximoNaDirecao, guinada)
        : Math.min(anguloMaximoNaDirecao, guinada);

      const atingiuLimiar = naDirecaoDireita
        ? guinada >= LIMIAR_GUINADA_GRAUS
        : guinada <= -LIMIAR_GUINADA_GRAUS;
      if (atingiuLimiar) {
        progressoDeGuinadaDetectado = true;
        quadrosNoAlvo += 1;
      } else {
        quadrosNoAlvo = 0;
      }
      if (quadrosNoAlvo >= QUADROS_MINIMOS_PARA_GUINADA) {
        aprovado = true;
        break;
      }
    }
  }

  const evidencia: EvidenciaDoDesafio = {
    desafio,
    quadrosAnalisados,
    duracaoMs: ultimoTimestamp - inicioMs,
    ...(desafio === "piscar_duas_vezes"
      ? { piscadasDetectadas }
      : { anguloMaximoGraus: anguloMaximoNaDirecao }),
  };

  if (aprovado) {
    return { aprovado: true, metodo: "desafio_ativo", evidencia };
  }

  const progressoDetectado =
    desafio === "piscar_duas_vezes" ? progressoDePiscadaDetectado : progressoDeGuinadaDetectado;

  return {
    aprovado: false,
    metodo: "desafio_ativo",
    motivoReprovacao: progressoDetectado ? "tempo_esgotado" : "movimento_insuficiente",
    evidencia,
  };
}
