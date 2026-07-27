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

export interface ValoresFormularioColaborador {
  empresaId: string;
  matricula: string;
  cpf: string;
  pisNit: string;
  nomeCompleto: string;
  nomeSocial: string;
  dataNascimento: string;
  sexo: Esquema<"Colaborador">["sexo"] | "";
  email: string;
  telefone: string;
  logradouro: string;
  numero: string;
  bairro: string;
  municipio: string;
  uf: string;
  cep: string;
  status: Esquema<"Colaborador">["status"] | "";
  dataAdmissao: string;
  pcd: boolean;
  observacoes: string;
}

const OPCOES_SEXO = [
  { valor: "feminino", rotulo: "Feminino" },
  { valor: "masculino", rotulo: "Masculino" },
  { valor: "outro", rotulo: "Outro" },
  { valor: "nao_informado", rotulo: "Não informado" },
];

const OPCOES_STATUS = [
  { valor: "pre_admissao", rotulo: "Pré-admissão" },
  { valor: "ativo", rotulo: "Ativo" },
  { valor: "afastado", rotulo: "Afastado" },
  { valor: "ferias", rotulo: "Férias" },
  { valor: "suspenso", rotulo: "Suspenso" },
  { valor: "desligado", rotulo: "Desligado" },
];

function valoresIniciais(colaborador: Esquema<"Colaborador"> | null): ValoresFormularioColaborador {
  return {
    empresaId: colaborador?.empresaId ?? "",
    matricula: colaborador?.matricula ?? "",
    cpf: colaborador?.cpf ?? "",
    pisNit: colaborador?.pisNit ?? "",
    nomeCompleto: colaborador?.nomeCompleto ?? "",
    nomeSocial: colaborador?.nomeSocial ?? "",
    dataNascimento: colaborador?.dataNascimento ?? "",
    sexo: colaborador?.sexo ?? "",
    email: colaborador?.email ?? "",
    telefone: colaborador?.telefone ?? "",
    logradouro: colaborador?.logradouro ?? "",
    numero: colaborador?.numero ?? "",
    bairro: colaborador?.bairro ?? "",
    municipio: colaborador?.municipio ?? "",
    uf: colaborador?.uf ?? "",
    cep: colaborador?.cep ?? "",
    status: colaborador?.status ?? "pre_admissao",
    dataAdmissao: colaborador?.dataAdmissao ?? "",
    pcd: colaborador?.pcd ?? false,
    observacoes: colaborador?.observacoes ?? "",
  };
}

export function paraCorpoDeColaborador(
  valores: ValoresFormularioColaborador,
): Esquema<"ColaboradorCriar"> | Esquema<"ColaboradorAtualizar"> {
  const corpo: Record<string, unknown> = {
    empresaId: valores.empresaId,
    matricula: valores.matricula,
    cpf: valores.cpf.replace(/\D/g, ""),
    nomeCompleto: valores.nomeCompleto,
    pcd: valores.pcd,
  };
  if (valores.pisNit) corpo.pisNit = valores.pisNit.replace(/\D/g, "");
  if (valores.nomeSocial) corpo.nomeSocial = valores.nomeSocial;
  if (valores.dataNascimento) corpo.dataNascimento = valores.dataNascimento;
  if (valores.sexo) corpo.sexo = valores.sexo;
  if (valores.email) corpo.email = valores.email;
  if (valores.telefone) corpo.telefone = valores.telefone;
  if (valores.logradouro) corpo.logradouro = valores.logradouro;
  if (valores.numero) corpo.numero = valores.numero;
  if (valores.bairro) corpo.bairro = valores.bairro;
  if (valores.municipio) corpo.municipio = valores.municipio;
  if (valores.uf) corpo.uf = valores.uf.toUpperCase();
  if (valores.cep) corpo.cep = valores.cep.replace(/\D/g, "");
  if (valores.status) corpo.status = valores.status;
  if (valores.dataAdmissao) corpo.dataAdmissao = valores.dataAdmissao;
  if (valores.observacoes) corpo.observacoes = valores.observacoes;
  return corpo as Esquema<"ColaboradorCriar">;
}

interface FormularioColaboradorProps {
  colaborador: Esquema<"Colaborador"> | null;
  empresas: Esquema<"Empresa">[];
  salvando: boolean;
  erro?: string | undefined;
  aoSalvar: (valores: ValoresFormularioColaborador) => void;
  aoCancelar: () => void;
}

export function FormularioColaborador({
  colaborador,
  empresas,
  salvando,
  erro,
  aoSalvar,
  aoCancelar,
}: FormularioColaboradorProps) {
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<ValoresFormularioColaborador>({ defaultValues: valoresIniciais(colaborador) });

  return (
    <form
      className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto pr-1"
      onSubmit={handleSubmit(aoSalvar)}
    >
      {erro ? (
        <Alerta variant="erro">
          <AlertaDescricao>{erro}</AlertaDescricao>
        </Alerta>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <CampoSelecao
          id="colaborador-empresa"
          rotulo="Empresa"
          obrigatorio
          name="empresaId"
          control={control}
          erro={errors.empresaId?.message}
          opcoes={empresas.map((e) => ({ valor: e.id ?? "", rotulo: e.razaoSocial ?? e.id ?? "" }))}
        />
        <CampoTexto
          id="colaborador-nome"
          rotulo="Nome completo"
          obrigatorio
          erro={errors.nomeCompleto?.message}
          {...register("nomeCompleto", { required: "Informe o nome completo." })}
        />
        <CampoTexto id="colaborador-nome-social" rotulo="Nome social" {...register("nomeSocial")} />
        <CampoTexto
          id="colaborador-matricula"
          rotulo="Matrícula"
          obrigatorio
          erro={errors.matricula?.message}
          {...register("matricula", { required: "Informe a matrícula." })}
        />
        <CampoTexto
          id="colaborador-cpf"
          rotulo="CPF"
          obrigatorio
          inputMode="numeric"
          maxLength={11}
          erro={errors.cpf?.message}
          {...register("cpf", {
            required: "Informe o CPF.",
            pattern: { value: /^\d{11}$/, message: "CPF deve ter 11 dígitos, sem pontuação." },
          })}
        />
        <CampoTexto
          id="colaborador-pis"
          rotulo="PIS/PASEP/NIT"
          inputMode="numeric"
          maxLength={11}
          {...register("pisNit")}
        />
        <CampoTexto id="colaborador-email" rotulo="E-mail" type="email" {...register("email")} />
        <CampoTexto id="colaborador-telefone" rotulo="Telefone" {...register("telefone")} />
        <CampoTexto
          id="colaborador-nascimento"
          rotulo="Data de nascimento"
          type="date"
          {...register("dataNascimento")}
        />
        <CampoSelecao
          id="colaborador-sexo"
          rotulo="Sexo"
          name="sexo"
          control={control}
          permitirVazio
          opcoes={OPCOES_SEXO}
        />
        <CampoSelecao
          id="colaborador-status"
          rotulo="Situação"
          name="status"
          control={control}
          opcoes={OPCOES_STATUS}
        />
        <CampoTexto
          id="colaborador-admissao"
          rotulo="Data de admissão"
          type="date"
          {...register("dataAdmissao")}
        />
      </div>

      <fieldset className="flex flex-col gap-4 rounded-medio border border-borda-sutil p-4">
        <legend className="estilo-rotulo px-1 text-texto-secundario">Endereço</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <CampoTexto id="colaborador-logradouro" rotulo="Logradouro" {...register("logradouro")} />
          <CampoTexto id="colaborador-numero" rotulo="Número" {...register("numero")} />
          <CampoTexto id="colaborador-bairro" rotulo="Bairro" {...register("bairro")} />
          <CampoTexto id="colaborador-municipio" rotulo="Município" {...register("municipio")} />
          <CampoTexto id="colaborador-uf" rotulo="UF" maxLength={2} {...register("uf")} />
          <CampoTexto id="colaborador-cep" rotulo="CEP" inputMode="numeric" {...register("cep")} />
        </div>
      </fieldset>

      <CampoTextoArea
        id="colaborador-observacoes"
        rotulo="Observações do RH"
        rows={2}
        {...register("observacoes")}
      />
      <CampoCheckbox
        id="colaborador-pcd"
        rotulo="Pessoa com deficiência (PCD)"
        name="pcd"
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
