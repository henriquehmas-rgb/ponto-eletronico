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

export interface ParametrosDeListaDeUnidades {
  empresaId?: string | undefined;
  tipo?: Esquema<"Unidade">["tipo"] | undefined;
  uf?: string | undefined;
  comGeocerca?: boolean | undefined;
  ativo?: boolean | undefined;
  busca?: string | undefined;
  incluirExcluidos?: boolean | undefined;
  cursor?: string | undefined;
}

/** `GET /v1/unidades` (`listarUnidades`) — CRUD de unidades + geocerca (T4/T5). */
export function useUnidades(
  parametros: ParametrosDeListaDeUnidades = {},
): UseQueryResult<Esquema<"ListaUnidade">> {
  return useQuery({
    queryKey: ["unidades", parametros],
    queryFn: async () => {
      const resultado = await api.GET("/v1/unidades", {
        params: { query: paramsSemUndefined({ ordenar: "nome:asc", limite: 200, ...parametros }) },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
  });
}

/** `POST /v1/unidades` (`criarUnidade`). */
export function useCriarUnidade(): UseMutationResult<
  Esquema<"Unidade">,
  unknown,
  Esquema<"UnidadeCriar">
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (corpo: Esquema<"UnidadeCriar">) => {
      const resultado = await api.POST("/v1/unidades", {
        params: { header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Unidade">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["unidades"] });
    },
  });
}

/** `PATCH /v1/unidades/{unidadeId}` (`atualizarUnidade`) — inclui campos de geocerca (T5). */
export function useAtualizarUnidade(): UseMutationResult<
  Esquema<"Unidade">,
  unknown,
  { id: string; corpo: Esquema<"UnidadeAtualizar"> }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, corpo }) => {
      const resultado = await api.PATCH("/v1/unidades/{unidadeId}", {
        params: { path: { unidadeId: id }, header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Unidade">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["unidades"] });
    },
  });
}

/** `DELETE /v1/unidades/{unidadeId}` (`excluirUnidade`) — exclusão lógica. */
export function useExcluirUnidade(): UseMutationResult<void, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (unidadeId: string) => {
      const resultado = await api.DELETE("/v1/unidades/{unidadeId}", {
        params: { path: { unidadeId }, header: { "Idempotency-Key": crypto.randomUUID() } },
      });
      if (resultado.error) throw resultado.error;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["unidades"] });
    },
  });
}

/** `GET /v1/unidades/{unidadeId}/redes-permitidas` (`listarRedesPermitidas`) — allowlist CIDR (T4). */
export function useRedesPermitidas(
  unidadeId: string | undefined,
): UseQueryResult<Esquema<"ListaRedePermitida">> {
  return useQuery({
    queryKey: ["redes-permitidas", unidadeId],
    queryFn: async () => {
      if (!unidadeId) throw new Error("unidadeId ausente");
      const resultado = await api.GET("/v1/unidades/{unidadeId}/redes-permitidas", {
        params: { path: { unidadeId }, query: { limite: 100 } },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    enabled: Boolean(unidadeId),
  });
}

/** `POST /v1/unidades/{unidadeId}/redes-permitidas` (`criarRedePermitida`). */
export function useCriarRedePermitida(): UseMutationResult<
  Esquema<"RedePermitida">,
  unknown,
  { unidadeId: string; corpo: Esquema<"RedePermitidaCriar"> }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ unidadeId, corpo }) => {
      const resultado = await api.POST("/v1/unidades/{unidadeId}/redes-permitidas", {
        params: { path: { unidadeId }, header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"RedePermitida">;
    },
    onSuccess: (_dados, variaveis) => {
      void queryClient.invalidateQueries({ queryKey: ["redes-permitidas", variaveis.unidadeId] });
    },
  });
}

/** `DELETE /v1/unidades/{unidadeId}/redes-permitidas/{redeId}` (`excluirRedePermitida`). */
export function useExcluirRedePermitida(): UseMutationResult<
  void,
  unknown,
  { unidadeId: string; redeId: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ unidadeId, redeId }) => {
      const resultado = await api.DELETE("/v1/unidades/{unidadeId}/redes-permitidas/{redeId}", {
        params: { path: { unidadeId, redeId }, header: { "Idempotency-Key": crypto.randomUUID() } },
      });
      if (resultado.error) throw resultado.error;
    },
    onSuccess: (_dados, variaveis) => {
      void queryClient.invalidateQueries({ queryKey: ["redes-permitidas", variaveis.unidadeId] });
    },
  });
}
