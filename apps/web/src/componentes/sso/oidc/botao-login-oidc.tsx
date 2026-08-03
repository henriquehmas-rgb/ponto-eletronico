"use client";

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";

import { Botao } from "@/componentes/ui/button";
import { api } from "@/lib/api";
import { URL_API_PUBLICA } from "@/lib/api/config";
import { validarRetornoSeguro } from "@/lib/sessao";
import { CHAVE_SESSION_STORAGE_RETURN_TO, CHAVE_SESSION_STORAGE_VINCULO } from "@/lib/sso/vinculo";

/**
 * Botões de login federado OIDC — Google Workspace e Microsoft Entra ID
 * (T21, F13/A9, RFC-018/ADR-013).
 *
 * Navegação de PÁGINA INTEIRA (nunca `fetch`): `GET /v1/sso/{provedor}/
 * iniciar` responde 302 direto ao Identity Provider (app OIDC compartilhado
 * da aplicação, ADR-013) — só um `<a>`/`window.location` real segue um
 * redirecionamento HTTP entre origens; código de cliente não pode.
 * `?tenant=` é o mesmo mecanismo que `X-Tenant` nas rotas JSON, adaptado a
 * link puro (a rota aceita os dois — ver `app/routers/sso.py`).
 *
 * `vinculoHash` (RFC-019, achado de revisão adversarial no fechamento da
 * F13): gera um valor aleatório por tentativa de login, guarda o valor BRUTO
 * em `sessionStorage` (nunca sai do navegador até o `fetch` servidor-a-
 * servidor da página de conclusão) e manda só o HASH SHA-256 para
 * `iniciarSso` — embutido no `state` assinado, conferido de volta em
 * `callbackSso`. Sem isto, um `state`/`code` válidos capturados pelo
 * PRÓPRIO atacante autenticariam qualquer navegador que os apresentasse
 * (login-CSRF) — ver `docs/rfc/RFC-019-vinculo-de-navegador-no-state-oidc.md`.
 *
 * `returnTo` (mesmo achado, item de completude): guardado no MESMO
 * `sessionStorage` (mesma origem sobrevive à volta do IdP) para a página de
 * conclusão devolver o usuário ao lugar certo, mesmo comportamento que o
 * login por senha já tem (`pagina-de-login.tsx`/`retorno-seguro.ts`).
 *
 * A consulta de `/v1/tenants/atual` usa a MESMA `queryKey` que
 * `pagina-de-login.tsx` (F1/F8) e `botao-login-saml.tsx` (F13/A10) já usam
 * para o mesmo fim — o React Query deduplica automaticamente, sem acoplar
 * este arquivo aos outros dois por import.
 */
async function gerarVinculoEHash(): Promise<{ vinculo: string; hash: string }> {
  const vinculo = crypto.randomUUID();
  const bytes = new TextEncoder().encode(vinculo);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const hash = Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  return { vinculo, hash };
}

function useIniciarSso() {
  const parametrosDeBusca = useSearchParams();
  const consultaTenant = useQuery({
    queryKey: ["tenant-atual"],
    queryFn: async () => {
      const resultado = await api.GET("/v1/tenants/atual");
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    retry: false,
    staleTime: Number.POSITIVE_INFINITY,
  });

  const slug = consultaTenant.data?.slug;
  const resolvidoPorSubdominio = Boolean(slug) && !consultaTenant.isError;

  return async function iniciar(provedor: "google" | "entra_id") {
    const { vinculo, hash } = await gerarVinculoEHash();
    sessionStorage.setItem(CHAVE_SESSION_STORAGE_VINCULO, vinculo);

    const retorno = validarRetornoSeguro(parametrosDeBusca.get("returnTo"));
    if (retorno) {
      sessionStorage.setItem(CHAVE_SESSION_STORAGE_RETURN_TO, retorno);
    } else {
      sessionStorage.removeItem(CHAVE_SESSION_STORAGE_RETURN_TO);
    }

    const url = new URL(`/v1/sso/${provedor}/iniciar`, URL_API_PUBLICA);
    url.searchParams.set("vinculoHash", hash);
    if (!resolvidoPorSubdominio && slug) {
      url.searchParams.set("tenant", slug);
    }
    window.location.href = url.toString();
  };
}

export function BotaoLoginGoogle() {
  const iniciar = useIniciarSso();
  return (
    <Botao
      type="button"
      variant="secundaria"
      tamanho="toque"
      onClick={() => {
        void iniciar("google");
      }}
    >
      Entrar com Google Workspace
    </Botao>
  );
}

export function BotaoLoginEntraId() {
  const iniciar = useIniciarSso();
  return (
    <Botao
      type="button"
      variant="secundaria"
      tamanho="toque"
      onClick={() => {
        void iniciar("entra_id");
      }}
    >
      Entrar com Microsoft Entra ID
    </Botao>
  );
}

/** Os dois botões juntos, para uso direto em `src/app/page.tsx`. */
export function BotoesLoginOidc() {
  return (
    <>
      <BotaoLoginGoogle />
      <BotaoLoginEntraId />
    </>
  );
}
