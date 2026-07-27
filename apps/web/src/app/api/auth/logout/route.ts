import { NextResponse, type NextRequest } from "next/server";

import { URL_API_INTERNA } from "@/lib/api";
import {
  limparCookieDeRefresh,
  NOME_COOKIE_REFRESH,
  NOME_COOKIE_TENANT,
} from "@/lib/sessao/servidor/cookie";
import { cabecalhosDeEscrita } from "@/lib/sessao/servidor/upstream";

/**
 * Proxy de logout (T1). Lê o cookie, chama `POST /v1/auth/logout` e limpa o
 * cookie localmente MESMO SE a chamada upstream falhar (rede fora do ar não
 * pode prender o colaborador numa sessão que ele quis encerrar).
 *
 * Encaminha `X-Tenant` do cookie `ponto_tenant` (mesmo achado do refresh, ver
 * `api/auth/refresh/route.ts`): normalmente desnecessário aqui, porque
 * `Authorization` (quando presente) já deixa o servidor resolver o tenant a
 * partir do token validado — mas defesa em profundidade para a chamada sem
 * `Authorization` (`accessToken` já ausente da memória, por exemplo após um
 * F5).
 */
export const dynamic = "force-dynamic";

interface CorpoLogout {
  todasAsSessoes?: boolean;
}

export async function POST(requisicao: NextRequest): Promise<NextResponse> {
  const refreshToken = requisicao.cookies.get(NOME_COOKIE_REFRESH)?.value;
  const tenantDoCookie = requisicao.cookies.get(NOME_COOKIE_TENANT)?.value || undefined;
  const autorizacao = requisicao.headers.get("authorization");

  let corpo: CorpoLogout = {};
  try {
    corpo = (await requisicao.json()) as CorpoLogout;
  } catch {
    // Corpo é opcional no contrato (LogoutRequisicao) — ausência não é erro.
  }

  if (refreshToken) {
    try {
      await fetch(`${URL_API_INTERNA}/v1/auth/logout`, {
        method: "POST",
        headers: {
          ...cabecalhosDeEscrita(tenantDoCookie, requisicao.headers.get("x-request-id")),
          ...(autorizacao ? { Authorization: autorizacao } : {}),
        },
        body: JSON.stringify({ refreshToken, todasAsSessoes: corpo.todasAsSessoes }),
        cache: "no-store",
      });
    } catch (erro) {
      console.error(
        "Falha ao chamar POST /v1/auth/logout upstream (cookie local limpo mesmo assim):",
        erro,
      );
    }
  }

  const resposta = new NextResponse(null, { status: 204 });
  limparCookieDeRefresh(resposta);
  return resposta;
}
