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

export interface ParametrosDeListaDeEquipes {
  empresaId?: string | undefined;
  unidadeId?: string | undefined;
  departamentoId?: string | undefined;
  ativo?: boolean | undefined;
  busca?: string | undefined;
  incluirExcluidos?: boolean | undefined;
  cursor?: string | undefined;
}

/**
 * `GET /v1/equipes` (`listarEquipes`) — T6.
 *
 * SEM exclusão no contrato (só `listar`/`criar`/`obter`/`atualizar` +
 * `adicionarMembroEquipe`) — mesma observação de centros de custo/cargos.
 */
export function useEquipes(
  parametros: ParametrosDeListaDeEquipes = {},
): UseQueryResult<Esquema<"ListaEquipe">> {
  return useQuery({
    queryKey: ["equipes", parametros],
    queryFn: async () => {
      const resultado = await api.GET("/v1/equipes", {
        params: { query: paramsSemUndefined({ ordenar: "nome:asc", limite: 200, ...parametros }) },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
  });
}

/** `POST /v1/equipes` (`criarEquipe`). */
export function useCriarEquipe(): UseMutationResult<
  Esquema<"Equipe">,
  unknown,
  Esquema<"EquipeCriar">
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (corpo: Esquema<"EquipeCriar">) => {
      const resultado = await api.POST("/v1/equipes", {
        params: { header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Equipe">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["equipes"] });
    },
  });
}

/** `PATCH /v1/equipes/{equipeId}` (`atualizarEquipe`). */
export function useAtualizarEquipe(): UseMutationResult<
  Esquema<"Equipe">,
  unknown,
  { id: string; corpo: Esquema<"EquipeAtualizar"> }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, corpo }) => {
      const resultado = await api.PATCH("/v1/equipes/{equipeId}", {
        params: { path: { equipeId: id }, header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"Equipe">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["equipes"] });
    },
  });
}

/**
 * Membros da equipe: **não existe** `GET /v1/equipes/{equipeId}/membros` no
 * contrato (só o `POST` de inclusão) — achado registrado em
 * `docs/backlog.md`. Como aproximação honesta, listamos os colaboradores
 * cujo vínculo aponta para esta equipe via `GET /v1/colaboradores?equipeId=`
 * (filtro que o contrato de fato oferece, `listarColaboradores`). Isto
 * mostra QUEM está na equipe, mas não o `papel`/vigência de
 * `EquipeMembro` — só `POST /v1/equipes/{equipeId}/membros` devolve isso.
 */
export function useMembrosDaEquipe(
  equipeId: string | undefined,
): UseQueryResult<Esquema<"ListaColaborador">> {
  return useQuery({
    queryKey: ["equipe-membros", equipeId],
    queryFn: async () => {
      if (!equipeId) throw new Error("equipeId ausente");
      const resultado = await api.GET("/v1/colaboradores", {
        params: { query: { equipeId, limite: 200, ordenar: "nomeCompleto:asc" } },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    enabled: Boolean(equipeId),
  });
}

/**
 * `POST /v1/equipes/{equipeId}/membros` (`adicionarMembroEquipe`).
 *
 * **Não há remoção de membro no contrato** (achado §2/§6 do PCF) — este
 * gancho por isso não expõe nenhuma mutação de remoção.
 */
export function useAdicionarMembroEquipe(): UseMutationResult<
  Esquema<"EquipeMembro">,
  unknown,
  { equipeId: string; corpo: Esquema<"EquipeMembroCriar"> }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ equipeId, corpo }) => {
      const resultado = await api.POST("/v1/equipes/{equipeId}/membros", {
        params: { path: { equipeId }, header: { "Idempotency-Key": crypto.randomUUID() } },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"EquipeMembro">;
    },
    onSuccess: (_dados, variaveis) => {
      void queryClient.invalidateQueries({ queryKey: ["equipe-membros", variaveis.equipeId] });
      void queryClient.invalidateQueries({ queryKey: ["colaboradores"] });
    },
  });
}
