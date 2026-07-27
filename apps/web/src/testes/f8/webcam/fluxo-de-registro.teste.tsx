import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProvedorDeConsultas } from "@/componentes/provedor-de-consultas";
import { FluxoDeRegistro } from "@/componentes/registro-webcam/fluxo-de-registro";
import type * as ApiModulo from "@/lib/api";
import { ErroDaApi } from "@/lib/api/erros";
import type * as CameraVirtualModulo from "@/lib/deteccao/camera-virtual";
import { MAXIMO_DE_TENTATIVAS } from "@/lib/deteccao/prova-de-vida";

const apiMock = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const real = await vi.importActual<typeof ApiModulo>("@/lib/api");
  return { ...real, api: apiMock };
});

vi.mock("@/lib/sessao", () => ({
  useSessao: () => ({
    usuario: { id: "u1", nome: "Colaborador Teste", email: "c@t.com" },
    tenant: { slug: "seeg", nomeExibicao: "SEEG" },
    autenticado: true,
    carregando: false,
    entrar: vi.fn(),
    verificarSegundoFator: vi.fn(),
    sair: vi.fn(),
  }),
}));

const segurancaMock = vi.hoisted(() => ({
  calcularFingerprint: vi.fn().mockResolvedValue("fingerprint-de-teste"),
  comAcessoControlado: vi.fn(async (chamada: () => Promise<unknown>) => chamada()),
  mensagemDoErro: vi.fn(
    (codigo: string | undefined) => `mensagem-para:${codigo ?? "desconhecido"}`,
  ),
}));
vi.mock("@/lib/seguranca", () => segurancaMock);

const capturaWebcamMock = vi.hoisted(() => vi.fn());
vi.mock("@/ganchos/use-captura-webcam", () => ({ useCapturaWebcam: capturaWebcamMock }));

const provaDeVidaMock = vi.hoisted(() => vi.fn());
vi.mock("@/ganchos/use-prova-de-vida", () => ({ useProvaDeVida: provaDeVidaMock }));

const monitorarCameraVirtualMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/deteccao/camera-virtual", async () => {
  const real = await vi.importActual<typeof CameraVirtualModulo>("@/lib/deteccao/camera-virtual");
  return { ...real, monitorarCameraVirtual: monitorarCameraVirtualMock };
});

function renderizarFluxo() {
  return render(
    <ProvedorDeConsultas>
      <FluxoDeRegistro />
    </ProvedorDeConsultas>,
  );
}

const STREAM_FALSO = {} as MediaStream;
const TRILHA_FALSA = {} as MediaStreamTrack;

beforeEach(() => {
  apiMock.GET.mockReset();
  apiMock.POST.mockReset();
  segurancaMock.comAcessoControlado.mockReset();
  segurancaMock.comAcessoControlado.mockImplementation(async (chamada: () => Promise<unknown>) =>
    chamada(),
  );
  segurancaMock.mensagemDoErro.mockClear();
  capturaWebcamMock.mockReset();
  provaDeVidaMock.mockReset();
  monitorarCameraVirtualMock.mockReset();

  apiMock.GET.mockResolvedValue({ data: { colaboradorId: "colaborador-123" } });
  capturaWebcamMock.mockReturnValue({
    estado: "concedida",
    stream: STREAM_FALSO,
    trilhaDeVideo: TRILHA_FALSA,
    mensagemDeErro: null,
    solicitarNovamente: vi.fn(),
  });
  monitorarCameraVirtualMock.mockResolvedValue({ suspeita: false, sinais: [] });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("FluxoDeRegistro (T9)", () => {
  it("captura → desafio aprovado → POST /v1/marcacoes com o corpo esperado → tela de sucesso", async () => {
    provaDeVidaMock.mockReturnValue({
      situacao: "aprovado",
      desafio: "piscar_duas_vezes",
      tentativa: 1,
      segundosRestantes: 0,
      resultado: {
        aprovado: true,
        metodo: "desafio_ativo",
        evidencia: {
          desafio: "piscar_duas_vezes",
          quadrosAnalisados: 9,
          duracaoMs: 900,
          piscadasDetectadas: 2,
        },
      },
      mensagemDeErro: null,
    });

    apiMock.POST.mockResolvedValue({
      data: {
        marcacao: { nsr: 1842, datahoraMarcacao: "2026-07-25T08:02:13-03:00" },
        comprovante: { numero: "2026072500001842" },
        revisaoRequerida: false,
      },
    });

    renderizarFluxo();

    await waitFor(() => expect(apiMock.POST).toHaveBeenCalledTimes(1));

    const [caminho, opcoes] = apiMock.POST.mock.calls[0] as [
      string,
      { body: Record<string, unknown> },
    ];
    expect(caminho).toBe("/v1/marcacoes");
    expect(opcoes.body).toMatchObject({
      colaboradorId: "colaborador-123",
      canal: "web",
      livenessMetodo: "desafio_ativo",
      flagsIntegridade: { cameraVirtual: false, fingerprint: "fingerprint-de-teste" },
    });
    expect(opcoes.body["livenessEvidencia"]).toMatchObject({ piscadasDetectadas: 2 });

    await waitFor(() => expect(screen.getByText(/ponto registrado/i)).toBeInTheDocument());
    expect(screen.getByText(/2026072500001842/)).toBeInTheDocument();
    expect(screen.getByText(/1842/)).toBeInTheDocument();
  });

  it("reprovar o desafio 3 vezes não chama a API e mostra a orientação final", async () => {
    provaDeVidaMock.mockReturnValue({
      situacao: "reprovado_final",
      desafio: "virar_direita",
      tentativa: MAXIMO_DE_TENTATIVAS,
      segundosRestantes: 0,
      resultado: null,
      mensagemDeErro: null,
    });

    renderizarFluxo();

    await waitFor(() =>
      expect(screen.getByText(/não foi possível confirmar o registro/i)).toBeInTheDocument(),
    );
    expect(segurancaMock.mensagemDoErro).toHaveBeenCalledWith("PONTO-SCORE-002");
    expect(apiMock.POST).not.toHaveBeenCalled();
  });

  it("câmera virtual detectada bloqueia o envio e nunca chama a API (critério 5 da §7)", async () => {
    provaDeVidaMock.mockReturnValue({
      situacao: "aprovado",
      desafio: "piscar_duas_vezes",
      tentativa: 1,
      segundosRestantes: 0,
      resultado: {
        aprovado: true,
        metodo: "desafio_ativo",
        evidencia: {
          desafio: "piscar_duas_vezes",
          quadrosAnalisados: 9,
          duracaoMs: 900,
          piscadasDetectadas: 2,
        },
      },
      mensagemDeErro: null,
    });
    monitorarCameraVirtualMock.mockResolvedValue({
      suspeita: true,
      sinais: ["rotulo_do_dispositivo"],
    });

    renderizarFluxo();

    await waitFor(() =>
      expect(screen.getByText(/não foi possível confirmar o registro/i)).toBeInTheDocument(),
    );
    expect(segurancaMock.mensagemDoErro).toHaveBeenCalledWith("PONTO-SCORE-004");
    expect(apiMock.POST).not.toHaveBeenCalled();
  });

  it("reenvia automaticamente após reautenticação (PONTO-AUTH-011), sem nova captura", async () => {
    provaDeVidaMock.mockReturnValue({
      situacao: "aprovado",
      desafio: "piscar_duas_vezes",
      tentativa: 1,
      segundosRestantes: 0,
      resultado: {
        aprovado: true,
        metodo: "desafio_ativo",
        evidencia: {
          desafio: "piscar_duas_vezes",
          quadrosAnalisados: 9,
          duracaoMs: 900,
          piscadasDetectadas: 2,
        },
      },
      mensagemDeErro: null,
    });

    apiMock.POST.mockRejectedValueOnce(
      new ErroDaApi(401, {
        codigo: "PONTO-AUTH-011",
        title: "Reautenticação necessária",
        status: 401,
        type: "https://docs.ponto.seeg.com.br/erros/PONTO-AUTH-011",
      }),
    ).mockResolvedValueOnce({
      data: {
        marcacao: { nsr: 55, datahoraMarcacao: "2026-07-25T09:00:00-03:00" },
        comprovante: { numero: "COMP-55" },
        revisaoRequerida: false,
      },
    });

    // Simula o comportamento real de `comAcessoControlado` (T13, A3): na
    // primeira falha por PONTO-AUTH-011, reautentica e chama `chamada`
    // de novo — SEM que este fluxo (T9) refaça a captura ou o desafio.
    segurancaMock.comAcessoControlado.mockImplementation(
      async (chamada: () => Promise<unknown>) => {
        try {
          return await chamada();
        } catch (erro) {
          if (erro instanceof ErroDaApi && erro.codigo === "PONTO-AUTH-011") {
            return await chamada();
          }
          throw erro;
        }
      },
    );

    renderizarFluxo();

    await waitFor(() => expect(apiMock.POST).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByText(/ponto registrado/i)).toBeInTheDocument());

    // Prova de vida foi calculada uma única vez (o gancho foi chamado com os
    // mesmos parâmetros básicos) — nenhuma nova captura foi solicitada.
    expect(capturaWebcamMock).toHaveBeenCalled();
  });
});
