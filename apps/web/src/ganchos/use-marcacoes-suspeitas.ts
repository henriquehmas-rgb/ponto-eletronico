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
 * Fila de revisão do gestor (F14/A1, ADR-008) — painel de marcações
 * suspeitas em `apps/web/src/app/painel/antifraude/`.
 *
 * `GET /v1/marcacoes/revisao-pendente` (RFC-020, decidida no fechamento da
 * F14): rota dedicada, server-side, sobre o índice parcial de
 * `marcacoes_meta (tenant_id, revisao_status)` — substitui a versão anterior
 * deste gancho, que buscava `GET /v1/marcacoes?incluirMeta=true` e filtrava
 * `revisaoStatus === 'pendente'` NO CLIENTE (não escalava para tenants com
 * muitas marcações por página).
 *
 * Exige `marcacoes.ler_sensivel` de verdade: sem essa permissão a chamada
 * responde `403 PONTO-PERM-001`, não uma lista vazia — por isso este gancho
 * só deve ser usado atrás de `<PortaoDePermissao permissao=
 * "marcacoes.ler_sensivel">` (ver `page.tsx`).
 */

export type ItemDeRevisaoPendente = Esquema<"ItemRevisaoPendente"> & {
  marcacaoId: string;
};

export interface MarcacaoSuspeita {
  item: ItemDeRevisaoPendente;
  nomeColaborador: string | undefined;
}

export interface ParametrosDeMarcacoesSuspeitas {
  empresaId?: string | undefined;
  habilitado?: boolean;
}

const LIMITE_DE_PAGINAS_DE_SEGURANCA = 20;
const TAMANHO_DE_PAGINA = 100;

function paramsSemUndefined<T extends Record<string, unknown>>(
  objeto: T,
): { [K in keyof T]?: Exclude<T[K], undefined> } {
  const resultado: Record<string, unknown> = {};
  for (const [chave, valor] of Object.entries(objeto)) {
    if (valor !== undefined) resultado[chave] = valor;
  }
  return resultado as { [K in keyof T]?: Exclude<T[K], undefined> };
}

async function buscarPendentes(filtros: {
  empresaId?: string | undefined;
}): Promise<ItemDeRevisaoPendente[]> {
  const pendentes: ItemDeRevisaoPendente[] = [];
  let cursor: string | undefined;
  let paginas = 0;
  do {
    const resultado = await api.GET("/v1/marcacoes/revisao-pendente", {
      params: {
        query: paramsSemUndefined({
          empresaId: filtros.empresaId,
          limite: TAMANHO_DE_PAGINA,
          cursor,
        }),
      },
    });
    if (resultado.error) throw resultado.error;
    for (const item of resultado.data?.dados ?? []) {
      if (item.marcacaoId) pendentes.push(item as ItemDeRevisaoPendente);
    }
    cursor = resultado.data?.paginacao?.proximoCursor;
    paginas += 1;
  } while (cursor && paginas < LIMITE_DE_PAGINAS_DE_SEGURANCA);
  return pendentes;
}

async function buscarMapaDeNomes(filtros: {
  empresaId?: string | undefined;
}): Promise<Map<string, string>> {
  const resultado = await api.GET("/v1/colaboradores", {
    params: {
      query: paramsSemUndefined({
        empresaId: filtros.empresaId,
        limite: 200,
      }),
    },
  });
  if (resultado.error) throw resultado.error;
  const mapa = new Map<string, string>();
  for (const colaborador of resultado.data?.dados ?? []) {
    if (colaborador.id) {
      mapa.set(
        colaborador.id,
        colaborador.nomeSocial || colaborador.nomeCompleto || colaborador.id,
      );
    }
  }
  return mapa;
}

export function useMarcacoesSuspeitas(
  parametros: ParametrosDeMarcacoesSuspeitas = {},
): UseQueryResult<MarcacaoSuspeita[]> {
  const { empresaId, habilitado = true } = parametros;

  return useQuery({
    queryKey: ["marcacoes-suspeitas", empresaId],
    queryFn: async () => {
      const [pendentes, nomes] = await Promise.all([
        buscarPendentes({ empresaId }),
        buscarMapaDeNomes({ empresaId }).catch(() => new Map<string, string>()),
      ]);
      return pendentes
        .map((item) => ({
          item,
          nomeColaborador: item.colaboradorId ? nomes.get(item.colaboradorId) : undefined,
        }))
        .sort((a, b) => (b.item.datahoraMarcacao ?? "").localeCompare(a.item.datahoraMarcacao ?? ""));
    },
    enabled: habilitado,
  });
}

/**
 * `POST /v1/marcacoes/{marcacaoId}/meta/decisao` (`decidirRevisaoMarcacao`,
 * RFC-020) — aprovar ou rejeitar um item da fila de revisão. Invalida
 * `marcacoes-suspeitas` no sucesso, para o item sair da lista sem precisar
 * de refresh manual.
 */
export function useDecidirRevisaoMarcacao(): UseMutationResult<
  Esquema<"MarcacaoMeta">,
  unknown,
  { marcacaoId: string; corpo: Esquema<"DecisaoRevisaoRequisicao"> }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ marcacaoId, corpo }) => {
      const resultado = await api.POST("/v1/marcacoes/{marcacaoId}/meta/decisao", {
        params: {
          path: { marcacaoId },
          header: { "Idempotency-Key": crypto.randomUUID() },
        },
        body: corpo,
      });
      if (resultado.error) throw resultado.error;
      return resultado.data as Esquema<"MarcacaoMeta">;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["marcacoes-suspeitas"] });
    },
  });
}
