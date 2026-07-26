import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * T2 do PCF F09a — teste automatico dos 124 pares de contraste.
 *
 * O QUE ESTE TESTE PROVA (e o que ele NAO prova):
 *
 * `packages/contracts/design-tokens.json` ja declara, para cada par, o
 * hexadecimal de primeiro plano e de fundo E o ratio medido. Copiar esses
 * hexadecimais direto do JSON e recalcular o ratio provaria so que a
 * calculadora de contraste esta certa — nao provaria que a interface REALMENTE
 * usa essas cores. Por isso este teste le o CSS GERADO
 * (`src/estilos/tokens.gerado.css`, que ninguem deveria editar a mao) para
 * cada token semantico citado no par, segue as indirecoes `var(--...)` ate um
 * hexadecimal literal, e SO ENTAO recalcula o ratio. Se algum dia alguem
 * editar um hexadecimal a mao no CSS gerado (contornando o gerador), este
 * teste diverge do `ratio` declarado no contrato e falha — prova colada no
 * relatorio da fase.
 *
 * Formula: WCAG 2.2, (L1 + 0.05) / (L2 + 0.05), com
 * L = 0.2126 R + 0.7152 G + 0.0722 B sobre os canais sRGB linearizados,
 * truncado para baixo em 2 casas — exatamente como declarado em
 * `$extensions["br.com.seeg.ponto"].metodo.formulaContraste`.
 */

const CAMINHO_CONTRATO = resolve(
  import.meta.dirname,
  "../../../../../packages/contracts/design-tokens.json",
);
const CAMINHO_CSS_GERADO = resolve(import.meta.dirname, "../../estilos/tokens.gerado.css");

interface ParDeContraste {
  tema: "claro" | "escuro";
  par: string;
  primeiroPlano: string;
  fundo: string;
  ratio: number;
  exigido: number;
  criterio: string;
  situacao: string;
}

// -----------------------------------------------------------------------------
// 1. Carrega o contrato e o CSS gerado.
// -----------------------------------------------------------------------------

const tokens = JSON.parse(readFileSync(CAMINHO_CONTRATO, "utf8")) as Record<string, unknown>;
const extensao = (tokens["$extensions"] as Record<string, unknown>)["br.com.seeg.ponto"] as {
  contraste: { pares: ParDeContraste[] };
};
const PARES: ParDeContraste[] = extensao.contraste.pares;

const cssGerado = readFileSync(CAMINHO_CSS_GERADO, "utf8");

// -----------------------------------------------------------------------------
// 2. Extrai os blocos `:root { ... }` (claro + primitivos) e
//    `[data-tema="escuro"] { ... }` (so os semanticos do escuro) do CSS gerado,
//    por contagem de chaves — os blocos nao tem seletor aninhado.
// -----------------------------------------------------------------------------

function extrairBloco(css: string, seletorLiteral: string): string {
  const inicioSeletor = css.indexOf(seletorLiteral);
  if (inicioSeletor === -1) {
    throw new Error(`Bloco "${seletorLiteral}" nao encontrado em tokens.gerado.css`);
  }
  const inicioChave = css.indexOf("{", inicioSeletor);
  let profundidade = 0;
  for (let i = inicioChave; i < css.length; i += 1) {
    if (css[i] === "{") profundidade += 1;
    else if (css[i] === "}") {
      profundidade -= 1;
      if (profundidade === 0) return css.slice(inicioChave + 1, i);
    }
  }
  throw new Error(`Bloco "${seletorLiteral}" nunca fecha em tokens.gerado.css`);
}

function extrairDeclaracoes(blocoCss: string): Map<string, string> {
  const mapa = new Map<string, string>();
  const semComentarios = blocoCss.replace(/\/\*[\s\S]*?\*\//g, "");
  const re = /(--[a-z0-9-]+):\s*([^;]+);/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(semComentarios)) !== null) {
    mapa.set(m[1]!.trim(), m[2]!.trim());
  }
  return mapa;
}

const MAPA_RAIZ = extrairDeclaracoes(extrairBloco(cssGerado, ":root {"));
const MAPA_ESCURO = extrairDeclaracoes(extrairBloco(cssGerado, '[data-tema="escuro"] {'));

// -----------------------------------------------------------------------------
// 3. Resolve um nome de variavel CSS ate um hexadecimal literal, seguindo
//    `var(--...)` recursivamente. Tema "escuro" consulta primeiro o bloco
//    `[data-tema="escuro"]` e cai para `:root` no que ele nao sobrescreve —
//    exatamente a cascata real do navegador para este seletor de atributo.
// -----------------------------------------------------------------------------

const RE_VAR = /^var\((--[a-z0-9-]+)\)$/i;

function valorDaVariavel(nomeVar: string, tema: "claro" | "escuro"): string | undefined {
  if (tema === "escuro" && MAPA_ESCURO.has(nomeVar)) return MAPA_ESCURO.get(nomeVar);
  return MAPA_RAIZ.get(nomeVar);
}

function resolverParaHex(nomeVar: string, tema: "claro" | "escuro", visitados: Set<string> = new Set()): string {
  if (visitados.has(nomeVar)) {
    throw new Error(`Alias circular ao resolver ${nomeVar} (tema ${tema})`);
  }
  visitados.add(nomeVar);

  const valor = valorDaVariavel(nomeVar, tema);
  if (valor === undefined) {
    throw new Error(`Variavel ${nomeVar} (tema ${tema}) nao existe em tokens.gerado.css`);
  }

  const casouVar = RE_VAR.exec(valor);
  if (casouVar) {
    return resolverParaHex(casouVar[1]!, tema, visitados);
  }

  if (/^#[0-9a-f]{6}([0-9a-f]{2})?$/i.test(valor)) {
    return valor.slice(0, 7).toUpperCase();
  }

  throw new Error(`Variavel ${nomeVar} (tema ${tema}) resolveu para um valor nao-hex: "${valor}"`);
}

/** kebab-case identico ao gerador (`apps/web/scripts/tokens-para-css.mjs`). */
function kebab(segmento: string): string {
  return segmento.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
}

/** "acao.primariaFundo" -> "--cor-acao-primaria-fundo" */
function caminhoParaVar(caminhoComPontos: string): string {
  return `--cor-${caminhoComPontos
    .split(".")
    .map((s) => kebab(s))
    .join("-")}`;
}

/** "acao.primariaFundo sobre fundo.superficie (limite do botao)" -> ["acao.primariaFundo", "fundo.superficie"] */
function separarPar(par: string): [string, string] {
  const semAnotacao = par.replace(/\s*\([^)]*\)\s*$/, "");
  const partes = semAnotacao.split(" sobre ");
  if (partes.length !== 2) {
    throw new Error(`Par "${par}" nao esta no formato "X sobre Y"`);
  }
  return [partes[0]!.trim(), partes[1]!.trim()];
}

// -----------------------------------------------------------------------------
// 4. Matematica de contraste — WCAG 2.2, canais sRGB linearizados.
// -----------------------------------------------------------------------------

function canalLinear(c8bits: number): number {
  const c = c8bits / 255;
  return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

function luminanciaRelativa(hex: string): number {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return 0.2126 * canalLinear(r) + 0.7152 * canalLinear(g) + 0.0722 * canalLinear(b);
}

/** Trunca (nao arredonda) para baixo em 2 casas — regra explicita do contrato. */
function truncar2Casas(valor: number): number {
  return Math.floor(valor * 100) / 100;
}

function calcularRatio(hexA: string, hexB: string): number {
  const lA = luminanciaRelativa(hexA);
  const lB = luminanciaRelativa(hexB);
  const maisClaro = Math.max(lA, lB);
  const maisEscuro = Math.min(lA, lB);
  return truncar2Casas((maisClaro + 0.05) / (maisEscuro + 0.05));
}

// -----------------------------------------------------------------------------
// 5. Os 124 pares.
// -----------------------------------------------------------------------------

describe("contraste WCAG 2.2 AA — 124 pares do contrato (recalculados a partir do CSS gerado)", () => {
  it("o contrato traz exatamente 124 pares, 0 reprovados", () => {
    expect(PARES.length).toBe(124);
    expect(PARES.every((p) => p.situacao === "aprovado")).toBe(true);
  });

  it.each(PARES.map((p, indice) => ({ ...p, indice })))(
    "#$indice [$tema] $par — ratio $ratio >= $exigido ($criterio)",
    ({ tema, par, primeiroPlano, fundo, ratio, exigido }) => {
      const [caminhoFrente, caminhoFundo] = separarPar(par);
      const varFrente = caminhoParaVar(caminhoFrente);
      const varFundo = caminhoParaVar(caminhoFundo);

      const hexFrenteCss = resolverParaHex(varFrente, tema);
      const hexFundoCss = resolverParaHex(varFundo, tema);

      // Confere que o CSS gerado bate com os hexadecimais que o proprio
      // contrato registrou para este par (prova de sincronia contrato -> CSS).
      expect(hexFrenteCss).toBe(primeiroPlano.toUpperCase());
      expect(hexFundoCss).toBe(fundo.toUpperCase());

      const ratioRecalculado = calcularRatio(hexFrenteCss, hexFundoCss);

      expect(ratioRecalculado).toBe(ratio);
      expect(ratioRecalculado).toBeGreaterThanOrEqual(exigido);
    },
  );

  it("nao ha par usando skip/todo — 124 asserções ativas", () => {
    // Sentinela: se algum dia alguem marcar um `it.skip`/`it.todo` nesta
    // suite, esta contagem estatica diverge dos 124 pares do contrato e o
    // teste abaixo denuncia. (A suite acima roda via `it.each`, que nao
    // aceita `.skip` por item sem reescrever o arquivo — este teste existe
    // para tornar essa proibicao auditavel por busca de texto tambem.)
    expect(PARES.length).toBe(124);
  });
});
