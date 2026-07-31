"use client";

import { useEffect, useState } from "react";

import { Botao } from "@/componentes/ui/button";
import { Entrada } from "@/componentes/ui/input";
import { Rotulo } from "@/componentes/ui/label";
import {
  Selecao,
  SelecaoConteudo,
  SelecaoGatilho,
  SelecaoItem,
  SelecaoValor,
} from "@/componentes/ui/select";
import { Esqueleto } from "@/componentes/ui/skeleton";
import {
  useExecutarRelatorio,
  usePreferenciaPadraoDoRelatorio,
  useRelatorio,
  useSalvarPreferenciaDeColunas,
} from "@/ganchos/use-relatorios";

import { AcompanhamentoDeExecucao } from "./acompanhamento-de-execucao";
import { SeletorDeColunas } from "./seletor-de-colunas";
import {
  agrupamentosDoCatalogo,
  colunasDoCatalogo,
  filtrosDoCatalogo,
  ROTULO_CATEGORIA,
  ROTULO_FORMATO,
} from "./tipos";

//: Chaves de filtro que a query de `executarRelatorio` já nomeia
//: individualmente (contrato) — qualquer outra chave declarada em
//: `filtrosDisponiveis` vira parâmetro extra dentro de `filtros` (JSON).
//: Lista fixa, nunca condicionada ao `codigo` do relatório (proibição 13).
const CHAVES_FILTRO_NOMEADAS = new Set([
  "periodoId",
  "de",
  "ate",
  "empresaId",
  "unidadeId",
  "departamentoId",
  "colaboradorId",
]);

interface ExecucaoDeRelatorioProps {
  codigo: string;
}

/**
 * Tela genérica de execução (T4): um único componente serve os 24
 * relatórios do catálogo — o formulário (filtros/colunas/agrupamento/
 * formato) é construído inteiramente a partir da `RelatorioDefinicao`
 * devolvida por `obterRelatorio`, sem nenhum `if (codigo === ...)`.
 */
export function ExecucaoDeRelatorio({ codigo }: ExecucaoDeRelatorioProps) {
  const definicaoConsulta = useRelatorio(codigo);
  const definicao = definicaoConsulta.data;
  const preferenciaConsulta = usePreferenciaPadraoDoRelatorio(definicao?.id);
  const executar = useExecutarRelatorio();
  const salvarPreferencia = useSalvarPreferenciaDeColunas();

  const colunas = colunasDoCatalogo(definicao);
  const filtros = filtrosDoCatalogo(definicao);
  const agrupamentos = agrupamentosDoCatalogo(definicao);

  const [colunasSelecionadas, setColunasSelecionadas] = useState<string[]>([]);
  const [valoresFiltroNomeado, setValoresFiltroNomeado] = useState<Record<string, string>>({});
  const [valoresFiltroExtra, setValoresFiltroExtra] = useState<Record<string, string>>({});
  const [agrupamento, setAgrupamento] = useState<string>("");
  const [formato, setFormato] = useState<string>("");
  const [execucaoId, setExecucaoId] = useState<string | null>(null);

  // Pré-carrega colunas: preferência salva do usuário (`padrao`) se existir,
  // senão todas as colunas do catálogo — só na primeira vez que os dados
  // chegam, para não sobrescrever uma escolha que o usuário já fez na tela.
  useEffect(() => {
    if (colunasSelecionadas.length > 0) return;
    if (preferenciaConsulta.isLoading) return;
    const salvas = preferenciaConsulta.data?.colunas;
    if (salvas && salvas.length > 0) {
      setColunasSelecionadas(salvas);
    } else if (colunas.length > 0) {
      setColunasSelecionadas(colunas.map((coluna) => coluna.chave));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- so na chegada dos dados, ver comentario acima
  }, [preferenciaConsulta.isLoading, preferenciaConsulta.data, definicao?.id]);

  useEffect(() => {
    if (!formato && definicao?.formatos && definicao.formatos.length > 0) {
      setFormato(definicao.formatos[0] ?? "");
    }
  }, [definicao?.formatos, formato]);

  if (definicaoConsulta.isLoading) {
    return <Esqueleto className="h-64 w-full rounded-medio" />;
  }
  if (definicaoConsulta.isError || !definicao) {
    return (
      <p className="estilo-corpo text-estado-erro-texto">
        Não foi possível carregar este relatório.
      </p>
    );
  }

  async function aoExecutar() {
    const extras = Object.fromEntries(
      Object.entries(valoresFiltroExtra).filter(([, valor]) => valor !== ""),
    );
    executar.mutate(
      {
        codigo,
        parametros: {
          formato: (formato || undefined) as never,
          periodoId: valoresFiltroNomeado.periodoId || undefined,
          de: valoresFiltroNomeado.de || undefined,
          ate: valoresFiltroNomeado.ate || undefined,
          empresaId: valoresFiltroNomeado.empresaId || undefined,
          unidadeId: valoresFiltroNomeado.unidadeId || undefined,
          departamentoId: valoresFiltroNomeado.departamentoId || undefined,
          colaboradorId: valoresFiltroNomeado.colaboradorId || undefined,
          agrupamento: agrupamento || undefined,
          colunas: colunasSelecionadas.length > 0 ? colunasSelecionadas : undefined,
          filtros: Object.keys(extras).length > 0 ? extras : undefined,
        },
      },
      { onSuccess: (execucao) => setExecucaoId(execucao.id ?? null) },
    );
  }

  function aoSalvarComoPadrao() {
    if (!definicao?.id) return;
    salvarPreferencia.mutate({
      relatorioDefinicaoId: definicao.id,
      nome: "padrao",
      colunas: colunasSelecionadas,
      padrao: true,
    });
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="estilo-titulo-pagina text-texto-primario">{definicao.nome}</h1>
        <p className="estilo-corpo text-texto-terciario">
          {ROTULO_CATEGORIA[definicao.categoria ?? ""] ?? definicao.categoria}
          {definicao.descricao ? ` · ${definicao.descricao}` : ""}
        </p>
      </div>

      {filtros.length > 0 ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filtros.map((filtro) => {
            const nomeado = CHAVES_FILTRO_NOMEADAS.has(filtro.chave);
            const valor = nomeado
              ? (valoresFiltroNomeado[filtro.chave] ?? "")
              : (valoresFiltroExtra[filtro.chave] ?? "");
            const tipoEntrada =
              filtro.tipo === "data" ? "date" : filtro.tipo === "numero" ? "number" : "text";
            return (
              <div key={filtro.chave} className="flex flex-col gap-1">
                <Rotulo htmlFor={`filtro-${filtro.chave}`}>{filtro.rotulo}</Rotulo>
                <Entrada
                  id={`filtro-${filtro.chave}`}
                  type={tipoEntrada}
                  value={valor}
                  onChange={(evento) => {
                    const novoValor = evento.target.value;
                    if (nomeado) {
                      setValoresFiltroNomeado((atual) => ({ ...atual, [filtro.chave]: novoValor }));
                    } else {
                      setValoresFiltroExtra((atual) => ({ ...atual, [filtro.chave]: novoValor }));
                    }
                  }}
                />
              </div>
            );
          })}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {agrupamentos.length > 0 ? (
          <div className="flex flex-col gap-1">
            <Rotulo htmlFor="agrupamento">Agrupar por</Rotulo>
            <Selecao
              value={agrupamento || "__nenhum__"}
              onValueChange={(valor) => setAgrupamento(valor === "__nenhum__" ? "" : valor)}
            >
              <SelecaoGatilho id="agrupamento" className="w-full">
                <SelecaoValor />
              </SelecaoGatilho>
              <SelecaoConteudo>
                <SelecaoItem value="__nenhum__">Sem agrupamento (detalhado)</SelecaoItem>
                {agrupamentos.map((item) => (
                  <SelecaoItem key={item.chave} value={item.chave}>
                    {item.rotulo}
                  </SelecaoItem>
                ))}
              </SelecaoConteudo>
            </Selecao>
          </div>
        ) : null}

        {definicao.formatos && definicao.formatos.length > 0 ? (
          <div className="flex flex-col gap-1">
            <Rotulo htmlFor="formato">Formato de exportação</Rotulo>
            <Selecao value={formato} onValueChange={setFormato}>
              <SelecaoGatilho id="formato" className="w-full">
                <SelecaoValor />
              </SelecaoGatilho>
              <SelecaoConteudo>
                {definicao.formatos.map((item) => (
                  <SelecaoItem key={item} value={item}>
                    {ROTULO_FORMATO[item] ?? item}
                  </SelecaoItem>
                ))}
              </SelecaoConteudo>
            </Selecao>
          </div>
        ) : null}
      </div>

      {colunas.length > 0 ? (
        <SeletorDeColunas
          colunas={colunas}
          selecionadas={colunasSelecionadas}
          aoMudar={setColunasSelecionadas}
          aoSalvarComoPadrao={aoSalvarComoPadrao}
          salvando={salvarPreferencia.isPending}
          temPadraoSalvo={Boolean(preferenciaConsulta.data)}
        />
      ) : null}

      <Botao type="button" onClick={aoExecutar} disabled={executar.isPending} className="w-fit">
        {executar.isPending ? "Executando…" : "Executar relatório"}
      </Botao>

      {executar.isError ? (
        <p className="estilo-legenda text-estado-erro-texto">
          Não foi possível executar o relatório.
        </p>
      ) : null}

      {execucaoId ? <AcompanhamentoDeExecucao execucaoId={execucaoId} /> : null}
    </div>
  );
}
