import type { NextResponse } from "next/server";

/**
 * Cookie do refresh token — só manipulado pelos três *Route Handlers* de T1
 * (`api/auth/{login,refresh,logout}`). Nunca lido nem escrito por JavaScript
 * de página: `httpOnly` garante isso (proibição 8, §9 do PCF).
 */
export const NOME_COOKIE_REFRESH = "ponto_refresh_token";

/**
 * Cookie companheiro, guardando só o SLUG do tenant (não é credencial — é o
 * mesmo valor que já viaja em texto claro na URL/subdomínio em produção).
 *
 * Por que existe (achado da verificação final da F8, corrigido aqui):
 * `POST /v1/auth/refresh` não aceita `tenant` no corpo (`RefreshRequisicao`
 * não tem esse campo — confirmado em `packages/contracts/openapi.yaml` e em
 * `apps/api/app/routers/auth.py::renovar_sessao`, que só resolve o tenant via
 * `X-Tenant` OU via subdomínio do `Host` da requisição). O refresh é chamado
 * SEM interação do colaborador (silencioso, ao montar `ProvedorDeSessao`) e
 * SEM `Authorization` (o acesso já expirou/sumiu da memória) — não há de
 * onde tirar o tenant na hora, a não ser que ele já esteja persistido desde o
 * login. Sem isto, `POST {URL_API_INTERNA}/v1/auth/refresh` (chamada
 * servidor-a-servidor, nunca por subdomínio do tenant — `URL_API_INTERNA` é
 * um endereço interno único) devolve `PONTO-VAL-011` sempre que o host não
 * resolve o tenant sozinho, quebrando literalmente o "recarregar a página em
 * `/eu` mantém a sessão" (critério 1 da §7 do PCF) em qualquer topologia onde
 * `URL_API_INTERNA` não é, ela mesma, um subdomínio por tenant — reproduzido
 * contra a API real durante esta verificação.
 */
export const NOME_COOKIE_TENANT = "ponto_tenant";

/** Restringe os cookies às próprias rotas de auth — o navegador não os envia em nenhuma outra chamada. */
const CAMINHO_COOKIE_REFRESH = "/api/auth";

export function definirCookieDeRefresh(
  resposta: NextResponse,
  refreshToken: string,
  tenantSlug?: string,
): void {
  resposta.cookies.set(NOME_COOKIE_REFRESH, refreshToken, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: CAMINHO_COOKIE_REFRESH,
  });
  if (tenantSlug) {
    resposta.cookies.set(NOME_COOKIE_TENANT, tenantSlug, {
      httpOnly: true,
      secure: true,
      sameSite: "lax",
      path: CAMINHO_COOKIE_REFRESH,
    });
  }
}

/** `Max-Age=0` limpa os dois cookies no navegador imediatamente. */
export function limparCookieDeRefresh(resposta: NextResponse): void {
  resposta.cookies.set(NOME_COOKIE_REFRESH, "", {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: CAMINHO_COOKIE_REFRESH,
    maxAge: 0,
  });
  resposta.cookies.set(NOME_COOKIE_TENANT, "", {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: CAMINHO_COOKIE_REFRESH,
    maxAge: 0,
  });
}
