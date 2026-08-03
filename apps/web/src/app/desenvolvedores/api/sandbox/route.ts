import { NextResponse } from "next/server";

import { URL_API_INTERNA, type Esquema } from "@/lib/api";
import { cabecalhosDeEscrita, repassarProblema } from "@/lib/sessao/servidor/upstream";

/**
 * Proxy do console "tente agora" (T7, PCF F13). Chamado pelo NAVEGADOR
 * (`ConsoleSandbox`); fala servidor-a-servidor com a API real
 * (`URL_API_INTERNA`) em nome do usuário administrador de demonstração que
 * `app.integracoes.sandbox.semear` (T8, A2) semeia — o navegador NUNCA vê a
 * senha desse usuário nem o `clientSecret` do `ApiClient` criado, só o
 * `accessToken` OAuth final (curta duração, escopo limitado, ambiente
 * sandbox). Mesmo padrão de forma de `src/app/api/auth/login/route.ts` (F1).
 *
 * Cadeia de três chamadas reais ao contrato, nenhuma reimplementada aqui:
 * 1. `POST /v1/auth/login` (F1, já implementado) com as credenciais do
 *    admin de demonstração — devolve uma sessão humana de curta vida.
 * 2. `POST /v1/admin/api-clients` (`criarApiClient`, A1/T2) com essa sessão
 *    — cria um `ApiClient` `ambiente="sandbox"` NOVO a cada clique.
 * 3. `POST /v1/auth/token` (F1, já implementado) com as credenciais desse
 *    cliente — emite o token OAuth que alimenta o "Authorize" do Swagger UI.
 *
 * Variáveis de ambiente (server-only, nunca `NEXT_PUBLIC_*`): precisam bater
 * exatamente com `apps/api/app/integracoes/sandbox/constantes.py`
 * (`PONTO_SANDBOX_TENANT_SLUG`/`PONTO_SANDBOX_ADMIN_EMAIL`/
 * `PONTO_SANDBOX_ADMIN_SENHA`) — os mesmos nomes, os dois lados leem do
 * mesmo `infra/.env.example` (bloco próprio de A2, ver relatório da fase).
 */
export const dynamic = "force-dynamic";

type LoginRequisicao = Esquema<"LoginRequisicao">;
type LoginResposta = Esquema<"LoginResposta">;
type ApiClientCriar = Esquema<"ApiClientCriar">;
type ApiClientCriado = Esquema<"ApiClientCriado">;
type TokenOAuthRequisicao = Esquema<"TokenOAuthRequisicao">;
type TokenOAuthResposta = Esquema<"TokenOAuthResposta">;

const TENANT_SANDBOX = process.env.PONTO_SANDBOX_TENANT_SLUG ?? "sandbox-demo";
const EMAIL_ADMIN_SANDBOX =
  process.env.PONTO_SANDBOX_ADMIN_EMAIL ?? `portal-sandbox@${TENANT_SANDBOX}.ponto.seeg.com.br`;

/**
 * Mesma lista de `apps/api/app/integracoes/sandbox/constantes.py::
 * ESCOPOS_CLIENTE_PORTAL` — deliberadamente sem `admin:*`: o visitante do
 * portal nunca deve conseguir, a partir do token de sandbox recebido,
 * gerenciar outros clientes de API ou configuração do tenant.
 */
const ESCOPOS_CLIENTE_PORTAL = [
  "colaboradores:ler",
  "jornadas:ler",
  "marcacoes:ler",
  "marcacoes:escrever",
  "tratamentos:ler",
  "fechamentos:ler",
  "relatorios:ler",
  "fiscal:ler",
  "webhooks:ler",
  "webhooks:escrever",
  "integracoes:ler",
  "integracoes:escrever",
] as const;

function respostaDeConfiguracaoAusente(variavel: string): NextResponse {
  return NextResponse.json(
    {
      type: "about:blank",
      title: "Sandbox não configurado neste ambiente",
      status: 503,
      codigo: "PONTO-INT-001",
      detail: `Variável de ambiente ${variavel} ausente no servidor do portal. Rode a semeadura do sandbox (apps/api/app/integracoes/sandbox/semear.py) e configure as variáveis PONTO_SANDBOX_* do serviço web antes de usar o console interativo.`,
    },
    { status: 503 },
  );
}

export async function POST(): Promise<NextResponse> {
  const senhaAdmin = process.env.PONTO_SANDBOX_ADMIN_SENHA;
  if (!senhaAdmin) {
    return respostaDeConfiguracaoAusente("PONTO_SANDBOX_ADMIN_SENHA");
  }

  // 1) Login do admin de demonstração — sessão humana de curta vida, usada
  // só nesta requisição, nunca devolvida ao navegador.
  const corpoLogin: LoginRequisicao = { email: EMAIL_ADMIN_SANDBOX, senha: senhaAdmin };
  const respostaLogin = await fetch(`${URL_API_INTERNA}/v1/auth/login`, {
    method: "POST",
    headers: cabecalhosDeEscrita(TENANT_SANDBOX),
    body: JSON.stringify(corpoLogin),
    cache: "no-store",
  });
  if (!respostaLogin.ok) return repassarProblema(respostaLogin);
  const login = (await respostaLogin.json()) as LoginResposta;
  if (login.mfaRequerido || !login.accessToken) {
    return NextResponse.json(
      {
        type: "about:blank",
        title: "Sandbox indisponível",
        status: 502,
        codigo: "PONTO-INT-001",
        detail: "O usuário administrador de demonstração não devolveu uma sessão utilizável.",
      },
      { status: 502 },
    );
  }

  // 2) Cria um ApiClient ambiente=sandbox NOVO para este visitante.
  const corpoCliente: ApiClientCriar = {
    nome: `Portal sandbox ${new Date().toISOString()}`,
    descricao: 'Criado pelo console "tente agora" de /desenvolvedores (T7, efêmero).',
    ambiente: "sandbox",
    tipo: "confidencial",
    escopos: [...ESCOPOS_CLIENTE_PORTAL],
  };
  const respostaCliente = await fetch(`${URL_API_INTERNA}/v1/admin/api-clients`, {
    method: "POST",
    headers: {
      ...cabecalhosDeEscrita(TENANT_SANDBOX),
      Authorization: `Bearer ${login.accessToken}`,
    },
    body: JSON.stringify(corpoCliente),
    cache: "no-store",
  });
  if (!respostaCliente.ok) return repassarProblema(respostaCliente);
  const clienteCriado = (await respostaCliente.json()) as ApiClientCriado;
  const clientId = clienteCriado.cliente?.clientId;
  const clientSecret = clienteCriado.clientSecret;
  if (!clientId || !clientSecret) {
    return NextResponse.json(
      {
        type: "about:blank",
        title: "Sandbox indisponível",
        status: 502,
        codigo: "PONTO-INT-001",
        detail: "A criação do cliente de sandbox não devolveu clientId/clientSecret.",
      },
      { status: 502 },
    );
  }

  // 3) Troca as credenciais do cliente por um token OAuth de verdade — o
  // ÚNICO segredo que chega ao navegador, e só ele (nunca o clientSecret).
  const corpoToken: TokenOAuthRequisicao = {
    grantType: "client_credentials",
    clientId,
    clientSecret,
    scope: ESCOPOS_CLIENTE_PORTAL.join(" "),
  };
  const respostaToken = await fetch(`${URL_API_INTERNA}/v1/auth/token`, {
    method: "POST",
    headers: cabecalhosDeEscrita(TENANT_SANDBOX),
    body: JSON.stringify(corpoToken),
    cache: "no-store",
  });
  if (!respostaToken.ok) return repassarProblema(respostaToken);
  const token = (await respostaToken.json()) as TokenOAuthResposta;

  return NextResponse.json({
    clientId,
    accessToken: token.accessToken,
    tokenType: token.tokenType ?? "Bearer",
    expiresIn: token.expiresIn ?? 0,
    scope: token.scope ?? ESCOPOS_CLIENTE_PORTAL.join(" "),
  });
}
