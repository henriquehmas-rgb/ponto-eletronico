import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ErroDaApi } from "@/lib/api";
import { useReautenticacao } from "@/ganchos/use-reautenticacao";
import {
  comAcessoControlado,
  definirSolicitadorDeReautenticacao,
} from "@/lib/seguranca/com-acesso-controlado";

/**
 * T12 do PCF F08. Critérios da seção "Pronto quando":
 *  1. O modal (aqui, o estado do gancho) abre automaticamente ao interceptar
 *     `PONTO-AUTH-011` via `comAcessoControlado`.
 *  2. Senha incorreta mostra o erro certo (`PONTO-AUTH-001`) sem fechar o
 *     modal.
 *  3. Reautenticação aceita fecha o modal e resolve a promessa que
 *     `comAcessoControlado` está esperando.
 */

function mockarGet(dados: Record<string, unknown>): void {
  const implementacao = (async () => ({ data: dados })) as unknown as typeof api.GET;
  vi.spyOn(api, "GET").mockImplementation(implementacao);
}

function mockarPostComSucesso(): void {
  const implementacao = (async () => ({
    data: { reautenticadoEm: "2026-07-26T10:00:00-03:00", validoAte: "2026-07-26T10:15:00-03:00" },
  })) as unknown as typeof api.POST;
  vi.spyOn(api, "POST").mockImplementation(implementacao);
}

function mockarPostComErro(erro: ErroDaApi): void {
  vi.spyOn(api, "POST").mockRejectedValue(erro);
}

function erroSenhaIncorreta(): ErroDaApi {
  return new ErroDaApi(401, {
    type: "https://docs.ponto.seeg.com.br/erros/PONTO-AUTH-001",
    title: "Credenciais inválidas",
    status: 401,
    codigo: "PONTO-AUTH-001",
  });
}

afterEach(() => {
  definirSolicitadorDeReautenticacao(undefined);
  vi.restoreAllMocks();
});

describe("useReautenticacao", () => {
  it("começa fechado e sem erro", () => {
    mockarGet({});
    const { result } = renderHook(() => useReautenticacao());
    expect(result.current.aberto).toBe(false);
    expect(result.current.erro).toBeUndefined();
  });

  it("abre quando comAcessoControlado intercepta PONTO-AUTH-011", async () => {
    mockarGet({});
    const { result } = renderHook(() => useReautenticacao());

    const chamadaOriginal = vi
      .fn()
      .mockRejectedValueOnce(
        new ErroDaApi(401, {
          type: "https://docs.ponto.seeg.com.br/erros/PONTO-AUTH-011",
          title: "Reautenticação necessária",
          status: 401,
          codigo: "PONTO-AUTH-011",
        }),
      )
      .mockResolvedValueOnce("marcacao-criada");

    let promessaDaOperacao!: Promise<string>;
    act(() => {
      promessaDaOperacao = comAcessoControlado(chamadaOriginal);
    });

    await waitFor(() => {
      expect(result.current.aberto).toBe(true);
    });

    mockarPostComSucesso();
    await act(async () => {
      await result.current.confirmar({ senha: "senha-correta" });
    });

    await expect(promessaDaOperacao).resolves.toBe("marcacao-criada");
    expect(result.current.aberto).toBe(false);
  });

  it("mostra o campo de MFA quando a sessão indica mfaValidadoEm", async () => {
    mockarGet({ mfaValidadoEm: "2026-07-20T08:00:00-03:00" });
    const { result } = renderHook(() => useReautenticacao());

    act(() => {
      void comAcessoControlado(() =>
        Promise.reject(
          new ErroDaApi(401, {
            type: "https://docs.ponto.seeg.com.br/erros/PONTO-AUTH-011",
            title: "Reautenticação necessária",
            status: 401,
            codigo: "PONTO-AUTH-011",
          }),
        ),
      );
    });

    await waitFor(() => {
      expect(result.current.mfaNecessario).toBe(true);
    });
  });

  it("senha incorreta mostra o erro certo sem fechar o modal", async () => {
    mockarGet({});
    const { result } = renderHook(() => useReautenticacao());

    act(() => {
      void comAcessoControlado(() =>
        Promise.reject(
          new ErroDaApi(401, {
            type: "https://docs.ponto.seeg.com.br/erros/PONTO-AUTH-011",
            title: "Reautenticação necessária",
            status: 401,
            codigo: "PONTO-AUTH-011",
          }),
        ),
      );
    });
    await waitFor(() => expect(result.current.aberto).toBe(true));

    mockarPostComErro(erroSenhaIncorreta());
    await act(async () => {
      await result.current.confirmar({ senha: "senha-errada" });
    });

    expect(result.current.aberto).toBe(true);
    expect(result.current.erro).toBe(
      "E-mail ou senha incorretos. Confira os dados e tente novamente.",
    );
  });

  it("cancelar fecha o modal e rejeita a promessa original", async () => {
    mockarGet({});
    const { result } = renderHook(() => useReautenticacao());

    let promessaDaOperacao!: Promise<unknown>;
    act(() => {
      promessaDaOperacao = comAcessoControlado(() =>
        Promise.reject(
          new ErroDaApi(401, {
            type: "https://docs.ponto.seeg.com.br/erros/PONTO-AUTH-011",
            title: "Reautenticação necessária",
            status: 401,
            codigo: "PONTO-AUTH-011",
          }),
        ),
      );
    });
    await waitFor(() => expect(result.current.aberto).toBe(true));

    act(() => {
      result.current.cancelar();
    });

    expect(result.current.aberto).toBe(false);
    await expect(promessaDaOperacao).rejects.toThrow();
  });
});
