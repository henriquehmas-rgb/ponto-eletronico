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

export interface ParametrosDeListaDeDepartamentos {
  empresaId?: string | undefined;
  departamentoPaiId?: string | undefined;
  ativo?: boolean | undefined;
  busca?: string | undefined;
  incluirExcluidos?: boolean | undefined;
  cursor?: string | undefined;
}

/** `GET /v1/departamentos` (`listarDepartamentos`) — CRUD completo (T6). */
export function useDepartamentos(
  parametros: ParametrosDeListaDeDepartamentos = {},
): UseQueryResult<Esquema<"ListaDepartamento">> {
  return useQuery({
    queryKey: ["departamentos", parametros],
    queryFn: async () => {
      const resultado = await api.GET("/v1/departamentos", {
        params: { query: paramsSemUndefined({ ordenar: "nome:asc", limite: 200, ...parametros }) },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
  });
}

/** `POST /v1/departamentos` (`criarDepartamento`). */
export function useCriarDepartamento(): UseMutationResult<
  Esquema<"Departamento">,
  unknown,
  Esquema<"DepartamentoCriar">
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (corpo: Esquema<"DepartamentoCriar">) => {
      const resultado = await api.POST("/v1/departamentos", {
        params: { header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Departamento">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["departamentos"] });
    },
  });
}

/** `PATCH /v1/departamentos/{departamentoId}` (`atualizarDepartamento`). */
export function useAtualizarDepartamento(): UseMutationResult<
  Esquema<"Departamento">,
  unknown,
  { id: string; corpo: Esquema<"DepartamentoAtualizar"> }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, corpo }) => {
      const resultado = await api.PATCH("/v1/departamentos/{departamentoId}", {
        params: {
          path: { departamentoId: id },
          header: { "Idempotency-Key": crypto.randomUUID() },
        },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Departamento">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["departamentos"] });
    },
  });
}

/** `DELETE /v1/departamentos/{departamentoId}` (`excluirDepartamento`) — exclusão lógica. */
export function useExcluirDepartamento(): UseMutationResult<void, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (departamentoId: string) => {
      const resultado = await api.DELETE("/v1/departamentos/{departamentoId}", {
        params: { path: { departamentoId }, header: { "Idempotency-Key": crypto.randomUUID() } },
      });
      if (resultado.error) throw resultado.error;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["departamentos"] });
    },
  });
}
