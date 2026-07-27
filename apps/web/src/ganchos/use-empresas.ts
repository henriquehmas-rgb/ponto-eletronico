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

export interface ParametrosDeListaDeEmpresas {
  empresaId?: string | undefined;
  cnpj?: string | undefined;
  tipo?: "matriz" | "filial" | undefined;
  matrizId?: string | undefined;
  ativo?: boolean | undefined;
  busca?: string | undefined;
  incluirExcluidos?: boolean | undefined;
  cursor?: string | undefined;
  limite?: number | undefined;
}

/** `GET /v1/empresas` (`listarEmpresas`) — CRUD de empresas (T4). */
export function useEmpresas(
  parametros: ParametrosDeListaDeEmpresas = {},
): UseQueryResult<Esquema<"ListaEmpresa">> {
  return useQuery({
    queryKey: ["empresas", parametros],
    queryFn: async () => {
      const resultado = await api.GET("/v1/empresas", {
        params: {
          query: paramsSemUndefined({
            ordenar: "razaoSocial:asc",
            limite: 200,
            ...parametros,
          }),
        },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
  });
}

/** `POST /v1/empresas` (`criarEmpresa`). */
export function useCriarEmpresa(): UseMutationResult<
  Esquema<"Empresa">,
  unknown,
  Esquema<"EmpresaCriar">
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (corpo: Esquema<"EmpresaCriar">) => {
      const resultado = await api.POST("/v1/empresas", {
        params: { header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Empresa">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["empresas"] });
    },
  });
}

/** `PATCH /v1/empresas/{empresaId}` (`atualizarEmpresa`). */
export function useAtualizarEmpresa(): UseMutationResult<
  Esquema<"Empresa">,
  unknown,
  { id: string; corpo: Esquema<"EmpresaAtualizar"> }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, corpo }) => {
      const resultado = await api.PATCH("/v1/empresas/{empresaId}", {
        params: { path: { empresaId: id }, header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Empresa">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["empresas"] });
    },
  });
}

/**
 * `DELETE /v1/empresas/{empresaId}` (`excluirEmpresa`) — exclusão LÓGICA
 * (o próprio contrato: "sai das listagens, preserva o histórico"). A tela
 * nunca chama isto de "apagar para sempre".
 */
export function useExcluirEmpresa(): UseMutationResult<void, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (empresaId: string) => {
      const resultado = await api.DELETE("/v1/empresas/{empresaId}", {
        params: { path: { empresaId }, header: { "Idempotency-Key": crypto.randomUUID() } },
      });
      if (resultado.error) throw resultado.error;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["empresas"] });
    },
  });
}
