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

export interface ParametrosDeListaDeDispositivos {
  empresaId?: string | undefined;
  unidadeId?: string | undefined;
  tipo?: Esquema<"Dispositivo">["tipo"] | undefined;
  status?: Esquema<"Dispositivo">["status"] | undefined;
  colaboradorVinculadoId?: string | undefined;
  busca?: string | undefined;
  cursor?: string | undefined;
}

/** `GET /v1/dispositivos` (`listarDispositivos`) — T8. */
export function useDispositivosCadastro(
  parametros: ParametrosDeListaDeDispositivos = {},
): UseQueryResult<Esquema<"ListaDispositivo">> {
  return useQuery({
    queryKey: ["dispositivos-cadastro", parametros],
    queryFn: async () => {
      const resultado = await api.GET("/v1/dispositivos", {
        params: {
          query: paramsSemUndefined({ ordenar: "criadoEm:desc", limite: 100, ...parametros }),
        },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
  });
}

/** `POST /v1/dispositivos` (`criarDispositivo`). */
export function useCriarDispositivo(): UseMutationResult<
  Esquema<"Dispositivo">,
  unknown,
  Esquema<"DispositivoCriar">
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (corpo: Esquema<"DispositivoCriar">) => {
      const resultado = await api.POST("/v1/dispositivos", {
        params: { header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Dispositivo">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["dispositivos-cadastro"] });
    },
  });
}

/** `PATCH /v1/dispositivos/{dispositivoId}` (`atualizarDispositivo`). */
export function useAtualizarDispositivo(): UseMutationResult<
  Esquema<"Dispositivo">,
  unknown,
  { id: string; corpo: Esquema<"DispositivoAtualizar"> }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, corpo }) => {
      const resultado = await api.PATCH("/v1/dispositivos/{dispositivoId}", {
        params: { path: { dispositivoId: id }, header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Dispositivo">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["dispositivos-cadastro"] });
    },
  });
}

/** `DELETE /v1/dispositivos/{dispositivoId}` (`excluirDispositivo`) — exclusão lógica. */
export function useExcluirDispositivo(): UseMutationResult<void, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (dispositivoId: string) => {
      const resultado = await api.DELETE("/v1/dispositivos/{dispositivoId}", {
        params: { path: { dispositivoId }, header: { "Idempotency-Key": crypto.randomUUID() } },
      });
      if (resultado.error) throw resultado.error;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["dispositivos-cadastro"] });
    },
  });
}

/**
 * `POST /v1/dispositivos/{dispositivoId}/vincular` (`vincularDispositivo`) —
 * cria o vínculo aparelho↔colaborador (nasce pendente, aguarda aprovação do
 * RH, salvo `aprovarImediatamente`).
 */
export function useVincularDispositivo(): UseMutationResult<
  Esquema<"Dispositivo">,
  unknown,
  { id: string; corpo: Esquema<"VinculoDispositivoRequisicao"> }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, corpo }) => {
      const resultado = await api.POST("/v1/dispositivos/{dispositivoId}/vincular", {
        params: { path: { dispositivoId: id }, header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Dispositivo">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["dispositivos-cadastro"] });
    },
  });
}
