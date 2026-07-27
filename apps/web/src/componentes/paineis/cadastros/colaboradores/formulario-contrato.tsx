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

export interface ValoresFormularioContrato {
  numero: string;
  tipo: Esquema<"Contrato">["tipo"] | "";
  regimeJornada: Esquema<"Contrato">["regimeJornada"] | "";
  cargoId: string;
  departamentoId: string;
  centroCustoId: string;
  unidadeId: string;
  dataInicio: string;
  dataFim: string;
  salario: string;
  tipoSalario: Esquema<"Contrato">["tipoSalario"] | "";
  cargaHorariaSemanalMinutos: string;
  controleJornada: boolean;
  status: Esquema<"Contrato">["status"] | "";
}

const OPCOES_TIPO = [
  { valor: "clt", rotulo: "CLT" },
  { valor: "aprendiz", rotulo: "Aprendiz" },
  { valor: "estagio", rotulo: "Estágio" },
  { valor: "temporario", rotulo: "Temporário" },
  { valor: "intermitente", rotulo: "Intermitente" },
  { valor: "avulso", rotulo: "Avulso" },
  { valor: "autonomo", rotulo: "Autônomo" },
  { valor: "pj", rotulo: "PJ" },
  { valor: "socio", rotulo: "Sócio" },
  { valor: "servidor", rotulo: "Servidor" },
];

const OPCOES_REGIME = [
  { valor: "fixa", rotulo: "Fixa" },
  { valor: "flexivel", rotulo: "Flexível" },
  { valor: "livre", rotulo: "Livre" },
  { valor: "escala", rotulo: "Escala" },
  { valor: "12x36", rotulo: "12x36" },
  { valor: "parcial", rotulo: "Parcial" },
  { valor: "teletrabalho", rotulo: "Teletrabalho" },
  { valor: "externo", rotulo: "Externo" },
  { valor: "sobreaviso", rotulo: "Sobreaviso" },
];

const OPCOES_TIPO_SALARIO = [
  { valor: "mensal", rotulo: "Mensal" },
  { valor: "horista", rotulo: "Horista" },
  { valor: "diarista", rotulo: "Diarista" },
  { valor: "semanal", rotulo: "Semanal" },
  { valor: "comissionado", rotulo: "Comissionado" },
  { valor: "tarefa", rotulo: "Tarefa" },
];

const OPCOES_STATUS = [
  { valor: "rascunho", rotulo: "Rascunho" },
  { valor: "ativo", rotulo: "Ativo" },
  { valor: "suspenso", rotulo: "Suspenso" },
  { valor: "encerrado", rotulo: "Encerrado" },
];

function valoresIniciais(contrato: Esquema<"Contrato"> | null): ValoresFormularioContrato {
  return {
    numero: contrato?.numero ?? "",
    tipo: contrato?.tipo ?? "",
    regimeJornada: contrato?.regimeJornada ?? "",
    cargoId: contrato?.cargoId ?? "",
    departamentoId: contrato?.departamentoId ?? "",
    centroCustoId: contrato?.centroCustoId ?? "",
    unidadeId: contrato?.unidadeId ?? "",
    dataInicio: contrato?.dataInicio ?? "",
    dataFim: contrato?.dataFim ?? "",
    salario: contrato?.salario != null ? String(contrato.salario) : "",
    tipoSalario: contrato?.tipoSalario ?? "",
    cargaHorariaSemanalMinutos:
      contrato?.cargaHorariaSemanalMinutos != null
        ? String(contrato.cargaHorariaSemanalMinutos)
        : "",
    controleJornada: contrato?.controleJornada ?? true,
    status: contrato?.status ?? "ativo",
  };
}

export function paraCorpoDeContrato(
  valores: ValoresFormularioContrato,
  colaboradorId: string,
  empresaId: string,
): Esquema<"ContratoCriar"> | Esquema<"ContratoAtualizar"> {
  const corpo: Record<string, unknown> = {
    colaboradorId,
    empresaId,
    dataInicio: valores.dataInicio,
    controleJornada: valores.controleJornada,
  };
  if (valores.numero) corpo.numero = valores.numero;
  if (valores.tipo) corpo.tipo = valores.tipo;
  if (valores.regimeJornada) corpo.regimeJornada = valores.regimeJornada;
  if (valores.cargoId) corpo.cargoId = valores.cargoId;
  if (valores.departamentoId) corpo.departamentoId = valores.departamentoId;
  if (valores.centroCustoId) corpo.centroCustoId = valores.centroCustoId;
  if (valores.unidadeId) corpo.unidadeId = valores.unidadeId;
  if (valores.dataFim) corpo.dataFim = valores.dataFim;
  if (valores.salario) corpo.salario = Number(valores.salario);
  if (valores.tipoSalario) corpo.tipoSalario = valores.tipoSalario;
  if (valores.cargaHorariaSemanalMinutos)
    corpo.cargaHorariaSemanalMinutos = Number(valores.cargaHorariaSemanalMinutos);
  if (valores.status) corpo.status = valores.status;
  return corpo as Esquema<"ContratoCriar">;
}

interface FormularioContratoProps {
  contrato: Esquema<"Contrato"> | null;
  cargos: Esquema<"Cargo">[];
  departamentos: Esquema<"Departamento">[];
  centrosCusto: Esquema<"CentroCusto">[];
  unidades: Esquema<"Unidade">[];
  salvando: boolean;
  erro?: string | undefined;
  aoSalvar: (valores: ValoresFormularioContrato) => void;
  aoCancelar: () => void;
}

/** Sem `excluirContrato` no contrato — encerramento via `status: "encerrado"` (T7). */
export function FormularioContrato({
  contrato,
  cargos,
  departamentos,
  centrosCusto,
  unidades,
  salvando,
  erro,
  aoSalvar,
  aoCancelar,
}: FormularioContratoProps) {
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<ValoresFormularioContrato>({ defaultValues: valoresIniciais(contrato) });

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
        <CampoTexto id="contrato-numero" rotulo="Número do contrato" {...register("numero")} />
        <CampoSelecao
          id="contrato-tipo"
          rotulo="Tipo"
          name="tipo"
          control={control}
          permitirVazio
          opcoes={OPCOES_TIPO}
        />
        <CampoSelecao
          id="contrato-regime"
          rotulo="Regime de jornada"
          name="regimeJornada"
          control={control}
          permitirVazio
          opcoes={OPCOES_REGIME}
        />
        <CampoTexto
          id="contrato-inicio"
          rotulo="Início da vigência"
          type="date"
          obrigatorio
          erro={errors.dataInicio?.message}
          {...register("dataInicio", { required: "Informe o início da vigência." })}
        />
        <CampoTexto
          id="contrato-fim"
          rotulo="Fim da vigência"
          type="date"
          {...register("dataFim")}
        />
        <CampoSelecao
          id="contrato-cargo"
          rotulo="Cargo"
          name="cargoId"
          control={control}
          permitirVazio
          opcoes={cargos.map((c) => ({ valor: c.id ?? "", rotulo: c.nome ?? c.id ?? "" }))}
        />
        <CampoSelecao
          id="contrato-departamento"
          rotulo="Departamento"
          name="departamentoId"
          control={control}
          permitirVazio
          opcoes={departamentos.map((d) => ({ valor: d.id ?? "", rotulo: d.nome ?? d.id ?? "" }))}
        />
        <CampoSelecao
          id="contrato-centro-custo"
          rotulo="Centro de custo"
          name="centroCustoId"
          control={control}
          permitirVazio
          opcoes={centrosCusto.map((c) => ({ valor: c.id ?? "", rotulo: c.nome ?? c.id ?? "" }))}
        />
        <CampoSelecao
          id="contrato-unidade"
          rotulo="Unidade"
          name="unidadeId"
          control={control}
          permitirVazio
          opcoes={unidades.map((u) => ({ valor: u.id ?? "", rotulo: u.nome ?? u.id ?? "" }))}
        />
        <CampoSelecao
          id="contrato-tipo-salario"
          rotulo="Forma de remuneração"
          name="tipoSalario"
          control={control}
          permitirVazio
          opcoes={OPCOES_TIPO_SALARIO}
        />
        <CampoTexto
          id="contrato-salario"
          rotulo="Salário"
          type="number"
          step="0.01"
          min={0}
          {...register("salario")}
        />
        <CampoTexto
          id="contrato-carga-semanal"
          rotulo="Carga semanal (minutos)"
          type="number"
          min={0}
          dica="44h = 2640 min"
          {...register("cargaHorariaSemanalMinutos")}
        />
        <CampoSelecao
          id="contrato-status"
          rotulo="Situação"
          name="status"
          control={control}
          opcoes={OPCOES_STATUS}
        />
      </div>
      <CampoCheckbox
        id="contrato-controle-jornada"
        rotulo="Controle de jornada aplicável (desmarque só para dispensa do art. 62 da CLT)"
        name="controleJornada"
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
