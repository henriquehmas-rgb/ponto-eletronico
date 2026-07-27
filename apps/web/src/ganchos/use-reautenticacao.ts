"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, ehErroDaApi } from "@/lib/api";
import { definirSolicitadorDeReautenticacao, mensagemDoErro } from "@/lib/seguranca";

/** Dados do formulário de reautenticação (T12). `codigoMfa` só é enviado
 *  quando o campo de segundo fator está visível (ver `mfaNecessario`). */
export interface DadosDeReautenticacao {
  senha: string;
  codigoMfa?: string;
}

interface EstadoDeReautenticacao {
  /** Controla a visibilidade do `ModalDeReautenticacao`. */
  aberto: boolean;
  /** Verdadeiro quando `GET /v1/auth/sessao` indica que esta sessão já
   *  validou um segundo fator (`SessaoAtual.mfaValidadoEm`) — sinal de que o
   *  usuário tem TOTP ativo e o formulário deve pedir o código também. */
  mfaNecessario: boolean;
  carregando: boolean;
  erro: string | undefined;
}

export interface UseReautenticacaoRetorno extends EstadoDeReautenticacao {
  confirmar: (dados: DadosDeReautenticacao) => Promise<void>;
  cancelar: () => void;
}

const ESTADO_INICIAL: EstadoDeReautenticacao = {
  aberto: false,
  mfaNecessario: false,
  carregando: false,
  erro: undefined,
};

/**
 * `useReautenticacao` — T12 do PCF F08.
 *
 * É o lado de estado do fluxo de reautenticação: `ModalDeReautenticacao`
 * (componente) usa este gancho para saber o que renderizar, e é este gancho
 * quem se registra em `comAcessoControlado` (T13) como o "solicitador" que
 * abre o modal quando o servidor recusa uma escrita sensível com
 * `PONTO-AUTH-011` — o mesmo padrão de gancho de módulo mutável que
 * `definirProvedorDeToken`/`definirTenant` já usam (`src/lib/api/cliente.ts`).
 *
 * `POST /v1/auth/reautenticar` é chamado direto pelo cliente `api` já
 * existente — SEM *Route Handler* (diferente de login/refresh/logout, T1 de
 * A1): usa o `accessToken` já em memória via `Authorization: Bearer`, nunca
 * o cookie `httpOnly` do refresh token (§2 do PCF).
 */
export function useReautenticacao(): UseReautenticacaoRetorno {
  const [estado, setEstado] = useState<EstadoDeReautenticacao>(ESTADO_INICIAL);
  const resolverRef = useRef<(() => void) | null>(null);
  const rejeitarRef = useRef<((motivo: Error) => void) | null>(null);

  /** Consulta best-effort: só decide se o campo de MFA aparece. Se falhar,
   *  o formulário continua funcional sem o campo — o servidor ainda valida
   *  o código se o colaborador enviar um mesmo assim. */
  const detectarMfa = useCallback(async (): Promise<void> => {
    try {
      const resposta = await api.GET("/v1/auth/sessao");
      const necessitaMfa = Boolean(resposta.data?.mfaValidadoEm);
      setEstado((atual) => (atual.aberto ? { ...atual, mfaNecessario: necessitaMfa } : atual));
    } catch {
      // Intencional: ver docstring da função.
    }
  }, []);

  const abrir = useCallback((): Promise<void> => {
    return new Promise<void>((resolve, reject) => {
      resolverRef.current = resolve;
      rejeitarRef.current = reject;
      setEstado({ aberto: true, mfaNecessario: false, carregando: false, erro: undefined });
      void detectarMfa();
    });
  }, [detectarMfa]);

  useEffect(() => {
    definirSolicitadorDeReautenticacao(abrir);
    return () => definirSolicitadorDeReautenticacao(undefined);
  }, [abrir]);

  const confirmar = useCallback(async (dados: DadosDeReautenticacao): Promise<void> => {
    setEstado((atual) => ({ ...atual, carregando: true, erro: undefined }));
    try {
      const corpo: { senha: string; codigoMfa?: string } = { senha: dados.senha };
      if (dados.codigoMfa) corpo.codigoMfa = dados.codigoMfa;
      // `Idempotency-Key` é parâmetro obrigatório do contrato para esta
      // operação (`x-idempotente: true`) — o cliente também a preenche
      // automaticamente quando ausente (`src/lib/api/cliente.ts`), mas o
      // tipo gerado exige o campo explícito para compilar. Gerada nova a
      // cada chamada — nunca reaproveitada entre tentativas.
      await api.POST("/v1/auth/reautenticar", {
        params: { header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });

      setEstado(ESTADO_INICIAL);
      resolverRef.current?.();
      resolverRef.current = null;
      rejeitarRef.current = null;
    } catch (erro) {
      const mensagem = mensagemDoErro(ehErroDaApi(erro) ? erro.codigo : undefined);
      setEstado((atual) => ({ ...atual, carregando: false, erro: mensagem }));
      // Não fecha o modal nem rejeita a promessa: o colaborador pode tentar
      // de novo com a senha certa, sem refazer o que quer que disparou a
      // reautenticação (T9, A2).
    }
  }, []);

  const cancelar = useCallback((): void => {
    setEstado(ESTADO_INICIAL);
    rejeitarRef.current?.(new Error("reautenticacao-cancelada"));
    resolverRef.current = null;
    rejeitarRef.current = null;
  }, []);

  return { ...estado, confirmar, cancelar };
}
