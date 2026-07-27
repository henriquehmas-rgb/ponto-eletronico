"use client";

import Link from "next/link";

import { CartaoDeSaldoDeBanco } from "@/componentes/dominio/cartao-de-saldo-de-banco";
import {
  LinhaDoTempoDeMarcacoes,
  type MarcacaoDaLinhaDoTempo,
} from "@/componentes/dominio/linha-do-tempo-de-marcacoes";
import { Alerta, AlertaDescricao, AlertaTitulo } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import { Cartao, CartaoCabecalho, CartaoConteudo, CartaoTitulo } from "@/componentes/ui/card";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { useSaldoBancoHoras } from "@/ganchos/use-banco-de-horas";
import { useEspelhoDePonto } from "@/ganchos/use-espelho-de-ponto";
import { ehErroDaApi, type Esquema } from "@/lib/api";
import { paramsSemUndefined } from "@/lib/formatacao-f8/parametros-de-consulta";

/** Início e fim (ISO) do dia civil corrente, no fuso do navegador. */
function limitesDoDiaDeHoje(): { de: string; ate: string } {
  const agora = new Date();
  const inicio = new Date(agora.getFullYear(), agora.getMonth(), agora.getDate(), 0, 0, 0, 0);
  const fim = new Date(agora.getFullYear(), agora.getMonth(), agora.getDate() + 1, 0, 0, 0, 0);
  return { de: inicio.toISOString(), ate: fim.toISOString() };
}

function paraLinhaDoTempo(marcacao: Esquema<"Marcacao">): MarcacaoDaLinhaDoTempo {
  return {
    id: marcacao.id ?? "",
    datahoraMarcacao: marcacao.datahoraMarcacao ?? "",
    canal: marcacao.canal ?? "web",
    ...paramsSemUndefined({ nsr: marcacao.nsr, sentidoInformado: marcacao.sentidoInformado }),
  };
}

export default function PainelDoColaborador() {
  const limites = limitesDoDiaDeHoje();
  const espelho = useEspelhoDePonto(limites);
  const saldo = useSaldoBancoHoras();

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="estilo-titulo-pagina text-texto-primario">Meu dia</h1>
        <Botao asChild tamanho="toque">
          <Link href="/eu/registrar">Registrar ponto</Link>
        </Botao>
      </header>

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <Cartao>
          <CartaoCabecalho>
            <CartaoTitulo>Marcações de hoje</CartaoTitulo>
          </CartaoCabecalho>
          <CartaoConteudo>
            {espelho.isPending ? (
              <div className="flex flex-col gap-2">
                <Esqueleto className="h-8 w-full" />
                <Esqueleto className="h-8 w-full" />
                <Esqueleto className="h-8 w-2/3" />
              </div>
            ) : espelho.isError ? (
              <Alerta variant="erro">
                <AlertaTitulo>Não foi possível carregar suas marcações</AlertaTitulo>
                <AlertaDescricao>
                  {ehErroDaApi(espelho.error)
                    ? espelho.error.problema?.title
                    : "Tente novamente em instantes."}
                </AlertaDescricao>
              </Alerta>
            ) : (
              <LinhaDoTempoDeMarcacoes
                marcacoes={(espelho.data?.dados ?? []).map(paraLinhaDoTempo)}
                mensagemVazia="Nenhuma marcação registrada hoje."
              />
            )}
          </CartaoConteudo>
        </Cartao>

        {saldo.isPending ? (
          <Esqueleto className="h-40 w-full" />
        ) : saldo.isError ? (
          <Alerta variant="erro">
            <AlertaTitulo>Não foi possível carregar seu saldo</AlertaTitulo>
            <AlertaDescricao>
              {ehErroDaApi(saldo.error)
                ? saldo.error.problema?.title
                : "Tente novamente em instantes."}
            </AlertaDescricao>
          </Alerta>
        ) : saldo.data ? (
          <CartaoDeSaldoDeBanco
            saldoMinutos={saldo.data.saldoMinutos ?? 0}
            {...paramsSemUndefined({
              contaCodigo: saldo.data.contaCodigo,
              aVencer30Minutos: saldo.data.aVencer30Minutos,
              proximoVencimentoEm:
                (saldo.data.aVencer30Minutos ?? 0) > 0 ? saldo.data.periodoFim : undefined,
            })}
          />
        ) : null}
      </div>
    </div>
  );
}
