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

export interface ParametrosDeListaDeVinculos {
  colaboradorId?: string | undefined;
  empresaId?: string | undefined;
  unidadeId?: string | undefined;
  status?: Esquema<"Vinculo">["status"] | undefined;
  cursor?: string | undefined;
}

/**
 * `GET /v1/vinculos` (`listarVinculos`) — aba "Vínculos" do detalhe do
 * colaborador (T7). **Não há `atualizarVinculo`** — só criação
 * (`useCriarVinculo`) e encerramento (`useEncerrarVinculo`). Nenhum botão de
 * "editar vínculo" genérico é oferecido, porque a operação não existe (achado
 * §2/§6 do PCF).
 */
export function useVinculos(
  parametros: ParametrosDeListaDeVinculos = {},
): UseQueryResult<Esquema<"ListaVinculo">> {
  return useQuery({
    queryKey: ["vinculos", parametros],
    queryFn: async () => {
      const resultado = await api.GET("/v1/vinculos", {
        params: {
          query: paramsSemUndefined({ ordenar: "dataInicio:desc", limite: 100, ...parametros }),
        },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    enabled: Boolean(parametros.colaboradorId ?? parametros.empresaId ?? parametros.unidadeId),
  });
}

/** `POST /v1/vinculos` (`criarVinculo`). */
export function useCriarVinculo(): UseMutationResult<
  Esquema<"Vinculo">,
  unknown,
  Esquema<"VinculoCriar">
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (corpo: Esquema<"VinculoCriar">) => {
      const resultado = await api.POST("/v1/vinculos", {
        params: { header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Vinculo">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["vinculos"] });
    },
  });
}

/**
 * `POST /v1/vinculos/{vinculoId}/encerrar` (`encerrarVinculo`) — desligamento:
 * data de fim, encerra jornada/escala, dispara acerto de banco de horas
 * (saldo credor/devedor conforme a política).
 */
export function useEncerrarVinculo(): UseMutationResult<
  Esquema<"Vinculo">,
  unknown,
  { id: string; corpo: Esquema<"EncerramentoVinculoRequisicao"> }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, corpo }) => {
      const resultado = await api.POST("/v1/vinculos/{vinculoId}/encerrar", {
        params: { path: { vinculoId: id }, header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Vinculo">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["vinculos"] });
    },
  });
}
