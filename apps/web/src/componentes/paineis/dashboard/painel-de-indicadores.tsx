"use client";

import { useState } from "react";

import { PortaoDePermissao } from "@/lib/permissoes";

import { MarcacoesEmAberto } from "./marcacoes-em-aberto";
import { SecaoApuracao } from "./secao-apuracao";
import { SecaoBancoDeHoras } from "./secao-banco-de-horas";
import { SecaoColaboradores } from "./secao-colaboradores";
import { SecaoOcorrencias } from "./secao-ocorrencias";
import { SeletorDeEscopo, type EscopoDoDashboard } from "./seletor-de-escopo";

/**
 * Dashboard de RH/gestor/diretoria (T2/T3, PCF F9b §6).
 *
 * Cada seção é individualmente controlada por `<PortaoDePermissao>` com a
 * permissão exata do dado que ela mostra — nunca um `if perfil === "rh"` em
 * lugar nenhum. Não existe rótulo de "papel" nesta tela: RH, gestor e
 * diretoria veem exatamente as seções que a permissão efetiva de cada um
 * autoriza, sem nenhuma bifurcação de código por nome de papel.
 */
export function PainelDeIndicadores() {
  const [escopo, definirEscopo] = useState<EscopoDoDashboard>({
    empresaId: undefined,
    unidadeId: undefined,
  });

  return (
    <div className="flex flex-col gap-6">
      <PortaoDePermissao permissao="empresas.ler">
        <SeletorDeEscopo valor={escopo} aoMudar={definirEscopo} />
      </PortaoDePermissao>

      <PortaoDePermissao permissao="colaboradores.ler">
        <SecaoColaboradores escopo={escopo} />
      </PortaoDePermissao>

      <PortaoDePermissao permissao="apuracoes.ler">
        <SecaoApuracao escopo={escopo} />
      </PortaoDePermissao>

      <div className="grid gap-4 lg:grid-cols-2">
        <PortaoDePermissao permissao="ocorrencias.ler">
          <SecaoOcorrencias escopo={escopo} />
        </PortaoDePermissao>

        <PortaoDePermissao permissao="marcacoes.ler">
          <MarcacoesEmAberto escopo={escopo} />
        </PortaoDePermissao>
      </div>

      <PortaoDePermissao permissao="banco_horas.ler">
        <SecaoBancoDeHoras />
      </PortaoDePermissao>
    </div>
  );
}
