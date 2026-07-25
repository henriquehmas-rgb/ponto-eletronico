"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  ATRIBUTO_TEMA,
  CHAVE_ARMAZENAMENTO,
  ehPreferencia,
  type PreferenciaDeTema,
  type TemaResolvido,
} from "./preferencia-de-tema";

interface ContextoDeTema {
  /** O que o usuario escolheu (pode ser `sistema`). */
  preferencia: PreferenciaDeTema;
  /** O que esta pintado agora (`sistema` ja resolvido). */
  resolvido: TemaResolvido;
  definirPreferencia: (nova: PreferenciaDeTema) => void;
}

const Contexto = createContext<ContextoDeTema | null>(null);

const CONSULTA_ESCURO = "(prefers-color-scheme: dark)";

function temaDoSistema(): TemaResolvido {
  if (typeof window === "undefined") return "claro";
  return window.matchMedia(CONSULTA_ESCURO).matches ? "escuro" : "claro";
}

function aplicarNoDocumento(resolvido: TemaResolvido): void {
  const raiz = document.documentElement;
  raiz.setAttribute(ATRIBUTO_TEMA, resolvido);
  raiz.style.colorScheme = resolvido === "escuro" ? "dark" : "light";
}

/**
 * Provedor de tema.
 *
 * O estado inicial e deliberadamente `sistema` nos dois lados (servidor e
 * primeiro render do cliente) para nao haver divergencia de hidratacao. Quem
 * ja pintou o tema certo foi o script inline do `<head>`; este efeito apenas
 * sincroniza o estado do React com o que ja esta no DOM.
 */
export function ProvedorDeTema({ children }: { children: ReactNode }) {
  const [preferencia, setPreferencia] = useState<PreferenciaDeTema>("sistema");
  const [doSistema, setDoSistema] = useState<TemaResolvido>("claro");
  const [montado, setMontado] = useState(false);

  useEffect(() => {
    const guardada = window.localStorage.getItem(CHAVE_ARMAZENAMENTO);
    if (ehPreferencia(guardada)) setPreferencia(guardada);
    setDoSistema(temaDoSistema());
    setMontado(true);

    const consulta = window.matchMedia(CONSULTA_ESCURO);
    const aoMudar = (evento: MediaQueryListEvent) => {
      setDoSistema(evento.matches ? "escuro" : "claro");
    };
    consulta.addEventListener("change", aoMudar);
    return () => {
      consulta.removeEventListener("change", aoMudar);
    };
  }, []);

  const resolvido: TemaResolvido = preferencia === "sistema" ? doSistema : preferencia;

  useEffect(() => {
    if (!montado) return;
    aplicarNoDocumento(resolvido);
  }, [montado, resolvido]);

  const definirPreferencia = useCallback((nova: PreferenciaDeTema) => {
    setPreferencia(nova);
    try {
      window.localStorage.setItem(CHAVE_ARMAZENAMENTO, nova);
    } catch {
      // Modo privativo ou armazenamento cheio: o tema vale so para esta aba.
    }
  }, []);

  const valor = useMemo<ContextoDeTema>(
    () => ({ preferencia, resolvido, definirPreferencia }),
    [preferencia, resolvido, definirPreferencia],
  );

  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useTema(): ContextoDeTema {
  const contexto = useContext(Contexto);
  if (contexto === null) {
    throw new Error("useTema precisa estar dentro de <ProvedorDeTema>.");
  }
  return contexto;
}
