"use client";

import { useForm } from "react-hook-form";

import { CampoSelecao, CampoTexto } from "@/componentes/paineis/cadastros/_campos/campos";
import { mensagemDeErroApi } from "@/componentes/paineis/cadastros/_shared/erro-amigavel";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import { Selo } from "@/componentes/ui/badge";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { useAdicionarMembroEquipe, useMembrosDaEquipe } from "@/ganchos/use-equipes";
import type { Esquema } from "@/lib/api";

interface ValoresMembro {
  colaboradorId: string;
  papel: Esquema<"EquipeMembroCriar">["papel"] | "";
  vigenciaInicio: string;
}

interface SecaoMembrosEquipeProps {
  equipeId: string;
  colaboradores: Esquema<"Colaborador">[];
}

const OPCOES_PAPEL = [
  { valor: "membro", rotulo: "Membro" },
  { valor: "lider", rotulo: "Líder" },
  { valor: "substituto", rotulo: "Substituto" },
];

/**
 * Membros da equipe (T6). **Não existe remoção de membro no contrato**
 * (`openapi.yaml`, tag `organizacao`: só `POST /v1/equipes/{id}/membros`) —
 * esta seção por isso nunca oferece um botão de remover. A listagem também
 * não é o recurso oficial de membros (que não tem `GET`): é uma aproximação
 * via `GET /v1/colaboradores?equipeId=`, documentada no gancho
 * `useMembrosDaEquipe` e em `docs/backlog.md`.
 */
export function SecaoMembrosEquipe({ equipeId, colaboradores }: SecaoMembrosEquipeProps) {
  const membros = useMembrosDaEquipe(equipeId);
  const adicionar = useAdicionarMembroEquipe();
  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<ValoresMembro>({
    defaultValues: { colaboradorId: "", papel: "membro", vigenciaInicio: "" },
  });

  function salvar(valores: ValoresMembro) {
    if (!valores.colaboradorId || !valores.vigenciaInicio) return;
    adicionar.mutate(
      {
        equipeId,
        corpo: {
          colaboradorId: valores.colaboradorId,
          ...(valores.papel ? { papel: valores.papel } : {}),
          vigenciaInicio: valores.vigenciaInicio,
        },
      },
      { onSuccess: () => reset({ colaboradorId: "", papel: "membro", vigenciaInicio: "" }) },
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {membros.isPending ? (
        <Esqueleto className="h-20 w-full" />
      ) : membros.isError ? (
        <Alerta variant="erro">
          <AlertaDescricao>{mensagemDeErroApi(membros.error)}</AlertaDescricao>
        </Alerta>
      ) : (membros.data?.dados ?? []).length === 0 ? (
        <p className="estilo-corpo text-texto-secundario">Nenhum colaborador nesta equipe ainda.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {(membros.data?.dados ?? []).map((colaborador) => (
            <li
              key={colaborador.id}
              className="flex items-center justify-between rounded-pequeno border border-borda-sutil p-2"
            >
              <span className="estilo-corpo text-texto-primario">{colaborador.nomeCompleto}</span>
              <Selo variant="neutro">{colaborador.matricula}</Selo>
            </li>
          ))}
        </ul>
      )}

      <form className="flex flex-wrap items-end gap-3" onSubmit={handleSubmit(salvar)}>
        <CampoSelecao
          id="membro-colaborador"
          rotulo="Colaborador"
          obrigatorio
          name="colaboradorId"
          control={control}
          erro={errors.colaboradorId?.message}
          opcoes={colaboradores.map((c) => ({
            valor: c.id ?? "",
            rotulo: c.nomeCompleto ?? c.id ?? "",
          }))}
        />
        <CampoSelecao
          id="membro-papel"
          rotulo="Papel"
          name="papel"
          control={control}
          opcoes={OPCOES_PAPEL}
        />
        <CampoTexto
          id="membro-vigencia"
          rotulo="Início da participação"
          type="date"
          obrigatorio
          erro={errors.vigenciaInicio?.message}
          {...register("vigenciaInicio", { required: "Informe a data de início." })}
        />
        <Botao type="submit" variant="secundaria" disabled={adicionar.isPending}>
          {adicionar.isPending ? "Adicionando…" : "Adicionar"}
        </Botao>
      </form>
      {adicionar.isError ? (
        <Alerta variant="erro">
          <AlertaDescricao>{mensagemDeErroApi(adicionar.error)}</AlertaDescricao>
        </Alerta>
      ) : null}
    </div>
  );
}
