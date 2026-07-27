"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { Alerta, AlertaDescricao, AlertaTitulo } from "@/componentes/ui/alert";
import { Esqueleto } from "@/componentes/ui/skeleton";
import {
  monitorarCameraVirtual,
  type ResultadoDaDeteccaoDeCameraVirtual,
} from "@/lib/deteccao/camera-virtual";
import { useCapturaWebcam } from "@/ganchos/use-captura-webcam";
import { useProvaDeVida } from "@/ganchos/use-prova-de-vida";
import { api, ehErroDaApi, type Esquema } from "@/lib/api";
import { calcularFingerprint, comAcessoControlado, mensagemDoErro } from "@/lib/seguranca";
import { useSessao } from "@/lib/sessao";

import { CapturaDeVideo } from "./captura-de-video";
import { ConfirmacaoDeRegistro, type VarianteDeConfirmacao } from "./confirmacao-de-registro";
import { DesafioDeProvaDeVida } from "./desafio-de-prova-de-vida";

/**
 * Fluxo de registro de ponto por webcam — T9 do PCF F08.
 *
 * Orquestra captura ao vivo (T6) → desafio de prova de vida (T7) → checagem
 * de câmera virtual (T8) → `POST /v1/marcacoes` via `comAcessoControlado`
 * (T13, A3 — que já cuida de reautenticação, T12) → um dos três desfechos
 * (`ConfirmacaoDeRegistro`, T9). Cada tentativa usa uma chamada nova do
 * cliente `api`, que já gera `Idempotency-Key` por chamada — nada aqui reusa
 * uma chave manualmente (`src/lib/api/cliente.ts`, já existente).
 */

/** `datahoraMarcacao` já vem com o fuso do tenant aplicado pelo servidor
 *  (ex.: "2026-07-25T08:02:13-03:00"): recorta "HH:MM" direto da string, sem
 *  reconverter fuso horário no navegador. */
function formatarHorario(iso: string): string {
  return iso.slice(11, 16);
}

function capturarFotoBase64(video: HTMLVideoElement): string {
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;
  const contexto = canvas.getContext("2d");
  if (!contexto) return "";
  contexto.drawImage(video, 0, 0, canvas.width, canvas.height);
  const dataUrl = canvas.toDataURL("image/jpeg", 0.85);
  const indiceDaVirgula = dataUrl.indexOf(",");
  return indiceDaVirgula === -1 ? dataUrl : dataUrl.slice(indiceDaVirgula + 1);
}

interface DesfechoDeSucesso {
  variante: Extract<VarianteDeConfirmacao, "sucesso" | "sucesso_com_revisao">;
  numeroDoComprovante: string;
  nsr: number;
  horario: string;
}

export function FluxoDeRegistro() {
  const { autenticado } = useSessao();

  // `useSessao()` (contrato fixado, §2 do PCF) não expõe `colaboradorId` — só
  // a F9b precisa de RBAC granular e já faz sua própria chamada a
  // `obterSessaoAtual`; esta tela precisa do mesmo dado por um motivo
  // diferente (identificar QUEM está registrando o próprio ponto), então
  // repete a mesma chamada padrão, por cima de `autenticado`, sem exigir
  // mudança na forma do módulo de sessão.
  const consultaDoColaborador = useQuery({
    queryKey: ["f8", "registro-webcam", "sessao-atual"],
    queryFn: async () => {
      const resposta = await api.GET("/v1/auth/sessao");
      if (!resposta.data) throw new Error("Sessão atual sem corpo de resposta.");
      return resposta.data;
    },
    enabled: autenticado,
    staleTime: 60_000,
  });

  const captura = useCapturaWebcam();
  const [video, setVideo] = useState<HTMLVideoElement | null>(null);

  const [deteccaoCameraVirtual, setDeteccaoCameraVirtual] =
    useState<ResultadoDaDeteccaoDeCameraVirtual | null>(null);
  useEffect(() => {
    if (!video || !captura.trilhaDeVideo) return;
    let cancelado = false;
    monitorarCameraVirtual(video, captura.trilhaDeVideo)
      .then((resultado) => {
        if (!cancelado) setDeteccaoCameraVirtual(resultado);
      })
      .catch(() => {
        // Sinal secundário indisponível (ex.: `getImageData` bloqueado por
        // política de origem): trata como "sem suspeita detectada por este
        // sinal" — os outros sinais e a allowlist/reautenticação do servidor
        // continuam de pé; nunca bloqueia o colaborador por uma falha do
        // PRÓPRIO instrumento de defesa em profundidade.
        if (!cancelado) setDeteccaoCameraVirtual({ suspeita: false, sinais: [] });
      });
    return () => {
      cancelado = true;
    };
  }, [video, captura.trilhaDeVideo]);

  const [mensagemDeRecusa, setMensagemDeRecusa] = useState<string | null>(null);

  // "Falha rápida": assim que a câmera virtual é confirmada (sinal 1 já
  // resolve quase instantaneamente; sinais 2/3 levam até ~3 s), a tela
  // recusa na hora — não faz sentido gastar até 12 s do desafio de prova de
  // vida (T7) num canal que já sabemos que vai ser recusado (T8). Isso
  // também torna o bloqueio verificável sem depender de um desafio aprovado.
  useEffect(() => {
    if (deteccaoCameraVirtual?.suspeita && !mensagemDeRecusa) {
      setMensagemDeRecusa(mensagemDoErro("PONTO-SCORE-004"));
    }
  }, [deteccaoCameraVirtual, mensagemDeRecusa]);

  // A prova de vida só roda enquanto a câmera está concedida E a câmera
  // virtual ainda não foi confirmada — confirmada, o gancho libera o
  // `FaceLandmarker` e para o laço de detecção (T7, cleanup do efeito).
  const provaDeVidaAtiva =
    captura.estado === "concedida" && deteccaoCameraVirtual?.suspeita !== true;
  const provaDeVida = useProvaDeVida(video, provaDeVidaAtiva);

  const [confirmacao, setConfirmacao] = useState<DesfechoDeSucesso | null>(null);
  const jaEnviouRef = useRef(false);

  useEffect(() => {
    if (provaDeVida.situacao !== "aprovado") return;
    if (!video) return;
    if (deteccaoCameraVirtual === null) return; // ainda amostrando (T8) — aguarda antes de decidir
    if (!consultaDoColaborador.data?.colaboradorId) return;
    if (jaEnviouRef.current) return;
    jaEnviouRef.current = true;

    if (deteccaoCameraVirtual.suspeita) {
      // Defesa em profundidade: o efeito de "falha rápida" acima já deveria
      // ter interrompido a prova de vida antes de chegar a "aprovado" — mas
      // se por alguma razão isso não aconteceu, o envio continua bloqueado
      // aqui também. Nunca chama a API neste caso.
      setMensagemDeRecusa(mensagemDoErro("PONTO-SCORE-004"));
      return;
    }

    const colaboradorId = consultaDoColaborador.data.colaboradorId;
    const evidencia = provaDeVida.resultado?.evidencia;

    async function registrar(): Promise<void> {
      try {
        const fingerprint = await calcularFingerprint();
        const corpo: Esquema<"MarcacaoCriar"> = {
          colaboradorId,
          canal: "web",
          fotoBase64: capturarFotoBase64(video as HTMLVideoElement),
          livenessMetodo: "desafio_ativo",
          ...(evidencia ? { livenessEvidencia: { ...evidencia } } : {}),
          flagsIntegridade: {
            cameraVirtual: (deteccaoCameraVirtual as ResultadoDaDeteccaoDeCameraVirtual).suspeita,
            fingerprint,
          },
        };

        // Chave nova a cada chamada (inclusive no reenvio automático que
        // `comAcessoControlado` faz após reautenticação) — nunca reusada
        // manualmente (T9, "pronto quando").
        const resposta = await comAcessoControlado(() =>
          api.POST("/v1/marcacoes", {
            params: { header: { "Idempotency-Key": crypto.randomUUID() } },
            body: corpo,
          }),
        );
        const dados = resposta.data;
        if (!dados?.marcacao || !dados.comprovante) {
          throw new Error("Resposta de criarMarcacao incompleta.");
        }

        setConfirmacao({
          variante: dados.revisaoRequerida ? "sucesso_com_revisao" : "sucesso",
          numeroDoComprovante: dados.comprovante.numero ?? "",
          nsr: dados.marcacao.nsr ?? 0,
          horario: dados.marcacao.datahoraMarcacao
            ? formatarHorario(dados.marcacao.datahoraMarcacao)
            : "",
        });
      } catch (erro) {
        setMensagemDeRecusa(
          ehErroDaApi(erro) ? mensagemDoErro(erro.codigo) : mensagemDoErro(undefined),
        );
      }
    }

    void registrar();
  }, [
    provaDeVida.situacao,
    provaDeVida.resultado,
    video,
    deteccaoCameraVirtual,
    consultaDoColaborador.data,
  ]);

  if (confirmacao) {
    return (
      <ConfirmacaoDeRegistro
        variante={confirmacao.variante}
        numeroDoComprovante={confirmacao.numeroDoComprovante}
        nsr={confirmacao.nsr}
        horario={confirmacao.horario}
      />
    );
  }

  if (mensagemDeRecusa) {
    return <ConfirmacaoDeRegistro variante="recusado" mensagem={mensagemDeRecusa} />;
  }

  if (provaDeVida.situacao === "reprovado_final") {
    return (
      <ConfirmacaoDeRegistro variante="recusado" mensagem={mensagemDoErro("PONTO-SCORE-002")} />
    );
  }

  if (consultaDoColaborador.isError) {
    return (
      <Alerta variant="erro">
        <AlertaTitulo>Não foi possível carregar seus dados</AlertaTitulo>
        <AlertaDescricao>Recarregue a página e tente novamente.</AlertaDescricao>
      </Alerta>
    );
  }

  if (provaDeVida.situacao === "erro") {
    return (
      <Alerta variant="erro">
        <AlertaTitulo>Não foi possível preparar a verificação de presença</AlertaTitulo>
        <AlertaDescricao>
          {provaDeVida.mensagemDeErro ?? "Recarregue a página e tente novamente."}
        </AlertaDescricao>
      </Alerta>
    );
  }

  return (
    <div className="flex flex-col gap-[var(--espacamento-3)]">
      <CapturaDeVideo
        estado={captura.estado}
        stream={captura.stream}
        onVideoPronto={setVideo}
        aoSolicitarNovamente={captura.solicitarNovamente}
      />

      {captura.estado === "concedida" && provaDeVida.situacao === "aprovado" && (
        <div
          role="status"
          aria-live="polite"
          className="flex flex-col items-center gap-[var(--espacamento-2)]"
        >
          <Esqueleto className="h-[var(--espacamento-6)] w-full" />
          <p className="estilo-legenda text-texto-secundario">Confirmando seu registro…</p>
        </div>
      )}

      {captura.estado === "concedida" &&
        (provaDeVida.situacao === "carregando_modelo" ||
          provaDeVida.situacao === "em_andamento" ||
          provaDeVida.situacao === "reprovado_tentativa") && (
          <DesafioDeProvaDeVida
            situacao={provaDeVida.situacao}
            desafio={provaDeVida.desafio}
            tentativa={provaDeVida.tentativa}
            segundosRestantes={provaDeVida.segundosRestantes}
          />
        )}
    </div>
  );
}
