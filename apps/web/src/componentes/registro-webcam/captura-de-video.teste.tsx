import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CapturaDeVideo } from "./captura-de-video";

describe("CapturaDeVideo", () => {
  it("mostra o estado de carregamento enquanto aguarda a permissão", () => {
    render(<CapturaDeVideo estado="solicitando" stream={null} />);
    expect(screen.getByRole("status")).toHaveTextContent(/aguardando permissão/i);
  });

  it("mostra mensagem clara quando a permissão é negada, com ação de tentar novamente", async () => {
    const usuario = userEvent.setup();
    const aoSolicitarNovamente = vi.fn();
    render(
      <CapturaDeVideo estado="negada" stream={null} aoSolicitarNovamente={aoSolicitarNovamente} />,
    );

    expect(screen.getByText(/permissão de câmera negada/i)).toBeInTheDocument();
    await usuario.click(screen.getByRole("button", { name: /tentar novamente/i }));
    expect(aoSolicitarNovamente).toHaveBeenCalledTimes(1);
  });

  it("mostra mensagem clara quando a câmera está indisponível", () => {
    render(<CapturaDeVideo estado="indisponivel" stream={null} />);
    expect(screen.getByText(/câmera indisponível/i)).toBeInTheDocument();
  });

  it("renderiza o elemento <video> ao vivo quando a permissão é concedida", () => {
    const { container } = render(<CapturaDeVideo estado="concedida" stream={null} />);
    const video = container.querySelector("video");
    expect(video).toBeInTheDocument();
    expect(video).toHaveAttribute("autoplay");
    // React aplica `muted` como propriedade do DOM, não como atributo HTML
    // refletido — por isso a asserção é na propriedade, não em `toHaveAttribute`.
    expect((video as HTMLVideoElement).muted).toBe(true);
  });

  it("NUNCA renderiza um input de upload de arquivo, em nenhum estado (critério 4 da §7)", () => {
    for (const estado of ["solicitando", "negada", "indisponivel", "concedida"] as const) {
      const { container, unmount } = render(<CapturaDeVideo estado={estado} stream={null} />);
      expect(container.querySelector('input[type="file"]')).not.toBeInTheDocument();
      unmount();
    }
  });
});
