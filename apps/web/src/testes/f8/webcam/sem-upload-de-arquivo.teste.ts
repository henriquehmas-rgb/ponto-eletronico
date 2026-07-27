import { readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Prova estática (critério 4 da §7 do PCF F08): nenhuma tela desta fase
 * aceita upload de arquivo de imagem no caminho de registro de ponto — é
 * proibição de PRODUTO, não só de código (§9, proibição 1). Também prova o
 * critério 9 (nenhuma chamada `PUT`/`PATCH`/`DELETE` a `/v1/marcacoes`) para
 * os diretórios de ownership de A2.
 *
 * Busca estática no texto-fonte, não no DOM renderizado — complementa (não
 * substitui) as asserções de render de `captura-de-video.teste.tsx`.
 */

const DIRETORIOS_DESTA_FASE = [
  join(import.meta.dirname, "../../../app/eu/registrar"),
  join(import.meta.dirname, "../../../componentes/registro-webcam"),
  join(import.meta.dirname, "../../../lib/deteccao"),
];

// `ganchos/**` é compartilhado entre os três agentes da fase — só os dois
// ganchos de ownership de A2 (T6/T7) entram nesta varredura, listados a
// dedo, para não afirmar nada sobre arquivo de outro agente.
const GANCHOS_DE_OWNERSHIP_DESTA_TAREFA = [
  join(import.meta.dirname, "../../../ganchos/use-captura-webcam.ts"),
  join(import.meta.dirname, "../../../ganchos/use-prova-de-vida.ts"),
];

function listarArquivosDeCodigo(pasta: string): string[] {
  const saida: string[] = [];
  for (const nome of readdirSync(pasta)) {
    const caminho = join(pasta, nome);
    const info = statSync(caminho);
    if (info.isDirectory()) {
      saida.push(...listarArquivosDeCodigo(caminho));
      continue;
    }
    if ([".ts", ".tsx"].includes(extname(nome))) {
      saida.push(caminho);
    }
  }
  return saida;
}

const arquivos = [
  ...DIRETORIOS_DESTA_FASE.flatMap((pasta) => listarArquivosDeCodigo(pasta)),
  ...GANCHOS_DE_OWNERSHIP_DESTA_TAREFA,
];

/**
 * Remove comentários de bloco e de linha antes de varrer.
 *
 * Necessário porque a docstring deste MÓDULO (e a de `captura-de-video.tsx`)
 * cita o próprio padrão proibido como exemplo negativo ("nunca existe
 * `<input type=\"file\">`") — sem isto, a varredura reprovaria por causa do
 * comentário que EXPLICA a proibição, não por causa de um upload real. Mesma
 * classe de cuidado que a varredura de literais da F9a já documenta para o
 * próprio texto deste tipo de comentário.
 */
function removerComentarios(codigo: string): string {
  return codigo.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
}

describe("busca estática — nenhum upload de arquivo no registro por webcam (critério 4)", () => {
  it("encontrou arquivos para varrer", () => {
    expect(arquivos.length).toBeGreaterThan(5);
  });

  it.each(arquivos)('%s não contém <input type="file"', (caminho) => {
    const conteudo = removerComentarios(readFileSync(caminho, "utf8"));
    expect(conteudo).not.toMatch(/<input[^>]*type=["']file["']/i);
  });
});

describe("busca estática — nenhuma escrita em /v1/marcacoes além de POST (critério 9)", () => {
  it.each(arquivos)("%s não chama PUT/PATCH/DELETE em /v1/marcacoes", (caminho) => {
    const conteudo = removerComentarios(readFileSync(caminho, "utf8"));
    expect(conteudo).not.toMatch(/\.(PUT|PATCH|DELETE)\(\s*["']\/v1\/marcacoes/);
  });
});
