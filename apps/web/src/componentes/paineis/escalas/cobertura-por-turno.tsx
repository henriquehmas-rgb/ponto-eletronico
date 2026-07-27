import { useMemo } from "react";

import type { LinhaDeColaboradorNaGrade } from "@/componentes/dominio/grade-de-escala";
import { formatarDiaDaSemanaAbreviado } from "@/lib/formatacao/data";
import { cn } from "@/lib/utils";

interface TurnoDaCobertura {
  id: string;
  nome: string;
  cor: string;
}

/** Uma linha da matriz: um turno, com a contagem de vínculos por dia (mesma ordem de `datas`). */
interface LinhaDeCobertura {
  turno: TurnoDaCobertura;
  contagemPorDia: number[];
}

function calcularCobertura(
  datas: string[],
  linhas: LinhaDeColaboradorNaGrade[],
): LinhaDeCobertura[] {
  const porTurno = new Map<string, LinhaDeCobertura>();
  linhas.forEach((linha) => {
    linha.celulas.forEach((celula, indiceDia) => {
      const turno = celula.turno;
      if (!turno) return;
      let entrada = porTurno.get(turno.id);
      if (!entrada) {
        entrada = { turno, contagemPorDia: datas.map(() => 0) };
        porTurno.set(turno.id, entrada);
      }
      entrada.contagemPorDia[indiceDia] = (entrada.contagemPorDia[indiceDia] ?? 0) + 1;
    });
  });
  return Array.from(porTurno.values()).sort((a, b) => a.turno.nome.localeCompare(b.turno.nome));
}

function ehFimDeSemana(dataIso: string): boolean {
  const data = new Date(`${dataIso}T12:00:00`);
  const diaDaSemana = data.getDay();
  return diaDaSemana === 0 || diaDaSemana === 6;
}

/**
 * Cobertura por turno (T13): agregação client-side das células já resolvidas
 * pela grade (`GradeDeEscala`) — contagem de vínculos por turno, por dia.
 * Não é um `<GradeDeEscala>` (a semântica é agregada, não por vínculo), mas
 * segue a mesma regra de acessibilidade dela: cor E rótulo/número, nunca só
 * cor (WCAG 1.4.1).
 */
export function CoberturaPorTurno({
  datas,
  linhas,
}: {
  datas: string[];
  linhas: LinhaDeColaboradorNaGrade[];
}) {
  const cobertura = useMemo(() => calcularCobertura(datas, linhas), [datas, linhas]);

  if (cobertura.length === 0) {
    return (
      <p className="estilo-corpo text-texto-secundario">
        Nenhum turno resolvido no período para calcular cobertura.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <h2 className="estilo-titulo-secao text-texto-primario">Cobertura por turno</h2>
      <div className="max-h-96 max-w-full overflow-auto rounded-medio border border-borda-sutil">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th
                scope="col"
                className="estilo-rotulo sticky left-0 top-0 z-[calc(var(--camada-elevado)+1)] min-w-40 border border-borda-sutil bg-fundo-superficie-elevada px-2 py-1 text-left text-texto-secundario"
              >
                Turno
              </th>
              {datas.map((data) => (
                <th
                  key={data}
                  scope="col"
                  className={cn(
                    "estilo-rotulo sticky top-0 z-[var(--camada-elevado)] min-w-14 border border-borda-sutil bg-fundo-superficie-elevada px-2 py-1 text-center text-texto-secundario",
                    ehFimDeSemana(data) && "bg-fundo-sutil",
                  )}
                >
                  <span className="block">{formatarDiaDaSemanaAbreviado(`${data}T12:00:00`)}</span>
                  <span className="estilo-tabular block text-texto-primario">
                    {data.slice(8, 10)}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {cobertura.map((linha) => (
              <tr key={linha.turno.id}>
                <th
                  scope="row"
                  className="estilo-corpo sticky left-0 z-[var(--camada-elevado)] min-w-40 border border-borda-sutil bg-fundo-superficie-elevada px-2 py-1 text-left font-normal text-texto-primario"
                >
                  <span className="inline-flex items-center gap-2">
                    <span
                      aria-hidden="true"
                      className="size-2 shrink-0 rounded-pleno border border-borda-sutil"
                      style={{ backgroundColor: linha.turno.cor }}
                    />
                    {linha.turno.nome}
                  </span>
                </th>
                {linha.contagemPorDia.map((contagem, indice) => (
                  <td
                    key={`${linha.turno.id}-${datas[indice] ?? indice}`}
                    className="estilo-tabular h-8 min-w-14 border border-borda-sutil px-2 text-center align-middle text-texto-primario"
                  >
                    {contagem > 0 ? contagem : "—"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
