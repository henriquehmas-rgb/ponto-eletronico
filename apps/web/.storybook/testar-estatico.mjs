#!/usr/bin/env node
// =============================================================================
// testar-storybook.mjs — serve o build estatico do Storybook e roda o
// test-runner (axe em todas as historias, nos dois temas) contra ele.
// =============================================================================
// Por que este script existe em vez de dois comandos soltos: o test-runner
// precisa de um SERVIDOR HTTP real (Playwright nao navega em file://), e este
// script garante que o servidor sobe antes do teste e cai depois — mesmo se o
// teste falhar — sem introduzir dependencia extra de orquestracao
// (concurrently, wait-on): so o que ja esta em devDependencies desta fase
// (http-server, @storybook/test-runner).
//
// Os dois binarios sao invocados pelo ARQUIVO JS real deles (resolvido via
// `require.resolve`), nunca via `npx`/`.cmd` com `shell: true`: no Windows,
// `spawn(..., { shell: true })` abre um `cmd.exe` novo cujo ambiente as vezes
// nao herda `fetch` global de forma previsivel dentro do processo do
// test-runner, fazendo o proprio `test-storybook` falhar ao verificar se o
// servidor esta de pe mesmo com o servidor respondendo (visto e reproduzido
// durante a verificacao desta fase). Rodar `node <caminho-do-bin>.js`
// diretamente elimina o `cmd.exe` intermediario.
//
// Uso:
//   pnpm build-storybook   # gera storybook-static/
//   pnpm test:storybook    # este script
// =============================================================================

import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { setTimeout as esperar } from "node:timers/promises";
import { fileURLToPath } from "node:url";

const AQUI = fileURLToPath(new URL(".", import.meta.url));
const RAIZ_WEB = resolve(AQUI, "..");
const PASTA_ESTATICA = resolve(RAIZ_WEB, "storybook-static");
const PORTA = process.env["PORTA_STORYBOOK_TESTE"] ?? "6007";
const URL_BASE = `http://127.0.0.1:${PORTA}`;

const requererDaRaizWeb = createRequire(resolve(RAIZ_WEB, "package.json"));
const BIN_HTTP_SERVER = requererDaRaizWeb.resolve("http-server/bin/http-server");
const BIN_TEST_STORYBOOK = requererDaRaizWeb.resolve("@storybook/test-runner/dist/test-storybook.js");

function rodarNode(argsDoScript, args) {
  return spawn(process.execPath, [...argsDoScript, ...args], { stdio: "inherit", cwd: RAIZ_WEB });
}

async function servidorPronto(url, tentativas = 60) {
  for (let i = 0; i < tentativas; i += 1) {
    try {
      const resposta = await fetch(url);
      if (resposta.status < 500) return true;
    } catch {
      // servidor ainda subindo — tenta de novo.
    }
    await esperar(500);
  }
  return false;
}

async function principal() {
  if (!existsSync(PASTA_ESTATICA)) {
    console.error(
      `ERRO: ${PASTA_ESTATICA} nao existe. Rode \`pnpm build-storybook\` antes de \`pnpm test:storybook\`.`,
    );
    process.exitCode = 1;
    return;
  }

  console.log(`Servindo ${PASTA_ESTATICA} em ${URL_BASE} ...`);
  const servidor = rodarNode([BIN_HTTP_SERVER], [PASTA_ESTATICA, "-p", PORTA, "-a", "127.0.0.1", "-s"]);

  let codigoDeSaida = 1;
  try {
    const pronto = await servidorPronto(URL_BASE);
    if (!pronto) {
      console.error(`ERRO: servidor estatico do Storybook nao respondeu em ${URL_BASE} a tempo.`);
      process.exitCode = 1;
      return;
    }

    console.log(`Rodando test-storybook contra ${URL_BASE} ...`);
    codigoDeSaida = await new Promise((resolvePromessa) => {
      const teste = rodarNode(
        [BIN_TEST_STORYBOOK],
        [
          // Contra um servidor estatico simples (http-server), a autodeteccao
          // do modo "index json" do test-runner nem sempre dispara — forcamos.
          "--index-json",
          "--url",
          URL_BASE,
          "--ci",
          // Ambiente com pouca CPU disponivel: menos workers em paralelo
          // evita que o axe de uma historia estoure o timeout padrao de 15 s
          // so por contencao de recurso (nao por violacao real).
          "--maxWorkers",
          "2",
          "--testTimeout",
          "30000",
        ],
      );
      teste.on("exit", (codigo) => resolvePromessa(codigo ?? 1));
      teste.on("error", () => resolvePromessa(1));
    });
  } finally {
    servidor.kill();
  }

  process.exitCode = codigoDeSaida;
}

await principal();
