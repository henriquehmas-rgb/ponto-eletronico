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
 * Ganchos da tela genérica de relatórios (T4, F11/A1).
 *
 * Um único conjunto de ganchos serve os 24 relatórios do catálogo: nenhum
 * gancho aqui conhece o `codigo` de um relatório específico (PCF §6/T4,
 * proibição 13 — "não crie tela de frontend por relatório específico"). A
 * tela (`app/painel/relatorios/**`) monta o formulário de execução
 * dinamicamente a partir de `RelatorioDefinicao.colunasDisponiveis`/
 * `filtrosDisponiveis`/`agrupamentos` devolvidos por `useRelatorio`.
 */

const LIMITE_PAGINA = 50;

// =============================================================================
// Catálogo (`listarRelatorios`, `obterRelatorio`)
// =============================================================================
export interface ParametrosDeCatalogoDeRelatorios {
  categoria?: Esquema<"RelatorioDefinicao">["categoria"] | undefined;
  sistema?: boolean | undefined;
  ativo?: boolean | undefined;
}

/** `GET /v1/relatorios` (`listarRelatorios`) — o catálogo completo, paginado
 * internamente até esgotar (24 relatórios de fábrica, mais eventuais
 * variantes do cliente). */
export function useCatalogoDeRelatorios(
  parametros: ParametrosDeCatalogoDeRelatorios = {},
): UseQueryResult<Esquema<"RelatorioDefinicao">[]> {
  return useQuery({
    queryKey: ["relatorios-catalogo", parametros],
    queryFn: async () => {
      const dados: Esquema<"RelatorioDefinicao">[] = [];
      let cursor: string | undefined;
      do {
        const resultado = await api.GET("/v1/relatorios", {
          params: {
            query: paramsSemUndefined({
              categoria: parametros.categoria,
              sistema: parametros.sistema,
              ativo: parametros.ativo,
              cursor,
              limite: LIMITE_PAGINA,
              ordenar: "codigo:asc",
            }),
          },
        });
        if (resultado.error) throw resultado.error;
        dados.push(...(resultado.data?.dados ?? []));
        cursor = resultado.data?.paginacao?.proximoCursor;
      } while (cursor);
      return dados;
    },
  });
}

/** `GET /v1/relatorios/{codigo}` (`obterRelatorio`) — a definição completa
 * (colunas/filtros/agrupamentos/formatos) que dirige o formulário dinâmico. */
export function useRelatorio(
  codigo: string | undefined,
): UseQueryResult<Esquema<"RelatorioDefinicao">> {
  return useQuery({
    queryKey: ["relatorio-definicao", codigo],
    queryFn: async () => {
      if (!codigo) throw new Error("codigo ausente");
      const resultado = await api.GET("/v1/relatorios/{codigo}", {
        params: { path: { codigo } },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    enabled: Boolean(codigo),
  });
}

// =============================================================================
// Execução (`executarRelatorio`, `obterExecucaoRelatorio`)
// =============================================================================
export interface ParametrosDeExecucaoDeRelatorio {
  formato?: "json" | "csv" | "xlsx" | "pdf" | undefined;
  periodoId?: string | undefined;
  de?: string | undefined;
  ate?: string | undefined;
  empresaId?: string | undefined;
  unidadeId?: string | undefined;
  departamentoId?: string | undefined;
  colaboradorId?: string | undefined;
  agrupamento?: string | undefined;
  colunas?: string[] | undefined;
  filtros?: Record<string, unknown> | undefined;
  converterDecimal?: boolean | undefined;
  incluirInativos?: boolean | undefined;
  assincrono?: boolean | undefined;
}

/**
 * `GET /v1/relatorios/{codigo}/executar` (`executarRelatorio`) — exposto
 * como mutação (não `useQuery`) porque tem efeito colateral real (cria uma
 * `RelatorioExecucao`, síncrona já concluída ou assíncrona enfileirada);
 * nunca deve dispersar automaticamente nem ficar em cache de leitura.
 */
export function useExecutarRelatorio(): UseMutationResult<
  Esquema<"RelatorioExecucao">,
  unknown,
  { codigo: string; parametros: ParametrosDeExecucaoDeRelatorio }
> {
  return useMutation({
    mutationFn: async ({ codigo, parametros }) => {
      const resultado = await api.GET("/v1/relatorios/{codigo}/executar", {
        params: {
          path: { codigo },
          query: paramsSemUndefined({
            formato: parametros.formato,
            periodoId: parametros.periodoId,
            de: parametros.de,
            ate: parametros.ate,
            empresaId: parametros.empresaId,
            unidadeId: parametros.unidadeId,
            departamentoId: parametros.departamentoId,
            colaboradorId: parametros.colaboradorId,
            agrupamento: parametros.agrupamento,
            colunas: parametros.colunas?.join(","),
            filtros: parametros.filtros ? JSON.stringify(parametros.filtros) : undefined,
            converterDecimal: parametros.converterDecimal,
            incluirInativos: parametros.incluirInativos,
            assincrono: parametros.assincrono,
          }),
        },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"RelatorioExecucao">;
    },
  });
}

/**
 * `GET /v1/relatorios/execucoes/{execucaoId}` (`obterExecucaoRelatorio`) —
 * acompanha o progresso. Faz *poll* a cada `intervaloMs` (padrão 2s)
 * enquanto `status` for `enfileirado`/`processando`; para sozinho ao
 * concluir/falhar/expirar (T4, "acompanhamento de progresso").
 */
export function useExecucaoDeRelatorio(
  execucaoId: string | undefined,
  opcoes: { intervaloMs?: number } = {},
): UseQueryResult<Esquema<"RelatorioExecucao">> {
  const intervaloMs = opcoes.intervaloMs ?? 2000;
  return useQuery({
    queryKey: ["relatorio-execucao", execucaoId],
    queryFn: async () => {
      if (!execucaoId) throw new Error("execucaoId ausente");
      const resultado = await api.GET("/v1/relatorios/execucoes/{execucaoId}", {
        params: { path: { execucaoId } },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    enabled: Boolean(execucaoId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "enfileirado" || status === "processando") return intervaloMs;
      return false;
    },
  });
}

// =============================================================================
// Preferências de colunas (RFC-015)
// =============================================================================
export interface ParametrosDePreferenciasDeColunas {
  relatorioDefinicaoId?: string | undefined;
  tela?: string | undefined;
}

/** `GET /v1/relatorios/preferencias-colunas` (`listarPreferenciasColunas`)
 * — sempre as preferências do próprio usuário autenticado (RFC-015). */
export function usePreferenciasDeColunas(
  parametros: ParametrosDePreferenciasDeColunas,
): UseQueryResult<Esquema<"PreferenciaColunas">[]> {
  return useQuery({
    queryKey: ["preferencias-colunas", parametros],
    queryFn: async () => {
      const resultado = await api.GET("/v1/relatorios/preferencias-colunas", {
        params: {
          query: paramsSemUndefined({
            relatorioDefinicaoId: parametros.relatorioDefinicaoId,
            tela: parametros.tela,
            limite: LIMITE_PAGINA,
          }),
        },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data?.dados ?? [];
    },
    enabled: Boolean(parametros.relatorioDefinicaoId || parametros.tela),
  });
}

/** A preferência `"padrao"` de um relatório, ou `undefined` se o usuário
 * nunca salvou uma — usada pela tela de execução para pré-carregar o
 * seletor de colunas. */
export function usePreferenciaPadraoDoRelatorio(
  relatorioDefinicaoId: string | undefined,
): UseQueryResult<Esquema<"PreferenciaColunas"> | undefined> {
  return useQuery({
    queryKey: ["preferencia-colunas-padrao", relatorioDefinicaoId],
    queryFn: async () => {
      if (!relatorioDefinicaoId) throw new Error("relatorioDefinicaoId ausente");
      const resultado = await api.GET("/v1/relatorios/preferencias-colunas", {
        params: { query: { relatorioDefinicaoId, limite: 50 } },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data?.dados?.find((item) => item.nome === "padrao") ?? undefined;
    },
    enabled: Boolean(relatorioDefinicaoId),
  });
}

/** `PUT /v1/relatorios/preferencias-colunas` (`salvarPreferenciaColunas`) —
 * sem `Idempotency-Key` (RFC-015, decisão 2): o corpo descreve o estado
 * final completo. */
export function useSalvarPreferenciaDeColunas(): UseMutationResult<
  Esquema<"PreferenciaColunas">,
  unknown,
  Esquema<"PreferenciaColunasCriar">
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (corpo: Esquema<"PreferenciaColunasCriar">) => {
      const resultado = await api.PUT("/v1/relatorios/preferencias-colunas", { body: corpo });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"PreferenciaColunas">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["preferencias-colunas"] });
      void queryClient.invalidateQueries({ queryKey: ["preferencia-colunas-padrao"] });
    },
  });
}
