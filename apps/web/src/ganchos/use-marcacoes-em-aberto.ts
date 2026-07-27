"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { api, type Esquema } from "@/lib/api";

/**
 * "Quem está com marcação em aberto hoje" (T3, PCF F9b §2/§6).
 *
 * Decisão de infraestrutura FIXADA pelo PCF: não existe WebSocket/SSE em
 * nenhuma camada do backend — "tempo real" aqui é *polling* via TanStack
 * Query (`refetchInterval`) contra `GET /v1/marcacoes` (leitura), nunca contra
 * `GET /v1/apuracoes` (o dia corrente tipicamente ainda não tem apuração
 * calculada).
 *
 * Regra de domínio INEGOCIÁVEL (mesma do docstring de `LinhaDoTempoDeMarcacoes`,
 * F9a): o REP-P não registra "entrada"/"saída" com certeza — o pareamento
 * definitivo só acontece na apuração (F4). Este gancho NUNCA afirma que um
 * colaborador "está trabalhando": ele só conta a PARIDADE das marcações do
 * dia por vínculo (número ímpar = ficou "em aberto", nem par nem ímpar é
 * "verdade oficial") e expõe o horário da última marcação. Rótulo de
 * apresentação — não é um campo novo de contrato, é inferência de UX
 * derivada só na tela (§2 do PCF).
 *
 * Simplificação documentada: o "início do dia" usa o fuso horário do
 * NAVEGADOR de quem está olhando o dashboard, não o fuso de cada unidade
 * (que pode divergir entre unidades diferentes na mesma consulta) — mesma
 * simplificação que `apps/web/src/app/eu/page.tsx` (F8, `limitesDoDiaDeHoje`)
 * já usa para "hoje". Resolver por-unidade exigiria uma chamada por unidade
 * visível só para descobrir o fuso; fora de escopo para um widget de
 * dashboard.
 */

export interface ParametrosDeMarcacoesEmAberto {
  // `| undefined` explícito: sob `exactOptionalPropertyTypes`, permite
  // repassar o estado de escopo do dashboard (que sempre tem as duas chaves
  // presentes, possivelmente `undefined`) sem ficção de tipos no chamador.
  empresaId?: string | undefined;
  unidadeId?: string | undefined;
  /** Intervalo entre buscas, em ms. Padrão 45s — dentro da janela de 30–60s pedida pela T3. */
  intervaloDeAtualizacaoMs?: number;
  /** Injetável em teste para paridade determinística (`vi.useFakeTimers`). */
  habilitado?: boolean;
}

export interface VinculoComMarcacaoEmAberto {
  vinculoId: string;
  colaboradorId: string | undefined;
  /** Preenchido só quando o lookup de colaboradores (mesmo filtro de empresa/unidade) resolve o nome. */
  nomeColaborador: string | undefined;
  quantidadeMarcacoes: number;
  ultimaMarcacaoEm: string;
  ultimoCanal: Esquema<"Marcacao">["canal"];
}

const LIMITE_DE_PAGINAS_DE_SEGURANCA = 20; // 20 × 100 = até 2000 marcações do dia, teto de segurança
const TAMANHO_DE_PAGINA = 100;
const INTERVALO_PADRAO_MS = 45_000;

/**
 * `exactOptionalPropertyTypes` (tsconfig, strict) trata `{ chave: undefined }`
 * como diferente de "chave ausente" — remove as chaves `undefined` de
 * verdade, em vez de mandá-las com valor `undefined`, para satisfazer tanto
 * o contrato de tipos gerado quanto o serializador de query do `openapi-fetch`.
 * Mesmo utilitário, mesma assinatura que `@/lib/formatacao-f8/parametros-de-consulta`
 * (F8) já usa — não importado de lá porque aquele diretório é ownership
 * exclusivo de F8 (PCF F9b §5), então este módulo tem sua própria cópia local.
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

/** Início do dia civil corrente (fuso do navegador) e "agora", em ISO 8601. */
function limitesDoDiaDeHoje(): { de: string; ate: string } {
  const agora = new Date();
  const inicio = new Date(agora.getFullYear(), agora.getMonth(), agora.getDate(), 0, 0, 0, 0);
  return { de: inicio.toISOString(), ate: agora.toISOString() };
}

async function buscarTodasAsMarcacoesDoDia(filtros: {
  empresaId?: string | undefined;
  unidadeId?: string | undefined;
  de: string;
  ate: string;
}): Promise<Esquema<"Marcacao">[]> {
  const marcacoes: Esquema<"Marcacao">[] = [];
  let cursor: string | undefined;
  let paginas = 0;
  do {
    const resultado = await api.GET("/v1/marcacoes", {
      params: {
        query: paramsSemUndefined({
          empresaId: filtros.empresaId,
          unidadeId: filtros.unidadeId,
          de: filtros.de,
          ate: filtros.ate,
          ordenar: "datahoraMarcacao:asc",
          limite: TAMANHO_DE_PAGINA,
          cursor,
        }),
      },
    });
    if (resultado.error) throw resultado.error;
    marcacoes.push(...(resultado.data?.dados ?? []));
    cursor = resultado.data?.paginacao?.proximoCursor;
    paginas += 1;
  } while (cursor && paginas < LIMITE_DE_PAGINAS_DE_SEGURANCA);
  return marcacoes;
}

/** Nome por `colaboradorId`, para decorar a lista com algo legível além do UUID. Best-effort: página única, nomes ausentes caem no fallback do componente. */
async function buscarMapaDeNomes(filtros: {
  empresaId?: string | undefined;
  unidadeId?: string | undefined;
}): Promise<Map<string, string>> {
  const resultado = await api.GET("/v1/colaboradores", {
    params: {
      query: paramsSemUndefined({
        empresaId: filtros.empresaId,
        unidadeId: filtros.unidadeId,
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

function agruparPorVinculo(
  marcacoes: Esquema<"Marcacao">[],
  nomesPorColaborador: Map<string, string>,
): VinculoComMarcacaoEmAberto[] {
  const porVinculo = new Map<string, Esquema<"Marcacao">[]>();
  for (const marcacao of marcacoes) {
    const chave = marcacao.vinculoId ?? marcacao.colaboradorId ?? marcacao.id;
    if (!chave) continue;
    const lista = porVinculo.get(chave) ?? [];
    lista.push(marcacao);
    porVinculo.set(chave, lista);
  }

  const resultado: VinculoComMarcacaoEmAberto[] = [];
  for (const [vinculoId, lista] of porVinculo) {
    // Paridade ímpar = provável "em aberto" (§2 do PCF): não corrige, não
    // pareia — só sinaliza. `lista` já vem ordenada por `datahoraMarcacao:asc`
    // da API; a última é a mais recente.
    if (lista.length % 2 !== 1) continue;
    const ultima = lista[lista.length - 1];
    if (!ultima?.datahoraMarcacao) continue;
    const colaboradorId = ultima.colaboradorId;
    resultado.push({
      vinculoId,
      colaboradorId,
      nomeColaborador: colaboradorId ? nomesPorColaborador.get(colaboradorId) : undefined,
      quantidadeMarcacoes: lista.length,
      ultimaMarcacaoEm: ultima.datahoraMarcacao,
      ultimoCanal: ultima.canal,
    });
  }
  return resultado.sort((a, b) => b.ultimaMarcacaoEm.localeCompare(a.ultimaMarcacaoEm));
}

export function useMarcacoesEmAberto(
  parametros: ParametrosDeMarcacoesEmAberto = {},
): UseQueryResult<VinculoComMarcacaoEmAberto[]> {
  const {
    empresaId,
    unidadeId,
    intervaloDeAtualizacaoMs = INTERVALO_PADRAO_MS,
    habilitado = true,
  } = parametros;

  return useQuery({
    queryKey: ["marcacoes-em-aberto", empresaId, unidadeId],
    queryFn: async () => {
      const { de, ate } = limitesDoDiaDeHoje();
      const [marcacoes, nomes] = await Promise.all([
        buscarTodasAsMarcacoesDoDia({ empresaId, unidadeId, de, ate }),
        buscarMapaDeNomes({ empresaId, unidadeId }).catch(() => new Map<string, string>()),
      ]);
      return agruparPorVinculo(marcacoes, nomes);
    },
    enabled: habilitado,
    refetchInterval: intervaloDeAtualizacaoMs,
    // A janela do dia muda a cada refetch (a marcação de "agora" avança) —
    // sem isto o TanStack Query poderia servir uma resposta obsoleta do cache
    // achando que nada mudou.
    staleTime: 0,
  });
}
