import { MAXIMO_DE_TENTATIVAS, JANELA_DO_DESAFIO_MS, type TipoDeDesafio } from "@/lib/deteccao/prova-de-vida";
import type { SituacaoDaProvaDeVida } from "@/ganchos/use-prova-de-vida";

/**
 * Desafio de prova de vida — apresentação de T7 do PCF F08.
 *
 * Puramente apresentacional (props fixas — a detecção em si é
 * `useProvaDeVida`, T7). Cobre os estados "carregando modelo", "desafio
 * ativo" (com contador regressivo) e "reprovado nesta tentativa" (antes de
 * uma nova tentativa começar). Os estados finais (aprovado/reprovado
 * definitivo) são responsabilidade de `ConfirmacaoDeRegistro`.
 *
 * Único lugar onde este componente é usado é dentro do painel escuro fixo de
 * captura (`FluxoDeRegistro`, que envolve a árvore em `data-tema="escuro"` —
 * ver comentário lá). Por isso usa normalmente os tokens semânticos
 * `texto-*`/`estado-*`: dentro dessa subárvore eles já resolvem para o par
 * escuro, independente do tema real escolhido pelo usuário.
 */
export interface DesafioDeProvaDeVidaProps {
  situacao: Extract<
    SituacaoDaProvaDeVida,
    "carregando_modelo" | "em_andamento" | "reprovado_tentativa"
  >;
  desafio: TipoDeDesafio | null;
  tentativa: number;
  segundosRestantes: number;
}

const INSTRUCAO_POR_DESAFIO: Record<TipoDeDesafio, string> = {
  piscar_duas_vezes: "Pisque duas vezes",
  virar_esquerda: "Vire o rosto para a esquerda",
  virar_direita: "Vire o rosto para a direita",
};

export function DesafioDeProvaDeVida({
  situacao,
  desafio,
  tentativa,
  segundosRestantes,
}: DesafioDeProvaDeVidaProps) {
  if (situacao === "carregando_modelo") {
    return (
      <div
        role="status"
        aria-live="polite"
        className="flex flex-col items-center gap-[var(--espacamento-2)]"
      >
        <div className="h-1.5 w-full animate-pulse rounded-pleno bg-texto-primario/15" />
        <p className="text-2xs text-texto-primario/70">Carregando verificação de presença…</p>
      </div>
    );
  }

  if (situacao === "reprovado_tentativa") {
    return (
      <div aria-live="polite" className="flex flex-col items-center gap-1 text-center">
        <p className="text-md font-semibold text-estado-atencao-icone">Não foi dessa vez</p>
        <p className="text-2xs text-texto-primario/70">Preparando uma nova tentativa…</p>
      </div>
    );
  }

  const instrucao = desafio ? INSTRUCAO_POR_DESAFIO[desafio] : "";
  const totalDeSegundos = Math.ceil(JANELA_DO_DESAFIO_MS / 1000);
  const progresso = totalDeSegundos > 0 ? (segundosRestantes / totalDeSegundos) * 100 : 0;

  return (
    <div className="flex w-full flex-col items-center gap-3 text-center">
      <div className="flex items-center gap-2">
        <p aria-live="polite" className="text-lg font-semibold text-balance text-texto-primario">
          {instrucao}
        </p>
        <span aria-hidden="true" className="font-mono text-sm font-semibold tabular-nums text-texto-primario/70">
          {segundosRestantes}
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-pleno bg-texto-primario/15">
        <div
          className="h-full rounded-pleno bg-estado-sucesso-icone transition-[width] duration-300 ease-linear"
          style={{ width: `${progresso}%` }}
        />
      </div>
      <p className="text-2xs text-texto-primario/60">
        Tentativa {tentativa} de {MAXIMO_DE_TENTATIVAS}
      </p>
    </div>
  );
}
