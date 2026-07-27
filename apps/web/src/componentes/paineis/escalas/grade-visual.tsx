"use client";

import { useMemo, useState } from "react";

import {
  GradeDeEscala,
  type CelulaDeEscala,
  type LinhaDeColaboradorNaGrade,
} from "@/componentes/dominio/grade-de-escala";
import { SeletorDePeriodo, type AtalhoDePeriodo } from "@/componentes/dominio/seletor-de-periodo";
import { Botao } from "@/componentes/ui/button";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { useApuracoes } from "@/ganchos/use-apuracoes";
import { useResolucoesJornadaEmLote, type ParDeResolucao } from "@/ganchos/use-resolucao-jornada";
import { useTurnos } from "@/ganchos/use-turnos";
import type { Esquema } from "@/lib/api";
import { PortaoDePermissao } from "@/lib/permissoes";

import { CoberturaPorTurno } from "./cobertura-por-turno";
import { CopiarPeriodoDialogo } from "./copiar-periodo-dialogo";
import { useEquipeVisivel } from "./dados-compartilhados";
import { mensagemDeErroApi } from "./mensagem-de-erro-api";
import {
  datasDoIntervalo,
  ehDataFutura,
  hojeIso,
  mapearTipoDia,
  mesAnteriorComoPeriodo,
  mesAtualComoPeriodo,
} from "./utilitarios-ciclo";

/**
 * Grade visual de escala, previsto × realizado e cobertura por turno (T13).
 *
 * Escopo: equipe VISÍVEL do gestor logado (recorte já aplicado pelo servidor
 * em `GET /v1/vinculos`/`GET /v1/colaboradores` — nunca refiltrado aqui) e o
 * período selecionado por `SeletorDePeriodo` (F9a).
 *
 * "Previsto × realizado": para cada `(vínculo, dia)` do período, dias JÁ
 * APURÁVEIS (`<= hoje`) usam `GET /v1/apuracoes` — uma ÚNICA chamada
 * cobrindo toda a equipe/período (sem `vinculoId`, o servidor já recorta à
 * árvore do gestor), sem N+1; dias FUTUROS (`> hoje`) usam
 * `resolverJornadaDoDia`, uma chamada por célula (achado de contrato nº 1,
 * PCF §2 — não há leitura em lote), cacheada por `(vinculoId, data)`.
 */
export function GradeVisualDeEscala() {
  const [periodo, definirPeriodo] = useState(() => mesAtualComoPeriodo());
  const [copiarAberto, definirCopiarAberto] = useState(false);
  const hoje = useState(() => hojeIso())[0];

  const equipe = useEquipeVisivel();
  const turnos = useTurnos({ ativo: true });

  const datas = useMemo(() => datasDoIntervalo(periodo.inicio, periodo.fim), [periodo]);
  const datasPassadas = useMemo(
    () => datas.filter((data) => !ehDataFutura(data, hoje)),
    [datas, hoje],
  );
  const datasFuturas = useMemo(
    () => datas.filter((data) => ehDataFutura(data, hoje)),
    [datas, hoje],
  );

  // Cobre só a fatia passada/hoje do período — se o período inteiro for
  // futuro, cai num único dia (`periodo.inicio`) que nenhuma célula usa (a
  // classificação por `ehDataFutura` decide a fonte por célula, não este
  // intervalo), então essa chamada extra é inofensiva, não incorreta.
  const deApuracoes = datasPassadas[0] ?? periodo.inicio;
  const ateApuracoes = datasPassadas[datasPassadas.length - 1] ?? periodo.inicio;
  const apuracoes = useApuracoes({ de: deApuracoes, ate: ateApuracoes });

  const paresFuturos = useMemo<ParDeResolucao[]>(() => {
    if (datasFuturas.length === 0) return [];
    const pares: ParDeResolucao[] = [];
    for (const membro of equipe.membros) {
      for (const data of datasFuturas) {
        pares.push({ vinculoId: membro.vinculoId, data });
      }
    }
    return pares;
  }, [equipe.membros, datasFuturas]);
  const resolucoes = useResolucoesJornadaEmLote(paresFuturos);

  const mapaDeTurnos = useMemo(() => {
    const mapa = new Map<string, Esquema<"Turno">>();
    for (const turno of turnos.data?.dados ?? []) {
      if (turno.id) mapa.set(turno.id, turno);
    }
    return mapa;
  }, [turnos.data]);

  const mapaDeApuracoes = useMemo(() => {
    const mapa = new Map<string, Esquema<"ApuracaoDia">>();
    for (const item of apuracoes.data ?? []) {
      if (item.vinculoId && item.data) mapa.set(`${item.vinculoId}|${item.data}`, item);
    }
    return mapa;
  }, [apuracoes.data]);

  // Sem `useMemo`, de propósito: `useQueries` devolve um array NOVO a cada
  // render (mesmo quando o conteúdo não mudou), então memoizar por
  // referência de `resolucoes` recalcularia de qualquer forma. O custo é
  // O(vínculos × dias futuros) — a mesma escala "dezenas × dias" que o
  // achado de contrato nº 1 já autoriza para esta grade, não os 15.500 da
  // apuração.
  const mapaDeResolucoes = new Map<string, Esquema<"ResolucaoJornada">>();
  paresFuturos.forEach((par, indice) => {
    const dados = resolucoes[indice]?.data;
    if (dados) mapaDeResolucoes.set(`${par.vinculoId}|${par.data}`, dados);
  });

  function montarCelula(vinculoId: string, data: string): CelulaDeEscala {
    const futura = ehDataFutura(data, hoje);
    let turnoId: string | undefined;
    let tipoDiaDominio: Esquema<"ApuracaoDia">["tipoDia"];
    let cruzaMeiaNoite: boolean | undefined;

    if (futura) {
      const resolucao = mapaDeResolucoes.get(`${vinculoId}|${data}`);
      turnoId = resolucao?.turnoId;
      tipoDiaDominio = resolucao?.tipoDia;
      cruzaMeiaNoite = resolucao?.cruzaMeiaNoite;
    } else {
      const apuracao = mapaDeApuracoes.get(`${vinculoId}|${data}`);
      turnoId = apuracao?.turnoId;
      tipoDiaDominio = apuracao?.tipoDia;
    }

    const turnoResolvido = turnoId ? mapaDeTurnos.get(turnoId) : undefined;
    const turno =
      turnoResolvido?.id && turnoResolvido.nome && turnoResolvido.cor
        ? { id: turnoResolvido.id, nome: turnoResolvido.nome, cor: turnoResolvido.cor }
        : null;
    const tipoDia = mapearTipoDia(tipoDiaDominio, Boolean(turno));

    return {
      data,
      turno,
      ...(tipoDia ? { tipoDia } : {}),
      ...(cruzaMeiaNoite !== undefined ? { cruzaMeiaNoite } : {}),
    };
  }

  // Também sem `useMemo`: `mapaDeResolucoes` já é recriado a cada render
  // (comentário acima), então memoizar `linhas` por ele recalcularia do
  // mesmo jeito — mesma escala pequena, sem ganho real de memoização.
  const linhas: LinhaDeColaboradorNaGrade[] = equipe.membros.map((membro) => ({
    // GradeDeEscala (F9a, congelado) chama este campo "colaboradorId", mas o
    // valor aqui é o vinculoId: é o vínculo, não o colaborador, que tem
    // apuração e escala (glossário §1) — um colaborador com dois vínculos
    // simultâneos (permitido em empresas diferentes do tenant) precisa de
    // DUAS linhas, o que só funciona com uma chave por vínculo. Registrado em
    // docs/backlog.md para quem evoluir o componente.
    colaboradorId: membro.vinculoId,
    nomeColaborador: membro.nomeColaborador,
    celulas: datas.map((data) => montarCelula(membro.vinculoId, data)),
  }));

  const atalhos: AtalhoDePeriodo[] = [
    { id: "mes-atual", rotulo: "Mês atual", ...mesAtualComoPeriodo() },
    { id: "mes-anterior", rotulo: "Mês anterior", ...mesAnteriorComoPeriodo() },
  ];

  const carregando = equipe.carregando || turnos.isPending || apuracoes.isPending;
  const erro = equipe.erro ?? apuracoes.error ?? turnos.error;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <SeletorDePeriodo
          inicio={periodo.inicio}
          fim={periodo.fim}
          aoSelecionarIntervalo={(inicio, fim) => {
            definirPeriodo({ inicio, fim });
          }}
          atalhos={atalhos}
        />
        <PortaoDePermissao permissao="escalas.editar">
          <Botao
            type="button"
            variant="secundaria"
            disabled={equipe.membros.length === 0}
            onClick={() => {
              definirCopiarAberto(true);
            }}
          >
            Copiar período
          </Botao>
        </PortaoDePermissao>
      </div>

      {erro ? (
        <p role="alert" className="estilo-corpo text-estado-erro-texto">
          {mensagemDeErroApi(erro)}
        </p>
      ) : null}

      {carregando ? (
        <Esqueleto className="h-64 w-full" />
      ) : equipe.membros.length === 0 ? (
        <p className="estilo-corpo text-texto-secundario">
          Nenhum vínculo ativo visível para montar a grade.
        </p>
      ) : (
        <>
          <GradeDeEscala datas={datas} linhas={linhas} />
          <CoberturaPorTurno datas={datas} linhas={linhas} />
        </>
      )}

      <PortaoDePermissao permissao="escalas.editar">
        <CopiarPeriodoDialogo
          aberto={copiarAberto}
          aoMudarAberto={definirCopiarAberto}
          equipe={equipe.membros}
        />
      </PortaoDePermissao>
    </div>
  );
}
