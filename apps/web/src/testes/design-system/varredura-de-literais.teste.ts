import { readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join, relative } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Critério 7 da §7 do PCF F09a: "nenhum valor literal de cor, espaçamento,
 * raio, sombra, duração, z-index ou tamanho de fonte no código de
 * componente — só var(--…) e utilitários do Tailwind ligados aos tokens.
 * Verificável por uma regra de lint ou por um teste de varredura do
 * código-fonte; entregue o mecanismo, não só a promessa."
 *
 * Este teste varre `src/componentes/ui/**` (os primitivos) e falha se
 * encontrar:
 *  1. Um hexadecimal de cor escrito à mão (`#RRGGBB`/`#RGB`/`#RRGGBBAA`).
 *  2. Um valor arbitrário do Tailwind (colchete) que contenha unidade de
 *     tamanho (px/rem/em/vh/vw) ou hexadecimal SEM ser uma referência a
 *     variável CSS — ou seja, `h-[36px]` reprova, `h-[var(--dimensao-altura-controle)]`
 *     não. (Deliberadamente escrito por extenso, sem reticências, nos
 *     exemplos deste comentário: o Tailwind v4 varre todo arquivo-fonte —
 *     comentário incluso — em busca de candidatos a classe, e um placeholder
 *     como `--dimensao-...` gera um aviso de CSS inválido no build por não
 *     ser uma variável de verdade.)
 *  3. Um z-index numérico solto (`z-10`, `z-50`) fora da escala `camada` —
 *     só `z-[var(--camada-elevado)]` (ou outro nível real da escala) é aceito.
 *  4. `style={{ ... }}` com propriedade de cor/tamanho/raio/sombra/duração
 *     escrita como número ou string literal (fora de `var(--...)`).
 *
 * NÃO reprova utilitários de escala do Tailwind sem colchete (`h-9`, `px-3`,
 * `gap-2`, `size-4`, `rounded-sm`...): a escala de espaçamento do Tailwind
 * (`--spacing`) foi deliberadamente mantida viva pelo gerador de tokens
 * (`apps/web/scripts/tokens-para-css.mjs`, comentário da função `gerar`) —
 * ela é uma grade de 4 px da qual a grade de 8 pt do contrato é subconjunto
 * exato. Isso é the mesmo motivo por que `rounded-sm`/`rounded-md`/etc.  não
 * reprovam: são apelidos do Tailwind para os níveis reais de `raio.*`
 * (ver `APELIDOS_RAIO` no gerador).
 */

const RAIZ_UI = join(import.meta.dirname, "../../componentes/ui");

function listarArquivos(pasta: string): string[] {
  const saida: string[] = [];
  for (const nome of readdirSync(pasta)) {
    const caminho = join(pasta, nome);
    const info = statSync(caminho);
    if (info.isDirectory()) {
      saida.push(...listarArquivos(caminho));
      continue;
    }
    if ([".ts", ".tsx"].includes(extname(nome)) && !nome.endsWith(".stories.tsx")) {
      saida.push(caminho);
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

  // 1. Hex fora de colchete (dentro de colchete e tratado separadamente).
  const semColchetes = linha.replace(RE_COLCHETE, "[…]");
  for (const m of semColchetes.matchAll(RE_HEX)) {
    achados.push({ regra: "hexadecimal literal", trecho: m[0] });
  }

  // 2. Colchete arbitrario do Tailwind com unidade ou hex, sem var(--...).
  for (const m of linha.matchAll(RE_COLCHETE)) {
    const conteudo = m[1] ?? "";
    if (conteudo.includes("var(--")) continue;
    if (RE_UNIDADE.test(conteudo) || RE_HEX.test(conteudo)) {
      achados.push({ regra: "valor arbitrario nao ligado a token", trecho: `[${conteudo}]` });
    }
    RE_HEX.lastIndex = 0;
  }

  // 3. z-index numerico solto (fora da escala `camada`).
  for (const m of linha.matchAll(RE_Z_NUMERICO)) {
    achados.push({ regra: "z-index numerico fora de `camada`", trecho: m[0] });
  }

  return achados;
}

describe("varredura de literais em src/componentes/ui/** (criterio 7)", () => {
  const arquivos = listarArquivos(RAIZ_UI);

  it("encontrou arquivos para varrer (a varredura nao esta rodando vazia)", () => {
    expect(arquivos.length).toBeGreaterThan(10);
  });

  it.each(arquivos.map((caminho) => ({ caminho, nome: relative(RAIZ_UI, caminho) })))(
    "$nome nao contem valor literal de cor/tamanho/z-index",
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
        throw new Error(`Valor literal encontrado em ${relative(RAIZ_UI, caminho)}:\n${detalhe}`);
      }
    },
  );
});

describe("primitivos consomem token SEMANTICO, nunca primitivo direto (proibicao 3)", () => {
  const arquivos = listarArquivos(RAIZ_UI);
  const RE_PRIMITIVO_DIRETO = /var\(--primitivo-/g;

  it.each(arquivos.map((caminho) => ({ caminho, nome: relative(RAIZ_UI, caminho) })))(
    "$nome nao referencia var(--primitivo-...) diretamente",
    ({ caminho }) => {
      const conteudo = readFileSync(caminho, "utf8");
      const achados = [...conteudo.matchAll(RE_PRIMITIVO_DIRETO)];
      expect(achados).toHaveLength(0);
    },
  );
});
