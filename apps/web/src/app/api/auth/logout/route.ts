import { NextResponse, type NextRequest } from "next/server";

import { URL_API_INTERNA } from "@/lib/api";
import {
  limparCookieDeRefresh,
  NOME_COOKIE_REFRESH,
  NOME_COOKIE_TENANT,
} from "@/lib/sessao/servidor/cookie";
import { corpoDeclaradoComoJson, requisicaoDeMesmaOrigem } from "@/lib/sessao/servidor/csrf";
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
 *
 * **CSRF de logout (F14/A2, retrofit).** Menor severidade que login/refresh
 * (o pior caso é um site terceiro forçar o encerramento da sessão da
 * vítima -- incômodo, não vazamento), mas mesma checagem por consistência
 * de padrão com as outras duas rotas de sessão (`lib/sessao/servidor/csrf.ts`).
 */
export const dynamic = "force-dynamic";

interface CorpoLogout {
  todasAsSessoes?: boolean;
}

function respostaOrigemInvalida(): NextResponse {
  return NextResponse.json(
    { type: "about:blank", title: "Origem da requisição não confere", status: 403, codigo: "PONTO-PERM-006" },
    { status: 403 },
  );
}

export async function POST(requisicao: NextRequest): Promise<NextResponse> {
  if (!requisicaoDeMesmaOrigem(requisicao) || !corpoDeclaradoComoJson(requisicao)) {
    return respostaOrigemInvalida();
  }

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
