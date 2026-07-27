import { readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Prova estática desta seção (T9/T10/T11, "pronto quando" da §6/§9 do PCF
 * F9b): nenhum arquivo desta seção usa termo proibido do glossário, sugere
 * "editar marcação" como ação, faz RBAC por nome de papel hardcoded, ou
 * inventa um endpoint inexistente (`obterTratamento` em lote,
 * `/v1/apuracoes/recalcular/status`, etc.). Busca no texto-fonte, não no DOM
 * renderizado — mesmo padrão de `testes/paineis/escalas/varredura-de-literais.teste.ts`
 * (A4).
 */

const DIRETORIOS_DESTA_SECAO = [
  join(import.meta.dirname, "../../../componentes/paineis/apuracao"),
  join(import.meta.dirname, "../../../app/painel/apuracao"),
];

// `ganchos/**` é compartilhado entre os quatro agentes da fase — só os quatro
// de ownership de A3 (T9/T10/T11) entram nesta varredura, listados a dedo.
const GANCHOS_DE_OWNERSHIP_DESTA_SECAO = [
  join(import.meta.dirname, "../../../ganchos/use-apuracoes.ts"),
  join(import.meta.dirname, "../../../ganchos/use-tratamentos.ts"),
  join(import.meta.dirname, "../../../ganchos/use-ocorrencias.ts"),
  join(import.meta.dirname, "../../../ganchos/use-recalculo.ts"),
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
    if (
      [".ts", ".tsx"].includes(extname(nome)) &&
      !nome.endsWith(".teste.ts") &&
      !nome.endsWith(".teste.tsx")
    ) {
      saida.push(caminho);
    }
  }
  return saida;
}

const arquivos = [
  ...DIRETORIOS_DESTA_SECAO.flatMap((pasta) => listarArquivosDeCodigo(pasta)),
  ...GANCHOS_DE_OWNERSHIP_DESTA_SECAO,
];

function removerComentarios(codigo: string): string {
  return codigo.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
}

describe("busca estática — vocabulário e RBAC corretos na grade de apuração (T9/T10/T11)", () => {
  it("encontrou arquivos para varrer", () => {
    expect(arquivos.length).toBeGreaterThan(5);
  });

  it.each(arquivos)(
    '%s não usa termo proibido do glossário ("batida"/"editar marcação")',
    (caminho) => {
      const conteudo = removerComentarios(readFileSync(caminho, "utf8")).toLowerCase();
      expect(conteudo).not.toMatch(/\bbatida\b/);
      expect(conteudo).not.toMatch(/editar marcaç[aã]o|corrigir marcaç[aã]o/);
    },
  );

  it.each(arquivos)(
    '%s não faz RBAC por nome de papel ("rh"/"gestor"/"diretoria" hardcoded)',
    (caminho) => {
      const conteudo = removerComentarios(readFileSync(caminho, "utf8"));
      expect(conteudo).not.toMatch(/perfil\s*===\s*["'](rh|gestor|diretoria)["']/i);
    },
  );

  it.each(arquivos)(
    "%s não faz polling de um endpoint de status de recálculo inexistente",
    (caminho) => {
      const conteudo = removerComentarios(readFileSync(caminho, "utf8"));
      expect(conteudo).not.toMatch(/\/v1\/apuracoes\/recalcular\/[^"'`]/);
      expect(conteudo).not.toMatch(/refetchInterval/);
    },
  );

  it.each(arquivos)('%s não usa "banco positivo/negativo" (é saldo credor/devedor)', (caminho) => {
    const conteudo = removerComentarios(readFileSync(caminho, "utf8")).toLowerCase();
    expect(conteudo).not.toMatch(/banco positivo|banco negativo/);
  });
});
