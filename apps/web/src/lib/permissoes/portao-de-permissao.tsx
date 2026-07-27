"use client";

import type { ReactNode } from "react";

import { useSessaoCompleta } from "@/ganchos/use-sessao-completa";

import { temPermissao } from "./tem-permissao";

export interface PortaoDePermissaoProps {
  /** Código exato de `x-permissao` do `openapi.yaml` (ex.: `"empresas.editar"`). */
  permissao: string;
  children: ReactNode;
  /** Mostrado enquanto a sessão completa ainda carrega. Padrão: nada (evita "pisca" de conteúdo indevido). */
  aoCarregar?: ReactNode;
  /** Mostrado quando a permissão está ausente. Padrão: nada — a seção simplesmente não existe para este usuário. */
  fallback?: ReactNode;
}

/**
 * Só renderiza os filhos quando `sessao.permissoes.includes(permissao)`
 * (T1, PCF F9b §6). Nenhuma tela desta fase decide visibilidade de
 * seção/ação por nome de papel — sempre por este componente (ou por
 * `temPermissao`, quando o gate está fora de JSX, ex. dentro de um `useQuery`
 * `enabled`).
 */
export function PortaoDePermissao({
  permissao,
  children,
  aoCarregar = null,
  fallback = null,
}: PortaoDePermissaoProps) {
  const { sessao, carregando } = useSessaoCompleta();

  if (carregando) return <>{aoCarregar}</>;
  if (!temPermissao(sessao, permissao)) return <>{fallback}</>;
  return <>{children}</>;
}
