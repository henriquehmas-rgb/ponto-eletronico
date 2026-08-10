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

/**
 * `GET /v1/aprovacoes` (`listarAprovacoesPendentes`) — fila de aprovação do
 * usuário autenticado, usada pelo card "Fila de aprovações" do `/painel`. O
 * padrão do endpoint já filtra `decisao: pendente`.
 */
export function useAprovacoesPendentes(limite = 5): UseQueryResult<Esquema<"ListaAprovacao">> {
  return useQuery({
    queryKey: ["aprovacoes-pendentes", limite],
    queryFn: async () => {
      const resultado = await api.GET("/v1/aprovacoes", {
        params: { query: paramsSemUndefined({ limite, ordenar: "prazoEm" }) },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
  });
}

/**
 * `GET /v1/aprovacoes` filtrado por `decisao` diferente de "pendente" — usa o
 * mesmo parâmetro `decisao` do contrato (§13276, `listarAprovacoesPendentes`),
 * que aceita um único valor do enum. Alimenta a seção "Decididas recentemente"
 * de `/painel/aprovacoes`.
 */
export function useAprovacoesPorDecisao(
  decisao: "aprovada" | "reprovada",
  limite = 5,
): UseQueryResult<Esquema<"ListaAprovacao">> {
  return useQuery({
    queryKey: ["aprovacoes-por-decisao", decisao, limite],
    queryFn: async () => {
      const resultado = await api.GET("/v1/aprovacoes", {
        params: { query: paramsSemUndefined({ decisao, limite, ordenar: "criadoEm:desc" }) },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
  });
}

export interface ParametrosDeDecisao {
  aprovacaoId: string;
  decisao: "aprovar" | "reprovar";
  /** Obrigatório na reprovação (contrato, `DecisaoRequisicao.comentario`). */
  comentario?: string;
}

/** `POST /v1/aprovacoes/{aprovacaoId}/decidir` (`decidirAprovacao`). */
export function useDecidirAprovacao(): UseMutationResult<
  Esquema<"Aprovacao">,
  unknown,
  ParametrosDeDecisao
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ aprovacaoId, decisao, comentario }: ParametrosDeDecisao) => {
      const resultado = await api.POST("/v1/aprovacoes/{aprovacaoId}/decidir", {
        params: {
          path: { aprovacaoId },
          header: { "Idempotency-Key": crypto.randomUUID() },
        },
        body: { decisao, ...(comentario ? { comentario } : {}) },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Aprovacao">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["aprovacoes-pendentes"] });
    },
  });
}
