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

export interface ParametrosDeListaDeTurnos {
  empresaId?: string | undefined;
  tipo?: Esquema<"Turno">["tipo"] | undefined;
  ativo?: boolean | undefined;
  cursor?: string | undefined;
}

/**
 * `GET /v1/turnos` (`listarTurnos`). Não existe `GET /v1/turnos/{turnoId}`
 * individual no contrato (T12, PCF §6) — o detalhe de um turno é sempre o
 * item já carregado por esta listagem, nunca uma chamada própria.
 */
export function useTurnos(
  parametros: ParametrosDeListaDeTurnos = {},
): UseQueryResult<Esquema<"ListaTurno">> {
  return useQuery({
    queryKey: [
      "turnos",
      parametros.empresaId,
      parametros.tipo,
      parametros.ativo,
      parametros.cursor,
    ],
    queryFn: async () => {
      const resultado = await api.GET("/v1/turnos", {
        params: {
          query: paramsSemUndefined({
            empresaId: parametros.empresaId,
            tipo: parametros.tipo,
            ativo: parametros.ativo,
            cursor: parametros.cursor,
            ordenar: "nome",
            limite: 100,
          }),
        },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
  });
}

/** `POST /v1/turnos` (`criarTurno`). */
export function useCriarTurno(): UseMutationResult<
  Esquema<"Turno">,
  unknown,
  Esquema<"TurnoCriar">
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (corpo: Esquema<"TurnoCriar">) => {
      // `Idempotency-Key` é obrigatória no contrato (`CabecalhoIdempotencia`)
      // para toda escrita — o middleware de `cliente.ts` também a gera
      // sozinha se ausente, mas os tipos gerados exigem o campo aqui.
      const resultado = await api.POST("/v1/turnos", {
        params: { header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Turno">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["turnos"] });
    },
  });
}

export interface ParametrosDeAtualizarTurno {
  turnoId: string;
  corpo: Esquema<"TurnoAtualizar">;
}

/** `PATCH /v1/turnos/{turnoId}` (`atualizarTurno`) — atualização parcial. */
export function useAtualizarTurno(): UseMutationResult<
  Esquema<"Turno">,
  unknown,
  ParametrosDeAtualizarTurno
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ turnoId, corpo }: ParametrosDeAtualizarTurno) => {
      const resultado = await api.PATCH("/v1/turnos/{turnoId}", {
        params: { path: { turnoId }, header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Turno">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["turnos"] });
    },
  });
}
