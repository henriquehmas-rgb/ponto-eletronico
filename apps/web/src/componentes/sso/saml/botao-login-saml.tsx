"use client";

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";

import { Botao } from "@/componentes/ui/button";
import { api } from "@/lib/api";
import { URL_API_PUBLICA } from "@/lib/api/config";
import { validarRetornoSeguro } from "@/lib/sessao";
import { CHAVE_SESSION_STORAGE_RETURN_TO } from "@/lib/sso/vinculo";

/**
 * Link de login federado SAML 2.0 (T22, F13/A10, RFC-018/ADR-013).
 *
 * Navegação de PÁGINA INTEIRA (nunca `fetch`): `GET /v1/sso/{provedor}/
 * iniciar` responde 302 direto ao Identity Provider do tenant, e só um
 * `<a>`/`window.location` real segue um redirecionamento HTTP entre
 * origens — código de cliente não pode. `?tenant=` é o mesmo mecanismo que
 * `X-Tenant` nas rotas JSON, adaptado a link puro (a rota aceita os dois).
 *
 * `returnTo` (achado de revisão adversarial no fechamento da F13, mesmo
 * mecanismo do botão OIDC): guardado em `sessionStorage` (sobrevive à volta
 * de página inteira do IdP, mesma origem/aba) para `sso/concluir/
 * pagina-de-conclusao.tsx` devolver o usuário ao lugar certo. Puramente do
 * lado do cliente — não depende do RelayState/backend SAML (A10, não
 * tocado): o anti-CSRF do SAML já é o RelayState assinado, isto aqui é só
 * UX de destino pós-login.
 *
 * A consulta de `/v1/tenants/atual` usa a MESMA `queryKey` que
 * `pagina-de-login.tsx` (F1/F8) já usa para o mesmo fim — o React Query
 * deduplica automaticamente, sem acoplar os dois arquivos por import.
 */
export function BotaoLoginSaml() {
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

  function entrar() {
    const retorno = validarRetornoSeguro(parametrosDeBusca.get("returnTo"));
    if (retorno) {
      sessionStorage.setItem(CHAVE_SESSION_STORAGE_RETURN_TO, retorno);
    } else {
      sessionStorage.removeItem(CHAVE_SESSION_STORAGE_RETURN_TO);
    }

    const url = new URL("/v1/sso/saml/iniciar", URL_API_PUBLICA);
    if (!resolvidoPorSubdominio && slug) {
      url.searchParams.set("tenant", slug);
    }
    window.location.href = url.toString();
  }

  return (
    <Botao type="button" variant="secundaria" tamanho="toque" onClick={entrar}>
      Entrar com SSO corporativo (SAML)
    </Botao>
  );
}
