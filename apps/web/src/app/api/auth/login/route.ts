import { NextResponse, type NextRequest } from "next/server";

import { URL_API_INTERNA, type Esquema } from "@/lib/api";
import { corpoDeclaradoComoJson, requisicaoDeMesmaOrigem } from "@/lib/sessao/servidor/csrf";
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
 *
 * **CSRF de login (F14/A2, retrofit).** Achado da F13 (fechamento,
 * `docs/backlog.md` 2026-08-03): a MESMA classe de vulnerabilidade já
 * corrigida em `api/auth/sso/**` (`lib/sessao/servidor/csrf.ts`) também se
 * aplica aqui -- um formulário cross-site com `enctype="text/plain"` monta
 * um corpo que `Request.json()` aceita como JSON válido independente do
 * `Content-Type` declarado, então sem esta checagem um site de terceiros
 * conseguiria induzir o navegador da vítima a autenticar como o ATACANTE
 * (login-CSRF: a vítima digitaria a PRÓPRIA credencial num formulário
 * induzido, mas a resposta plantaria um cookie de sessão vinculado ao tenant/
 * conta que o atacante escolheu no corpo forjado). Mesmo padrão já testado
 * de `api/auth/sso/concluir/route.ts`.
 */
export const dynamic = "force-dynamic";

type LoginRequisicao = Esquema<"LoginRequisicao">;
type LoginResposta = Esquema<"LoginResposta">;

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
