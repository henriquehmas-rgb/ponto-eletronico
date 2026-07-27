"use client";

import { useSessaoAtual } from "./use-sessao";
import type { Esquema } from "@/lib/api";

/**
 * `{ sessao, carregando, erro }` por cima de `GET /v1/auth/sessao`
 * (`obterSessaoAtual`) — é aqui, e só aqui nesta fase, que `permissoes`/
 * `perfis` aparecem (T1, PCF F9b §2/§6). `apps/web/src/lib/permissoes/**`
 * (RBAC no cliente) consome este gancho, nunca chama `obterSessaoAtual`
 * diretamente.
 *
 * ACHADO documentado no relatório da fase (não é bloqueio, é reconciliação
 * para o orquestrador): o PCF da F9b instruía criar este arquivo do zero
 * ("useQuery de obterSessaoAtual por cima de useSessao() da F8"), presumindo
 * que o gancho ainda não existiria quando A1 começasse. Na prática, a F8
 * (mesma onda, já commitada em `ad71354`) já entrega exatamente essa consulta
 * em `apps/web/src/ganchos/use-sessao.ts` (`useSessaoAtual`), usada por
 * `use-espelho-de-ponto.ts`/`use-banco-de-horas.ts` do portal do colaborador.
 * Em vez de duplicar a chamada de rede (e o `queryKey`) escrevendo um segundo
 * `useQuery` sobre o mesmo endpoint, este módulo ENVOLVE o gancho da F8 e só
 * adapta o formato de saída ao que a T1 desta fase pede — mesmo espírito de
 * reuso que o resto do PCF exige para sessão/design system.
 */
export interface SessaoCompleta {
  sessao: Esquema<"SessaoAtual"> | undefined;
  carregando: boolean;
  erro: unknown;
}

export function useSessaoCompleta(): SessaoCompleta {
  const resultado = useSessaoAtual();
  return {
    sessao: resultado.data,
    carregando: resultado.isPending,
    erro: resultado.error,
  };
}
