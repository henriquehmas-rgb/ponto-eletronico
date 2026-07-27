"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import { api, type Esquema } from "@/lib/api";
import { paramsSemUndefined } from "@/lib/formatacao-f8/parametros-de-consulta";

export interface ParametrosDeListaDeCentrosCusto {
  empresaId?: string | undefined;
  centroCustoPaiId?: string | undefined;
  ativo?: boolean | undefined;
  busca?: string | undefined;
  incluirExcluidos?: boolean | undefined;
  cursor?: string | undefined;
}

/**
 * `GET /v1/centros-custo` (`listarCentrosCusto`) — T6.
 *
 * SEM exclusão no contrato (só `listar`/`criar`/`obter`/`atualizar`) — a tela
 * usa o campo `ativo` via `atualizarCentroCusto` para desativar (T6, achado
 * de contrato §2 do PCF). Este gancho não expõe `useExcluirCentroCusto`
 * porque a operação não existe.
 */
export function useCentrosCusto(
  parametros: ParametrosDeListaDeCentrosCusto = {},
): UseQueryResult<Esquema<"ListaCentroCusto">> {
  return useQuery({
    queryKey: ["centros-custo", parametros],
    queryFn: async () => {
      const resultado = await api.GET("/v1/centros-custo", {
        params: { query: paramsSemUndefined({ ordenar: "nome:asc", limite: 200, ...parametros }) },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
  });
}

/** `POST /v1/centros-custo` (`criarCentroCusto`). */
export function useCriarCentroCusto(): UseMutationResult<
  Esquema<"CentroCusto">,
  unknown,
  Esquema<"CentroCustoCriar">
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (corpo: Esquema<"CentroCustoCriar">) => {
      const resultado = await api.POST("/v1/centros-custo", {
        params: { header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"CentroCusto">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["centros-custo"] });
    },
  });
}

/** `PATCH /v1/centros-custo/{centroCustoId}` (`atualizarCentroCusto`) — inclui alternar `ativo`. */
export function useAtualizarCentroCusto(): UseMutationResult<
  Esquema<"CentroCusto">,
  unknown,
  { id: string; corpo: Esquema<"CentroCustoAtualizar"> }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, corpo }) => {
      const resultado = await api.PATCH("/v1/centros-custo/{centroCustoId}", {
        params: { path: { centroCustoId: id }, header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"CentroCusto">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["centros-custo"] });
    },
  });
}
