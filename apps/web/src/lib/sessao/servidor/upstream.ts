import { NextResponse } from "next/server";

import { URL_API_INTERNA, type Esquema, type Problema } from "@/lib/api";

import { definirCookieDeRefresh } from "./cookie";
import type { TenantResumido } from "../tipos";

/**
 * Utilitários usados exclusivamente pelos *Route Handlers* de `src/app/api/auth/**`
 * (T1). Estes módulos rodam só no servidor (Node do processo Next.js) e falam
 * com `URL_API_INTERNA` — nunca importados por um componente de cliente.
 */

/**
 * `Idempotency-Key` é obrigatória em toda escrita do contrato (mesma regra
 * que `src/lib/api/cliente.ts` aplica para o cliente do navegador — aqui
 * replicada porque estas chamadas são feitas por `fetch` direto, servidor a
 * servidor, sem passar pelo cliente tipado).
 */
function gerarChaveDeIdempotencia(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `idem-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

export function cabecalhosDeEscrita(
  tenant?: string,
  requestId?: string | null,
): Record<string, string> {
  const cabecalhos: Record<string, string> = {
    "Content-Type": "application/json",
    "Idempotency-Key": gerarChaveDeIdempotencia(),
  };
  if (tenant) cabecalhos["X-Tenant"] = tenant;
  if (requestId) cabecalhos["X-Request-Id"] = requestId;
  return cabecalhos;
}

async function tentarLerProblema(resposta: Response): Promise<Problema | undefined> {
  try {
    return (await resposta.clone().json()) as Problema;
  } catch {
    return undefined;
  }
}

/**
 * Encaminha o status e o corpo de erro (RFC 9457, `Problema`) de uma resposta
 * upstream tal como veio — nunca reinterpreta nem troca o código do catálogo.
 */
export async function repassarProblema(respostaUpstream: Response): Promise<NextResponse> {
  const problema = await tentarLerProblema(respostaUpstream);
  return NextResponse.json(
    problema ?? {
      type: "about:blank",
      title: "Erro ao comunicar com a API",
      status: respostaUpstream.status,
      codigo: "PONTO-INT-001",
    },
    { status: respostaUpstream.status },
  );
}

/**
 * Resolve `{slug, nomeExibicao}` do tenant corrente chamando
 * `GET /v1/auth/sessao` com o `accessToken` recém-emitido — o token já carrega
 * o escopo do tenant, então nenhum `X-Tenant` adicional é necessário aqui.
 *
 * Deliberadamente NÃO expõe `permissoes`/`perfis` de `SessaoAtual`: a F9b tem
 * sua própria chamada a `obterSessaoAtual` para RBAC (§2 do PCF) — isto aqui é
 * só para completar a forma fixada de `useSessao().tenant`.
 */
export async function buscarTenantDaSessao(
  accessToken: string,
): Promise<TenantResumido | undefined> {
  try {
    const resposta = await fetch(`${URL_API_INTERNA}/v1/auth/sessao`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      cache: "no-store",
    });
    if (!resposta.ok) return undefined;
    const sessao = (await resposta.json()) as Esquema<"SessaoAtual">;
    if (!sessao.tenant) return undefined;
    const slug = sessao.tenant.slug ?? "";
    return { slug, nomeExibicao: sessao.tenant.nomeExibicao ?? slug };
  } catch {
    return undefined;
  }
}

/**
 * Monta a resposta segura de autenticação (`login`/`mfa/verificar`/`refresh`):
 * grava o cookie `httpOnly` do refresh token e devolve ao cliente **apenas**
 * `{ accessToken, expiresIn, usuario, tenant }` — nunca o refreshToken
 * (proibição 8, §9 do PCF).
 */
export async function montarRespostaAutenticada(
  resultado: Esquema<"LoginResposta">,
): Promise<NextResponse> {
  if (!resultado.accessToken || !resultado.refreshToken || !resultado.usuario) {
    return NextResponse.json(
      {
        type: "about:blank",
        title: "Resposta de autenticação incompleta",
        status: 502,
        codigo: "PONTO-INT-001",
      },
      { status: 502 },
    );
  }

  const tenant = (await buscarTenantDaSessao(resultado.accessToken)) ?? {
    slug: "",
    nomeExibicao: "",
  };

  const resposta = NextResponse.json({
    mfaRequerido: false,
    accessToken: resultado.accessToken,
    expiresIn: resultado.expiresIn ?? 0,
    usuario: {
      id: resultado.usuario.id ?? "",
      nome: resultado.usuario.nomeCompleto ?? "",
      email: resultado.usuario.email ?? "",
    },
    tenant,
  });
  // `tenant.slug` persistido junto (cookie `ponto_tenant`, ver
  // `servidor/cookie.ts`) para que um refresh silencioso futuro — sem
  // Authorization, sem corpo com tenant — ainda consiga resolver o tenant no
  // servidor quando `URL_API_INTERNA` não é, ela mesma, um subdomínio do
  // tenant.
  definirCookieDeRefresh(resposta, resultado.refreshToken, tenant.slug || undefined);
  return resposta;
}
