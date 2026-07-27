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

export interface ValoresFormularioEmpresa {
  tipo: "matriz" | "filial" | "";
  matrizId: string;
  cnpj: string;
  razaoSocial: string;
  nomeFantasia: string;
  inscricaoEstadual: string;
  inscricaoMunicipal: string;
  cnaePrincipal: string;
  logradouro: string;
  numero: string;
  complemento: string;
  bairro: string;
  municipio: string;
  uf: string;
  cep: string;
  codigoIbgeMunicipio: string;
  telefone: string;
  email: string;
  fusoHorario: string;
  ativo: boolean;
}

function valoresIniciais(empresa: Esquema<"Empresa"> | null): ValoresFormularioEmpresa {
  return {
    tipo: empresa?.tipo ?? "",
    matrizId: empresa?.matrizId ?? "",
    cnpj: empresa?.cnpj ?? "",
    razaoSocial: empresa?.razaoSocial ?? "",
    nomeFantasia: empresa?.nomeFantasia ?? "",
    inscricaoEstadual: empresa?.inscricaoEstadual ?? "",
    inscricaoMunicipal: empresa?.inscricaoMunicipal ?? "",
    cnaePrincipal: empresa?.cnaePrincipal ?? "",
    logradouro: empresa?.logradouro ?? "",
    numero: empresa?.numero ?? "",
    complemento: empresa?.complemento ?? "",
    bairro: empresa?.bairro ?? "",
    municipio: empresa?.municipio ?? "",
    uf: empresa?.uf ?? "",
    cep: empresa?.cep ?? "",
    codigoIbgeMunicipio: empresa?.codigoIbgeMunicipio ?? "",
    telefone: empresa?.telefone ?? "",
    email: empresa?.email ?? "",
    fusoHorario: empresa?.fusoHorario ?? "America/Sao_Paulo",
    ativo: empresa?.ativo ?? true,
  };
}

/** Monta o corpo aceito por `criarEmpresa`/`atualizarEmpresa`, sem campos vazios. */
export function paraCorpoDeEmpresa(
  valores: ValoresFormularioEmpresa,
): Esquema<"EmpresaCriar"> | Esquema<"EmpresaAtualizar"> {
  const corpo: Record<string, unknown> = {
    cnpj: valores.cnpj,
    razaoSocial: valores.razaoSocial,
    ativo: valores.ativo,
  };
  if (valores.tipo) corpo.tipo = valores.tipo;
  if (valores.tipo === "filial" && valores.matrizId) corpo.matrizId = valores.matrizId;
  if (valores.nomeFantasia) corpo.nomeFantasia = valores.nomeFantasia;
  if (valores.inscricaoEstadual) corpo.inscricaoEstadual = valores.inscricaoEstadual;
  if (valores.inscricaoMunicipal) corpo.inscricaoMunicipal = valores.inscricaoMunicipal;
  if (valores.cnaePrincipal) corpo.cnaePrincipal = valores.cnaePrincipal;
  if (valores.logradouro) corpo.logradouro = valores.logradouro;
  if (valores.numero) corpo.numero = valores.numero;
  if (valores.complemento) corpo.complemento = valores.complemento;
  if (valores.bairro) corpo.bairro = valores.bairro;
  if (valores.municipio) corpo.municipio = valores.municipio;
  if (valores.uf) corpo.uf = valores.uf.toUpperCase();
  if (valores.cep) corpo.cep = valores.cep.replace(/\D/g, "");
  if (valores.codigoIbgeMunicipio) corpo.codigoIbgeMunicipio = valores.codigoIbgeMunicipio;
  if (valores.telefone) corpo.telefone = valores.telefone;
  if (valores.email) corpo.email = valores.email;
  if (valores.fusoHorario) corpo.fusoHorario = valores.fusoHorario;
  return corpo as Esquema<"EmpresaCriar">;
}

interface FormularioEmpresaProps {
  empresa: Esquema<"Empresa"> | null;
  matrizes: Esquema<"Empresa">[];
  salvando: boolean;
  erro?: string | undefined;
  aoSalvar: (valores: ValoresFormularioEmpresa) => void;
  aoCancelar: () => void;
}

export function FormularioEmpresa({
  empresa,
  matrizes,
  salvando,
  erro,
  aoSalvar,
  aoCancelar,
}: FormularioEmpresaProps) {
  const {
    register,
    handleSubmit,
    control,
    watch,
    formState: { errors },
  } = useForm<ValoresFormularioEmpresa>({ defaultValues: valoresIniciais(empresa) });
  const tipo = watch("tipo");

  return (
    <form
      className="flex max-h-[75vh] flex-col gap-4 overflow-y-auto pr-1"
      onSubmit={handleSubmit(aoSalvar)}
    >
      {erro ? (
        <Alerta variant="erro">
          <AlertaDescricao>{erro}</AlertaDescricao>
        </Alerta>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <CampoTexto
          id="empresa-razao-social"
          rotulo="Razão social"
          obrigatorio
          erro={errors.razaoSocial?.message}
          {...register("razaoSocial", { required: "Informe a razão social." })}
        />
        <CampoTexto
          id="empresa-nome-fantasia"
          rotulo="Nome fantasia"
          {...register("nomeFantasia")}
        />
        <CampoTexto
          id="empresa-cnpj"
          rotulo="CNPJ"
          obrigatorio
          inputMode="numeric"
          maxLength={14}
          erro={errors.cnpj?.message}
          {...register("cnpj", {
            required: "Informe o CNPJ.",
            pattern: { value: /^\d{14}$/, message: "CNPJ deve ter 14 dígitos, sem pontuação." },
          })}
        />
        <CampoSelecao
          id="empresa-tipo"
          rotulo="Tipo"
          name="tipo"
          control={control}
          opcoes={[
            { valor: "matriz", rotulo: "Matriz" },
            { valor: "filial", rotulo: "Filial" },
          ]}
        />
        {tipo === "filial" ? (
          <CampoSelecao
            id="empresa-matriz"
            rotulo="Empresa matriz"
            name="matrizId"
            control={control}
            opcoes={matrizes.map((m) => ({
              valor: m.id ?? "",
              rotulo: m.razaoSocial ?? m.id ?? "",
            }))}
          />
        ) : null}
        <CampoTexto
          id="empresa-ie"
          rotulo="Inscrição estadual"
          {...register("inscricaoEstadual")}
        />
        <CampoTexto
          id="empresa-im"
          rotulo="Inscrição municipal"
          {...register("inscricaoMunicipal")}
        />
        <CampoTexto id="empresa-cnae" rotulo="CNAE principal" {...register("cnaePrincipal")} />
        <CampoTexto
          id="empresa-fuso"
          rotulo="Fuso horário"
          {...register("fusoHorario")}
          dica="Ex.: America/Sao_Paulo"
        />
        <CampoTexto id="empresa-telefone" rotulo="Telefone" {...register("telefone")} />
        <CampoTexto id="empresa-email" rotulo="E-mail" type="email" {...register("email")} />
      </div>

      <fieldset className="flex flex-col gap-4 rounded-medio border border-borda-sutil p-4">
        <legend className="estilo-rotulo px-1 text-texto-secundario">Endereço</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <CampoTexto id="empresa-logradouro" rotulo="Logradouro" {...register("logradouro")} />
          <CampoTexto id="empresa-numero" rotulo="Número" {...register("numero")} />
          <CampoTexto id="empresa-complemento" rotulo="Complemento" {...register("complemento")} />
          <CampoTexto id="empresa-bairro" rotulo="Bairro" {...register("bairro")} />
          <CampoTexto id="empresa-municipio" rotulo="Município" {...register("municipio")} />
          <CampoTexto id="empresa-uf" rotulo="UF" maxLength={2} {...register("uf")} />
          <CampoTexto id="empresa-cep" rotulo="CEP" inputMode="numeric" {...register("cep")} />
          <CampoTexto
            id="empresa-codigo-ibge"
            rotulo="Código IBGE do município"
            {...register("codigoIbgeMunicipio")}
          />
        </div>
      </fieldset>

      <CampoCheckbox id="empresa-ativo" rotulo="Empresa ativa" name="ativo" control={control} />

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
