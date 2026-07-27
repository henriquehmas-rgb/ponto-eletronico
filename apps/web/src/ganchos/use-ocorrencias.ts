"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import { paramsSemUndefined } from "@/componentes/paineis/apuracao/utilitarios";
import { api, type Esquema } from "@/lib/api";

export interface ParametrosDeOcorrencias {
  empresaId?: string | undefined;
  unidadeId?: string | undefined;
  colaboradorId?: string | undefined;
  codigo?: Esquema<"Ocorrencia">["codigo"] | undefined;
  severidade?: Esquema<"Ocorrencia">["severidade"] | undefined;
  status?: Esquema<"Ocorrencia">["status"] | undefined;
  de?: string | undefined;
  ate?: string | undefined;
}

/**
 * `GET /v1/ocorrencias` (`listarOcorrencias`) — fila de inconsistências
 * detectadas pelo motor. Usado tanto para o destaque de célula na grade (T9)
 * quanto para a lista dentro do dialogo de detalhe (T10).
 */
export function useOcorrencias(
  parametros: ParametrosDeOcorrencias = {},
): UseQueryResult<Esquema<"ListaOcorrencia">> {
  return useQuery({
    queryKey: [
      "ocorrencias",
      parametros.empresaId,
      parametros.unidadeId,
      parametros.colaboradorId,
      parametros.codigo,
      parametros.severidade,
      parametros.status,
      parametros.de,
      parametros.ate,
    ],
    queryFn: async () => {
      const resultado = await api.GET("/v1/ocorrencias", {
        params: {
          query: paramsSemUndefined({
            empresaId: parametros.empresaId,
            unidadeId: parametros.unidadeId,
            colaboradorId: parametros.colaboradorId,
            codigo: parametros.codigo,
            severidade: parametros.severidade,
            status: parametros.status,
            de: parametros.de,
            ate: parametros.ate,
            limite: 200,
            ordenar: "severidade:desc,data:desc",
          }),
        },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
  });
}

/**
 * `PATCH /v1/ocorrencias/{ocorrenciaId}` (`atualizarOcorrencia`) — assumir,
 * ignorar (com justificativa) ou marcar como resolvida. **Nunca corrige a
 * jornada**: quando a resolução decorre de uma correção, é o `tratamentoId`
 * do tratamento já criado que se referencia aqui — o formulário nunca oferece
 * um caminho de "corrigir" que não passe por `useCriarTratamento` primeiro.
 */
export function useAtualizarOcorrencia(): UseMutationResult<
  Esquema<"Ocorrencia">,
  unknown,
  { ocorrenciaId: string; corpo: Esquema<"OcorrenciaAtualizar"> }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ ocorrenciaId, corpo }) => {
      const resultado = await api.PATCH("/v1/ocorrencias/{ocorrenciaId}", {
        params: {
          path: { ocorrenciaId },
          header: { "Idempotency-Key": crypto.randomUUID() },
        },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Ocorrencia">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["ocorrencias"] });
      void queryClient.invalidateQueries({ queryKey: ["apuracoes"] });
    },
  });
}
