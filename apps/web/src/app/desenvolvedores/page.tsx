"use client";

import { useState } from "react";

import { AvisoClienteTolerante } from "@/componentes/desenvolvedores/aviso-cliente-tolerante";
import { ConsoleSandbox } from "@/componentes/desenvolvedores/console-sandbox";
import { VisualizadorOpenApi } from "@/componentes/desenvolvedores/visualizador-openapi";

/**
 * Portal de documentação interativo (T7, PCF F13). Estado do token vive
 * aqui (o pai) porque `ConsoleSandbox` (emite) e `VisualizadorOpenApi`
 * (consome no `requestInterceptor` do "Try it out") são irmãos.
 *
 * "Pronto quando" de T7 (PCF §6): navegar até `/desenvolvedores`, criar um
 * cliente de sandbox pela própria tela e emitir um token contra ele
 * funciona de ponta a ponta — os dois componentes abaixo são exatamente essa
 * jornada, nesta ordem.
 */
export default function PaginaDeDesenvolvedores() {
  const [token, setToken] = useState<string | undefined>(undefined);

  return (
    <div className="grid gap-6">
      <div>
        <h1 className="estilo-titulo-pagina">Documentação da API</h1>
        <p className="mt-1 estilo-corpo text-texto-secundario">
          OAuth 2.0 client credentials, API key, webhooks assinados e integrações de folha — o mesmo
          contrato{" "}
          <code className="rounded-pequeno bg-fundo-sutil px-1 py-0.5 font-mono text-[0.9em]">
            /v1
          </code>{" "}
          que a própria SEEG usa.
        </p>
      </div>

      <AvisoClienteTolerante />

      <ConsoleSandbox onToken={setToken} />

      <VisualizadorOpenApi token={token} />
    </div>
  );
}
