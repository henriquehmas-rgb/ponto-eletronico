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

import { useSessaoAtual } from "./use-sessao";

/** `GET /v1/colaboradores/{colaboradorId}` (`obterColaborador`) do colaborador autenticado. */
export function useColaborador(): UseQueryResult<Esquema<"Colaborador">> {
  const { data: sessaoAtual } = useSessaoAtual();
  const colaboradorId = sessaoAtual?.colaboradorId;

  return useQuery({
    queryKey: ["colaborador", colaboradorId],
    queryFn: async () => {
      if (!colaboradorId) throw new Error("colaboradorId ausente");
      const resultado = await api.GET("/v1/colaboradores/{colaboradorId}", {
        params: { path: { colaboradorId } },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    enabled: Boolean(colaboradorId),
  });
}

/** `GET /v1/dispositivos` (`listarDispositivos`) vinculados ao colaborador autenticado. */
export function useDispositivos(): UseQueryResult<Esquema<"ListaDispositivo">> {
  const { data: sessaoAtual } = useSessaoAtual();
  const colaboradorId = sessaoAtual?.colaboradorId;

  return useQuery({
    queryKey: ["dispositivos", colaboradorId],
    queryFn: async () => {
      const resultado = await api.GET("/v1/dispositivos", {
        params: { query: paramsSemUndefined({ colaboradorId, limite: 100 }) },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    enabled: Boolean(colaboradorId),
  });
}

/** `GET /v1/auth/sessoes` (`listarSessoes`) do usuário autenticado — sessões ativas e dispositivos, tela de perfil. */
export function useSessoesAtivas(): UseQueryResult<Esquema<"ListaSessao">> {
  const sessao = useSessaoAtual();
  return useQuery({
    queryKey: ["sessoes-ativas"],
    queryFn: async () => {
      const resultado = await api.GET("/v1/auth/sessoes", { params: { query: { limite: 100 } } });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    enabled: Boolean(sessao.data),
  });
}

/** `DELETE /v1/auth/sessoes/{sessaoId}` (`revogarSessao`). */
export function useRevogarSessao(): UseMutationResult<void, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (sessaoId: string) => {
      const resultado = await api.DELETE("/v1/auth/sessoes/{sessaoId}", {
        params: { path: { sessaoId }, header: { "Idempotency-Key": crypto.randomUUID() } },
      });
      if (resultado.error) throw resultado.error;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["sessoes-ativas"] });
    },
  });
}
