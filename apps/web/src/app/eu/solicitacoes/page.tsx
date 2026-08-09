"use client";

import { CalendarDays, Clock, FileText, Plane, RefreshCw, Smartphone } from "lucide-react";
import Link from "next/link";
import type { ComponentType } from "react";

import { Alerta, AlertaDescricao, AlertaTitulo } from "@/componentes/ui/alert";
import { Selo } from "@/componentes/ui/badge";
import { Botao } from "@/componentes/ui/button";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { useSolicitacoes } from "@/ganchos/use-solicitacoes";
import { useTiposSolicitacao } from "@/ganchos/use-tipos-solicitacao";
import { ehErroDaApi, type Esquema } from "@/lib/api";
import { formatarDataHora } from "@/lib/formatacao";

type StatusDeSolicitacao = NonNullable<Esquema<"Solicitacao">["status"]>;
type CategoriaDeTipo = NonNullable<Esquema<"TipoSolicitacao">["categoria"]>;

const ROTULO_STATUS: Record<StatusDeSolicitacao, string> = {
  rascunho: "Rascunho",
  pendente: "Pendente",
  em_aprovacao: "Em aprovação",
  aprovada: "Aprovada",
  reprovada: "Reprovada",
  cancelada: "Cancelada",
  expirada: "Expirada",
};

const VARIANTE_STATUS: Record<
  StatusDeSolicitacao,
  "neutro" | "sucesso" | "atencao" | "erro" | "info"
> = {
  rascunho: "neutro",
  pendente: "info",
  em_aprovacao: "atencao",
  aprovada: "sucesso",
  reprovada: "erro",
  cancelada: "neutro",
  expirada: "neutro",
};

/** Ícone por categoria funcional do tipo — puramente decorativo, não altera nenhum dado. */
const ICONE_POR_CATEGORIA: Record<CategoriaDeTipo, ComponentType<{ className?: string }>> = {
  ajuste_ponto: Clock,
  abono: FileText,
  justificativa: FileText,
  ferias: Plane,
  folga: CalendarDays,
  compensacao: RefreshCw,
  afastamento: CalendarDays,
  troca_escala: RefreshCw,
  hora_extra: Clock,
  desbloqueio_dispositivo: Smartphone,
  outro: FileText,
};

/** `PONTO-INT-005` = handler ainda não implementado (F10 pendente, §2 do PCF) — nunca uma tela quebrada. */
function ehIndisponivel(erro: unknown): boolean {
  return ehErroDaApi(erro) && erro.codigo === "PONTO-INT-005";
}

export default function ListaDeSolicitacoes() {
  const solicitacoes = useSolicitacoes();
  const tipos = useTiposSolicitacao({});

  const mapaDeTipos = new Map((tipos.data?.dados ?? []).map((tipo) => [tipo.id ?? "", tipo]));

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="estilo-titulo-pagina text-texto-primario">Solicitações</h1>
        <Botao asChild tamanho="toque" className="rounded-grande">
          <Link href="/eu/solicitacoes/nova">
            <span aria-hidden="true">+</span> Nova
          </Link>
        </Botao>
      </header>

      {solicitacoes.isPending ? (
        <Esqueleto className="h-40 w-full" />
      ) : ehIndisponivel(solicitacoes.error) ? (
        <Alerta variant="info">
          <AlertaTitulo>Acompanhamento disponível em breve</AlertaTitulo>
          <AlertaDescricao>
            O acompanhamento de solicitações ainda está em implementação nesta versão. Você já pode
            abrir um novo pedido — ele será processado assim que o fluxo de aprovação estiver
            disponível.
          </AlertaDescricao>
        </Alerta>
      ) : solicitacoes.isError ? (
        <Alerta variant="erro">
          <AlertaTitulo>Não foi possível carregar suas solicitações</AlertaTitulo>
          <AlertaDescricao>
            {ehErroDaApi(solicitacoes.error)
              ? solicitacoes.error.problema?.title
              : "Tente novamente em instantes."}
          </AlertaDescricao>
        </Alerta>
      ) : (solicitacoes.data?.dados ?? []).length === 0 ? (
        <div className="rounded-suave border border-dashed border-borda-padrao p-6 text-center">
          <p className="estilo-corpo font-semibold text-texto-secundario">
            Nenhuma solicitação aberta
          </p>
          <p className="estilo-legenda mt-1 text-texto-terciario">
            Toque em &ldquo;Nova&rdquo; para abrir um pedido.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {(solicitacoes.data?.dados ?? []).map((solicitacao) => {
            const tipo = mapaDeTipos.get(solicitacao.tipoSolicitacaoId ?? "");
            const Icone = tipo?.categoria ? ICONE_POR_CATEGORIA[tipo.categoria] : FileText;
            const status = solicitacao.status;
            return (
              <div
                key={solicitacao.id ?? solicitacao.protocolo}
                className="flex flex-col gap-2 rounded-suave bg-fundo-superficie p-4 shadow-flutuante-cartao"
              >
                <div className="flex items-center gap-3">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-medio bg-acao-sutil-fundo text-acao-sutil-texto">
                    <Icone className="size-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="estilo-corpo truncate font-semibold text-texto-primario">
                      {tipo?.nome ?? "Solicitação"}
                    </p>
                    <p className="estilo-legenda text-texto-terciario">
                      {solicitacao.criadoEm ? formatarDataHora(solicitacao.criadoEm) : "—"}
                    </p>
                  </div>
                  <Selo variant={status ? VARIANTE_STATUS[status] : "neutro"}>
                    {status ? ROTULO_STATUS[status] : "—"}
                  </Selo>
                </div>
                {solicitacao.descricao ? (
                  <p className="estilo-legenda leading-relaxed text-texto-secundario">
                    {solicitacao.descricao}
                  </p>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
