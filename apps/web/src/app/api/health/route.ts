import { NextResponse } from "next/server";

import { AMBIENTE } from "@/lib/api";

/**
 * Healthcheck do processo web.
 *
 * O caminho NAO e escolha desta aplicacao: `infra/docker-compose.yml` (servico
 * `web`) sonda exatamente `http://127.0.0.1:3000/api/health`, e o Traefik usa o
 * mesmo caminho em `loadbalancer.healthcheck.path`. Mudar aqui derruba o
 * healthcheck do container.
 *
 * De liveness, nao de readiness: responde sobre ESTE processo. Nao chama a API,
 * o banco nem o Redis de proposito — um pico de latencia na API nao pode fazer
 * o orquestrador matar o front, que ainda serve pagina estatica e erro decente.
 */
export const dynamic = "force-dynamic";
export const revalidate = 0;

export function GET(): NextResponse {
  return NextResponse.json(
    {
      status: "ok",
      servico: "web",
      ambiente: AMBIENTE,
      fase: "F0 — andaime",
      horario: new Date().toISOString(),
    },
    { headers: { "cache-control": "no-store" } },
  );
}
