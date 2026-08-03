"use client";

import { useState } from "react";
import { Check, Copy, Loader2 } from "lucide-react";

import { Alerta, AlertaDescricao, AlertaTitulo } from "@/componentes/ui/alert";
import { Selo } from "@/componentes/ui/badge";
import { Botao } from "@/componentes/ui/button";
import {
  Cartao,
  CartaoCabecalho,
  CartaoConteudo,
  CartaoDescricao,
  CartaoTitulo,
} from "@/componentes/ui/card";

interface RespostaSandbox {
  clientId: string;
  accessToken: string;
  tokenType: string;
  expiresIn: number;
  scope: string;
}

interface RespostaProblema {
  title?: string;
  detail?: string;
  codigo?: string;
}

interface ConsoleSandboxProps {
  /** Chamado com o `accessToken` assim que o fluxo de ponta a ponta termina,
   * para o `VisualizadorOpenApi` irmão passar a assinar as requisições de
   * "Try it out" com ele (`requestInterceptor`). */
  onToken: (token: string | undefined) => void;
}

type Estado =
  | { fase: "ocioso" }
  | { fase: "carregando" }
  | { fase: "erro"; mensagem: string }
  | { fase: "pronto"; resultado: RespostaSandbox };

/**
 * "Tente agora" (T7). Um clique dispara, no servidor
 * (`/desenvolvedores/api/sandbox`), a cadeia real login -> criarApiClient
 * (ambiente=sandbox) -> emitirTokenOAuth (depende de A1/T2 — ver PCF F13
 * §5.1, "A2 depende de A1 (leve)") e devolve só o `accessToken` final: o
 * navegador nunca vê senha nem `clientSecret`.
 */
export function ConsoleSandbox({ onToken }: ConsoleSandboxProps) {
  const [estado, setEstado] = useState<Estado>({ fase: "ocioso" });
  const [copiado, setCopiado] = useState(false);

  async function criarClienteEEmitirToken() {
    setEstado({ fase: "carregando" });
    onToken(undefined);
    try {
      const resposta = await fetch("/desenvolvedores/api/sandbox", { method: "POST" });
      const corpo = (await resposta.json()) as RespostaSandbox | RespostaProblema;
      if (!resposta.ok) {
        const problema = corpo as RespostaProblema;
        setEstado({
          fase: "erro",
          mensagem: problema.detail ?? problema.title ?? `Falha (${resposta.status}).`,
        });
        return;
      }
      const resultado = corpo as RespostaSandbox;
      setEstado({ fase: "pronto", resultado });
      onToken(resultado.accessToken);
    } catch {
      setEstado({ fase: "erro", mensagem: "Não foi possível falar com o servidor do portal." });
    }
  }

  async function copiarToken(token: string) {
    try {
      await navigator.clipboard.writeText(token);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      // Área restrita/HTTP sem clipboard API: o token continua visível para
      // seleção manual, então a falha de cópia não é um erro que bloqueia o fluxo.
    }
  }

  return (
    <Cartao>
      <CartaoCabecalho>
        <CartaoTitulo>Tente agora</CartaoTitulo>
        <CartaoDescricao>
          Cria um cliente de API real (<Selo variant="info">ambiente sandbox</Selo>) e emite um
          token OAuth 2.0 contra ele — o mesmo par de chamadas que sua integração fará em produção.
        </CartaoDescricao>
      </CartaoCabecalho>
      <CartaoConteudo className="flex flex-col gap-4">
        <Botao
          onClick={criarClienteEEmitirToken}
          disabled={estado.fase === "carregando"}
          className="w-fit"
        >
          {estado.fase === "carregando" && <Loader2 className="animate-spin" aria-hidden="true" />}
          Criar cliente de sandbox e emitir token
        </Botao>

        {estado.fase === "erro" && (
          <Alerta variant="erro">
            <AlertaTitulo>Não foi possível emitir o token de sandbox</AlertaTitulo>
            <AlertaDescricao>{estado.mensagem}</AlertaDescricao>
          </Alerta>
        )}

        {estado.fase === "pronto" && (
          <div className="grid gap-3">
            <Alerta variant="sucesso">
              <AlertaTitulo>Token de sandbox emitido</AlertaTitulo>
              <AlertaDescricao>
                Válido por {Math.round(estado.resultado.expiresIn / 60)} minutos. O visualizador do
                contrato abaixo já está usando este token — abra qualquer operação e clique em
                &quot;Try it out&quot;.
              </AlertaDescricao>
            </Alerta>
            <div className="grid gap-1">
              <span className="estilo-legenda text-texto-secundario">Access token</span>
              <div className="flex items-center gap-2">
                <code className="flex-1 overflow-x-auto rounded-pequeno bg-fundo-sutil px-2 py-1.5 font-mono text-xs">
                  {estado.resultado.accessToken}
                </code>
                <Botao
                  variant="secundaria"
                  tamanho="icone"
                  aria-label="Copiar token"
                  onClick={() => copiarToken(estado.resultado.accessToken)}
                >
                  {copiado ? <Check /> : <Copy />}
                </Botao>
              </div>
            </div>
            <div className="grid gap-1">
              <span className="estilo-legenda text-texto-secundario">
                Exemplo (curl, escopo {estado.resultado.scope})
              </span>
              <pre className="overflow-x-auto rounded-pequeno bg-fundo-sutil px-3 py-2 font-mono text-xs">
                {`curl -H "Authorization: Bearer ${estado.resultado.accessToken}" \\\n  -H "X-Tenant: sandbox-demo" \\\n  https://api.ponto.seeg.com.br/v1/webhooks`}
              </pre>
            </div>
          </div>
        )}
      </CartaoConteudo>
    </Cartao>
  );
}
