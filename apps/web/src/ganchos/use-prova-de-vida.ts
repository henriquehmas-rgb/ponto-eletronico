"use client";

import { useEffect, useRef, useState } from "react";

import {
  avaliarSequenciaDeQuadros,
  JANELA_DO_DESAFIO_MS,
  MAXIMO_DE_TENTATIVAS,
  sortearDesafio,
  type ResultadoDaProvaDeVida,
  type TipoDeDesafio,
} from "@/lib/deteccao/prova-de-vida";
import type { QuadroDeDeteccaoFacial } from "@/lib/deteccao/tipos";

/**
 * Prova de vida com desafio aleatório — T7 do PCF F08 (gancho).
 *
 * Fala com a câmera (via o `<video>` já aberto por `useCapturaWebcam`, T6) e
 * com o `FaceLandmarker` (`@mediapipe/tasks-vision`, WASM auto-hospedado em
 * `public/mediapipe/**`/`public/modelos/**` — nunca o CDN do Google, §9,
 * carregado por `import()` dinâmico só quando este gancho é usado, ou seja,
 * só quando `/eu/registrar` monta). A decisão de aprovado/reprovado é
 * SEMPRE do módulo puro `lib/deteccao/prova-de-vida.ts` (testado com
 * sequências sintéticas); este gancho só alimenta quadros e administra
 * tentativas/tempo.
 *
 * NENHUMA chamada de rede acontece aqui — só quando o colaborador confirma
 * o registro (T9) é que `POST /v1/marcacoes` é chamado.
 */

const CAMINHO_DO_FILESET_WASM = "/mediapipe/wasm";
const CAMINHO_DO_MODELO = "/modelos/face_landmarker.task";

/** Pausa entre uma tentativa reprovada (não final) e o início da próxima — só para dar tempo do colaborador ler o aviso. */
const PAUSA_ENTRE_TENTATIVAS_MS = 1_500;

export type SituacaoDaProvaDeVida =
  | "carregando_modelo"
  | "em_andamento"
  | "aprovado"
  | "reprovado_tentativa"
  | "reprovado_final"
  | "erro";

export interface UsoDeProvaDeVida {
  situacao: SituacaoDaProvaDeVida;
  desafio: TipoDeDesafio | null;
  tentativa: number;
  segundosRestantes: number;
  resultado: ResultadoDaProvaDeVida | null;
  mensagemDeErro: string | null;
}

/** Ponte mínima com o `FaceLandmarker` — isolada para poder ser trocada em teste (`opcoes.criarDetector`). */
export interface DetectorFacial {
  detectarQuadro: (
    video: HTMLVideoElement,
    timestampMs: number,
  ) => Pick<QuadroDeDeteccaoFacial, "landmarks" | "matrizTransformacaoFacial">;
  liberar: () => void;
}

async function criarDetectorFacial(): Promise<DetectorFacial> {
  const { FaceLandmarker, FilesetResolver } = await import("@mediapipe/tasks-vision");
  const fileset = await FilesetResolver.forVisionTasks(CAMINHO_DO_FILESET_WASM);
  const faceLandmarker = await FaceLandmarker.createFromOptions(fileset, {
    // `delegate: "CPU"` de propósito: o delegate "GPU" (padrão da lib) exige
    // um contexto WebGL2, indisponível em navegadores sem aceleração de
    // hardware (comum em máquinas corporativas travadas e em execução
    // headless de CI/E2E) — o CPU funciona em qualquer navegador, a um custo
    // de desempenho aceitável para um desafio que já orça vários segundos.
    baseOptions: { modelAssetPath: CAMINHO_DO_MODELO, delegate: "CPU" },
    runningMode: "VIDEO",
    numFaces: 1,
    outputFaceBlendshapes: false,
    outputFacialTransformationMatrixes: true,
  });

  return {
    detectarQuadro(video, timestampMs) {
      const resultado = faceLandmarker.detectForVideo(video, timestampMs);
      const landmarks = resultado.faceLandmarks[0];
      const matriz = resultado.facialTransformationMatrixes[0];
      return {
        landmarks: landmarks
          ? landmarks.map((ponto) => ({ x: ponto.x, y: ponto.y, z: ponto.z }))
          : null,
        matrizTransformacaoFacial: matriz
          ? { rows: matriz.rows, columns: matriz.columns, data: matriz.data }
          : null,
      };
    },
    liberar() {
      faceLandmarker.close();
    },
  };
}

export interface OpcoesDeProvaDeVida {
  /** Injeção só para teste — produção sempre usa `criarDetectorFacial` (import dinâmico do WASM). */
  criarDetector?: () => Promise<DetectorFacial>;
  gerarAleatorio?: () => number;
  agora?: () => number;
  pausaEntreTentativasMs?: number;
  /** Injeção só para teste — produção sempre usa `requestAnimationFrame`. */
  agendarProximoQuadro?: (callback: () => void) => number;
  cancelarQuadroAgendado?: (identificador: number) => void;
}

/**
 * @param video Elemento de vídeo já com a `MediaStream` da câmera (T6). `null` enquanto a captura não está pronta.
 * @param ativo Só roda a detecção enquanto `true` — controlado pelo fluxo de registro (T9): evita
 *   gastar CPU/bateria antes da hora e depois de aprovado/reprovado definitivamente.
 */
export function useProvaDeVida(
  video: HTMLVideoElement | null,
  ativo: boolean,
  opcoes: OpcoesDeProvaDeVida = {},
): UsoDeProvaDeVida {
  const criarDetector = opcoes.criarDetector ?? criarDetectorFacial;
  const gerarAleatorio = opcoes.gerarAleatorio ?? Math.random;
  const agora = opcoes.agora ?? (() => performance.now());
  const pausaEntreTentativasMs = opcoes.pausaEntreTentativasMs ?? PAUSA_ENTRE_TENTATIVAS_MS;
  // Envolvidos em arrow function (não a referência nua) para não desanexar o
  // `this` esperado por `window.requestAnimationFrame`/`cancelAnimationFrame`
  // em navegadores que exigem a chamada no objeto original.
  const agendarProximoQuadro =
    opcoes.agendarProximoQuadro ?? ((retorno: () => void) => requestAnimationFrame(retorno));
  const cancelarQuadroAgendado =
    opcoes.cancelarQuadroAgendado ??
    ((identificador: number) => cancelAnimationFrame(identificador));

  const [situacao, setSituacao] = useState<SituacaoDaProvaDeVida>("carregando_modelo");
  const [desafio, setDesafio] = useState<TipoDeDesafio | null>(null);
  const [tentativa, setTentativa] = useState(1);
  const [segundosRestantes, setSegundosRestantes] = useState(
    Math.ceil(JANELA_DO_DESAFIO_MS / 1000),
  );
  const [resultado, setResultado] = useState<ResultadoDaProvaDeVida | null>(null);
  const [mensagemDeErro, setMensagemDeErro] = useState<string | null>(null);

  // Refs: fonte da verdade para o laço de detecção (não esperam re-render).
  // O estado acima existe só para a UI ler o valor atual.
  const quadrosRef = useRef<QuadroDeDeteccaoFacial[]>([]);
  const desafioRef = useRef<TipoDeDesafio | null>(null);
  const tentativaRef = useRef(1);
  const inicioDaTentativaRef = useRef(0);
  const finalizadoRef = useRef(false);
  const rafRef = useRef<number | null>(null);
  const pausaRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!ativo || !video) return;

    let cancelado = false;
    let detector: DetectorFacial | null = null;

    function iniciarTentativa(numero: number): void {
      const novoDesafio = sortearDesafio(gerarAleatorio);
      desafioRef.current = novoDesafio;
      tentativaRef.current = numero;
      quadrosRef.current = [];
      inicioDaTentativaRef.current = agora();
      setDesafio(novoDesafio);
      setTentativa(numero);
      setResultado(null);
      setSegundosRestantes(Math.ceil(JANELA_DO_DESAFIO_MS / 1000));
      setSituacao("em_andamento");
    }

    function laco(): void {
      if (cancelado || !detector || !video || finalizadoRef.current) return;
      const detectorAtivo = detector;

      const timestampMs = agora();
      const decorrido = timestampMs - inicioDaTentativaRef.current;
      const desafioAtual = desafioRef.current;

      if (desafioAtual) {
        // `detectarQuadro` pode lançar em quadros específicos (observado com
        // o padrão sintético do Chromium em `--use-fake-device-for-media-
        // stream`, sem rosto real: o MediaPipe às vezes falha internamente
        // ao montar a região de interesse quando não encontra nada
        // parecido com um rosto). Um quadro que falha é tratado como
        // "nenhum rosto neste quadro" (não conta como piscada nem giro) —
        // nunca deixa o laço inteiro morrer silenciosamente e travar a
        // tela no desafio para sempre.
        let leitura: ReturnType<DetectorFacial["detectarQuadro"]>;
        try {
          leitura = detectorAtivo.detectarQuadro(video, timestampMs);
        } catch {
          leitura = { landmarks: null, matrizTransformacaoFacial: null };
        }
        quadrosRef.current = [
          ...quadrosRef.current,
          {
            timestampMs,
            landmarks: leitura.landmarks,
            matrizTransformacaoFacial: leitura.matrizTransformacaoFacial,
          },
        ];

        setSegundosRestantes(Math.max(0, Math.ceil((JANELA_DO_DESAFIO_MS - decorrido) / 1000)));

        const avaliacao = avaliarSequenciaDeQuadros(
          desafioAtual,
          quadrosRef.current,
          JANELA_DO_DESAFIO_MS,
        );

        if (avaliacao.aprovado) {
          finalizadoRef.current = true;
          setResultado(avaliacao);
          setSituacao("aprovado");
          return;
        }

        if (decorrido >= JANELA_DO_DESAFIO_MS) {
          setResultado(avaliacao);

          if (tentativaRef.current >= MAXIMO_DE_TENTATIVAS) {
            finalizadoRef.current = true;
            setSituacao("reprovado_final");
            return;
          }

          setSituacao("reprovado_tentativa");
          pausaRef.current = setTimeout(() => {
            if (cancelado) return;
            iniciarTentativa(tentativaRef.current + 1);
            rafRef.current = agendarProximoQuadro(laco);
          }, pausaEntreTentativasMs);
          return;
        }
      }

      if (!cancelado) {
        rafRef.current = agendarProximoQuadro(laco);
      }
    }

    async function preparar(): Promise<void> {
      setSituacao("carregando_modelo");
      try {
        const detectorCriado = await criarDetector();
        if (cancelado) {
          detectorCriado.liberar();
          return;
        }
        detector = detectorCriado;
        iniciarTentativa(1);
        rafRef.current = agendarProximoQuadro(laco);
      } catch (erro) {
        if (cancelado) return;
        setSituacao("erro");
        setMensagemDeErro(
          erro instanceof Error
            ? erro.message
            : "Não foi possível carregar o modelo de prova de vida.",
        );
      }
    }

    void preparar();

    return () => {
      cancelado = true;
      if (rafRef.current !== null) cancelarQuadroAgendado(rafRef.current);
      if (pausaRef.current !== null) clearTimeout(pausaRef.current);
      detector?.liberar();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `video`/`ativo` são os únicos gatilhos de propósito; funções injetadas por `opcoes` não devem reiniciar o laço a cada render.
  }, [video, ativo]);

  return { situacao, desafio, tentativa, segundosRestantes, resultado, mensagemDeErro };
}
