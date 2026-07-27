import { NextResponse, type NextRequest } from "next/server";

import { URL_API_INTERNA, type Esquema } from "@/lib/api";
import {
  limparCookieDeRefresh,
  NOME_COOKIE_REFRESH,
  NOME_COOKIE_TENANT,
} from "@/lib/sessao/servidor/cookie";
import {
  cabecalhosDeEscrita,
  montarRespostaAutenticada,
  repassarProblema,
} from "@/lib/sessao/servidor/upstream";

/**
 * Proxy de renovação de sessão (T1). Lê o refresh token do cookie `httpOnly`
 * (nunca do corpo — o navegador não tem acesso a ele), chama
 * `POST /v1/auth/refresh` e regrava o cookie com o token rotacionado.
 *
 * Chamado silenciosamente por `ProvedorDeSessao` ao montar, para a sessão
 * sobreviver a um recarregamento de página.
 *
 * Encaminha `X-Tenant` a partir do cookie `ponto_tenant` (gravado no login,
 * ver `servidor/cookie.ts`): `RefreshRequisicao` não tem campo `tenant` no
 * contrato, e esta chamada não tem `Authorization` (é exatamente por isso
 * que está renovando) — sem o cookie, o servidor só resolveria o tenant pelo
 * subdomínio do `Host` da requisição, que `URL_API_INTERNA` (endereço
 * interno único, servidor-a-servidor) não carrega. Achado e corrigido na
 * verificação final da F8 — reproduzido contra a API real: sem isto,
 * `PONTO-VAL-011` em qualquer topologia onde `URL_API_INTERNA` não é, ela
 * mesma, um subdomínio do tenant.
 */
export const dynamic = "force-dynamic";

type LoginResposta = Esquema<"LoginResposta">;

export async function POST(requisicao: NextRequest): Promise<NextResponse> {
  const refreshToken = requisicao.cookies.get(NOME_COOKIE_REFRESH)?.value;
  if (!refreshToken) {
    return NextResponse.json(
      { type: "about:blank", title: "Sessão ausente", status: 401, codigo: "PONTO-AUTH-006" },
      { status: 401 },
    );
  }
  const tenantDoCookie = requisicao.cookies.get(NOME_COOKIE_TENANT)?.value || undefined;

  const respostaUpstream = await fetch(`${URL_API_INTERNA}/v1/auth/refresh`, {
    method: "POST",
    headers: cabecalhosDeEscrita(tenantDoCookie, requisicao.headers.get("x-request-id")),
    body: JSON.stringify({ refreshToken }),
    cache: "no-store",
  });

  if (!respostaUpstream.ok) {
    const resposta = await repassarProblema(respostaUpstream);
    // Reapresentar um refresh token já consumido (reuso) revoga a família
    // inteira no servidor (contrato, `renovarSessao`) — o cookie local deixa
    // de fazer sentido nesse caso, então é limpo aqui também.
    limparCookieDeRefresh(resposta);
    return resposta;
  }

  const resultado = (await respostaUpstream.json()) as LoginResposta;
  return montarRespostaAutenticada(resultado);
}
