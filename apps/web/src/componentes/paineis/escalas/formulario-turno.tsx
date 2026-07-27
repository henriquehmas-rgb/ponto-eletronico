"use client";

import { useEffect } from "react";
import { useForm } from "react-hook-form";
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
import { useAtualizarTurno, useCriarTurno } from "@/ganchos/use-turnos";
import type { Esquema } from "@/lib/api";

import { CampoCheckbox, CampoSelecao, CampoTexto, type OpcaoDeSelecao } from "./campos";
import { nomeExibidoDaEmpresa } from "./dados-compartilhados";
import { mensagemDeErroApi } from "./mensagem-de-erro-api";
import { resolverZod } from "./resolver-zod";

const TIPOS_DE_TURNO: OpcaoDeSelecao[] = [
  { valor: "diurno", rotulo: "Diurno" },
  { valor: "noturno", rotulo: "Noturno" },
  { valor: "misto", rotulo: "Misto" },
  { valor: "folga", rotulo: "Folga" },
  { valor: "dsr", rotulo: "DSR" },
  { valor: "sobreaviso", rotulo: "Sobreaviso" },
  { valor: "prontidao", rotulo: "Prontidão" },
];

const ESQUEMA = z.object({
  empresaId: z.string().min(1, "Selecione a empresa."),
  codigo: z.string().min(1, "Informe o código do turno."),
  nome: z.string().min(1, "Informe o nome do turno."),
  tipo: z.enum(["diurno", "noturno", "misto", "folga", "dsr", "sobreaviso", "prontidao"], {
    message: "Selecione a natureza do turno.",
  }),
  cor: z.string().regex(/^#[0-9A-Fa-f]{6}$/, "Informe uma cor hexadecimal válida (ex.: #1E293B)."),
  ativo: z.boolean(),
});
type FormularioDeTurno = z.infer<typeof ESQUEMA>;

const COR_PADRAO = "#2563EB";

export interface FormularioTurnoProps {
  aberto: boolean;
  aoMudarAberto: (aberto: boolean) => void;
  /** Presente = editar; ausente = criar. */
  turno?: Esquema<"Turno"> | null;
  empresas: Esquema<"Empresa">[];
  empresaIdPadrao?: string | undefined;
}

function valoresIniciais(
  turno: Esquema<"Turno"> | null | undefined,
  empresaIdPadrao: string | undefined,
): FormularioDeTurno {
  return {
    empresaId: turno?.empresaId ?? empresaIdPadrao ?? "",
    codigo: turno?.codigo ?? "",
    nome: turno?.nome ?? "",
    tipo: turno?.tipo ?? "diurno",
    cor: turno?.cor ?? COR_PADRAO,
    ativo: turno?.ativo ?? true,
  };
}

/**
 * Formulário de criação/edição de turno (T12). Não oferece `horarioId`: esta
 * fase só CONSOME `jornadas`/`horarios` pelas três operações citadas no PCF
 * (`listarJornadasVinculo`, `atribuirJornadaVinculo`, `resolverJornadaDoDia`)
 * — não há leitura de horários cadastrados sancionada aqui, então o turno
 * fica sem horário materializado até uma fase futura ligar os dois.
 */
export function FormularioTurno({
  aberto,
  aoMudarAberto,
  turno,
  empresas,
  empresaIdPadrao,
}: FormularioTurnoProps) {
  const criar = useCriarTurno();
  const atualizar = useAtualizarTurno();
  const emEdicao = Boolean(turno);
  const mutacao = emEdicao ? atualizar : criar;

  const opcoesDeEmpresa: OpcaoDeSelecao[] = empresas.map((empresa) => ({
    valor: empresa.id ?? "",
    rotulo: nomeExibidoDaEmpresa(empresa),
  }));

  const formulario = useForm<FormularioDeTurno>({
    resolver: resolverZod(ESQUEMA),
    defaultValues: valoresIniciais(turno, empresaIdPadrao),
  });

  useEffect(() => {
    if (!aberto) return;
    formulario.reset(valoresIniciais(turno, empresaIdPadrao));
    mutacao.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aberto, turno]);

  async function aoSubmeter(valores: FormularioDeTurno) {
    try {
      if (emEdicao && turno?.id) {
        await atualizar.mutateAsync({ turnoId: turno.id, corpo: valores });
      } else {
        await criar.mutateAsync(valores);
      }
      aoMudarAberto(false);
    } catch {
      // Erro exibido abaixo via `mutacao.isError` — nada mais a fazer aqui.
    }
  }

  const corAtual = formulario.watch("cor");
  const corValida = /^#[0-9A-Fa-f]{6}$/.test(corAtual);

  return (
    <Dialogo open={aberto} onOpenChange={aoMudarAberto}>
      <DialogoConteudo>
        <DialogoCabecalho>
          <DialogoTitulo>{emEdicao ? "Editar turno" : "Novo turno"}</DialogoTitulo>
          <DialogoDescricao>
            {emEdicao
              ? "Altera nome, natureza, cor ou ativação do turno."
              : "Cria um turno nomeado para compor escalas."}
          </DialogoDescricao>
        </DialogoCabecalho>

        <form
          className="flex flex-col gap-4"
          noValidate
          onSubmit={(evento) => {
            void formulario.handleSubmit(aoSubmeter)(evento);
          }}
        >
          <CampoSelecao<FormularioDeTurno>
            id="turno-empresa"
            rotulo="Empresa"
            obrigatorio
            name="empresaId"
            control={formulario.control}
            opcoes={opcoesDeEmpresa}
            erro={formulario.formState.errors.empresaId?.message}
          />

          <div className="grid grid-cols-2 gap-4">
            <CampoTexto
              id="turno-codigo"
              rotulo="Código"
              obrigatorio
              erro={formulario.formState.errors.codigo?.message}
              {...formulario.register("codigo")}
            />
            <CampoTexto
              id="turno-nome"
              rotulo="Nome"
              obrigatorio
              erro={formulario.formState.errors.nome?.message}
              {...formulario.register("nome")}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <CampoSelecao<FormularioDeTurno>
              id="turno-tipo"
              rotulo="Natureza"
              obrigatorio
              name="tipo"
              control={formulario.control}
              opcoes={TIPOS_DE_TURNO}
              erro={formulario.formState.errors.tipo?.message}
            />
            <div className="flex flex-col gap-1">
              <label
                htmlFor="turno-cor"
                className="estilo-rotulo flex items-center gap-2 text-texto-secundario"
              >
                Cor na grade *
              </label>
              <div className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className="size-6 shrink-0 rounded-pleno border border-borda-sutil"
                  style={{ backgroundColor: corValida ? corAtual : undefined }}
                />
                <input
                  id="turno-cor"
                  type="text"
                  aria-invalid={Boolean(formulario.formState.errors.cor)}
                  className="h-[var(--dimensao-altura-controle)] w-full min-w-0 rounded-pequeno border border-borda-controle bg-fundo-superficie px-3 estilo-corpo text-texto-primario aria-invalid:border-estado-erro-borda"
                  {...formulario.register("cor")}
                />
              </div>
              <MensagemDeErro>{formulario.formState.errors.cor?.message}</MensagemDeErro>
            </div>
          </div>

          <CampoCheckbox<FormularioDeTurno>
            id="turno-ativo"
            rotulo="Turno ativo"
            name="ativo"
            control={formulario.control}
          />

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
              {mutacao.isPending ? "Salvando…" : "Salvar turno"}
            </Botao>
          </DialogoRodape>
        </form>
      </DialogoConteudo>
    </Dialogo>
  );
}
