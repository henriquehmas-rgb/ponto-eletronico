"use client";

import Link from "next/link";

import { type ColunaDeTabela, TabelaDeDados } from "@/componentes/dominio/tabela-de-dados";
import { Selo } from "@/componentes/ui/badge";
import { Alerta, AlertaDescricao, AlertaTitulo } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { useSolicitacoes } from "@/ganchos/use-solicitacoes";
import { useTiposSolicitacao } from "@/ganchos/use-tipos-solicitacao";
import { ehErroDaApi, type Esquema } from "@/lib/api";
import { formatarDataHora } from "@/lib/formatacao";

type StatusDeSolicitacao = NonNullable<Esquema<"Solicitacao">["status"]>;

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

/** `PONTO-INT-005` = handler ainda não implementado (F10 pendente, §2 do PCF) — nunca uma tela quebrada. */
function ehIndisponivel(erro: unknown): boolean {
  return ehErroDaApi(erro) && erro.codigo === "PONTO-INT-005";
}

export default function ListaDeSolicitacoes() {
  const solicitacoes = useSolicitacoes();
  const tipos = useTiposSolicitacao({});

  const mapaDeTipos = new Map((tipos.data?.dados ?? []).map((tipo) => [tipo.id ?? "", tipo]));

  const colunas: ColunaDeTabela<Esquema<"Solicitacao">>[] = [
    {
      id: "protocolo",
      cabecalho: "Protocolo",
      renderizarCelula: (linha) => linha.protocolo ?? "—",
    },
    {
      id: "tipo",
      cabecalho: "Tipo",
      renderizarCelula: (linha) => mapaDeTipos.get(linha.tipoSolicitacaoId ?? "")?.nome ?? "—",
    },
    {
      id: "status",
      cabecalho: "Situação",
      renderizarCelula: (linha) => {
        const status = linha.status;
        return (
          <Selo variant={status ? VARIANTE_STATUS[status] : "neutro"}>
            {status ? ROTULO_STATUS[status] : "—"}
          </Selo>
        );
      },
    },
    {
      id: "criadoEm",
      cabecalho: "Aberta em",
      renderizarCelula: (linha) => (linha.criadoEm ? formatarDataHora(linha.criadoEm) : "—"),
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="estilo-titulo-pagina text-texto-primario">Solicitações</h1>
        <Botao asChild tamanho="toque">
          <Link href="/eu/solicitacoes/nova">Nova solicitação</Link>
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
      ) : (
        <TabelaDeDados
          linhas={solicitacoes.data?.dados ?? []}
          colunas={colunas}
          obterId={(linha) => linha.id ?? linha.protocolo ?? String(Math.random())}
          mensagemVazia="Nenhuma solicitação aberta."
        />
      )}
    </div>
  );
}
