#!/usr/bin/env node
// =============================================================================
// tokens-para-css.mjs — gerador de CSS custom properties a partir dos tokens
// =============================================================================
// Le  : packages/contracts/design-tokens.json   (W3C Design Tokens / DTCG)
// Grava: apps/web/src/estilos/tokens.gerado.css
//
// Uso:
//   node scripts/tokens-para-css.mjs           grava o arquivo
//   node scripts/tokens-para-css.mjs --check   falha se o arquivo estiver
//                                              desatualizado (gate de CI local)
//
// PRINCIPIO: o arquivo de tokens e a FONTE DA VERDADE congelada da Fase 0.
// Nenhum valor de cor, espacamento, raio, sombra ou tipografia e escrito a mao
// no CSS da aplicacao. Se um valor nao esta em design-tokens.json, ele nao
// existe no produto. Este script e a unica ponte entre os dois mundos.
//
// ESTRUTURA DA SAIDA (nesta ordem):
//   1. :root                      primitivos + tokens agnosticos de tema
//                                 + semanticos do tema CLARO
//                                 + ponte de nomes do shadcn/ui
//   2. [data-tema="escuro"]       so os semanticos do tema ESCURO
//   3. @media (prefers-color-scheme: dark)  mesma coisa, para quem esta sem JS
//   4. .estilo-*                  os 10 estilos tipograficos compostos
//   5. @theme                     fecha as escalas do Tailwind que os tokens
//                                 substituem (`--color-*: initial` etc.)
//   6. @theme inline              expoe os tokens como utilitarios do Tailwind
//
// Por que a ponte do shadcn/ui mora so no :root: ela e feita de indirecoes
// (`--background: var(--cor-fundo-aplicacao)`). Como `--cor-fundo-aplicacao` e
// que muda no bloco escuro, e o var() resolve no momento do uso, a ponte nao
// precisa ser repetida por tema.
// =============================================================================

import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const AQUI = dirname(fileURLToPath(import.meta.url));
const RAIZ_WEB = resolve(AQUI, "..");
const ORIGEM = resolve(RAIZ_WEB, "../../packages/contracts/design-tokens.json");
const DESTINO = resolve(RAIZ_WEB, "src/estilos/tokens.gerado.css");

// -----------------------------------------------------------------------------
// Ponte de nomes: shadcn/ui espera nomes canonicos em ingles. Cada um aponta
// para um token SEMANTICO do tema — nunca para um primitivo, nunca para um
// valor literal. Alterar esta tabela e decisao de design system (F9a), nao de
// andaime; ela existe aqui para que `npx shadcn add <componente>` produza
// componentes ja tematizados pelos tokens, nos dois temas, sem retrabalho.
// -----------------------------------------------------------------------------
const PONTE_SHADCN = {
  background: "fundo.aplicacao",
  foreground: "texto.primario",
  card: "fundo.superficie",
  "card-foreground": "texto.primario",
  popover: "fundo.superficieElevada",
  "popover-foreground": "texto.primario",
  primary: "acao.primariaFundo",
  "primary-foreground": "acao.primariaTexto",
  secondary: "acao.secundariaFundo",
  "secondary-foreground": "acao.secundariaTexto",
  muted: "fundo.sutil",
  "muted-foreground": "texto.secundario",
  accent: "fundo.enfase",
  "accent-foreground": "texto.primario",
  destructive: "acao.destrutivaFundo",
  "destructive-foreground": "acao.destrutivaTexto",
  border: "borda.padrao",
  input: "borda.controle",
  ring: "acao.anelFoco",
  "chart-1": "grafico.serie1",
  "chart-2": "grafico.serie2",
  "chart-3": "grafico.serie3",
  "chart-4": "grafico.serie4",
  "chart-5": "grafico.serie5",
  sidebar: "fundo.superficie",
  "sidebar-foreground": "texto.primario",
  "sidebar-primary": "acao.primariaFundo",
  "sidebar-primary-foreground": "acao.primariaTexto",
  "sidebar-accent": "fundo.sutil",
  "sidebar-accent-foreground": "texto.primario",
  "sidebar-border": "borda.sutil",
  "sidebar-ring": "acao.anelFoco",
};

// Apelidos: nomes que o Tailwind e o shadcn/ui usam por convencao, apontando
// para tokens existentes. Nenhum valor novo nasce aqui — so indirecoes.
const APELIDOS_RAIO = {
  none: "nulo",
  sm: "pequeno",
  md: "medio",
  lg: "grande",
  xl: "grande",
  full: "pleno",
};
const APELIDOS_SOMBRA = { xs: "baixa", sm: "baixa", md: "media", lg: "alta", xl: "alta" };
const APELIDO_TEXTO_BASE = "md"; // `text-base` do Tailwind = tipografia.tamanho.md

// -----------------------------------------------------------------------------
// Utilidades
// -----------------------------------------------------------------------------

/** camelCase -> kebab-case, preservando digitos (`serie1`, `1x5`, `2xl`). */
function kebab(segmento) {
  return String(segmento)
    .replace(/([a-z0-9])([A-Z])/g, "$1-$2")
    .toLowerCase();
}

function ehToken(no) {
  return no !== null && typeof no === "object" && !Array.isArray(no) && "$value" in no;
}

/** Percorre a arvore e devolve [{ caminho: string[], tipo, valor }]. */
function percorrer(no, caminho = []) {
  if (ehToken(no)) return [{ caminho, tipo: no.$type, valor: no.$value }];
  if (no === null || typeof no !== "object" || Array.isArray(no)) return [];
  const saida = [];
  for (const [chave, filho] of Object.entries(no)) {
    if (chave.startsWith("$")) continue;
    saida.push(...percorrer(filho, [...caminho, chave]));
  }
  return saida;
}

/** Le um token pelo caminho pontilhado ("primitivo.cor.neutro.50"). */
function obter(raiz, caminhoPontilhado) {
  let atual = raiz;
  for (const parte of caminhoPontilhado.split(".")) {
    if (atual === undefined || atual === null) return undefined;
    atual = atual[parte];
  }
  return atual;
}

const RE_ALIAS = /^\{([^}]+)\}$/;

/** Resolve um alias DTCG `{a.b.c}` ate chegar num valor concreto. */
function resolverAlias(raiz, valor, visitados = new Set()) {
  if (typeof valor !== "string") return valor;
  const casou = RE_ALIAS.exec(valor.trim());
  if (!casou) return valor;
  const alvo = casou[1];
  if (visitados.has(alvo)) throw new Error(`Alias circular em {${alvo}}`);
  visitados.add(alvo);
  const no = obter(raiz, alvo);
  if (!ehToken(no)) throw new Error(`Alias {${alvo}} nao aponta para um token`);
  return resolverAlias(raiz, no.$value, visitados);
}

// -----------------------------------------------------------------------------
// Conversao DTCG -> CSS
// -----------------------------------------------------------------------------

function dimensaoParaCss(valor) {
  if (typeof valor === "string") return valor;
  if (valor && typeof valor === "object" && "value" in valor) {
    return `${valor.value}${valor.unit ?? ""}`;
  }
  return String(valor);
}

function familiaParaCss(valor) {
  const lista = Array.isArray(valor) ? valor : [valor];
  return lista.map((n) => (/[^A-Za-z0-9-]/.test(n) ? `"${n}"` : n)).join(", ");
}

function sombraParaCss(raiz, valor) {
  const camadas = Array.isArray(valor) ? valor : [valor];
  return camadas
    .map((c) => {
      const cor = resolverAlias(raiz, c.color);
      const partes = [
        dimensaoParaCss(c.offsetX),
        dimensaoParaCss(c.offsetY),
        dimensaoParaCss(c.blur),
        dimensaoParaCss(c.spread),
        cor,
      ];
      return (c.inset ? ["inset", ...partes] : partes).join(" ");
    })
    .join(", ");
}

/**
 * Converte um token para o texto CSS do lado direito da declaracao.
 * `refPrimitivo` transforma alias de cor em `var(--primitivo-...)`, preservando
 * a rastreabilidade semantico -> primitivo dentro do proprio CSS.
 */
function valorCss(raiz, tipo, valorBruto, { refPrimitivo = false } = {}) {
  if (refPrimitivo && typeof valorBruto === "string") {
    const casou = RE_ALIAS.exec(valorBruto.trim());
    if (casou) return `var(--${casou[1].split(".").map(kebab).join("-")})`;
  }
  const valor = resolverAlias(raiz, valorBruto);
  switch (tipo) {
    case "color":
      return String(valor);
    case "dimension":
    case "duration":
      return dimensaoParaCss(valor);
    case "fontFamily":
      return familiaParaCss(valor);
    case "fontWeight":
    case "number":
      return String(valor);
    case "cubicBezier":
      return `cubic-bezier(${valor.join(", ")})`;
    case "shadow":
      return sombraParaCss(raiz, valor);
    default:
      return String(valor);
  }
}

// -----------------------------------------------------------------------------
// Emissao
// -----------------------------------------------------------------------------

const nomeVar = (caminho) => `--${caminho.map(kebab).join("-")}`;

function bloco(seletor, linhas, indent = "  ") {
  return [`${seletor} {`, ...linhas.map((l) => (l ? indent + l : "")), "}"].join("\n");
}

function gerar(tokens) {
  const ext = tokens.$extensions?.["br.com.seeg.ponto"] ?? {};
  const linhasClaro = [];
  const linhasEscuro = [];

  // --- 1. primitivos ---------------------------------------------------------
  linhasClaro.push("/* --- primitivos: valores crus. Nao consuma direto na interface. --- */");
  for (const { caminho, tipo, valor } of percorrer(tokens.primitivo, ["primitivo"])) {
    linhasClaro.push(`${nomeVar(caminho)}: ${valorCss(tokens, tipo, valor)};`);
  }

  // --- 2. tokens agnosticos de tema ------------------------------------------
  const gruposGlobais = [
    ["tipografia", "tipografia"],
    ["espacamento", "espacamento"],
    ["raio", "raio"],
    ["movimento", "movimento"],
    ["camada", "camada"],
    ["pontoQuebra", "ponto de quebra"],
    ["dimensao", "dimensao"],
  ];
  for (const [grupo, rotulo] of gruposGlobais) {
    linhasClaro.push("", `/* --- ${rotulo} --- */`);
    for (const { caminho, tipo, valor } of percorrer(tokens[grupo], [grupo])) {
      // Os estilos compostos viram classes (secao 4), nao custom properties.
      if (tipo === "typography") continue;
      linhasClaro.push(`${nomeVar(caminho)}: ${valorCss(tokens, tipo, valor)};`);
    }
  }

  // --- 3. semanticos por tema ------------------------------------------------
  const semanticos = percorrer(tokens.tema.claro).map(({ caminho }) => caminho);
  const caminhosEscuro = new Set(percorrer(tokens.tema.escuro).map((t) => t.caminho.join(".")));
  for (const caminho of semanticos) {
    if (!caminhosEscuro.has(caminho.join("."))) {
      throw new Error(`Token ${caminho.join(".")} existe no tema claro e falta no escuro`);
    }
  }

  const emitirTema = (tema) => {
    const saida = [];
    let grupoAtual = null;
    for (const caminho of semanticos) {
      if (caminho[0] !== grupoAtual) {
        grupoAtual = caminho[0];
        saida.push(saida.length ? "" : null, `/* --- ${grupoAtual} --- */`);
      }
      const no = obter(tokens.tema[tema], caminho.join("."));
      const prefixo = no.$type === "shadow" ? "sombra" : "cor";
      const nome =
        no.$type === "shadow"
          ? `--sombra-${caminho.slice(1).map(kebab).join("-")}`
          : `--${prefixo}-${caminho.map(kebab).join("-")}`;
      saida.push(`${nome}: ${valorCss(tokens, no.$type, no.$value, { refPrimitivo: true })};`);
    }
    return saida.filter((l) => l !== null);
  };

  linhasClaro.push("", "/* ======== tema CLARO (padrao) ======== */", ...emitirTema("claro"));
  linhasEscuro.push(...emitirTema("escuro"));

  // --- 4. ponte shadcn/ui ----------------------------------------------------
  linhasClaro.push(
    "",
    "/* --- ponte shadcn/ui: indirecao pura, valida nos dois temas --- */",
    "--radius: var(--raio-medio);",
  );
  for (const [nome, alvo] of Object.entries(PONTE_SHADCN)) {
    if (!obter(tokens.tema.claro, alvo)) {
      throw new Error(`Ponte shadcn "${nome}" aponta para tema.claro.${alvo}, que nao existe`);
    }
    linhasClaro.push(`--${nome}: var(--cor-${alvo.split(".").map(kebab).join("-")});`);
  }

  // --- 5. estilos tipograficos compostos -------------------------------------
  const classesEstilo = [];
  for (const [nome, no] of Object.entries(tokens.tipografia.estilo)) {
    if (!ehToken(no)) continue;
    const v = no.$value;
    const ref = (alias) => `var(--${alias.replace(/[{}]/g, "").split(".").map(kebab).join("-")})`;
    classesEstilo.push(
      bloco(`.estilo-${kebab(nome)}`, [
        `font-family: ${ref(v.fontFamily)};`,
        `font-size: ${ref(v.fontSize)};`,
        `font-weight: ${ref(v.fontWeight)};`,
        `line-height: ${ref(v.lineHeight)};`,
        `letter-spacing: ${ref(v.letterSpacing)};`,
      ]),
    );
  }

  // --- 6. mapeamento para o Tailwind v4 --------------------------------------
  const inline = [];
  const push = (rotulo, linhas) => inline.push("", `/* ${rotulo} */`, ...linhas);

  const coresTema = semanticos
    .filter((c) => obter(tokens.tema.claro, c.join(".")).$type === "color")
    .map((c) => {
      const k = c.map(kebab).join("-");
      return `--color-${k}: var(--cor-${k});`;
    });
  push("cores semanticas do tema ativo", coresTema);

  const coresPrimitivas = percorrer(tokens.primitivo.cor, ["primitivo", "cor"]).map(
    ({ caminho }) => {
      const k = caminho.slice(2).map(kebab).join("-");
      return `--color-${k}: var(${nomeVar(caminho)});`;
    },
  );
  push("rampas primitivas (uso restrito: ilustracao, grafico, depuracao)", coresPrimitivas);

  push(
    "ponte shadcn/ui",
    Object.keys(PONTE_SHADCN).map((n) => `--color-${n}: var(--${n});`),
  );

  push("familias tipograficas", [
    "--font-sans: var(--tipografia-familia-sans);",
    "--font-mono: var(--tipografia-familia-mono);",
  ]);

  push("tamanhos de texto", [
    ...Object.keys(tokens.tipografia.tamanho)
      .filter((k) => !k.startsWith("$"))
      .flatMap((k) => [
        `--text-${kebab(k)}: var(--tipografia-tamanho-${kebab(k)});`,
        `--text-${kebab(k)}--line-height: var(--tipografia-altura-linha-${kebab(k)});`,
        `--text-${kebab(k)}--letter-spacing: var(--tipografia-rastreio-${kebab(k)});`,
      ]),
    `--text-base: var(--tipografia-tamanho-${APELIDO_TEXTO_BASE});`,
    `--text-base--line-height: var(--tipografia-altura-linha-${APELIDO_TEXTO_BASE});`,
    `--text-base--letter-spacing: var(--tipografia-rastreio-${APELIDO_TEXTO_BASE});`,
  ]);

  push("pesos, alturas de linha e rastreio como utilitarios independentes", [
    ...Object.keys(tokens.tipografia.peso)
      .filter((k) => !k.startsWith("$"))
      .map((k) => `--font-weight-${kebab(k)}: var(--tipografia-peso-${kebab(k)});`),
    ...Object.keys(tokens.tipografia.alturaLinha)
      .filter((k) => !k.startsWith("$"))
      .map((k) => `--leading-${kebab(k)}: var(--tipografia-altura-linha-${kebab(k)});`),
    ...Object.keys(tokens.tipografia.rastreio)
      .filter((k) => !k.startsWith("$"))
      .map((k) => `--tracking-${kebab(k)}: var(--tipografia-rastreio-${kebab(k)});`),
  ]);

  push("raio", [
    ...Object.keys(tokens.raio)
      .filter((k) => !k.startsWith("$"))
      .map((k) => `--radius-${kebab(k)}: var(--raio-${kebab(k)});`),
    ...Object.entries(APELIDOS_RAIO).map(([ap, t]) => `--radius-${ap}: var(--raio-${kebab(t)});`),
  ]);

  push("sombra", [
    ...Object.keys(tokens.tema.claro.sombra)
      .filter((k) => !k.startsWith("$"))
      .map((k) => `--shadow-${kebab(k)}: var(--sombra-${kebab(k)});`),
    ...Object.entries(APELIDOS_SOMBRA).map(
      ([ap, t]) => `--shadow-${ap}: var(--sombra-${kebab(t)});`,
    ),
  ]);

  push("curvas e duracoes de movimento", [
    ...Object.keys(tokens.movimento.curva)
      .filter((k) => !k.startsWith("$"))
      .map((k) => `--ease-${kebab(k)}: var(--movimento-curva-${kebab(k)});`),
    ...Object.keys(tokens.movimento.duracao)
      .filter((k) => !k.startsWith("$"))
      .map((k) => `--duration-${kebab(k)}: var(--movimento-duracao-${kebab(k)});`),
  ]);

  // --- 7. valores que NAO podem ser var() ------------------------------------
  // Media query e container query nao aceitam var(): `@media (width >= var(--x))`
  // e sintaxe invalida e derruba o build do Tailwind. Estes dois grupos, e so
  // eles, saem com o valor literal ja resolvido a partir do contrato.
  const literais = [
    "/* pontos de quebra — literais: @media nao resolve var() */",
    ...Object.entries(tokens.pontoQuebra)
      .filter(([k]) => !k.startsWith("$"))
      .map(([k, no]) => `--breakpoint-${kebab(k)}: ${valorCss(tokens, no.$type, no.$value)};`),
    "",
    "/* larguras de container — literais: @container nao resolve var() */",
    ...["larguraMaximaTexto", "larguraMaximaConteudo", "larguraBarraLateral"].map((k) => {
      const no = tokens.dimensao[k];
      return `--container-${kebab(k)}: ${valorCss(tokens, no.$type, no.$value)};`;
    }),
  ];

  // --- cabecalho -------------------------------------------------------------
  const contagem = {
    primitivos: percorrer(tokens.primitivo, ["primitivo"]).length,
    semanticosPorTema: semanticos.length,
    variaveisTailwind: inline.filter((l) => l.startsWith("--")).length,
  };

  const cabecalho = `/* ===========================================================================
 * ARQUIVO GERADO — NAO EDITE A MAO.
 * ===========================================================================
 * Origem : packages/contracts/design-tokens.json (congelado na Fase 0)
 * Gerador: apps/web/scripts/tokens-para-css.mjs
 * Regerar: pnpm tokens        Conferir: pnpm tokens:check
 *
 * Qualquer edicao feita aqui e perdida na proxima geracao. Para mudar um
 * valor, mude o token no contrato — e isso exige RFC aprovada
 * (protocolo em FASES-E-AGENTES.md secao 1.3).
 *
 * Versao dos tokens : ${ext.versao ?? "?"} (${ext.atualizadoEm ?? "?"})
 * Primitivos        : ${contagem.primitivos}
 * Semanticos/tema   : ${contagem.semanticosPorTema} (identicos em claro e escuro)
 * Vars do Tailwind  : ${contagem.variaveisTailwind}
 *
 * Troca de tema: o atributo data-tema no elemento <html> manda. O bloco
 * @media prefers-color-scheme so vale quando data-tema esta ausente — caso
 * de JavaScript desligado. Ver src/componentes/tema/script-tema.tsx.
 * =========================================================================== */`;

  const recuar = (texto) =>
    texto
      .split("\n")
      .map((l) => (l ? "  " + l : l))
      .join("\n");

  const partes = [
    cabecalho,
    "",
    bloco(":root", ["color-scheme: light;", "", ...linhasClaro]),
    "",
    "/* ======== tema ESCURO — escolha explicita do usuario ======== */",
    bloco('[data-tema="escuro"]', ["color-scheme: dark;", "", ...linhasEscuro]),
    "",
    "/* ======== tema ESCURO — preferencia do sistema, sem JavaScript ======== */",
    "@media (prefers-color-scheme: dark) {",
    recuar(bloco(":root:not([data-tema])", ["color-scheme: dark;", "", ...linhasEscuro])),
    "}",
    "",
    "/* ======== estilos tipograficos compostos do contrato ======== */",
    "@layer components {",
    recuar(classesEstilo.join("\n\n")),
    "}",
    "",
    "/* ===========================================================================\n" +
      " * Fechamento das escalas padrao do Tailwind.\n" +
      " *\n" +
      " * --color-*: initial apaga a paleta que vem de fabrica: depois disto, a unica\n" +
      " * cor que existe no produto e a que saiu do contrato. O mesmo vale para raio,\n" +
      " * sombra, tamanho de texto, ponto de quebra e curva de movimento.\n" +
      " *\n" +
      " * A escala de espacamento (--spacing, base 4px) e MANTIDA de proposito: ela e\n" +
      " * calculada, nao escolhida a dedo, e a grade de 8 pt do contrato e um\n" +
      " * subconjunto exato dela (todo valor de espacamento.* e multiplo de 4px). Os\n" +
      " * valores nomeados do contrato seguem disponiveis como var(--espacamento-*).\n" +
      " * Idem para --container-*, que so alimenta max-w-* e nao e paleta.\n" +
      " * =========================================================================== */",
    bloco("@theme", [
      "--color-*: initial;",
      "--radius-*: initial;",
      "--shadow-*: initial;",
      "--inset-shadow-*: initial;",
      "--drop-shadow-*: initial;",
      "--text-*: initial;",
      "--leading-*: initial;",
      "--tracking-*: initial;",
      "--breakpoint-*: initial;",
      "--ease-*: initial;",
      "--font-serif: initial;",
      "",
      ...literais,
    ]),
    "",
    `/* ===========================================================================
 * Ponte para o Tailwind v4. \`inline\` e obrigatorio: sem ele o Tailwind
 * congelaria o valor no momento do build e a troca de tema em runtime nao
 * teria efeito nenhum sobre os utilitarios.
 * =========================================================================== */`,
    bloco(
      "@theme inline",
      inline.filter((l, i) => !(l === "" && i === 0)),
    ),
    "",
  ];

  return partes.join("\n");
}

// -----------------------------------------------------------------------------
// Execucao
// -----------------------------------------------------------------------------

function principal() {
  const conferir = process.argv.includes("--check");

  if (!existsSync(ORIGEM)) {
    console.error(`ERRO: contrato de tokens nao encontrado em ${ORIGEM}`);
    process.exit(1);
  }

  const tokens = JSON.parse(readFileSync(ORIGEM, "utf8"));
  const css = gerar(tokens);
  const digest = createHash("sha256").update(css).digest("hex").slice(0, 12);

  if (conferir) {
    if (!existsSync(DESTINO)) {
      console.error("ERRO: src/estilos/tokens.gerado.css nao existe. Rode `pnpm tokens`.");
      process.exit(1);
    }
    const atual = readFileSync(DESTINO, "utf8").replace(/\r\n/g, "\n");
    if (atual !== css) {
      console.error(
        "ERRO: src/estilos/tokens.gerado.css esta desatualizado em relacao a\n" +
          "      packages/contracts/design-tokens.json. Rode `pnpm tokens`.",
      );
      process.exit(1);
    }
    console.log(`tokens.gerado.css em dia (sha256:${digest}).`);
    return;
  }

  mkdirSync(dirname(DESTINO), { recursive: true });
  writeFileSync(DESTINO, css, "utf8");
  const linhas = css.split("\n").length;
  const vars = (css.match(/^\s*--[a-z0-9-]+(?:\*)?:/gm) ?? []).length;
  console.log(`gerado  : ${DESTINO}`);
  console.log(`origem  : ${ORIGEM}`);
  console.log(`linhas  : ${linhas}`);
  console.log(`declaracoes de custom property: ${vars}`);
  console.log(`sha256  : ${digest}`);
}

principal();
