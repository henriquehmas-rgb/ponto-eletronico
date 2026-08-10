"use client";

import { useAprovacoesPendentes } from "@/ganchos/use-aprovacoes";

/** Cabeçalho de `/painel/aprovacoes` — subtítulo com a contagem real de
 * pendentes (`GET /v1/aprovacoes`, mesma consulta do widget do dashboard). */
export function CabecalhoDeAprovacoes() {
  const consulta = useAprovacoesPendentes(50);
  const total = consulta.data?.dados?.length;

  return (
    <header>
      <h1 className="estilo-titulo-pagina text-texto-primario">Aprovações</h1>
      <p className="estilo-corpo text-texto-secundario">
        {consulta.isPending
          ? "Carregando fila…"
          : total === 0
            ? "Nenhuma etapa aguardando decisão."
            : `${total} etapa${total === 1 ? "" : "s"} aguardando decisão.`}
      </p>
    </header>
  );
}
