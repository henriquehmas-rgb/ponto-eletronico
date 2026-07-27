"use client";

import { useForm } from "react-hook-form";

import {
  CampoCheckbox,
  CampoSelecao,
  CampoTexto,
} from "@/componentes/paineis/cadastros/_campos/campos";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import { DialogoRodape } from "@/componentes/ui/dialog";
import type { Esquema } from "@/lib/api";

export interface ValoresFormularioUnidade {
  empresaId: string;
  codigo: string;
  nome: string;
  tipo: Esquema<"Unidade">["tipo"] | "";
  logradouro: string;
  numero: string;
  complemento: string;
  bairro: string;
  municipio: string;
  uf: string;
  cep: string;
  codigoIbgeMunicipio: string;
  fusoHorario: string;
  ativo: boolean;
}

const OPCOES_TIPO = [
  { valor: "sede", rotulo: "Sede" },
  { valor: "filial", rotulo: "Filial" },
  { valor: "obra", rotulo: "Obra" },
  { valor: "cliente", rotulo: "Cliente" },
  { valor: "home_office", rotulo: "Home office" },
  { valor: "movel", rotulo: "Móvel" },
  { valor: "deposito", rotulo: "Depósito" },
];

function valoresIniciais(unidade: Esquema<"Unidade"> | null): ValoresFormularioUnidade {
  return {
    empresaId: unidade?.empresaId ?? "",
    codigo: unidade?.codigo ?? "",
    nome: unidade?.nome ?? "",
    tipo: unidade?.tipo ?? "",
    logradouro: unidade?.logradouro ?? "",
    numero: unidade?.numero ?? "",
    complemento: unidade?.complemento ?? "",
    bairro: unidade?.bairro ?? "",
    municipio: unidade?.municipio ?? "",
    uf: unidade?.uf ?? "",
    cep: unidade?.cep ?? "",
    codigoIbgeMunicipio: unidade?.codigoIbgeMunicipio ?? "",
    fusoHorario: unidade?.fusoHorario ?? "America/Sao_Paulo",
    ativo: unidade?.ativo ?? true,
  };
}

export function paraCorpoDeUnidade(
  valores: ValoresFormularioUnidade,
): Esquema<"UnidadeCriar"> | Esquema<"UnidadeAtualizar"> {
  const corpo: Record<string, unknown> = {
    empresaId: valores.empresaId,
    codigo: valores.codigo,
    nome: valores.nome,
    ativo: valores.ativo,
  };
  if (valores.tipo) corpo.tipo = valores.tipo;
  if (valores.logradouro) corpo.logradouro = valores.logradouro;
  if (valores.numero) corpo.numero = valores.numero;
  if (valores.complemento) corpo.complemento = valores.complemento;
  if (valores.bairro) corpo.bairro = valores.bairro;
  if (valores.municipio) corpo.municipio = valores.municipio;
  if (valores.uf) corpo.uf = valores.uf.toUpperCase();
  if (valores.cep) corpo.cep = valores.cep.replace(/\D/g, "");
  if (valores.codigoIbgeMunicipio) corpo.codigoIbgeMunicipio = valores.codigoIbgeMunicipio;
  if (valores.fusoHorario) corpo.fusoHorario = valores.fusoHorario;
  return corpo as Esquema<"UnidadeCriar">;
}

interface FormularioUnidadeProps {
  unidade: Esquema<"Unidade"> | null;
  empresas: Esquema<"Empresa">[];
  salvando: boolean;
  erro?: string | undefined;
  aoSalvar: (valores: ValoresFormularioUnidade) => void;
  aoCancelar: () => void;
}

export function FormularioUnidade({
  unidade,
  empresas,
  salvando,
  erro,
  aoSalvar,
  aoCancelar,
}: FormularioUnidadeProps) {
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<ValoresFormularioUnidade>({ defaultValues: valoresIniciais(unidade) });

  return (
    <form
      className="flex max-h-[65vh] flex-col gap-4 overflow-y-auto pr-1"
      onSubmit={handleSubmit(aoSalvar)}
    >
      {erro ? (
        <Alerta variant="erro">
          <AlertaDescricao>{erro}</AlertaDescricao>
        </Alerta>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <CampoSelecao
          id="unidade-empresa"
          rotulo="Empresa"
          obrigatorio
          name="empresaId"
          control={control}
          erro={errors.empresaId?.message}
          opcoes={empresas.map((e) => ({ valor: e.id ?? "", rotulo: e.razaoSocial ?? e.id ?? "" }))}
        />
        <CampoSelecao
          id="unidade-tipo"
          rotulo="Tipo"
          name="tipo"
          control={control}
          opcoes={OPCOES_TIPO}
        />
        <CampoTexto
          id="unidade-codigo"
          rotulo="Código"
          obrigatorio
          erro={errors.codigo?.message}
          {...register("codigo", { required: "Informe o código." })}
        />
        <CampoTexto
          id="unidade-nome"
          rotulo="Nome"
          obrigatorio
          erro={errors.nome?.message}
          {...register("nome", { required: "Informe o nome." })}
        />
        <CampoTexto
          id="unidade-fuso"
          rotulo="Fuso horário"
          dica="Ex.: America/Sao_Paulo — usado na apuração desta unidade."
          {...register("fusoHorario")}
        />
      </div>

      <fieldset className="flex flex-col gap-4 rounded-medio border border-borda-sutil p-4">
        <legend className="estilo-rotulo px-1 text-texto-secundario">Endereço</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <CampoTexto id="unidade-logradouro" rotulo="Logradouro" {...register("logradouro")} />
          <CampoTexto id="unidade-numero" rotulo="Número" {...register("numero")} />
          <CampoTexto id="unidade-complemento" rotulo="Complemento" {...register("complemento")} />
          <CampoTexto id="unidade-bairro" rotulo="Bairro" {...register("bairro")} />
          <CampoTexto id="unidade-municipio" rotulo="Município" {...register("municipio")} />
          <CampoTexto id="unidade-uf" rotulo="UF" maxLength={2} {...register("uf")} />
          <CampoTexto id="unidade-cep" rotulo="CEP" inputMode="numeric" {...register("cep")} />
          <CampoTexto
            id="unidade-codigo-ibge"
            rotulo="Código IBGE do município"
            {...register("codigoIbgeMunicipio")}
          />
        </div>
      </fieldset>

      <CampoCheckbox id="unidade-ativo" rotulo="Unidade ativa" name="ativo" control={control} />

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
