"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { api, type Esquema } from "@/lib/api";
import { paramsSemUndefined } from "@/lib/formatacao-f8/parametros-de-consulta";

export interface ParametrosDeComprovantes {
  cursor?: string;
}

/** `GET /v1/comprovantes` (`listarComprovantes`), escopado ao colaborador autenticado pelo próprio backend. */
export function useComprovantes(
  parametros: ParametrosDeComprovantes = {},
): UseQueryResult<Esquema<"ListaComprovante">> {
  return useQuery({
    queryKey: ["comprovantes", parametros.cursor],
    queryFn: async () => {
      const resultado = await api.GET("/v1/comprovantes", {
        params: {
          query: paramsSemUndefined({ cursor: parametros.cursor, ordenar: "emitidoEm:desc" }),
        },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
  });
}

/** `GET /v1/comprovantes/{comprovanteId}` (`obterComprovante`) — detalhe. */
export function useComprovante(
  comprovanteId: string | undefined,
): UseQueryResult<Esquema<"Comprovante">> {
  return useQuery({
    queryKey: ["comprovante", comprovanteId],
    queryFn: async () => {
      if (!comprovanteId) throw new Error("comprovanteId ausente");
      const resultado = await api.GET("/v1/comprovantes/{comprovanteId}", {
        params: { path: { comprovanteId } },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    enabled: Boolean(comprovanteId),
  });
}
