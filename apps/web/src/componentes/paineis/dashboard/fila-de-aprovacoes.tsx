"use client";

import { Cartao, CartaoCabecalho, CartaoConteudo, CartaoTitulo } from "@/componentes/ui/card";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { ItemDeAprovacao } from "@/componentes/paineis/aprovacoes/item-de-aprovacao";
import { useAprovacoesPendentes } from "@/ganchos/use-aprovacoes";
import { useSessaoCompleta } from "@/ganchos/use-sessao-completa";
import { ehErroDaApi } from "@/lib/api";
import { temPermissao } from "@/lib/permissoes";
import { cn } from "@/lib/utils";

/**
 * "Fila de aprovações" do dashboard (T-painel, `docs/design-system-oficial.md`).
 * `GET /v1/aprovacoes` + `POST /v1/aprovacoes/{id}/decidir` já existiam desde
 * a F10 — esta é a primeira tela que os consome. O cartão de cada etapa
 * (`ItemDeAprovacao`) é compartilhado com a tela cheia `/painel/aprovacoes`.
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
