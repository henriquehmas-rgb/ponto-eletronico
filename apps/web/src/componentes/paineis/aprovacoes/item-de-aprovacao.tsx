"use client";

import { useState } from "react";

import { Botao } from "@/componentes/ui/button";
import { useDecidirAprovacao } from "@/ganchos/use-aprovacoes";
import { useColaborador } from "@/ganchos/use-colaboradores";
import { useSolicitacao } from "@/ganchos/use-solicitacoes";
import { useTiposSolicitacao } from "@/ganchos/use-tipos-solicitacao";
import { ehErroDaApi, type Esquema } from "@/lib/api";

/** Iniciais de um nome completo — mesma regra usada no avatar circular do
 * padrão "item de lista com avatar circular" (`docs/design-system-oficial.md`). */
export function iniciaisDoNome(nome: string | undefined): string {
  if (!nome) return "—";
  const partes = nome.trim().split(/\s+/);
  const primeira = partes[0]?.[0] ?? "";
  const ultima = partes.length > 1 ? (partes.at(-1)?.[0] ?? "") : "";
  return (primeira + ultima).toUpperCase();
}

/**
 * Um cartão de etapa de aprovação — busca `Solicitacao` (para tipo/descrição/
 * colaborador) e `Colaborador` (para nome) por fora, já que `GET /v1/aprovacoes`
 * só devolve IDs (achado real: o contrato nunca embutiu os dados do
 * solicitante). Compartilhado entre o widget resumido do dashboard
 * (`componentes/paineis/dashboard/fila-de-aprovacoes.tsx`) e a tela cheia
 * `/painel/aprovacoes` — a lógica de decidir (aprovar/recusar com comentário
 * obrigatório na recusa) vive só aqui, uma vez.
 */
export function ItemDeAprovacao({
  aprovacao,
  podeDecidir,
}: {
  aprovacao: Esquema<"Aprovacao">;
  podeDecidir: boolean;
}) {
  const aprovacaoId = aprovacao.id;
  const solicitacao = useSolicitacao(aprovacao.solicitacaoId);
  const colaborador = useColaborador(solicitacao.data?.colaboradorId);
  const tipos = useTiposSolicitacao();
  const decidir = useDecidirAprovacao();
  const [recusando, definirRecusando] = useState(false);
  const [comentario, definirComentario] = useState("");

  const tipoRotulo =
    tipos.data?.dados?.find((tipo) => tipo.id === solicitacao.data?.tipoSolicitacaoId)?.nome ??
    "Solicitação";
  const nomeColaborador = colaborador.data?.nomeCompleto;

  function aoAprovar() {
    if (!aprovacaoId) return;
    decidir.mutate({ aprovacaoId, decisao: "aprovar" });
  }

  function aoConfirmarRecusa() {
    if (!aprovacaoId || !comentario.trim()) return;
    decidir.mutate(
      { aprovacaoId, decisao: "reprovar", comentario: comentario.trim() },
      { onSuccess: () => definirRecusando(false) },
    );
  }

  return (
    <div className="rounded-suave border border-borda-sutil bg-fundo-sutil p-3.5">
      <div className="flex items-start gap-2.5">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-pleno bg-acao-sutil-fundo text-3xs font-semibold text-acao-sutil-texto">
          {colaborador.isPending ? "…" : iniciaisDoNome(nomeColaborador)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="estilo-corpo truncate font-semibold text-texto-primario">
            {colaborador.isPending ? "Carregando…" : (nomeColaborador ?? "Colaborador")}
          </p>
          <p className="estilo-legenda text-texto-secundario">
            {tipoRotulo}
            {solicitacao.data?.descricao ? ` · ${solicitacao.data.descricao}` : ""}
          </p>
          {aprovacao.prazoEm ? (
            <p className="estilo-identificador mt-0.5 text-texto-terciario">
              Prazo {new Date(aprovacao.prazoEm).toLocaleDateString("pt-BR")}
            </p>
          ) : null}
        </div>
      </div>

      {!podeDecidir ? null : recusando ? (
        <div className="mt-3 flex flex-col gap-2">
          <textarea
            value={comentario}
            onChange={(evento) => definirComentario(evento.target.value)}
            placeholder="Motivo da recusa (obrigatório)"
            rows={2}
            className="w-full rounded-medio border border-borda-sutil bg-fundo-aplicacao p-2 text-xs text-texto-primario placeholder:text-texto-terciario"
          />
          <div className="flex gap-2">
            <Botao
              type="button"
              variant="destrutiva"
              tamanho="compacto"
              className="flex-1"
              disabled={!comentario.trim() || decidir.isPending}
              onClick={aoConfirmarRecusa}
            >
              Confirmar recusa
            </Botao>
            <Botao
              type="button"
              variant="secundaria"
              tamanho="compacto"
              onClick={() => {
                definirRecusando(false);
                definirComentario("");
              }}
            >
              Cancelar
            </Botao>
          </div>
        </div>
      ) : (
        <div className="mt-3 flex gap-2">
          <Botao
            type="button"
            variant="primaria"
            tamanho="compacto"
            className="flex-1"
            disabled={decidir.isPending}
            onClick={aoAprovar}
          >
            Aprovar
          </Botao>
          <Botao
            type="button"
            variant="secundaria"
            tamanho="compacto"
            className="flex-1"
            disabled={decidir.isPending}
            onClick={() => definirRecusando(true)}
          >
            Recusar
          </Botao>
        </div>
      )}

      {decidir.isError ? (
        <p className="estilo-legenda mt-2 text-estado-erro-texto">
          {ehErroDaApi(decidir.error) ? decidir.error.problema?.title : "Não foi possível decidir."}
        </p>
      ) : null}
    </div>
  );
}
