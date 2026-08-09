"use client";

import { GraficoDeBarras } from "@/componentes/graficos/graficos";
import { Cartao, CartaoCabecalho, CartaoConteudo, CartaoTitulo } from "@/componentes/ui/card";
import { Selo } from "@/componentes/ui/badge";
import { CHAVE_VALOR_OCORRENCIAS, useTendenciaMensal } from "@/ganchos/use-dataviz-dashboard";
import {
  useFilaDeOcorrenciasPorSeveridade,
  type FiltroDeEscopo,
} from "@/ganchos/use-indicadores-dashboard";

const ROTULO_SEVERIDADE: Record<string, string> = {
  info: "Informativa",
  atencao: "Atenção",
  alta: "Alta",
  critica: "Crítica",
};

const VARIANTE_SEVERIDADE: Record<string, "neutro" | "atencao" | "erro"> = {
  info: "neutro",
  atencao: "atencao",
  alta: "atencao",
  critica: "erro",
};

/** Fila de ocorrências abertas, por severidade (T2 — `GET /v1/ocorrencias`). Ocorrência não corrige nada: só chama o humano. */
export function SecaoOcorrencias({ escopo }: { escopo: FiltroDeEscopo }) {
  const contagens = useFilaDeOcorrenciasPorSeveridade(escopo);
  const carregando = contagens.some((item) => item.carregando);
  const totalAbertas = contagens.reduce((soma, item) => soma + item.total, 0);
  // Dataviz (T13, PCF F11 §2.6): volume de ocorrências por mês, alimentado
  // pelo motor de relatórios (dataset `ocorrencias` do catálogo) — nunca a
  // mesma consulta de `useFilaDeOcorrenciasPorSeveridade` acima (contagem do
  // dia corrente por severidade), que é outra FORMA de dado.
  const tendenciaDeOcorrencias = useTendenciaMensal({
    codigo: "ocorrencias",
    chaveValor: CHAVE_VALOR_OCORRENCIAS,
    empresaId: escopo.empresaId,
    unidadeId: escopo.unidadeId,
  });

  return (
    <div className="flex flex-col gap-4">
      <Cartao className="rounded-suave shadow-flutuante-cartao">
        <CartaoCabecalho>
          <CartaoTitulo>Ocorrências abertas</CartaoTitulo>
        </CartaoCabecalho>
        <CartaoConteudo className="flex flex-col gap-3">
          {carregando ? (
            <p className="estilo-corpo text-texto-secundario">Carregando…</p>
          ) : totalAbertas === 0 ? (
            <p className="estilo-corpo text-texto-secundario">
              Nenhuma ocorrência aberta no escopo selecionado.
            </p>
          ) : (
            <>
              <p className="estilo-numero-destaque text-texto-primario">{totalAbertas}</p>
              <ul className="flex flex-wrap gap-2">
                {contagens
                  .filter((item) => item.total > 0)
                  .map((item) => (
                    <li key={item.severidade}>
                      <Selo variant={VARIANTE_SEVERIDADE[item.severidade]}>
                        {ROTULO_SEVERIDADE[item.severidade] ?? item.severidade}: {item.total}
                      </Selo>
                    </li>
                  ))}
              </ul>
            </>
          )}
        </CartaoConteudo>
      </Cartao>

      <Cartao className="rounded-suave shadow-flutuante-cartao">
        <CartaoCabecalho>
          <CartaoTitulo>Ocorrências por mês (últimos 6 meses)</CartaoTitulo>
        </CartaoCabecalho>
        <CartaoConteudo>
          {tendenciaDeOcorrencias.isPending ? (
            <p className="estilo-corpo text-texto-secundario">Carregando…</p>
          ) : tendenciaDeOcorrencias.isError ? (
            <p className="estilo-corpo text-estado-erro-texto">
              Não foi possível carregar a série mensal de ocorrências.
            </p>
          ) : !tendenciaDeOcorrencias.data || tendenciaDeOcorrencias.data.length === 0 ? (
            <p className="estilo-corpo text-texto-secundario">
              Sem dado suficiente no período para montar a série mensal.
            </p>
          ) : (
            <GraficoDeBarras
              dados={tendenciaDeOcorrencias.data}
              chaveCategoria="mes"
              altura={220}
              series={[{ chave: "valor", rotulo: "Ocorrências" }]}
            />
          )}
        </CartaoConteudo>
      </Cartao>
    </div>
  );
}
