"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { api, type Esquema } from "@/lib/api";

/**
 * Dataviz dos dashboards de RH/gestor (T13, PCF F11 §2.6/§5 -- ownership de
 * A4). Nomeado deliberadamente `use-dataviz-dashboard.ts` (não
 * `use-indicadores-dashboard.ts`, que é ownership EXCLUSIVO de A1 da F9b,
 * nem `use-apuracoes.ts`/`use-ocorrencias.ts`, ownership de A2/A3 da F9b) --
 * mesmo padrão de nomeação por dono já documentado no topo daquele arquivo.
 *
 * **Fonte do dado: o motor de relatórios da F11 (`executarRelatorio`), nunca
 * uma segunda leitura ad-hoc de `/v1/apuracoes`/`/v1/ocorrencias`.** O PCF
 * exige explicitamente (T13 "pronto quando") que o gráfico renderize "dado
 * mockado da forma de `RelatorioExecucao`/resultado JSON real do motor (não
 * um formato inventado)" -- por isso este módulo NUNCA reaproveita as
 * consultas agregadas de `use-indicadores-dashboard.ts` (que são outra
 * FORMA de dado, pensada para KPI de cartão, não para série mensal).
 *
 * **Por que toda chamada passa por artefato (`urlDownload`), mesmo em
 * `formato=json`: achado de contrato, não escolha de implementação.** O
 * schema `RelatorioExecucao` (`packages/contracts/openapi.yaml`,
 * `GET /v1/relatorios/{codigo}/executar` e `GET /v1/relatorios/execucoes/
 * {execucaoId}`, ambos ancorados no MESMO schema) não tem nenhum campo de
 * linhas/dados inline -- só metadados de execução (`status`, `progresso`,
 * `conteudoRef`, `urlDownload`, `totalLinhas`, `hashSha256`...). Isto é
 * verdade para QUALQUER `formato`, inclusive `json`: não existe, no
 * contrato, uma resposta alternativa com um array de linhas embutido. A
 * única leitura consistente com o schema (fixo, congelado, independente de
 * quem/quando implementa o motor) é que mesmo `formato=json` materializa um
 * artefato (curto, mas artefato) e o cliente busca o conteúdo pela
 * `urlDownload` devolvida -- exatamente como PDF/XLSX/CSV. Este gancho seria
 * reescrito numa linha só se uma fase futura provar o contrário.
 *
 * **Achado/suposição documentada, não escondida: as CHAVES de coluna
 * abaixo (`mes`, `totalMinutos`, `saldoMinutos`, `total`) são uma inferência
 * de A4 sobre o que os datasets de A2 (`horas-extras`, `banco-de-horas`,
 * `ocorrencias`, PCF §2.2) vão devolver quando agrupados por `mes` --
 * `app/relatorios/datasets/operacionais.py` (T7/T8) ainda não existia no
 * momento em que este gancho foi escrito, então as chaves não puderam ser
 * confirmadas contra a implementação real. Ancoragem da inferência: os
 * MESMOS nomes de campo já fixados pelo contrato para os schemas de origem
 * (`ApuracaoDia.extrasMinutos`, `SaldoBancoHoras.saldoMinutos`) e a
 * convenção `mes`/`AAAA-MM` já usada para agrupamento mensal noutros lugares
 * deste PCF. Se o dataset real devolver outra chave, o ajuste é
 * `CHAVE_VALOR_*` abaixo, não uma reescrita deste módulo -- centralizado de
 * propósito para isso.
 */

/** Nome da chave de categoria (eixo X) que todo dataset agrupado por `mes` devolve -- convenção assumida (ver docstring do módulo). */
const CHAVE_MES = "mes";

/** Intervalo de poll de uma execução assíncrona ainda em andamento. */
const INTERVALO_POLL_MS = 1_500;
/** Teto de tentativas de poll -- ~45s, dentro do orçamento de 60s que o próprio PCF F11 usa como meta de performance (§2.3/§7 critério 2). */
const MAXIMO_TENTATIVAS_POLL = 30;

export interface PontoDeTendenciaMensal {
  mes: string;
  valor: number;
  // Índice extra: `GraficoDeLinha`/`GraficoDeBarras` (F9a, `graficos.tsx`)
  // aceitam `ReadonlyArray<Record<string, unknown>>` — a assinatura de
  // índice deixa este tipo compatível sem precisar de um `as` no ponto de
  // uso em cada seção do dashboard.
  [chave: string]: string | number;
}

/**
 * `exactOptionalPropertyTypes` (tsconfig, strict): cópia local do mesmo
 * utilitário que `use-marcacoes-em-aberto.ts`/`use-indicadores-dashboard.ts`
 * já têm -- cada arquivo de dashboard mantém sua própria cópia por regra de
 * fronteira de ownership (nenhum dos dois é editável por A4).
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

/** Primeiro dia de `quantidadeDeMeses` meses atrás e hoje, em `AAAA-MM-DD` (fuso do navegador -- mesma simplificação de `use-indicadores-dashboard.ts::periodoDoMesCorrente`). */
function janelaDosUltimosMeses(quantidadeDeMeses: number): { de: string; ate: string } {
  const agora = new Date();
  const paraIso = (data: Date) =>
    `${data.getFullYear()}-${String(data.getMonth() + 1).padStart(2, "0")}-${String(data.getDate()).padStart(2, "0")}`;
  const inicio = new Date(agora.getFullYear(), agora.getMonth() - (quantidadeDeMeses - 1), 1);
  return { de: paraIso(inicio), ate: paraIso(agora) };
}

function delay(ms: number): Promise<void> {
  return new Promise((resolver) => setTimeout(resolver, ms));
}

/**
 * Executa `codigo` do catálogo com `formato=json` e `agrupamento=mes`,
 * aguarda a conclusão (fazendo *poll* de `obterExecucaoRelatorio` quando o
 * caminho é assíncrono, PCF §2.3 item 3) e busca o artefato pela
 * `urlDownload` -- devolve o array de linhas cru, sem interpretar chave
 * nenhuma (quem chama decide qual campo é o valor).
 */
async function executarRelatorioMensal(
  codigo: string,
  parametros: {
    de: string;
    ate: string;
    colunas: string;
    colaboradorId?: string | undefined;
    empresaId?: string | undefined;
    unidadeId?: string | undefined;
  },
): Promise<Record<string, unknown>[]> {
  const resultadoInicial = await api.GET("/v1/relatorios/{codigo}/executar", {
    params: {
      path: { codigo },
      query: paramsSemUndefined({
        formato: "json" as const,
        agrupamento: CHAVE_MES,
        de: parametros.de,
        ate: parametros.ate,
        colunas: parametros.colunas,
        colaboradorId: parametros.colaboradorId,
        empresaId: parametros.empresaId,
        unidadeId: parametros.unidadeId,
      }),
    },
  });
  if (resultadoInicial.error) throw resultadoInicial.error;

  let execucao = resultadoInicial.data;
  let tentativas = 0;
  while (
    execucao &&
    (execucao.status === "enfileirado" || execucao.status === "processando") &&
    tentativas < MAXIMO_TENTATIVAS_POLL
  ) {
    await delay(INTERVALO_POLL_MS);
    const execucaoId = execucao.id;
    if (!execucaoId) break;
    const resultadoPoll = await api.GET("/v1/relatorios/execucoes/{execucaoId}", {
      params: { path: { execucaoId } },
    });
    if (resultadoPoll.error) throw resultadoPoll.error;
    execucao = resultadoPoll.data;
    tentativas += 1;
  }

  if (!execucao || execucao.status === "falhou" || execucao.status === "cancelado") {
    throw new Error(execucao?.erro ?? `Execucao do relatorio ${codigo} nao foi concluida.`);
  }
  if (execucao.status !== "concluido" || !execucao.urlDownload) {
    // Ainda enfileirado/processando após o teto de tentativas, ou concluído
    // sem artefato (relatório sem linhas) -- devolve vazio, não erro: a
    // seção do dashboard trata "sem dado" como estado normal (mesmo padrão
    // de `secao-apuracao.tsx` para o período sem apuração).
    return [];
  }

  const resposta = await fetch(execucao.urlDownload);
  if (!resposta.ok) {
    throw new Error(`Falha ao baixar o artefato do relatorio ${codigo}: HTTP ${resposta.status}`);
  }
  const corpo: unknown = await resposta.json();
  return Array.isArray(corpo) ? (corpo as Record<string, unknown>[]) : [];
}

/**
 * Série mensal genérica: um dataset do catálogo, agrupado por `mes`,
 * projetado numa única coluna de valor numérico. Usada pelas três seções
 * que ganham gráfico nesta fase (T13) -- centraliza a lógica de
 * execução/poll/download num único lugar, então uma chave de coluna errada
 * (ver docstring do módulo) se corrige aqui, não em três componentes.
 */
export function useTendenciaMensal(parametros: {
  codigo: string;
  chaveValor: string;
  meses?: number;
  colaboradorId?: string | undefined;
  empresaId?: string | undefined;
  unidadeId?: string | undefined;
  habilitado?: boolean;
}): UseQueryResult<PontoDeTendenciaMensal[]> {
  const {
    codigo,
    chaveValor,
    meses = 6,
    colaboradorId,
    empresaId,
    unidadeId,
    habilitado = true,
  } = parametros;
  const { de, ate } = janelaDosUltimosMeses(meses);

  return useQuery({
    queryKey: [
      "dataviz-tendencia-mensal",
      codigo,
      chaveValor,
      de,
      ate,
      colaboradorId,
      empresaId,
      unidadeId,
    ],
    queryFn: async () => {
      const linhas = await executarRelatorioMensal(codigo, {
        de,
        ate,
        colunas: `${CHAVE_MES},${chaveValor}`,
        colaboradorId,
        empresaId,
        unidadeId,
      });
      return linhas
        .map((linha): PontoDeTendenciaMensal | undefined => {
          const mes = linha[CHAVE_MES];
          const valor = linha[chaveValor];
          if (typeof mes !== "string") return undefined;
          const valorNumerico = typeof valor === "number" ? valor : Number(valor ?? 0);
          return { mes, valor: Number.isFinite(valorNumerico) ? valorNumerico : 0 };
        })
        .filter((ponto): ponto is PontoDeTendenciaMensal => ponto !== undefined)
        .sort((a, b) => a.mes.localeCompare(b.mes));
    },
    enabled: habilitado,
    staleTime: 60_000,
  });
}

/**
 * Chaves de coluna que o motor de relatórios (`app/relatorios/motor.py::
 * _montar_consulta_agrupada`) realmente devolve quando `agrupamento=mes` --
 * corrigido em 09/08/2026 (achado real: os 3 widgets sempre respondiam 400
 * porque nem os nomes de coluna abaixo, nem o próprio agrupamento "mes",
 * existiam em `relatorio_definicoes` antes do catálogo de fábrica ser
 * semeado; ao testar com dado real, os nomes assumidos aqui também
 * estavam errados). `minutos`/`saldoAposMinutos` são colunas reais de
 * `COLUNAS_HORAS_EXTRAS`/`COLUNAS_BANCO_DE_HORAS`
 * (`app/relatorios/datasets/operacionais.py`); `quantidadeRegistros` é a
 * contagem que o motor sempre sintetiza ao agrupar
 * (`app.relatorios.catalogo.COLUNA_QUANTIDADE`), nunca "total".
 */
export const CHAVE_VALOR_HORAS_EXTRAS = "minutos";
export const CHAVE_VALOR_SALDO_BANCO_HORAS = "saldoAposMinutos";
export const CHAVE_VALOR_OCORRENCIAS = "quantidadeRegistros";

export type { Esquema };
