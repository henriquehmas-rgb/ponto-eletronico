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

export interface ParametrosDeListaDeBiometrias {
  colaboradorId?: string | undefined;
  modalidade?: Esquema<"Biometria">["modalidade"] | undefined;
  status?: Esquema<"Biometria">["status"] | undefined;
  cursor?: string | undefined;
}

/**
 * `GET /v1/biometrias` (`listarBiometrias`) — aba "Biometria" do detalhe do
 * colaborador (T8). **Esta fase só administra credenciais já existentes**
 * (listar/revogar/aprovar) — nenhuma captura nova via câmera (`getUserMedia`),
 * é escopo de F7/F8. O vetor biométrico em si nunca é exposto pela API.
 */
export function useBiometrias(
  parametros: ParametrosDeListaDeBiometrias = {},
): UseQueryResult<Esquema<"ListaBiometria">> {
  return useQuery({
    queryKey: ["biometrias", parametros],
    queryFn: async () => {
      const resultado = await api.GET("/v1/biometrias", {
        params: {
          query: paramsSemUndefined({ ordenar: "cadastradaEm:desc", limite: 50, ...parametros }),
        },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    enabled: Boolean(parametros.colaboradorId),
  });
}

/** `DELETE /v1/biometrias/{biometriaId}` (`revogarBiometria`). */
export function useRevogarBiometria(): UseMutationResult<void, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (biometriaId: string) => {
      const resultado = await api.DELETE("/v1/biometrias/{biometriaId}", {
        params: { path: { biometriaId }, header: { "Idempotency-Key": crypto.randomUUID() } },
      });
      if (resultado.error) throw resultado.error;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["biometrias"] });
    },
  });
}

/**
 * `POST /v1/biometrias/{biometriaId}/validar` (`validarBiometria`) — aprova
 * ou reprova a credencial pendente (`DecisaoRequisicao`, mesmo schema usado
 * por decisões de tratamento/solicitação).
 */
export function useValidarBiometria(): UseMutationResult<
  Esquema<"Biometria">,
  unknown,
  { id: string; corpo: Esquema<"DecisaoRequisicao"> }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, corpo }) => {
      const resultado = await api.POST("/v1/biometrias/{biometriaId}/validar", {
        params: { path: { biometriaId: id }, header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Biometria">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["biometrias"] });
    },
  });
}
