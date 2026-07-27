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

export interface ValoresFormularioVinculo {
  contratoId: string;
  matriculaEsocial: string;
  tipoVinculo: Esquema<"Vinculo">["tipoVinculo"] | "";
  unidadeId: string;
  departamentoId: string;
  centroCustoId: string;
  cargoId: string;
  dataInicio: string;
  principal: boolean;
  apuraPonto: boolean;
}

const OPCOES_TIPO_VINCULO = [
  { valor: "empregado", rotulo: "Empregado" },
  { valor: "estagiario", rotulo: "Estagiário" },
  { valor: "aprendiz", rotulo: "Aprendiz" },
  { valor: "temporario", rotulo: "Temporário" },
  { valor: "avulso", rotulo: "Avulso" },
  { valor: "autonomo", rotulo: "Autônomo" },
  { valor: "cooperado", rotulo: "Cooperado" },
  { valor: "diretor", rotulo: "Diretor" },
  { valor: "servidor", rotulo: "Servidor" },
];

function valoresIniciais(): ValoresFormularioVinculo {
  return {
    contratoId: "",
    matriculaEsocial: "",
    tipoVinculo: "",
    unidadeId: "",
    departamentoId: "",
    centroCustoId: "",
    cargoId: "",
    dataInicio: "",
    principal: true,
    apuraPonto: true,
  };
}

export function paraCorpoDeVinculo(
  valores: ValoresFormularioVinculo,
  colaboradorId: string,
  empresaId: string,
): Esquema<"VinculoCriar"> {
  const corpo: Record<string, unknown> = {
    colaboradorId,
    empresaId,
    matriculaEsocial: valores.matriculaEsocial,
    dataInicio: valores.dataInicio,
    principal: valores.principal,
    apuraPonto: valores.apuraPonto,
  };
  if (valores.contratoId) corpo.contratoId = valores.contratoId;
  if (valores.tipoVinculo) corpo.tipoVinculo = valores.tipoVinculo;
  if (valores.unidadeId) corpo.unidadeId = valores.unidadeId;
  if (valores.departamentoId) corpo.departamentoId = valores.departamentoId;
  if (valores.centroCustoId) corpo.centroCustoId = valores.centroCustoId;
  if (valores.cargoId) corpo.cargoId = valores.cargoId;
  return corpo as Esquema<"VinculoCriar">;
}

interface FormularioVinculoProps {
  contratos: Esquema<"Contrato">[];
  cargos: Esquema<"Cargo">[];
  departamentos: Esquema<"Departamento">[];
  centrosCusto: Esquema<"CentroCusto">[];
  unidades: Esquema<"Unidade">[];
  salvando: boolean;
  erro?: string | undefined;
  aoSalvar: (valores: ValoresFormularioVinculo) => void;
  aoCancelar: () => void;
}

/**
 * Só criação — **não há `atualizarVinculo`** no contrato (achado §2/§6 do
 * PCF). Para mudar de situação depois de criado, a única operação é
 * `encerrarVinculo` (ver `DialogoEncerrarVinculo`).
 */
export function FormularioVinculo({
  contratos,
  cargos,
  departamentos,
  centrosCusto,
  unidades,
  salvando,
  erro,
  aoSalvar,
  aoCancelar,
}: FormularioVinculoProps) {
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<ValoresFormularioVinculo>({ defaultValues: valoresIniciais() });

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
        <CampoTexto
          id="vinculo-matricula-esocial"
          rotulo="Matrícula eSocial"
          obrigatorio
          erro={errors.matriculaEsocial?.message}
          {...register("matriculaEsocial", { required: "Informe a matrícula do eSocial." })}
        />
        <CampoTexto
          id="vinculo-inicio"
          rotulo="Início do vínculo"
          type="date"
          obrigatorio
          erro={errors.dataInicio?.message}
          {...register("dataInicio", { required: "Informe o início do vínculo." })}
        />
        <CampoSelecao
          id="vinculo-tipo"
          rotulo="Natureza do vínculo"
          name="tipoVinculo"
          control={control}
          permitirVazio
          opcoes={OPCOES_TIPO_VINCULO}
        />
        <CampoSelecao
          id="vinculo-contrato"
          rotulo="Contrato de origem"
          name="contratoId"
          control={control}
          permitirVazio
          opcoes={contratos.map((c) => ({
            valor: c.id ?? "",
            rotulo: c.numero ?? c.tipo ?? c.id ?? "",
          }))}
        />
        <CampoSelecao
          id="vinculo-unidade"
          rotulo="Unidade"
          name="unidadeId"
          control={control}
          permitirVazio
          opcoes={unidades.map((u) => ({ valor: u.id ?? "", rotulo: u.nome ?? u.id ?? "" }))}
        />
        <CampoSelecao
          id="vinculo-departamento"
          rotulo="Departamento"
          name="departamentoId"
          control={control}
          permitirVazio
          opcoes={departamentos.map((d) => ({ valor: d.id ?? "", rotulo: d.nome ?? d.id ?? "" }))}
        />
        <CampoSelecao
          id="vinculo-centro-custo"
          rotulo="Centro de custo"
          name="centroCustoId"
          control={control}
          permitirVazio
          opcoes={centrosCusto.map((c) => ({ valor: c.id ?? "", rotulo: c.nome ?? c.id ?? "" }))}
        />
        <CampoSelecao
          id="vinculo-cargo"
          rotulo="Cargo"
          name="cargoId"
          control={control}
          permitirVazio
          opcoes={cargos.map((c) => ({ valor: c.id ?? "", rotulo: c.nome ?? c.id ?? "" }))}
        />
      </div>
      <div className="flex flex-wrap gap-6">
        <CampoCheckbox
          id="vinculo-principal"
          rotulo="Vínculo principal"
          name="principal"
          control={control}
        />
        <CampoCheckbox
          id="vinculo-apura-ponto"
          rotulo="Entra na apuração de ponto"
          name="apuraPonto"
          control={control}
        />
      </div>
      <DialogoRodape>
        <Botao type="button" variant="secundaria" onClick={aoCancelar} disabled={salvando}>
          Cancelar
        </Botao>
        <Botao type="submit" disabled={salvando}>
          {salvando ? "Salvando…" : "Criar vínculo"}
        </Botao>
      </DialogoRodape>
    </form>
  );
}
