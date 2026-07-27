"use client";

import { useQueries, useQuery, type UseQueryResult } from "@tanstack/react-query";

import { api, type Esquema } from "@/lib/api";

/**
 * `GET /v1/jornadas/resolver` (`resolverJornadaDoDia`) — um vínculo + uma
 * data por chamada. Não existe leitura em lote no contrato (achado de
 * contrato nº 1, PCF F9b §2) — por isso este módulo expõe tanto a consulta
 * unitária quanto uma versão em lote (`useResolucoesJornadaEmLote`) que só
 * multiplica a MESMA chamada cacheada por `(vinculoId, data)`, nunca inventa
 * um endpoint novo.
 */
export function useResolucaoJornada(
  vinculoId: string | undefined,
  data: string | undefined,
  habilitado = true,
): UseQueryResult<Esquema<"ResolucaoJornada">> {
  return useQuery({
    queryKey: ["resolucao-jornada", vinculoId, data],
    queryFn: async () => {
      if (!vinculoId || !data) throw new Error("vinculoId/data ausente");
      const resultado = await api.GET("/v1/jornadas/resolver", {
        params: { query: { vinculoId, data } },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    enabled: habilitado && Boolean(vinculoId) && Boolean(data),
    staleTime: 60_000,
  });
}

export interface ParDeResolucao {
  vinculoId: string;
  data: string;
}

/**
 * Uma consulta cacheada por `(vinculoId, data)` para cada par pedido —
 * `TanStack Query` deduplica automaticamente pares repetidos entre
 * renderizações graças à `queryKey` estável. Escopado pelo chamador à
 * equipe/período VISÍVEIS (a grade de T13 nunca pede o tenant inteiro,
 * mesma regra do achado de contrato nº 1).
 */
export function useResolucoesJornadaEmLote(
  pares: ParDeResolucao[],
): UseQueryResult<Esquema<"ResolucaoJornada">>[] {
  return useQueries({
    queries: pares.map((par) => ({
      queryKey: ["resolucao-jornada", par.vinculoId, par.data],
      queryFn: async () => {
        const resultado = await api.GET("/v1/jornadas/resolver", {
          params: { query: { vinculoId: par.vinculoId, data: par.data } },
        });
        if (resultado.error) throw resultado.error;
        return resultado.data;
      },
      staleTime: 60_000,
    })),
  });
}
