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

export interface ParametrosDeListaDeCargos {
  empresaId?: string | undefined;
  nivel?: Esquema<"Cargo">["nivel"] | undefined;
  ativo?: boolean | undefined;
  busca?: string | undefined;
  incluirExcluidos?: boolean | undefined;
  cursor?: string | undefined;
}

/**
 * `GET /v1/cargos` (`listarCargos`) — T6.
 *
 * SEM exclusão no contrato, mesma observação de centros de custo: usa
 * `atualizarCargo` com `ativo: false` para desativar.
 */
export function useCargos(
  parametros: ParametrosDeListaDeCargos = {},
): UseQueryResult<Esquema<"ListaCargo">> {
  return useQuery({
    queryKey: ["cargos", parametros],
    queryFn: async () => {
      const resultado = await api.GET("/v1/cargos", {
        params: { query: paramsSemUndefined({ ordenar: "nome:asc", limite: 200, ...parametros }) },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
  });
}

/** `POST /v1/cargos` (`criarCargo`). */
export function useCriarCargo(): UseMutationResult<
  Esquema<"Cargo">,
  unknown,
  Esquema<"CargoCriar">
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (corpo: Esquema<"CargoCriar">) => {
      const resultado = await api.POST("/v1/cargos", {
        params: { header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Cargo">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["cargos"] });
    },
  });
}

/** `PATCH /v1/cargos/{cargoId}` (`atualizarCargo`) — inclui alternar `ativo`. */
export function useAtualizarCargo(): UseMutationResult<
  Esquema<"Cargo">,
  unknown,
  { id: string; corpo: Esquema<"CargoAtualizar"> }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, corpo }) => {
      const resultado = await api.PATCH("/v1/cargos/{cargoId}", {
        params: { path: { cargoId: id }, header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Cargo">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["cargos"] });
    },
  });
}
