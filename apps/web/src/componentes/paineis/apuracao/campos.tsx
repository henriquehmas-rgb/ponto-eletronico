"use client";

import type { ReactNode } from "react";
import { Controller, type Control, type FieldValues, type Path } from "react-hook-form";

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
 * Campos de formulário desta seção (`paineis/apuracao`) — mesma composição
 * que `paineis/cadastros/_campos/campos.tsx` (A2) sobre os primitivos
 * congelados da F9a (`Entrada`, `Selecao`, `AreaDeTexto`), mas copiada
 * localmente: `_campos/campos.tsx` é ownership exclusivo de A2 (§5 do PCF),
 * então o formulário de tratamento (T10) não importa de lá — evita acoplar
 * duas seções independentes por um arquivo compartilhado que nenhuma delas
 * pode editar sem esbarrar na outra. Mesmo espírito da cópia local de
 * `paramsSemUndefined` em `utilitarios.ts`.
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
  dica,
  ...props
}: CampoBaseProps & React.ComponentProps<typeof AreaDeTexto>) {
  return (
    <div className="flex flex-col gap-1">
      <Rotulo htmlFor={id}>
        {rotulo}
        {obrigatorio ? " *" : ""}
      </Rotulo>
      <AreaDeTexto id={id} aria-invalid={Boolean(erro)} {...props} />
      {dica && !erro ? <p className="estilo-legenda text-texto-terciario">{dica}</p> : null}
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

interface SeletorSimplesProps {
  id: string;
  rotulo: string;
  valor: string;
  aoMudar: (valor: string) => void;
  opcoes: OpcaoDeSelecao[];
  placeholder?: string;
  rotuloTodos?: string;
}

/**
 * Seleção NÃO controlada por `react-hook-form` — usada pelos filtros da
 * grade (T9), que vivem fora de qualquer `<form>`. `rotuloTodos` (padrão
 * "Todos") sempre limpa o filtro (`valor: ""`), nunca envia um UUID vazio à
 * API.
 */
export function SeletorSimples({
  id,
  rotulo,
  valor,
  aoMudar,
  opcoes,
  placeholder = "Selecione…",
  rotuloTodos = "Todos",
}: SeletorSimplesProps) {
  return (
    <div className="flex flex-col gap-1">
      <Rotulo htmlFor={id}>{rotulo}</Rotulo>
      <Selecao
        value={valor || "__todos__"}
        onValueChange={(novoValor) => {
          aoMudar(novoValor === "__todos__" ? "" : novoValor);
        }}
      >
        <SelecaoGatilho id={id} tamanho="compacto" className="w-full min-w-40">
          <SelecaoValor placeholder={placeholder} />
        </SelecaoGatilho>
        <SelecaoConteudo>
          <SelecaoItem value="__todos__">{rotuloTodos}</SelecaoItem>
          {opcoes.map((opcao) => (
            <SelecaoItem key={opcao.valor} value={opcao.valor}>
              {opcao.rotulo}
            </SelecaoItem>
          ))}
        </SelecaoConteudo>
      </Selecao>
    </div>
  );
}

interface CampoCheckboxSimplesProps {
  id: string;
  rotulo: ReactNode;
  marcado: boolean;
  aoMudar: (marcado: boolean) => void;
}

export function CampoCheckboxSimples({ id, rotulo, marcado, aoMudar }: CampoCheckboxSimplesProps) {
  return (
    <label htmlFor={id} className="flex cursor-pointer items-center gap-2">
      <input
        id={id}
        type="checkbox"
        checked={marcado}
        onChange={(evento) => {
          aoMudar(evento.target.checked);
        }}
      />
      <span className="estilo-corpo text-texto-primario">{rotulo}</span>
    </label>
  );
}
