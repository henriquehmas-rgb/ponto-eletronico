"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { api, type Esquema } from "@/lib/api";
import { paramsSemUndefined } from "@/lib/formatacao-f8/parametros-de-consulta";

export interface ParametrosDeTiposDeSolicitacao {
  ativo?: boolean;
}

/** `GET /v1/tipos-solicitacao` (`listarTiposSolicitacao`) — popula o seletor de categoria em `/eu/solicitacoes/nova`. */
export function useTiposSolicitacao(
  parametros: ParametrosDeTiposDeSolicitacao = { ativo: true },
): UseQueryResult<Esquema<"ListaTipoSolicitacao">> {
  return useQuery({
    queryKey: ["tipos-solicitacao", parametros.ativo],
    queryFn: async () => {
      const resultado = await api.GET("/v1/tipos-solicitacao", {
        params: { query: paramsSemUndefined({ ativo: parametros.ativo, limite: 200 }) },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    staleTime: 60_000,
  });
}
