"use client";

import { Rotulo } from "@/componentes/ui/label";
import {
  Selecao,
  SelecaoConteudo,
  SelecaoGatilho,
  SelecaoItem,
  SelecaoValor,
} from "@/componentes/ui/select";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { useEmpresasDoTenant, useUnidadesDoTenant } from "@/ganchos/use-indicadores-dashboard";

const TODAS = "todas";

export interface EscopoDoDashboard {
  empresaId?: string | undefined;
  unidadeId?: string | undefined;
}

export interface SeletorDeEscopoProps {
  valor: EscopoDoDashboard;
  aoMudar: (escopo: EscopoDoDashboard) => void;
}

/**
 * Seletor de empresa/unidade do dashboard (T2, PCF F9b §6). Lê `GET
 * /v1/empresas`/`GET /v1/unidades` — NUNCA `SessaoAtual.empresasVisiveis`
 * (achado bloqueante nº2 do PCF: o campo está sempre `null` hoje, porque a F1
 * nunca o preencheu para sessão humana). A listagem já vem recortada pelo
 * RLS/RBAC do próprio tenant e escopo hierárquico do usuário — este
 * componente não filtra nada por conta própria, só oferece ESTREITAR a
 * consulta quando o usuário enxerga mais de uma empresa/unidade.
 */
export function SeletorDeEscopo({ valor, aoMudar }: SeletorDeEscopoProps) {
  const empresas = useEmpresasDoTenant();
  const unidades = useUnidadesDoTenant(valor.empresaId);

  if (empresas.isPending) {
    return <Esqueleto className="h-9 w-56" />;
  }

  // Radix `<Selecao>` não aceita `value=""` (reservado) — só entram itens com `id` real.
  const listaDeEmpresas = (empresas.data?.dados ?? []).filter(
    (empresa): empresa is typeof empresa & { id: string } => Boolean(empresa.id),
  );
  const listaDeUnidades = (unidades.data?.dados ?? []).filter(
    (unidade): unidade is typeof unidade & { id: string } => Boolean(unidade.id),
  );
  // Só uma empresa visível: o seletor não agrega valor, esconde para não poluir a tela.
  if (listaDeEmpresas.length <= 1) return null;

  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="flex flex-col gap-1">
        <Rotulo htmlFor="dashboard-seletor-empresa">Empresa</Rotulo>
        <Selecao
          value={valor.empresaId ?? TODAS}
          onValueChange={(novoValor) => {
            aoMudar({
              empresaId: novoValor === TODAS ? undefined : novoValor,
              unidadeId: undefined,
            });
          }}
        >
          <SelecaoGatilho id="dashboard-seletor-empresa" tamanho="compacto">
            <SelecaoValor placeholder="Todas as empresas" />
          </SelecaoGatilho>
          <SelecaoConteudo>
            <SelecaoItem value={TODAS}>Todas as empresas</SelecaoItem>
            {listaDeEmpresas.map((empresa) => (
              <SelecaoItem key={empresa.id} value={empresa.id}>
                {empresa.nomeFantasia || empresa.razaoSocial}
              </SelecaoItem>
            ))}
          </SelecaoConteudo>
        </Selecao>
      </div>

      {valor.empresaId && listaDeUnidades.length > 1 ? (
        <div className="flex flex-col gap-1">
          <Rotulo htmlFor="dashboard-seletor-unidade">Unidade</Rotulo>
          <Selecao
            value={valor.unidadeId ?? TODAS}
            onValueChange={(novoValor) => {
              aoMudar({ ...valor, unidadeId: novoValor === TODAS ? undefined : novoValor });
            }}
          >
            <SelecaoGatilho id="dashboard-seletor-unidade" tamanho="compacto">
              <SelecaoValor placeholder="Todas as unidades" />
            </SelecaoGatilho>
            <SelecaoConteudo>
              <SelecaoItem value={TODAS}>Todas as unidades</SelecaoItem>
              {listaDeUnidades.map((unidade) => (
                <SelecaoItem key={unidade.id} value={unidade.id}>
                  {unidade.nome}
                </SelecaoItem>
              ))}
            </SelecaoConteudo>
          </Selecao>
        </div>
      ) : null}
    </div>
  );
}
