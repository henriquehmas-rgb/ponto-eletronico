"use client";

import type { VariantProps } from "class-variance-authority";
import { Ban, CheckCircle2, Clock, Loader2, XCircle } from "lucide-react";

import { Selo, type badgeVariants } from "@/componentes/ui/badge";
import { Botao } from "@/componentes/ui/button";
import { useExecucaoDeRelatorio } from "@/ganchos/use-relatorios";
import { formatarDataHora } from "@/lib/formatacao/data";

import { ROTULO_STATUS_EXECUCAO } from "./tipos";

interface AcompanhamentoDeExecucaoProps {
  execucaoId: string;
  /** Nome do relatório (`RelatorioDefinicao.nome`), para a linha da lista de
   * execuções recentes — o componente só recebe o `execucaoId`, então quem
   * já carregou a definição (tela de execução) repassa o nome. */
  nome?: string | undefined;
}

type VarianteDoSelo = VariantProps<typeof badgeVariants>["variant"];

const VARIANTE_POR_STATUS: Record<string, VarianteDoSelo> = {
  enfileirado: "neutro",
  processando: "atencao",
  concluido: "sucesso",
  falhou: "erro",
  cancelado: "neutro",
  expirado: "neutro",
};

const ICONE_POR_STATUS: Record<string, typeof Clock> = {
  enfileirado: Clock,
  processando: Loader2,
  concluido: CheckCircle2,
  falhou: XCircle,
  cancelado: Ban,
  expirado: Clock,
};

/**
 * Acompanha uma execução até concluir (poll de `GET /v1/relatorios/
 * execucoes/{execucaoId}` — `useExecucaoDeRelatorio` já para de sondar
 * sozinho quando o status deixa de ser `enfileirado`/`processando`). Serve
 * tanto o caminho síncrono (já chega `concluido`, sem nenhum poll extra:
 * a primeira leitura já para) quanto o assíncrono.
 *
 * Visualmente é uma linha de "execuções recentes" (ícone + nome + quando +
 * selo de status), reaproveitada como item único logo após executar.
 */
export function AcompanhamentoDeExecucao({ execucaoId, nome }: AcompanhamentoDeExecucaoProps) {
  const consulta = useExecucaoDeRelatorio(execucaoId);
  const execucao = consulta.data;

  if (consulta.isLoading || !execucao) {
    return <p className="estilo-legenda text-texto-terciario">Consultando execução…</p>;
  }

  const emAndamento = execucao.status === "enfileirado" || execucao.status === "processando";
  const Icone = ICONE_POR_STATUS[execucao.status ?? ""] ?? Clock;
  const quando = execucao.criadoEm ? formatarDataHora(execucao.criadoEm) : null;

  return (
    <div className="flex flex-col gap-3 rounded-suave bg-fundo-superficie p-4 shadow-flutuante-cartao">
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-pleno bg-acao-sutil-fundo text-acao-sutil-texto">
          <Icone className={emAndamento ? "size-5 animate-spin" : "size-5"} aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate estilo-corpo font-medium text-texto-primario">
            {nome ?? execucao.relatorioCodigo}
          </p>
          <p className="estilo-legenda text-texto-terciario">
            {quando ?? "agora"}
            {typeof execucao.totalLinhas === "number" ? ` · ${execucao.totalLinhas} linha(s)` : ""}
          </p>
        </div>
        <Selo variant={VARIANTE_POR_STATUS[execucao.status ?? ""] ?? "neutro"}>
          {ROTULO_STATUS_EXECUCAO[execucao.status ?? ""] ?? execucao.status}
        </Selo>
      </div>

      {emAndamento ? (
        <div
          className="h-2 w-full overflow-hidden rounded-pequeno bg-fundo-enfase"
          role="progressbar"
          aria-valuenow={execucao.progresso ?? 0}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className="h-full bg-acao-primaria-fundo transition-[width] duration-padrao"
            style={{ width: `${execucao.progresso ?? 0}%` }}
          />
        </div>
      ) : null}

      {execucao.status === "falhou" ? (
        <p className="estilo-legenda text-estado-erro-texto">
          {execucao.erro ?? "A execução falhou."}
        </p>
      ) : null}

      {execucao.status === "concluido" && execucao.urlDownload ? (
        <Botao asChild variant="primaria" tamanho="compacto" className="w-fit rounded-pleno">
          <a href={execucao.urlDownload} target="_blank" rel="noreferrer">
            Baixar resultado
          </a>
        </Botao>
      ) : null}

      {execucao.status === "expirado" ? (
        <p className="estilo-legenda text-texto-terciario">
          O artefato expirou. Execute o relatório novamente.
        </p>
      ) : null}
    </div>
  );
}
