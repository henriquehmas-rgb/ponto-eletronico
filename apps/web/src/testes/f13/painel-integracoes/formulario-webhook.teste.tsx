import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { FormularioWebhook } from "@/componentes/paineis/integracoes/formulario-webhook";

/**
 * Formulário de criação/edição de webhook (T14, F13/A4).
 *
 * Estes testes exercitam só a validação client-side (zod) e a montagem do
 * corpo enviado — não dependem da API real (A3 pode ainda não ter terminado
 * o motor de entrega; PCF F13 §5.1, "pode desenvolver contra o schema do
 * contrato/mock").
 */

/** O jsdom não implementa `ResizeObserver`, usado pelo `Checkbox` Radix
 * (grade de eventos) — mesmo stub de
 * `testes/paineis/dashboard/secao-apuracao.teste.tsx` (F9a). */
class ResizeObserverForjado {
  private aoRedimensionar: ResizeObserverCallback;
  constructor(aoRedimensionar: ResizeObserverCallback) {
    this.aoRedimensionar = aoRedimensionar;
  }
  observe(alvo: Element) {
    const entrada = {
      target: alvo,
      contentRect: {
        width: (alvo as HTMLElement).offsetWidth,
        height: (alvo as HTMLElement).offsetHeight,
      },
    } as ResizeObserverEntry;
    this.aoRedimensionar([entrada], this as unknown as ResizeObserver);
  }
  unobserve() {}
  disconnect() {}
}

beforeAll(() => {
  vi.stubGlobal("ResizeObserver", ResizeObserverForjado);
});

describe("FormularioWebhook (T14)", () => {
  it("submeter vazio mostra as três validações obrigatórias e não chama aoSalvar", async () => {
    const aoSalvar = vi.fn();
    const usuario = userEvent.setup();
    render(
      <FormularioWebhook
        webhook={null}
        salvando={false}
        aoSalvar={aoSalvar}
        aoCancelar={vi.fn()}
      />,
    );

    await usuario.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => {
      expect(screen.getByText("Informe o nome do webhook.")).toBeInTheDocument();
      expect(screen.getByText("Informe a URL de destino.")).toBeInTheDocument();
      expect(screen.getByText("Selecione ao menos um evento.")).toBeInTheDocument();
    });
    expect(aoSalvar).not.toHaveBeenCalled();
  });

  it("URL sem HTTPS é recusada antes de chamar a API (PONTO-WEBH-001 é validação de servidor, mas o cliente evita a viagem)", async () => {
    const aoSalvar = vi.fn();
    const usuario = userEvent.setup();
    render(
      <FormularioWebhook
        webhook={null}
        salvando={false}
        aoSalvar={aoSalvar}
        aoCancelar={vi.fn()}
      />,
    );

    await usuario.type(screen.getByLabelText(/Nome/), "Meu webhook");
    await usuario.type(screen.getByLabelText(/URL de destino/), "http://exemplo.com/webhook");
    await usuario.click(screen.getByRole("checkbox", { name: /Marcação criada/ }));
    await usuario.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => {
      expect(screen.getByText(/precisa ser HTTPS/)).toBeInTheDocument();
    });
    expect(aoSalvar).not.toHaveBeenCalled();
  });

  it("formulário válido chama aoSalvar com nome/url/eventos preenchidos", async () => {
    const aoSalvar = vi.fn();
    const usuario = userEvent.setup();
    render(
      <FormularioWebhook
        webhook={null}
        salvando={false}
        aoSalvar={aoSalvar}
        aoCancelar={vi.fn()}
      />,
    );

    await usuario.type(screen.getByLabelText(/Nome/), "Meu webhook");
    await usuario.type(screen.getByLabelText(/URL de destino/), "https://exemplo.com/webhook");
    await usuario.click(screen.getByRole("checkbox", { name: /Marcação criada/ }));
    await usuario.click(screen.getByRole("checkbox", { name: /Período fechado/ }));
    await usuario.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(aoSalvar).toHaveBeenCalledTimes(1));
    const valores = aoSalvar.mock.calls[0]?.[0];
    expect(valores.nome).toBe("Meu webhook");
    expect(valores.url).toBe("https://exemplo.com/webhook");
    expect(valores.eventos).toEqual(expect.arrayContaining(["marcacao.criada", "periodo.fechado"]));
  });

  it("cabeçalhos extras com JSON inválido bloqueia o envio", async () => {
    const aoSalvar = vi.fn();
    const usuario = userEvent.setup();
    render(
      <FormularioWebhook
        webhook={null}
        salvando={false}
        aoSalvar={aoSalvar}
        aoCancelar={vi.fn()}
      />,
    );

    await usuario.type(screen.getByLabelText(/Nome/), "Meu webhook");
    await usuario.type(screen.getByLabelText(/URL de destino/), "https://exemplo.com/webhook");
    await usuario.click(screen.getByRole("checkbox", { name: /Marcação criada/ }));
    // `{{` é a forma de escapar uma chave literal na sintaxe de teclado do
    // `@testing-library/user-event` (uma chave sozinha abriria uma sequência
    // de tecla especial, ex. "{enter}").
    await usuario.type(screen.getByLabelText(/Cabeçalhos extras/), "{{invalido");
    await usuario.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => {
      expect(screen.getByText(/JSON válido/)).toBeInTheDocument();
    });
    expect(aoSalvar).not.toHaveBeenCalled();
  });

  it("editando um webhook existente pré-preenche os campos e mostra o seletor de situação", () => {
    render(
      <FormularioWebhook
        webhook={{
          id: "wh-1",
          nome: "Webhook existente",
          url: "https://exemplo.com/hook",
          eventos: ["marcacao.criada"],
          status: "suspenso",
          maxTentativas: 8,
          timeoutSegundos: 10,
        }}
        salvando={false}
        aoSalvar={vi.fn()}
        aoCancelar={vi.fn()}
      />,
    );

    expect(screen.getByLabelText(/Nome/)).toHaveValue("Webhook existente");
    expect(screen.getByLabelText(/URL de destino/)).toHaveValue("https://exemplo.com/hook");
    expect(screen.getByRole("checkbox", { name: /Marcação criada/ })).toBeChecked();
    expect(screen.getByText("Situação")).toBeInTheDocument();
  });
});
