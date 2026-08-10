"use client";

import { useMemo, useState } from "react";

import { type ColunaDeTabela, TabelaDeDados } from "@/componentes/dominio/tabela-de-dados";
import { SeletorDePeriodo, type AtalhoDePeriodo } from "@/componentes/dominio/seletor-de-periodo";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import { Cartao } from "@/componentes/ui/card";
import { useApuracoes } from "@/ganchos/use-apuracoes";
import { useOcorrencias } from "@/ganchos/use-ocorrencias";
import { useDepartamentos } from "@/ganchos/use-departamentos";
import { useEmpresas } from "@/ganchos/use-empresas";
import { useEquipes } from "@/ganchos/use-equipes";
import { useUnidades } from "@/ganchos/use-unidades";
import { useColaboradores } from "@/ganchos/use-colaboradores";
import { formatarData } from "@/lib/formatacao/data";
import { PortaoDePermissao } from "@/lib/permissoes";
import { cn } from "@/lib/utils";

import { CampoCheckboxSimples, SeletorSimples } from "./campos";
import { CelulaDeApuracao } from "./celula-de-apuracao";
import { DialogoDeRecalculo, type EscopoDeRecalculo } from "./dialogo-de-recalculo";
import { DialogoDeTratamento } from "./dialogo-de-tratamento";
import { useMapaDeNomesDeColaboradores } from "./use-nomes-de-colaboradores";
import {
  agruparApuracoesPorVinculo,
  COR_PONTO_STATUS_APURACAO,
  MARCADOR_TIPO_DIA,
  mensagemDeErroApi,
  mesAnteriorComoPeriodo,
  mesAtualComoPeriodo,
  obterDiasDoIntervalo,
  ROTULO_STATUS_APURACAO,
  ROTULO_TIPO_DIA,
  type LinhaDeApuracaoGrade,
} from "./utilitarios";

/** Dia clicado na grade — contexto que abre o diálogo de tratamento (T10). */
export interface CelulaSelecionada {
  vinculoId: string;
  colaboradorId: string;
  data: string;
  nomeColaborador: string;
}

const ALTURA_CONTAINER_GRADE_PX = 560;
const ALTURA_LINHA_GRADE_PX = 44;
const LARGURA_COLUNA_COLABORADOR_PX = 220;
const LARGURA_COLUNA_DIA_PX = 60;

/**
 * Grade de apuração mês × colaborador, virtualizada (T9), com abertura de
 * tratamento a partir da célula (T10) e recálculo/ações em lote (T11).
 *
 * Uma linha por VÍNCULO (não colaborador — glossário §1: um colaborador com
 * dois vínculos simultâneos tem duas linhas), uma coluna por dia do intervalo
 * selecionado. `TabelaDeDados` (F9a, congelada) virtualiza as LINHAS via
 * `@tanstack/react-virtual` — com 500 vínculos × 31 dias (15.500 células) o
 * DOM nunca chega a montar mais do que a janela visível + `overscan` de
 * linhas, mesmo padrão que a F9a já comprovou para 10.000 linhas.
 */
export function GradeDeApuracao() {
  const [periodo, definirPeriodo] = useState(() => mesAtualComoPeriodo());
  const [filtroEmpresaId, definirFiltroEmpresaId] = useState("");
  const [filtroUnidadeId, definirFiltroUnidadeId] = useState("");
  const [filtroDepartamentoId, definirFiltroDepartamentoId] = useState("");
  const [filtroEquipeId, definirFiltroEquipeId] = useState("");
  const [filtroColaboradorId, definirFiltroColaboradorId] = useState("");
  const [somenteInconsistentes, definirSomenteInconsistentes] = useState(false);

  const [selecionadosIds, definirSelecionadosIds] = useState<ReadonlySet<string>>(new Set());
  const [celulaSelecionada, definirCelulaSelecionada] = useState<CelulaSelecionada | null>(null);
  const [recalculoAberto, definirRecalculoAberto] = useState(false);

  const escopoFiltro = {
    empresaId: filtroEmpresaId || undefined,
    unidadeId: filtroUnidadeId || undefined,
    departamentoId: filtroDepartamentoId || undefined,
    equipeId: filtroEquipeId || undefined,
    colaboradorId: filtroColaboradorId || undefined,
  };

  const empresas = useEmpresas({ ativo: true });
  const unidades = useUnidades({ empresaId: filtroEmpresaId || undefined, ativo: true });
  const departamentos = useDepartamentos({ empresaId: filtroEmpresaId || undefined, ativo: true });
  const equipes = useEquipes({
    empresaId: filtroEmpresaId || undefined,
    unidadeId: filtroUnidadeId || undefined,
    departamentoId: filtroDepartamentoId || undefined,
    ativo: true,
  });
  const colaboradores = useColaboradores({
    empresaId: filtroEmpresaId || undefined,
    unidadeId: filtroUnidadeId || undefined,
    departamentoId: filtroDepartamentoId || undefined,
    equipeId: filtroEquipeId || undefined,
    limite: 200,
  });

  const apuracoes = useApuracoes({
    de: periodo.inicio,
    ate: periodo.fim,
    ...escopoFiltro,
    somenteInconsistentes: somenteInconsistentes || undefined,
  });
  const ocorrencias = useOcorrencias({
    empresaId: filtroEmpresaId || undefined,
    unidadeId: filtroUnidadeId || undefined,
    colaboradorId: filtroColaboradorId || undefined,
    de: periodo.inicio,
    ate: periodo.fim,
  });
  const nomes = useMapaDeNomesDeColaboradores({
    empresaId: filtroEmpresaId || undefined,
    unidadeId: filtroUnidadeId || undefined,
    departamentoId: filtroDepartamentoId || undefined,
    equipeId: filtroEquipeId || undefined,
  });

  const dias = useMemo(() => obterDiasDoIntervalo(periodo.inicio, periodo.fim), [periodo]);
  const linhas = useMemo(() => agruparApuracoesPorVinculo(apuracoes.data ?? []), [apuracoes.data]);

  const mapaDeOcorrenciasAbertas = useMemo(() => {
    const conjunto = new Set<string>();
    for (const ocorrencia of ocorrencias.data?.dados ?? []) {
      if (!ocorrencia.vinculoId || !ocorrencia.data) continue;
      if (ocorrencia.status !== "aberta" && ocorrencia.status !== "em_tratamento") continue;
      conjunto.add(`${ocorrencia.vinculoId}|${ocorrencia.data}`);
    }
    return conjunto;
  }, [ocorrencias.data]);

  function nomeDoColaborador(linha: LinhaDeApuracaoGrade): string {
    return nomes.get(linha.colaboradorId) || linha.colaboradorId || "—";
  }

  const colunas: ColunaDeTabela<LinhaDeApuracaoGrade>[] = useMemo(() => {
    const colunaColaborador: ColunaDeTabela<LinhaDeApuracaoGrade> = {
      id: "colaborador",
      cabecalho: "Colaborador",
      renderizarCelula: (linha) => (
        <span className="estilo-corpo truncate text-texto-primario">
          {nomeDoColaborador(linha)}
        </span>
      ),
      valorDeOrdenacao: (linha) => nomeDoColaborador(linha),
      ordenavel: true,
      larguraPx: LARGURA_COLUNA_COLABORADOR_PX,
    };

    const colunasDeDia: ColunaDeTabela<LinhaDeApuracaoGrade>[] = dias.map((data) => {
      const diaDoMes = data.slice(8, 10);
      return {
        id: data,
        cabecalho: diaDoMes,
        larguraPx: LARGURA_COLUNA_DIA_PX,
        renderizarCelula: (linha) => (
          <CelulaDeApuracao
            data={data}
            apuracao={linha.porDia.get(data)}
            temOcorrenciaAberta={mapaDeOcorrenciasAbertas.has(`${linha.vinculoId}|${data}`)}
            onClick={() => {
              definirCelulaSelecionada({
                vinculoId: linha.vinculoId,
                colaboradorId: linha.colaboradorId,
                data,
                nomeColaborador: nomeDoColaborador(linha),
              });
            }}
          />
        ),
      };
    });

    return [colunaColaborador, ...colunasDeDia];
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `nomes`/`mapaDeOcorrenciasAbertas` são recriados a cada render que os alimenta; recalcular junto com `dias` já cobre o caso.
  }, [dias, mapaDeOcorrenciasAbertas, nomes]);

  const atalhos: AtalhoDePeriodo[] = [
    { id: "mes-atual", rotulo: "Mês atual", ...mesAtualComoPeriodo() },
    { id: "mes-anterior", rotulo: "Mês anterior", ...mesAnteriorComoPeriodo() },
  ];

  function limparFiltrosDependentes(nivel: "empresa" | "unidade" | "departamento") {
    if (nivel === "empresa") {
      definirFiltroUnidadeId("");
      definirFiltroDepartamentoId("");
      definirFiltroEquipeId("");
      definirFiltroColaboradorId("");
    } else if (nivel === "unidade") {
      definirFiltroEquipeId("");
      definirFiltroColaboradorId("");
    } else {
      definirFiltroEquipeId("");
      definirFiltroColaboradorId("");
    }
  }

  const escopoRecalculo: EscopoDeRecalculo | null = useMemo(() => {
    if (selecionadosIds.size > 0) {
      const vinculoIds = Array.from(selecionadosIds);
      return {
        vinculoIds,
        descricao: `${vinculoIds.length} vínculo${vinculoIds.length === 1 ? "" : "s"} selecionado${vinculoIds.length === 1 ? "" : "s"} na grade, de ${periodo.inicio} até ${periodo.fim}.`,
      };
    }
    if (filtroColaboradorId) {
      return {
        colaboradorIds: [filtroColaboradorId],
        ...(filtroEmpresaId ? { empresaId: filtroEmpresaId } : {}),
        descricao: `Colaborador filtrado atualmente, de ${periodo.inicio} até ${periodo.fim}.`,
      };
    }
    if (filtroEmpresaId) {
      return {
        empresaId: filtroEmpresaId,
        ...(filtroUnidadeId ? { unidadeId: filtroUnidadeId } : {}),
        ...(filtroDepartamentoId ? { departamentoId: filtroDepartamentoId } : {}),
        descricao: `Escopo do filtro atual (empresa${filtroUnidadeId ? " + unidade" : ""}${filtroDepartamentoId ? " + departamento" : ""}), de ${periodo.inicio} até ${periodo.fim}.`,
      };
    }
    return null;
  }, [
    selecionadosIds,
    filtroColaboradorId,
    filtroEmpresaId,
    filtroUnidadeId,
    filtroDepartamentoId,
    periodo,
  ]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="estilo-titulo-pagina text-texto-primario">Apuração</h1>
          <p className="estilo-corpo text-texto-secundario">
            Período {formatarData(`${periodo.inicio}T12:00:00`)}–{formatarData(`${periodo.fim}T12:00:00`)}{" "}
            · uma linha por vínculo, uma coluna por dia. Clique numa célula para ver o detalhe do dia e
            registrar um tratamento — esta tela nunca edita marcação.
          </p>
        </div>
        <PortaoDePermissao permissao="apuracoes.executar">
          <Botao
            type="button"
            variant="secundaria"
            className="rounded-pleno"
            onClick={() => {
              definirRecalculoAberto(true);
            }}
          >
            {selecionadosIds.size > 0
              ? `Recalcular ${selecionadosIds.size} selecionado${selecionadosIds.size === 1 ? "" : "s"}`
              : "Recalcular"}
          </Botao>
        </PortaoDePermissao>
      </header>

      <div className="flex flex-wrap items-end gap-4">
        <SeletorDePeriodo
          inicio={periodo.inicio}
          fim={periodo.fim}
          aoSelecionarIntervalo={(inicio, fim) => {
            definirPeriodo({ inicio, fim });
          }}
          atalhos={atalhos}
        />
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <PortaoDePermissao permissao="empresas.ler">
          <SeletorSimples
            id="apuracao-filtro-empresa"
            rotulo="Empresa"
            valor={filtroEmpresaId}
            aoMudar={(valor) => {
              definirFiltroEmpresaId(valor);
              limparFiltrosDependentes("empresa");
            }}
            opcoes={(empresas.data?.dados ?? []).map((e) => ({
              valor: e.id ?? "",
              rotulo: e.razaoSocial ?? e.id ?? "",
            }))}
          />
        </PortaoDePermissao>
        <PortaoDePermissao permissao="unidades.ler">
          <SeletorSimples
            id="apuracao-filtro-unidade"
            rotulo="Unidade"
            valor={filtroUnidadeId}
            aoMudar={(valor) => {
              definirFiltroUnidadeId(valor);
              limparFiltrosDependentes("unidade");
            }}
            opcoes={(unidades.data?.dados ?? []).map((u) => ({
              valor: u.id ?? "",
              rotulo: u.nome ?? u.id ?? "",
            }))}
          />
        </PortaoDePermissao>
        <PortaoDePermissao permissao="departamentos.ler">
          <SeletorSimples
            id="apuracao-filtro-departamento"
            rotulo="Departamento"
            valor={filtroDepartamentoId}
            aoMudar={(valor) => {
              definirFiltroDepartamentoId(valor);
              limparFiltrosDependentes("departamento");
            }}
            opcoes={(departamentos.data?.dados ?? []).map((d) => ({
              valor: d.id ?? "",
              rotulo: d.nome ?? d.id ?? "",
            }))}
          />
        </PortaoDePermissao>
        <PortaoDePermissao permissao="equipes.ler">
          <SeletorSimples
            id="apuracao-filtro-equipe"
            rotulo="Equipe"
            valor={filtroEquipeId}
            aoMudar={definirFiltroEquipeId}
            opcoes={(equipes.data?.dados ?? []).map((e) => ({
              valor: e.id ?? "",
              rotulo: e.nome ?? e.id ?? "",
            }))}
          />
        </PortaoDePermissao>
        <PortaoDePermissao permissao="colaboradores.ler">
          <SeletorSimples
            id="apuracao-filtro-colaborador"
            rotulo="Colaborador"
            valor={filtroColaboradorId}
            aoMudar={definirFiltroColaboradorId}
            opcoes={(colaboradores.data?.dados ?? []).map((c) => ({
              valor: c.id ?? "",
              rotulo: c.nomeCompleto ?? c.id ?? "",
            }))}
          />
        </PortaoDePermissao>
        <CampoCheckboxSimples
          id="apuracao-somente-inconsistentes"
          rotulo="Somente inconsistentes"
          marcado={somenteInconsistentes}
          aoMudar={definirSomenteInconsistentes}
        />
      </div>

      {apuracoes.isError ? (
        <Alerta variant="erro">
          <AlertaDescricao>{mensagemDeErroApi(apuracoes.error)}</AlertaDescricao>
        </Alerta>
      ) : null}

      <Legenda />

      <Cartao className="rounded-suave p-[var(--espacamento-3)] shadow-flutuante-cartao">
        <TabelaDeDados
          linhas={linhas}
          colunas={colunas}
          obterId={(linha) => linha.vinculoId}
          alturaContainerPx={ALTURA_CONTAINER_GRADE_PX}
          alturaLinhaPx={ALTURA_LINHA_GRADE_PX}
          carregando={apuracoes.isPending}
          mensagemVazia="Nenhuma apuração encontrada para o período e filtros selecionados."
          selecionaveis
          selecionadosIds={selecionadosIds}
          aoMudarSelecionadosIds={definirSelecionadosIds}
        />
      </Cartao>

      <DialogoDeTratamento
        celula={celulaSelecionada}
        aoFechar={() => {
          definirCelulaSelecionada(null);
        }}
      />

      <DialogoDeRecalculo
        aberto={recalculoAberto}
        aoMudarAberto={definirRecalculoAberto}
        escopo={escopoRecalculo}
        dataInicioPadrao={periodo.inicio}
        dataFimPadrao={periodo.fim}
      />
    </div>
  );
}

/**
 * Legenda acima da grade: bolinha de cor + nome para cada status de apuração
 * (canal auxiliar) e, num acordeão à parte, os marcadores de forma de cada
 * tipo de dia. Cor nunca é o único canal (WCAG 1.4.1) — todo marcador,
 * bolinha ou forma, vem sempre acompanhado do rótulo textual.
 */
function Legenda() {
  const statusList = Object.keys(ROTULO_STATUS_APURACAO) as (keyof typeof ROTULO_STATUS_APURACAO)[];
  const tipos = Object.keys(MARCADOR_TIPO_DIA) as (keyof typeof MARCADOR_TIPO_DIA)[];
  return (
    <div className="flex flex-col gap-2">
      <ul className="flex flex-wrap gap-x-4 gap-y-1" aria-label="Legenda de status da apuração">
        {statusList.map((status) => (
          <li key={status} className="estilo-legenda flex items-center gap-1.5 text-texto-secundario">
            <span
              aria-hidden="true"
              className={cn("size-[9px] shrink-0 rounded-pleno", COR_PONTO_STATUS_APURACAO[status])}
            />
            {ROTULO_STATUS_APURACAO[status]}
          </li>
        ))}
      </ul>

      <details className="rounded-suave bg-fundo-superficie p-3 shadow-flutuante-chip">
        <summary className="estilo-rotulo cursor-pointer text-texto-secundario">
          Legenda dos marcadores de tipo de dia
        </summary>
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
          {tipos.map((tipo) => (
            <li key={tipo} className="estilo-legenda flex items-center gap-1 text-texto-secundario">
              <span aria-hidden="true">{MARCADOR_TIPO_DIA[tipo]}</span>
              {ROTULO_TIPO_DIA[tipo]}
            </li>
          ))}
          <li className="estilo-legenda flex items-center gap-1 text-texto-secundario">
            <span aria-hidden="true">⚠</span>
            Ocorrência aberta
          </li>
        </ul>
      </details>
    </div>
  );
}
