"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Alerta, AlertaDescricao, AlertaTitulo } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import { Esqueleto } from "@/componentes/ui/skeleton";
import type { Problema } from "@/lib/api";
import { validarRetornoSeguro } from "@/lib/sessao";
import { mensagemDoErro } from "@/lib/seguranca/dicionario-de-erros";
import { CHAVE_SESSION_STORAGE_RETURN_TO } from "@/lib/sso/vinculo";

/**
 * `{webBaseUrl}/sso/concluir` — destino fixo do redirecionamento final do
 * login federado SAML (`POST /v1/sso/saml/acs`, ver
 * `apps/api/app/identidade/sso/saml/fluxo.py:url_conclusao_spa` e a
 * descrição de `concluirLoginSaml` no contrato). Os tokens chegam no
 * FRAGMENTO da URL (`window.location.hash`) — nunca na query string, nunca
 * visíveis a nenhum servidor, só ao JavaScript do navegador — por isso esta
 * página, e só ela, pode lê-los.
 *
 * Não usa `useSearchParams()` (fragmento não é parte da query string que o
 * Next.js exporia por ali); lê `window.location.hash` diretamente dentro de
 * `useEffect`, garantindo que só roda no navegador.
 *
 * Achados de revisão adversarial no fechamento da F13, ambos corrigidos
 * aqui: (1) o fragmento com `accessToken`/`refreshToken` brutos ficava
 * exposto no histórico do navegador até o `fetch` assíncrono resolver (ou
 * indefinidamente, no caminho de erro) — agora `history.replaceState` limpa
 * o fragmento da barra de endereço IMEDIATAMENTE ao montar, antes de
 * qualquer chamada de rede, em vez de depender só do `router.replace` do
 * caminho de sucesso. (2) o erro exibido era sempre o mesmo texto genérico,
 * ignorando o `Problema` (RFC 9457) que o Route Handler já repassa
 * corretamente — agora usa `mensagemDoErro`, mesmo dicionário que
 * `pagina-de-login.tsx` já usa.
 */
export function PaginaDeConclusaoSaml() {
  const router = useRouter();
  const [erro, definirErro] = useState<string | null>(null);
  const chamadaEmAndamento = useRef(false);

  useEffect(() => {
    if (chamadaEmAndamento.current) return;
    chamadaEmAndamento.current = true;

    const fragmento = window.location.hash.replace(/^#/, "");
    const parametros = new URLSearchParams(fragmento);
    const accessToken = parametros.get("accessToken");
    const refreshToken = parametros.get("refreshToken");
    const expiresInBruto = parametros.get("expiresIn");
    const expiresIn = expiresInBruto ? Number(expiresInBruto) : Number.NaN;

    // Limpa o fragmento sensível da barra de endereço/histórico ANTES de
    // qualquer outra coisa — nunca espera o resultado da chamada de rede.
    window.history.replaceState(null, "", window.location.pathname + window.location.search);

    const retorno = validarRetornoSeguro(sessionStorage.getItem(CHAVE_SESSION_STORAGE_RETURN_TO)) ?? "/";
    sessionStorage.removeItem(CHAVE_SESSION_STORAGE_RETURN_TO);

    if (!accessToken || !refreshToken || Number.isNaN(expiresIn)) {
      definirErro(mensagemDoErro("PONTO-AUTH-004"));
      return;
    }

    fetch("/api/auth/sso/concluir", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ accessToken, refreshToken, expiresIn }),
    })
      .then(async (resposta) => {
        if (!resposta.ok) {
          const problema = (await resposta.json().catch(() => undefined)) as Problema | undefined;
          throw new Error(mensagemDoErro(problema?.codigo));
        }
        router.replace(retorno);
      })
      .catch((erroCapturado: unknown) => {
        definirErro(erroCapturado instanceof Error ? erroCapturado.message : mensagemDoErro(undefined));
      });
  }, [router]);

  if (erro) {
    return (
      <section className="mx-auto flex w-full max-w-sm flex-col gap-4 px-6 py-16">
        <Alerta variant="erro">
          <AlertaTitulo>Não foi possível entrar</AlertaTitulo>
          <AlertaDescricao>{erro}</AlertaDescricao>
        </Alerta>
        <Botao type="button" tamanho="toque" onClick={() => router.replace("/")}>
          Voltar ao login
        </Botao>
      </section>
    );
  }

  return (
    <section className="mx-auto flex w-full max-w-sm flex-col gap-4 px-6 py-16">
      <Esqueleto className="h-8 w-40" />
      <Esqueleto className="h-10 w-full" />
      <Esqueleto className="h-10 w-full" />
    </section>
  );
}
