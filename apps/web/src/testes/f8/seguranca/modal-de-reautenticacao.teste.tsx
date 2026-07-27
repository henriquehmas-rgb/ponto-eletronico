import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ModalDeReautenticacao } from "@/componentes/seguranca/modal-de-reautenticacao";
import { api, ErroDaApi } from "@/lib/api";
import {
  comAcessoControlado,
  definirSolicitadorDeReautenticacao,
} from "@/lib/seguranca/com-acesso-controlado";

/**
 * T12 do PCF F08 (componente). Mesmos critérios de "Pronto quando" que
 * `use-reautenticacao.teste.ts`, mas exercitados pela árvore de UI real —
 * prova que o `Dialogo` da F9a está corretamente ligado ao gancho.
 */

function mockarGet(dados: Record<string, unknown> = {}): void {
  const implementacao = (async () => ({ data: dados })) as unknown as typeof api.GET;
  vi.spyOn(api, "GET").mockImplementation(implementacao);
}

function erroReautenticacaoNecessaria(): ErroDaApi {
  return new ErroDaApi(401, {
    type: "https://docs.ponto.seeg.com.br/erros/PONTO-AUTH-011",
    title: "Reautenticação necessária",
    status: 401,
    codigo: "PONTO-AUTH-011",
  });
}

afterEach(() => {
  definirSolicitadorDeReautenticacao(undefined);
  vi.restoreAllMocks();
});

describe("ModalDeReautenticacao", () => {
  it("não aparece antes de ser solicitado", () => {
    mockarGet();
    render(<ModalDeReautenticacao />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("abre automaticamente ao interceptar PONTO-AUTH-011 e, confirmado, fecha e resolve a operação original", async () => {
    mockarGet();
    render(<ModalDeReautenticacao />);
    const usuario = userEvent.setup();

    const chamadaOriginal = vi
      .fn()
      .mockRejectedValueOnce(erroReautenticacaoNecessaria())
      .mockResolvedValueOnce("marcacao-criada");

    let promessaDaOperacao!: Promise<string>;
    act(() => {
      promessaDaOperacao = comAcessoControlado(chamadaOriginal);
    });

    expect(await screen.findByRole("dialog")).toBeInTheDocument();

    const implementacaoPost = (async () => ({
      data: {
        reautenticadoEm: "2026-07-26T10:00:00-03:00",
        validoAte: "2026-07-26T10:15:00-03:00",
      },
    })) as unknown as typeof api.POST;
    vi.spyOn(api, "POST").mockImplementation(implementacaoPost);

    await usuario.type(screen.getByLabelText("Senha"), "senha-correta");
    await usuario.click(screen.getByRole("button", { name: "Confirmar" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await expect(promessaDaOperacao).resolves.toBe("marcacao-criada");
    expect(chamadaOriginal).toHaveBeenCalledTimes(2);
  });

  it("senha incorreta mostra a mensagem do dicionário sem fechar o modal", async () => {
    mockarGet();
    render(<ModalDeReautenticacao />);
    const usuario = userEvent.setup();

    act(() => {
      void comAcessoControlado(() => Promise.reject(erroReautenticacaoNecessaria()));
    });
    expect(await screen.findByRole("dialog")).toBeInTheDocument();

    vi.spyOn(api, "POST").mockRejectedValue(
      new ErroDaApi(401, {
        type: "https://docs.ponto.seeg.com.br/erros/PONTO-AUTH-001",
        title: "Credenciais inválidas",
        status: 401,
        codigo: "PONTO-AUTH-001",
      }),
    );

    await usuario.type(screen.getByLabelText("Senha"), "senha-errada");
    await usuario.click(screen.getByRole("button", { name: "Confirmar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "E-mail ou senha incorretos. Confira os dados e tente novamente.",
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("mostra o campo de código de verificação quando a sessão indica MFA ativo", async () => {
    mockarGet({ mfaValidadoEm: "2026-07-20T08:00:00-03:00" });
    render(<ModalDeReautenticacao />);

    act(() => {
      void comAcessoControlado(() => Promise.reject(erroReautenticacaoNecessaria()));
    });

    await screen.findByRole("dialog");
    expect(await screen.findByLabelText("Código de verificação")).toBeInTheDocument();
  });

  it("não mostra o campo de código de verificação quando a sessão não indica MFA", async () => {
    mockarGet({});
    render(<ModalDeReautenticacao />);

    act(() => {
      void comAcessoControlado(() => Promise.reject(erroReautenticacaoNecessaria()));
    });

    await screen.findByRole("dialog");
    expect(screen.queryByLabelText("Código de verificação")).not.toBeInTheDocument();
  });

  it("cancelar fecha o modal sem chamar a API de reautenticação", async () => {
    mockarGet();
    render(<ModalDeReautenticacao />);
    const usuario = userEvent.setup();
    const espiaoPost = vi.spyOn(api, "POST");

    let promessaDaOperacao!: Promise<unknown>;
    act(() => {
      promessaDaOperacao = comAcessoControlado(() =>
        Promise.reject(erroReautenticacaoNecessaria()),
      );
    });
    // Registra o handler já no ato da criação (a rejeição real só acontece
    // depois do clique em "Cancelar", mais abaixo) — evita que o Node acuse
    // rejeição não tratada pelo intervalo entre a rejeição e o `await`.
    const capturaDeRejeicao = promessaDaOperacao.catch((erro: unknown) => erro);
    await screen.findByRole("dialog");

    await usuario.click(screen.getByRole("button", { name: "Cancelar" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(espiaoPost).not.toHaveBeenCalled();
    const erroCapturado = await capturaDeRejeicao;
    expect(erroCapturado).toBeInstanceOf(Error);
    expect((erroCapturado as Error).message).toBe("reautenticacao-cancelada");
  });
});
