"use client";

import { Selo } from "@/componentes/ui/badge";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { ItemDeAprovacao, iniciaisDoNome } from "@/componentes/paineis/aprovacoes/item-de-aprovacao";
import { useAprovacoesPendentes, useAprovacoesPorDecisao } from "@/ganchos/use-aprovacoes";
import { useColaborador } from "@/ganchos/use-colaboradores";
import { useSessaoCompleta } from "@/ganchos/use-sessao-completa";
import { useSolicitacao } from "@/ganchos/use-solicitacoes";
import { useTiposSolicitacao } from "@/ganchos/use-tipos-solicitacao";
import { ehErroDaApi, type Esquema } from "@/lib/api";
import { temPermissao } from "@/lib/permissoes";

const SELO_POR_DECISAO: Record<string, "sucesso" | "erro"> = {
  aprovada: "sucesso",
  reprovada: "erro",
};

/**
 * Uma linha da seção "Decididas recentemente" — mesma resolução por fora
 * (solicitação → colaborador/tipo) que `ItemDeAprovacao`, mas sem os botões
 * de decisão (a etapa já foi decidida).
 */
function LinhaDecidida({ aprovacao }: { aprovacao: Esquema<"Aprovacao"> }) {
  const solicitacao = useSolicitacao(aprovacao.solicitacaoId);
  const colaborador = useColaborador(solicitacao.data?.colaboradorId);
  const tipos = useTiposSolicitacao();
  const tipoRotulo =
    tipos.data?.dados?.find((tipo) => tipo.id === solicitacao.data?.tipoSolicitacaoId)?.nome ??
    "Solicitação";
  const nomeColaborador = colaborador.data?.nomeCompleto;

  return (
    <div className="flex items-center gap-[var(--espacamento-3)] rounded-suave bg-fundo-superficie p-[var(--espacamento-3)] shadow-flutuante-cartao">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-pleno bg-acao-sutil-fundo text-3xs font-semibold text-acao-sutil-texto">
        {colaborador.isPending ? "…" : iniciaisDoNome(nomeColaborador)}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[14px] font-medium text-texto-primario">
          {colaborador.isPending ? "Carregando…" : (nomeColaborador ?? "Colaborador")}
        </p>
        <p className="truncate text-[11px] text-texto-terciario">
          {tipoRotulo}
          {solicitacao.data?.descricao ? ` · ${solicitacao.data.descricao}` : ""}
        </p>
      </div>
      <Selo variant={SELO_POR_DECISAO[aprovacao.decisao ?? ""] ?? "neutro"}>
        {aprovacao.decisao === "aprovada" ? "Aprovada" : "Recusada"}
      </Selo>
      {aprovacao.id ? (
        <span className="font-mono text-3xs text-texto-desabilitado">
          {aprovacao.id.slice(0, 8)}
        </span>
      ) : null}
    </div>
  );
}

/**
 * Conteúdo da rota `/painel/aprovacoes` — grade de 2 colunas com as etapas
 * pendentes (mesmo cartão do widget do dashboard) e, quando há dado real
 * disponível, a seção "Decididas recentemente" (`GET /v1/aprovacoes` com
 * `decisao=aprovada`/`reprovada`, contrato §13295).
 */
export function ListaDeAprovacoes() {
  const { sessao } = useSessaoCompleta();
  const podeDecidir = temPermissao(sessao, "aprovacoes.aprovar");
  const pendentes = useAprovacoesPendentes(50);
  const aprovadas = useAprovacoesPorDecisao("aprovada", 6);
  const reprovadas = useAprovacoesPorDecisao("reprovada", 6);

  const itensPendentes = pendentes.data?.dados ?? [];
  const decididas = [...(aprovadas.data?.dados ?? []), ...(reprovadas.data?.dados ?? [])]
    .sort((a, b) => (b.decididoEm ?? "").localeCompare(a.decididoEm ?? ""))
    .slice(0, 6);
  const carregandoDecididas = aprovadas.isPending || reprovadas.isPending;

  return (
    <div className="flex flex-col gap-8">
      <section>
        {pendentes.isPending ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Esqueleto className="h-24 w-full rounded-suave" />
            <Esqueleto className="h-24 w-full rounded-suave" />
            <Esqueleto className="h-24 w-full rounded-suave" />
            <Esqueleto className="h-24 w-full rounded-suave" />
          </div>
        ) : pendentes.isError ? (
          <p className="estilo-corpo text-estado-erro-texto">
            {ehErroDaApi(pendentes.error) && pendentes.error.problema?.title
              ? pendentes.error.problema.title
              : "Não foi possível carregar a fila de aprovações."}
          </p>
        ) : itensPendentes.length === 0 ? (
          <div className="rounded-suave border border-dashed border-borda-padrao p-6 text-center">
            <p className="estilo-corpo font-semibold text-estado-sucesso-texto">Fila zerada</p>
            <p className="estilo-legenda mt-1 text-texto-terciario">
              Nada aguardando decisão sua.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {itensPendentes.map((aprovacao) => (
              <ItemDeAprovacao key={aprovacao.id} aprovacao={aprovacao} podeDecidir={podeDecidir} />
            ))}
          </div>
        )}
      </section>

      {carregandoDecididas || decididas.length > 0 ? (
        <section className="flex flex-col gap-3">
          <h2 className="estilo-corpo font-semibold text-texto-primario">
            Decididas recentemente
          </h2>
          {carregandoDecididas ? (
            <div className="flex flex-col gap-2.5">
              <Esqueleto className="h-14 w-full rounded-suave" />
              <Esqueleto className="h-14 w-full rounded-suave" />
            </div>
          ) : (
            <div className="flex flex-col gap-2.5">
              {decididas.map((aprovacao) => (
                <LinhaDecidida key={aprovacao.id} aprovacao={aprovacao} />
              ))}
            </div>
          )}
        </section>
      ) : null}
    </div>
  );
}
