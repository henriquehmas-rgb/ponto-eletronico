import { NextResponse, type NextRequest } from "next/server";

import { URL_API_INTERNA, type Esquema } from "@/lib/api";
import { corpoDeclaradoComoJson, requisicaoDeMesmaOrigem } from "@/lib/sessao/servidor/csrf";
import { montarRespostaAutenticada } from "@/lib/sessao/servidor/upstream";

/**
 * Proxy de conclusão de login federado SAML. Diferente do proxy OIDC
 * (`src/app/api/auth/sso/[provedor]/callback/route.ts`): a API já concluiu
 * o fluxo inteiro e emitiu os tokens ANTES de redirecionar
 * (`POST /v1/sso/saml/acs` -> 302 para `{webBaseUrl}/sso/concluir` com os
 * tokens no FRAGMENTO da URL, nunca na query string — fragmento nunca
 * trafega até nenhum servidor, só o navegador o vê). Por isso este proxy
 * não fala com `/v1/sso/**` de novo: recebe do cliente, por `fetch` (mesma
 * origem), os valores que `src/app/sso/concluir/pagina-de-conclusao.tsx` já
 * leu de `window.location.hash`, e só precisa completar o que o fragmento
 * não carrega — o objeto `usuario` — antes de reusar `montarRespostaAutenticada`
 * (mesmo helper de `login`/`refresh`, mesmo cookie `httpOnly`).
 */
export const dynamic = "force-dynamic";

type LoginResposta = Esquema<"LoginResposta">;
type SessaoAtual = Esquema<"SessaoAtual">;

interface CorpoConclusaoSaml {
  accessToken?: string;
  refreshToken?: string;
  expiresIn?: number;
}

function respostaInvalida(): NextResponse {
  return NextResponse.json(
    {
      type: "about:blank",
      title: "Dados de conclusão de SSO ausentes ou incompletos",
      status: 400,
      codigo: "PONTO-VAL-001",
    },
    { status: 400 },
  );
}

/**
 * Achado de revisão adversarial (fechamento da F13): esta rota aceita
 * tokens que o PRÓPRIO CLIENTE alega serem válidos (só confirma "vivos" via
 * `/v1/auth/sessao`, nunca de onde vieram) -- sem a checagem abaixo, um site
 * de terceiros conseguiria forjar um POST cross-site com um `accessToken`/
 * `refreshToken` do PRÓPRIO ATACANTE, fazendo o navegador da VÍTIMA plantar
 * um cookie de sessão autenticado como o atacante (login-CSRF) -- a vítima,
 * pensando estar na própria sessão, pode expor dado sensível ao atacante.
 */
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

  let corpo: CorpoConclusaoSaml;
  try {
    corpo = (await requisicao.json()) as CorpoConclusaoSaml;
  } catch {
    return respostaInvalida();
  }

  const { accessToken, refreshToken, expiresIn } = corpo;
  if (!accessToken || !refreshToken || typeof expiresIn !== "number") {
    return respostaInvalida();
  }

  const respostaSessao = await fetch(`${URL_API_INTERNA}/v1/auth/sessao`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });
  if (!respostaSessao.ok) {
    return NextResponse.json(
      {
        type: "about:blank",
        title: "Não foi possível confirmar a identidade do usuário",
        status: 502,
        codigo: "PONTO-INT-001",
      },
      { status: 502 },
    );
  }
  const sessaoAtual = (await respostaSessao.json()) as SessaoAtual;
  if (!sessaoAtual.usuario) {
    return NextResponse.json(
      {
        type: "about:blank",
        title: "Resposta de sessão incompleta",
        status: 502,
        codigo: "PONTO-INT-001",
      },
      { status: 502 },
    );
  }

  const resultado: LoginResposta = {
    mfaRequerido: false,
    accessToken,
    refreshToken,
    tokenType: "Bearer",
    expiresIn,
    usuario: sessaoAtual.usuario,
  };
  return montarRespostaAutenticada(resultado);
}
