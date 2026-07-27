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

export interface ValoresFormularioDepartamento {
  empresaId: string;
  departamentoPaiId: string;
  responsavelColaboradorId: string;
  codigo: string;
  nome: string;
  descricao: string;
  ativo: boolean;
}

function valoresIniciais(
  departamento: Esquema<"Departamento"> | null,
): ValoresFormularioDepartamento {
  return {
    empresaId: departamento?.empresaId ?? "",
    departamentoPaiId: departamento?.departamentoPaiId ?? "",
    responsavelColaboradorId: departamento?.responsavelColaboradorId ?? "",
    codigo: departamento?.codigo ?? "",
    nome: departamento?.nome ?? "",
    descricao: departamento?.descricao ?? "",
    ativo: departamento?.ativo ?? true,
  };
}

export function paraCorpoDeDepartamento(
  valores: ValoresFormularioDepartamento,
): Esquema<"DepartamentoCriar"> | Esquema<"DepartamentoAtualizar"> {
  const corpo: Record<string, unknown> = {
    empresaId: valores.empresaId,
    codigo: valores.codigo,
    nome: valores.nome,
    ativo: valores.ativo,
  };
  if (valores.departamentoPaiId) corpo.departamentoPaiId = valores.departamentoPaiId;
  if (valores.responsavelColaboradorId)
    corpo.responsavelColaboradorId = valores.responsavelColaboradorId;
  if (valores.descricao) corpo.descricao = valores.descricao;
  return corpo as Esquema<"DepartamentoCriar">;
}

interface FormularioDepartamentoProps {
  departamento: Esquema<"Departamento"> | null;
  empresas: Esquema<"Empresa">[];
  departamentosDaEmpresa: Esquema<"Departamento">[];
  colaboradores: Esquema<"Colaborador">[];
  salvando: boolean;
  erro?: string | undefined;
  aoSalvar: (valores: ValoresFormularioDepartamento) => void;
  aoCancelar: () => void;
}

export function FormularioDepartamento({
  departamento,
  empresas,
  departamentosDaEmpresa,
  colaboradores,
  salvando,
  erro,
  aoSalvar,
  aoCancelar,
}: FormularioDepartamentoProps) {
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<ValoresFormularioDepartamento>({ defaultValues: valoresIniciais(departamento) });

  const opcoesPai = departamentosDaEmpresa
    .filter((d) => d.id !== departamento?.id)
    .map((d) => ({ valor: d.id ?? "", rotulo: d.nome ?? d.id ?? "" }));
  const opcoesColaborador = colaboradores.map((c) => ({
    valor: c.id ?? "",
    rotulo: c.nomeCompleto ?? c.id ?? "",
  }));

  return (
    <form className="flex flex-col gap-4" onSubmit={handleSubmit(aoSalvar)}>
      {erro ? (
        <Alerta variant="erro">
          <AlertaDescricao>{erro}</AlertaDescricao>
        </Alerta>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <CampoSelecao
          id="departamento-empresa"
          rotulo="Empresa"
          obrigatorio
          name="empresaId"
          control={control}
          erro={errors.empresaId?.message}
          opcoes={empresas.map((e) => ({ valor: e.id ?? "", rotulo: e.razaoSocial ?? e.id ?? "" }))}
        />
        <CampoTexto
          id="departamento-codigo"
          rotulo="Código"
          obrigatorio
          erro={errors.codigo?.message}
          {...register("codigo", { required: "Informe o código." })}
        />
        <CampoTexto
          id="departamento-nome"
          rotulo="Nome"
          obrigatorio
          erro={errors.nome?.message}
          {...register("nome", { required: "Informe o nome." })}
        />
        <CampoSelecao
          id="departamento-pai"
          rotulo="Departamento superior"
          name="departamentoPaiId"
          control={control}
          permitirVazio
          opcoes={opcoesPai}
        />
        <CampoSelecao
          id="departamento-responsavel"
          rotulo="Responsável"
          name="responsavelColaboradorId"
          control={control}
          permitirVazio
          opcoes={opcoesColaborador}
        />
      </div>
      <CampoTextoArea
        id="departamento-descricao"
        rotulo="Descrição"
        rows={3}
        {...register("descricao")}
      />
      <CampoCheckbox
        id="departamento-ativo"
        rotulo="Departamento ativo"
        name="ativo"
        control={control}
      />
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
