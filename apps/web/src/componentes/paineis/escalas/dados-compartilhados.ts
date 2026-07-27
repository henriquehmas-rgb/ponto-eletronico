"use client";

import { useMemo } from "react";
import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { api, type Esquema } from "@/lib/api";
import { paramsSemUndefined } from "@/lib/formatacao-f8/parametros-de-consulta";

/**
 * Leitura auxiliar só desta seção (T12/T13) — deliberadamente NÃO em
 * `apps/web/src/ganchos/use-vinculos.ts`/`use-colaboradores.ts`: esses nomes
 * são ownership exclusivo de A2 (§5 do PCF F9b) e, no momento em que este
 * arquivo foi escrito, ainda não existiam. Em vez de esperar por eles (ou
 * criar um arquivo de mesmo nome, o que violaria a exclusividade), esta seção
 * lê `GET /v1/vinculos` e `GET /v1/colaboradores` diretamente, só para montar
 * a lista "vínculo → nome do colaborador" que a grade de escala e os
 * formulários de atribuição precisam. Nenhum filtro de hierarquia é aplicado
 * aqui — as duas listagens já chegam recortadas ao escopo do usuário pelo
 * servidor (§2 do PCF: "gestor vê sua árvore" nunca é reimplementado no
 * cliente). Para empresas, esta seção CONSOME `useEmpresas` de
 * `@/ganchos/use-empresas` (A2, já disponível) em vez de duplicar.
 */

export interface MembroDaEquipe {
  vinculoId: string;
  colaboradorId: string;
  empresaId: string;
  nomeColaborador: string;
}

/** `GET /v1/vinculos?status=ativo` — só vínculos ativos entram na grade/atribuição. */
function useVinculosAtivos(): UseQueryResult<Esquema<"ListaVinculo">> {
  return useQuery({
    queryKey: ["escalas", "vinculos-ativos"],
    queryFn: async () => {
      const resultado = await api.GET("/v1/vinculos", {
        params: {
          query: paramsSemUndefined({ status: "ativo", limite: 100, ordenar: "dataInicio" }),
        },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    staleTime: 60_000,
  });
}

/** `GET /v1/colaboradores?status=ativo` — só para resolver o nome exibido de cada vínculo. */
function useColaboradoresAtivos(): UseQueryResult<Esquema<"ListaColaborador">> {
  return useQuery({
    queryKey: ["escalas", "colaboradores-ativos"],
    queryFn: async () => {
      const resultado = await api.GET("/v1/colaboradores", {
        params: {
          query: paramsSemUndefined({ status: "ativo", limite: 100, ordenar: "nomeCompleto" }),
        },
      });
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    staleTime: 60_000,
  });
}

export interface EquipeVisivel {
  membros: MembroDaEquipe[];
  carregando: boolean;
  erro: unknown;
}

/**
 * Combina vínculos ativos + colaboradores (mesmo escopo do servidor) numa
 * lista pronta para `GradeDeEscala` e para os seletores de vínculo dos
 * formulários de atribuição/"copiar período". `Vinculo` não carrega o nome
 * do colaborador (só `colaboradorId`) — por isso as duas listagens.
 */
export function useEquipeVisivel(): EquipeVisivel {
  const vinculos = useVinculosAtivos();
  const colaboradores = useColaboradoresAtivos();

  const membros = useMemo<MembroDaEquipe[]>(() => {
    const nomesPorColaborador = new Map<string, string>();
    for (const colaborador of colaboradores.data?.dados ?? []) {
      if (!colaborador.id) continue;
      nomesPorColaborador.set(
        colaborador.id,
        colaborador.nomeSocial || colaborador.nomeCompleto || "Colaborador sem nome cadastrado",
      );
    }
    const lista: MembroDaEquipe[] = [];
    for (const vinculo of vinculos.data?.dados ?? []) {
      if (!vinculo.id || !vinculo.colaboradorId || !vinculo.empresaId) continue;
      lista.push({
        vinculoId: vinculo.id,
        colaboradorId: vinculo.colaboradorId,
        empresaId: vinculo.empresaId,
        nomeColaborador:
          nomesPorColaborador.get(vinculo.colaboradorId) ?? "Colaborador sem nome cadastrado",
      });
    }
    return lista;
  }, [vinculos.data, colaboradores.data]);

  return {
    membros,
    carregando: vinculos.isPending || colaboradores.isPending,
    erro: vinculos.error ?? colaboradores.error,
  };
}

/** `nomeFantasia` quando preenchido, senão `razaoSocial` — mesmo padrão usado no restante do produto. */
export function nomeExibidoDaEmpresa(empresa: Esquema<"Empresa">): string {
  return empresa.nomeFantasia || empresa.razaoSocial || "Empresa sem nome cadastrado";
}
