"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState, type ReactNode } from "react";

import { type AtalhoDePeriodo, SeletorDePeriodo } from "@/componentes/dominio/seletor-de-periodo";
import { type ColunaDeTabela, TabelaDeDados } from "@/componentes/dominio/tabela-de-dados";
import { Alerta, AlertaDescricao, AlertaTitulo } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import { Cartao, CartaoCabecalho, CartaoConteudo, CartaoTitulo } from "@/componentes/ui/card";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { useExtratoBancoHoras } from "@/ganchos/use-banco-de-horas";
import { useSessaoAtual } from "@/ganchos/use-sessao";
import { api, ehErroDaApi, type Esquema } from "@/lib/api";
import { formatarData, formatarSaldo, minutosParaHHMM } from "@/lib/formatacao";
import { paramsSemUndefined } from "@/lib/formatacao-f8/parametros-de-consulta";
import { cn } from "@/lib/utils";

function paraIso(data: Date): string {
  return `${data.getFullYear()}-${String(data.getMonth() + 1).padStart(2, "0")}-${String(data.getDate()).padStart(2, "0")}`;
}

function periodoDoMes(referencia: Date): { inicio: string; fim: string } {
  const inicio = new Date(referencia.getFullYear(), referencia.getMonth(), 1);
  const fim = new Date(referencia.getFullYear(), referencia.getMonth() + 1, 0);
  return { inicio: paraIso(inicio), fim: paraIso(fim) };
}

const CLASSE_COR_POR_SINAL: Record<ReturnType<typeof formatarSaldo>["sinal"], string> = {
  credor: "text-estado-sucesso-texto",
  devedor: "text-estado-erro-texto",
  neutro: "text-texto-secundario",
};

/** Sempre saldo credor/devedor (nunca "positivo/negativo") — sinal por forma (▲/▼) e por cor, nunca só por cor. */
function CelulaDeSaldo({ minutos }: { minutos: number }): ReactNode {
  const saldo = formatarSaldo(minutos);
  return (
    <span
      className={cn(
        "estilo-tabular inline-flex items-center gap-1",
        CLASSE_COR_POR_SINAL[saldo.sinal],
      )}
    >
      <span aria-hidden="true">
        {saldo.sinal === "devedor" ? "▼" : saldo.sinal === "credor" ? "▲" : "■"}
      </span>
      {saldo.textoComSinal}
    </span>
  );
}

/** Soma de um campo de minutos sobre a apuração do período — usada só nos dois tiles de resumo, não recalcula nada que a API já não tenha mandado. */
function somarMinutos(
  linhas: Esquema<"ApuracaoDia">[] | undefined,
  campo: "trabalhadoMinutos" | "saldoMinutos",
): number {
  return (linhas ?? []).reduce((total, linha) => total + (linha[campo] ?? 0), 0);
}

export default function ExtratoDoColaborador() {
  const hoje = new Date();
  const mesAtual = periodoDoMes(hoje);
  const mesAnterior = periodoDoMes(new Date(hoje.getFullYear(), hoje.getMonth() - 1, 1));

  const atalhos: AtalhoDePeriodo[] = [
    { id: "mes-atual", rotulo: "Mês atual", inicio: mesAtual.inicio, fim: mesAtual.fim },
    {
      id: "mes-anterior",
      rotulo: "Mês anterior",
      inicio: mesAnterior.inicio,
      fim: mesAnterior.fim,
    },
  ];

  const [periodo, definirPeriodo] = useState<{ inicio: string | null; fim: string | null }>({
    inicio: mesAtual.inicio,
    fim: mesAtual.fim,
  });
  const [cursor, definirCursor] = useState<string | undefined>(undefined);

  const { data: sessaoAtual } = useSessaoAtual();
  const colaboradorId = sessaoAtual?.colaboradorId;

  const apuracoes = useQuery({
    queryKey: ["apuracoes", colaboradorId, periodo.inicio, periodo.fim],
    queryFn: async () => {
      const resultado = await api.GET("/v1/apuracoes", {
        params: {
          query: {
            ...paramsSemUndefined({ colaboradorId }),
            de: periodo.inicio ?? "",
            ate: periodo.fim ?? "",
            ordenar: "data:asc",
          },
        },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    enabled: Boolean(colaboradorId && periodo.inicio && periodo.fim),
  });

  const extrato = useExtratoBancoHoras(
    paramsSemUndefined({
      de: periodo.inicio ?? undefined,
      ate: periodo.fim ?? undefined,
      cursor,
    }),
  );

  const colunasApuracao: ColunaDeTabela<Esquema<"ApuracaoDia">>[] = [
    {
      id: "data",
      cabecalho: "Data",
      renderizarCelula: (linha) => (linha.data ? formatarData(`${linha.data}T12:00:00`) : "—"),
    },
    {
      id: "trabalhado",
      cabecalho: "Trabalhado",
      renderizarCelula: (linha) => minutosParaHHMM(linha.trabalhadoMinutos ?? 0),
    },
    {
      id: "extras",
      cabecalho: "Extras",
      renderizarCelula: (linha) => minutosParaHHMM(linha.extrasMinutos ?? 0),
    },
    {
      id: "noturno",
      cabecalho: "Adicional noturno",
      renderizarCelula: (linha) => minutosParaHHMM(linha.noturnoMinutos ?? 0),
    },
    {
      id: "saldo",
      cabecalho: "Saldo do dia",
      renderizarCelula: (linha) => <CelulaDeSaldo minutos={linha.saldoMinutos ?? 0} />,
    },
  ];

  const colunasLancamentos: ColunaDeTabela<Esquema<"BhLancamento">>[] = [
    {
      id: "data",
      cabecalho: "Data",
      renderizarCelula: (linha) =>
        linha.dataCompetencia ? formatarData(`${linha.dataCompetencia}T12:00:00`) : "—",
    },
    { id: "tipo", cabecalho: "Tipo", renderizarCelula: (linha) => linha.tipo ?? "—" },
    { id: "origem", cabecalho: "Origem", renderizarCelula: (linha) => linha.origem ?? "—" },
    {
      id: "minutos",
      cabecalho: "Lançamento",
      renderizarCelula: (linha) => <CelulaDeSaldo minutos={linha.minutosEquivalentes ?? 0} />,
    },
    {
      id: "saldoApos",
      cabecalho: "Saldo após",
      renderizarCelula: (linha) => <CelulaDeSaldo minutos={linha.saldoAposMinutos ?? 0} />,
    },
  ];

  const totalTrabalhado = somarMinutos(apuracoes.data?.dados, "trabalhadoMinutos");
  const totalSaldo = somarMinutos(apuracoes.data?.dados, "saldoMinutos");
  const saldoDoPeriodo = formatarSaldo(totalSaldo);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="estilo-titulo-pagina text-texto-primario">Extrato</h1>
        <p className="estilo-legenda mt-1 text-texto-terciario">Espelho de ponto do período</p>
      </div>

      {!apuracoes.isPending && !apuracoes.isError ? (
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-suave bg-fundo-superficie p-4 shadow-flutuante-cartao">
            <p className="estilo-legenda text-texto-terciario">Saldo do período</p>
            <p
              className={cn(
                "estilo-numero-destaque mt-2",
                CLASSE_COR_POR_SINAL[saldoDoPeriodo.sinal],
              )}
            >
              {saldoDoPeriodo.textoComSinal}
            </p>
          </div>
          <div className="rounded-suave bg-fundo-superficie p-4 shadow-flutuante-cartao">
            <p className="estilo-legenda text-texto-terciario">Horas trabalhadas</p>
            <p className="estilo-tabular mt-2 text-lg font-semibold text-texto-primario">
              {minutosParaHHMM(totalTrabalhado)}
            </p>
          </div>
        </div>
      ) : null}

      <Cartao className="rounded-suave shadow-flutuante-cartao">
        <CartaoConteudo>
          <SeletorDePeriodo
            inicio={periodo.inicio}
            fim={periodo.fim}
            atalhos={atalhos}
            aoSelecionarIntervalo={(inicio, fim) => {
              definirPeriodo({ inicio, fim });
              definirCursor(undefined);
            }}
          />
        </CartaoConteudo>
      </Cartao>

      <Cartao className="rounded-suave shadow-flutuante-cartao">
        <CartaoCabecalho>
          <CartaoTitulo>Apuração do período</CartaoTitulo>
        </CartaoCabecalho>
        <CartaoConteudo>
          {apuracoes.isPending ? (
            <Esqueleto className="h-40 w-full" />
          ) : apuracoes.isError ? (
            <Alerta variant="erro">
              <AlertaTitulo>Não foi possível carregar a apuração</AlertaTitulo>
              <AlertaDescricao>
                {ehErroDaApi(apuracoes.error)
                  ? apuracoes.error.problema?.title
                  : "Tente novamente em instantes."}
              </AlertaDescricao>
            </Alerta>
          ) : (
            <TabelaDeDados
              linhas={apuracoes.data?.dados ?? []}
              colunas={colunasApuracao}
              obterId={(linha) => linha.id ?? `${linha.data ?? ""}-${linha.vinculoId ?? ""}`}
              mensagemVazia="Nenhuma apuração neste período."
            />
          )}
        </CartaoConteudo>
      </Cartao>

      <Cartao className="rounded-suave shadow-flutuante-cartao">
        <CartaoCabecalho>
          <CartaoTitulo>Extrato de banco de horas</CartaoTitulo>
        </CartaoCabecalho>
        <CartaoConteudo className="flex flex-col gap-3">
          {extrato.isPending ? (
            <Esqueleto className="h-40 w-full" />
          ) : extrato.isError ? (
            <Alerta variant="erro">
              <AlertaTitulo>Não foi possível carregar o extrato</AlertaTitulo>
              <AlertaDescricao>
                {ehErroDaApi(extrato.error)
                  ? extrato.error.problema?.title
                  : "Tente novamente em instantes."}
              </AlertaDescricao>
            </Alerta>
          ) : (
            <>
              <TabelaDeDados
                linhas={extrato.data?.lancamentos ?? []}
                colunas={colunasLancamentos}
                obterId={(linha) => linha.id ?? `${linha.sequencia ?? ""}`}
                mensagemVazia="Nenhum lançamento neste período."
              />
              <div className="flex items-center justify-between">
                <Botao
                  type="button"
                  variant="secundaria"
                  disabled={!extrato.data?.paginacao?.cursorAnterior}
                  onClick={() => {
                    definirCursor(extrato.data?.paginacao?.cursorAnterior);
                  }}
                >
                  Página anterior
                </Botao>
                <Botao
                  type="button"
                  variant="secundaria"
                  disabled={!extrato.data?.paginacao?.temMais}
                  onClick={() => {
                    definirCursor(extrato.data?.paginacao?.proximoCursor);
                  }}
                >
                  Próxima página
                </Botao>
              </div>
            </>
          )}
        </CartaoConteudo>
      </Cartao>

      <Botao asChild variant="secundaria" tamanho="toque" className="rounded-grande">
        <Link href="/eu/comprovantes">Ver comprovantes</Link>
      </Botao>
    </div>
  );
}
