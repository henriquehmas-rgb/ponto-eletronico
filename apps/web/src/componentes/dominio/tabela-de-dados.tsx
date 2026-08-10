"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { useEstadoControlavel } from "@/ganchos/use-estado-controlavel";
import { cn } from "@/lib/utils";

export interface ColunaDeTabela<T> {
  id: string;
  cabecalho: string;
  renderizarCelula: (linha: T) => ReactNode;
  /** Usado para ordenar quando `ordenavel` é verdadeiro. Ausente = coluna não ordenável. */
  valorDeOrdenacao?: (linha: T) => string | number;
  ordenavel?: boolean;
  larguraPx?: number;
}

export interface OrdenacaoDeTabela {
  colunaId: string;
  direcao: "asc" | "desc";
}

export interface TabelaDeDadosProps<T> {
  linhas: T[];
  colunas: ColunaDeTabela<T>[];
  obterId: (linha: T) => string;
  /** Altura do viewport rolável, em px. É o que faz a virtualização ter efeito. */
  alturaContainerPx?: number;
  /** Altura de cada linha, em px. Espelha `--dimensao-altura-linha-grade` (32px) do contrato — fixa de propósito, a virtualização depende de altura conhecida. */
  alturaLinhaPx?: number;
  carregando?: boolean;
  mensagemVazia?: string;
  selecionaveis?: boolean;
  /** IDs selecionados (controlado). Sem isto, a tabela guarda a seleção internamente. */
  selecionadosIds?: ReadonlySet<string>;
  aoMudarSelecionadosIds?: (selecionados: ReadonlySet<string>) => void;
  ordenacao?: OrdenacaoDeTabela | null;
  aoMudarOrdenacao?: (ordenacao: OrdenacaoDeTabela | null) => void;
  /** IDs das colunas visíveis, na ordem de exibição (controlado). Sem isto, todas as colunas de `colunas`, na ordem dada. */
  colunasVisiveisIds?: string[];
  aoMudarColunasVisiveisIds?: (ids: string[]) => void;
}

const ALTURA_LINHA_PADRAO = 32; // --dimensao-altura-linha-grade
const ALTURA_CONTAINER_PADRAO = 384;

function proximaDirecao(atual: OrdenacaoDeTabela | null, colunaId: string): OrdenacaoDeTabela | null {
  if (atual?.colunaId !== colunaId) return { colunaId, direcao: "asc" };
  if (atual.direcao === "asc") return { colunaId, direcao: "desc" };
  return null;
}

/**
 * Data-table com colunas configuráveis (mostrar/ocultar, reordenar, largura),
 * ordenação, seleção de linha e virtualização via `@tanstack/react-virtual`.
 * A preferência de colunas é estado do componente, mas aceita props
 * controladas para quem precisar persistir por fora (F11) — este componente
 * nunca persiste nada sozinho.
 */
export function TabelaDeDados<T>({
  linhas,
  colunas,
  obterId,
  alturaContainerPx = ALTURA_CONTAINER_PADRAO,
  alturaLinhaPx = ALTURA_LINHA_PADRAO,
  carregando = false,
  mensagemVazia = "Nenhum registro encontrado.",
  selecionaveis = false,
  selecionadosIds: selecionadosControlado,
  aoMudarSelecionadosIds,
  ordenacao: ordenacaoControlada,
  aoMudarOrdenacao,
  colunasVisiveisIds: colunasVisiveisControlado,
  aoMudarColunasVisiveisIds,
}: TabelaDeDadosProps<T>) {
  const idPainelColunas = useId();
  const parentRef = useRef<HTMLDivElement>(null);
  const refCelulas = useRef<Record<string, HTMLDivElement | null>>({});

  const [selecionadosIds, definirSelecionadosIds] = useEstadoControlavel<ReadonlySet<string>>(
    selecionadosControlado,
    new Set(),
    aoMudarSelecionadosIds,
  );
  const [ordenacao, definirOrdenacao] = useEstadoControlavel<OrdenacaoDeTabela | null>(
    ordenacaoControlada,
    null,
    aoMudarOrdenacao,
  );
  const [colunasVisiveisIds, definirColunasVisiveisIds] = useEstadoControlavel<string[]>(
    colunasVisiveisControlado,
    colunas.map((coluna) => coluna.id),
    aoMudarColunasVisiveisIds,
  );

  const [foco, setFoco] = useState<{ linha: number; coluna: number }>({ linha: 0, coluna: 0 });

  const colunasVisiveis = useMemo(
    () =>
      colunasVisiveisIds
        .map((id) => colunas.find((coluna) => coluna.id === id))
        .filter((coluna): coluna is ColunaDeTabela<T> => coluna !== undefined),
    [colunasVisiveisIds, colunas],
  );

  const linhasOrdenadas = useMemo(() => {
    if (!ordenacao) return linhas;
    const coluna = colunas.find((item) => item.id === ordenacao.colunaId);
    if (!coluna?.valorDeOrdenacao) return linhas;
    const { valorDeOrdenacao } = coluna;
    const copia = [...linhas];
    copia.sort((a, b) => {
      const valorA = valorDeOrdenacao(a);
      const valorB = valorDeOrdenacao(b);
      const comparacao = valorA < valorB ? -1 : valorA > valorB ? 1 : 0;
      return ordenacao.direcao === "asc" ? comparacao : -comparacao;
    });
    return copia;
  }, [linhas, ordenacao, colunas]);

  const virtualizador = useVirtualizer({
    count: linhasOrdenadas.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => alturaLinhaPx,
    overscan: 12,
  });

  const gridTemplateColumns = useMemo(() => {
    const larguraSelecao = selecionaveis ? "40px " : "";
    const larguraColunas = colunasVisiveis.map((coluna) => `${coluna.larguraPx ?? 160}px`).join(" ");
    return `${larguraSelecao}${larguraColunas}`;
  }, [colunasVisiveis, selecionaveis]);

  const totalColunasFocaveis = colunasVisiveis.length + (selecionaveis ? 1 : 0);

  function alternarColunaVisivel(id: string) {
    const jaVisivel = colunasVisiveisIds.includes(id);
    if (jaVisivel) {
      if (colunasVisiveisIds.length === 1) return; // nunca esconde a ultima coluna
      definirColunasVisiveisIds(colunasVisiveisIds.filter((atual) => atual !== id));
    } else {
      // Reinsere na posicao original entre as colunas cadastradas.
      const ordemOriginal = colunas.map((coluna) => coluna.id);
      const novaLista = [...colunasVisiveisIds, id].sort(
        (a, b) => ordemOriginal.indexOf(a) - ordemOriginal.indexOf(b),
      );
      definirColunasVisiveisIds(novaLista);
    }
  }

  function moverColuna(id: string, direcao: -1 | 1) {
    const indice = colunasVisiveisIds.indexOf(id);
    const novoIndice = indice + direcao;
    if (indice === -1 || novoIndice < 0 || novoIndice >= colunasVisiveisIds.length) return;
    const nova = [...colunasVisiveisIds];
    const [removida] = nova.splice(indice, 1);
    if (removida === undefined) return;
    nova.splice(novoIndice, 0, removida);
    definirColunasVisiveisIds(nova);
  }

  function alternarSelecaoTudo() {
    if (selecionadosIds.size === linhasOrdenadas.length) {
      definirSelecionadosIds(new Set());
    } else {
      definirSelecionadosIds(new Set(linhasOrdenadas.map(obterId)));
    }
  }

  function alternarSelecaoLinha(id: string) {
    const novo = new Set(selecionadosIds);
    if (novo.has(id)) novo.delete(id);
    else novo.add(id);
    definirSelecionadosIds(novo);
  }

  function focarCelula(linha: number, coluna: number) {
    const linhaLimitada = Math.max(0, Math.min(linha, linhasOrdenadas.length - 1));
    const colunaLimitada = Math.max(0, Math.min(coluna, totalColunasFocaveis - 1));
    setFoco({ linha: linhaLimitada, coluna: colunaLimitada });
    virtualizador.scrollToIndex(linhaLimitada);
    queueMicrotask(() => refCelulas.current[`${linhaLimitada}-${colunaLimitada}`]?.focus());
  }

  function aoTeclarNaCelula(evento: KeyboardEvent<HTMLDivElement>, linha: number, coluna: number) {
    switch (evento.key) {
      case "ArrowDown":
        evento.preventDefault();
        focarCelula(linha + 1, coluna);
        break;
      case "ArrowUp":
        evento.preventDefault();
        focarCelula(linha - 1, coluna);
        break;
      case "ArrowRight":
        evento.preventDefault();
        focarCelula(linha, coluna + 1);
        break;
      case "ArrowLeft":
        evento.preventDefault();
        focarCelula(linha, coluna - 1);
        break;
      case "Home":
        evento.preventDefault();
        focarCelula(linha, 0);
        break;
      case "End":
        evento.preventDefault();
        focarCelula(linha, totalColunasFocaveis - 1);
        break;
      default:
        break;
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <details id={idPainelColunas} className="relative">
          <summary className="estilo-rotulo inline-block cursor-pointer select-none rounded-pequeno border border-borda-padrao bg-fundo-superficie px-2 py-1 text-texto-primario">
            Colunas
          </summary>
          <div className="absolute z-[var(--camada-suspenso)] mt-1 flex flex-col gap-1 rounded-medio border border-borda-padrao bg-fundo-superficie-elevada p-2 shadow-media">
            {colunas.map((coluna) => (
              <div key={coluna.id} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id={`${idPainelColunas}-${coluna.id}`}
                  checked={colunasVisiveisIds.includes(coluna.id)}
                  onChange={() => {
                    alternarColunaVisivel(coluna.id);
                  }}
                />
                <label
                  htmlFor={`${idPainelColunas}-${coluna.id}`}
                  className="estilo-corpo flex-1 text-texto-primario"
                >
                  {coluna.cabecalho}
                </label>
                <button
                  type="button"
                  aria-label={`Mover ${coluna.cabecalho} para a esquerda`}
                  className="estilo-legenda px-1 text-texto-secundario hover:text-texto-primario disabled:opacity-40"
                  disabled={!colunasVisiveisIds.includes(coluna.id)}
                  onClick={() => {
                    moverColuna(coluna.id, -1);
                  }}
                >
                  ‹
                </button>
                <button
                  type="button"
                  aria-label={`Mover ${coluna.cabecalho} para a direita`}
                  className="estilo-legenda px-1 text-texto-secundario hover:text-texto-primario disabled:opacity-40"
                  disabled={!colunasVisiveisIds.includes(coluna.id)}
                  onClick={() => {
                    moverColuna(coluna.id, 1);
                  }}
                >
                  ›
                </button>
              </div>
            ))}
          </div>
        </details>
        {selecionaveis ? (
          <p className="estilo-legenda text-texto-secundario" aria-live="polite">
            {selecionadosIds.size} selecionada{selecionadosIds.size === 1 ? "" : "s"}
          </p>
        ) : null}
      </div>

      <div
        ref={parentRef}
        role="grid"
        aria-rowcount={linhasOrdenadas.length}
        aria-colcount={totalColunasFocaveis}
        className="overflow-auto rounded-medio border border-borda-sutil"
        // `maxHeight`, nao `height` fixo: poucas linhas encolhem o cartao para o
        // conteudo real (evitava uma area vazia enorme abaixo de 1-2 linhas);
        // muitas linhas continuam limitadas a `alturaContainerPx` com scroll,
        // preservando a virtualizacao.
        style={{ maxHeight: alturaContainerPx }}
      >
        <div role="rowgroup">
          <div
            role="row"
            className="sticky top-0 z-[var(--camada-elevado)] grid bg-fundo-superficie-elevada"
            style={{ gridTemplateColumns }}
          >
            {selecionaveis ? (
              <div role="columnheader" className="flex items-center justify-center border-b border-borda-sutil p-1">
                <input
                  type="checkbox"
                  aria-label="Selecionar todas as linhas"
                  checked={linhasOrdenadas.length > 0 && selecionadosIds.size === linhasOrdenadas.length}
                  ref={(elemento) => {
                    if (elemento) {
                      elemento.indeterminate =
                        selecionadosIds.size > 0 && selecionadosIds.size < linhasOrdenadas.length;
                    }
                  }}
                  onChange={alternarSelecaoTudo}
                />
              </div>
            ) : null}
            {colunasVisiveis.map((coluna) => {
              const ordenacaoDaColuna = ordenacao?.colunaId === coluna.id ? ordenacao.direcao : null;
              const ariaSort = !coluna.ordenavel
                ? undefined
                : ordenacaoDaColuna === "asc"
                  ? "ascending"
                  : ordenacaoDaColuna === "desc"
                    ? "descending"
                    : "none";
              return (
                <div
                  key={coluna.id}
                  role="columnheader"
                  aria-sort={ariaSort}
                  className="estilo-rotulo border-b border-borda-sutil p-2 text-left text-texto-secundario"
                >
                  {coluna.ordenavel ? (
                    <button
                      type="button"
                      className="flex w-full items-center gap-1 text-left"
                      onClick={() => {
                        definirOrdenacao(proximaDirecao(ordenacao, coluna.id));
                      }}
                    >
                      {coluna.cabecalho}
                      {ordenacaoDaColuna === "asc" ? "▲" : ordenacaoDaColuna === "desc" ? "▼" : ""}
                    </button>
                  ) : (
                    coluna.cabecalho
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {carregando ? (
          <p className="estilo-corpo p-4 text-center text-texto-secundario">Carregando…</p>
        ) : linhasOrdenadas.length === 0 ? (
          <p className="estilo-corpo p-4 text-center text-texto-secundario">{mensagemVazia}</p>
        ) : (
          <div role="rowgroup" style={{ height: virtualizador.getTotalSize(), position: "relative" }}>
            {virtualizador.getVirtualItems().map((itemVirtual) => {
              const linhaAtual = linhasOrdenadas[itemVirtual.index];
              if (!linhaAtual) return null;
              const idDaLinha = obterId(linhaAtual);
              const selecionada = selecionadosIds.has(idDaLinha);
              let colunaFocavel = 0;

              return (
                <div
                  key={idDaLinha}
                  role="row"
                  aria-rowindex={itemVirtual.index + 1}
                  aria-selected={selecionaveis ? selecionada : undefined}
                  className={cn(
                    "absolute left-0 top-0 grid w-full items-center border-b border-borda-sutil",
                    selecionada && "bg-acao-sutil-fundo",
                  )}
                  style={{
                    gridTemplateColumns,
                    height: itemVirtual.size,
                    transform: `translateY(${itemVirtual.start}px)`,
                  }}
                >
                  {selecionaveis ? (
                    <div role="gridcell" className="flex items-center justify-center p-1">
                      <input
                        type="checkbox"
                        aria-label={`Selecionar linha ${itemVirtual.index + 1}`}
                        checked={selecionada}
                        onChange={() => {
                          alternarSelecaoLinha(idDaLinha);
                        }}
                      />
                    </div>
                  ) : null}
                  {colunasVisiveis.map((coluna) => {
                    const indiceColuna = colunaFocavel;
                    colunaFocavel += 1;
                    const emFoco = foco.linha === itemVirtual.index && foco.coluna === indiceColuna;
                    return (
                      <div
                        key={coluna.id}
                        ref={(elemento) => {
                          refCelulas.current[`${itemVirtual.index}-${indiceColuna}`] = elemento;
                        }}
                        role="gridcell"
                        tabIndex={emFoco ? 0 : -1}
                        className="estilo-tabular truncate p-2 text-texto-primario focus-visible:outline-none"
                        onFocus={() => {
                          setFoco({ linha: itemVirtual.index, coluna: indiceColuna });
                        }}
                        onKeyDown={(evento) => {
                          aoTeclarNaCelula(evento, itemVirtual.index, indiceColuna);
                        }}
                      >
                        {coluna.renderizarCelula(linhaAtual)}
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
