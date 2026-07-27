"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { definirProvedorDeToken, definirTenant } from "@/lib/api";

import {
  chamarLogin,
  chamarLogout,
  chamarRefresh,
  chamarVerificarSegundoFator,
} from "./cliente-de-sessao";
import type {
  CredenciaisDeEntrada,
  RespostaDeAutenticacao,
  TenantResumido,
  UsuarioAutenticado,
} from "./tipos";

/**
 * `ProvedorDeSessao`/`useSessao` — módulo ÚNICO de sessão do produto (T1).
 *
 * Contrato fixado em `docs/fases/F08-web-colaborador-webcam.md` §2: a F9b
 * (fase irmã, mesma onda) importa exatamente esta interface, sem recriar
 * login nem sessão próprios. Não mude a forma sem avisar quem consome.
 *
 * `accessToken` vive só em memória (`useRef`, nunca em estado que force
 * re-render, nunca em `localStorage`/`sessionStorage` — proibição 8, §9 do
 * PCF): é lido pelo cliente HTTP (`src/lib/api/cliente.ts`) através do
 * `provedor` registrado em `definirProvedorDeToken`.
 */

interface EstadoDeSessao {
  usuario: UsuarioAutenticado | null;
  tenant: TenantResumido | null;
  autenticado: boolean;
  carregando: boolean;
}

export interface ContextoDeSessao extends EstadoDeSessao {
  entrar: (credenciais: CredenciaisDeEntrada) => Promise<{ mfaRequerido: boolean }>;
  verificarSegundoFator: (codigo: string) => Promise<void>;
  sair: () => Promise<void>;
}

const ESTADO_INICIAL: EstadoDeSessao = {
  usuario: null,
  tenant: null,
  autenticado: false,
  carregando: true,
};

const ContextoSessao = createContext<ContextoDeSessao | undefined>(undefined);

export function ProvedorDeSessao({ children }: { children: ReactNode }) {
  const [estado, definirEstado] = useState<EstadoDeSessao>(ESTADO_INICIAL);
  const accessTokenRef = useRef<string | undefined>(undefined);
  // Desafio de MFA pendente entre `entrar()` (que recebe mfaRequerido) e
  // `verificarSegundoFator()` (que resolve o desafio). Estado interno — nunca
  // exposto na interface fixada.
  const desafioMfaRef = useRef<{ desafioId: string; tenant: string | undefined } | undefined>(
    undefined,
  );

  const aplicarAutenticacao = useCallback((resposta: RespostaDeAutenticacao) => {
    accessTokenRef.current = resposta.accessToken;
    definirTenant(resposta.tenant.slug || undefined);
    definirEstado({
      usuario: resposta.usuario,
      tenant: resposta.tenant,
      autenticado: true,
      carregando: false,
    });
  }, []);

  const limparAutenticacao = useCallback(() => {
    accessTokenRef.current = undefined;
    definirTenant(undefined);
    definirEstado({ usuario: null, tenant: null, autenticado: false, carregando: false });
  }, []);

  useEffect(() => {
    // Registrado uma única vez: o cliente HTTP sempre lê o valor CORRENTE do
    // ref, então não precisa ser re-registrado a cada troca de token.
    definirProvedorDeToken(() => accessTokenRef.current);
  }, []);

  useEffect(() => {
    let cancelado = false;
    chamarRefresh()
      .then((resposta) => {
        if (!cancelado) aplicarAutenticacao(resposta);
      })
      .catch(() => {
        if (!cancelado) limparAutenticacao();
      });
    return () => {
      cancelado = true;
    };
    // Roda uma única vez, ao montar — é o "refresh silencioso" que faz a
    // sessão sobreviver a um recarregamento de página.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const entrar = useCallback<ContextoDeSessao["entrar"]>(
    async (credenciais) => {
      const resposta = await chamarLogin(credenciais);
      if (resposta.mfaRequerido) {
        desafioMfaRef.current = { desafioId: resposta.desafioId, tenant: credenciais.tenant };
        return { mfaRequerido: true };
      }
      desafioMfaRef.current = undefined;
      aplicarAutenticacao(resposta);
      return { mfaRequerido: false };
    },
    [aplicarAutenticacao],
  );

  const verificarSegundoFator = useCallback(
    async (codigo: string) => {
      const desafio = desafioMfaRef.current;
      if (!desafio) {
        throw new Error("Nenhum desafio de segundo fator pendente — chame entrar() primeiro.");
      }
      const resposta = await chamarVerificarSegundoFator({
        desafioId: desafio.desafioId,
        codigo,
        ...(desafio.tenant ? { tenant: desafio.tenant } : {}),
      });
      desafioMfaRef.current = undefined;
      aplicarAutenticacao(resposta);
    },
    [aplicarAutenticacao],
  );

  const sair = useCallback(async () => {
    try {
      await chamarLogout(accessTokenRef.current);
    } catch (erro) {
      // Mesma regra do Route Handler (T1): uma falha de rede ao encerrar a
      // sessão no servidor nunca prende o colaborador numa sessão que ele
      // quis encerrar — o estado local é limpo de qualquer jeito (`finally`).
      console.error("Falha ao chamar logout (estado local limpo mesmo assim):", erro);
    } finally {
      limparAutenticacao();
    }
  }, [limparAutenticacao]);

  const valor = useMemo<ContextoDeSessao>(
    () => ({ ...estado, entrar, verificarSegundoFator, sair }),
    [estado, entrar, verificarSegundoFator, sair],
  );

  return <ContextoSessao.Provider value={valor}>{children}</ContextoSessao.Provider>;
}

export function useSessao(): ContextoDeSessao {
  const contexto = useContext(ContextoSessao);
  if (!contexto) {
    throw new Error("useSessao precisa ser chamado dentro de <ProvedorDeSessao>.");
  }
  return contexto;
}
