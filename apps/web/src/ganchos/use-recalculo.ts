"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { api, type Esquema } from "@/lib/api";

/**
 * Intervalo antes de tentar refletir o resultado de um recálculo assíncrono
 * na grade. Não existe endpoint de consulta de status por identificador
 * (`docs/backlog.md`, achado da F4) — a UI nunca faz *polling* de um
 * identificador; em vez disso, dispara um único *refetch* das apurações após
 * um intervalo curto, junto com o botão manual "Atualizar" que a T11 expõe.
 */
const INTERVALO_REFETCH_APOS_RECALCULO_MS = 5_000;

/**
 * `POST /v1/apuracoes/recalcular` (`recalcularApuracoes`) — T11. Responde
 * `202` com `ProcessamentoAssincrono` (`status: "enfileirado"`); o motor é
 * determinístico e compara o hash dos insumos antes de reprocessar, então
 * chamar de novo sobre o mesmo escopo é seguro.
 */
export function useRecalcularApuracoes(): UseMutationResult<
  Esquema<"ProcessamentoAssincrono">,
  unknown,
  Esquema<"RecalculoRequisicao">
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (corpo: Esquema<"RecalculoRequisicao">) => {
      const resultado = await api.POST("/v1/apuracoes/recalcular", {
        params: { header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"ProcessamentoAssincrono">;
    },
    onSuccess: () => {
      setTimeout(() => {
        void queryClient.invalidateQueries({ queryKey: ["apuracoes"] });
        void queryClient.invalidateQueries({ queryKey: ["ocorrencias"] });
      }, INTERVALO_REFETCH_APOS_RECALCULO_MS);
    },
  });
}
