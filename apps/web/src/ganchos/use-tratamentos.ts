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

/**
 * `GET /v1/tipos-tratamento` (`listarTiposTratamento`) — catálogo que povoa
 * o seletor de categoria do formulário de tratamento (T10).
 */
export function useTiposTratamento(
  parametros: { ativo?: boolean } = { ativo: true },
): UseQueryResult<Esquema<"ListaTipoTratamento">> {
  return useQuery({
    queryKey: ["tipos-tratamento", parametros.ativo],
    queryFn: async () => {
      const resultado = await api.GET("/v1/tipos-tratamento", {
        params: { query: paramsSemUndefined({ ativo: parametros.ativo, limite: 200 }) },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    staleTime: 60_000,
  });
}

/**
 * `GET /v1/tratamentos` (`listarTratamentos`) escopado a um vínculo e um
 * único dia — a lista que aparece no dialogo de detalhe da célula (T10).
 * Inclui tratamentos cancelados: o cancelamento é histórico, nunca some da
 * tela (`Pronto quando` da T10).
 */
export function useTratamentosDoDia(
  vinculoId: string | undefined,
  data: string | undefined,
): UseQueryResult<Esquema<"ListaTratamento">> {
  return useQuery({
    queryKey: ["tratamentos-do-dia", vinculoId, data],
    queryFn: async () => {
      if (!vinculoId || !data) throw new Error("vinculoId/data ausentes");
      const resultado = await api.GET("/v1/tratamentos", {
        params: {
          query: paramsSemUndefined({
            vinculoId,
            de: data,
            ate: data,
            limite: 200,
            ordenar: "criadoEm:desc",
          }),
        },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    enabled: Boolean(vinculoId && data),
  });
}

function invalidarConsultasDoDia(
  queryClient: ReturnType<typeof useQueryClient>,
  vinculoId: string | undefined,
  data: string | undefined,
): void {
  void queryClient.invalidateQueries({ queryKey: ["tratamentos-do-dia", vinculoId, data] });
  void queryClient.invalidateQueries({ queryKey: ["apuracao-do-vinculo-no-dia", vinculoId, data] });
  void queryClient.invalidateQueries({ queryKey: ["apuracoes"] });
  void queryClient.invalidateQueries({ queryKey: ["ocorrencias"] });
}

/**
 * `POST /v1/tratamentos` (`criarTratamento`) — ÚNICA forma de correção de
 * jornada oferecida por esta tela (T10). Nunca chama nem sugere alterar uma
 * marcação: o corpo é sempre `TratamentoCriar`.
 */
export function useCriarTratamento(): UseMutationResult<
  Esquema<"Tratamento">,
  unknown,
  Esquema<"TratamentoCriar">
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (corpo: Esquema<"TratamentoCriar">) => {
      const resultado = await api.POST("/v1/tratamentos", {
        params: { header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Tratamento">;
    },
    onSuccess: (tratamento) => {
      invalidarConsultasDoDia(queryClient, tratamento.vinculoId, tratamento.dataReferencia);
    },
  });
}

/**
 * `PATCH /v1/tratamentos/{tratamentoId}` (`atualizarTratamento`) — só altera
 * tratamento em rascunho ou pendente (regra do servidor, `PONTO-CONF-003`
 * caso contrário).
 */
export function useAtualizarTratamento(): UseMutationResult<
  Esquema<"Tratamento">,
  unknown,
  { tratamentoId: string; corpo: Esquema<"TratamentoAtualizar"> }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ tratamentoId, corpo }) => {
      const resultado = await api.PATCH("/v1/tratamentos/{tratamentoId}", {
        params: {
          path: { tratamentoId },
          header: { "Idempotency-Key": crypto.randomUUID() },
        },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Tratamento">;
    },
    onSuccess: (tratamento) => {
      invalidarConsultasDoDia(queryClient, tratamento.vinculoId, tratamento.dataReferencia);
    },
  });
}

/**
 * `DELETE /v1/tratamentos/{tratamentoId}` (`cancelarTratamento`). O nome no
 * contrato é "cancelar", nunca "excluir": o registro cancelado permanece na
 * trilha (a UI nunca o remove da lista, só muda o rótulo de situação).
 */
export function useCancelarTratamento(): UseMutationResult<
  void,
  unknown,
  { tratamentoId: string; vinculoId: string; data: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ tratamentoId }) => {
      const resultado = await api.DELETE("/v1/tratamentos/{tratamentoId}", {
        params: {
          path: { tratamentoId },
          header: { "Idempotency-Key": crypto.randomUUID() },
        },
      });
      if (resultado.error) throw resultado.error;
    },
    onSuccess: (_dados, variaveis) => {
      invalidarConsultasDoDia(queryClient, variaveis.vinculoId, variaveis.data);
    },
  });
}

/**
 * `POST /v1/tratamentos/{tratamentoId}/decidir` (`decidirTratamento`) —
 * aprovar ou reprovar um tratamento pendente. Aprovar agenda o recálculo do
 * dia (`x-eventos: apuracao.recalculada`); a UI observa o efeito indiretamente
 * via *refetch* de `useApuracaoDoVinculoNoDia`/`useApuracoes` (não há
 * WebSocket, T3/A1 já fixou essa decisão para a fase inteira).
 */
export function useDecidirTratamento(): UseMutationResult<
  Esquema<"Tratamento">,
  unknown,
  { tratamentoId: string; corpo: Esquema<"DecisaoRequisicao"> }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ tratamentoId, corpo }) => {
      const resultado = await api.POST("/v1/tratamentos/{tratamentoId}/decidir", {
        params: {
          path: { tratamentoId },
          header: { "Idempotency-Key": crypto.randomUUID() },
        },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Tratamento">;
    },
    onSuccess: (tratamento) => {
      invalidarConsultasDoDia(queryClient, tratamento.vinculoId, tratamento.dataReferencia);
    },
  });
}
