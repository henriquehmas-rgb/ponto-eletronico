#!/usr/bin/env node
// =============================================================================
// tipos-da-api.mjs — gera os tipos TypeScript da API a partir do contrato
// =============================================================================
// Le  : packages/contracts/openapi.yaml   (congelado na Fase 0)
// Grava: apps/web/src/lib/api/tipos.gerado.ts
//
// Uso:
//   node scripts/tipos-da-api.mjs           grava o arquivo
//   node scripts/tipos-da-api.mjs --check   falha se estiver desatualizado
//
// DECISAO (T5 da Fase 0): o contrato tem 39.404 linhas, 140 caminhos, 215
// operacoes e 245 schemas. Foi medido antes de decidir: `openapi-typescript`
// converte o arquivo inteiro em ~0,55 s e produz ~31 mil linhas de tipo. Como
// o custo e irrisorio, NAO ha recorte: gera-se o contrato COMPLETO. Nenhum tipo
// de request, response ou schema e escrito a mao nesta aplicacao — duplicar o
// contrato a mao e exatamente o defeito que a Fase 0 existe para impedir.
// =============================================================================

import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import openapiTS, { astToString } from "openapi-typescript";

const AQUI = dirname(fileURLToPath(import.meta.url));
const RAIZ_WEB = resolve(AQUI, "..");
const ORIGEM = resolve(RAIZ_WEB, "../../packages/contracts/openapi.yaml");
const DESTINO = resolve(RAIZ_WEB, "src/lib/api/tipos.gerado.ts");

const CABECALHO = `/* eslint-disable */
/**
 * ARQUIVO GERADO — NAO EDITE A MAO.
 *
 * Origem : packages/contracts/openapi.yaml (congelado na Fase 0)
 * Gerador: apps/web/scripts/tipos-da-api.mjs (openapi-typescript)
 * Regerar: pnpm tipos:api        Conferir: pnpm tipos:api:check
 *
 * Qualquer edicao aqui e perdida na proxima geracao. O contrato so muda por
 * RFC aprovada (protocolo em FASES-E-AGENTES.md secao 1.3).
 */
`;

async function principal() {
  const conferir = process.argv.includes("--check");

  if (!existsSync(ORIGEM)) {
    console.error(`ERRO: contrato nao encontrado em ${ORIGEM}`);
    process.exit(1);
  }

  const inicio = Date.now();
  const ast = await openapiTS(new URL(`file://${ORIGEM.replace(/\\/g, "/")}`), {
    alphabetize: true,
    emptyObjectsUnknown: true,
  });
  const conteudo = CABECALHO + astToString(ast);
  const digest = createHash("sha256").update(conteudo).digest("hex").slice(0, 12);

  if (conferir) {
    if (!existsSync(DESTINO)) {
      console.error("ERRO: src/lib/api/tipos.gerado.ts nao existe. Rode `pnpm tipos:api`.");
      process.exit(1);
    }
    const atual = readFileSync(DESTINO, "utf8").replace(/\r\n/g, "\n");
    if (atual !== conteudo) {
      console.error(
        "ERRO: src/lib/api/tipos.gerado.ts esta desatualizado em relacao a\n" +
          "      packages/contracts/openapi.yaml. Rode `pnpm tipos:api`.",
      );
      process.exit(1);
    }
    console.log(`tipos.gerado.ts em dia (sha256:${digest}).`);
    return;
  }

  mkdirSync(dirname(DESTINO), { recursive: true });
  writeFileSync(DESTINO, conteudo, "utf8");

  const linhas = conteudo.split("\n").length;
  const caminhos = (conteudo.match(/^\s{4}"\/v1[^"]*":/gm) ?? []).length;
  console.log(`gerado  : ${DESTINO}`);
  console.log(`origem  : ${ORIGEM}`);
  console.log(`linhas  : ${linhas}`);
  console.log(`caminhos: ${caminhos}`);
  console.log(`tempo   : ${Date.now() - inicio} ms`);
  console.log(`sha256  : ${digest}`);
}

await principal();
