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

export interface ParametrosDeListaDeContratos {
  colaboradorId?: string | undefined;
  empresaId?: string | undefined;
  tipo?: Esquema<"Contrato">["tipo"] | undefined;
  status?: Esquema<"Contrato">["status"] | undefined;
  cursor?: string | undefined;
}

/**
 * `GET /v1/contratos` (`listarContratos`) — aba "Contratos" do detalhe do
 * colaborador (T7). SEM exclusão no contrato: só `listar`/`criar`/`obter`/
 * `atualizar` — use `status: "encerrado"` via `atualizarContrato`.
 */
export function useContratos(
  parametros: ParametrosDeListaDeContratos = {},
): UseQueryResult<Esquema<"ListaContrato">> {
  return useQuery({
    queryKey: ["contratos", parametros],
    queryFn: async () => {
      const resultado = await api.GET("/v1/contratos", {
        params: {
          query: paramsSemUndefined({ ordenar: "dataInicio:desc", limite: 100, ...parametros }),
        },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    enabled: Boolean(parametros.colaboradorId ?? parametros.empresaId),
  });
}

/** `POST /v1/contratos` (`criarContrato`). */
export function useCriarContrato(): UseMutationResult<
  Esquema<"Contrato">,
  unknown,
  Esquema<"ContratoCriar">
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (corpo: Esquema<"ContratoCriar">) => {
      const resultado = await api.POST("/v1/contratos", {
        params: { header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Contrato">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["contratos"] });
    },
  });
}

/** `PATCH /v1/contratos/{contratoId}` (`atualizarContrato`). */
export function useAtualizarContrato(): UseMutationResult<
  Esquema<"Contrato">,
  unknown,
  { id: string; corpo: Esquema<"ContratoAtualizar"> }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, corpo }) => {
      const resultado = await api.PATCH("/v1/contratos/{contratoId}", {
        params: { path: { contratoId: id }, header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Contrato">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["contratos"] });
    },
  });
}
