import { ErroDaApi, type Problema } from "@/lib/api";

import type { CredenciaisDeEntrada, RespostaDeAutenticacao, RespostaDeLogin } from "./tipos";

/**
 * Cliente que fala SÓ com os três `Route Handlers` de `src/app/api/auth/**`
 * (T1) — nunca direto com a origem da API. É o único módulo que sabe a forma
 * exata da resposta desses proxies.
 */
async function chamarRotaDeAuth<T>(
  caminho: string,
  corpo?: unknown,
  accessToken?: string,
): Promise<T> {
  const cabecalhos: Record<string, string> = { "Content-Type": "application/json" };
  if (accessToken) cabecalhos.Authorization = `Bearer ${accessToken}`;

  const resposta = await fetch(caminho, {
    method: "POST",
    headers: cabecalhos,
    credentials: "same-origin",
    ...(corpo !== undefined ? { body: JSON.stringify(corpo) } : {}),
  });

  if (resposta.status === 204) {
    return undefined as T;
  }

  let corpoResposta: unknown;
  try {
    corpoResposta = await resposta.json();
  } catch {
    corpoResposta = undefined;
  }

  if (!resposta.ok) {
    throw new ErroDaApi(resposta.status, corpoResposta as Problema | undefined);
  }

  return corpoResposta as T;
}

export function chamarLogin(credenciais: CredenciaisDeEntrada): Promise<RespostaDeLogin> {
  return chamarRotaDeAuth<RespostaDeLogin>("/api/auth/login", credenciais);
}

export function chamarVerificarSegundoFator(dados: {
  desafioId: string;
  codigo: string;
  tenant?: string;
}): Promise<RespostaDeAutenticacao> {
  return chamarRotaDeAuth<RespostaDeAutenticacao>("/api/auth/mfa/verificar", dados);
}

/** Sem corpo: o refresh token vive só no cookie `httpOnly`, lido pelo próprio Route Handler. */
export function chamarRefresh(): Promise<RespostaDeAutenticacao> {
  return chamarRotaDeAuth<RespostaDeAutenticacao>("/api/auth/refresh");
}

export function chamarLogout(
  accessToken: string | undefined,
  todasAsSessoes?: boolean,
): Promise<void> {
  return chamarRotaDeAuth<void>("/api/auth/logout", { todasAsSessoes }, accessToken);
}
