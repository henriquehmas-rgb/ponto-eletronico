"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

import { paramsSemUndefined } from "./utilitarios";

export interface EscopoDeApuracao {
  empresaId?: string | undefined;
  unidadeId?: string | undefined;
  departamentoId?: string | undefined;
  equipeId?: string | undefined;
}

const LIMITE_PAGINAS = 10; // 10 x 200 = 2.000 colaboradores — teto generoso acima do alvo de 500 (T9).

/**
 * Enriquecimento *best-effort* de nome do colaborador para a grade de
 * apuração (T9): `GET /v1/apuracoes` só devolve `colaboradorId`. Reusa `GET
 * /v1/colaboradores` (tag já liberada à fase inteira em §4 do PCF — a TELA de
 * cadastro é ownership exclusivo de A2, a leitura em si não é) com o MESMO
 * recorte de escopo da grade. Falha graciosamente: se a sessão não tiver
 * `colaboradores.ler`, ou a chamada errar por qualquer outro motivo, a grade
 * simplesmente cai para o identificador cru em vez de quebrar por causa de um
 * rótulo cosmético — por isso não expõe erro nenhum, só o mapa (vazio na
 * ausência de dado).
 */
export function useMapaDeNomesDeColaboradores(
  escopo: EscopoDeApuracao,
): ReadonlyMap<string, string> {
  const consulta = useQuery({
    queryKey: [
      "nomes-colaboradores-apuracao",
      escopo.empresaId,
      escopo.unidadeId,
      escopo.departamentoId,
      escopo.equipeId,
    ],
    queryFn: async () => {
      const mapa = new Map<string, string>();
      let cursor: string | undefined;
      let pagina = 0;
      do {
        const resultado = await api.GET("/v1/colaboradores", {
          params: {
            query: paramsSemUndefined({
              empresaId: escopo.empresaId,
              unidadeId: escopo.unidadeId,
              departamentoId: escopo.departamentoId,
              equipeId: escopo.equipeId,
              incluirInativos: true,
              cursor,
              limite: 200,
            }),
          },
        });
        if (resultado.error) throw resultado.error;
        for (const colaborador of resultado.data?.dados ?? []) {
          if (colaborador.id && colaborador.nomeCompleto) {
            mapa.set(colaborador.id, colaborador.nomeCompleto);
          }
        }
        cursor = resultado.data?.paginacao?.proximoCursor;
        pagina += 1;
      } while (cursor && pagina < LIMITE_PAGINAS);
      return mapa;
    },
    retry: false,
  });
  return consulta.data ?? new Map();
}
