"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { paramsSemUndefined } from "@/componentes/paineis/apuracao/utilitarios";
import { api, type Esquema } from "@/lib/api";

export interface ParametrosDeApuracoes {
  /** Primeiro dia do intervalo (`AAAA-MM-DD`). Obrigatório no contrato. */
  de: string;
  /** Último dia do intervalo (`AAAA-MM-DD`). Obrigatório no contrato. */
  ate: string;
  empresaId?: string | undefined;
  unidadeId?: string | undefined;
  departamentoId?: string | undefined;
  equipeId?: string | undefined;
  colaboradorId?: string | undefined;
  vinculoId?: string | undefined;
  status?: Esquema<"ApuracaoDia">["status"] | undefined;
  somenteInconsistentes?: boolean | undefined;
  incluirComponentes?: boolean | undefined;
  incluirMarcacoes?: boolean | undefined;
}

const LIMITE_PAGINA = 200;

/**
 * `GET /v1/apuracoes` (`listarApuracoes`) — a grade mês × colaborador (T9).
 *
 * `de`/`ate` são obrigatórios no contrato; o gancho não dispara sem os dois.
 * A resposta é paginada por cursor (200 itens/página, o máximo do contrato) —
 * uma grade de 500 vínculos × 31 dias chega a ~15.500 linhas, então este
 * gancho pagina internamente até `paginacao.temMais` ser falso e devolve o
 * array completo já achatado. `incluirComponentes`/`incluirMarcacoes` ficam
 * `false` por padrão (a descrição do parâmetro no contrato avisa que
 * "aumenta bastante o volume da resposta") — a T10 os liga sob demanda ao
 * abrir o detalhe de uma célula, via `useApuracoesDoDia`.
 */
export function useApuracoes(
  parametros: ParametrosDeApuracoes,
): UseQueryResult<Esquema<"ApuracaoDia">[]> {
  return useQuery({
    queryKey: [
      "apuracoes",
      parametros.de,
      parametros.ate,
      parametros.empresaId,
      parametros.unidadeId,
      parametros.departamentoId,
      parametros.equipeId,
      parametros.colaboradorId,
      parametros.vinculoId,
      parametros.status,
      parametros.somenteInconsistentes,
      parametros.incluirComponentes,
      parametros.incluirMarcacoes,
    ],
    queryFn: async () => {
      const dados: Esquema<"ApuracaoDia">[] = [];
      let cursor: string | undefined;
      do {
        const resultado = await api.GET("/v1/apuracoes", {
          params: {
            query: paramsSemUndefined({
              de: parametros.de,
              ate: parametros.ate,
              empresaId: parametros.empresaId,
              unidadeId: parametros.unidadeId,
              departamentoId: parametros.departamentoId,
              equipeId: parametros.equipeId,
              colaboradorId: parametros.colaboradorId,
              vinculoId: parametros.vinculoId,
              status: parametros.status,
              somenteInconsistentes: parametros.somenteInconsistentes,
              incluirComponentes: parametros.incluirComponentes,
              incluirMarcacoes: parametros.incluirMarcacoes,
              cursor,
              limite: LIMITE_PAGINA,
              ordenar: "colaboradorId:asc,data:asc",
            }),
          },
        });
        if (resultado.error) throw resultado.error;
        dados.push(...(resultado.data?.dados ?? []));
        cursor = resultado.data?.paginacao?.proximoCursor;
      } while (cursor);
      return dados;
    },
    enabled: Boolean(parametros.de && parametros.ate),
  });
}

/**
 * Apuração de um vínculo num único dia — usado pelo dialogo de tratamento
 * (T10) para abrir o detalhe de uma célula com a decomposição completa
 * (`incluirComponentes`/`incluirMarcacoes=true`, aceitável aqui: é UM dia,
 * não a grade inteira).
 */
export function useApuracaoDoVinculoNoDia(
  vinculoId: string | undefined,
  data: string | undefined,
): UseQueryResult<Esquema<"ApuracaoDia"> | undefined> {
  return useQuery({
    queryKey: ["apuracao-do-vinculo-no-dia", vinculoId, data],
    queryFn: async () => {
      if (!vinculoId || !data) throw new Error("vinculoId/data ausentes");
      const resultado = await api.GET("/v1/apuracoes", {
        params: {
          query: paramsSemUndefined({
            vinculoId,
            de: data,
            ate: data,
            incluirComponentes: true,
            incluirMarcacoes: true,
            limite: 1,
          }),
        },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data?.dados?.[0];
    },
    enabled: Boolean(vinculoId && data),
  });
}
