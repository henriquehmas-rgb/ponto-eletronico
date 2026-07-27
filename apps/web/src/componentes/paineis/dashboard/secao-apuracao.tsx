"use client";

import { GraficoDeBarras } from "@/componentes/graficos/graficos";
import { Cartao, CartaoCabecalho, CartaoConteudo, CartaoTitulo } from "@/componentes/ui/card";
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
    </div>
  );
}
