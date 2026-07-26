import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useEstadoControlavel } from "./use-estado-controlavel";

describe("useEstadoControlavel", () => {
  it("funciona como estado interno quando nao controlado", () => {
    const { result } = renderHook(() => useEstadoControlavel<number>(undefined, 1));
    expect(result.current[0]).toBe(1);

    act(() => {
      result.current[1](2);
    });
    expect(result.current[0]).toBe(2);
  });

  it("o valor controlado sempre vence, mas ainda avisa a mudanca", () => {
    const aoMudar = vi.fn();
    const { result, rerender } = renderHook(
      ({ valor }: { valor: number }) => useEstadoControlavel<number>(valor, 0, aoMudar),
      { initialProps: { valor: 5 } },
    );
    expect(result.current[0]).toBe(5);

    act(() => {
      result.current[1](9);
    });
    // Sem o pai atualizar a prop, o valor exibido continua o controlado.
    expect(aoMudar).toHaveBeenCalledWith(9);
    expect(result.current[0]).toBe(5);

    rerender({ valor: 9 });
    expect(result.current[0]).toBe(9);
  });
});
