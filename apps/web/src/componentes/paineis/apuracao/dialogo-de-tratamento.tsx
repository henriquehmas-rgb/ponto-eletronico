"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  LinhaDoTempoDeMarcacoes,
  type MarcacaoDaLinhaDoTempo,
} from "@/componentes/dominio/linha-do-tempo-de-marcacoes";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Selo } from "@/componentes/ui/badge";
import { Botao } from "@/componentes/ui/button";
import {
  Dialogo,
  DialogoCabecalho,
  DialogoConteudo,
  DialogoDescricao,
  DialogoTitulo,
} from "@/componentes/ui/dialog";
import { Entrada } from "@/componentes/ui/input";
import { Esqueleto } from "@/componentes/ui/skeleton";
import {
  TabelaBase,
  TabelaBaseCabecalho,
  TabelaBaseCabecalhoDeColuna,
  TabelaBaseCelula,
  TabelaBaseCorpo,
  TabelaBaseLinha,
} from "@/componentes/ui/table";
import { useApuracaoDoVinculoNoDia } from "@/ganchos/use-apuracoes";
import { useAtualizarOcorrencia, useOcorrencias } from "@/ganchos/use-ocorrencias";
import {
  useAtualizarTratamento,
  useCancelarTratamento,
  useCriarTratamento,
  useDecidirTratamento,
  useTiposTratamento,
  useTratamentosDoDia,
} from "@/ganchos/use-tratamentos";
import { api, type Esquema } from "@/lib/api";
import { formatarData, formatarHora, minutosParaHHMM } from "@/lib/formatacao";
import { PortaoDePermissao } from "@/lib/permissoes";

import {
  FormularioDeTratamento,
  paraCorpoDeTratamento,
  type ValoresFormularioDeTratamento,
} from "./formulario-de-tratamento";
import type { CelulaSelecionada } from "./grade-de-apuracao";
import {
  mensagemDeErroApi,
  ROTULO_CODIGO_OCORRENCIA,
  ROTULO_SEVERIDADE_OCORRENCIA,
  ROTULO_STATUS_APURACAO,
  ROTULO_STATUS_TRATAMENTO,
  ROTULO_TIPO_DIA,
  VARIANTE_SEVERIDADE_OCORRENCIA,
  VARIANTE_STATUS_APURACAO,
  VARIANTE_STATUS_TRATAMENTO,
} from "./utilitarios";

export interface DialogoDeTratamentoProps {
  celula: CelulaSelecionada | null;
  aoFechar: () => void;
}

function limitesDoDia(data: string): { de: string; ate: string } {
  const [ano = 1970, mes = 1, dia = 1] = data.split("-").map(Number);
  const inicio = new Date(ano, mes - 1, dia, 0, 0, 0, 0);
  const fim = new Date(ano, mes - 1, dia, 23, 59, 59, 999);
  return { de: inicio.toISOString(), ate: fim.toISOString() };
}

/**
 * Marcações do dia, buscadas DIRETO de `GET /v1/marcacoes` (não dependem de
 * já existir `ApuracaoDia` para o dia — um dia ainda não apurado também pode
 * receber um tratamento, ex. lançamento retroativo antes do primeiro
 * recálculo).
 */
function useMarcacoesDoDia(vinculoId: string | undefined, data: string | undefined) {
  return useQuery({
    queryKey: ["marcacoes-do-dia", vinculoId, data],
    queryFn: async () => {
      if (!vinculoId || !data) return [];
      const { de, ate } = limitesDoDia(data);
      const resultado = await api.GET("/v1/marcacoes", {
        params: { query: { vinculoId, de, ate, ordenar: "datahoraMarcacao:asc", limite: 100 } },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data?.dados ?? [];
    },
    enabled: Boolean(vinculoId && data),
  });
}

function paraMarcacaoDaLinhaDoTempo(m: Esquema<"Marcacao">): MarcacaoDaLinhaDoTempo | null {
  if (!m.id || !m.datahoraMarcacao || !m.canal) return null;
  return {
    id: m.id,
    datahoraMarcacao: m.datahoraMarcacao,
    canal: m.canal,
    ...(m.nsr !== undefined ? { nsr: m.nsr } : {}),
    ...(m.sentidoInformado ? { sentidoInformado: m.sentidoInformado } : {}),
  };
}

/**
 * Detalhe do dia + tratamento (T10) — a ÚNICA porta de correção de jornada
 * desta grade. Abre a partir de uma célula da grade de apuração (T9); nenhum
 * controle aqui chama, sugere ou nomeia "editar marcação" — toda correção
 * passa por `POST`/`PATCH`/`DELETE /v1/tratamentos*`.
 */
export function DialogoDeTratamento({ celula, aoFechar }: DialogoDeTratamentoProps) {
  const [editando, setEditando] = useState<Esquema<"Tratamento"> | null>(null);
  const [confirmandoCancelamentoId, setConfirmandoCancelamentoId] = useState<string | null>(null);
  const [comentarios, setComentarios] = useState<Record<string, string>>({});
  const [resolucaoPorOcorrencia, setResolucaoPorOcorrencia] = useState<Record<string, string>>({});

  useEffect(() => {
    // Cada célula aberta começa um novo ciclo: nunca herda edição/confirmação da célula anterior.
    setEditando(null);
    setConfirmandoCancelamentoId(null);
  }, [celula?.vinculoId, celula?.data]);

  const vinculoId = celula?.vinculoId;
  const data = celula?.data;

  const apuracao = useApuracaoDoVinculoNoDia(vinculoId, data);
  const marcacoes = useMarcacoesDoDia(vinculoId, data);
  const tratamentos = useTratamentosDoDia(vinculoId, data);
  const ocorrencias = useOcorrencias({ colaboradorId: celula?.colaboradorId, de: data, ate: data });
  const tipos = useTiposTratamento({ ativo: true });

  const criar = useCriarTratamento();
  const atualizar = useAtualizarTratamento();
  const cancelar = useCancelarTratamento();
  const decidir = useDecidirTratamento();
  const atualizarOcorrencia = useAtualizarOcorrencia();

  const marcacoesMapeadas = useMemo(
    () =>
      (marcacoes.data ?? [])
        .map(paraMarcacaoDaLinhaDoTempo)
        .filter((m): m is MarcacaoDaLinhaDoTempo => m !== null),
    [marcacoes.data],
  );
  const opcoesMarcacoes = useMemo(
    () =>
      (marcacoes.data ?? [])
        .filter((m): m is Esquema<"Marcacao"> & { id: string } => Boolean(m.id))
        .map((m) => ({
          id: m.id,
          rotulo: m.datahoraMarcacao ? formatarHora(m.datahoraMarcacao) : m.id,
        })),
    [marcacoes.data],
  );

  function fechar() {
    setEditando(null);
    setConfirmandoCancelamentoId(null);
    aoFechar();
  }

  function salvar(
    valores: ValoresFormularioDeTratamento,
    categoria: Esquema<"TipoTratamento">["categoria"] | undefined,
  ) {
    if (!celula) return;
    const corpo = paraCorpoDeTratamento(
      valores,
      {
        colaboradorId: celula.colaboradorId,
        vinculoId: celula.vinculoId,
        dataReferencia: celula.data,
      },
      categoria,
    );
    if (editando?.id) {
      atualizar.mutate(
        { tratamentoId: editando.id, corpo },
        { onSuccess: () => setEditando(null) },
      );
    } else {
      criar.mutate(corpo);
    }
  }

  const mutacaoAtiva = editando ? atualizar : criar;

  return (
    <Dialogo
      open={Boolean(celula)}
      onOpenChange={(aberto) => {
        if (!aberto) fechar();
      }}
    >
      <DialogoConteudo className="sm:max-w-3xl">
        <div className="flex max-h-[78vh] flex-col gap-6 overflow-y-auto pr-1">
          <DialogoCabecalho>
            <DialogoTitulo>
              {celula?.nomeColaborador} — {celula ? formatarData(`${celula.data}T12:00:00`) : ""}
            </DialogoTitulo>
            <DialogoDescricao>
              Detalhe do dia. Toda correção de jornada é registrada como tratamento, auditado — esta
              tela nunca altera a marcação em si.
            </DialogoDescricao>
          </DialogoCabecalho>

          <ResumoDoDia apuracao={apuracao.data} carregando={apuracao.isPending} />

          <section className="flex flex-col gap-2">
            <h3 className="estilo-titulo-cartao text-texto-primario">Marcações do dia</h3>
            {marcacoes.isPending ? (
              <Esqueleto className="h-16 w-full" />
            ) : (
              <LinhaDoTempoDeMarcacoes marcacoes={marcacoesMapeadas} densidade="compacta" />
            )}
          </section>

          {apuracao.data?.componentes?.length ? (
            <section className="flex flex-col gap-2">
              <h3 className="estilo-titulo-cartao text-texto-primario">Decomposição da apuração</h3>
              <TabelaBase>
                <TabelaBaseCabecalho>
                  <TabelaBaseLinha>
                    <TabelaBaseCabecalhoDeColuna>Rubrica</TabelaBaseCabecalhoDeColuna>
                    <TabelaBaseCabecalhoDeColuna>Categoria</TabelaBaseCabecalhoDeColuna>
                    <TabelaBaseCabecalhoDeColuna>Minutos</TabelaBaseCabecalhoDeColuna>
                    <TabelaBaseCabecalhoDeColuna>Equivalente</TabelaBaseCabecalhoDeColuna>
                  </TabelaBaseLinha>
                </TabelaBaseCabecalho>
                <TabelaBaseCorpo>
                  {apuracao.data.componentes.map((componente) => (
                    <TabelaBaseLinha
                      key={componente.id ?? `${componente.codigo}-${componente.inicio}`}
                    >
                      <TabelaBaseCelula>
                        {componente.descricao ?? componente.codigo}
                      </TabelaBaseCelula>
                      <TabelaBaseCelula>{componente.categoria}</TabelaBaseCelula>
                      <TabelaBaseCelula className="estilo-tabular">
                        {componente.minutos !== undefined
                          ? minutosParaHHMM(componente.minutos)
                          : "—"}
                      </TabelaBaseCelula>
                      <TabelaBaseCelula className="estilo-tabular">
                        {componente.minutosEquivalentes !== undefined
                          ? minutosParaHHMM(componente.minutosEquivalentes)
                          : "—"}
                      </TabelaBaseCelula>
                    </TabelaBaseLinha>
                  ))}
                </TabelaBaseCorpo>
              </TabelaBase>
            </section>
          ) : null}

          <section className="flex flex-col gap-2">
            <h3 className="estilo-titulo-cartao text-texto-primario">Tratamentos do dia</h3>
            {tratamentos.isPending ? (
              <Esqueleto className="h-12 w-full" />
            ) : (tratamentos.data?.dados ?? []).length === 0 ? (
              <p className="estilo-corpo text-texto-secundario">
                Nenhum tratamento registrado neste dia.
              </p>
            ) : (
              <ul className="flex flex-col gap-2">
                {(tratamentos.data?.dados ?? []).map((tratamento) => {
                  const podeAlterar =
                    tratamento.status === "rascunho" || tratamento.status === "pendente";
                  return (
                    <li
                      key={tratamento.id}
                      className="flex flex-col gap-2 rounded-medio border border-borda-sutil p-3"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <Selo
                            variant={
                              tratamento.status
                                ? VARIANTE_STATUS_TRATAMENTO[tratamento.status]
                                : "neutro"
                            }
                          >
                            {tratamento.status ? ROTULO_STATUS_TRATAMENTO[tratamento.status] : "—"}
                          </Selo>
                          <span className="estilo-corpo text-texto-primario">
                            {tipos.data?.dados?.find((t) => t.id === tratamento.tipoTratamentoId)
                              ?.nome ?? "Tratamento"}
                          </span>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {podeAlterar ? (
                            <PortaoDePermissao permissao="tratamentos.editar">
                              <Botao
                                type="button"
                                variant="secundaria"
                                tamanho="compacto"
                                onClick={() => {
                                  setEditando(tratamento);
                                }}
                              >
                                Editar
                              </Botao>
                            </PortaoDePermissao>
                          ) : null}
                          {tratamento.status === "pendente" ? (
                            <PortaoDePermissao permissao="tratamentos.aprovar">
                              <Botao
                                type="button"
                                tamanho="compacto"
                                disabled={decidir.isPending}
                                onClick={() => {
                                  if (!tratamento.id) return;
                                  decidir.mutate({
                                    tratamentoId: tratamento.id,
                                    corpo: { decisao: "aprovar" },
                                  });
                                }}
                              >
                                Aprovar
                              </Botao>
                            </PortaoDePermissao>
                          ) : null}
                          {podeAlterar ? (
                            <PortaoDePermissao permissao="tratamentos.excluir">
                              {confirmandoCancelamentoId === tratamento.id ? (
                                <div className="flex items-center gap-1">
                                  <span className="estilo-legenda text-texto-secundario">
                                    Cancelar mesmo?
                                  </span>
                                  <Botao
                                    type="button"
                                    variant="destrutiva"
                                    tamanho="compacto"
                                    disabled={cancelar.isPending}
                                    onClick={() => {
                                      if (!tratamento.id || !celula) return;
                                      cancelar.mutate(
                                        {
                                          tratamentoId: tratamento.id,
                                          vinculoId: celula.vinculoId,
                                          data: celula.data,
                                        },
                                        { onSuccess: () => setConfirmandoCancelamentoId(null) },
                                      );
                                    }}
                                  >
                                    Confirmar
                                  </Botao>
                                  <Botao
                                    type="button"
                                    variant="secundaria"
                                    tamanho="compacto"
                                    onClick={() => setConfirmandoCancelamentoId(null)}
                                  >
                                    Voltar
                                  </Botao>
                                </div>
                              ) : (
                                <Botao
                                  type="button"
                                  variant="destrutiva"
                                  tamanho="compacto"
                                  onClick={() =>
                                    setConfirmandoCancelamentoId(tratamento.id ?? null)
                                  }
                                >
                                  Cancelar tratamento
                                </Botao>
                              )}
                            </PortaoDePermissao>
                          ) : null}
                        </div>
                      </div>
                      <p className="estilo-corpo text-texto-secundario">{tratamento.motivo}</p>
                      {tratamento.status === "pendente" ? (
                        <PortaoDePermissao permissao="tratamentos.aprovar">
                          <div className="flex flex-wrap items-center gap-2">
                            <Entrada
                              aria-label="Comentário de reprovação"
                              placeholder="Comentário (obrigatório para reprovar)"
                              value={comentarios[tratamento.id ?? ""] ?? ""}
                              onChange={(evento) => {
                                setComentarios((atual) => ({
                                  ...atual,
                                  [tratamento.id ?? ""]: evento.target.value,
                                }));
                              }}
                              className="max-w-xs"
                            />
                            <Botao
                              type="button"
                              variant="destrutiva"
                              tamanho="compacto"
                              disabled={decidir.isPending || !comentarios[tratamento.id ?? ""]}
                              onClick={() => {
                                if (!tratamento.id) return;
                                decidir.mutate({
                                  tratamentoId: tratamento.id,
                                  corpo: {
                                    decisao: "reprovar",
                                    comentario: comentarios[tratamento.id] ?? "",
                                  },
                                });
                              }}
                            >
                              Reprovar
                            </Botao>
                          </div>
                        </PortaoDePermissao>
                      ) : null}
                      {decidir.isError ? (
                        <Alerta variant="erro">
                          <AlertaDescricao>{mensagemDeErroApi(decidir.error)}</AlertaDescricao>
                        </Alerta>
                      ) : null}
                      {cancelar.isError ? (
                        <Alerta variant="erro">
                          <AlertaDescricao>{mensagemDeErroApi(cancelar.error)}</AlertaDescricao>
                        </Alerta>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <PortaoDePermissao permissao="ocorrencias.ler">
            <section className="flex flex-col gap-2">
              <h3 className="estilo-titulo-cartao text-texto-primario">Ocorrências do dia</h3>
              {(ocorrencias.data?.dados ?? []).length === 0 ? (
                <p className="estilo-corpo text-texto-secundario">Nenhuma ocorrência neste dia.</p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {(ocorrencias.data?.dados ?? []).map((ocorrencia) => {
                    const aberta =
                      ocorrencia.status === "aberta" || ocorrencia.status === "em_tratamento";
                    return (
                      <li
                        key={ocorrencia.id}
                        className="flex flex-col gap-2 rounded-medio border border-borda-sutil p-3"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <Selo
                            variant={
                              ocorrencia.severidade
                                ? VARIANTE_SEVERIDADE_OCORRENCIA[ocorrencia.severidade]
                                : "neutro"
                            }
                          >
                            {ocorrencia.severidade
                              ? ROTULO_SEVERIDADE_OCORRENCIA[ocorrencia.severidade]
                              : "—"}
                          </Selo>
                          <span className="estilo-corpo text-texto-primario">
                            {ocorrencia.codigo
                              ? ROTULO_CODIGO_OCORRENCIA[ocorrencia.codigo]
                              : "Ocorrência"}
                          </span>
                          <span className="estilo-legenda text-texto-terciario">
                            {ocorrencia.status}
                          </span>
                        </div>
                        {ocorrencia.descricao ? (
                          <p className="estilo-corpo text-texto-secundario">
                            {ocorrencia.descricao}
                          </p>
                        ) : null}
                        {aberta ? (
                          <PortaoDePermissao permissao="ocorrencias.editar">
                            <div className="flex flex-wrap items-center gap-2">
                              <Entrada
                                aria-label="Resolução da ocorrência"
                                placeholder="Descreva a resolução"
                                value={resolucaoPorOcorrencia[ocorrencia.id ?? ""] ?? ""}
                                onChange={(evento) => {
                                  setResolucaoPorOcorrencia((atual) => ({
                                    ...atual,
                                    [ocorrencia.id ?? ""]: evento.target.value,
                                  }));
                                }}
                                className="max-w-xs"
                              />
                              <Botao
                                type="button"
                                tamanho="compacto"
                                variant="secundaria"
                                disabled={atualizarOcorrencia.isPending}
                                onClick={() => {
                                  if (!ocorrencia.id) return;
                                  const ultimoTratamento = tratamentos.data?.dados?.[0];
                                  atualizarOcorrencia.mutate({
                                    ocorrenciaId: ocorrencia.id,
                                    corpo: {
                                      status: "resolvida",
                                      resolucao:
                                        resolucaoPorOcorrencia[ocorrencia.id] ||
                                        "Resolvida a partir da grade de apuração.",
                                      ...(ultimoTratamento?.id
                                        ? { tratamentoId: ultimoTratamento.id }
                                        : {}),
                                    },
                                  });
                                }}
                              >
                                Marcar como resolvida
                              </Botao>
                              <Botao
                                type="button"
                                tamanho="compacto"
                                variant="sutil"
                                disabled={atualizarOcorrencia.isPending}
                                onClick={() => {
                                  if (!ocorrencia.id) return;
                                  atualizarOcorrencia.mutate({
                                    ocorrenciaId: ocorrencia.id,
                                    corpo: {
                                      status: "ignorada",
                                      resolucao:
                                        resolucaoPorOcorrencia[ocorrencia.id] ||
                                        "Ignorada a partir da grade de apuração.",
                                    },
                                  });
                                }}
                              >
                                Ignorar
                              </Botao>
                            </div>
                          </PortaoDePermissao>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              )}
              {atualizarOcorrencia.isError ? (
                <Alerta variant="erro">
                  <AlertaDescricao>{mensagemDeErroApi(atualizarOcorrencia.error)}</AlertaDescricao>
                </Alerta>
              ) : null}
            </section>
          </PortaoDePermissao>

          <PortaoDePermissao permissao={editando ? "tratamentos.editar" : "tratamentos.criar"}>
            <section className="flex flex-col gap-2 border-t border-borda-sutil pt-4">
              <div className="flex items-center justify-between">
                <h3 className="estilo-titulo-cartao text-texto-primario">
                  {editando ? "Editar tratamento" : "Novo tratamento"}
                </h3>
                {editando ? (
                  <Botao
                    type="button"
                    variant="secundaria"
                    tamanho="compacto"
                    onClick={() => setEditando(null)}
                  >
                    Cancelar edição
                  </Botao>
                ) : null}
              </div>
              <FormularioDeTratamento
                key={editando?.id ?? "novo"}
                tipos={tipos.data?.dados ?? []}
                marcacoesDoDia={opcoesMarcacoes}
                tratamento={editando}
                salvando={mutacaoAtiva.isPending}
                erro={mutacaoAtiva.isError ? mensagemDeErroApi(mutacaoAtiva.error) : undefined}
                aoSalvar={salvar}
                aoCancelar={() => {
                  if (editando) setEditando(null);
                  else fechar();
                }}
              />
            </section>
          </PortaoDePermissao>
        </div>
      </DialogoConteudo>
    </Dialogo>
  );
}

function ResumoDoDia({
  apuracao,
  carregando,
}: {
  apuracao: Esquema<"ApuracaoDia"> | undefined;
  carregando: boolean;
}) {
  if (carregando) return <Esqueleto className="h-10 w-full" />;
  if (!apuracao?.status) {
    return (
      <Alerta variant="neutro">
        <AlertaDescricao>
          Este dia ainda não tem apuração calculada — o tratamento pode ser registrado mesmo assim e
          será considerado no próximo recálculo.
        </AlertaDescricao>
      </Alerta>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Selo variant={VARIANTE_STATUS_APURACAO[apuracao.status]}>
        {ROTULO_STATUS_APURACAO[apuracao.status]}
      </Selo>
      {apuracao.tipoDia ? <Selo variant="neutro">{ROTULO_TIPO_DIA[apuracao.tipoDia]}</Selo> : null}
      <span className="estilo-corpo text-texto-secundario">
        Previsto{" "}
        {apuracao.previstoMinutos !== undefined ? minutosParaHHMM(apuracao.previstoMinutos) : "—"} ·
        Trabalhado{" "}
        {apuracao.trabalhadoMinutos !== undefined
          ? minutosParaHHMM(apuracao.trabalhadoMinutos)
          : "—"}
      </span>
      {apuracao.marcacoesImpares ? <Selo variant="atencao">Marcações ímpares</Selo> : null}
    </div>
  );
}
