"use client";

import { Botao } from "@/componentes/ui/button";
import { useExecucaoDeRelatorio } from "@/ganchos/use-relatorios";

import { ROTULO_STATUS_EXECUCAO } from "./tipos";

interface AcompanhamentoDeExecucaoProps {
  execucaoId: string;
}

/**
 * Acompanha uma execução até concluir (poll de `GET /v1/relatorios/
 * execucoes/{execucaoId}` — `useExecucaoDeRelatorio` já para de sondar
 * sozinho quando o status deixa de ser `enfileirado`/`processando`). Serve
 * tanto o caminho síncrono (já chega `concluido`, sem nenhum poll extra:
 * a primeira leitura já para) quanto o assíncrono.
 */
export function AcompanhamentoDeExecucao({ execucaoId }: AcompanhamentoDeExecucaoProps) {
  const consulta = useExecucaoDeRelatorio(execucaoId);
  const execucao = consulta.data;

  if (consulta.isLoading || !execucao) {
    return <p className="estilo-legenda text-texto-terciario">Consultando execução…</p>;
  }

  const emAndamento = execucao.status === "enfileirado" || execucao.status === "processando";

  return (
    <div className="flex flex-col gap-2 rounded-suave bg-fundo-superficie p-4 shadow-flutuante-cartao">
      <div className="flex items-center justify-between">
        <p className="estilo-corpo font-medium text-texto-primario">
          {ROTULO_STATUS_EXECUCAO[execucao.status ?? ""] ?? execucao.status}
        </p>
        {typeof execucao.totalLinhas === "number" ? (
          <p className="estilo-legenda text-texto-terciario">{execucao.totalLinhas} linha(s)</p>
        ) : null}
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
