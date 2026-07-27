import { NextResponse, type NextRequest } from "next/server";

import { URL_API_INTERNA, type Esquema } from "@/lib/api";
import {
  cabecalhosDeEscrita,
  montarRespostaAutenticada,
  repassarProblema,
} from "@/lib/sessao/servidor/upstream";

/**
 * Proxy do segundo passo do login (MFA), T1. Mesmo motivo de existir do
 * `api/auth/login`: só um *Route Handler* da própria origem pode gravar o
 * cookie `httpOnly` do refresh token.
 */
export const dynamic = "force-dynamic";

type MfaVerificacaoRequisicao = Esquema<"MfaVerificacaoRequisicao">;
type LoginResposta = Esquema<"LoginResposta">;

/**
 * `MfaVerificacaoRequisicao` (contrato) não tem campo `tenant` — mas o
 * navegador pode já saber o tenant desde a tela de login. Aceito aqui só para
 * resolver o cabeçalho `X-Tenant` desta chamada; nunca repassado no corpo
 * upstream (que seguiria o schema exato do contrato).
 */
interface CorpoRecebido extends MfaVerificacaoRequisicao {
  tenant?: string;
}

export async function POST(requisicao: NextRequest): Promise<NextResponse> {
  let corpo: CorpoRecebido;
  try {
    corpo = (await requisicao.json()) as CorpoRecebido;
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

  const { tenant, ...corpoUpstream } = corpo;

  const respostaUpstream = await fetch(`${URL_API_INTERNA}/v1/auth/mfa/verificar`, {
    method: "POST",
    headers: cabecalhosDeEscrita(tenant, requisicao.headers.get("x-request-id")),
    body: JSON.stringify(corpoUpstream),
    cache: "no-store",
  });

  if (!respostaUpstream.ok) {
    return repassarProblema(respostaUpstream);
  }

  const resultado = (await respostaUpstream.json()) as LoginResposta;
  return montarRespostaAutenticada(resultado);
}
