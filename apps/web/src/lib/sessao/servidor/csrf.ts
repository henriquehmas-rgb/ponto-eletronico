import type { NextRequest } from "next/server";

/**
 * Defesa contra CSRF para os Route Handlers de SSO (`api/auth/sso/**`,
 * fechamento da F13). Achado real de revisão adversarial: um formulário
 * cross-site com `enctype="text/plain"` monta um corpo que `Request.json()`
 * aceita como JSON válido independente do `Content-Type` declarado (a Fetch
 * spec não valida isso) — sem esta checagem, qualquer site de terceiros
 * conseguiria fazer o navegador da vítima enviar um POST "de verdade" para
 * estas rotas.
 *
 * Duas camadas, nenhuma delas suficiente sozinha:
 * 1. `Sec-Fetch-Site` (metadado injetado pelo NAVEGADOR, nunca controlável
 *    por JavaScript/HTML de terceiros) — quando presente, é a prova mais
 *    forte de que a requisição partiu da própria origem. Suportado por todo
 *    navegador relevante hoje (Baseline "Widely available").
 * 2. `Origin` como resguardo para o raro cliente sem `Sec-Fetch-Site` —
 *    também injetado pelo navegador em toda requisição de escrita
 *    (`POST`/`PUT`/...), nunca pelo corpo/formulário do atacante.
 *
 * Combinada com a checagem de `Content-Type: application/json` estrita
 * (feita no próprio Route Handler antes de chamar `requisicao.json()` —
 * um `<form>` HTML NUNCA consegue produzir esse Content-Type), fecha o
 * vetor: um formulário cross-site não pode simultaneamente declarar
 * `application/json` E aparentar mesma origem.
 */
export function requisicaoDeMesmaOrigem(requisicao: NextRequest): boolean {
  const site = requisicao.headers.get("sec-fetch-site");
  if (site) {
    return site === "same-origin" || site === "none";
  }
  const origem = requisicao.headers.get("origin");
  if (!origem) {
    // Nem `Sec-Fetch-Site` nem `Origin`: navegador antigo demais ou
    // requisição fora de navegador. Falha fechada -- rejeitada.
    return false;
  }
  return origem === requisicao.nextUrl.origin;
}

/** `Content-Type` declarado precisa ser exatamente JSON -- nenhum `<form>` HTML consegue produzir isto. */
export function corpoDeclaradoComoJson(requisicao: NextRequest): boolean {
  const tipo = requisicao.headers.get("content-type") ?? "";
  return tipo.toLowerCase().startsWith("application/json");
}
