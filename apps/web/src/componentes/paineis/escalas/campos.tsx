"use client";

import type { ReactNode } from "react";
import { Controller, type Control, type FieldValues, type Path } from "react-hook-form";

import { CaixaDeSelecao } from "@/componentes/ui/checkbox";
import { Entrada } from "@/componentes/ui/input";
import { Rotulo } from "@/componentes/ui/label";
import { MensagemDeErro } from "@/componentes/ui/mensagem-de-erro";
import {
  Selecao,
  SelecaoConteudo,
  SelecaoGatilho,
  SelecaoItem,
  SelecaoValor,
} from "@/componentes/ui/select";

/**
 * Campos de formulário desta seção (turnos, escalas, atribuições) — compõem
 * os primitivos congelados da F9a (`Entrada`, `Selecao`, `CaixaDeSelecao`)
 * com rótulo e mensagem de erro. Cópia local do mesmo padrão independente em
 * `paineis/cadastros/_campos/campos.tsx` (A2) — não é ownership desta seção,
 * então não é importado de lá.
 */

interface CampoBaseProps {
  id: string;
  rotulo: string;
  erro?: string | undefined;
  obrigatorio?: boolean;
}

export function CampoTexto({
  id,
  rotulo,
  erro,
  obrigatorio,
  ...props
}: CampoBaseProps & React.ComponentProps<typeof Entrada>) {
  return (
    <div className="flex flex-col gap-1">
      <Rotulo htmlFor={id}>
        {rotulo}
        {obrigatorio ? " *" : ""}
      </Rotulo>
      <Entrada id={id} aria-invalid={Boolean(erro)} {...props} />
      <MensagemDeErro>{erro}</MensagemDeErro>
    </div>
  );
}

export interface OpcaoDeSelecao {
  valor: string;
  rotulo: string;
}

interface CampoSelecaoProps<T extends FieldValues> extends CampoBaseProps {
  name: Path<T>;
  control: Control<T>;
  opcoes: OpcaoDeSelecao[];
  placeholder?: string;
}

/** Seleção controlada por `react-hook-form` (Radix `Selecao` não é um `<input>` nativo). */
export function CampoSelecao<T extends FieldValues>({
  id,
  rotulo,
  erro,
  obrigatorio,
  name,
  control,
  opcoes,
  placeholder = "Selecione…",
}: CampoSelecaoProps<T>) {
  return (
    <div className="flex flex-col gap-1">
      <Rotulo htmlFor={id}>
        {rotulo}
        {obrigatorio ? " *" : ""}
      </Rotulo>
      <Controller
        name={name}
        control={control}
        render={({ field }) => (
          <Selecao
            {...(typeof field.value === "string" && field.value ? { value: field.value } : {})}
            onValueChange={field.onChange}
          >
            <SelecaoGatilho id={id} aria-invalid={Boolean(erro)} className="w-full">
              <SelecaoValor placeholder={placeholder} />
            </SelecaoGatilho>
            <SelecaoConteudo>
              {opcoes.map((opcao) => (
                <SelecaoItem key={opcao.valor} value={opcao.valor}>
                  {opcao.rotulo}
                </SelecaoItem>
              ))}
            </SelecaoConteudo>
          </Selecao>
        )}
      />
      <MensagemDeErro>{erro}</MensagemDeErro>
    </div>
  );
}

interface CampoCheckboxProps<T extends FieldValues> {
  id: string;
  rotulo: ReactNode;
  name: Path<T>;
  control: Control<T>;
}

export function CampoCheckbox<T extends FieldValues>({
  id,
  rotulo,
  name,
  control,
}: CampoCheckboxProps<T>) {
  return (
    <Controller
      name={name}
      control={control}
      render={({ field }) => (
        <label htmlFor={id} className="flex cursor-pointer items-center gap-2">
          <CaixaDeSelecao
            id={id}
            checked={Boolean(field.value)}
            onCheckedChange={(valor) => {
              field.onChange(valor === true);
            }}
          />
          <span className="estilo-corpo text-texto-primario">{rotulo}</span>
        </label>
      )}
    />
  );
}
