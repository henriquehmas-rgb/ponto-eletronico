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

export interface ValoresFormularioCargo {
  empresaId: string;
  codigo: string;
  nome: string;
  cbo: string;
  descricao: string;
  nivel: Esquema<"Cargo">["nivel"] | "";
  salarioBase: string;
  cargoConfianca: boolean;
  ativo: boolean;
}

const OPCOES_NIVEL = [
  { valor: "estagio", rotulo: "Estágio" },
  { valor: "aprendiz", rotulo: "Aprendiz" },
  { valor: "junior", rotulo: "Júnior" },
  { valor: "pleno", rotulo: "Pleno" },
  { valor: "senior", rotulo: "Sênior" },
  { valor: "especialista", rotulo: "Especialista" },
  { valor: "coordenacao", rotulo: "Coordenação" },
  { valor: "gerencia", rotulo: "Gerência" },
  { valor: "diretoria", rotulo: "Diretoria" },
];

function valoresIniciais(cargo: Esquema<"Cargo"> | null): ValoresFormularioCargo {
  return {
    empresaId: cargo?.empresaId ?? "",
    codigo: cargo?.codigo ?? "",
    nome: cargo?.nome ?? "",
    cbo: cargo?.cbo ?? "",
    descricao: cargo?.descricao ?? "",
    nivel: cargo?.nivel ?? "",
    salarioBase: cargo?.salarioBase != null ? String(cargo.salarioBase) : "",
    cargoConfianca: cargo?.cargoConfianca ?? false,
    ativo: cargo?.ativo ?? true,
  };
}

export function paraCorpoDeCargo(
  valores: ValoresFormularioCargo,
): Esquema<"CargoCriar"> | Esquema<"CargoAtualizar"> {
  const corpo: Record<string, unknown> = {
    empresaId: valores.empresaId,
    codigo: valores.codigo,
    nome: valores.nome,
    cargoConfianca: valores.cargoConfianca,
    ativo: valores.ativo,
  };
  if (valores.cbo) corpo.cbo = valores.cbo;
  if (valores.descricao) corpo.descricao = valores.descricao;
  if (valores.nivel) corpo.nivel = valores.nivel;
  if (valores.salarioBase) corpo.salarioBase = Number(valores.salarioBase);
  return corpo as Esquema<"CargoCriar">;
}

interface FormularioCargoProps {
  cargo: Esquema<"Cargo"> | null;
  empresas: Esquema<"Empresa">[];
  salvando: boolean;
  erro?: string | undefined;
  aoSalvar: (valores: ValoresFormularioCargo) => void;
  aoCancelar: () => void;
}

/** Sem `excluirCargo` no contrato — desativação via `ativo: false` (T6). */
export function FormularioCargo({
  cargo,
  empresas,
  salvando,
  erro,
  aoSalvar,
  aoCancelar,
}: FormularioCargoProps) {
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<ValoresFormularioCargo>({ defaultValues: valoresIniciais(cargo) });

  return (
    <form className="flex flex-col gap-4" onSubmit={handleSubmit(aoSalvar)}>
      {erro ? (
        <Alerta variant="erro">
          <AlertaDescricao>{erro}</AlertaDescricao>
        </Alerta>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <CampoSelecao
          id="cargo-empresa"
          rotulo="Empresa"
          obrigatorio
          name="empresaId"
          control={control}
          erro={errors.empresaId?.message}
          opcoes={empresas.map((e) => ({ valor: e.id ?? "", rotulo: e.razaoSocial ?? e.id ?? "" }))}
        />
        <CampoTexto
          id="cargo-codigo"
          rotulo="Código"
          obrigatorio
          erro={errors.codigo?.message}
          {...register("codigo", { required: "Informe o código." })}
        />
        <CampoTexto
          id="cargo-nome"
          rotulo="Nome"
          obrigatorio
          erro={errors.nome?.message}
          {...register("nome", { required: "Informe o nome." })}
        />
        <CampoTexto
          id="cargo-cbo"
          rotulo="CBO"
          dica="6 dígitos, sem pontuação."
          maxLength={6}
          {...register("cbo")}
        />
        <CampoSelecao
          id="cargo-nivel"
          rotulo="Nível"
          name="nivel"
          control={control}
          permitirVazio
          opcoes={OPCOES_NIVEL}
        />
        <CampoTexto
          id="cargo-salario"
          rotulo="Salário base (referência)"
          type="number"
          step="0.01"
          min={0}
          {...register("salarioBase")}
        />
      </div>
      <CampoTextoArea
        id="cargo-descricao"
        rotulo="Descrição das atribuições"
        rows={3}
        {...register("descricao")}
      />
      <div className="flex flex-wrap gap-6">
        <CampoCheckbox
          id="cargo-confianca"
          rotulo="Cargo de confiança (art. 62, II da CLT)"
          name="cargoConfianca"
          control={control}
        />
        <CampoCheckbox id="cargo-ativo" rotulo="Cargo ativo" name="ativo" control={control} />
      </div>
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
