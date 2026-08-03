"use client";

import dynamic from "next/dynamic";

import "swagger-ui-react/swagger-ui.css";

/**
 * Console interativo do contrato (T7). `swagger-ui-react` (Apache-2.0,
 * compatível com licença comercial) escolhido em vez de Redoc: Redoc é
 * só leitura (nenhum "Try it out" embutido, exigiria construir um console
 * HTTP do zero); Swagger UI já entrega exatamente o console "tente agora"
 * que T7 pede, com "Authorize" pronto para o token de sandbox. Peso de
 * bundle mitigado por `next/dynamic({ ssr: false })`: só carrega quando
 * `/desenvolvedores` é visitado, nunca entra no bundle comum da aplicação
 * (nenhuma outra rota importa este módulo).
 *
 * `ssr: false` é obrigatório aqui: `swagger-ui-react` toca `window`/`document`
 * na primeira renderização e quebra em Server Component/SSR.
 */
const SwaggerUI = dynamic(() => import("swagger-ui-react"), { ssr: false });

interface VisualizadorOpenApiProps {
  /** Token OAuth do cliente de sandbox (`ConsoleSandbox`). Ausente: o
   * visualizador ainda funciona para LER o contrato, só "Try it out" falha
   * com 401 até o visitante criar um cliente de sandbox. */
  token?: string | undefined;
}

export function VisualizadorOpenApi({ token }: VisualizadorOpenApiProps) {
  return (
    <div className="overflow-hidden rounded-medio border border-borda-padrao [color-scheme:light]">
      <SwaggerUI
        url="/desenvolvedores/api/openapi"
        docExpansion="list"
        defaultModelsExpandDepth={-1}
        requestInterceptor={(requisicao) => {
          if (token) {
            (requisicao as { headers: Record<string, string> }).headers.Authorization =
              `Bearer ${token}`;
          }
          return requisicao;
        }}
      />
    </div>
  );
}
