import type { Metadata } from "next";

import { PainelDeIndicadores } from "@/componentes/paineis/dashboard";

export const metadata: Metadata = { title: "Painel" };

/**
 * `/painel` — dashboard de RH, gestor e diretoria (T2/T3, PCF F9b).
 *
 * A vedação legal mais importante do projeto continua valendo aqui: nenhuma
 * tela desta área edita marcação. Toda correção de jornada é sempre um
 * TRATAMENTO (`POST /v1/tratamentos`), numa camada separada e auditada — a
 * regra é imposta em três lugares fora do controle do cliente (ausência de
 * rota de escrita em `marcacoes` no contrato, gatilho no banco, revogação de
 * privilégio da role da aplicação).
 *
 * A guarda de sessão (redireciona para `/?returnTo=/painel` sem sessão
 * válida) e a navegação vivem em `apps/web/src/app/painel/layout.tsx` /
 * `@/componentes/paineis/shell` — esta página assume que só monta quando já
 * existe sessão.
 */
export default function PaginaDoPainel() {
  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="estilo-titulo-pagina text-texto-primario">Painel</h1>
        <p className="estilo-corpo text-texto-secundario">
          Visão geral de colaboradores, apuração, ocorrências e marcações do dia.
        </p>
      </header>
      <PainelDeIndicadores />
    </div>
  );
}
