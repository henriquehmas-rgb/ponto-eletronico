import { describe, expect, it } from "vitest";

import {
  amostraIndicaRepeticaoDeQuadro,
  avaliarSinaisDeCameraVirtual,
  calcularHashPerceptual,
  capacidadesIndicamSuspeita,
  rotuloIndicaCameraVirtual,
  ROTULOS_DE_CAMERA_VIRTUAL_CONHECIDOS,
} from "./camera-virtual";
import type { DadosDeImagemRgba } from "./camera-virtual";

describe("rotuloIndicaCameraVirtual — sinal 1", () => {
  it.each([
    "OBS Virtual Camera",
    "obs-camera",
    "DroidCam",
    "ManyCam",
    "Snap Camera",
    "CamTwist",
    "XSplit VCam",
    "Iriun Webcam",
    "EpocCam",
  ])("sinaliza o rótulo de fabricante conhecido: %s", (rotulo) => {
    expect(rotuloIndicaCameraVirtual(rotulo)).toBe(true);
  });

  it.each(["HD WebCam", "FaceTime HD Camera", "Integrated Webcam", "Logitech BRIO"])(
    "não sinaliza uma webcam física comum: %s",
    (rotulo) => {
      expect(rotuloIndicaCameraVirtual(rotulo)).toBe(false);
    },
  );

  it("cobre pelo menos um rótulo de cada fabricante da lista mínima do PCF", () => {
    expect(ROTULOS_DE_CAMERA_VIRTUAL_CONHECIDOS.length).toBeGreaterThanOrEqual(9);
  });
});

describe("capacidadesIndicamSuspeita — sinal 2", () => {
  it("não sinaliza quando a trilha anuncia uma faixa (min !== max)", () => {
    expect(capacidadesIndicamSuspeita({ frameRateMin: 15, frameRateMax: 30 })).toBe(false);
  });

  it("não sinaliza um valor fixo dentro do padrão típico de webcam física (30 fps)", () => {
    expect(capacidadesIndicamSuspeita({ frameRateMin: 30, frameRateMax: 30 })).toBe(false);
  });

  it("sinaliza um valor fixo fora do padrão típico (ex.: 12 fps exato, fora das faixas típicas)", () => {
    expect(capacidadesIndicamSuspeita({ frameRateMin: 12, frameRateMax: 12 })).toBe(true);
  });

  it("não sinaliza quando a informação de frameRate está ausente", () => {
    expect(capacidadesIndicamSuspeita({})).toBe(false);
  });
});

function imagemSolida(tom: number): DadosDeImagemRgba {
  const largura = 32;
  const altura = 32;
  const dados = new Uint8ClampedArray(largura * altura * 4);
  for (let i = 0; i < dados.length; i += 4) {
    dados[i] = tom;
    dados[i + 1] = tom;
    dados[i + 2] = tom;
    dados[i + 3] = 255;
  }
  return { largura, altura, dados };
}

function imagemComGradiente(deslocamento: number): DadosDeImagemRgba {
  const largura = 32;
  const altura = 32;
  const dados = new Uint8ClampedArray(largura * altura * 4);
  for (let y = 0; y < altura; y++) {
    for (let x = 0; x < largura; x++) {
      const indice = (y * largura + x) * 4;
      const tom = (x * 8 + deslocamento) % 256;
      dados[indice] = tom;
      dados[indice + 1] = tom;
      dados[indice + 2] = tom;
      dados[indice + 3] = 255;
    }
  }
  return { largura, altura, dados };
}

describe("calcularHashPerceptual — base do sinal 3", () => {
  it("produz o mesmo hash para duas imagens idênticas", () => {
    expect(calcularHashPerceptual(imagemSolida(120))).toBe(
      calcularHashPerceptual(imagemSolida(120)),
    );
  });

  it("produz hashes diferentes para imagens visualmente diferentes", () => {
    expect(calcularHashPerceptual(imagemComGradiente(0))).not.toBe(
      calcularHashPerceptual(imagemComGradiente(120)),
    );
  });

  it("devolve uma string hexadecimal de 64 dígitos (256 bits)", () => {
    expect(calcularHashPerceptual(imagemSolida(80))).toMatch(/^[0-9a-f]{64}$/);
  });
});

describe("amostraIndicaRepeticaoDeQuadro — sinal 3", () => {
  it("sinaliza uma sequência de quadros idênticos (vídeo em loop)", () => {
    const hash = calcularHashPerceptual(imagemComGradiente(10));
    const hashes = Array.from({ length: 10 }, () => hash);
    expect(amostraIndicaRepeticaoDeQuadro(hashes)).toBe(true);
  });

  it("sinaliza um loop curto com período regular (ex.: repete a cada 3 quadros)", () => {
    const ciclo = [
      calcularHashPerceptual(imagemComGradiente(0)),
      calcularHashPerceptual(imagemComGradiente(50)),
      calcularHashPerceptual(imagemComGradiente(100)),
    ];
    const hashes = Array.from({ length: 12 }, (_, indice) => ciclo[indice % ciclo.length] ?? "");
    expect(amostraIndicaRepeticaoDeQuadro(hashes)).toBe(true);
  });

  it("não sinaliza uma sequência de quadros todos diferentes (rosto vivo)", () => {
    const hashes = Array.from({ length: 10 }, (_, indice) =>
      calcularHashPerceptual(imagemComGradiente(indice * 23)),
    );
    expect(amostraIndicaRepeticaoDeQuadro(hashes)).toBe(false);
  });

  it("não sinaliza amostras curtas demais para inferir periodicidade", () => {
    expect(amostraIndicaRepeticaoDeQuadro(["a", "a", "a"])).toBe(false);
  });
});

describe("avaliarSinaisDeCameraVirtual — combinador", () => {
  it("marca suspeita quando qualquer um dos três sinais é positivo", () => {
    expect(
      avaliarSinaisDeCameraVirtual({ rotuloDoDispositivo: "OBS Virtual Camera" }).suspeita,
    ).toBe(true);
    expect(
      avaliarSinaisDeCameraVirtual({ capacidadesDaTrilha: { frameRateMin: 12, frameRateMax: 12 } })
        .suspeita,
    ).toBe(true);
  });

  it("não marca suspeita quando nenhum sinal está presente ou todos são negativos", () => {
    const resultado = avaliarSinaisDeCameraVirtual({
      rotuloDoDispositivo: "HD WebCam",
      capacidadesDaTrilha: { frameRateMin: 24, frameRateMax: 60 },
    });
    expect(resultado.suspeita).toBe(false);
    expect(resultado.sinais).toHaveLength(0);
  });

  it("lista todos os sinais positivos, não só o primeiro", () => {
    const resultado = avaliarSinaisDeCameraVirtual({
      rotuloDoDispositivo: "droidcam",
      capacidadesDaTrilha: { frameRateMin: 12, frameRateMax: 12 },
    });
    expect(resultado.sinais).toEqual(
      expect.arrayContaining(["rotulo_do_dispositivo", "capacidades_da_trilha"]),
    );
  });
});
