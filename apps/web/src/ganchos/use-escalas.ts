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

export interface ParametrosDeListaDeEscalas {
  empresaId?: string | undefined;
  tipo?: Esquema<"Escala">["tipo"] | undefined;
  ativo?: boolean | undefined;
  cursor?: string | undefined;
}

/** `GET /v1/escalas` (`listarEscalas`) — padrões cíclicos de trabalho e folga. */
export function useEscalas(
  parametros: ParametrosDeListaDeEscalas = {},
): UseQueryResult<Esquema<"ListaEscala">> {
  return useQuery({
    queryKey: [
      "escalas",
      parametros.empresaId,
      parametros.tipo,
      parametros.ativo,
      parametros.cursor,
    ],
    queryFn: async () => {
      const resultado = await api.GET("/v1/escalas", {
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

/** `GET /v1/escalas/{escalaId}` (`obterEscala`) — composição completa do ciclo. */
export function useEscala(escalaId: string | undefined): UseQueryResult<Esquema<"Escala">> {
  return useQuery({
    queryKey: ["escala", escalaId],
    queryFn: async () => {
      if (!escalaId) throw new Error("escalaId ausente");
      const resultado = await api.GET("/v1/escalas/{escalaId}", {
        params: { path: { escalaId } },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    enabled: Boolean(escalaId),
  });
}

/** `POST /v1/escalas` (`criarEscala`). */
export function useCriarEscala(): UseMutationResult<
  Esquema<"Escala">,
  unknown,
  Esquema<"EscalaCriar">
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (corpo: Esquema<"EscalaCriar">) => {
      const resultado = await api.POST("/v1/escalas", {
        params: { header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Escala">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["escalas"] });
    },
  });
}

export interface ParametrosDeAtualizarEscala {
  escalaId: string;
  corpo: Esquema<"EscalaAtualizar">;
}

/** `PATCH /v1/escalas/{escalaId}` (`atualizarEscala`) — atualização parcial. */
export function useAtualizarEscala(): UseMutationResult<
  Esquema<"Escala">,
  unknown,
  ParametrosDeAtualizarEscala
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ escalaId, corpo }: ParametrosDeAtualizarEscala) => {
      const resultado = await api.PATCH("/v1/escalas/{escalaId}", {
        params: { path: { escalaId }, header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Escala">;
    },
    onSuccess: (_dados, variaveis) => {
      void queryClient.invalidateQueries({ queryKey: ["escalas"] });
      void queryClient.invalidateQueries({ queryKey: ["escala", variaveis.escalaId] });
    },
  });
}

/**
 * `DELETE /v1/escalas/{escalaId}` (`excluirEscala`) — exclusão lógica,
 * recusada (`PONTO-CONF-004`) quando há atribuições vigentes.
 */
export function useExcluirEscala(): UseMutationResult<void, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (escalaId: string) => {
      const resultado = await api.DELETE("/v1/escalas/{escalaId}", {
        params: { path: { escalaId }, header: { "Idempotency-Key": crypto.randomUUID() } },
      });
      if (resultado.error) throw resultado.error;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["escalas"] });
    },
  });
}

export interface ParametrosDeAtribuicao {
  escalaId: string;
  corpo: Esquema<"EscalaAtribuicaoCriar">;
}

/**
 * `POST /v1/escalas/{escalaId}/atribuicoes` (`atribuirEscalaVinculo`).
 * Também a operação usada por "copiar período" (T13) — uma chamada por
 * vínculo-alvo, `posicaoInicial` recalculado no cliente (achado de contrato
 * nº 2, PCF §2).
 */
export function useAtribuirEscalaVinculo(): UseMutationResult<
  Esquema<"EscalaAtribuicao">,
  unknown,
  ParametrosDeAtribuicao
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ escalaId, corpo }: ParametrosDeAtribuicao) => {
      const resultado = await api.POST("/v1/escalas/{escalaId}/atribuicoes", {
        params: { path: { escalaId }, header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"EscalaAtribuicao">;
    },
    onSuccess: () => {
      // Não há leitura em lote de atribuições (achado de contrato nº 1) —
      // o que muda de verdade é a resolução por vínculo/dia.
      void queryClient.invalidateQueries({ queryKey: ["resolucao-jornada"] });
      void queryClient.invalidateQueries({ queryKey: ["apuracoes"] });
    },
  });
}
