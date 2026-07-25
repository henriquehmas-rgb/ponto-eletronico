"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { ehErroDaApi } from "@/lib/api";

/**
 * Provedor do TanStack Query.
 *
 * O `QueryClient` nasce dentro de `useState` de proposito: criado no escopo do
 * modulo, ele seria COMPARTILHADO entre requisicoes no servidor e um usuario
 * enxergaria cache de outro — vazamento entre tenants, que neste produto e
 * incidente de LGPD, nao bug de performance.
 */
function criarClienteDeConsultas(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Streaming SSR: sem isto, tudo refaz fetch imediatamente no cliente.
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        retry: (tentativas, erro) => {
          // 4xx e decisao do servidor sobre a requisicao: insistir nao muda
          // nada e ainda gasta cota de rate limit. 401 quem trata e a F1.
          if (ehErroDaApi(erro) && erro.status >= 400 && erro.status < 500) return false;
          return tentativas < 2;
        },
      },
      mutations: {
        // Escrita e idempotente por contrato, mas a chave `Idempotency-Key` e
        // gerada por requisicao: reenviar automaticamente criaria uma chave
        // nova e, com ela, um segundo efeito. Retentativa e decisao de quem
        // chama, com a mesma chave. Ver src/lib/api/cliente.ts.
        retry: false,
      },
    },
  });
}

export function ProvedorDeConsultas({ children }: { children: ReactNode }) {
  const [cliente] = useState(criarClienteDeConsultas);
  return <QueryClientProvider client={cliente}>{children}</QueryClientProvider>;
}
