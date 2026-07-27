"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { api, type Esquema } from "@/lib/api";
import { paramsSemUndefined } from "@/lib/formatacao-f8/parametros-de-consulta";

import { useSessaoAtual } from "./use-sessao";

/**
 * `GET /v1/banco-horas/{colaboradorId}/saldo` (`obterSaldoBancoHoras`) do
 * colaborador autenticado. `colaboradorId` é parte da URL (obrigatório no
 * contrato) — por isso este gancho depende de `useSessaoAtual` resolver
 * primeiro.
 */
export function useSaldoBancoHoras(
  contaCodigo?: string,
): UseQueryResult<Esquema<"SaldoBancoHoras">> {
  const { data: sessaoAtual } = useSessaoAtual();
  const colaboradorId = sessaoAtual?.colaboradorId;

  return useQuery({
    queryKey: ["saldo-banco-horas", colaboradorId, contaCodigo],
    queryFn: async () => {
      if (!colaboradorId) throw new Error("colaboradorId ausente");
      const resultado = await api.GET("/v1/banco-horas/{colaboradorId}/saldo", {
        params: { path: { colaboradorId }, query: paramsSemUndefined({ contaCodigo }) },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    enabled: Boolean(colaboradorId),
  });
}

export interface ParametrosDeExtrato {
  de?: string;
  ate?: string;
  contaCodigo?: string;
  cursor?: string;
}

/**
 * `GET /v1/banco-horas/{colaboradorId}/extrato` (`obterExtratoBancoHoras`),
 * paginado por cursor (contrato: `paginacao.proximoCursor` da página
 * anterior, sem alterar filtros nem ordenação — T3).
 */
export function useExtratoBancoHoras(
  parametros: ParametrosDeExtrato = {},
): UseQueryResult<Esquema<"ExtratoBancoHoras">> {
  const { data: sessaoAtual } = useSessaoAtual();
  const colaboradorId = sessaoAtual?.colaboradorId;

  return useQuery({
    queryKey: [
      "extrato-banco-horas",
      colaboradorId,
      parametros.de,
      parametros.ate,
      parametros.contaCodigo,
      parametros.cursor,
    ],
    queryFn: async () => {
      if (!colaboradorId) throw new Error("colaboradorId ausente");
      const resultado = await api.GET("/v1/banco-horas/{colaboradorId}/extrato", {
        params: {
          path: { colaboradorId },
          query: paramsSemUndefined({
            de: parametros.de,
            ate: parametros.ate,
            contaCodigo: parametros.contaCodigo,
            cursor: parametros.cursor,
          }),
        },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    enabled: Boolean(colaboradorId),
  });
}
