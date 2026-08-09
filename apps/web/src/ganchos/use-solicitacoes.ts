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

export interface ParametrosDeListaDeSolicitacoes {
  status?: Esquema<"Solicitacao">["status"];
  categoria?: Esquema<"TipoSolicitacao">["categoria"];
  cursor?: string;
}

/**
 * `GET /v1/solicitacoes` (`listarSolicitacoes`), sempre `minhas=true`: o
 * portal do colaborador só lista os PRÓPRIOS pedidos — ver solicitações de
 * terceiros é tela de RH/gestor (F9b, `/painel`), fora do escopo desta fase.
 */
export function useSolicitacoes(
  parametros: ParametrosDeListaDeSolicitacoes = {},
): UseQueryResult<Esquema<"ListaSolicitacao">> {
  return useQuery({
    queryKey: ["solicitacoes", parametros.status, parametros.categoria, parametros.cursor],
    queryFn: async () => {
      const resultado = await api.GET("/v1/solicitacoes", {
        params: {
          query: paramsSemUndefined({
            minhas: true,
            status: parametros.status,
            categoria: parametros.categoria,
            cursor: parametros.cursor,
            ordenar: "criadoEm:desc",
          }),
        },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
  });
}

/** `GET /v1/solicitacoes/{solicitacaoId}` (`obterSolicitacao`) — usado pela fila de aprovações do `/painel` (T-painel). */
export function useSolicitacao(
  solicitacaoId: string | undefined,
): UseQueryResult<Esquema<"Solicitacao">> {
  return useQuery({
    queryKey: ["solicitacao", solicitacaoId],
    queryFn: async () => {
      if (!solicitacaoId) throw new Error("solicitacaoId ausente");
      const resultado = await api.GET("/v1/solicitacoes/{solicitacaoId}", {
        params: { path: { solicitacaoId } },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    enabled: Boolean(solicitacaoId),
  });
}

/**
 * `POST /v1/solicitacoes` (`criarSolicitacao`) — contrato real; o *handler*
 * ainda responde `501`/`PONTO-INT-005` (F10 pendente, §2 do PCF). A tela
 * (T4) trata esse código com um estado "disponível em breve" — este gancho
 * só encaminha o erro, sem reinterpretar.
 */
export function useCriarSolicitacao(): UseMutationResult<
  Esquema<"Solicitacao">,
  unknown,
  Esquema<"SolicitacaoCriar">
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (corpo: Esquema<"SolicitacaoCriar">) => {
      const resultado = await api.POST("/v1/solicitacoes", {
        params: { header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Solicitacao">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["solicitacoes"] });
    },
  });
}
