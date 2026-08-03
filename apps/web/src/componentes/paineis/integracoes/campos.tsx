"use client";

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

import type { EventoPublico } from "./eventos-publicos";

/**
 * Campos de formulário desta seção (webhooks) — compõem os primitivos
 * congelados da F9a (`Entrada`, `Selecao`, `CaixaDeSelecao`) com rótulo e
 * mensagem de erro. Cópia local do mesmo padrão independente em
 * `paineis/cadastros/_campos/campos.tsx` (F9a/A2) e
 * `paineis/escalas/campos.tsx` (F9a/A3) — nenhum dos dois é ownership desta
 * seção, então não é importado de lá.
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

interface CampoListaDeEventosProps<T extends FieldValues> {
  name: Path<T>;
  control: Control<T>;
  opcoes: EventoPublico[];
  erro?: string | undefined;
}

/**
 * Grade de caixas de seleção agrupada por domínio — controla um campo
 * `string[]` (códigos de `events.yaml`), não um booleano isolado como
 * `CampoCheckbox` de outras seções. Só eventos com `webhookPublico: true`
 * entram em `opcoes` (`./eventos-publicos.ts`); o servidor recusa qualquer
 * outro com `PONTO-WEBH-003`.
 */
export function CampoListaDeEventos<T extends FieldValues>({
  name,
  control,
  opcoes,
  erro,
}: CampoListaDeEventosProps<T>) {
  const grupos = agruparPorGrupo(opcoes);
  return (
    <div className="flex flex-col gap-1">
      <Rotulo>Eventos assinados *</Rotulo>
      <Controller
        name={name}
        control={control}
        render={({ field }) => {
          const selecionados: string[] = Array.isArray(field.value) ? field.value : [];
          function alternar(codigo: string, marcado: boolean) {
            const proximo = marcado
              ? [...selecionados, codigo]
              : selecionados.filter((c) => c !== codigo);
            field.onChange(proximo);
          }
          return (
            <div
              className="flex max-h-64 flex-col gap-3 overflow-y-auto rounded-medio border border-borda-padrao p-3"
              aria-invalid={Boolean(erro)}
            >
              {Object.entries(grupos).map(([grupo, itens]) => (
                <div key={grupo} className="flex flex-col gap-1">
                  <p className="estilo-legenda text-texto-terciario">{grupo}</p>
                  <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
                    {itens.map((evento) => {
                      const id = `evento-${evento.codigo}`;
                      const marcado = selecionados.includes(evento.codigo);
                      return (
                        <label
                          key={evento.codigo}
                          htmlFor={id}
                          className="flex cursor-pointer items-center gap-2"
                        >
                          <CaixaDeSelecao
                            id={id}
                            checked={marcado}
                            onCheckedChange={(valor) => {
                              alternar(evento.codigo, valor === true);
                            }}
                          />
                          <span className="estilo-corpo text-texto-primario">{evento.rotulo}</span>
                          <span className="estilo-legenda text-texto-terciario">
                            ({evento.codigo})
                          </span>
                        </label>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          );
        }}
      />
      <MensagemDeErro>{erro}</MensagemDeErro>
    </div>
  );
}

function agruparPorGrupo(opcoes: EventoPublico[]): Record<string, EventoPublico[]> {
  const mapa: Record<string, EventoPublico[]> = {};
  for (const opcao of opcoes) {
    const lista = mapa[opcao.grupo] ?? [];
    lista.push(opcao);
    mapa[opcao.grupo] = lista;
  }
  return mapa;
}
