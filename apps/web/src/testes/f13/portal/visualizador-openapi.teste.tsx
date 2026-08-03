import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { VisualizadorOpenApi } from "@/componentes/desenvolvedores/visualizador-openapi";

const propsCapturadas: {
  requestInterceptor?: ((req: unknown) => unknown) | undefined;
  url?: string | undefined;
} = {};

vi.mock("swagger-ui-react", () => ({
  default: (props: { requestInterceptor?: (req: unknown) => unknown; url?: string }) => {
    propsCapturadas.requestInterceptor = props.requestInterceptor;
    propsCapturadas.url = props.url;
    return <div data-testid="swagger-ui-stub" />;
  },
}));

describe("VisualizadorOpenApi (F13/A2, T7)", () => {
  it("aponta para o proxy /desenvolvedores/api/openapi (nunca o arquivo direto)", async () => {
    render(<VisualizadorOpenApi />);
    await waitFor(() => expect(screen.getByTestId("swagger-ui-stub")).toBeInTheDocument());
    expect(propsCapturadas.url).toBe("/desenvolvedores/api/openapi");
  });

  it("requestInterceptor injeta Authorization quando ha token de sandbox", async () => {
    render(<VisualizadorOpenApi token="token-de-sandbox-abc" />);
    await waitFor(() => expect(propsCapturadas.requestInterceptor).toBeDefined());

    const requisicao = { headers: {} as Record<string, string> };
    const resultado = propsCapturadas.requestInterceptor?.(requisicao) as typeof requisicao;

    expect(resultado.headers.Authorization).toBe("Bearer token-de-sandbox-abc");
  });

  it("requestInterceptor nao mexe nos cabecalhos quando nao ha token (sem sandbox ainda)", async () => {
    render(<VisualizadorOpenApi />);
    await waitFor(() => expect(propsCapturadas.requestInterceptor).toBeDefined());

    const requisicao = { headers: {} as Record<string, string> };
    const resultado = propsCapturadas.requestInterceptor?.(requisicao) as typeof requisicao;

    expect(resultado.headers.Authorization).toBeUndefined();
  });
});
