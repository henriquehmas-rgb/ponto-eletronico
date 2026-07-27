"use client";

import { CartaoDeSaldoDeBanco } from "@/componentes/dominio/cartao-de-saldo-de-banco";
import { Cartao, CartaoConteudo } from "@/componentes/ui/card";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { useSaldoBancoHorasAmostra } from "@/ganchos/use-indicadores-dashboard";
import { useSessaoCompleta } from "@/ganchos/use-sessao-completa";
import { ehErroDaApi } from "@/lib/api";

/**
 * Banco de horas como AMOSTRA — só o do próprio usuário logado, quando
 * `SessaoAtual.colaboradorId` existir (T2, PCF F9b §2: `obterSaldoBancoHoras`
 * exige `colaboradorId` no caminho; não há endpoint agregado por empresa/
 * unidade, e administração de política/conta está fora do escopo desta fase).
 * Sem `colaboradorId` (RH/gestor sem vínculo próprio, o caso comum), a seção
 * simplesmente não aparece — honesto em vez de inventar uma agregação que o
 * contrato não oferece.
 */
export function SecaoBancoDeHoras() {
  const { sessao, carregando: carregandoSessao } = useSessaoCompleta();
  const saldo = useSaldoBancoHorasAmostra();

  if (carregandoSessao) return <Esqueleto className="h-40 w-full" />;
  if (!sessao?.colaboradorId) return null;

  if (saldo.isPending) return <Esqueleto className="h-40 w-full" />;

  if (saldo.isError) {
    return (
      <Cartao>
        <CartaoConteudo>
          <p className="estilo-corpo text-estado-erro-texto">
            Não foi possível carregar o saldo de banco de horas
            {ehErroDaApi(saldo.error) && saldo.error.problema?.title
              ? `: ${saldo.error.problema.title}`
              : "."}
          </p>
        </CartaoConteudo>
      </Cartao>
    );
  }

  if (!saldo.data) return null;

  return (
    <CartaoDeSaldoDeBanco
      saldoMinutos={saldo.data.saldoMinutos ?? 0}
      {...(saldo.data.contaCodigo ? { contaCodigo: saldo.data.contaCodigo } : {})}
      {...(saldo.data.aVencer30Minutos !== undefined
        ? { aVencer30Minutos: saldo.data.aVencer30Minutos }
        : {})}
      {...((saldo.data.aVencer30Minutos ?? 0) > 0 && saldo.data.periodoFim
        ? { proximoVencimentoEm: saldo.data.periodoFim }
        : {})}
    />
  );
}
