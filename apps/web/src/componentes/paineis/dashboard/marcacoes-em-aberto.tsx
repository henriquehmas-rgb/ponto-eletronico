"use client";

import { Cartao, CartaoCabecalho, CartaoConteudo, CartaoTitulo } from "@/componentes/ui/card";
import type { FiltroDeEscopo } from "@/ganchos/use-indicadores-dashboard";
import { useMarcacoesEmAberto } from "@/ganchos/use-marcacoes-em-aberto";
import { ehErroDaApi } from "@/lib/api";
import { formatarHora } from "@/lib/formatacao";

const ROTULO_CANAL: Record<string, string> = {
  terminal: "Terminal",
  mobile: "Celular",
  web: "Web",
  totem: "Totem",
  api: "API",
  importacao: "Importação",
};

/**
 * "Quem está com marcação em aberto hoje" (T3). *Polling* via TanStack Query
 * (`refetchInterval`, ver `useMarcacoesEmAberto`) — não é WebSocket/SSE, não
 * existe nenhum no backend.
 *
 * REGRA INEGOCIÁVEL: este widget nunca afirma "está trabalhando" como fato —
 * o REP-P não registra entrada/saída com certeza, o pareamento definitivo só
 * acontece na apuração. O rótulo é sempre honesto: "última marcação às HH:MM,
 * sem marcação registrada depois".
 */
export function MarcacoesEmAberto({ escopo }: { escopo: FiltroDeEscopo }) {
  const consulta = useMarcacoesEmAberto(escopo);

  return (
    <Cartao className="rounded-suave shadow-flutuante-cartao">
      <CartaoCabecalho>
        <CartaoTitulo>Marcações em aberto hoje</CartaoTitulo>
      </CartaoCabecalho>
      <CartaoConteudo className="flex flex-col gap-2">
        <p className="estilo-legenda text-texto-terciario">
          Número ímpar de marcações no dia — inferência de apresentação, não confirmação de
          presença. O pareamento oficial só acontece na apuração.
        </p>

        {consulta.isPending ? (
          <p className="estilo-corpo text-texto-secundario">Carregando…</p>
        ) : consulta.isError ? (
          <p className="estilo-corpo text-estado-erro-texto">
            Não foi possível carregar as marcações de hoje
            {ehErroDaApi(consulta.error) && consulta.error.problema?.title
              ? `: ${consulta.error.problema.title}`
              : "."}
          </p>
        ) : (consulta.data ?? []).length === 0 ? (
          <p className="estilo-corpo text-texto-secundario">
            Nenhum vínculo com marcação em aberto no momento.
          </p>
        ) : (
          <ul
            className="flex flex-col divide-y divide-borda-sutil"
            aria-label="Vínculos com marcação em aberto hoje"
          >
            {(consulta.data ?? []).map((item) => (
              <li key={item.vinculoId} className="flex items-center justify-between gap-3 py-2">
                <span className="estilo-corpo text-texto-primario">
                  {item.nomeColaborador ?? `Vínculo ${item.vinculoId.slice(0, 8)}`}
                </span>
                <span className="estilo-legenda text-texto-secundario">
                  última marcação às {formatarHora(item.ultimaMarcacaoEm)}
                  {item.ultimoCanal
                    ? ` · ${ROTULO_CANAL[item.ultimoCanal] ?? item.ultimoCanal}`
                    : ""}
                  , sem marcação registrada depois
                </span>
              </li>
            ))}
          </ul>
        )}
      </CartaoConteudo>
    </Cartao>
  );
}
