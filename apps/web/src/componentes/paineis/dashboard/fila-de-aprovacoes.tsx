"use client";

import { useState } from "react";

import { Botao } from "@/componentes/ui/button";
import { Cartao, CartaoCabecalho, CartaoConteudo, CartaoTitulo } from "@/componentes/ui/card";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { useAprovacoesPendentes, useDecidirAprovacao } from "@/ganchos/use-aprovacoes";
import { useColaborador } from "@/ganchos/use-colaboradores";
import { useSessaoCompleta } from "@/ganchos/use-sessao-completa";
import { useSolicitacao } from "@/ganchos/use-solicitacoes";
import { useTiposSolicitacao } from "@/ganchos/use-tipos-solicitacao";
import { ehErroDaApi, type Esquema } from "@/lib/api";
import { temPermissao } from "@/lib/permissoes";
import { cn } from "@/lib/utils";

function iniciaisDoNome(nome: string | undefined): string {
  if (!nome) return "—";
  const partes = nome.trim().split(/\s+/);
  const primeira = partes[0]?.[0] ?? "";
  const ultima = partes.length > 1 ? (partes.at(-1)?.[0] ?? "") : "";
  return (primeira + ultima).toUpperCase();
}

/**
 * Uma etapa pendente — busca `Solicitacao` (para tipo/descrição/colaborador)
 * e `Colaborador` (para nome) por fora, já que `GET /v1/aprovacoes` só
 * devolve IDs (achado real: nenhuma tela consumia este endpoint antes desta
 * fila, o contrato nunca embutiu os dados do solicitante).
 */
function ItemDeAprovacao({
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

/**
 * "Fila de aprovações" do dashboard (T-painel, `docs/design-system-oficial.md`).
 * `GET /v1/aprovacoes` + `POST /v1/aprovacoes/{id}/decidir` já existiam desde
 * a F10 — esta é a primeira tela que os consome.
 */
export function FilaDeAprovacoes() {
  const { sessao } = useSessaoCompleta();
  const podeDecidir = temPermissao(sessao, "aprovacoes.aprovar");
  const consulta = useAprovacoesPendentes();
  const itens = consulta.data?.dados ?? [];

  return (
    <Cartao className={cn("rounded-suave shadow-flutuante-cartao")}>
      <CartaoCabecalho className="flex-row items-center gap-2">
        <CartaoTitulo>Fila de aprovações</CartaoTitulo>
        {consulta.isPending ? null : (
          <span className="font-mono text-2xs font-semibold rounded-pleno bg-acao-sutil-fundo px-2 py-0.5 text-acao-sutil-texto">
            {itens.length}
          </span>
        )}
      </CartaoCabecalho>
      <CartaoConteudo className="flex flex-col gap-2.5">
        {consulta.isPending ? (
          <>
            <Esqueleto className="h-20 w-full rounded-suave" />
            <Esqueleto className="h-20 w-full rounded-suave" />
          </>
        ) : consulta.isError ? (
          <p className="estilo-corpo text-estado-erro-texto">
            {ehErroDaApi(consulta.error) && consulta.error.problema?.title
              ? consulta.error.problema.title
              : "Não foi possível carregar a fila de aprovações."}
          </p>
        ) : itens.length === 0 ? (
          <div className="rounded-suave border border-dashed border-borda-sutil px-3.5 py-5 text-center">
            <p className="estilo-corpo font-semibold text-estado-sucesso-texto">Fila zerada</p>
            <p className="estilo-legenda mt-1 text-texto-terciario">
              Nada aguardando decisão sua.
            </p>
          </div>
        ) : (
          itens.map((aprovacao) => (
            <ItemDeAprovacao
              key={aprovacao.id}
              aprovacao={aprovacao}
              podeDecidir={podeDecidir}
            />
          ))
        )}
      </CartaoConteudo>
    </Cartao>
  );
}
