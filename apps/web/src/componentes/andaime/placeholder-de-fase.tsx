import type { ReactNode } from "react";

/**
 * Placeholder honesto de rota.
 *
 * A Fase 0 e contrato e andaime: nao existe regra de negocio, nao existe UI de
 * produto. Em vez de desenhar uma tela falsa que alguem possa confundir com
 * entrega, cada rota diz o que sera, QUEM a implementa e do que depende.
 */
export interface PlaceholderDeFaseProps {
  fase: string;
  tituloDaFase: string;
  rota: string;
  destinatario: string;
  descricao: string;
  dependeDe: readonly string[];
  entregas: readonly string[];
  extra?: ReactNode;
}

export function PlaceholderDeFase({
  fase,
  tituloDaFase,
  rota,
  destinatario,
  descricao,
  dependeDe,
  entregas,
  extra,
}: PlaceholderDeFaseProps) {
  return (
    <section className="mx-auto w-full max-w-3xl px-6 py-12">
      <p className="estilo-rotulo uppercase text-texto-terciario">
        Andaime da Fase 0 — sem regra de negocio
      </p>

      <h1 className="estilo-titulo-pagina mt-2 text-texto-primario">{rota}</h1>

      <p className="estilo-corpo-grande mt-3 text-texto-secundario">{descricao}</p>

      <dl className="mt-8 grid gap-px overflow-hidden rounded-medio border border-borda-sutil bg-borda-sutil sm:grid-cols-2">
        <Celula rotulo="Implementada por">
          <span className="estilo-identificador rounded-pequeno bg-acao-sutil-fundo px-2 py-1 text-acao-sutil-texto">
            {fase}
          </span>{" "}
          {tituloDaFase}
        </Celula>
        <Celula rotulo="Publico">{destinatario}</Celula>
        <Celula rotulo="Depende de">{dependeDe.join(" · ")}</Celula>
        <Celula rotulo="Estado hoje">
          Rota existe, tema e cliente HTTP ligados, nenhuma chamada a API.
        </Celula>
      </dl>

      <h2 className="estilo-titulo-secao mt-10 text-texto-primario">O que esta fase entrega</h2>
      <ul className="mt-3 space-y-2">
        {entregas.map((item) => (
          <li key={item} className="estilo-corpo flex gap-3 text-texto-secundario">
            <span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-pleno bg-borda-forte" />
            {item}
          </li>
        ))}
      </ul>

      {extra}
    </section>
  );
}

function Celula({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return (
    <div className="bg-fundo-superficie p-4">
      <dt className="estilo-legenda uppercase text-texto-terciario">{rotulo}</dt>
      <dd className="estilo-corpo mt-1 text-texto-primario">{children}</dd>
    </div>
  );
}
