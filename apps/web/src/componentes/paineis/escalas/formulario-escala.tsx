"use client";

import { useEffect } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { z } from "zod";

import { Botao } from "@/componentes/ui/button";
import {
  Dialogo,
  DialogoCabecalho,
  DialogoConteudo,
  DialogoDescricao,
  DialogoRodape,
  DialogoTitulo,
} from "@/componentes/ui/dialog";
import { MensagemDeErro } from "@/componentes/ui/mensagem-de-erro";
import { useAtualizarEscala, useCriarEscala } from "@/ganchos/use-escalas";
import { useTurnos } from "@/ganchos/use-turnos";
import type { Esquema } from "@/lib/api";

import { CampoCheckbox, CampoSelecao, CampoTexto, type OpcaoDeSelecao } from "./campos";
import { nomeExibidoDaEmpresa } from "./dados-compartilhados";
import { mensagemDeErroApi } from "./mensagem-de-erro-api";
import { resolverZod } from "./resolver-zod";

const TIPOS_DE_ESCALA: OpcaoDeSelecao[] = [
  { valor: "5x2", rotulo: "5x2 (diasCiclo 7)" },
  { valor: "6x1", rotulo: "6x1 (diasCiclo 7)" },
  { valor: "4x2", rotulo: "4x2 (diasCiclo 6)" },
  { valor: "12x36", rotulo: "12x36 (diasCiclo 2)" },
  { valor: "espanhola", rotulo: "Espanhola" },
  { valor: "rotativa", rotulo: "Rotativa" },
  { valor: "personalizada", rotulo: "Personalizada" },
];

const TIPOS_DE_DIA_DO_CICLO: OpcaoDeSelecao[] = [
  { valor: "trabalho", rotulo: "Trabalho" },
  { valor: "folga", rotulo: "Folga" },
  { valor: "dsr", rotulo: "DSR" },
  { valor: "compensado", rotulo: "Compensado" },
];

const ESQUEMA_CICLO = z
  .object({
    turnoId: z.string().optional(),
    tipoDia: z.enum(["trabalho", "folga", "dsr", "compensado"], {
      message: "Selecione a natureza do dia.",
    }),
    cargaMinutos: z.coerce.number().int().min(0).max(1440),
  })
  .refine((valor) => valor.tipoDia !== "trabalho" || Boolean(valor.turnoId), {
    message: "Selecione o turno para um dia de trabalho.",
    path: ["turnoId"],
  });

const ESQUEMA = z
  .object({
    empresaId: z.string().min(1, "Selecione a empresa."),
    codigo: z.string().min(1, "Informe o código da escala."),
    nome: z.string().min(1, "Informe o nome da escala."),
    tipo: z.enum(["5x2", "6x1", "4x2", "12x36", "espanhola", "rotativa", "personalizada"], {
      message: "Selecione o padrão da escala.",
    }),
    diasCiclo: z.coerce.number().int().min(1).max(366),
    dataReferencia: z.string().min(1, "Informe a data-âncora do ciclo."),
    ativo: z.boolean(),
    ciclos: z.array(ESQUEMA_CICLO).min(1, "Adicione ao menos uma posição do ciclo."),
  })
  .refine((valor) => valor.ciclos.length === valor.diasCiclo, {
    message: "O número de posições do ciclo precisa ser igual a diasCiclo.",
    path: ["ciclos"],
  });
type FormularioDeEscala = z.infer<typeof ESQUEMA>;

function valoresIniciais(
  escala: Esquema<"Escala"> | null | undefined,
  empresaIdPadrao: string | undefined,
): FormularioDeEscala {
  return {
    empresaId: escala?.empresaId ?? empresaIdPadrao ?? "",
    codigo: escala?.codigo ?? "",
    nome: escala?.nome ?? "",
    tipo: escala?.tipo ?? "5x2",
    diasCiclo: escala?.diasCiclo ?? 7,
    dataReferencia: escala?.dataReferencia ?? "",
    ativo: escala?.ativo ?? true,
    ciclos: (escala?.ciclos ?? []).map((ciclo) => ({
      turnoId: ciclo.turnoId ?? undefined,
      tipoDia: ciclo.tipoDia ?? "trabalho",
      cargaMinutos: ciclo.cargaMinutos ?? 0,
    })),
  };
}

export interface FormularioEscalaProps {
  aberto: boolean;
  aoMudarAberto: (aberto: boolean) => void;
  /** Presente = editar; ausente = criar. */
  escala?: Esquema<"Escala"> | null;
  empresas: Esquema<"Empresa">[];
  empresaIdPadrao?: string | undefined;
}

/**
 * Formulário de criação/edição de escala (T12), com editor de `ciclos`
 * (`EscalaCiclo[]`) — uma posição por linha, `posicao` sempre `índice + 1`
 * (o próprio índice na lista, nunca um campo editável separado, evita buraco
 * ou duplicidade de posição). Não oferece `jornadaId`: mesma restrição de
 * escopo do formulário de turno (só consome `resolverJornadaDoDia`/
 * `listarJornadasVinculo`/`atribuirJornadaVinculo`, não lista jornadas).
 */
export function FormularioEscala({
  aberto,
  aoMudarAberto,
  escala,
  empresas,
  empresaIdPadrao,
}: FormularioEscalaProps) {
  const criar = useCriarEscala();
  const atualizar = useAtualizarEscala();
  const emEdicao = Boolean(escala);
  const mutacao = emEdicao ? atualizar : criar;

  const opcoesDeEmpresa: OpcaoDeSelecao[] = empresas.map((empresa) => ({
    valor: empresa.id ?? "",
    rotulo: nomeExibidoDaEmpresa(empresa),
  }));

  const formulario = useForm<FormularioDeEscala>({
    resolver: resolverZod(ESQUEMA),
    defaultValues: valoresIniciais(escala, empresaIdPadrao),
  });
  const arrayDeCiclos = useFieldArray({ control: formulario.control, name: "ciclos" });

  const empresaSelecionada = formulario.watch("empresaId");
  const turnos = useTurnos({ empresaId: empresaSelecionada || undefined, ativo: true });
  const opcoesDeTurno: OpcaoDeSelecao[] = (turnos.data?.dados ?? []).map((turno) => ({
    valor: turno.id ?? "",
    rotulo: turno.nome ?? turno.codigo ?? "",
  }));

  useEffect(() => {
    if (!aberto) return;
    formulario.reset(valoresIniciais(escala, empresaIdPadrao));
    mutacao.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aberto, escala]);

  async function aoSubmeter(valores: FormularioDeEscala) {
    const ciclos: Esquema<"EscalaCiclo">[] = valores.ciclos.map((ciclo, indice) => ({
      posicao: indice + 1,
      tipoDia: ciclo.tipoDia,
      cargaMinutos: ciclo.cargaMinutos,
      ...(ciclo.turnoId ? { turnoId: ciclo.turnoId } : {}),
    }));
    const corpo = {
      empresaId: valores.empresaId,
      codigo: valores.codigo,
      nome: valores.nome,
      tipo: valores.tipo,
      diasCiclo: valores.diasCiclo,
      dataReferencia: valores.dataReferencia,
      ativo: valores.ativo,
      ciclos,
    };
    try {
      if (emEdicao && escala?.id) {
        await atualizar.mutateAsync({ escalaId: escala.id, corpo });
      } else {
        await criar.mutateAsync(corpo);
      }
      aoMudarAberto(false);
    } catch {
      // Erro exibido abaixo via `mutacao.isError`.
    }
  }

  const erroCiclos = formulario.formState.errors.ciclos;
  const mensagemErroCiclos =
    typeof erroCiclos?.message === "string" ? erroCiclos.message : undefined;

  return (
    <Dialogo open={aberto} onOpenChange={aoMudarAberto}>
      <DialogoConteudo className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogoCabecalho>
          <DialogoTitulo>{emEdicao ? "Editar escala" : "Nova escala"}</DialogoTitulo>
          <DialogoDescricao>
            Padrão cíclico de trabalho e folga. O ciclo se repete a partir de dataReferencia por
            aritmética modular — nada de calendário materializado.
          </DialogoDescricao>
        </DialogoCabecalho>

        <form
          className="flex flex-col gap-4"
          noValidate
          onSubmit={(evento) => {
            void formulario.handleSubmit(aoSubmeter)(evento);
          }}
        >
          <CampoSelecao<FormularioDeEscala>
            id="escala-empresa"
            rotulo="Empresa"
            obrigatorio
            name="empresaId"
            control={formulario.control}
            opcoes={opcoesDeEmpresa}
            erro={formulario.formState.errors.empresaId?.message}
          />

          <div className="grid grid-cols-2 gap-4">
            <CampoTexto
              id="escala-codigo"
              rotulo="Código"
              obrigatorio
              erro={formulario.formState.errors.codigo?.message}
              {...formulario.register("codigo")}
            />
            <CampoTexto
              id="escala-nome"
              rotulo="Nome"
              obrigatorio
              erro={formulario.formState.errors.nome?.message}
              {...formulario.register("nome")}
            />
          </div>

          <div className="grid grid-cols-3 gap-4">
            <CampoSelecao<FormularioDeEscala>
              id="escala-tipo"
              rotulo="Padrão"
              obrigatorio
              name="tipo"
              control={formulario.control}
              opcoes={TIPOS_DE_ESCALA}
              erro={formulario.formState.errors.tipo?.message}
            />
            <CampoTexto
              id="escala-dias-ciclo"
              rotulo="Dias do ciclo"
              obrigatorio
              type="number"
              min={1}
              max={366}
              erro={formulario.formState.errors.diasCiclo?.message}
              {...formulario.register("diasCiclo")}
            />
            <CampoTexto
              id="escala-data-referencia"
              rotulo="Data-âncora (posição 1)"
              obrigatorio
              type="date"
              erro={formulario.formState.errors.dataReferencia?.message}
              {...formulario.register("dataReferencia")}
            />
          </div>

          <CampoCheckbox<FormularioDeEscala>
            id="escala-ativo"
            rotulo="Escala ativa"
            name="ativo"
            control={formulario.control}
          />

          <div className="flex flex-col gap-2 rounded-medio border border-borda-sutil p-3">
            <div className="flex items-center justify-between">
              <p className="estilo-rotulo text-texto-primario">
                Posições do ciclo ({arrayDeCiclos.fields.length} de{" "}
                {formulario.watch("diasCiclo") || 0})
              </p>
              <Botao
                type="button"
                variant="secundaria"
                tamanho="compacto"
                onClick={() => {
                  arrayDeCiclos.append({ tipoDia: "folga", cargaMinutos: 0 });
                }}
              >
                Adicionar posição
              </Botao>
            </div>

            {arrayDeCiclos.fields.map((campo, indice) => (
              <div
                key={campo.id}
                className="grid grid-cols-[2rem_1fr_1fr_6rem_2.5rem] items-end gap-2"
              >
                <p className="estilo-tabular pb-2 text-texto-secundario">{indice + 1}</p>
                <CampoSelecao<FormularioDeEscala>
                  id={`escala-ciclo-${indice}-tipo`}
                  rotulo="Tipo do dia"
                  name={`ciclos.${indice}.tipoDia`}
                  control={formulario.control}
                  opcoes={TIPOS_DE_DIA_DO_CICLO}
                  erro={formulario.formState.errors.ciclos?.[indice]?.tipoDia?.message}
                />
                <CampoSelecao<FormularioDeEscala>
                  id={`escala-ciclo-${indice}-turno`}
                  rotulo="Turno"
                  name={`ciclos.${indice}.turnoId`}
                  control={formulario.control}
                  opcoes={opcoesDeTurno}
                  erro={formulario.formState.errors.ciclos?.[indice]?.turnoId?.message}
                />
                <CampoTexto
                  id={`escala-ciclo-${indice}-carga`}
                  rotulo="Carga (min)"
                  type="number"
                  min={0}
                  max={1440}
                  erro={formulario.formState.errors.ciclos?.[indice]?.cargaMinutos?.message}
                  {...formulario.register(`ciclos.${indice}.cargaMinutos`)}
                />
                <Botao
                  type="button"
                  variant="sutil"
                  tamanho="icone"
                  aria-label={`Remover posição ${indice + 1}`}
                  onClick={() => {
                    arrayDeCiclos.remove(indice);
                  }}
                >
                  ×
                </Botao>
              </div>
            ))}
            <MensagemDeErro>{mensagemErroCiclos}</MensagemDeErro>
          </div>

          {mutacao.isError ? (
            <MensagemDeErro role="alert">{mensagemDeErroApi(mutacao.error)}</MensagemDeErro>
          ) : null}

          <DialogoRodape>
            <Botao
              type="button"
              variant="secundaria"
              onClick={() => {
                aoMudarAberto(false);
              }}
            >
              Cancelar
            </Botao>
            <Botao type="submit" disabled={mutacao.isPending}>
              {mutacao.isPending ? "Salvando…" : "Salvar escala"}
            </Botao>
          </DialogoRodape>
        </form>
      </DialogoConteudo>
    </Dialogo>
  );
}
