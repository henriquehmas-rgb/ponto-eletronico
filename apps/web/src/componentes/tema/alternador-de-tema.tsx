"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import type { ComponentType } from "react";

import { cn } from "@/lib/utils";

import { PREFERENCIAS, ROTULO_DA_PREFERENCIA, type PreferenciaDeTema } from "./preferencia-de-tema";
import { useTema } from "./provedor-de-tema";

const ICONE: Record<PreferenciaDeTema, ComponentType<{ className?: string }>> = {
  claro: Sun,
  escuro: Moon,
  sistema: Monitor,
};

/**
 * Alternador de tema: tres opcoes explicitas em um grupo de radio.
 *
 * Grupo de radio, e nao um botao que cicla, porque "seguir o sistema" e um
 * estado que o usuario precisa conseguir VER — num botao de ciclo ele so
 * descobre onde esta depois de clicar.
 */
export function AlternadorDeTema({ className }: { className?: string }) {
  const { preferencia, definirPreferencia } = useTema();

  return (
    <div
      role="radiogroup"
      aria-label="Tema da interface"
      className={cn(
        "inline-flex items-center gap-1 rounded-full border border-borda-sutil bg-fundo-superficie p-1",
        className,
      )}
    >
      {PREFERENCIAS.map((opcao) => {
        const Icone = ICONE[opcao];
        const ativa = preferencia === opcao;
        return (
          <button
            key={opcao}
            type="button"
            role="radio"
            aria-checked={ativa}
            title={ROTULO_DA_PREFERENCIA[opcao]}
            onClick={() => {
              definirPreferencia(opcao);
            }}
            className={cn(
              "inline-flex size-8 items-center justify-center rounded-full",
              "transition-colors duration-rapida ease-padrao",
              "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-acao-anel-foco",
              ativa
                ? "bg-acao-primaria-fundo text-acao-primaria-texto"
                : "text-texto-terciario hover:bg-fundo-sutil hover:text-texto-primario",
            )}
          >
            <Icone className="size-4" />
            <span className="sr-only">{ROTULO_DA_PREFERENCIA[opcao]}</span>
          </button>
        );
      })}
    </div>
  );
}
