import { NextResponse, type NextRequest } from "next/server";

import { URL_API_INTERNA, type Esquema } from "@/lib/api";
import { requisicaoDeMesmaOrigem } from "@/lib/sessao/servidor/csrf";
import { montarRespostaAutenticada, repassarProblema } from "@/lib/sessao/servidor/upstream";

const PROVEDORES_VALIDOS = new Set(["google", "entra_id"]);

/**
 * Proxy de conclusão de login federado OIDC (Google/Entra ID). Chamado pelo
 * NAVEGADOR (via `fetch`, por `src/app/sso/callback/[provedor]/page.tsx` —
 * a página que recebe o redirecionamento de página inteira do IdP e só
 * ENTÃO chama este proxy), exatamente como `GET /v1/sso/{provedor}/callback`
 * já é documentado no contrato ("Chamado via fetch pela página que recebe o
 * redirecionamento do IdP, nunca por navegação de documento completa").
 *
 * Mesmo motivo de `src/app/api/auth/login/route.ts` existir: só um
 * `Set-Cookie` que vem da MESMA origem da página é respeitado pelo
 * navegador, e é este proxy — servidor a servidor — que grava o cookie
 * `httpOnly` do refresh token.
 *
 * `code`/`state` chegam na query string (não no corpo): é assim que
 * `callbackSso` os declara no contrato, refletindo o formato padrão do
 * redirecionamento OAuth 2.0 authorization code.
 */
export const dynamic = "force-dynamic";

type LoginResposta = Esquema<"LoginResposta">;

export async function GET(
  requisicao: NextRequest,
  { params }: { params: Promise<{ provedor: string }> },
): Promise<NextResponse> {
  const { provedor } = await params;

  // Achado de revisão adversarial: sem isto, um site de terceiros conseguiria
  // chamar esta rota diretamente (`<img src>`/fetch `no-cors`), plantando o
  // efeito colateral de `Set-Cookie` mesmo sem conseguir LER a resposta —
  // esta rota só deve ser alcançada pelo próprio `fetch` de
  // `src/app/sso/callback/[provedor]/pagina-de-conclusao.tsx`.
  if (!requisicaoDeMesmaOrigem(requisicao)) {
    return NextResponse.json(
      { type: "about:blank", title: "Origem da requisição não confere", status: 403, codigo: "PONTO-PERM-006" },
      { status: 403 },
    );
  }

  if (!PROVEDORES_VALIDOS.has(provedor)) {
    return NextResponse.json(
      { type: "about:blank", title: "Provedor de SSO desconhecido", status: 400, codigo: "PONTO-VAL-001" },
      { status: 400 },
    );
  }

  const code = requisicao.nextUrl.searchParams.get("code");
  const state = requisicao.nextUrl.searchParams.get("state");
  // RFC-019: valor bruto do vínculo de navegador, lido de `sessionStorage`
  // por `pagina-de-conclusao.tsx` e enviado só nesta chamada servidor-a-
  // servidor — nunca na query string que o IdP vê.
  const vinculo = requisicao.nextUrl.searchParams.get("vinculo");

  if (!code || !state || !vinculo) {
    return NextResponse.json(
      {
        type: "about:blank",
        title: "Parâmetros de retorno do provedor ausentes",
        status: 400,
        codigo: "PONTO-VAL-001",
      },
      { status: 400 },
    );
  }

  const urlUpstream = new URL(`/v1/sso/${provedor}/callback`, URL_API_INTERNA);
  urlUpstream.searchParams.set("code", code);
  urlUpstream.searchParams.set("state", state);
  urlUpstream.searchParams.set("vinculo", vinculo);

  const requestId = requisicao.headers.get("x-request-id");
  const respostaUpstream = await fetch(urlUpstream, {
    method: "GET",
    headers: requestId ? { "X-Request-Id": requestId } : {},
    cache: "no-store",
  });

  if (!respostaUpstream.ok) {
    return repassarProblema(respostaUpstream);
  }

  const resultado = (await respostaUpstream.json()) as LoginResposta;
  return montarRespostaAutenticada(resultado);
}
