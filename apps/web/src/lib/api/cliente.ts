import createClient, { type Middleware } from "openapi-fetch";

import { URL_BASE_API } from "./config";
import { ErroDaApi, type Problema } from "./erros";
import type { paths } from "./tipos.gerado";

/**
 * Cliente HTTP tipado pelo contrato.
 *
 * Todo caminho, parametro, corpo e resposta vem de `tipos.gerado.ts`, que sai
 * de `packages/contracts/openapi.yaml`. Chamar um caminho que nao existe, ou
 * mandar um corpo com forma errada, e ERRO DE COMPILACAO — nao de execucao.
 *
 * FASE 0: a API responde 501 (`PONTO-INT-005`) em 214 das 215 operacoes. Este
 * modulo e o andaime; quem liga sessao e token e a F1.
 */

/** Verbos que o contrato exige idempotentes (openapi.yaml, "Convencoes"). */
const VERBOS_DE_ESCRITA = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/** Fonte do token de acesso. A F1 substitui por leitura da sessao real. */
export type ProvedorDeToken = () => string | undefined | Promise<string | undefined>;

let provedorDeToken: ProvedorDeToken = () => undefined;
let tenantAtual: string | undefined;

/** Registra de onde o cliente tira o JWT. Chamado pela camada de sessao (F1). */
export function definirProvedorDeToken(provedor: ProvedorDeToken): void {
  provedorDeToken = provedor;
}

/** Define o tenant enviado em `X-Tenant` quando o host nao o identifica. */
export function definirTenant(tenant: string | undefined): void {
  tenantAtual = tenant;
}

/**
 * `Idempotency-Key` e OBRIGATORIA em toda escrita. Gerar aqui, e nao no ponto
 * de chamada, garante que nenhuma escrita saia sem chave — inclusive as que
 * fases futuras escreverem sem lembrar da regra.
 */
function novaChaveDeIdempotencia(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `idem-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

const autenticacao: Middleware = {
  async onRequest({ request }) {
    const token = await provedorDeToken();
    if (token !== undefined && !request.headers.has("Authorization")) {
      request.headers.set("Authorization", `Bearer ${token}`);
    }
    if (tenantAtual !== undefined && !request.headers.has("X-Tenant")) {
      request.headers.set("X-Tenant", tenantAtual);
    }
    if (VERBOS_DE_ESCRITA.has(request.method) && !request.headers.has("Idempotency-Key")) {
      request.headers.set("Idempotency-Key", novaChaveDeIdempotencia());
    }
    return request;
  },
};

const traducaoDeErro: Middleware = {
  async onResponse({ response }) {
    if (response.ok) return response;

    let problema: Problema | undefined;
    const tipoDoConteudo = response.headers.get("content-type") ?? "";
    if (tipoDoConteudo.includes("json")) {
      try {
        problema = (await response.clone().json()) as Problema;
      } catch {
        problema = undefined;
      }
    }
    throw new ErroDaApi(response.status, problema);
  },
};

/**
 * Cliente compartilhado.
 *
 * A `baseUrl` e so a origem: os caminhos do contrato ja carregam o `/v1`.
 */
export const api = createClient<paths>({
  baseUrl: URL_BASE_API,
  headers: { Accept: "application/json" },
});

api.use(autenticacao);
api.use(traducaoDeErro);

export const { GET, POST, PUT, PATCH, DELETE } = api;
