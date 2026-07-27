"use client";

import { useState } from "react";

import { mensagemDeErroApi } from "@/componentes/paineis/cadastros/_shared/erro-amigavel";
import {
  FormularioContrato,
  paraCorpoDeContrato,
  type ValoresFormularioContrato,
} from "@/componentes/paineis/cadastros/colaboradores/formulario-contrato";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Selo } from "@/componentes/ui/badge";
import { Botao } from "@/componentes/ui/button";
import { Dialogo, DialogoCabecalho, DialogoConteudo, DialogoTitulo } from "@/componentes/ui/dialog";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { useAtualizarContrato, useContratos, useCriarContrato } from "@/ganchos/use-contratos";
import { formatarData } from "@/lib/formatacao";
import type { Esquema } from "@/lib/api";

interface SecaoContratosProps {
  colaborador: Esquema<"Colaborador">;
  cargos: Esquema<"Cargo">[];
  departamentos: Esquema<"Departamento">[];
  centrosCusto: Esquema<"CentroCusto">[];
  unidades: Esquema<"Unidade">[];
}

const SELO_POR_STATUS: Record<string, "sucesso" | "atencao" | "neutro"> = {
  ativo: "sucesso",
  rascunho: "neutro",
  suspenso: "atencao",
  encerrado: "neutro",
};

export function SecaoContratos({
  colaborador,
  cargos,
  departamentos,
  centrosCusto,
  unidades,
}: SecaoContratosProps) {
  const consulta = useContratos({ colaboradorId: colaborador.id });
  const criar = useCriarContrato();
  const atualizar = useAtualizarContrato();
  const [dialogoAberto, setDialogoAberto] = useState(false);
  const [editando, setEditando] = useState<Esquema<"Contrato"> | null>(null);

  function salvar(valores: ValoresFormularioContrato) {
    if (!colaborador.id || !colaborador.empresaId) return;
    const corpo = paraCorpoDeContrato(valores, colaborador.id, colaborador.empresaId);
    if (editando?.id) {
      atualizar.mutate(
        { id: editando.id, corpo: corpo as Esquema<"ContratoAtualizar"> },
        { onSuccess: () => setDialogoAberto(false) },
      );
    } else {
      criar.mutate(corpo as Esquema<"ContratoCriar">, { onSuccess: () => setDialogoAberto(false) });
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-end">
        <Botao
          tamanho="compacto"
          onClick={() => {
            setEditando(null);
            setDialogoAberto(true);
          }}
        >
          Novo contrato
        </Botao>
      </div>

      {consulta.isPending ? (
        <Esqueleto className="h-24 w-full" />
      ) : consulta.isError ? (
        <Alerta variant="erro">
          <AlertaDescricao>{mensagemDeErroApi(consulta.error)}</AlertaDescricao>
        </Alerta>
      ) : (consulta.data?.dados ?? []).length === 0 ? (
        <p className="estilo-corpo text-texto-secundario">Nenhum contrato cadastrado.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {(consulta.data?.dados ?? []).map((contrato) => (
            <li
              key={contrato.id}
              className="flex items-center justify-between gap-3 rounded-pequeno border border-borda-sutil p-3"
            >
              <div>
                <p className="estilo-corpo text-texto-primario">
                  {contrato.tipo ?? "—"} {contrato.numero ? `· nº ${contrato.numero}` : ""}
                </p>
                <p className="estilo-legenda text-texto-secundario">
                  {contrato.dataInicio ? formatarData(contrato.dataInicio) : "—"}
                  {contrato.dataFim ? ` até ${formatarData(contrato.dataFim)}` : ""}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Selo variant={SELO_POR_STATUS[contrato.status ?? ""] ?? "neutro"}>
                  {contrato.status ?? "—"}
                </Selo>
                <Botao
                  variant="secundaria"
                  tamanho="compacto"
                  onClick={() => {
                    setEditando(contrato);
                    setDialogoAberto(true);
                  }}
                >
                  Editar
                </Botao>
              </div>
            </li>
          ))}
        </ul>
      )}

      <Dialogo open={dialogoAberto} onOpenChange={setDialogoAberto}>
        <DialogoConteudo className="sm:max-w-2xl">
          <DialogoCabecalho>
            <DialogoTitulo>{editando ? "Editar contrato" : "Novo contrato"}</DialogoTitulo>
          </DialogoCabecalho>
          <FormularioContrato
            key={editando?.id ?? "novo"}
            contrato={editando}
            cargos={cargos}
            departamentos={departamentos}
            centrosCusto={centrosCusto}
            unidades={unidades}
            salvando={criar.isPending || atualizar.isPending}
            erro={
              criar.isError
                ? mensagemDeErroApi(criar.error)
                : atualizar.isError
                  ? mensagemDeErroApi(atualizar.error)
                  : undefined
            }
            aoSalvar={salvar}
            aoCancelar={() => setDialogoAberto(false)}
          />
        </DialogoConteudo>
      </Dialogo>
    </div>
  );
}
