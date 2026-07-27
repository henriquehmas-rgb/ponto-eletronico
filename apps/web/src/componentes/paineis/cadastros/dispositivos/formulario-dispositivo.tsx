"use client";

import { useForm } from "react-hook-form";

import {
  CampoSelecao,
  CampoTexto,
  CampoTextoArea,
} from "@/componentes/paineis/cadastros/_campos/campos";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import { DialogoRodape } from "@/componentes/ui/dialog";
import type { Esquema } from "@/lib/api";

export interface ValoresFormularioDispositivo {
  empresaId: string;
  unidadeId: string;
  tipo: Esquema<"Dispositivo">["tipo"] | "";
  plataforma: Esquema<"Dispositivo">["plataforma"] | "";
  identificador: string;
  nome: string;
  fabricante: string;
  modelo: string;
  status: Esquema<"Dispositivo">["status"] | "";
  observacoes: string;
}

const OPCOES_TIPO = [
  { valor: "terminal", rotulo: "Terminal" },
  { valor: "celular", rotulo: "Celular" },
  { valor: "tablet", rotulo: "Tablet" },
  { valor: "navegador", rotulo: "Navegador" },
  { valor: "totem", rotulo: "Totem" },
  { valor: "integracao", rotulo: "Integração" },
];

const OPCOES_PLATAFORMA = [
  { valor: "android", rotulo: "Android" },
  { valor: "ios", rotulo: "iOS" },
  { valor: "web", rotulo: "Web" },
  { valor: "linux", rotulo: "Linux" },
  { valor: "windows", rotulo: "Windows" },
  { valor: "macos", rotulo: "macOS" },
  { valor: "embarcado", rotulo: "Embarcado" },
];

const OPCOES_STATUS = [
  { valor: "pendente", rotulo: "Pendente" },
  { valor: "ativo", rotulo: "Ativo" },
  { valor: "bloqueado", rotulo: "Bloqueado" },
  { valor: "revogado", rotulo: "Revogado" },
  { valor: "substituido", rotulo: "Substituído" },
];

function valoresIniciais(dispositivo: Esquema<"Dispositivo"> | null): ValoresFormularioDispositivo {
  return {
    empresaId: dispositivo?.empresaId ?? "",
    unidadeId: dispositivo?.unidadeId ?? "",
    tipo: dispositivo?.tipo ?? "",
    plataforma: dispositivo?.plataforma ?? "",
    identificador: dispositivo?.identificador ?? "",
    nome: dispositivo?.nome ?? "",
    fabricante: dispositivo?.fabricante ?? "",
    modelo: dispositivo?.modelo ?? "",
    status: dispositivo?.status ?? "pendente",
    observacoes: dispositivo?.observacoes ?? "",
  };
}

export function paraCorpoDeDispositivo(
  valores: ValoresFormularioDispositivo,
): Esquema<"DispositivoCriar"> | Esquema<"DispositivoAtualizar"> {
  const corpo: Record<string, unknown> = {
    identificador: valores.identificador,
  };
  if (valores.tipo) corpo.tipo = valores.tipo;
  if (valores.empresaId) corpo.empresaId = valores.empresaId;
  if (valores.unidadeId) corpo.unidadeId = valores.unidadeId;
  if (valores.plataforma) corpo.plataforma = valores.plataforma;
  if (valores.nome) corpo.nome = valores.nome;
  if (valores.fabricante) corpo.fabricante = valores.fabricante;
  if (valores.modelo) corpo.modelo = valores.modelo;
  if (valores.status) corpo.status = valores.status;
  if (valores.observacoes) corpo.observacoes = valores.observacoes;
  return corpo as Esquema<"DispositivoCriar">;
}

interface FormularioDispositivoProps {
  dispositivo: Esquema<"Dispositivo"> | null;
  empresas: Esquema<"Empresa">[];
  unidades: Esquema<"Unidade">[];
  salvando: boolean;
  erro?: string | undefined;
  aoSalvar: (valores: ValoresFormularioDispositivo) => void;
  aoCancelar: () => void;
}

export function FormularioDispositivo({
  dispositivo,
  empresas,
  unidades,
  salvando,
  erro,
  aoSalvar,
  aoCancelar,
}: FormularioDispositivoProps) {
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<ValoresFormularioDispositivo>({ defaultValues: valoresIniciais(dispositivo) });

  return (
    <form className="flex flex-col gap-4" onSubmit={handleSubmit(aoSalvar)}>
      {erro ? (
        <Alerta variant="erro">
          <AlertaDescricao>{erro}</AlertaDescricao>
        </Alerta>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <CampoSelecao
          id="dispositivo-empresa"
          rotulo="Empresa"
          name="empresaId"
          control={control}
          permitirVazio
          opcoes={empresas.map((e) => ({ valor: e.id ?? "", rotulo: e.razaoSocial ?? e.id ?? "" }))}
        />
        <CampoSelecao
          id="dispositivo-unidade"
          rotulo="Unidade"
          name="unidadeId"
          control={control}
          permitirVazio
          opcoes={unidades.map((u) => ({ valor: u.id ?? "", rotulo: u.nome ?? u.id ?? "" }))}
        />
        <CampoSelecao
          id="dispositivo-tipo"
          rotulo="Tipo"
          obrigatorio
          name="tipo"
          control={control}
          erro={errors.tipo?.message}
          opcoes={OPCOES_TIPO}
        />
        <CampoSelecao
          id="dispositivo-plataforma"
          rotulo="Plataforma"
          name="plataforma"
          control={control}
          permitirVazio
          opcoes={OPCOES_PLATAFORMA}
        />
        <CampoTexto
          id="dispositivo-identificador"
          rotulo="Identificador estável"
          obrigatorio
          dica="android_id, identifierForVendor, fingerprint do navegador ou nº de série."
          erro={errors.identificador?.message}
          {...register("identificador", { required: "Informe o identificador do aparelho." })}
        />
        <CampoTexto id="dispositivo-nome" rotulo="Nome amigável" {...register("nome")} />
        <CampoTexto id="dispositivo-fabricante" rotulo="Fabricante" {...register("fabricante")} />
        <CampoTexto id="dispositivo-modelo" rotulo="Modelo" {...register("modelo")} />
        <CampoSelecao
          id="dispositivo-status"
          rotulo="Situação"
          name="status"
          control={control}
          opcoes={OPCOES_STATUS}
        />
      </div>
      <CampoTextoArea
        id="dispositivo-observacoes"
        rotulo="Observações"
        rows={2}
        {...register("observacoes")}
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
