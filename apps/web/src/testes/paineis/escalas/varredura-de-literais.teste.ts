import { readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Prova estática desta seção (T12/T13, "pronto quando" da §6 do PCF F9b):
 * nenhum arquivo desta seção chama uma operação inexistente no contrato
 * (`obterTurno`/`excluirTurno`/`atualizarVinculo`/`removerMembroEquipe`/
 * `POST /v1/escalas/copiar`), usa termo proibido do glossário, ou faz
 * `if perfil === "..."` (RBAC deve ser só por permissão exata). Busca no
 * texto-fonte, não no DOM renderizado — mesmo padrão de
 * `testes/f8/webcam/sem-upload-de-arquivo.teste.ts`.
 */

const DIRETORIOS_DESTA_SECAO = [
  join(import.meta.dirname, "../../../componentes/paineis/escalas"),
  join(import.meta.dirname, "../../../app/painel/escalas"),
];

// `ganchos/**` é compartilhado entre os quatro agentes da fase — só os três
// de ownership de A4 (T12/T13) entram nesta varredura, listados a dedo.
const GANCHOS_DE_OWNERSHIP_DESTA_SECAO = [
  join(import.meta.dirname, "../../../ganchos/use-turnos.ts"),
  join(import.meta.dirname, "../../../ganchos/use-escalas.ts"),
  join(import.meta.dirname, "../../../ganchos/use-resolucao-jornada.ts"),
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

describe("busca estática — nenhuma operação inexistente no contrato (T12/T13)", () => {
  it("encontrou arquivos para varrer", () => {
    expect(arquivos.length).toBeGreaterThan(5);
  });

  it.each(arquivos)("%s não chama GET individual de turno (obterTurno não existe)", (caminho) => {
    const conteudo = removerComentarios(readFileSync(caminho, "utf8"));
    expect(conteudo).not.toMatch(/\.GET\(\s*["']\/v1\/turnos\/\{turnoId\}["']/);
  });

  it.each(arquivos)("%s não chama exclusão de turno (excluirTurno não existe)", (caminho) => {
    const conteudo = removerComentarios(readFileSync(caminho, "utf8"));
    expect(conteudo).not.toMatch(/\.DELETE\(\s*["']\/v1\/turnos/);
  });

  it.each(arquivos)(
    "%s não chama atualização de vínculo (atualizarVinculo não existe)",
    (caminho) => {
      const conteudo = removerComentarios(readFileSync(caminho, "utf8"));
      expect(conteudo).not.toMatch(/\.PATCH\(\s*["']\/v1\/vinculos/);
      expect(conteudo).not.toMatch(/atualizarVinculo/);
    },
  );

  it.each(arquivos)(
    "%s não chama remoção de membro de equipe (removerMembroEquipe não existe)",
    (caminho) => {
      const conteudo = removerComentarios(readFileSync(caminho, "utf8"));
      expect(conteudo).not.toMatch(/removerMembroEquipe/);
    },
  );

  it.each(arquivos)('%s não inventa "copiar período" como endpoint', (caminho) => {
    const conteudo = removerComentarios(readFileSync(caminho, "utf8"));
    expect(conteudo).not.toMatch(/\/v1\/escalas\/copiar/);
  });

  it.each(arquivos)("%s não usa termo proibido do glossário (§6)", (caminho) => {
    const conteudo = removerComentarios(readFileSync(caminho, "utf8"));
    expect(conteudo.toLowerCase()).not.toMatch(/\bbatida\b/);
    expect(conteudo.toLowerCase()).not.toMatch(/editar marcação|corrigir marcação/);
  });

  it.each(arquivos)(
    '%s não faz RBAC por nome de papel ("rh"/"gestor"/"diretoria" hardcoded)',
    (caminho) => {
      const conteudo = removerComentarios(readFileSync(caminho, "utf8"));
      expect(conteudo).not.toMatch(/perfil\s*===\s*["'](rh|gestor|diretoria)["']/i);
    },
  );
});
