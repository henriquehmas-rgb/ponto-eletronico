import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join, relative } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * T14 do PCF F08 — réplica, para os diretórios NOVOS desta fase, da mesma
 * técnica de `src/testes/design-system/varredura-de-literais.teste.ts`
 * (F9a, lido como modelo — este é um arquivo NOVO, não uma edição do
 * original, que continua cobrindo só `componentes/ui/**`).
 *
 * Critério 11 da §7 do PCF F08: "nenhum valor literal de cor, espaçamento,
 * raio, sombra, z-index nos componentes novos desta fase — verificado pela
 * varredura de T14, mecanismo entregue, não promessa."
 *
 * Cobre exatamente os caminhos listados na descrição da T14:
 * `src/app/eu/**`, `src/app/page.tsx`, e
 * `src/componentes/{sessao,seguranca,registro-webcam}/**`.
 *
 * T14 é tarefa COMPARTILHADA entre A1 (`app/eu/**`, `app/page.tsx`,
 * `componentes/sessao/**`), A2 (`componentes/registro-webcam/**`) e A3
 * (`componentes/seguranca/**`) — nenhum dos três tem ownership exclusivo
 * deste arquivo. Por isso a varredura tolera diretório ainda inexistente
 * (`listarArquivos` devolve `[]` em vez de lançar) em vez de exigir que
 * todos os três agentes já tenham escrito seus caminhos: cada agente que
 * rodar este teste localmente vê, no mínimo, a cobertura do que já existe.
 */

const RAIZ_DO_PROJETO = join(import.meta.dirname, "../../..");

const ALVOS = [
  join(RAIZ_DO_PROJETO, "src/app/eu"),
  join(RAIZ_DO_PROJETO, "src/app/page.tsx"),
  join(RAIZ_DO_PROJETO, "src/componentes/sessao"),
  join(RAIZ_DO_PROJETO, "src/componentes/seguranca"),
  join(RAIZ_DO_PROJETO, "src/componentes/registro-webcam"),
];

function listarArquivos(caminho: string): string[] {
  if (!existsSync(caminho)) return [];
  const info = statSync(caminho);
  if (info.isFile()) {
    return [".ts", ".tsx"].includes(extname(caminho)) ? [caminho] : [];
  }
  const saida: string[] = [];
  for (const nome of readdirSync(caminho)) {
    const filho = join(caminho, nome);
    const infoFilho = statSync(filho);
    if (infoFilho.isDirectory()) {
      saida.push(...listarArquivos(filho));
      continue;
    }
    if (
      [".ts", ".tsx"].includes(extname(nome)) &&
      !nome.endsWith(".stories.tsx") &&
      !nome.endsWith(".teste.tsx") &&
      !nome.endsWith(".teste.ts")
    ) {
      saida.push(filho);
    }
  }
  return saida;
}

interface Violacao {
  arquivo: string;
  linha: number;
  trecho: string;
  regra: string;
}

const RE_HEX = /#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3}(?:[0-9a-fA-F]{2})?)?\b/g;
const RE_COLCHETE = /\[([^\]]+)\]/g;
const RE_Z_NUMERICO = /(?<![\w-])z-(?:\d+)\b/g;
const RE_UNIDADE = /\d(px|rem|em|vh|vw)\b/;

function varreLinha(linha: string): Array<{ regra: string; trecho: string }> {
  const achados: Array<{ regra: string; trecho: string }> = [];

  const semColchetes = linha.replace(RE_COLCHETE, "[…]");
  for (const m of semColchetes.matchAll(RE_HEX)) {
    achados.push({ regra: "hexadecimal literal", trecho: m[0] });
  }

  for (const m of linha.matchAll(RE_COLCHETE)) {
    const conteudo = m[1] ?? "";
    if (conteudo.includes("var(--")) continue;
    if (RE_UNIDADE.test(conteudo) || RE_HEX.test(conteudo)) {
      achados.push({ regra: "valor arbitrario nao ligado a token", trecho: `[${conteudo}]` });
    }
    RE_HEX.lastIndex = 0;
  }

  for (const m of linha.matchAll(RE_Z_NUMERICO)) {
    achados.push({ regra: "z-index numerico fora de `camada`", trecho: m[0] });
  }

  return achados;
}

const arquivos = ALVOS.flatMap(listarArquivos);

describe("varredura de literais em src/app/eu, src/app/page.tsx e componentes/{sessao,seguranca,registro-webcam} (F08, T14)", () => {
  it("encontrou pelo menos os arquivos desta fase já escritos (a varredura não está rodando vazia)", () => {
    // Ao menos os arquivos de A3 (lib/seguranca não entra aqui, só
    // componentes/seguranca) precisam existir quando A3 roda este teste.
    expect(arquivos.length).toBeGreaterThan(0);
  });

  it.each(arquivos.map((caminho) => ({ caminho, nome: relative(RAIZ_DO_PROJETO, caminho) })))(
    "$nome não contém valor literal de cor/tamanho/z-index",
    ({ caminho }) => {
      const conteudo = readFileSync(caminho, "utf8");
      const violacoes: Violacao[] = [];
      conteudo.split("\n").forEach((linha, indice) => {
        for (const achado of varreLinha(linha)) {
          violacoes.push({
            arquivo: caminho,
            linha: indice + 1,
            trecho: achado.trecho,
            regra: achado.regra,
          });
        }
      });

      if (violacoes.length > 0) {
        const detalhe = violacoes
          .map((v) => `  linha ${v.linha}: [${v.regra}] ${v.trecho}`)
          .join("\n");
        throw new Error(
          `Valor literal encontrado em ${relative(RAIZ_DO_PROJETO, caminho)}:\n${detalhe}`,
        );
      }
    },
  );
});

describe("componentes novos consomem token SEMÂNTICO, nunca primitivo direto (F08, T14)", () => {
  const RE_PRIMITIVO_DIRETO = /var\(--primitivo-/g;

  it.each(arquivos.map((caminho) => ({ caminho, nome: relative(RAIZ_DO_PROJETO, caminho) })))(
    "$nome não referencia var(--primitivo-...) diretamente",
    ({ caminho }) => {
      const conteudo = readFileSync(caminho, "utf8");
      const achados = [...conteudo.matchAll(RE_PRIMITIVO_DIRETO)];
      expect(achados).toHaveLength(0);
    },
  );
});
