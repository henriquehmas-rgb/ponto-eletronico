/**
 * Tipos compartilhados de `lib/deteccao/**` — T7/T8 do PCF F08.
 *
 * Estruturalmente compatíveis com os tipos que `@mediapipe/tasks-vision`
 * devolve (`NormalizedLandmark`, `Matrix`, `FaceLandmarkerResult`), mas
 * declarados aqui, sem importar o pacote: os módulos de `lib/deteccao/**`
 * são puros (nenhum I/O, nenhuma dependência de WASM/DOM) e os testes
 * unitários usam sequências SINTÉTICAS (fixadas no código do teste, nunca
 * capturadas de webcam real — T7, "pronto quando"). Um valor real do
 * FaceLandmarker é estruturalmente atribuível a estes tipos (campos a mais,
 * como `visibility`/`presence`, não quebram a atribuição).
 */

/** Marco facial normalizado (0..1 em relação à imagem). */
export interface PontoDeMarco {
  x: number;
  y: number;
  z?: number;
}

/**
 * Matriz de transformação facial 4x4, no formato de
 * `facialTransformationMatrixes` do `FaceLandmarker`: `data` é o array
 * achatado em ORDEM DE COLUNA (column-major) — mesma convenção padrão
 * (`COLUMN_MAJOR`) do proto `MatrixData` usado internamente pelo MediaPipe.
 */
export interface MatrizDeTransformacao {
  rows: number;
  columns: number;
  data: number[];
}

/** Leitura de um quadro de vídeo já processado pelo `FaceLandmarker`. */
export interface QuadroDeDeteccaoFacial {
  timestampMs: number;
  /** `null` quando nenhum rosto foi detectado neste quadro. */
  landmarks: PontoDeMarco[] | null;
  matrizTransformacaoFacial: MatrizDeTransformacao | null;
}
