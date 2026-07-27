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

export interface ParametrosDeListaDeColaboradores {
  empresaId?: string | undefined;
  unidadeId?: string | undefined;
  departamentoId?: string | undefined;
  equipeId?: string | undefined;
  gestorColaboradorId?: string | undefined;
  status?: Esquema<"Colaborador">["status"] | undefined;
  cpf?: string | undefined;
  matricula?: string | undefined;
  admitidoDe?: string | undefined;
  admitidoAte?: string | undefined;
  incluirInativos?: boolean | undefined;
  busca?: string | undefined;
  incluirExcluidos?: boolean | undefined;
  cursor?: string | undefined;
  limite?: number | undefined;
}

/** `GET /v1/colaboradores` (`listarColaboradores`) — T7. Escopo hierárquico já aplicado pelo servidor. */
export function useColaboradores(
  parametros: ParametrosDeListaDeColaboradores = {},
): UseQueryResult<Esquema<"ListaColaborador">> {
  return useQuery({
    queryKey: ["colaboradores", parametros],
    queryFn: async () => {
      const resultado = await api.GET("/v1/colaboradores", {
        params: {
          query: paramsSemUndefined({
            ordenar: "nomeCompleto:asc",
            limite: 100,
            ...parametros,
          }),
        },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
  });
}

/** `GET /v1/colaboradores/{colaboradorId}` (`obterColaborador`) — página de detalhe (T7). */
export function useColaborador(
  colaboradorId: string | undefined,
): UseQueryResult<Esquema<"Colaborador">> {
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

/**
 * `POST /v1/colaboradores` (`criarColaborador`). Criar o colaborador NÃO
 * cria vínculo — o contrato é explícito: use `useCriarVinculo` (`use-vinculos.ts`)
 * depois, para estabelecer a relação de trabalho que a apuração consome.
 */
export function useCriarColaborador(): UseMutationResult<
  Esquema<"Colaborador">,
  unknown,
  Esquema<"ColaboradorCriar">
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (corpo: Esquema<"ColaboradorCriar">) => {
      const resultado = await api.POST("/v1/colaboradores", {
        params: { header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Colaborador">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["colaboradores"] });
    },
  });
}

/** `PATCH /v1/colaboradores/{colaboradorId}` (`atualizarColaborador`). */
export function useAtualizarColaborador(): UseMutationResult<
  Esquema<"Colaborador">,
  unknown,
  { id: string; corpo: Esquema<"ColaboradorAtualizar"> }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, corpo }) => {
      const resultado = await api.PATCH("/v1/colaboradores/{colaboradorId}", {
        params: { path: { colaboradorId: id }, header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Colaborador">;
    },
    onSuccess: (_dados, variaveis) => {
      void queryClient.invalidateQueries({ queryKey: ["colaboradores"] });
      void queryClient.invalidateQueries({ queryKey: ["colaborador", variaveis.id] });
    },
  });
}

/** `DELETE /v1/colaboradores/{colaboradorId}` (`excluirColaborador`) — exclusão lógica. */
export function useExcluirColaborador(): UseMutationResult<void, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (colaboradorId: string) => {
      const resultado = await api.DELETE("/v1/colaboradores/{colaboradorId}", {
        params: { path: { colaboradorId }, header: { "Idempotency-Key": crypto.randomUUID() } },
      });
      if (resultado.error) throw resultado.error;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["colaboradores"] });
    },
  });
}

/** `GET /v1/colaboradores/{colaboradorId}/gestores` (`listarGestoresColaborador`). */
export function useGestoresDoColaborador(
  colaboradorId: string | undefined,
): UseQueryResult<Esquema<"ListaColaboradorGestor">> {
  return useQuery({
    queryKey: ["colaborador-gestores", colaboradorId],
    queryFn: async () => {
      if (!colaboradorId) throw new Error("colaboradorId ausente");
      const resultado = await api.GET("/v1/colaboradores/{colaboradorId}/gestores", {
        params: { path: { colaboradorId }, query: { limite: 50 } },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    enabled: Boolean(colaboradorId),
  });
}

/**
 * `PUT /v1/colaboradores/{colaboradorId}/gestores` (`definirGestoresColaborador`).
 * Substitui a vigência do TIPO de gestão informado (imediato/substituto/
 * matricial/rh) — não é uma lista em lote, é um vínculo de gestão por vez.
 */
export function useDefinirGestorDoColaborador(): UseMutationResult<
  Esquema<"ColaboradorGestor">,
  unknown,
  { colaboradorId: string; corpo: Esquema<"ColaboradorGestorCriar"> }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ colaboradorId, corpo }) => {
      const resultado = await api.PUT("/v1/colaboradores/{colaboradorId}/gestores", {
        params: { path: { colaboradorId }, header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"ColaboradorGestor">;
    },
    onSuccess: (_dados, variaveis) => {
      void queryClient.invalidateQueries({
        queryKey: ["colaborador-gestores", variaveis.colaboradorId],
      });
    },
  });
}

/**
 * `POST /v1/colaboradores/importar` (`importarColaboradores`) — processamento
 * assíncrono (`Importacao`, `status: recebido|validando|processando|concluido|
 * concluido_com_erros|falhou|cancelado`). `conteudoRef` pressupõe um arquivo já
 * enviado ao armazenamento de objetos — não existe, em nenhuma tag do
 * `openapi.yaml`, endpoint de upload para obter essa referência (achado já
 * documentado em `docs/backlog.md`, mesma lacuna que `worker/tarefas/
 * importacoes.py` registra para F2/F6). Por isso o formulário desta tela pede
 * `conteudoRef` como texto (a app não tem como gerar essa chave sozinha).
 *
 * NOTA: `apps/web/src/lib/api/tipos.gerado.ts` está desatualizado em relação
 * a `openapi.yaml` (achado já registrado em `docs/backlog.md`, 2026-07-27,
 * F8/A1) — `ImportacaoCriar.conteudoRef` existe no contrato real (RFC-007)
 * mas não no tipo gerado. Por isso o parâmetro aceita um campo extra e o
 * corpo é convertido para o tipo gerado só na fronteira da chamada HTTP, sem
 * regenerar `tipos.gerado.ts` (proibição §9 do PCF — só `pnpm tipos:api:check`).
 */
export function useImportarColaboradores(): UseMutationResult<
  Esquema<"Importacao">,
  unknown,
  Esquema<"ImportacaoCriar"> & { conteudoRef: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (corpo: Esquema<"ImportacaoCriar"> & { conteudoRef: string }) => {
      const resultado = await api.POST("/v1/colaboradores/importar", {
        params: { header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo as Esquema<"ImportacaoCriar">,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Importacao">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["colaboradores"] });
    },
  });
}
