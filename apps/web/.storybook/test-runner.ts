import { getViolations, injectAxe } from "axe-playwright";

import { getStoryContext, type TestRunnerConfig } from "@storybook/test-runner";

/**
 * Gate automatico de acessibilidade (T1 do PCF F09a).
 *
 * Para CADA historia, roda o axe-core DUAS vezes na MESMA visita de pagina —
 * uma com `data-tema="claro"`, outra com `data-tema="escuro"` — porque o
 * requisito do PCF e "todas as historias, nos dois temas", e o tema escuro
 * NAO e uma inversao do claro (tokens medidos separadamente): uma violacao de
 * contraste pode existir em um tema e nao no outro.
 *
 * Alternar o atributo diretamente (em vez de navegar duas vezes com
 * `globals=tema:X` na URL) evita depender da ordem interna de navegacao do
 * test-runner e mantem os dois testes na mesma execucao do axe.
 *
 * So falha em violacao de severidade `serious` ou `critical` (regra do PCF —
 * critério 3 da §7): `minor` e `moderate` aparecem no relatorio do addon-a11y
 * dentro do proprio Storybook para triagem manual, mas nao derrubam o build.
 */

const TEMAS = ["claro", "escuro"] as const;
const GRAVIDADES_QUE_REPROVAM = new Set(["serious", "critical"]);
const SELETOR_RAIZ_DA_HISTORIA = "#storybook-root";

const config: TestRunnerConfig = {
  async preVisit(page) {
    await injectAxe(page);
  },

  async postVisit(page, context) {
    const contextoDaHistoria = await getStoryContext(page, context);

    // Historia pode se auto-excluir do gate (ex.: story deliberadamente
    // decorativa) via `parameters.a11y.disable` — mecanismo padrao do
    // addon-a11y, reaproveitado aqui.
    if (contextoDaHistoria.parameters?.["a11y"]?.disable) return;

    const opcoesDoAxe = contextoDaHistoria.parameters?.["a11y"]?.axeOptions;
    const falhasPorTema: string[] = [];

    for (const tema of TEMAS) {
      await page.evaluate((t: string) => {
        document.documentElement.setAttribute("data-tema", t);
        document.documentElement.style.colorScheme = t === "escuro" ? "dark" : "light";
      }, tema);

      // Da tempo dos custom properties (tema.<t>.*) assentarem antes do axe
      // medir contraste computado.
      await page.waitForTimeout(60);

      const violacoes = await getViolations(page, SELETOR_RAIZ_DA_HISTORIA, opcoesDoAxe);
      const graves = violacoes.filter((v) => GRAVIDADES_QUE_REPROVAM.has(v.impact ?? ""));

      if (graves.length > 0) {
        const detalhe = graves
          .map((v) => {
            const alvos = v.nodes
              .slice(0, 3)
              .map((n) => n.target.join(" "))
              .join("; ");
            return `    [${v.impact}] ${v.id} — ${v.help} (${v.nodes.length} nó(s): ${alvos})`;
          })
          .join("\n");
        falhasPorTema.push(`  tema "${tema}":\n${detalhe}`);
      }
    }

    if (falhasPorTema.length > 0) {
      throw new Error(
        `Violação(ões) de acessibilidade serious/critical em "${context.title} > ${context.name}":\n` +
          falhasPorTema.join("\n"),
      );
    }
  },
};

export default config;
