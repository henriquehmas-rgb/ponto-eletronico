"use client";

import { GraficoDeLinha } from "@/componentes/graficos/graficos";
import { CartaoDeSaldoDeBanco } from "@/componentes/dominio/cartao-de-saldo-de-banco";
import { Cartao, CartaoCabecalho, CartaoConteudo, CartaoTitulo } from "@/componentes/ui/card";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { CHAVE_VALOR_SALDO_BANCO_HORAS, useTendenciaMensal } from "@/ganchos/use-dataviz-dashboard";
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
  // Dataviz (T13, PCF F11 §2.6): evolução do saldo dos últimos 6 meses,
  // alimentada pelo motor de relatórios (dataset `banco-de-horas` do
  // catálogo) — mesma restrição de AMOSTRA do KPI acima (só o
  // `colaboradorId` do próprio usuário logado; hooks sempre chamados, nunca
  // condicionalmente, `habilitado` decide se a chamada de rede dispara).
  const tendenciaDeSaldo = useTendenciaMensal({
    codigo: "banco-de-horas",
    chaveValor: CHAVE_VALOR_SALDO_BANCO_HORAS,
    colaboradorId: sessao?.colaboradorId,
    habilitado: Boolean(sessao?.colaboradorId),
  });

  if (carregandoSessao) return <Esqueleto className="h-40 w-full" />;
  if (!sessao?.colaboradorId) return null;

  if (saldo.isPending) return <Esqueleto className="h-40 w-full" />;

  if (saldo.isError) {
    // 404 = colaborador sem conta de banco de horas (ex.: perfil administrativo
    // sem jornada de compensação vinculada) — estado normal, mesmo tratamento
    // de "seção não se aplica" já usado acima para `!sessao?.colaboradorId`,
    // não um erro de servidor. Achado real em ponto-hml, 09/08/2026 (mesma
    // causa raiz já corrigida em `/eu`, `app/eu/page.tsx`).
    if (ehErroDaApi(saldo.error) && saldo.error.status === 404) return null;
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
    <div className="flex flex-col gap-4">
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

      <Cartao className="rounded-suave shadow-flutuante-cartao">
        <CartaoCabecalho>
          <CartaoTitulo>Evolução do saldo (últimos 6 meses)</CartaoTitulo>
        </CartaoCabecalho>
        <CartaoConteudo>
          {tendenciaDeSaldo.isPending ? (
            <p className="estilo-corpo text-texto-secundario">Carregando…</p>
          ) : tendenciaDeSaldo.isError ? (
            <p className="estilo-corpo text-estado-erro-texto">
              Não foi possível carregar a evolução do saldo.
            </p>
          ) : !tendenciaDeSaldo.data || tendenciaDeSaldo.data.length === 0 ? (
            <p className="estilo-corpo text-texto-secundario">
              Sem dado suficiente no período para montar a evolução.
            </p>
          ) : (
            <GraficoDeLinha
              dados={tendenciaDeSaldo.data}
              chaveCategoria="mes"
              altura={220}
              series={[{ chave: "valor", rotulo: "Saldo (min)" }]}
            />
          )}
        </CartaoConteudo>
      </Cartao>
    </div>
  );
}
