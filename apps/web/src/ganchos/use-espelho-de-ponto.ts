"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { api, type Esquema } from "@/lib/api";
import { paramsSemUndefined } from "@/lib/formatacao-f8/parametros-de-consulta";

import { useSessaoAtual } from "./use-sessao";

export interface ParametrosDeEspelho {
  /** ISO 8601 (instante). Ausente = sem limite inferior. */
  de?: string;
  /** ISO 8601 (instante). Ausente = sem limite superior. */
  ate?: string;
}

/**
 * `GET /v1/marcacoes` (`listarMarcacoes`) escopado ao colaborador
 * autenticado — nunca chama antes de conhecer `colaboradorId` (via
 * `useSessaoAtual`). Só leitura: marcação é append-only (glossário §1.2),
 * este gancho nunca cria, altera nem apaga nada.
 */
export function useEspelhoDePonto(
  parametros: ParametrosDeEspelho = {},
): UseQueryResult<Esquema<"ListaMarcacao">> {
  const { data: sessaoAtual } = useSessaoAtual();
  const colaboradorId = sessaoAtual?.colaboradorId;

  return useQuery({
    queryKey: ["espelho-de-ponto", colaboradorId, parametros.de, parametros.ate],
    queryFn: async () => {
      const resultado = await api.GET("/v1/marcacoes", {
        params: {
          query: paramsSemUndefined({
            colaboradorId,
            de: parametros.de,
            ate: parametros.ate,
            ordenar: "datahoraMarcacao:asc",
            limite: 100,
          }),
        },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    enabled: Boolean(colaboradorId),
  });
}
