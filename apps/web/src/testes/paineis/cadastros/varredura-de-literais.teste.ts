import { readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Prova estática desta seção (T4–T8, "pronto quando" da §6 do PCF F9b):
 * nenhum arquivo desta seção chama uma operação inexistente no contrato
 * (`excluirCentroCusto`/`excluirCargo`/`atualizarVinculo`/`removerMembroEquipe`),
 * usa termo proibido do glossário, sugere "editar marcação", ou faz
 * `if perfil === "..."` (RBAC deve ser só por permissão exata). Busca no
 * texto-fonte, não no DOM renderizado — mesmo padrão de
 * `testes/paineis/escalas/varredura-de-literais.teste.ts` (A4).
 */

const DIRETORIOS_DESTA_SECAO = [
  join(import.meta.dirname, "../../../componentes/paineis/cadastros"),
  join(import.meta.dirname, "../../../componentes/paineis/mapa"),
  join(import.meta.dirname, "../../../app/painel/cadastros"),
];

// `ganchos/**` é compartilhado entre os quatro agentes da fase — só os
// onze de ownership de A2 (T4–T8) entram nesta varredura, listados a dedo.
const GANCHOS_DE_OWNERSHIP_DESTA_SECAO = [
  "use-empresas.ts",
  "use-unidades.ts",
  "use-departamentos.ts",
  "use-centros-custo.ts",
  "use-cargos.ts",
  "use-equipes.ts",
  "use-colaboradores.ts",
  "use-contratos.ts",
  "use-vinculos.ts",
  "use-dispositivos.ts",
  "use-biometrias.ts",
].map((nome) => join(import.meta.dirname, "../../../ganchos", nome));

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

describe("busca estática — nenhuma operação inexistente no contrato (T4–T8)", () => {
  it("encontrou arquivos para varrer", () => {
    expect(arquivos.length).toBeGreaterThan(10);
  });

  it.each(arquivos)(
    "%s não chama exclusão de centro de custo (excluirCentroCusto não existe)",
    (caminho) => {
      const conteudo = removerComentarios(readFileSync(caminho, "utf8"));
      expect(conteudo).not.toMatch(/\.DELETE\(\s*["']\/v1\/centros-custo/);
      expect(conteudo).not.toMatch(/excluirCentroCusto/);
    },
  );

  it.each(arquivos)("%s não chama exclusão de cargo (excluirCargo não existe)", (caminho) => {
    const conteudo = removerComentarios(readFileSync(caminho, "utf8"));
    expect(conteudo).not.toMatch(/\.DELETE\(\s*["']\/v1\/cargos/);
    expect(conteudo).not.toMatch(/excluirCargo\b/);
  });

  it.each(arquivos)("%s não chama exclusão de contrato (excluirContrato não existe)", (caminho) => {
    const conteudo = removerComentarios(readFileSync(caminho, "utf8"));
    expect(conteudo).not.toMatch(/\.DELETE\(\s*["']\/v1\/contratos/);
  });

  it.each(arquivos)(
    "%s não chama atualização genérica de vínculo (atualizarVinculo não existe)",
    (caminho) => {
      const conteudo = removerComentarios(readFileSync(caminho, "utf8"));
      expect(conteudo).not.toMatch(/\.PATCH\(\s*["']\/v1\/vinculos/);
      expect(conteudo).not.toMatch(/atualizarVinculo/);
    },
  );

  it.each(arquivos)("%s não chama exclusão de vínculo (excluirVinculo não existe)", (caminho) => {
    const conteudo = removerComentarios(readFileSync(caminho, "utf8"));
    expect(conteudo).not.toMatch(/\.DELETE\(\s*["']\/v1\/vinculos/);
  });

  it.each(arquivos)(
    "%s não chama remoção de membro de equipe (removerMembroEquipe não existe)",
    (caminho) => {
      const conteudo = removerComentarios(readFileSync(caminho, "utf8"));
      expect(conteudo).not.toMatch(/removerMembroEquipe/);
    },
  );

  it.each(arquivos)(
    "%s não chama leitura em lote de membros de equipe (GET .../membros não existe)",
    (caminho) => {
      const conteudo = removerComentarios(readFileSync(caminho, "utf8"));
      expect(conteudo).not.toMatch(/\.GET\(\s*["']\/v1\/equipes\/\{equipeId\}\/membros["']/);
    },
  );

  it.each(arquivos)("%s não usa termo proibido do glossário (§6)", (caminho) => {
    const conteudo = removerComentarios(readFileSync(caminho, "utf8")).toLowerCase();
    expect(conteudo).not.toMatch(/\bbatida\b/);
    expect(conteudo).not.toMatch(/editar marcação|corrigir marcação/);
    expect(conteudo).not.toMatch(/banco positivo|banco negativo/);
  });

  it.each(arquivos)(
    '%s não faz RBAC por nome de papel ("rh"/"gestor"/"diretoria" hardcoded)',
    (caminho) => {
      const conteudo = removerComentarios(readFileSync(caminho, "utf8"));
      expect(conteudo).not.toMatch(/perfil\s*===\s*["'](rh|gestor|diretoria)["']/i);
    },
  );

  it.each(arquivos)(
    "%s não usa getUserMedia (captura de biometria é F7/F8, fora desta fase)",
    (caminho) => {
      const conteudo = removerComentarios(readFileSync(caminho, "utf8"));
      expect(conteudo).not.toMatch(/getUserMedia/);
    },
  );
});
