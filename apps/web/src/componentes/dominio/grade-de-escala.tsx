import { formatarDiaDaSemanaAbreviado } from "@/lib/formatacao/data";
import { cn } from "@/lib/utils";

export type TipoDeDiaDeEscala = "trabalho" | "folga" | "dsr" | "feriado" | "compensado";

export interface CelulaDeEscala {
  /** Data ISO (`AAAA-MM-DD`) do dia de INÍCIO do turno — jornada que cruza a meia-noite pertence a este dia. */
  data: string;
  turno?: {
    id: string;
    nome: string;
    /** Cor em hexadecimal cadastrada no turno (contrato `Turno.cor`) — não é um token de design, é dado de negócio configurável por empresa. */
    cor: string;
  } | null;
  tipoDia?: TipoDeDiaDeEscala;
  /** Verdadeiro quando o turno começa neste dia e termina depois da meia-noite. */
  cruzaMeiaNoite?: boolean;
}

export interface LinhaDeColaboradorNaGrade {
  colaboradorId: string;
  nomeColaborador: string;
  /** Uma célula por data em `datas`, na mesma ordem. */
  celulas: CelulaDeEscala[];
}

export interface GradeDeEscalaProps {
  /** Datas ISO (`AAAA-MM-DD`) das colunas, em ordem — pode atravessar virada de mês. */
  datas: string[];
  linhas: LinhaDeColaboradorNaGrade[];
  fusoHorario?: string;
}

function ehFimDeSemana(dataIso: string): boolean {
  const data = new Date(`${dataIso}T12:00:00`);
  const diaDaSemana = data.getDay();
  return diaDaSemana === 0 || diaDaSemana === 6;
}

function ROTULO_TIPO_DIA(tipo: TipoDeDiaDeEscala): string {
  switch (tipo) {
    case "folga":
      return "Folga";
    case "dsr":
      return "DSR";
    case "feriado":
      return "Feriado";
    case "compensado":
      return "Compensado";
    case "trabalho":
      return "";
  }
}

function CelulaDaGrade({ celula }: { celula: CelulaDeEscala }) {
  const tipoDia = celula.tipoDia ?? (celula.turno ? "trabalho" : "folga");

  if (tipoDia !== "trabalho" || !celula.turno) {
    return (
      <td
        className={cn(
          "estilo-legenda h-8 min-w-20 border border-borda-sutil px-2 text-center align-middle",
          tipoDia === "feriado" && "bg-estado-info-fundo text-estado-info-texto",
          tipoDia === "dsr" && "bg-fundo-enfase text-texto-secundario",
          (tipoDia === "folga" || tipoDia === "compensado") && "bg-fundo-sutil text-texto-terciario",
        )}
      >
        {ROTULO_TIPO_DIA(tipoDia)}
      </td>
    );
  }

  return (
    <td className="h-8 min-w-20 border border-borda-sutil px-2 align-middle">
      <span
        className="estilo-legenda inline-flex max-w-full items-center gap-1 truncate"
        title={
          celula.cruzaMeiaNoite
            ? `${celula.turno.nome} — continua no dia seguinte`
            : celula.turno.nome
        }
      >
        <span
          aria-hidden="true"
          className="inline-block size-2 shrink-0 rounded-pleno border border-borda-sutil"
          style={{ backgroundColor: celula.turno.cor }}
        />
        <span className="truncate text-texto-primario">{celula.turno.nome}</span>
        {celula.cruzaMeiaNoite ? (
          <span aria-label="continua no dia seguinte" className="shrink-0 text-texto-terciario">
            →
          </span>
        ) : null}
      </span>
    </td>
  );
}

/**
 * Matriz colaborador × dia com turno por célula. Cabeçalho fixo nas duas
 * direções (data no topo, colaborador à esquerda) para conferir escalas
 * longas sem perder a referência. Suporta qualquer ciclo (5x2, 6x1, 12x36,
 * espanhola, rotativa) porque só desenha o que vier em `celulas` — a
 * aritmética do ciclo é resolvida por quem monta os dados (F3), não aqui.
 */
export function GradeDeEscala({ datas, linhas, fusoHorario }: GradeDeEscalaProps) {
  return (
    <div className="max-h-128 max-w-full overflow-auto rounded-medio border border-borda-sutil">
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <th
              scope="col"
              className="estilo-rotulo sticky left-0 top-0 z-[calc(var(--camada-elevado)+1)] min-w-32 border border-borda-sutil bg-fundo-superficie-elevada px-2 py-1 text-left text-texto-secundario"
            >
              Colaborador
            </th>
            {datas.map((data) => (
              <th
                key={data}
                scope="col"
                className={cn(
                  "estilo-rotulo sticky top-0 z-[var(--camada-elevado)] min-w-20 border border-borda-sutil bg-fundo-superficie-elevada px-2 py-1 text-center text-texto-secundario",
                  ehFimDeSemana(data) && "bg-fundo-sutil",
                )}
              >
                <span className="block">{formatarDiaDaSemanaAbreviado(`${data}T12:00:00`, fusoHorario)}</span>
                <span className="estilo-tabular block text-texto-primario">{data.slice(8, 10)}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {linhas.map((linha) => (
            <tr key={linha.colaboradorId}>
              <th
                scope="row"
                className="estilo-corpo sticky left-0 z-[var(--camada-elevado)] min-w-32 border border-borda-sutil bg-fundo-superficie-elevada px-2 py-1 text-left font-normal text-texto-primario"
              >
                {linha.nomeColaborador}
              </th>
              {linha.celulas.map((celula, indice) => (
                <CelulaDaGrade key={datas[indice] ?? celula.data} celula={celula} />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
