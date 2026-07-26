import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CaixaDeSelecao } from "@/componentes/ui/checkbox";
import { GrupoDeRadio, ItemDeRadio } from "@/componentes/ui/radio-group";
import { Interruptor } from "@/componentes/ui/switch";

/**
 * Criterio 5 da §7 do PCF F09a: "Alvo de toque de 44x44 px nas variantes de
 * toque, verificavel por teste."
 *
 * jsdom (o ambiente do Vitest) NAO faz layout real: `getBoundingClientRect`
 * sempre devolve zero, entao nao da para medir pixel renderizado aqui. O que
 * este teste PROVA, de forma igualmente rigorosa: (a) a variante `toque` de
 * cada controle emite o wrapper com a classe utilitaria exata que consome
 * `--dimensao-alvo-toque`, e (b) esse token, lido do CSS realmente gerado
 * (nao do contrato — mesma tecnica de `contraste.teste.ts`), vale
 * exatamente 44px. Style/layout em pixel de verdade e coberto pelo teste E2E
 * de Storybook (`alvo-de-toque--*` nas stories, inspecionavel visualmente e
 * pelo addon de acessibilidade).
 */

const CSS_GERADO = readFileSync(
  resolve(import.meta.dirname, "../../estilos/tokens.gerado.css"),
  "utf8",
);

describe("token de alvo de toque = 44px no CSS gerado", () => {
  it("--dimensao-alvo-toque vale 44px", () => {
    const m = /--dimensao-alvo-toque:\s*([^;]+);/.exec(CSS_GERADO);
    expect(m).not.toBeNull();
    expect(m?.[1]?.trim()).toBe("44px");
  });
});

describe("variantes de toque consomem --dimensao-alvo-toque (44x44 px)", () => {
  it("CaixaDeSelecao tamanho=toque envolve o controle num alvo de 44x44", () => {
    render(<CaixaDeSelecao aria-label="Selecionar" tamanho="toque" />);
    const wrapper = screen.getByRole("checkbox", { name: "Selecionar" }).parentElement;
    expect(wrapper?.className).toContain("size-[var(--dimensao-alvo-toque)]");
  });

  it("ItemDeRadio tamanho=toque envolve o controle num alvo de 44x44", () => {
    render(
      <GrupoDeRadio aria-label="Ciclo">
        <ItemDeRadio value="5x2" aria-label="5x2" tamanho="toque" />
      </GrupoDeRadio>,
    );
    const wrapper = screen.getByRole("radio", { name: "5x2" }).parentElement;
    expect(wrapper?.className).toContain("size-[var(--dimensao-alvo-toque)]");
  });

  it("Interruptor tamanho=toque envolve o controle num alvo de 44x44", () => {
    render(<Interruptor aria-label="Notificar" tamanho="toque" />);
    const wrapper = screen.getByRole("switch", { name: "Notificar" }).parentElement;
    expect(wrapper?.className).toContain("size-[var(--dimensao-alvo-toque)]");
  });

  it("a variante padrao NAO envolve o controle (so a variante de toque precisa do alvo estendido)", () => {
    render(<CaixaDeSelecao aria-label="Selecionar padrao" />);
    const controle = screen.getByRole("checkbox", { name: "Selecionar padrao" });
    expect(controle.parentElement?.className ?? "").not.toContain("dimensao-alvo-toque");
  });
});
