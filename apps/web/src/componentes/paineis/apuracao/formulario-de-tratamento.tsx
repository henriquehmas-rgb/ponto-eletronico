"use client";

import { useMemo } from "react";
import { useForm } from "react-hook-form";

import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import { DialogoRodape } from "@/componentes/ui/dialog";
import type { Esquema } from "@/lib/api";

import { CampoSelecao, CampoTexto, CampoTextoArea, type OpcaoDeSelecao } from "./campos";

export interface ValoresFormularioDeTratamento {
  tipoTratamentoId: string;
  motivo: string;
  observacao: string;
  datahoraProposta: string;
  sentido: "entrada" | "saida" | "indefinido" | "";
  marcacaoId: string;
  minutosAjuste: string;
}

const VALORES_INICIAIS: ValoresFormularioDeTratamento = {
  tipoTratamentoId: "",
  motivo: "",
  observacao: "",
  datahoraProposta: "",
  sentido: "",
  marcacaoId: "",
  minutosAjuste: "",
};

/** `datetime-local` não aceita o `Z`/offset do ISO — recorta para `AAAA-MM-DDTHH:mm`. */
function paraDatetimeLocal(iso: string | undefined): string {
  if (!iso) return "";
  const data = new Date(iso);
  if (Number.isNaN(data.getTime())) return "";
  const par = (n: number) => String(n).padStart(2, "0");
  return `${data.getFullYear()}-${par(data.getMonth() + 1)}-${par(data.getDate())}T${par(data.getHours())}:${par(data.getMinutes())}`;
}

/** Valores iniciais do formulário a partir de um `Tratamento` existente (modo edição). */
export function valoresIniciaisDeTratamento(
  tratamento: Esquema<"Tratamento"> | null,
): ValoresFormularioDeTratamento {
  if (!tratamento) return VALORES_INICIAIS;
  return {
    tipoTratamentoId: tratamento.tipoTratamentoId ?? "",
    motivo: tratamento.motivo ?? "",
    observacao: tratamento.observacao ?? "",
    datahoraProposta: paraDatetimeLocal(tratamento.datahoraProposta),
    sentido: tratamento.sentido ?? "",
    marcacaoId: tratamento.marcacaoId ?? "",
    minutosAjuste: tratamento.minutosAjuste !== undefined ? String(tratamento.minutosAjuste) : "",
  };
}

const OPCOES_SENTIDO: OpcaoDeSelecao[] = [
  { valor: "entrada", rotulo: "Entrada" },
  { valor: "saida", rotulo: "Saída" },
  { valor: "indefinido", rotulo: "Indefinido" },
];

/**
 * Monta `TratamentoCriar` a partir dos valores do formulário — só inclui os
 * campos relevantes para a `categoria` do tipo de tratamento selecionado, e
 * NUNCA um campo que sugira alterar a marcação em si (`marcacaoId`, quando
 * presente, é uma REFERÊNCIA à marcação existente para desconsiderá-la na
 * apuração — a marcação permanece intacta, glossário §1).
 */
export function paraCorpoDeTratamento(
  valores: ValoresFormularioDeTratamento,
  contexto: { colaboradorId: string; vinculoId: string; dataReferencia: string },
  categoria: Esquema<"TipoTratamento">["categoria"] | undefined,
): Esquema<"TratamentoCriar"> {
  const corpo: Esquema<"TratamentoCriar"> = {
    colaboradorId: contexto.colaboradorId,
    vinculoId: contexto.vinculoId,
    tipoTratamentoId: valores.tipoTratamentoId,
    dataReferencia: contexto.dataReferencia,
    motivo: valores.motivo,
  };
  if (valores.observacao) corpo.observacao = valores.observacao;

  if (categoria === "inclusao_marcacao") {
    if (valores.datahoraProposta)
      corpo.datahoraProposta = new Date(valores.datahoraProposta).toISOString();
    if (valores.sentido) corpo.sentido = valores.sentido;
  }
  if (categoria === "desconsideracao_marcacao" && valores.marcacaoId) {
    corpo.marcacaoId = valores.marcacaoId;
  }
  if ((categoria === "ajuste_intervalo" || categoria === "ajuste_saldo") && valores.minutosAjuste) {
    corpo.minutosAjuste = Number(valores.minutosAjuste);
  }
  return corpo;
}

interface FormularioDeTratamentoProps {
  tipos: Esquema<"TipoTratamento">[];
  marcacoesDoDia: { id: string; rotulo: string }[];
  salvando: boolean;
  erro?: string | undefined;
  /** Presente = formulário em modo EDIÇÃO (pré-preenchido a partir deste tratamento). Ausente/`null` = novo tratamento. */
  tratamento?: Esquema<"Tratamento"> | null;
  aoSalvar: (
    valores: ValoresFormularioDeTratamento,
    categoria: Esquema<"TipoTratamento">["categoria"] | undefined,
  ) => void;
  aoCancelar: () => void;
}

/**
 * Formulário de tratamento — criação OU atualização (T10), a única forma de
 * correção que esta grade oferece. Nenhum rótulo aqui é "editar
 * marcação"/"corrigir marcação": o vocabulário do formulário inteiro é
 * "tratamento".
 */
export function FormularioDeTratamento({
  tipos,
  marcacoesDoDia,
  salvando,
  erro,
  tratamento = null,
  aoSalvar,
  aoCancelar,
}: FormularioDeTratamentoProps) {
  const {
    register,
    handleSubmit,
    control,
    watch,
    formState: { errors },
  } = useForm<ValoresFormularioDeTratamento>({
    defaultValues: valoresIniciaisDeTratamento(tratamento),
  });

  const tipoTratamentoId = watch("tipoTratamentoId");
  const categoriaSelecionada = useMemo(
    () => tipos.find((tipo) => tipo.id === tipoTratamentoId)?.categoria,
    [tipos, tipoTratamentoId],
  );

  const opcoesTipos: OpcaoDeSelecao[] = tipos.map((tipo) => ({
    valor: tipo.id ?? "",
    rotulo: tipo.nome ?? tipo.codigo ?? tipo.id ?? "",
  }));
  const opcoesMarcacoes: OpcaoDeSelecao[] = marcacoesDoDia.map((m) => ({
    valor: m.id,
    rotulo: m.rotulo,
  }));

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={handleSubmit((valores) => {
        aoSalvar(valores, categoriaSelecionada);
      })}
    >
      {erro ? (
        <Alerta variant="erro">
          <AlertaDescricao>{erro}</AlertaDescricao>
        </Alerta>
      ) : null}

      <CampoSelecao
        id="tratamento-tipo"
        rotulo="Tipo de tratamento"
        obrigatorio
        erro={errors.tipoTratamentoId?.message}
        name="tipoTratamentoId"
        control={control}
        opcoes={opcoesTipos}
      />

      {categoriaSelecionada === "inclusao_marcacao" ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <CampoTexto
            id="tratamento-datahora-proposta"
            rotulo="Horário proposto"
            type="datetime-local"
            {...register("datahoraProposta")}
          />
          <CampoSelecao
            id="tratamento-sentido"
            rotulo="Sentido"
            name="sentido"
            control={control}
            opcoes={OPCOES_SENTIDO}
            permitirVazio
          />
        </div>
      ) : null}

      {categoriaSelecionada === "desconsideracao_marcacao" ? (
        <CampoSelecao
          id="tratamento-marcacao"
          rotulo="Marcação a desconsiderar na apuração"
          dica="A marcação permanece intacta; ela só deixa de ser considerada no cálculo deste dia."
          name="marcacaoId"
          control={control}
          opcoes={opcoesMarcacoes}
          permitirVazio
        />
      ) : null}

      {categoriaSelecionada === "ajuste_intervalo" || categoriaSelecionada === "ajuste_saldo" ? (
        <CampoTexto
          id="tratamento-minutos-ajuste"
          rotulo="Ajuste (minutos)"
          type="number"
          dica="Positivo credita, negativo debita."
          {...register("minutosAjuste")}
        />
      ) : null}

      <CampoTextoArea
        id="tratamento-motivo"
        rotulo="Motivo"
        obrigatorio
        erro={errors.motivo?.message}
        {...register("motivo", { required: "Informe o motivo do tratamento." })}
      />
      <CampoTextoArea id="tratamento-observacao" rotulo="Observação" {...register("observacao")} />

      <DialogoRodape>
        <Botao type="button" variant="secundaria" onClick={aoCancelar} disabled={salvando}>
          Cancelar
        </Botao>
        <Botao type="submit" disabled={salvando || !tipoTratamentoId}>
          {salvando ? "Salvando…" : tratamento ? "Salvar alterações" : "Registrar tratamento"}
        </Botao>
      </DialogoRodape>
    </form>
  );
}
