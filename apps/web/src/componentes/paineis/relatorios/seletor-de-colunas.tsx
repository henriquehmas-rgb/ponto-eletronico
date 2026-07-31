"use client";

import { GripVertical, X } from "lucide-react";
import { useState, type DragEvent } from "react";

import { Botao } from "@/componentes/ui/button";

import type { ColunaDoCatalogo } from "./tipos";

interface SeletorDeColunasProps {
  colunas: ColunaDoCatalogo[];
  selecionadas: string[];
  aoMudar: (chaves: string[]) => void;
  aoSalvarComoPadrao?: (() => void) | undefined;
  salvando?: boolean;
  temPadraoSalvo?: boolean;
}

/**
 * Seletor de colunas da tela genérica de relatórios (T4): mostrar/ocultar
 * (adicionar/remover da lista de selecionadas) e arrastar-para-reordenar
 * (API nativa de drag-and-drop do HTML5 — nenhuma biblioteca nova só para
 * isto). "Salvar como padrão" delega ao chamador (`useSalvarPreferenciaDe
 * Colunas`, RFC-015) — este componente não fala com a API diretamente.
 */
export function SeletorDeColunas({
  colunas,
  selecionadas,
  aoMudar,
  aoSalvarComoPadrao,
  salvando = false,
  temPadraoSalvo = false,
}: SeletorDeColunasProps) {
  const [chaveArrastada, setChaveArrastada] = useState<string | null>(null);
  const porChave = new Map(colunas.map((coluna) => [coluna.chave, coluna]));
  const naoSelecionadas = colunas.filter((coluna) => !selecionadas.includes(coluna.chave));

  function remover(chave: string) {
    aoMudar(selecionadas.filter((item) => item !== chave));
  }

  function adicionar(chave: string) {
    aoMudar([...selecionadas, chave]);
  }

  function moverPara(chaveAlvo: string) {
    if (!chaveArrastada || chaveArrastada === chaveAlvo) return;
    const semArrastada = selecionadas.filter((item) => item !== chaveArrastada);
    const indiceAlvo = semArrastada.indexOf(chaveAlvo);
    const proxima = [
      ...semArrastada.slice(0, indiceAlvo),
      chaveArrastada,
      ...semArrastada.slice(indiceAlvo),
    ];
    aoMudar(proxima);
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="estilo-legenda font-medium text-texto-secundario">
          Colunas exibidas (arraste para reordenar)
        </p>
        {aoSalvarComoPadrao ? (
          <Botao
            type="button"
            variant="secundaria"
            tamanho="compacto"
            disabled={salvando}
            onClick={aoSalvarComoPadrao}
          >
            {salvando ? "Salvando…" : temPadraoSalvo ? "Atualizar padrão" : "Salvar como padrão"}
          </Botao>
        ) : null}
      </div>

      <ul className="flex flex-col gap-1" data-testid="colunas-selecionadas">
        {selecionadas.length === 0 ? (
          <li className="estilo-legenda text-texto-terciario">Nenhuma coluna selecionada.</li>
        ) : null}
        {selecionadas.map((chave) => {
          const coluna = porChave.get(chave);
          if (!coluna) return null;
          return (
            <li
              key={chave}
              draggable
              onDragStart={() => setChaveArrastada(chave)}
              onDragOver={(evento: DragEvent<HTMLLIElement>) => evento.preventDefault()}
              onDrop={(evento: DragEvent<HTMLLIElement>) => {
                evento.preventDefault();
                moverPara(chave);
              }}
              onDragEnd={() => setChaveArrastada(null)}
              className="flex items-center gap-2 rounded-pequeno border border-borda-sutil bg-fundo-superficie px-2 py-1"
            >
              <GripVertical
                className="size-4 shrink-0 cursor-grab text-texto-terciario"
                aria-hidden="true"
              />
              <span className="estilo-corpo flex-1 text-texto-primario">{coluna.rotulo}</span>
              <button
                type="button"
                onClick={() => remover(chave)}
                aria-label={`Ocultar coluna ${coluna.rotulo}`}
                className="rounded-pequeno p-1 text-texto-terciario hover:text-texto-primario"
              >
                <X className="size-4" aria-hidden="true" />
              </button>
            </li>
          );
        })}
      </ul>

      {naoSelecionadas.length > 0 ? (
        <div className="flex flex-col gap-1">
          <p className="estilo-legenda font-medium text-texto-secundario">Colunas disponíveis</p>
          <div className="flex flex-wrap gap-2">
            {naoSelecionadas.map((coluna) => (
              <button
                key={coluna.chave}
                type="button"
                onClick={() => adicionar(coluna.chave)}
                className="estilo-legenda rounded-pequeno border border-borda-controle px-2 py-1 text-texto-secundario hover:border-borda-forte"
              >
                + {coluna.rotulo}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
