"use client";

import { GraficoDePizza } from "@/componentes/graficos/graficos";
import { Cartao, CartaoCabecalho, CartaoConteudo, CartaoTitulo } from "@/componentes/ui/card";
import {
  useContagemColaboradoresPorStatus,
  type FiltroDeEscopo,
} from "@/ganchos/use-indicadores-dashboard";

import { CartaoDeKpi } from "./cartao-de-kpi";

const ROTULO_STATUS: Record<string, string> = {
  ativo: "Ativos",
  afastado: "Afastados",
  ferias: "Em férias",
  suspenso: "Suspensos",
  pre_admissao: "Pré-admissão",
  desligado: "Desligados",
};

/** KPI de colaboradores ativos + composição por status (T2 — `GET /v1/colaboradores`, contagem por status). */
export function SecaoColaboradores({ escopo }: { escopo: FiltroDeEscopo }) {
  const contagens = useContagemColaboradoresPorStatus(escopo);
  const carregando = contagens.some((item) => item.carregando);
  const ativos = contagens.find((item) => item.status === "ativo")?.total ?? 0;
  const total = contagens.reduce((soma, item) => soma + item.total, 0);

  const fatias = contagens
    .filter((item) => item.total > 0)
    .map((item) => ({
      chave: item.status,
      rotulo: ROTULO_STATUS[item.status] ?? item.status,
      valor: item.total,
    }));

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_2fr]">
      <CartaoDeKpi
        rotulo="Colaboradores ativos"
        valor={String(ativos)}
        descricao={`${total} no total do escopo selecionado`}
        carregando={carregando}
      />
      <Cartao>
        <CartaoCabecalho>
          <CartaoTitulo>Colaboradores por situação</CartaoTitulo>
        </CartaoCabecalho>
        <CartaoConteudo>
          {carregando ? (
            <p className="estilo-corpo text-texto-secundario">Carregando…</p>
          ) : fatias.length === 0 ? (
            <p className="estilo-corpo text-texto-secundario">
              Nenhum colaborador no escopo selecionado.
            </p>
          ) : (
            <GraficoDePizza fatias={fatias} altura={240} />
          )}
        </CartaoConteudo>
      </Cartao>
    </div>
  );
}
