"use client";

import { useQueries, useQuery, type UseQueryResult } from "@tanstack/react-query";

import { api, type Esquema } from "@/lib/api";

import { useSessaoCompleta } from "./use-sessao-completa";

/**
 * Ganchos de dados do dashboard de RH/gestor/diretoria (T2, PCF F9b §6).
 *
 * Nomeados deliberadamente `use-indicadores-dashboard.ts` (em vez de
 * `use-empresas.ts`/`use-unidades.ts`/`use-apuracoes.ts`/`use-ocorrencias.ts`/
 * `use-colaboradores.ts`): esses nomes de arquivo são ownership EXCLUSIVO de
 * A2/A3 (PCF F9b §5 — `use-empresas.ts`/`use-unidades.ts`/`use-colaboradores.ts`
 * são de A2; `use-apuracoes.ts`/`use-ocorrencias.ts` são de A3), mesmo esta
 * tela (T2, ownership de A1) precisando ler os mesmos quatro recursos para
 * montar KPIs agregados. Este arquivo chama os mesmos endpoints (`GET
 * /v1/empresas`, `/v1/unidades`, `/v1/apuracoes`, `/v1/ocorrencias`, `/v1/
 * colaboradores`) sem duplicar a FORMA de nenhum gancho de A2/A3 — não expõe
 * CRUD nem cache reaproveitável por eles, só as agregações que o dashboard
 * precisa.
 */

/**
 * `exactOptionalPropertyTypes` (tsconfig, strict) trata `{ chave: undefined }`
 * como diferente de "chave ausente" — remove as chaves `undefined` de
 * verdade, para satisfazer tanto o contrato de tipos gerado quanto o
 * serializador de query do `openapi-fetch`. Mesma assinatura que
 * `@/lib/formatacao-f8/parametros-de-consulta` (F8) já usa — cópia local
 * porque aquele diretório é ownership exclusivo de F8 (PCF F9b §5).
 */
function paramsSemUndefined<T extends Record<string, unknown>>(
  objeto: T,
): { [K in keyof T]?: Exclude<T[K], undefined> } {
  const resultado: Record<string, unknown> = {};
  for (const [chave, valor] of Object.entries(objeto)) {
    if (valor !== undefined) resultado[chave] = valor;
  }
  return resultado as { [K in keyof T]?: Exclude<T[K], undefined> };
}

/** Primeiro dia do mês corrente e hoje, em `AAAA-MM-DD` (fuso do navegador — mesma simplificação de `use-marcacoes-em-aberto.ts`). */
export function periodoDoMesCorrente(): { de: string; ate: string } {
  const agora = new Date();
  const paraIso = (data: Date) =>
    `${data.getFullYear()}-${String(data.getMonth() + 1).padStart(2, "0")}-${String(data.getDate()).padStart(2, "0")}`;
  return {
    de: paraIso(new Date(agora.getFullYear(), agora.getMonth(), 1)),
    ate: paraIso(agora),
  };
}

export interface FiltroDeEscopo {
  // `| undefined` explícito de propósito: sob `exactOptionalPropertyTypes`,
  // isso permite que o chamador (estado de seleção do dashboard, sempre com
  // as duas chaves presentes) passe `{ empresaId: undefined, ... }` sem
  // conflito de tipos — a chave AUSENTE e a chave PRESENTE-com-undefined
  // significam a mesma coisa aqui ("sem filtro").
  empresaId?: string | undefined;
  unidadeId?: string | undefined;
}

/** `GET /v1/empresas` — para o seletor de empresa do dashboard (RH multiempresa, §2 do PCF: nunca via `SessaoAtual.empresasVisiveis`, sempre `null` hoje). */
export function useEmpresasDoTenant(): UseQueryResult<Esquema<"ListaEmpresa">> {
  return useQuery({
    queryKey: ["dashboard-empresas"],
    queryFn: async () => {
      const resultado = await api.GET("/v1/empresas", { params: { query: { limite: 100 } } });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    staleTime: 60_000,
  });
}

/** `GET /v1/unidades`, opcionalmente restrito a uma empresa. */
export function useUnidadesDoTenant(empresaId?: string): UseQueryResult<Esquema<"ListaUnidade">> {
  return useQuery({
    queryKey: ["dashboard-unidades", empresaId],
    queryFn: async () => {
      const resultado = await api.GET("/v1/unidades", {
        params: { query: paramsSemUndefined({ empresaId, limite: 100 }) },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    staleTime: 60_000,
  });
}

export interface ResumoDeApuracao {
  diasApurados: number;
  extrasMinutos: number;
  faltaMinutos: number;
  atrasoMinutos: number;
  diasComOcorrencia: number;
  /** Uma linha por dia do período, para o gráfico de barras (extras/faltas/atrasos agregados naquele dia, somando todos os vínculos retornados). */
  serieDiaria: {
    data: string;
    extrasMinutos: number;
    faltaMinutos: number;
    atrasoMinutos: number;
  }[];
}

const TETO_DE_PAGINAS_APURACAO = 10; // 10 × 200 = até 2.000 linhas de apuração agregadas no dashboard

/**
 * `GET /v1/apuracoes` agregado (extras/faltas/atrasos, dias com ocorrência) no
 * período informado. Teto de páginas documentado: o dashboard soma um
 * recorte, não a folha inteira do tenant — quem precisa da grade completa é a
 * T9 (A3), virtualizada.
 */
export function useResumoDeApuracao(
  escopo: FiltroDeEscopo,
  periodo: { de: string; ate: string },
): UseQueryResult<ResumoDeApuracao> {
  return useQuery({
    queryKey: [
      "dashboard-resumo-apuracao",
      escopo.empresaId,
      escopo.unidadeId,
      periodo.de,
      periodo.ate,
    ],
    queryFn: async () => {
      const porDia = new Map<
        string,
        { extrasMinutos: number; faltaMinutos: number; atrasoMinutos: number }
      >();
      let diasApurados = 0;
      let extrasMinutos = 0;
      let faltaMinutos = 0;
      let atrasoMinutos = 0;
      let diasComOcorrencia = 0;
      let cursor: string | undefined;
      let paginas = 0;
      do {
        const resultado = await api.GET("/v1/apuracoes", {
          params: {
            // `de`/`ate` são obrigatórios no contrato (`ListaApuracaoDia`) —
            // ficam FORA de `paramsSemUndefined` (que só teria efeito sobre
            // campos opcionais) para não virarem opcionais no tipo também.
            query: {
              ...paramsSemUndefined({
                empresaId: escopo.empresaId,
                unidadeId: escopo.unidadeId,
                cursor,
              }),
              de: periodo.de,
              ate: periodo.ate,
              incluirComponentes: false,
              limite: 200,
            },
          },
        });
        if (resultado.error) throw resultado.error;
        for (const dia of resultado.data?.dados ?? []) {
          diasApurados += 1;
          extrasMinutos += dia.extrasMinutos ?? 0;
          faltaMinutos += dia.faltaMinutos ?? 0;
          atrasoMinutos += dia.atrasoMinutos ?? 0;
          if (dia.status === "com_ocorrencia") diasComOcorrencia += 1;
          if (dia.data) {
            const acumulado = porDia.get(dia.data) ?? {
              extrasMinutos: 0,
              faltaMinutos: 0,
              atrasoMinutos: 0,
            };
            acumulado.extrasMinutos += dia.extrasMinutos ?? 0;
            acumulado.faltaMinutos += dia.faltaMinutos ?? 0;
            acumulado.atrasoMinutos += dia.atrasoMinutos ?? 0;
            porDia.set(dia.data, acumulado);
          }
        }
        cursor = resultado.data?.paginacao?.proximoCursor;
        paginas += 1;
      } while (cursor && paginas < TETO_DE_PAGINAS_APURACAO);

      const serieDiaria = [...porDia.entries()]
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([data, valores]) => ({ data, ...valores }));

      return {
        diasApurados,
        extrasMinutos,
        faltaMinutos,
        atrasoMinutos,
        diasComOcorrencia,
        serieDiaria,
      };
    },
    staleTime: 60_000,
  });
}

const SEVERIDADES = ["info", "atencao", "alta", "critica"] as const;
export type SeveridadeDeOcorrencia = (typeof SEVERIDADES)[number];

/**
 * Contagem de ocorrências ABERTAS por severidade. Uma chamada por severidade
 * com `limite: 1`, lendo `paginacao.total` — mesmo padrão que
 * `useContagemColaboradoresPorStatus` usa abaixo, porque o contrato não tem
 * um endpoint de agregação por severidade (`GET /v1/ocorrencias` só lista).
 */
export function useFilaDeOcorrenciasPorSeveridade(
  escopo: FiltroDeEscopo,
): { severidade: SeveridadeDeOcorrencia; total: number; carregando: boolean }[] {
  const resultados = useQueries({
    queries: SEVERIDADES.map((severidade) => ({
      queryKey: [
        "dashboard-ocorrencias-severidade",
        escopo.empresaId,
        escopo.unidadeId,
        severidade,
      ],
      queryFn: async () => {
        const resultado = await api.GET("/v1/ocorrencias", {
          params: {
            query: paramsSemUndefined({
              empresaId: escopo.empresaId,
              unidadeId: escopo.unidadeId,
              status: "aberta" as const,
              severidade,
              limite: 1,
            }),
          },
        });
        if (resultado.error) throw resultado.error;
        return resultado.data?.paginacao?.total ?? resultado.data?.dados?.length ?? 0;
      },
      staleTime: 60_000,
    })),
  });

  return SEVERIDADES.map((severidade, indice) => ({
    severidade,
    total: resultados[indice]?.data ?? 0,
    carregando: resultados[indice]?.isPending ?? true,
  }));
}

const STATUS_DE_COLABORADOR = [
  "ativo",
  "afastado",
  "ferias",
  "suspenso",
  "pre_admissao",
  "desligado",
] as const;
export type StatusDeColaborador = (typeof STATUS_DE_COLABORADOR)[number];

/**
 * Contagem de colaboradores por `status`. `GET /v1/colaboradores` não agrega
 * — uma chamada por status com `limite: 1`, lendo `paginacao.total` (o mesmo
 * truque documentado acima para ocorrências).
 */
export function useContagemColaboradoresPorStatus(
  escopo: FiltroDeEscopo,
): { status: StatusDeColaborador; total: number; carregando: boolean }[] {
  const resultados = useQueries({
    queries: STATUS_DE_COLABORADOR.map((status) => ({
      queryKey: ["dashboard-colaboradores-status", escopo.empresaId, escopo.unidadeId, status],
      queryFn: async () => {
        const resultado = await api.GET("/v1/colaboradores", {
          params: {
            query: paramsSemUndefined({
              empresaId: escopo.empresaId,
              unidadeId: escopo.unidadeId,
              status,
              limite: 1,
            }),
          },
        });
        if (resultado.error) throw resultado.error;
        return resultado.data?.paginacao?.total ?? resultado.data?.dados?.length ?? 0;
      },
      staleTime: 60_000,
    })),
  });

  return STATUS_DE_COLABORADOR.map((status, indice) => ({
    status,
    total: resultados[indice]?.data ?? 0,
    carregando: resultados[indice]?.isPending ?? true,
  }));
}

/**
 * Saldo de banco de horas como AMOSTRA — só o do próprio usuário logado,
 * quando `SessaoAtual.colaboradorId` existir (§2/T2 do PCF: `obterSaldoBancoHoras`
 * exige `colaboradorId` no caminho, não existe endpoint agregado por
 * empresa/unidade). RH/gestor sem `colaboradorId` (o caso comum) não tem
 * amostra própria — a seção simplesmente não aparece, honesto em vez de
 * inventar uma agregação que o contrato não oferece.
 */
export function useSaldoBancoHorasAmostra(): UseQueryResult<Esquema<"SaldoBancoHoras">> {
  const { sessao } = useSessaoCompleta();
  const colaboradorId = sessao?.colaboradorId;

  return useQuery({
    queryKey: ["dashboard-saldo-banco-horas-amostra", colaboradorId],
    queryFn: async () => {
      if (!colaboradorId) throw new Error("colaboradorId ausente");
      const resultado = await api.GET("/v1/banco-horas/{colaboradorId}/saldo", {
        params: { path: { colaboradorId } },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    // Sem `colaboradorId` (caso comum de RH/gestor), a consulta nunca dispara
    // — o chamador decide não renderizar a seção checando `sessao.colaboradorId`
    // antes, não checando este resultado.
    enabled: Boolean(colaboradorId),
  });
}
