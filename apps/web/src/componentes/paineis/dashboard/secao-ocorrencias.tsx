"use client";

import { Cartao, CartaoCabecalho, CartaoConteudo, CartaoTitulo } from "@/componentes/ui/card";
import { Selo } from "@/componentes/ui/badge";
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

  return (
    <Cartao>
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
  );
}
