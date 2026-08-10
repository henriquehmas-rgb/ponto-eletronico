"use client";

import Link from "next/link";
import { useState } from "react";

import {
  Cartao,
  CartaoAcao,
  CartaoCabecalho,
  CartaoConteudo,
  CartaoDescricao,
  CartaoRodape,
  CartaoTitulo,
} from "@/componentes/ui/card";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { useCatalogoDeRelatorios } from "@/ganchos/use-relatorios";

import { ROTULO_CATEGORIA } from "./tipos";

/**
 * Catálogo de relatórios (T4): lista os 24, filtrável por categoria. Cada
 * item leva à tela de execução genérica (`/painel/relatorios/[codigo]`) —
 * nenhum item tem tela própria (PCF §6/T4, proibição 13).
 */
export function CatalogoDeRelatorios() {
  const [categoria, setCategoria] = useState<string>("");
  const consulta = useCatalogoDeRelatorios(categoria ? { categoria: categoria as never } : {});

  const categorias = Array.from(
    new Set((consulta.data ?? []).map((item) => item.categoria).filter(Boolean)),
  ) as string[];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setCategoria("")}
          className="estilo-legenda rounded-pleno bg-fundo-superficie px-3 py-1.5 text-texto-secundario shadow-flutuante-chip aria-pressed:bg-fundo-inverso aria-pressed:text-texto-inverso"
          aria-pressed={categoria === ""}
        >
          Todos
        </button>
        {categorias.map((valor) => (
          <button
            key={valor}
            type="button"
            onClick={() => setCategoria(valor)}
            className="estilo-legenda rounded-pleno bg-fundo-superficie px-3 py-1.5 text-texto-secundario shadow-flutuante-chip aria-pressed:bg-fundo-inverso aria-pressed:text-texto-inverso"
            aria-pressed={categoria === valor}
          >
            {ROTULO_CATEGORIA[valor] ?? valor}
          </button>
        ))}
      </div>

      {consulta.isLoading ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, indice) => (
            <Esqueleto key={indice} className="h-28 w-full rounded-suave" />
          ))}
        </div>
      ) : null}

      {consulta.isError ? (
        <p className="estilo-corpo text-estado-erro-texto">
          Não foi possível carregar o catálogo de relatórios.
        </p>
      ) : null}

      {consulta.data ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {consulta.data.map((relatorio) => (
            <Link key={relatorio.codigo} href={`/painel/relatorios/${relatorio.codigo}`}>
              <Cartao className="h-full gap-3 rounded-suave border-none shadow-flutuante-cartao transition-shadow hover:shadow-flutuante-alta">
                <CartaoCabecalho>
                  <CartaoTitulo className="estilo-titulo-secao">{relatorio.nome}</CartaoTitulo>
                  {relatorio.formatos && relatorio.formatos.length > 0 ? (
                    <CartaoAcao>
                      <span className="rounded-pleno bg-fundo-sutil px-2 py-1 font-mono text-[10px] font-semibold uppercase text-texto-terciario">
                        {relatorio.formatos[0]}
                      </span>
                    </CartaoAcao>
                  ) : null}
                  <CartaoDescricao>
                    {ROTULO_CATEGORIA[relatorio.categoria ?? ""] ?? relatorio.categoria}
                  </CartaoDescricao>
                </CartaoCabecalho>
                <CartaoConteudo>
                  <p className="estilo-legenda text-texto-terciario">{relatorio.descricao}</p>
                </CartaoConteudo>
                <CartaoRodape className="justify-end">
                  <span className="rounded-pleno bg-fundo-inverso px-3 py-1.5 text-[13px] font-semibold text-texto-inverso">
                    Gerar
                  </span>
                </CartaoRodape>
              </Cartao>
            </Link>
          ))}
        </div>
      ) : null}
    </div>
  );
}
