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
import { useAtribuirEscalaVinculo } from "@/ganchos/use-escalas";
import type { Esquema } from "@/lib/api";

import type { MembroDaEquipe } from "./dados-compartilhados";
import { CampoSelecao, CampoTexto, type OpcaoDeSelecao } from "./campos";
import { mensagemDeErroApi } from "./mensagem-de-erro-api";
import { resolverZod } from "./resolver-zod";

const ESQUEMA = z.object({
  vinculoId: z.string().min(1, "Selecione o vínculo."),
  posicaoInicial: z.coerce.number().int().min(1, "A posição inicial precisa ser >= 1."),
  vigenciaInicio: z.string().min(1, "Informe a data de início da vigência."),
  vigenciaFim: z.string().optional(),
  motivo: z.string().optional(),
});
type FormularioDeAtribuicao = z.infer<typeof ESQUEMA>;

export interface FormularioAtribuicaoProps {
  aberto: boolean;
  aoMudarAberto: (aberto: boolean) => void;
  escala: Esquema<"Escala"> | null;
  equipe: MembroDaEquipe[];
}

/**
 * `POST /v1/escalas/{escalaId}/atribuicoes` (`atribuirEscalaVinculo`, T12).
 * `posicaoInicial` é o que permite equipes desencontradas na mesma escala
 * (plantão A na posição 1, plantão B na posição 2) — por isso fica editável
 * aqui, não fixado em 1.
 */
export function FormularioAtribuicao({
  aberto,
  aoMudarAberto,
  escala,
  equipe,
}: FormularioAtribuicaoProps) {
  const atribuir = useAtribuirEscalaVinculo();

  const opcoesDeVinculo: OpcaoDeSelecao[] = equipe.map((membro) => ({
    valor: membro.vinculoId,
    rotulo: membro.nomeColaborador,
  }));

  const formulario = useForm<FormularioDeAtribuicao>({
    resolver: resolverZod(ESQUEMA),
    defaultValues: {
      vinculoId: "",
      posicaoInicial: 1,
      vigenciaInicio: "",
      vigenciaFim: "",
      motivo: "",
    },
  });

  useEffect(() => {
    if (!aberto) return;
    formulario.reset({
      vinculoId: "",
      posicaoInicial: 1,
      vigenciaInicio: "",
      vigenciaFim: "",
      motivo: "",
    });
    atribuir.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aberto, escala?.id]);

  async function aoSubmeter(valores: FormularioDeAtribuicao) {
    if (!escala?.id) return;
    try {
      await atribuir.mutateAsync({
        escalaId: escala.id,
        corpo: {
          vinculoId: valores.vinculoId,
          posicaoInicial: valores.posicaoInicial,
          vigenciaInicio: valores.vigenciaInicio,
          ...(valores.vigenciaFim ? { vigenciaFim: valores.vigenciaFim } : {}),
          ...(valores.motivo ? { motivo: valores.motivo } : {}),
        },
      });
      aoMudarAberto(false);
    } catch {
      // Erro exibido abaixo via `atribuir.isError`.
    }
  }

  return (
    <Dialogo open={aberto} onOpenChange={aoMudarAberto}>
      <DialogoConteudo>
        <DialogoCabecalho>
          <DialogoTitulo>Atribuir escala a vínculo</DialogoTitulo>
          <DialogoDescricao>
            {escala ? `Escala "${escala.nome}" (${escala.codigo}).` : ""} A posição inicial define
            em que ponto do ciclo o vínculo entra na vigência.
          </DialogoDescricao>
        </DialogoCabecalho>

        <form
          className="flex flex-col gap-4"
          noValidate
          onSubmit={(evento) => {
            void formulario.handleSubmit(aoSubmeter)(evento);
          }}
        >
          <CampoSelecao<FormularioDeAtribuicao>
            id="atribuicao-vinculo"
            rotulo="Vínculo"
            obrigatorio
            name="vinculoId"
            control={formulario.control}
            opcoes={opcoesDeVinculo}
            erro={formulario.formState.errors.vinculoId?.message}
          />

          <div className="grid grid-cols-3 gap-4">
            <CampoTexto
              id="atribuicao-posicao"
              rotulo="Posição inicial"
              obrigatorio
              type="number"
              min={1}
              erro={formulario.formState.errors.posicaoInicial?.message}
              {...formulario.register("posicaoInicial")}
            />
            <CampoTexto
              id="atribuicao-vigencia-inicio"
              rotulo="Vigência — início"
              obrigatorio
              type="date"
              erro={formulario.formState.errors.vigenciaInicio?.message}
              {...formulario.register("vigenciaInicio")}
            />
            <CampoTexto
              id="atribuicao-vigencia-fim"
              rotulo="Vigência — fim"
              type="date"
              erro={formulario.formState.errors.vigenciaFim?.message}
              {...formulario.register("vigenciaFim")}
            />
          </div>

          <CampoTexto
            id="atribuicao-motivo"
            rotulo="Motivo"
            erro={formulario.formState.errors.motivo?.message}
            {...formulario.register("motivo")}
          />

          {atribuir.isError ? (
            <MensagemDeErro role="alert">{mensagemDeErroApi(atribuir.error)}</MensagemDeErro>
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
            <Botao type="submit" disabled={atribuir.isPending || !escala}>
              {atribuir.isPending ? "Atribuindo…" : "Atribuir"}
            </Botao>
          </DialogoRodape>
        </form>
      </DialogoConteudo>
    </Dialogo>
  );
}
