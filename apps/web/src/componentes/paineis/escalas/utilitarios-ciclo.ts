import type { Esquema } from "@/lib/api";

/**
 * Funções puras de apoio à grade de escala (T13) — sem chamada de rede, sem
 * estado. Cada uma tem teste unitário dedicado em
 * `src/testes/paineis/escalas/utilitarios-ciclo.teste.ts`.
 */

/** `tipoDia` como o contrato devolve (`ApuracaoDia`/`ResolucaoJornada` — os dois usam o mesmo enum de 8 valores). */
type TipoDiaDoDominio = NonNullable<Esquema<"ApuracaoDia">["tipoDia"]>;

/** `tipoDia` como `GradeDeEscala` (F9a, congelado) aceita — só 5 valores. */
export type TipoDeDiaDeEscala = "trabalho" | "folga" | "dsr" | "feriado" | "compensado";

/**
 * O enum de domínio (`ResolucaoJornada.tipoDia`/`ApuracaoDia.tipoDia`) tem 8
 * valores; `GradeDeEscala.CelulaDeEscala.tipoDia` (design system congelado,
 * F9a) só aceita 5 — não é uma variante que falta pedir de volta, é uma
 * classificação mais rica (a apuração distingue "dia útil sem jornada
 * resolvida" de "ponto facultativo", a grade visual não precisa dessa
 * distinção). Mapeamento, não invenção: quando o dia tem turno resolvido
 * (`temTurno`), devolve `undefined` para deixar `GradeDeEscala` inferir
 * "trabalho" a partir do turno (mesma regra que o componente já usa);
 * "ponto_facultativo"/"afastamento"/"nao_apurado" caem em "folga" — o rótulo
 * mais neutro entre os cinco que `GradeDeEscala` sabe desenhar. Registrado em
 * `docs/backlog.md` para quem eventualmente ampliar o componente de domínio.
 */
export function mapearTipoDia(
  tipoDia: TipoDiaDoDominio | undefined,
  temTurno: boolean,
): TipoDeDiaDeEscala | undefined {
  if (temTurno) return undefined;
  switch (tipoDia) {
    case "dsr":
      return "dsr";
    case "folga":
      return "folga";
    case "feriado":
      return "feriado";
    case "compensado":
      return "compensado";
    case "util":
    case "ponto_facultativo":
    case "afastamento":
    case "nao_apurado":
    case undefined:
      return "folga";
    default:
      return "folga";
  }
}

const MS_POR_DIA = 24 * 60 * 60 * 1000;

/** ISO (`AAAA-MM-DD`) → meio-dia UTC, para diferenças de data imunes a DST. */
function paraMeioDiaUtc(dataIso: string): Date {
  return new Date(`${dataIso}T12:00:00Z`);
}

/** Quantidade de dias corridos de `a` até `b` (pode ser negativo se `b` for anterior a `a`). */
export function diasEntreIso(a: string, b: string): number {
  const diferencaMs = paraMeioDiaUtc(b).getTime() - paraMeioDiaUtc(a).getTime();
  return Math.round(diferencaMs / MS_POR_DIA);
}

/** Lista de datas ISO (`AAAA-MM-DD`), inclusive nas duas pontas, em ordem crescente. */
export function datasDoIntervalo(inicioIso: string, fimIso: string): string[] {
  const datas: string[] = [];
  let cursor = paraMeioDiaUtc(inicioIso);
  const fim = paraMeioDiaUtc(fimIso);
  while (cursor.getTime() <= fim.getTime()) {
    datas.push(cursor.toISOString().slice(0, 10));
    cursor = new Date(cursor.getTime() + MS_POR_DIA);
  }
  return datas;
}

/**
 * Verdadeiro quando `data` é posterior a `hojeIso` — a fronteira que decide
 * se a grade de escala (T13) usa `GET /v1/apuracoes` (passado/hoje, já
 * apurado ou apurável) ou `resolverJornadaDoDia` (futuro, achado de contrato
 * nº 1 do PCF F9b §2: sem leitura em lote, uma chamada por célula).
 */
export function ehDataFutura(dataIso: string, hojeIso: string): boolean {
  return dataIso > hojeIso;
}

/**
 * "Copiar período" (achado de contrato nº 2, PCF F9b §2): não existe
 * endpoint de cópia — é composição no cliente usando a aritmética modular que
 * o próprio schema de `Escala` já expõe (`diasCiclo`).
 *
 * Em vez de recalcular a partir de `Escala.dataReferencia` (o que exigiria
 * reproduzir a precedência de fase que cada `EscalaAtribuicao.posicaoInicial`
 * pode introduzir — plantão A na posição 1, plantão B na posição 2 da MESMA
 * escala), ancora no par `(dataOrigem, posicaoCicloOrigem)` que
 * `resolverJornadaDoDia` já devolveu para o vínculo de referência: isso
 * preserva a fase resolvida DAQUELE vínculo (o que "copiar o período dele"
 * significa), sem duplicar a lógica de precedência escondida do resolvedor
 * (proibição expressa do PCF).
 *
 * `diasCiclo` vem de `Escala.diasCiclo` (`obterEscala`). Resultado sempre em
 * `[1, diasCiclo]`.
 */
export function calcularPosicaoInicial(
  dataOrigemIso: string,
  posicaoCicloOrigem: number,
  novaVigenciaInicioIso: string,
  diasCiclo: number,
): number {
  if (diasCiclo < 1) {
    throw new Error(`calcularPosicaoInicial: diasCiclo precisa ser >= 1 (recebido ${diasCiclo}).`);
  }
  const deslocamento = diasEntreIso(dataOrigemIso, novaVigenciaInicioIso);
  const resto = (((posicaoCicloOrigem - 1 + deslocamento) % diasCiclo) + diasCiclo) % diasCiclo;
  return resto + 1;
}

function paraIsoData(ano: number, mes: number, dia: number): string {
  return `${String(ano).padStart(4, "0")}-${String(mes).padStart(2, "0")}-${String(dia).padStart(2, "0")}`;
}

/**
 * Data de hoje em ISO (`AAAA-MM-DD`), usando componentes LOCAIS de `Date`
 * (nunca `toISOString`, que converte para UTC e pode deslocar o dia perto da
 * meia-noite) — mesmo cuidado que `seletor-de-periodo.tsx` (F9a) e
 * `paineis/apuracao/utilitarios.ts` (A3) já tomam para o mesmo problema.
 * Parâmetro injetável para teste determinístico.
 */
export function hojeIso(agora: Date = new Date()): string {
  return paraIsoData(agora.getFullYear(), agora.getMonth() + 1, agora.getDate());
}

/** Primeiro e último dia do mês de `agora`, em ISO — período padrão da grade de escala (T13). */
export function mesAtualComoPeriodo(agora: Date = new Date()): { inicio: string; fim: string } {
  const ano = agora.getFullYear();
  const mes = agora.getMonth() + 1;
  const ultimoDia = new Date(ano, mes, 0).getDate();
  return { inicio: paraIsoData(ano, mes, 1), fim: paraIsoData(ano, mes, ultimoDia) };
}

/** Primeiro e último dia do mês ANTERIOR ao de `agora`, em ISO — atalho da grade de escala (T13). */
export function mesAnteriorComoPeriodo(agora: Date = new Date()): { inicio: string; fim: string } {
  const anterior = new Date(agora.getFullYear(), agora.getMonth() - 1, 1);
  return mesAtualComoPeriodo(anterior);
}
