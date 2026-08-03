import { readFile } from "node:fs/promises";
import path from "node:path";

import { NextResponse } from "next/server";

/**
 * Serve `packages/contracts/openapi.yaml` cru para o visualizador interativo
 * do portal (T7, `VisualizadorOpenApi`). Devolve YAML, nao JSON: o
 * `swagger-client` que `swagger-ui-react` embute reconhece os dois formatos
 * sozinho — nenhuma conversao acontece aqui, entao este endpoint nunca
 * pode divergir do contrato congelado por um bug de conversao.
 *
 * `process.cwd()` e o diretorio de onde `next dev`/`next build`/`next start`
 * roda (`apps/web`, ver `package.json`, scripts) — mesmo padrao de
 * resolucao de caminho que `apps/web/scripts/tipos-da-api.mjs` ja usa para
 * achar o mesmo arquivo.
 */
export const dynamic = "force-static";

const CAMINHO_CONTRATO = path.resolve(process.cwd(), "../../packages/contracts/openapi.yaml");

export async function GET(): Promise<NextResponse> {
  try {
    const conteudo = await readFile(CAMINHO_CONTRATO, "utf-8");
    return new NextResponse(conteudo, {
      status: 200,
      headers: {
        "Content-Type": "application/yaml; charset=utf-8",
        "Cache-Control": "public, max-age=300",
      },
    });
  } catch {
    return NextResponse.json(
      {
        type: "about:blank",
        title: "Contrato indisponível",
        status: 500,
        codigo: "PONTO-INT-001",
        detail: "Não foi possível ler packages/contracts/openapi.yaml no servidor.",
      },
      { status: 500 },
    );
  }
}
