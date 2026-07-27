/// <reference lib="webworker" />

import { NetworkFirst, NetworkOnly, Serwist } from "serwist";
import type { PrecacheEntry, SerwistGlobalConfig } from "serwist";

/**
 * Fonte do *service worker* (T5, PWA). `@serwist/next` (InjectManifest)
 * injeta a lista de precache em `self.__SW_MANIFEST` no momento do build —
 * ela cobre os ativos estáticos gerados (JS/CSS/fontes) e é o "shell" que
 * permite `/eu` renderizar offline assim que já visitada uma vez.
 *
 * Regra inegociável (§5/T5 do PCF): NUNCA cachear escrita. `POST
 * /v1/marcacoes` — e qualquer outro método diferente de GET — vai sempre
 * direto para a rede, nunca para o cache.
 */
declare global {
  interface WorkerGlobalScope extends SerwistGlobalConfig {
    __SW_MANIFEST: (PrecacheEntry | string)[] | undefined;
  }
}

declare const self: ServiceWorkerGlobalScope;

// `self.__SW_MANIFEST` só pode aparecer UMA VEZ no código-fonte: o plugin de
// injeção (`@serwist/next`) procura o texto literal para substituir pela
// lista real de precache no build, e reprova ("Multiple instances...") se
// encontrar mais de uma ocorrência — por isso a leitura é isolada aqui, antes
// de qualquer outro uso.
const precacheEntries = self.__SW_MANIFEST ?? [];

const serwist = new Serwist({
  precacheEntries,
  skipWaiting: true,
  clientsClaim: true,
  navigationPreload: true,
  runtimeCaching: [
    {
      // Qualquer escrita (POST/PUT/PATCH/DELETE) vai direto para a rede —
      // nunca cacheada, nunca servida do cache em caso de falha.
      matcher: ({ request }) => request.method !== "GET",
      handler: new NetworkOnly(),
    },
    {
      // Leituras da API (mesma origem via `/api/**` ou origem própria da API
      // em `/v1/**`): network-first — tenta a rede, cai no cache só quando a
      // rede falha (uso breve offline), nunca serve dado desatualizado com a
      // rede disponível.
      matcher: ({ url }) => url.pathname.startsWith("/v1/") || url.pathname.startsWith("/api/"),
      handler: new NetworkFirst({ cacheName: "ponto-api" }),
    },
    {
      // Navegação (documentos HTML, inclusive `/eu`): mesma estratégia —
      // sempre tenta a rede primeiro.
      matcher: ({ request }) => request.mode === "navigate",
      handler: new NetworkFirst({ cacheName: "ponto-paginas" }),
    },
  ],
});

serwist.addEventListeners();
