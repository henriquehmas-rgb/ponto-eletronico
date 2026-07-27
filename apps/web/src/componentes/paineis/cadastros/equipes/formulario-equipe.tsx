"use client";

import { useForm } from "react-hook-form";

import {
  CampoCheckbox,
  CampoSelecao,
  CampoTexto,
  CampoTextoArea,
} from "@/componentes/paineis/cadastros/_campos/campos";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import { DialogoRodape } from "@/componentes/ui/dialog";
import type { Esquema } from "@/lib/api";

export interface ValoresFormularioEquipe {
  empresaId: string;
  unidadeId: string;
  departamentoId: string;
  gestorColaboradorId: string;
  codigo: string;
  nome: string;
  descricao: string;
  cor: string;
  ativo: boolean;
}

function valoresIniciais(equipe: Esquema<"Equipe"> | null): ValoresFormularioEquipe {
  return {
    empresaId: equipe?.empresaId ?? "",
    unidadeId: equipe?.unidadeId ?? "",
    departamentoId: equipe?.departamentoId ?? "",
    gestorColaboradorId: equipe?.gestorColaboradorId ?? "",
    codigo: equipe?.codigo ?? "",
    nome: equipe?.nome ?? "",
    descricao: equipe?.descricao ?? "",
    cor: equipe?.cor ?? "#2563eb",
    ativo: equipe?.ativo ?? true,
  };
}

export function paraCorpoDeEquipe(
  valores: ValoresFormularioEquipe,
): Esquema<"EquipeCriar"> | Esquema<"EquipeAtualizar"> {
  const corpo: Record<string, unknown> = {
    empresaId: valores.empresaId,
    codigo: valores.codigo,
    nome: valores.nome,
    ativo: valores.ativo,
  };
  if (valores.unidadeId) corpo.unidadeId = valores.unidadeId;
  if (valores.departamentoId) corpo.departamentoId = valores.departamentoId;
  if (valores.gestorColaboradorId) corpo.gestorColaboradorId = valores.gestorColaboradorId;
  if (valores.descricao) corpo.descricao = valores.descricao;
  if (valores.cor) corpo.cor = valores.cor;
  return corpo as Esquema<"EquipeCriar">;
}

interface FormularioEquipeProps {
  equipe: Esquema<"Equipe"> | null;
  empresas: Esquema<"Empresa">[];
  unidades: Esquema<"Unidade">[];
  departamentos: Esquema<"Departamento">[];
  colaboradores: Esquema<"Colaborador">[];
  salvando: boolean;
  erro?: string | undefined;
  aoSalvar: (valores: ValoresFormularioEquipe) => void;
  aoCancelar: () => void;
}

export function FormularioEquipe({
  equipe,
  empresas,
  unidades,
  departamentos,
  colaboradores,
  salvando,
  erro,
  aoSalvar,
  aoCancelar,
}: FormularioEquipeProps) {
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<ValoresFormularioEquipe>({ defaultValues: valoresIniciais(equipe) });

  return (
    <form className="flex flex-col gap-4" onSubmit={handleSubmit(aoSalvar)}>
      {erro ? (
        <Alerta variant="erro">
          <AlertaDescricao>{erro}</AlertaDescricao>
        </Alerta>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <CampoSelecao
          id="equipe-empresa"
          rotulo="Empresa"
          obrigatorio
          name="empresaId"
          control={control}
          erro={errors.empresaId?.message}
          opcoes={empresas.map((e) => ({ valor: e.id ?? "", rotulo: e.razaoSocial ?? e.id ?? "" }))}
        />
        <CampoTexto
          id="equipe-codigo"
          rotulo="Código"
          obrigatorio
          erro={errors.codigo?.message}
          {...register("codigo", { required: "Informe o código." })}
        />
        <CampoTexto
          id="equipe-nome"
          rotulo="Nome"
          obrigatorio
          erro={errors.nome?.message}
          {...register("nome", { required: "Informe o nome." })}
        />
        <CampoSelecao
          id="equipe-unidade"
          rotulo="Unidade"
          name="unidadeId"
          control={control}
          permitirVazio
          opcoes={unidades.map((u) => ({ valor: u.id ?? "", rotulo: u.nome ?? u.id ?? "" }))}
        />
        <CampoSelecao
          id="equipe-departamento"
          rotulo="Departamento predominante"
          name="departamentoId"
          control={control}
          permitirVazio
          opcoes={departamentos.map((d) => ({ valor: d.id ?? "", rotulo: d.nome ?? d.id ?? "" }))}
        />
        <CampoSelecao
          id="equipe-gestor"
          rotulo="Gestor da equipe"
          name="gestorColaboradorId"
          control={control}
          permitirVazio
          opcoes={colaboradores.map((c) => ({
            valor: c.id ?? "",
            rotulo: c.nomeCompleto ?? c.id ?? "",
          }))}
        />
        <CampoTexto
          id="equipe-cor"
          rotulo="Cor na grade de escala"
          type="color"
          {...register("cor")}
        />
      </div>
      <CampoTextoArea
        id="equipe-descricao"
        rotulo="Descrição"
        rows={3}
        {...register("descricao")}
      />
      <CampoCheckbox id="equipe-ativo" rotulo="Equipe ativa" name="ativo" control={control} />
      <DialogoRodape>
        <Botao type="button" variant="secundaria" onClick={aoCancelar} disabled={salvando}>
          Cancelar
        </Botao>
        <Botao type="submit" disabled={salvando}>
          {salvando ? "Salvando…" : "Salvar"}
        </Botao>
      </DialogoRodape>
    </form>
  );
}
