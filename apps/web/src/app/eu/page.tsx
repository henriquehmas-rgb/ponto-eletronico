"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowUpRight, Clock3 } from "lucide-react";

import { Alerta, AlertaDescricao, AlertaTitulo } from "@/componentes/ui/alert";
import { Cartao } from "@/componentes/ui/card";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { useSaldoBancoHoras } from "@/ganchos/use-banco-de-horas";
import { useEspelhoDePonto } from "@/ganchos/use-espelho-de-ponto";
import { ehErroDaApi, type Esquema } from "@/lib/api";
import { formatarHora } from "@/lib/formatacao/data";
import { formatarSaldo } from "@/lib/formatacao/saldo";
import { minutosParaHHMM } from "@/lib/formatacao/tempo";
import { paramsSemUndefined } from "@/lib/formatacao-f8/parametros-de-consulta";
import { useSessao } from "@/lib/sessao";
import { cn } from "@/lib/utils";

/** Início e fim (ISO) do dia civil corrente, no fuso do navegador. */
function limitesDoDiaDeHoje(): { de: string; ate: string } {
  const agora = new Date();
  const inicio = new Date(agora.getFullYear(), agora.getMonth(), agora.getDate(), 0, 0, 0, 0);
  const fim = new Date(agora.getFullYear(), agora.getMonth(), agora.getDate() + 1, 0, 0, 0, 0);
  return { de: inicio.toISOString(), ate: fim.toISOString() };
}

const ROTULO_CANAL: Record<string, string> = {
  terminal: "Terminal",
  mobile: "Celular",
  web: "Web",
  totem: "Totem",
  api: "API",
  importacao: "Importação",
};

const ROTULO_SENTIDO: Record<string, string> = {
  entrada: "Entrada",
  saida: "Saída",
};

/** Iniciais do nome (até duas letras) para o avatar — sem depender de foto. */
function iniciaisDoNome(nome: string | undefined): string {
  if (!nome) return "?";
  const partes = nome.trim().split(/\s+/).filter(Boolean);
  if (partes.length === 0) return "?";
  const primeira = partes[0]?.[0] ?? "";
  const ultima = partes.length > 1 ? (partes[partes.length - 1]?.[0] ?? "") : "";
  return `${primeira}${ultima}`.toUpperCase();
}

function saudacaoPorHora(hora: number): string {
  if (hora < 12) return "Bom dia";
  if (hora < 18) return "Boa tarde";
  return "Boa noite";
}

/** Atalhos de serviço reais da área do colaborador — nenhum é fabricado, todos apontam para rotas existentes. */
const SERVICOS = [
  { rotulo: "Solicitações", href: "/eu/solicitacoes", sigla: "SO" },
  { rotulo: "Comprovantes", href: "/eu/comprovantes", sigla: "CO" },
  { rotulo: "Perfil", href: "/eu/perfil", sigla: "PE" },
] as const;

export default function PainelDoColaborador() {
  const sessao = useSessao();
  const limites = limitesDoDiaDeHoje();
  const espelho = useEspelhoDePonto(limites);
  const saldo = useSaldoBancoHoras();

  // `agora` só é preenchido depois de montar, no cliente — evita divergir do
  // horário renderizado no servidor (hidratação) e mantém o relógio vivo.
  const [agora, definirAgora] = useState<Date | null>(null);
  useEffect(() => {
    definirAgora(new Date());
    const intervalo = window.setInterval(() => definirAgora(new Date()), 30_000);
    return () => window.clearInterval(intervalo);
  }, []);

  const marcacoes = espelho.data?.dados ?? [];
  const ultimaMarcacao = marcacoes.at(-1);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-center gap-3 px-1">
        <span
          aria-hidden="true"
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-pleno bg-gradient-to-br from-acao-primaria-fundo to-acao-primaria-fundo-ativo text-sm font-semibold text-texto-inverso"
        >
          {iniciaisDoNome(sessao.usuario?.nome)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="estilo-legenda text-texto-terciario">
            {agora ? saudacaoPorHora(agora.getHours()) : "Olá"}
          </p>
          <h1 className="estilo-titulo-cartao truncate text-texto-primario">
            {sessao.usuario?.nome ?? "Colaborador"}
          </h1>
        </div>
      </header>

      <div
        className="relative overflow-hidden rounded-pronunciado p-[var(--espacamento-5)]
                   bg-gradient-to-br from-acao-primaria-fundo
                   via-acao-primaria-fundo-hover to-acao-primaria-fundo-ativo
                   shadow-flutuante-alta text-texto-inverso"
      >
        <div className="relative flex flex-col gap-4">
          <div>
            <p
              className="estilo-legenda uppercase text-texto-inverso/70"
              style={{ letterSpacing: "0.06em" }}
            >
              {agora
                ? new Intl.DateTimeFormat("pt-BR", {
                    weekday: "long",
                    day: "2-digit",
                    month: "long",
                  }).format(agora)
                : "—"}
            </p>
            <p className="estilo-numero-destaque mt-1 tabular-nums text-texto-inverso">
              {agora
                ? new Intl.DateTimeFormat("pt-BR", {
                    hour: "2-digit",
                    minute: "2-digit",
                    hour12: false,
                  }).format(agora)
                : "--:--"}
            </p>
            <p className="estilo-corpo mt-1 text-texto-inverso/90">
              {ultimaMarcacao
                ? `Última marcação às ${formatarHora(ultimaMarcacao.datahoraMarcacao ?? "")}`
                : "Nenhuma marcação registrada hoje"}
            </p>
          </div>

          <Link
            href="/eu/registrar"
            style={{ height: 60 }}
            className="flex items-center justify-between gap-3 rounded-suave bg-fundo-superficie pl-[var(--espacamento-5)] pr-2 text-texto-primario shadow-flutuante-cartao"
          >
            <span className="estilo-titulo-cartao">Registrar ponto</span>
            <span className="flex h-11 w-11 items-center justify-center rounded-pleno bg-fundo-inverso text-texto-inverso">
              <ArrowUpRight className="h-5 w-5" aria-hidden="true" />
            </span>
          </Link>
        </div>
      </div>

      {saldo.isPending ? (
        <Esqueleto className="h-32 w-full rounded-suave" />
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
        <TileDeSaldoDeBanco
          saldoMinutos={saldo.data.saldoMinutos ?? 0}
          {...paramsSemUndefined({
            contaCodigo: saldo.data.contaCodigo,
            aVencer30Minutos: saldo.data.aVencer30Minutos,
            proximoVencimentoEm:
              (saldo.data.aVencer30Minutos ?? 0) > 0 ? saldo.data.periodoFim : undefined,
          })}
        />
      ) : null}

      <div className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between px-1">
          <h2 className="estilo-titulo-secao text-texto-primario">Hoje</h2>
          <Link href="/eu/extrato" className="estilo-rotulo text-acao-sutil-texto">
            Ver espelho
          </Link>
        </div>

        {espelho.isPending ? (
          <div className="flex flex-col gap-2">
            <Esqueleto className="h-16 w-full rounded-suave" />
            <Esqueleto className="h-16 w-full rounded-suave" />
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
        ) : marcacoes.length === 0 ? (
          <div className="rounded-suave border border-dashed border-borda-padrao p-6 text-center">
            <p className="estilo-corpo font-semibold text-texto-primario">Nenhuma marcação hoje</p>
            <p className="estilo-legenda mt-1 text-texto-terciario">
              Suas marcações do dia aparecem aqui assim que forem registradas.
            </p>
          </div>
        ) : (
          <ol className="flex flex-col gap-2" aria-label="Marcações de hoje">
            {marcacoes.map((marcacao) => (
              <li key={marcacao.id ?? marcacao.datahoraMarcacao}>
                <ItemDeMarcacao marcacao={marcacao} />
              </li>
            ))}
          </ol>
        )}
      </div>

      <div className="flex flex-col gap-3">
        <h2 className="estilo-titulo-secao px-1 text-texto-primario">Serviços</h2>
        <div className="flex flex-wrap gap-2">
          {SERVICOS.map((servico) => (
            <Link
              key={servico.href}
              href={servico.href}
              className="inline-flex items-center gap-2 rounded-pleno bg-fundo-superficie px-3 py-2
                         shadow-flutuante-chip estilo-rotulo text-texto-secundario"
            >
              <span
                style={{ height: 22, width: 22 }}
                className="flex items-center justify-center rounded-pleno bg-acao-sutil-fundo text-3xs font-semibold text-acao-sutil-texto"
              >
                {servico.sigla}
              </span>
              {servico.rotulo}
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}

function TileDeSaldoDeBanco({
  saldoMinutos,
  contaCodigo,
  aVencer30Minutos,
  proximoVencimentoEm,
}: {
  saldoMinutos: number;
  contaCodigo?: string;
  aVencer30Minutos?: number;
  proximoVencimentoEm?: string;
}) {
  const saldo = formatarSaldo(saldoMinutos);
  const corSinal =
    saldo.sinal === "credor"
      ? "text-estado-sucesso-texto"
      : saldo.sinal === "devedor"
        ? "text-estado-erro-texto"
        : "text-texto-secundario";
  // Sinal explícito por FORMA (ícone), não só por cor (WCAG 1.4.1) — mesma
  // regra de `CartaoDeSaldoDeBanco`, que este tile duplica visualmente sem
  // reaproveitar o componente (compartilhado com /painel, fora deste round).
  const rotuloSinal =
    saldo.sinal === "credor" ? "Saldo credor" : saldo.sinal === "devedor" ? "Saldo devedor" : "Saldo zerado";
  const iconeSinal = saldo.sinal === "credor" ? "▲" : saldo.sinal === "devedor" ? "▼" : "■";
  const diasParaVencer = proximoVencimentoEm
    ? Math.ceil((new Date(proximoVencimentoEm).getTime() - Date.now()) / (24 * 60 * 60 * 1000))
    : null;
  const vencimentoProximo =
    diasParaVencer !== null && diasParaVencer >= 0 && (aVencer30Minutos ?? 0) > 0;

  return (
    <Cartao
      className="rounded-suave p-[var(--espacamento-4)] shadow-flutuante-cartao"
      aria-label={contaCodigo ? `Saldo de banco de horas — conta ${contaCodigo}` : "Saldo de banco de horas"}
    >
      <div className="flex items-center gap-2 text-texto-terciario">
        <Clock3 className="h-4 w-4" aria-hidden="true" />
        <p className="estilo-rotulo">Banco de horas</p>
      </div>
      <div className="flex items-baseline gap-2">
        <span aria-hidden="true" className={cn("estilo-titulo-secao", corSinal)}>
          {iconeSinal}
        </span>
        <p className={cn("estilo-numero-destaque tabular-nums", corSinal)}>{saldo.textoComSinal}</p>
      </div>
      <p className={cn("estilo-rotulo", corSinal)}>{rotuloSinal}</p>
      <p className="estilo-legenda text-texto-desabilitado">
        {vencimentoProximo
          ? `${minutosParaHHMM(aVencer30Minutos ?? 0)} vencem em ${diasParaVencer} ${diasParaVencer === 1 ? "dia" : "dias"}`
          : contaCodigo
            ? `Conta ${contaCodigo}`
            : "Sem vencimento próximo"}
      </p>
    </Cartao>
  );
}

function ItemDeMarcacao({ marcacao }: { marcacao: Esquema<"Marcacao"> }) {
  const sentido = marcacao.sentidoInformado ? ROTULO_SENTIDO[marcacao.sentidoInformado] : undefined;
  const canal = marcacao.canal ? ROTULO_CANAL[marcacao.canal] : undefined;
  return (
    <div className="flex items-center gap-3 rounded-suave bg-fundo-superficie p-[var(--espacamento-3)] shadow-flutuante-cartao">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-grande bg-acao-sutil-fundo text-acao-sutil-texto">
        <Clock3 className="h-4 w-4" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-texto-primario">
          {sentido ?? canal ?? "Marcação"}
        </p>
        <p className="estilo-identificador text-texto-terciario">
          {marcacao.nsr !== undefined ? `NSR ${marcacao.nsr}` : "NSR pendente"}
          {canal ? ` · ${canal}` : ""}
        </p>
      </div>
      <p className="estilo-tabular text-lg font-semibold tabular-nums text-texto-primario">
        {formatarHora(marcacao.datahoraMarcacao ?? "")}
      </p>
    </div>
  );
}
