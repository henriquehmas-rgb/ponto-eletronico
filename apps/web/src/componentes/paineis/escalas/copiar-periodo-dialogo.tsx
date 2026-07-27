"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { CaixaDeSelecao } from "@/componentes/ui/checkbox";
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
import { api } from "@/lib/api";

import { CampoSelecao, CampoTexto, type OpcaoDeSelecao } from "./campos";
import type { MembroDaEquipe } from "./dados-compartilhados";
import { mensagemDeErroApi } from "./mensagem-de-erro-api";
import { resolverZod } from "./resolver-zod";
import { calcularPosicaoInicial } from "./utilitarios-ciclo";

const ESQUEMA = z.object({
  vinculoReferenciaId: z.string().min(1, "Selecione o vínculo de referência."),
  dataReferencia: z.string().min(1, "Informe a data de referência (na origem)."),
  novaVigenciaInicio: z.string().min(1, "Informe a data de início da nova vigência."),
  motivo: z.string().optional(),
});
type FormularioDeCopia = z.infer<typeof ESQUEMA>;

export interface CopiarPeriodoDialogoProps {
  aberto: boolean;
  aoMudarAberto: (aberto: boolean) => void;
  equipe: MembroDaEquipe[];
}

interface ResultadoPorVinculo {
  vinculoId: string;
  nome: string;
  status: "sucesso" | "erro";
  mensagem?: string;
}

/**
 * "Copiar período" (T13, achado de contrato nº 2 do PCF §2): não existe
 * `POST /v1/escalas/copiar` — é composição no cliente.
 *
 * 1. `resolverJornadaDoDia(vinculoReferenciaId, dataReferencia)` → lê a
 *    posição de ciclo VIGENTE do vínculo de referência (a fase resolvida
 *    daquele vínculo especificamente, não a posição canônica da escala).
 * 2. `obterEscala(escalaId)` → `diasCiclo`, para a aritmética modular.
 * 3. Para cada vínculo-alvo: `calcularPosicaoInicial` (função pura,
 *    testada) recalcula a posição inicial na NOVA vigência, preservando a
 *    fase da referência; `atribuirEscalaVinculo` grava a atribuição.
 *
 * Não reproduz a lógica de precedência do resolvedor (proibição expressa do
 * PCF) — só usa o resultado que ele já devolveu.
 */
export function CopiarPeriodoDialogo({ aberto, aoMudarAberto, equipe }: CopiarPeriodoDialogoProps) {
  const queryClient = useQueryClient();
  const [enviando, definirEnviando] = useState(false);
  const [erroGeral, definirErroGeral] = useState<string | undefined>(undefined);
  const [resultados, definirResultados] = useState<ResultadoPorVinculo[] | null>(null);
  const [alvosSelecionados, definirAlvosSelecionados] = useState<Set<string>>(new Set());
  const [erroAlvos, definirErroAlvos] = useState<string | undefined>(undefined);

  const opcoesDeVinculo: OpcaoDeSelecao[] = equipe.map((membro) => ({
    valor: membro.vinculoId,
    rotulo: membro.nomeColaborador,
  }));

  const formulario = useForm<FormularioDeCopia>({
    resolver: resolverZod(ESQUEMA),
    defaultValues: {
      vinculoReferenciaId: "",
      dataReferencia: "",
      novaVigenciaInicio: "",
      motivo: "",
    },
  });

  function fecharEReiniciar() {
    formulario.reset({
      vinculoReferenciaId: "",
      dataReferencia: "",
      novaVigenciaInicio: "",
      motivo: "",
    });
    definirAlvosSelecionados(new Set());
    definirResultados(null);
    definirErroGeral(undefined);
    definirErroAlvos(undefined);
    aoMudarAberto(false);
  }

  function alternarAlvo(vinculoId: string) {
    const novo = new Set(alvosSelecionados);
    if (novo.has(vinculoId)) novo.delete(vinculoId);
    else novo.add(vinculoId);
    definirAlvosSelecionados(novo);
  }

  async function aoSubmeter(valores: FormularioDeCopia) {
    definirErroGeral(undefined);
    definirErroAlvos(undefined);
    definirResultados(null);

    const alvos = equipe.filter(
      (membro) =>
        alvosSelecionados.has(membro.vinculoId) && membro.vinculoId !== valores.vinculoReferenciaId,
    );
    if (alvos.length === 0) {
      definirErroAlvos("Selecione ao menos um vínculo-alvo (diferente da referência).");
      return;
    }

    definirEnviando(true);
    try {
      const resolucao = await api.GET("/v1/jornadas/resolver", {
        params: { query: { vinculoId: valores.vinculoReferenciaId, data: valores.dataReferencia } },
      });
      if (resolucao.error) throw resolucao.error;
      const escalaId = resolucao.data?.escalaId;
      const posicaoCiclo = resolucao.data?.posicaoCiclo;
      if (!escalaId || !posicaoCiclo) {
        definirErroGeral(
          "O vínculo de referência não tem escala resolvida nessa data (jornada, não escala, ou sem regra).",
        );
        return;
      }

      const escala = await api.GET("/v1/escalas/{escalaId}", { params: { path: { escalaId } } });
      if (escala.error) throw escala.error;
      const diasCiclo = escala.data?.diasCiclo;
      if (!diasCiclo) {
        definirErroGeral("A escala resolvida não tem diasCiclo cadastrado.");
        return;
      }

      const listaDeResultados: ResultadoPorVinculo[] = [];
      for (const alvo of alvos) {
        const posicaoInicial = calcularPosicaoInicial(
          resolucao.data?.data ?? valores.dataReferencia,
          posicaoCiclo,
          valores.novaVigenciaInicio,
          diasCiclo,
        );
        try {
          const criado = await api.POST("/v1/escalas/{escalaId}/atribuicoes", {
            params: { path: { escalaId }, header: { "Idempotency-Key": crypto.randomUUID() } },
            body: {
              vinculoId: alvo.vinculoId,
              posicaoInicial,
              vigenciaInicio: valores.novaVigenciaInicio,
              ...(valores.motivo ? { motivo: valores.motivo } : {}),
            },
          });
          if (criado.error) throw criado.error;
          listaDeResultados.push({
            vinculoId: alvo.vinculoId,
            nome: alvo.nomeColaborador,
            status: "sucesso",
          });
        } catch (erroDoAlvo) {
          listaDeResultados.push({
            vinculoId: alvo.vinculoId,
            nome: alvo.nomeColaborador,
            status: "erro",
            mensagem: mensagemDeErroApi(erroDoAlvo),
          });
        }
      }
      definirResultados(listaDeResultados);
      void queryClient.invalidateQueries({ queryKey: ["resolucao-jornada"] });
      void queryClient.invalidateQueries({ queryKey: ["apuracoes"] });
    } catch (erro) {
      definirErroGeral(mensagemDeErroApi(erro));
    } finally {
      definirEnviando(false);
    }
  }

  const houveFalha = resultados?.some((resultado) => resultado.status === "erro") ?? false;

  return (
    <Dialogo
      open={aberto}
      onOpenChange={(valor) => {
        if (!valor) fecharEReiniciar();
        else aoMudarAberto(true);
      }}
    >
      <DialogoConteudo className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
        <DialogoCabecalho>
          <DialogoTitulo>Copiar período</DialogoTitulo>
          <DialogoDescricao>
            Aplica o mesmo padrão de escala de um vínculo de referência a um novo grupo de vínculos,
            preservando a fase do ciclo (não é um endpoint de cópia — é composição no cliente a
            partir de <code className="estilo-identificador">resolverJornadaDoDia</code> e{" "}
            <code className="estilo-identificador">atribuirEscalaVinculo</code>).
          </DialogoDescricao>
        </DialogoCabecalho>

        {resultados ? (
          <div className="flex flex-col gap-2">
            <p className="estilo-corpo text-texto-primario">
              {resultados.filter((r) => r.status === "sucesso").length} de {resultados.length}{" "}
              atribuições concluídas.
            </p>
            <ul className="flex flex-col gap-1">
              {resultados.map((resultado) => (
                <li
                  key={resultado.vinculoId}
                  className={
                    resultado.status === "sucesso"
                      ? "estilo-legenda text-estado-sucesso-texto"
                      : "estilo-legenda text-estado-erro-texto"
                  }
                >
                  {resultado.status === "sucesso" ? "✓" : "✗"} {resultado.nome}
                  {resultado.mensagem ? ` — ${resultado.mensagem}` : ""}
                </li>
              ))}
            </ul>
            <DialogoRodape>
              <Botao type="button" onClick={fecharEReiniciar}>
                {houveFalha ? "Fechar" : "Concluído"}
              </Botao>
            </DialogoRodape>
          </div>
        ) : (
          <form
            className="flex flex-col gap-4"
            noValidate
            onSubmit={(evento) => {
              void formulario.handleSubmit(aoSubmeter)(evento);
            }}
          >
            <CampoSelecao<FormularioDeCopia>
              id="copiar-vinculo-referencia"
              rotulo="Vínculo de referência (origem)"
              obrigatorio
              name="vinculoReferenciaId"
              control={formulario.control}
              opcoes={opcoesDeVinculo}
              erro={formulario.formState.errors.vinculoReferenciaId?.message}
            />

            <div className="grid grid-cols-2 gap-4">
              <CampoTexto
                id="copiar-data-referencia"
                rotulo="Data de referência (origem)"
                obrigatorio
                type="date"
                erro={formulario.formState.errors.dataReferencia?.message}
                {...formulario.register("dataReferencia")}
              />
              <CampoTexto
                id="copiar-nova-vigencia"
                rotulo="Nova vigência — início"
                obrigatorio
                type="date"
                erro={formulario.formState.errors.novaVigenciaInicio?.message}
                {...formulario.register("novaVigenciaInicio")}
              />
            </div>

            <CampoTexto
              id="copiar-motivo"
              rotulo="Motivo"
              erro={formulario.formState.errors.motivo?.message}
              {...formulario.register("motivo")}
            />

            <fieldset className="flex flex-col gap-2 rounded-medio border border-borda-sutil p-3">
              <legend className="estilo-rotulo px-1 text-texto-primario">Vínculos-alvo</legend>
              <div className="flex max-h-48 flex-col gap-1 overflow-y-auto">
                {equipe.map((membro) => (
                  <label key={membro.vinculoId} className="flex cursor-pointer items-center gap-2">
                    <CaixaDeSelecao
                      checked={alvosSelecionados.has(membro.vinculoId)}
                      onCheckedChange={() => {
                        alternarAlvo(membro.vinculoId);
                      }}
                      disabled={membro.vinculoId === formulario.watch("vinculoReferenciaId")}
                    />
                    <span className="estilo-corpo text-texto-primario">
                      {membro.nomeColaborador}
                    </span>
                  </label>
                ))}
              </div>
              <MensagemDeErro>{erroAlvos}</MensagemDeErro>
            </fieldset>

            {erroGeral ? <MensagemDeErro role="alert">{erroGeral}</MensagemDeErro> : null}

            <DialogoRodape>
              <Botao type="button" variant="secundaria" onClick={fecharEReiniciar}>
                Cancelar
              </Botao>
              <Botao type="submit" disabled={enviando}>
                {enviando ? "Copiando…" : "Copiar período"}
              </Botao>
            </DialogoRodape>
          </form>
        )}
      </DialogoConteudo>
    </Dialogo>
  );
}
