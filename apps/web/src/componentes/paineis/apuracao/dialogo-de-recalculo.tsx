"use client";

import { useEffect, useState } from "react";

import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import {
  Dialogo,
  DialogoCabecalho,
  DialogoConteudo,
  DialogoDescricao,
  DialogoRodape,
  DialogoTitulo,
} from "@/componentes/ui/dialog";
import { Entrada } from "@/componentes/ui/input";
import { Rotulo } from "@/componentes/ui/label";
import {
  Selecao,
  SelecaoConteudo,
  SelecaoGatilho,
  SelecaoItem,
  SelecaoValor,
} from "@/componentes/ui/select";
import { useRecalcularApuracoes } from "@/ganchos/use-recalculo";
import type { Esquema } from "@/lib/api";

import { CampoCheckboxSimples, type OpcaoDeSelecao } from "./campos";
import { mensagemDeErroApi } from "./utilitarios";

type Motivo = NonNullable<Esquema<"RecalculoRequisicao">["motivo"]>;

const OPCOES_MOTIVO: OpcaoDeSelecao[] = [
  { valor: "manual", rotulo: "Solicitação manual" },
  { valor: "tratamento", rotulo: "Tratamento aprovado" },
  { valor: "afastamento", rotulo: "Afastamento" },
  { valor: "jornada", rotulo: "Alteração de jornada" },
  { valor: "escala", rotulo: "Alteração de escala" },
  { valor: "feriado", rotulo: "Feriado" },
  { valor: "marcacao_tardia", rotulo: "Marcação chegou depois do fechamento anterior" },
  { valor: "politica_banco", rotulo: "Alteração de política de banco de horas" },
];

/** Escopo resolvido a partir da seleção da grade OU dos filtros ativos (T11). */
export interface EscopoDeRecalculo {
  vinculoIds?: string[];
  empresaId?: string;
  unidadeId?: string;
  departamentoId?: string;
  colaboradorIds?: string[];
  /** Descrição legível do escopo, para o usuário confirmar antes de disparar. */
  descricao: string;
}

export interface DialogoDeRecalculoProps {
  aberto: boolean;
  aoMudarAberto: (aberto: boolean) => void;
  escopo: EscopoDeRecalculo | null;
  dataInicioPadrao: string;
  dataFimPadrao: string;
}

/**
 * Recálculo sob demanda (T11): `POST /v1/apuracoes/recalcular` — resposta
 * `202` com `ProcessamentoAssincrono` (`status: "enfileirado"`). **Não existe
 * endpoint de consulta de status por identificador** (achado já documentado
 * pela F4, `docs/backlog.md`) — este diálogo nunca faz *polling* de um
 * identificador; `useRecalcularApuracoes` já agenda um único *refetch* de
 * `apuracoes`/`ocorrencias` após um intervalo curto, e este diálogo só
 * informa "recálculo solicitado" e se fecha, sem travar a grade.
 */
export function DialogoDeRecalculo({
  aberto,
  aoMudarAberto,
  escopo,
  dataInicioPadrao,
  dataFimPadrao,
}: DialogoDeRecalculoProps) {
  const [dataInicio, setDataInicio] = useState(dataInicioPadrao);
  const [dataFim, setDataFim] = useState(dataFimPadrao);
  const [motivo, setMotivo] = useState<Motivo>("manual");
  const [forcar, setForcar] = useState(false);

  const recalcular = useRecalcularApuracoes();

  useEffect(() => {
    if (aberto) {
      setDataInicio(dataInicioPadrao);
      setDataFim(dataFimPadrao);
      setMotivo("manual");
      setForcar(false);
      recalcular.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- só reinicializa quando o diálogo abre, não a cada digitação.
  }, [aberto, dataInicioPadrao, dataFimPadrao]);

  const escopoValido = Boolean(
    escopo && (escopo.vinculoIds?.length || escopo.colaboradorIds?.length || escopo.empresaId),
  );

  function disparar() {
    if (!escopo || !escopoValido) return;
    const corpo: Esquema<"RecalculoRequisicao"> = {
      dataInicio,
      dataFim,
      motivo,
      ...(forcar ? { forcar: true } : {}),
      ...(escopo.vinculoIds?.length ? { vinculoIds: escopo.vinculoIds } : {}),
      ...(!escopo.vinculoIds?.length && escopo.colaboradorIds?.length
        ? { colaboradorIds: escopo.colaboradorIds }
        : {}),
      ...(escopo.empresaId ? { empresaId: escopo.empresaId } : {}),
      ...(escopo.unidadeId ? { unidadeId: escopo.unidadeId } : {}),
      ...(escopo.departamentoId ? { departamentoId: escopo.departamentoId } : {}),
    };
    recalcular.mutate(corpo);
  }

  return (
    <Dialogo open={aberto} onOpenChange={aoMudarAberto}>
      <DialogoConteudo>
        <DialogoCabecalho>
          <DialogoTitulo>Recalcular apuração</DialogoTitulo>
          <DialogoDescricao>
            {escopo?.descricao ?? "Selecione ao menos um vínculo ou filtre por empresa."}
          </DialogoDescricao>
        </DialogoCabecalho>

        {recalcular.isSuccess ? (
          <Alerta variant="sucesso">
            <AlertaDescricao>
              Recálculo solicitado (situação: enfileirado). A grade é atualizada automaticamente em
              instantes — se preferir, atualize manualmente os filtros para ver o resultado agora.
            </AlertaDescricao>
          </Alerta>
        ) : (
          <div className="flex flex-col gap-4">
            {recalcular.isError ? (
              <Alerta variant="erro">
                <AlertaDescricao>{mensagemDeErroApi(recalcular.error)}</AlertaDescricao>
              </Alerta>
            ) : null}

            {!escopoValido ? (
              <Alerta variant="atencao">
                <AlertaDescricao>
                  Selecione vínculos na grade (seleção múltipla) ou escolha um filtro de empresa
                  antes de recalcular.
                </AlertaDescricao>
              </Alerta>
            ) : null}

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1">
                <Rotulo htmlFor="recalculo-data-inicio">Início do intervalo</Rotulo>
                <Entrada
                  id="recalculo-data-inicio"
                  type="date"
                  value={dataInicio}
                  onChange={(evento) => {
                    setDataInicio(evento.target.value);
                  }}
                />
              </div>
              <div className="flex flex-col gap-1">
                <Rotulo htmlFor="recalculo-data-fim">Fim do intervalo</Rotulo>
                <Entrada
                  id="recalculo-data-fim"
                  type="date"
                  value={dataFim}
                  onChange={(evento) => {
                    setDataFim(evento.target.value);
                  }}
                />
              </div>
            </div>

            <div className="flex flex-col gap-1">
              <Rotulo htmlFor="recalculo-motivo">Motivo *</Rotulo>
              <Selecao value={motivo} onValueChange={(valor) => setMotivo(valor as Motivo)}>
                <SelecaoGatilho id="recalculo-motivo" className="w-full">
                  <SelecaoValor />
                </SelecaoGatilho>
                <SelecaoConteudo>
                  {OPCOES_MOTIVO.map((opcao) => (
                    <SelecaoItem key={opcao.valor} value={opcao.valor}>
                      {opcao.rotulo}
                    </SelecaoItem>
                  ))}
                </SelecaoConteudo>
              </Selecao>
            </div>

            <CampoCheckboxSimples
              id="recalculo-forcar"
              rotulo="Forçar recálculo mesmo sem mudança nos insumos (diagnóstico)"
              marcado={forcar}
              aoMudar={setForcar}
            />
          </div>
        )}

        <DialogoRodape>
          <Botao type="button" variant="secundaria" onClick={() => aoMudarAberto(false)}>
            {recalcular.isSuccess ? "Fechar" : "Cancelar"}
          </Botao>
          {!recalcular.isSuccess ? (
            <Botao
              type="button"
              disabled={!escopoValido || recalcular.isPending}
              onClick={disparar}
            >
              {recalcular.isPending ? "Solicitando…" : "Recalcular"}
            </Botao>
          ) : null}
        </DialogoRodape>
      </DialogoConteudo>
    </Dialogo>
  );
}
