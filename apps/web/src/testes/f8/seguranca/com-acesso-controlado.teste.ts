import { afterEach, describe, expect, it, vi } from "vitest";

import { ErroDaApi } from "@/lib/api";
import {
  comAcessoControlado,
  definirSolicitadorDeReautenticacao,
} from "@/lib/seguranca/com-acesso-controlado";

/**
 * T13 do PCF F08. Critérios da seção "Pronto quando":
 *  1. `comAcessoControlado` reexecuta `chamada` exatamente uma vez após
 *     reautenticação aceita.
 *  2. Não entra em laço se a segunda tentativa também falhar com
 *     `PONTO-AUTH-011`.
 *  3. Um erro diferente de `PONTO-AUTH-011` nunca abre o modal de
 *     reautenticação (nunca chama o solicitador).
 */

function erroDeReautenticacaoNecessaria(): ErroDaApi {
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

describe("comAcessoControlado", () => {
  it("devolve o resultado direto quando a chamada não falha", async () => {
    const chamada = vi.fn().mockResolvedValue("ok");
    const resultado = await comAcessoControlado(chamada);
    expect(resultado).toBe("ok");
    expect(chamada).toHaveBeenCalledTimes(1);
  });

  it("relança um erro que não é PONTO-AUTH-011 sem chamar o solicitador de reautenticação", async () => {
    const solicitador = vi.fn().mockResolvedValue(undefined);
    definirSolicitadorDeReautenticacao(solicitador);

    const erroDeValidacao = new ErroDaApi(400, {
      type: "https://docs.ponto.seeg.com.br/erros/PONTO-VAL-001",
      title: "Corpo da requisição inválido",
      status: 400,
      codigo: "PONTO-VAL-001",
    });
    const chamada = vi.fn().mockRejectedValue(erroDeValidacao);

    await expect(comAcessoControlado(chamada)).rejects.toBe(erroDeValidacao);
    expect(solicitador).not.toHaveBeenCalled();
    expect(chamada).toHaveBeenCalledTimes(1);
  });

  it("relança PONTO-AUTH-011 sem reexecutar quando nenhum solicitador está registrado", async () => {
    const erro = erroDeReautenticacaoNecessaria();
    const chamada = vi.fn().mockRejectedValue(erro);

    await expect(comAcessoControlado(chamada)).rejects.toBe(erro);
    expect(chamada).toHaveBeenCalledTimes(1);
  });

  it("dispara o solicitador em PONTO-AUTH-011 e reexecuta a chamada exatamente uma vez após aceite", async () => {
    const solicitador = vi.fn().mockResolvedValue(undefined);
    definirSolicitadorDeReautenticacao(solicitador);

    const chamada = vi
      .fn()
      .mockRejectedValueOnce(erroDeReautenticacaoNecessaria())
      .mockResolvedValueOnce("sucesso");

    const resultado = await comAcessoControlado(chamada);

    expect(resultado).toBe("sucesso");
    expect(solicitador).toHaveBeenCalledTimes(1);
    expect(chamada).toHaveBeenCalledTimes(2);
  });

  it("não entra em laço: se a segunda tentativa também falhar com PONTO-AUTH-011, propaga sem chamar o solicitador de novo", async () => {
    const solicitador = vi.fn().mockResolvedValue(undefined);
    definirSolicitadorDeReautenticacao(solicitador);

    const segundoErro = erroDeReautenticacaoNecessaria();
    const chamada = vi
      .fn()
      .mockRejectedValueOnce(erroDeReautenticacaoNecessaria())
      .mockRejectedValueOnce(segundoErro);

    await expect(comAcessoControlado(chamada)).rejects.toBe(segundoErro);
    expect(solicitador).toHaveBeenCalledTimes(1);
    expect(chamada).toHaveBeenCalledTimes(2);
  });

  it("propaga a rejeição quando o colaborador cancela a reautenticação", async () => {
    const motivoDeCancelamento = new Error("reautenticacao-cancelada");
    const solicitador = vi.fn().mockRejectedValue(motivoDeCancelamento);
    definirSolicitadorDeReautenticacao(solicitador);

    const chamada = vi.fn().mockRejectedValue(erroDeReautenticacaoNecessaria());

    await expect(comAcessoControlado(chamada)).rejects.toBe(motivoDeCancelamento);
    expect(chamada).toHaveBeenCalledTimes(1);
  });
});
