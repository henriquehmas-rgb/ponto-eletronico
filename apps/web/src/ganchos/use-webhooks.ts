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
 * Ganchos do painel de entregas de webhook (T14, F13/A4).
 *
 * As sete operações da tag `webhooks` são ownership de A3
 * (`apps/api/app/routers/webhooks.py`); este arquivo só consome o contrato
 * pelo cliente gerado (`@/lib/api`), mesmo padrão de qualquer outro domínio
 * do painel (ex. `use-dispositivos.ts`, F9a). Nenhuma lógica de entrega,
 * cifra ou retentativa mora aqui — só leitura/escrita HTTP e invalidação de
 * cache.
 */

// =============================================================================
// Webhooks (`listarWebhooks`, `obterWebhook`, `criarWebhook`, `atualizarWebhook`, `excluirWebhook`)
// =============================================================================

export interface ParametrosDeListaDeWebhooks {
  apiClientId?: string | undefined;
  evento?: string | undefined;
  status?: Esquema<"Webhook">["status"] | undefined;
  cursor?: string | undefined;
}

/** `GET /v1/webhooks` (`listarWebhooks`). Campos aceitos em `ordenar`: `nome`, `ultimaEntregaEm`. */
export function useWebhooks(
  parametros: ParametrosDeListaDeWebhooks = {},
): UseQueryResult<Esquema<"ListaWebhook">> {
  return useQuery({
    queryKey: ["webhooks", parametros],
    queryFn: async () => {
      const resultado = await api.GET("/v1/webhooks", {
        params: { query: paramsSemUndefined({ ordenar: "nome:asc", limite: 100, ...parametros }) },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
  });
}

/** `GET /v1/webhooks/{webhookId}` (`obterWebhook`). */
export function useWebhook(webhookId: string | undefined): UseQueryResult<Esquema<"Webhook">> {
  return useQuery({
    queryKey: ["webhook", webhookId],
    queryFn: async () => {
      if (!webhookId) throw new Error("webhookId ausente");
      const resultado = await api.GET("/v1/webhooks/{webhookId}", {
        params: { path: { webhookId } },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    enabled: Boolean(webhookId),
  });
}

/** `POST /v1/webhooks` (`criarWebhook`). O segredo HMAC devolvido aparece uma única vez. */
export function useCriarWebhook(): UseMutationResult<
  Esquema<"WebhookCriado">,
  unknown,
  Esquema<"WebhookCriar">
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (corpo: Esquema<"WebhookCriar">) => {
      const resultado = await api.POST("/v1/webhooks", {
        params: { header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"WebhookCriado">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["webhooks"] });
    },
  });
}

/** `PATCH /v1/webhooks/{webhookId}` (`atualizarWebhook`). Reativar zera `falhasConsecutivas`. */
export function useAtualizarWebhook(): UseMutationResult<
  Esquema<"Webhook">,
  unknown,
  { id: string; corpo: Esquema<"WebhookAtualizar"> }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, corpo }) => {
      const resultado = await api.PATCH("/v1/webhooks/{webhookId}", {
        params: { path: { webhookId: id }, header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Webhook">;
    },
    onSuccess: (_dados, variaveis) => {
      void queryClient.invalidateQueries({ queryKey: ["webhooks"] });
      void queryClient.invalidateQueries({ queryKey: ["webhook", variaveis.id] });
    },
  });
}

/** `DELETE /v1/webhooks/{webhookId}` (`excluirWebhook`) — remove a assinatura; entregas pendentes são canceladas. */
export function useExcluirWebhook(): UseMutationResult<void, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (webhookId: string) => {
      const resultado = await api.DELETE("/v1/webhooks/{webhookId}", {
        params: { path: { webhookId }, header: { "Idempotency-Key": crypto.randomUUID() } },
      });
      if (resultado.error) throw resultado.error;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["webhooks"] });
    },
  });
}

// =============================================================================
// Entregas (`listarEntregasWebhook`, `reenviarEntregaWebhook`)
// =============================================================================

export interface ParametrosDeListaDeEntregas {
  status?: Esquema<"WebhookEntrega">["status"] | undefined;
  evento?: string | undefined;
  de?: string | undefined;
  ate?: string | undefined;
  cursor?: string | undefined;
}

/** `GET /v1/webhooks/{webhookId}/entregas` (`listarEntregasWebhook`). Campo aceito em `ordenar`: `criadoEm`. */
export function useEntregasWebhook(
  webhookId: string | undefined,
  parametros: ParametrosDeListaDeEntregas = {},
): UseQueryResult<Esquema<"ListaWebhookEntrega">> {
  return useQuery({
    queryKey: ["webhook-entregas", webhookId, parametros],
    queryFn: async () => {
      if (!webhookId) throw new Error("webhookId ausente");
      const resultado = await api.GET("/v1/webhooks/{webhookId}/entregas", {
        params: {
          path: { webhookId },
          query: paramsSemUndefined({ ordenar: "criadoEm:desc", limite: 50, ...parametros }),
        },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    enabled: Boolean(webhookId),
  });
}

/**
 * `POST /v1/webhooks/{webhookId}/entregas/{entregaId}/reenviar` (`reenviarEntregaWebhook`) —
 * reenvia mesmo uma entrega já em `dlq`; o identificador do evento é preservado.
 */
export function useReenviarEntregaWebhook(): UseMutationResult<
  Esquema<"WebhookEntrega">,
  unknown,
  { webhookId: string; entregaId: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ webhookId, entregaId }) => {
      const resultado = await api.POST("/v1/webhooks/{webhookId}/entregas/{entregaId}/reenviar", {
        params: {
          path: { webhookId, entregaId },
          header: { "Idempotency-Key": crypto.randomUUID() },
        },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"WebhookEntrega">;
    },
    onSuccess: (_dados, variaveis) => {
      void queryClient.invalidateQueries({ queryKey: ["webhook-entregas", variaveis.webhookId] });
      void queryClient.invalidateQueries({ queryKey: ["webhook", variaveis.webhookId] });
    },
  });
}
