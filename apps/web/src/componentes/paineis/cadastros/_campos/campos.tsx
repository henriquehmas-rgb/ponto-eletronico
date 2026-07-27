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
import { AreaDeTexto } from "@/componentes/ui/textarea";

/**
 * Campos de formulário desta área (`paineis/cadastros`) — envolvem os
 * primitivos congelados da F9a (`Entrada`, `Selecao`, `CaixaDeSelecao`,
 * `AreaDeTexto`) com rótulo e mensagem de erro, sem redefinir nenhum token.
 * Não são um primitivo novo do design system — são composição do que já
 * existe, para reduzir repetição nos ~10 formulários desta fase.
 */

interface CampoBaseProps {
  id: string;
  rotulo: string;
  erro?: string | undefined;
  obrigatorio?: boolean;
  dica?: string;
}

export function CampoTexto({
  id,
  rotulo,
  erro,
  obrigatorio,
  dica,
  ...props
}: CampoBaseProps & React.ComponentProps<typeof Entrada>) {
  return (
    <div className="flex flex-col gap-1">
      <Rotulo htmlFor={id}>
        {rotulo}
        {obrigatorio ? " *" : ""}
      </Rotulo>
      <Entrada id={id} aria-invalid={Boolean(erro)} {...props} />
      {dica && !erro ? <p className="estilo-legenda text-texto-terciario">{dica}</p> : null}
      <MensagemDeErro>{erro}</MensagemDeErro>
    </div>
  );
}

export function CampoTextoArea({
  id,
  rotulo,
  erro,
  obrigatorio,
  ...props
}: CampoBaseProps & React.ComponentProps<typeof AreaDeTexto>) {
  return (
    <div className="flex flex-col gap-1">
      <Rotulo htmlFor={id}>
        {rotulo}
        {obrigatorio ? " *" : ""}
      </Rotulo>
      <AreaDeTexto id={id} aria-invalid={Boolean(erro)} {...props} />
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
  permitirVazio?: boolean;
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
  permitirVazio = false,
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
            onValueChange={(valor) => {
              field.onChange(permitirVazio && valor === "__vazio__" ? "" : valor);
            }}
          >
            <SelecaoGatilho id={id} aria-invalid={Boolean(erro)} className="w-full">
              <SelecaoValor placeholder={placeholder} />
            </SelecaoGatilho>
            <SelecaoConteudo>
              {permitirVazio ? <SelecaoItem value="__vazio__">— nenhum —</SelecaoItem> : null}
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
