"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { Alerta, AlertaDescricao, AlertaTitulo } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import { Cartao, CartaoCabecalho, CartaoConteudo, CartaoTitulo } from "@/componentes/ui/card";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { useComprovante } from "@/ganchos/use-comprovantes";
import { ehErroDaApi } from "@/lib/api";
import { formatarDataHora } from "@/lib/formatacao";

/**
 * `useParams()` (Client Component) em vez de aceitar `params` como prop:
 * evita depender de `React.use()` sobre uma Promise dentro de um teste sem
 * limite de suspensão dedicado, e é a forma padrão do App Router para ler o
 * segmento dinâmico num Client Component.
 */
export default function DetalheDeComprovante() {
  const parametros = useParams<{ comprovanteId: string }>();
  const comprovante = useComprovante(parametros.comprovanteId);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <Botao
          asChild
          variant="secundaria"
          tamanho="icone-toque"
          className="rounded-pleno shadow-flutuante-chip"
          aria-label="Voltar para comprovantes"
        >
          <Link href="/eu/comprovantes">
            <ArrowLeft className="size-4" />
          </Link>
        </Botao>
        <h1 className="estilo-titulo-pagina text-texto-primario">Comprovante</h1>
      </div>

      {comprovante.isPending ? (
        <Esqueleto className="h-64 w-full" />
      ) : comprovante.isError ? (
        <Alerta variant="erro">
          <AlertaTitulo>Não foi possível carregar este comprovante</AlertaTitulo>
          <AlertaDescricao>
            {ehErroDaApi(comprovante.error)
              ? comprovante.error.problema?.title
              : "Tente novamente em instantes."}
          </AlertaDescricao>
        </Alerta>
      ) : comprovante.data ? (
        <Cartao className="rounded-pronunciado shadow-flutuante-alta">
          <CartaoCabecalho>
            <CartaoTitulo>Comprovante {comprovante.data.numero}</CartaoTitulo>
          </CartaoCabecalho>
          <CartaoConteudo className="flex flex-col gap-4">
            <dl className="grid gap-3 sm:grid-cols-2">
              <div>
                <dt className="estilo-legenda uppercase text-texto-terciario">NSR</dt>
                <dd className="estilo-corpo text-texto-primario">{comprovante.data.nsr ?? "—"}</dd>
              </div>
              <div>
                <dt className="estilo-legenda uppercase text-texto-terciario">Marcação</dt>
                <dd className="estilo-corpo text-texto-primario">
                  {comprovante.data.datahoraMarcacao
                    ? formatarDataHora(comprovante.data.datahoraMarcacao)
                    : "—"}
                </dd>
              </div>
              <div>
                <dt className="estilo-legenda uppercase text-texto-terciario">Emitido em</dt>
                <dd className="estilo-corpo text-texto-primario">
                  {comprovante.data.emitidoEm ? formatarDataHora(comprovante.data.emitidoEm) : "—"}
                </dd>
              </div>
              <div>
                <dt className="estilo-legenda uppercase text-texto-terciario">Hash SHA-256</dt>
                <dd className="estilo-identificador break-all text-texto-primario">
                  {comprovante.data.hashSha256 ?? "—"}
                </dd>
              </div>
            </dl>

            {comprovante.data.conteudoTexto ? (
              <pre className="estilo-tabular whitespace-pre-wrap rounded-medio border border-borda-sutil bg-fundo-sutil p-4 text-texto-primario">
                {comprovante.data.conteudoTexto}
              </pre>
            ) : null}
          </CartaoConteudo>
        </Cartao>
      ) : null}
    </div>
  );
}
