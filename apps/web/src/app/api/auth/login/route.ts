import { NextResponse, type NextRequest } from "next/server";

import { URL_API_INTERNA, type Esquema } from "@/lib/api";
import {
  cabecalhosDeEscrita,
  montarRespostaAutenticada,
  repassarProblema,
} from "@/lib/sessao/servidor/upstream";

/**
 * Proxy de login (T1). Chamado pelo NAVEGADOR (via `chamarLogin`,
 * `src/lib/sessao/cliente-de-sessao.ts`); fala servidor-a-servidor com a API
 * (`URL_API_INTERNA`) e é o ÚNICO lugar que grava o cookie `httpOnly` do
 * refresh token — o `Set-Cookie` só é respeitado pelo navegador quando vem da
 * mesma origem da página (§2 do PCF), por isso este proxy existe em vez de o
 * navegador chamar `POST /v1/auth/login` direto.
 *
 * Mesmo padrão de forma de `src/app/api/health/route.ts`.
 */
export const dynamic = "force-dynamic";

type LoginRequisicao = Esquema<"LoginRequisicao">;
type LoginResposta = Esquema<"LoginResposta">;

export async function POST(requisicao: NextRequest): Promise<NextResponse> {
  let corpo: LoginRequisicao;
  try {
    corpo = (await requisicao.json()) as LoginRequisicao;
  } catch {
    return NextResponse.json(
      {
        type: "about:blank",
        title: "Corpo da requisição inválido",
        status: 400,
        codigo: "PONTO-VAL-001",
      },
      { status: 400 },
    );
  }

  const respostaUpstream = await fetch(`${URL_API_INTERNA}/v1/auth/login`, {
    method: "POST",
    headers: cabecalhosDeEscrita(corpo.tenant, requisicao.headers.get("x-request-id")),
    body: JSON.stringify(corpo),
    cache: "no-store",
  });

  if (!respostaUpstream.ok) {
    return repassarProblema(respostaUpstream);
  }

  const resultado = (await respostaUpstream.json()) as LoginResposta;

  if (resultado.mfaRequerido) {
    return NextResponse.json({
      mfaRequerido: true,
      desafioId: resultado.desafioId ?? "",
      metodosMfa: resultado.metodosMfa ?? [],
    });
  }

  return montarRespostaAutenticada(resultado);
}
