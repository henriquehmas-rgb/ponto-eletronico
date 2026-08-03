"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import { api, type Esquema } from "@/lib/api";

/**
 * Gancho de `GET/PUT /v1/admin/sso/provedores` (`obterConfiguracaoSso`/
 * `atualizarConfiguracaoSso`, RFC-018/ADR-013). As duas operações são
 * superfície ÚNICA para os três provedores (google/entra_id/saml — RFC-018
 * não separa a configuração por protocolo, ver descrição da operação no
 * contrato); a tela de configuração de IdP por tenant (T22, A10,
 * `apps/web/src/app/painel/cadastros/sso/**`) só lê/escreve os três campos
 * `saml*`, mas o corpo inteiro (`ConfiguracaoSso`) é sempre enviado/recebido
 * junto — mesmo padrão de atualização parcial que o backend
 * (`app.identidade.sso.oidc.configuracao.atualizar_configuracao`, A9)
 * documenta: campo omitido mantém o valor anterior.
 */

const CHAVE_CONSULTA = ["sso-provedores"] as const;

/** `GET /v1/admin/sso/provedores`. */
export function useConfiguracaoSso(): UseQueryResult<Esquema<"ConfiguracaoSso">> {
  return useQuery({
    queryKey: CHAVE_CONSULTA,
    queryFn: async () => {
      const resultado = await api.GET("/v1/admin/sso/provedores", {});
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
  });
}

/** `PUT /v1/admin/sso/provedores`. */
export function useAtualizarConfiguracaoSso(): UseMutationResult<
  Esquema<"ConfiguracaoSso">,
  unknown,
  Esquema<"ConfiguracaoSso">
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (corpo: Esquema<"ConfiguracaoSso">) => {
      const resultado = await api.PUT("/v1/admin/sso/provedores", {
        params: { header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"ConfiguracaoSso">;
    },
    onSuccess: (dados) => {
      queryClient.setQueryData(CHAVE_CONSULTA, dados);
    },
  });
}
