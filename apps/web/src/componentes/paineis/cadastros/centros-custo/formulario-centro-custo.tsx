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

export interface ValoresFormularioCentroCusto {
  empresaId: string;
  centroCustoPaiId: string;
  codigo: string;
  nome: string;
  descricao: string;
  codigoExterno: string;
  ativo: boolean;
}

function valoresIniciais(centro: Esquema<"CentroCusto"> | null): ValoresFormularioCentroCusto {
  return {
    empresaId: centro?.empresaId ?? "",
    centroCustoPaiId: centro?.centroCustoPaiId ?? "",
    codigo: centro?.codigo ?? "",
    nome: centro?.nome ?? "",
    descricao: centro?.descricao ?? "",
    codigoExterno: centro?.codigoExterno ?? "",
    ativo: centro?.ativo ?? true,
  };
}

export function paraCorpoDeCentroCusto(
  valores: ValoresFormularioCentroCusto,
): Esquema<"CentroCustoCriar"> | Esquema<"CentroCustoAtualizar"> {
  const corpo: Record<string, unknown> = {
    empresaId: valores.empresaId,
    codigo: valores.codigo,
    nome: valores.nome,
    ativo: valores.ativo,
  };
  if (valores.centroCustoPaiId) corpo.centroCustoPaiId = valores.centroCustoPaiId;
  if (valores.descricao) corpo.descricao = valores.descricao;
  if (valores.codigoExterno) corpo.codigoExterno = valores.codigoExterno;
  return corpo as Esquema<"CentroCustoCriar">;
}

interface FormularioCentroCustoProps {
  centro: Esquema<"CentroCusto"> | null;
  empresas: Esquema<"Empresa">[];
  centrosDaEmpresa: Esquema<"CentroCusto">[];
  salvando: boolean;
  erro?: string | undefined;
  aoSalvar: (valores: ValoresFormularioCentroCusto) => void;
  aoCancelar: () => void;
}

/**
 * Sem `excluirCentroCusto` no contrato (T6, achado §2 do PCF) — a única forma
 * de "remover" é desativar via `ativo: false` neste mesmo formulário. Nenhum
 * botão "excluir" existe nesta tela.
 */
export function FormularioCentroCusto({
  centro,
  empresas,
  centrosDaEmpresa,
  salvando,
  erro,
  aoSalvar,
  aoCancelar,
}: FormularioCentroCustoProps) {
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<ValoresFormularioCentroCusto>({ defaultValues: valoresIniciais(centro) });

  return (
    <form className="flex flex-col gap-4" onSubmit={handleSubmit(aoSalvar)}>
      {erro ? (
        <Alerta variant="erro">
          <AlertaDescricao>{erro}</AlertaDescricao>
        </Alerta>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <CampoSelecao
          id="centro-custo-empresa"
          rotulo="Empresa"
          obrigatorio
          name="empresaId"
          control={control}
          erro={errors.empresaId?.message}
          opcoes={empresas.map((e) => ({ valor: e.id ?? "", rotulo: e.razaoSocial ?? e.id ?? "" }))}
        />
        <CampoTexto
          id="centro-custo-codigo"
          rotulo="Código"
          obrigatorio
          erro={errors.codigo?.message}
          {...register("codigo", { required: "Informe o código." })}
        />
        <CampoTexto
          id="centro-custo-nome"
          rotulo="Nome"
          obrigatorio
          erro={errors.nome?.message}
          {...register("nome", { required: "Informe o nome." })}
        />
        <CampoSelecao
          id="centro-custo-pai"
          rotulo="Centro de custo superior"
          name="centroCustoPaiId"
          control={control}
          permitirVazio
          opcoes={centrosDaEmpresa
            .filter((c) => c.id !== centro?.id)
            .map((c) => ({ valor: c.id ?? "", rotulo: c.nome ?? c.id ?? "" }))}
        />
        <CampoTexto
          id="centro-custo-externo"
          rotulo="Código externo (ERP/folha)"
          {...register("codigoExterno")}
        />
      </div>
      <CampoTextoArea
        id="centro-custo-descricao"
        rotulo="Descrição"
        rows={3}
        {...register("descricao")}
      />
      <CampoCheckbox
        id="centro-custo-ativo"
        rotulo="Centro de custo ativo"
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
