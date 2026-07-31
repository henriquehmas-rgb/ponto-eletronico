"use client";

import { GraficoDeBarras, GraficoDeLinha } from "@/componentes/graficos/graficos";
import { Cartao, CartaoCabecalho, CartaoConteudo, CartaoTitulo } from "@/componentes/ui/card";
import { CHAVE_VALOR_HORAS_EXTRAS, useTendenciaMensal } from "@/ganchos/use-dataviz-dashboard";
import {
  periodoDoMesCorrente,
  useResumoDeApuracao,
  type FiltroDeEscopo,
} from "@/ganchos/use-indicadores-dashboard";
import { minutosParaHHMM } from "@/lib/formatacao";

import { CartaoDeKpi } from "./cartao-de-kpi";

/** Extras/faltas/atrasos agregados do mês corrente + série diária (T2 — `GET /v1/apuracoes`). */
export function SecaoApuracao({ escopo }: { escopo: FiltroDeEscopo }) {
  const periodo = periodoDoMesCorrente();
  const resumo = useResumoDeApuracao(escopo, periodo);
  const carregando = resumo.isPending;
  const dados = resumo.data;

  // Dataviz (T13, PCF F11 §2.6): tendência de horas extras dos últimos 6
  // meses, alimentada pelo motor de relatórios (`executarRelatorio`,
  // dataset `horas-extras` do catálogo) — nunca a mesma consulta de
  // `useResumoDeApuracao` acima, que é outra FORMA de dado (KPI do mês
  // corrente, não série histórica).
  const tendenciaDeExtras = useTendenciaMensal({
    codigo: "horas-extras",
    chaveValor: CHAVE_VALOR_HORAS_EXTRAS,
    empresaId: escopo.empresaId,
    unidadeId: escopo.unidadeId,
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <CartaoDeKpi
          rotulo="Horas extras (mês)"
          valor={dados ? minutosParaHHMM(dados.extrasMinutos) : "—"}
          carregando={carregando}
        />
        <CartaoDeKpi
          rotulo="Faltas (mês)"
          valor={dados ? minutosParaHHMM(dados.faltaMinutos) : "—"}
          carregando={carregando}
        />
        <CartaoDeKpi
          rotulo="Atrasos (mês)"
          valor={dados ? minutosParaHHMM(dados.atrasoMinutos) : "—"}
          carregando={carregando}
        />
        <CartaoDeKpi
          rotulo="Dias com ocorrência"
          valor={dados ? String(dados.diasComOcorrencia) : "—"}
          descricao={dados ? `de ${dados.diasApurados} dias apurados` : undefined}
          carregando={carregando}
        />
      </div>

      <Cartao>
        <CartaoCabecalho>
          <CartaoTitulo>Extras, faltas e atrasos por dia</CartaoTitulo>
        </CartaoCabecalho>
        <CartaoConteudo>
          {carregando ? (
            <p className="estilo-corpo text-texto-secundario">Carregando…</p>
          ) : !dados || dados.serieDiaria.length === 0 ? (
            <p className="estilo-corpo text-texto-secundario">
              Nenhuma apuração no período (mês corrente) para o escopo selecionado.
            </p>
          ) : (
            <GraficoDeBarras
              dados={dados.serieDiaria}
              chaveCategoria="data"
              altura={260}
              series={[
                { chave: "extrasMinutos", rotulo: "Extras (min)" },
                { chave: "faltaMinutos", rotulo: "Faltas (min)" },
                { chave: "atrasoMinutos", rotulo: "Atrasos (min)" },
              ]}
            />
          )}
        </CartaoConteudo>
      </Cartao>

      <Cartao>
        <CartaoCabecalho>
          <CartaoTitulo>Tendência de horas extras (últimos 6 meses)</CartaoTitulo>
        </CartaoCabecalho>
        <CartaoConteudo>
          {tendenciaDeExtras.isPending ? (
            <p className="estilo-corpo text-texto-secundario">Carregando…</p>
          ) : tendenciaDeExtras.isError ? (
            <p className="estilo-corpo text-estado-erro-texto">
              Não foi possível carregar a tendência de horas extras.
            </p>
          ) : !tendenciaDeExtras.data || tendenciaDeExtras.data.length === 0 ? (
            <p className="estilo-corpo text-texto-secundario">
              Sem dado suficiente no período para montar a tendência.
            </p>
          ) : (
            <GraficoDeLinha
              dados={tendenciaDeExtras.data}
              chaveCategoria="mes"
              altura={220}
              series={[{ chave: "valor", rotulo: "Extras (min)" }]}
            />
          )}
        </CartaoConteudo>
      </Cartao>
    </div>
  );
}
