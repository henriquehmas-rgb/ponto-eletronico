import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

/**
 * O jsdom nao implementa `matchMedia`, e o provedor de tema depende dele para
 * resolver a preferencia `sistema`. Sem este stub o teste quebra por falta de
 * API do navegador, e nao por defeito do componente.
 */
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((consulta: string) => ({
    matches: false,
    media: consulta,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

/**
 * O jsdom não implementa a Pointer Events API (`hasPointerCapture`,
 * `setPointerCapture`, `releasePointerCapture`) nem `scrollIntoView`. O
 * `Selecao` (`@radix-ui/react-select`, F9a) depende dessas chamadas mesmo em
 * navegação por teclado/clique — sem este stub, qualquer teste que interaja
 * com um `<Selecao>` via `@testing-library/user-event` quebra por falta de
 * API do navegador, não por defeito do componente (F8, T4).
 */
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = () => undefined;
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => undefined;
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => undefined;
}

afterEach(() => {
  cleanup();
});
