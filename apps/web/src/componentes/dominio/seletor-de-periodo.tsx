"use client";

import { useId, useMemo, useRef, useState, type KeyboardEvent } from "react";

import { formatarData } from "@/lib/formatacao/data";
import { cn } from "@/lib/utils";

export interface AtalhoDePeriodo {
  id: string;
  rotulo: string;
  inicio: string;
  fim: string;
}

export interface SeletorDePeriodoProps {
  /** Data ISO (`AAAA-MM-DD`) do início do intervalo selecionado, ou `null` se nada foi escolhido ainda. */
  inicio: string | null;
  fim: string | null;
  aoSelecionarIntervalo: (inicio: string, fim: string) => void;
  /** Atalhos oferecidos (mês corrente, mês anterior, período de apuração…). Sem atalho próprio, o componente não inventa um. */
  atalhos?: AtalhoDePeriodo[];
  /** Mês (1-indexado do usuário) inicialmente exibido no calendário. Padrão: mês de `inicio`, senão o mês atual. */
  mesInicial?: { ano: number; mes: number };
}

const NOMES_DIA_DA_SEMANA = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
const NOMES_MES = [
  "janeiro",
  "fevereiro",
  "março",
  "abril",
  "maio",
  "junho",
  "julho",
  "agosto",
  "setembro",
  "outubro",
  "novembro",
  "dezembro",
];

function paraIso(ano: number, mes: number, dia: number): string {
  const mesTexto = String(mes).padStart(2, "0");
  const diaTexto = String(dia).padStart(2, "0");
  return `${ano}-${mesTexto}-${diaTexto}`;
}

function diasDoMes(ano: number, mes: number): number {
  return new Date(ano, mes, 0).getDate();
}

/** Grade de 6×7 com os dias do mês, preenchendo as pontas com dias do mês vizinho para completar a semana. */
function construirGrade(ano: number, mes: number): { iso: string; foraDoMes: boolean }[] {
  const primeiroDiaSemana = new Date(ano, mes - 1, 1).getDay();
  const totalDiasMes = diasDoMes(ano, mes);
  const mesAnterior = mes === 1 ? 12 : mes - 1;
  const anoDoMesAnterior = mes === 1 ? ano - 1 : ano;
  const diasMesAnterior = diasDoMes(anoDoMesAnterior, mesAnterior);

  const celulas: { iso: string; foraDoMes: boolean }[] = [];

  for (let i = primeiroDiaSemana - 1; i >= 0; i--) {
    celulas.push({ iso: paraIso(anoDoMesAnterior, mesAnterior, diasMesAnterior - i), foraDoMes: true });
  }
  for (let dia = 1; dia <= totalDiasMes; dia++) {
    celulas.push({ iso: paraIso(ano, mes, dia), foraDoMes: false });
  }
  const mesSeguinte = mes === 12 ? 1 : mes + 1;
  const anoDoMesSeguinte = mes === 12 ? ano + 1 : ano;
  let diaSeguinte = 1;
  while (celulas.length % 7 !== 0) {
    celulas.push({ iso: paraIso(anoDoMesSeguinte, mesSeguinte, diaSeguinte), foraDoMes: true });
    diaSeguinte += 1;
  }
  return celulas;
}

/**
 * Seletor de intervalo de datas com atalhos, entrada por teclado completa e
 * validação de intervalo invertido. Navegação no calendário segue o padrão
 * WAI-ARIA de grade de datas: setas movem o foco dia a dia, `PageUp`/`PageDown`
 * trocam de mês, `Home`/`End` vão ao início/fim da semana, `Enter`/`Espaço`
 * seleciona.
 */
export function SeletorDePeriodo({
  inicio,
  fim,
  aoSelecionarIntervalo,
  atalhos = [],
  mesInicial,
}: SeletorDePeriodoProps) {
  const hoje = new Date();
  const anoInicial = mesInicial?.ano ?? (inicio ? Number(inicio.slice(0, 4)) : hoje.getFullYear());
  const mesInicialResolvido = mesInicial?.mes ?? (inicio ? Number(inicio.slice(5, 7)) : hoje.getMonth() + 1);

  const [ano, setAno] = useState(anoInicial);
  const [mes, setMes] = useState(mesInicialResolvido);
  const [diaComFoco, setDiaComFoco] = useState<string>(inicio ?? paraIso(anoInicial, mesInicialResolvido, 1));
  const [erro, setErro] = useState<string | null>(null);
  // Ancora do clique inicial do intervalo em andamento. E estado INTERNO,
  // separado de `inicio`/`fim` (que sao props controladas): a primeira
  // selecao ja emite um intervalo de um dia so (inicio === fim), entao nao
  // da para usar "fim preenchido" como sinal de "intervalo completo".
  const [ancoraSelecao, setAncoraSelecao] = useState<string | null>(null);
  const idAnuncio = useId();
  const idErro = useId();
  const refCelulas = useRef<Record<string, HTMLButtonElement | null>>({});

  const grade = useMemo(() => construirGrade(ano, mes), [ano, mes]);

  function irParaMes(delta: number) {
    let novoMes = mes + delta;
    let novoAno = ano;
    while (novoMes > 12) {
      novoMes -= 12;
      novoAno += 1;
    }
    while (novoMes < 1) {
      novoMes += 12;
      novoAno -= 1;
    }
    setMes(novoMes);
    setAno(novoAno);
  }

  function focar(iso: string) {
    setDiaComFoco(iso);
    const novoAno = Number(iso.slice(0, 4));
    const novoMes = Number(iso.slice(5, 7));
    if (novoAno !== ano || novoMes !== mes) {
      setAno(novoAno);
      setMes(novoMes);
    }
    queueMicrotask(() => refCelulas.current[iso]?.focus());
  }

  function selecionarDia(iso: string) {
    if (ancoraSelecao === null) {
      // Primeiro clique: comeca um intervalo novo (provisoriamente de um dia so).
      setErro(null);
      setAncoraSelecao(iso);
      aoSelecionarIntervalo(iso, iso);
      return;
    }
    if (iso < ancoraSelecao) {
      setErro("Data final não pode ser anterior à data inicial. Selecione novamente.");
      return;
    }
    setErro(null);
    aoSelecionarIntervalo(ancoraSelecao, iso);
    setAncoraSelecao(null);
  }

  function aoTeclarNaCelula(evento: KeyboardEvent<HTMLButtonElement>, iso: string) {
    const data = new Date(`${iso}T12:00:00`);
    switch (evento.key) {
      case "ArrowRight":
        evento.preventDefault();
        data.setDate(data.getDate() + 1);
        focar(paraIso(data.getFullYear(), data.getMonth() + 1, data.getDate()));
        break;
      case "ArrowLeft":
        evento.preventDefault();
        data.setDate(data.getDate() - 1);
        focar(paraIso(data.getFullYear(), data.getMonth() + 1, data.getDate()));
        break;
      case "ArrowDown":
        evento.preventDefault();
        data.setDate(data.getDate() + 7);
        focar(paraIso(data.getFullYear(), data.getMonth() + 1, data.getDate()));
        break;
      case "ArrowUp":
        evento.preventDefault();
        data.setDate(data.getDate() - 7);
        focar(paraIso(data.getFullYear(), data.getMonth() + 1, data.getDate()));
        break;
      case "Home": {
        evento.preventDefault();
        const diaSemana = data.getDay();
        data.setDate(data.getDate() - diaSemana);
        focar(paraIso(data.getFullYear(), data.getMonth() + 1, data.getDate()));
        break;
      }
      case "End": {
        evento.preventDefault();
        const diaSemana = data.getDay();
        data.setDate(data.getDate() + (6 - diaSemana));
        focar(paraIso(data.getFullYear(), data.getMonth() + 1, data.getDate()));
        break;
      }
      case "PageUp":
        evento.preventDefault();
        irParaMes(evento.shiftKey ? -12 : -1);
        break;
      case "PageDown":
        evento.preventDefault();
        irParaMes(evento.shiftKey ? 12 : 1);
        break;
      case "Enter":
      case " ":
        evento.preventDefault();
        selecionarDia(iso);
        break;
      default:
        break;
    }
  }

  const rotuloIntervalo =
    inicio && fim
      ? inicio === fim
        ? `Dia selecionado: ${formatarData(`${inicio}T12:00:00`)}`
        : `Intervalo selecionado: de ${formatarData(`${inicio}T12:00:00`)} até ${formatarData(`${fim}T12:00:00`)}`
      : "Nenhum intervalo selecionado";

  return (
    <div className="flex flex-col gap-3">
      {atalhos.length > 0 ? (
        <div className="flex flex-wrap gap-2" role="group" aria-label="Atalhos de período">
          {atalhos.map((atalho) => (
            <button
              key={atalho.id}
              type="button"
              className="estilo-rotulo rounded-pequeno border border-borda-padrao bg-fundo-superficie px-2 py-1 text-texto-primario hover:bg-fundo-sutil focus-visible:outline-none"
              onClick={() => {
                setErro(null);
                setAncoraSelecao(null);
                aoSelecionarIntervalo(atalho.inicio, atalho.fim);
                focar(atalho.inicio);
              }}
            >
              {atalho.rotulo}
            </button>
          ))}
        </div>
      ) : null}

      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          aria-label="Mês anterior"
          className="estilo-corpo flex size-9 items-center justify-center rounded-pequeno border border-borda-padrao text-texto-primario hover:bg-fundo-sutil"
          onClick={() => {
            irParaMes(-1);
          }}
        >
          ‹
        </button>
        <p className="estilo-titulo-cartao text-texto-primario" aria-live="off">
          {NOMES_MES[mes - 1]} de {ano}
        </p>
        <button
          type="button"
          aria-label="Próximo mês"
          className="estilo-corpo flex size-9 items-center justify-center rounded-pequeno border border-borda-padrao text-texto-primario hover:bg-fundo-sutil"
          onClick={() => {
            irParaMes(1);
          }}
        >
          ›
        </button>
      </div>

      <table role="grid" aria-label="Calendário" className="w-full border-collapse">
        <thead>
          <tr>
            {NOMES_DIA_DA_SEMANA.map((nome) => (
              <th key={nome} scope="col" className="estilo-legenda p-1 text-center text-texto-terciario">
                {nome}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: grade.length / 7 }, (_valor, indiceSemana) => {
            const semana = grade.slice(indiceSemana * 7, indiceSemana * 7 + 7);
            const chaveSemana = semana[0]?.iso ?? String(indiceSemana);
            return (
            <tr key={chaveSemana}>
              {semana.map((celula) => {
                const selecionado =
                  inicio !== null && fim !== null && celula.iso >= inicio && celula.iso <= fim;
                const ehFoco = celula.iso === diaComFoco;
                return (
                  <td key={celula.iso} className="p-0.5 text-center">
                    <button
                      type="button"
                      ref={(elemento) => {
                        refCelulas.current[celula.iso] = elemento;
                      }}
                      tabIndex={ehFoco ? 0 : -1}
                      aria-label={formatarData(`${celula.iso}T12:00:00`)}
                      aria-pressed={selecionado}
                      aria-current={celula.iso === paraIso(hoje.getFullYear(), hoje.getMonth() + 1, hoje.getDate()) ? "date" : undefined}
                      className={cn(
                        "estilo-tabular flex size-9 items-center justify-center rounded-pequeno text-texto-primario",
                        // Dia fora do mes ainda e clicavel (navega para o mes vizinho) — por
                        // isso usa texto.terciario (discreto, mas AA), nunca texto.desabilitado
                        // (reservado para controle de verdade indisponivel, sem esse contraste).
                        celula.foraDoMes && "text-texto-terciario",
                        selecionado && "bg-acao-primaria-fundo text-acao-primaria-texto",
                        !selecionado && "hover:bg-fundo-sutil",
                      )}
                      onKeyDown={(evento) => {
                        aoTeclarNaCelula(evento, celula.iso);
                      }}
                      onClick={() => {
                        focar(celula.iso);
                        selecionarDia(celula.iso);
                      }}
                    >
                      {Number(celula.iso.slice(8, 10))}
                    </button>
                  </td>
                );
              })}
            </tr>
            );
          })}
        </tbody>
      </table>

      <p id={idAnuncio} role="status" className="estilo-legenda text-texto-secundario">
        {rotuloIntervalo}
      </p>
      {erro ? (
        <p id={idErro} role="alert" className="estilo-legenda text-estado-erro-texto">
          {erro}
        </p>
      ) : null}
    </div>
  );
}
