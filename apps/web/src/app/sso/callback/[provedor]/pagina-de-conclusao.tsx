"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Alerta, AlertaDescricao, AlertaTitulo } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import { Esqueleto } from "@/componentes/ui/skeleton";
import type { Problema } from "@/lib/api";
import { validarRetornoSeguro } from "@/lib/sessao";
import { mensagemDoErro } from "@/lib/seguranca/dicionario-de-erros";
import { CHAVE_SESSION_STORAGE_RETURN_TO, CHAVE_SESSION_STORAGE_VINCULO } from "@/lib/sso/vinculo";

/**
 * Página que o Identity Provider (Google Workspace/Entra ID) navega o
 * navegador inteiro até ela (é o `redirect_uri` registrado, ver
 * `apps/api/app/routers/sso.py:_redirect_uri`) — nunca alcançada por
 * `fetch`. `code`/`state` chegam na própria query string desta página; ela
 * então chama `GET /api/auth/sso/{provedor}/callback` (proxy servidor a
 * servidor, mesma origem, único jeito do `Set-Cookie` do refresh token ser
 * aceito pelo navegador) e, tendo sucesso, deixa o refresh silencioso de
 * `ProvedorDeSessao` (`src/lib/sessao/contexto-de-sessao.tsx`) — disparado
 * ao montar `/` — hidratar a sessão a partir do cookie recém-gravado. Não
 * chama `aplicarAutenticacao` diretamente: essa função é interna ao
 * contexto de sessão (T1), nunca exposta fora dele.
 *
 * `vinculo` (RFC-019, achado de revisão adversarial): lê de volta o valor
 * bruto que `botao-login-oidc.tsx` guardou em `sessionStorage` antes de
 * navegar ao IdP, e o envia ao proxy — prova que ESTE navegador é o mesmo
 * que iniciou o fluxo, fechando o login-CSRF que um `state`/`code` capturado
 * por terceiro tentaria explorar. `returnTo`: mesmo mecanismo, devolve o
 * usuário ao lugar certo após o login (mesmo comportamento do login por
 * senha, `pagina-de-login.tsx`).
 */
export function PaginaDeConclusaoOidc({ provedor }: { provedor: string }) {
  const router = useRouter();
  const parametrosDeBusca = useSearchParams();
  const [erro, definirErro] = useState<string | null>(null);
  const chamadaEmAndamento = useRef(false);

  useEffect(() => {
    if (chamadaEmAndamento.current) return;
    chamadaEmAndamento.current = true;

    const code = parametrosDeBusca.get("code");
    const state = parametrosDeBusca.get("state");
    const vinculo = sessionStorage.getItem(CHAVE_SESSION_STORAGE_VINCULO);
    const retorno = validarRetornoSeguro(sessionStorage.getItem(CHAVE_SESSION_STORAGE_RETURN_TO)) ?? "/";
    sessionStorage.removeItem(CHAVE_SESSION_STORAGE_VINCULO);
    sessionStorage.removeItem(CHAVE_SESSION_STORAGE_RETURN_TO);

    if (!code || !state || !vinculo) {
      definirErro(mensagemDoErro("PONTO-AUTH-004"));
      return;
    }

    const url =
      `/api/auth/sso/${encodeURIComponent(provedor)}/callback` +
      `?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}&vinculo=${encodeURIComponent(vinculo)}`;

    fetch(url, { method: "GET", credentials: "same-origin" })
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
  }, [provedor, parametrosDeBusca, router]);

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
