import { Alerta, AlertaDescricao, AlertaTitulo } from "@/componentes/ui/alert";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { MAXIMO_DE_TENTATIVAS, type TipoDeDesafio } from "@/lib/deteccao/prova-de-vida";
import type { SituacaoDaProvaDeVida } from "@/ganchos/use-prova-de-vida";

/**
 * Desafio de prova de vida — apresentação de T7 do PCF F08.
 *
 * Puramente apresentacional (props fixas — a detecção em si é
 * `useProvaDeVida`, T7). Cobre os estados "carregando modelo", "desafio
 * ativo" (com contador regressivo) e "reprovado nesta tentativa" (antes de
 * uma nova tentativa começar). Os estados finais (aprovado/reprovado
 * definitivo) são responsabilidade de `ConfirmacaoDeRegistro`.
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
        <Esqueleto className="h-[var(--espacamento-8)] w-full" />
        <p className="estilo-legenda text-texto-secundario">Carregando verificação de presença…</p>
      </div>
    );
  }

  if (situacao === "reprovado_tentativa") {
    return (
      <Alerta variant="atencao" aria-live="polite">
        <AlertaTitulo>Não foi dessa vez</AlertaTitulo>
        <AlertaDescricao>Preparando uma nova tentativa…</AlertaDescricao>
      </Alerta>
    );
  }

  const instrucao = desafio ? INSTRUCAO_POR_DESAFIO[desafio] : "";

  return (
    <div className="flex flex-col items-center gap-[var(--espacamento-3)] text-center">
      <p aria-live="polite" className="estilo-titulo-secao">
        {instrucao}
      </p>
      <p aria-hidden="true" className="estilo-numero-destaque text-texto-primario">
        {segundosRestantes}
      </p>
      <p className="estilo-legenda text-texto-secundario">
        Tentativa {tentativa} de {MAXIMO_DE_TENTATIVAS}
      </p>
    </div>
  );
}
