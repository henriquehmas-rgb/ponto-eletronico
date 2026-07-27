"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { api, type Esquema } from "@/lib/api";
import { useSessao as useSessaoDeAutenticacao } from "@/lib/sessao";

/**
 * Consulta `GET /v1/auth/sessao` (`obterSessaoAtual`) via TanStack Query.
 *
 * Distinto de `useSessao` (`@/lib/sessao`, contrato fixado entre F8 e F9b —
 * só `usuario`/`tenant`/`autenticado`/`carregando` e as ações de entrar/sair):
 * este gancho traz o CONTEXTO completo da sessão, em particular
 * `colaboradorId` — que os ganchos de espelho de ponto, banco de horas e
 * apuração desta fase (T2/T3) precisam para montar `GET /v1/banco-horas/
 * {colaboradorId}/...` e para escopar `listarMarcacoes`/`listarApuracoes` ao
 * próprio colaborador. Nunca chamado antes de `autenticado === true` — a
 * operação exige `bearerAuth`.
 */
export function useSessaoAtual(): UseQueryResult<Esquema<"SessaoAtual">> {
  const sessao = useSessaoDeAutenticacao();
  return useQuery({
    queryKey: ["sessao-atual"],
    queryFn: async () => {
      const resultado = await api.GET("/v1/auth/sessao");
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    enabled: sessao.autenticado,
    staleTime: 60_000,
  });
}
