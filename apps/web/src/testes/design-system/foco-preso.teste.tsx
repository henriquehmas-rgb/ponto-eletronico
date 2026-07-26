import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Botao } from "@/componentes/ui/button";
import {
  Dialogo,
  DialogoConteudo,
  DialogoDescricao,
  DialogoTitulo,
  DialogoGatilho,
} from "@/componentes/ui/dialog";
import { Folha, FolhaConteudo, FolhaDescricao, FolhaTitulo, FolhaGatilho } from "@/componentes/ui/sheet";

/**
 * T4 do PCF F09a — "teste prova, para dialog e sheet, que o foco entra, fica
 * preso, retorna ao gatilho e que Escape fecha".
 */

describe("Dialogo — foco preso, retorno ao gatilho, Escape fecha", () => {
  it("move o foco para dentro ao abrir e devolve ao gatilho ao fechar com Escape", async () => {
    const usuario = userEvent.setup();
    render(
      <Dialogo>
        <DialogoGatilho asChild>
          <Botao>Abrir tratamento</Botao>
        </DialogoGatilho>
        <DialogoConteudo>
          <DialogoTitulo>Registrar tratamento</DialogoTitulo>
          <DialogoDescricao>Descricao do tratamento.</DialogoDescricao>
          <Botao>Confirmar</Botao>
        </DialogoConteudo>
      </Dialogo>,
    );

    const gatilho = screen.getByRole("button", { name: "Abrir tratamento" });
    gatilho.focus();
    expect(gatilho).toHaveFocus();

    await usuario.click(gatilho);

    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });
    // O Radix move o foco para dentro do conteudo do dialogo assim que ele
    // monta (no proprio conteudo ou no primeiro elemento focavel dele -
    // depende da versao/config; o que importa e que o foco SAIU do gatilho
    // e entrou no dialogo).
    await waitFor(
      () => {
        const dialogo = screen.getByRole("dialog");
        expect(dialogo.contains(document.activeElement)).toBe(true);
      },
      { timeout: 2000 },
    );

    await usuario.keyboard("{Escape}");

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(gatilho).toHaveFocus();
  });

  it("Tab nao escapa do dialogo — o foco fica preso dentro dele", async () => {
    const usuario = userEvent.setup();
    render(
      <Dialogo>
        <DialogoGatilho asChild>
          <Botao>Abrir</Botao>
        </DialogoGatilho>
        <DialogoConteudo>
          <DialogoTitulo>Titulo</DialogoTitulo>
          <DialogoDescricao>Descricao.</DialogoDescricao>
          <Botao>Um</Botao>
          <Botao>Dois</Botao>
        </DialogoConteudo>
      </Dialogo>,
    );

    await usuario.click(screen.getByRole("button", { name: "Abrir" }));
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());

    const dialogo = screen.getByRole("dialog");
    // Percorre bem mais Tabs que o numero de elementos focaveis dentro do
    // dialogo: se o foco escapasse, um elemento fora de `dialogo` receberia
    // foco em algum momento.
    for (let i = 0; i < 8; i += 1) {
      await usuario.tab();
      expect(dialogo.contains(document.activeElement)).toBe(true);
    }
  });
});

describe("Folha — mesmo mecanismo de foco do Dialogo (constroi sobre o mesmo primitivo Radix)", () => {
  it("abre, prende o foco e Escape fecha devolvendo o foco ao gatilho", async () => {
    const usuario = userEvent.setup();
    render(
      <Folha>
        <FolhaGatilho asChild>
          <Botao>Ver vinculo</Botao>
        </FolhaGatilho>
        <FolhaConteudo>
          <FolhaTitulo>Vinculo</FolhaTitulo>
          <FolhaDescricao>Detalhes do vinculo.</FolhaDescricao>
        </FolhaConteudo>
      </Folha>,
    );

    const gatilho = screen.getByRole("button", { name: "Ver vinculo" });
    gatilho.focus();
    await usuario.click(gatilho);

    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
    await waitFor(
      () => {
        const dialogo = screen.getByRole("dialog");
        expect(dialogo.contains(document.activeElement)).toBe(true);
      },
      { timeout: 2000 },
    );

    await usuario.keyboard("{Escape}");

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(gatilho).toHaveFocus();
  });
});
