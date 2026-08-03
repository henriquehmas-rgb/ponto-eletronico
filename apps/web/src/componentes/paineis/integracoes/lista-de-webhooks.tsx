"use client";

import Link from "next/link";
import { useState } from "react";

import { type ColunaDeTabela, TabelaDeDados } from "@/componentes/dominio/tabela-de-dados";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Selo } from "@/componentes/ui/badge";
import { Botao } from "@/componentes/ui/button";
import { Dialogo, DialogoCabecalho, DialogoConteudo, DialogoTitulo } from "@/componentes/ui/dialog";
import { Rotulo } from "@/componentes/ui/label";
import {
  Selecao,
  SelecaoConteudo,
  SelecaoGatilho,
  SelecaoItem,
  SelecaoValor,
} from "@/componentes/ui/select";
import {
  useAtualizarWebhook,
  useCriarWebhook,
  useExcluirWebhook,
  useWebhooks,
} from "@/ganchos/use-webhooks";
import { formatarDataHora } from "@/lib/formatacao";
import { PortaoDePermissao } from "@/lib/permissoes";
import type { Esquema } from "@/lib/api";

import { DialogoConfirmacao } from "./dialogo-confirmacao";
import { DialogoSegredoWebhook } from "./dialogo-segredo-webhook";
import {
  FormularioWebhook,
  paraCorpoDeWebhook,
  type FormularioDeWebhook,
} from "./formulario-webhook";
import { mensagemDeErroApi } from "./mensagem-de-erro-api";

type Webhook = Esquema<"Webhook">;

const SELO_POR_STATUS: Record<string, "sucesso" | "atencao" | "erro" | "neutro"> = {
  ativo: "sucesso",
  suspenso: "atencao",
  desabilitado_por_falha: "erro",
};

const OPCOES_STATUS_FILTRO = [
  { valor: "ativo", rotulo: "Ativo" },
  { valor: "suspenso", rotulo: "Suspenso" },
  { valor: "desabilitado_por_falha", rotulo: "Desabilitado por falha" },
];

const SEM_FILTRO = "__todos__";

/**
 * CRUD de webhooks (T14) — mesmo padrão visual das demais telas de `painel`
 * (F9a): tabela virtualizada (`TabelaDeDados`), diálogo de formulário,
 * confirmação de exclusão. `webhooks.criar`/`webhooks.editar`/
 * `webhooks.excluir`/`webhooks.ler` são os `x-permissao` exatos declarados
 * pelas operações correspondentes em `packages/contracts/openapi.yaml`
 * (tag `webhooks`, A3).
 */
export function ListaDeWebhooks() {
  const [statusFiltro, setStatusFiltro] = useState<string>(SEM_FILTRO);

  const consulta = useWebhooks(
    statusFiltro === SEM_FILTRO ? {} : { status: statusFiltro as NonNullable<Webhook["status"]> },
  );

  const [dialogoAberto, setDialogoAberto] = useState(false);
  const [editando, setEditando] = useState<Webhook | null>(null);
  const [excluindo, setExcluindo] = useState<Webhook | null>(null);
  const [webhookCriado, setWebhookCriado] = useState<Esquema<"WebhookCriado"> | null>(null);

  const criar = useCriarWebhook();
  const atualizar = useAtualizarWebhook();
  const excluir = useExcluirWebhook();

  function salvar(valores: FormularioDeWebhook) {
    const corpo = paraCorpoDeWebhook(valores);
    if (editando?.id) {
      atualizar.mutate(
        { id: editando.id, corpo: corpo as Esquema<"WebhookAtualizar"> },
        { onSuccess: () => setDialogoAberto(false) },
      );
    } else {
      criar.mutate(corpo as Esquema<"WebhookCriar">, {
        onSuccess: (criado) => {
          setDialogoAberto(false);
          setWebhookCriado(criado);
        },
      });
    }
  }

  const colunas: ColunaDeTabela<Webhook>[] = [
    {
      id: "nome",
      cabecalho: "Webhook",
      renderizarCelula: (w) => (
        <Link
          href={`/painel/integracoes/${w.id}`}
          className="text-left text-acao-sutil-texto hover:underline"
        >
          {w.nome ?? w.id}
        </Link>
      ),
      larguraPx: 200,
    },
    {
      id: "url",
      cabecalho: "Destino",
      renderizarCelula: (w) => <span className="truncate">{w.url ?? "—"}</span>,
      larguraPx: 260,
    },
    {
      id: "eventos",
      cabecalho: "Eventos",
      renderizarCelula: (w) => `${w.eventos?.length ?? 0} assinado(s)`,
      larguraPx: 120,
    },
    {
      id: "status",
      cabecalho: "Situação",
      renderizarCelula: (w) => (
        <Selo variant={SELO_POR_STATUS[w.status ?? ""] ?? "neutro"}>{w.status ?? "—"}</Selo>
      ),
      larguraPx: 140,
    },
    {
      id: "falhasConsecutivas",
      cabecalho: "Falhas",
      renderizarCelula: (w) => w.falhasConsecutivas ?? 0,
      larguraPx: 80,
    },
    {
      id: "ultimaEntregaEm",
      cabecalho: "Última entrega",
      renderizarCelula: (w) => (w.ultimaEntregaEm ? formatarDataHora(w.ultimaEntregaEm) : "—"),
      larguraPx: 160,
    },
    {
      id: "acoes",
      cabecalho: "Ações",
      renderizarCelula: (w) => (
        <div className="flex gap-2">
          <PortaoDePermissao permissao="webhooks.editar">
            <Botao
              variant="secundaria"
              tamanho="compacto"
              onClick={() => {
                setEditando(w);
                setDialogoAberto(true);
              }}
            >
              Editar
            </Botao>
          </PortaoDePermissao>
          <PortaoDePermissao permissao="webhooks.excluir">
            <Botao variant="destrutiva" tamanho="compacto" onClick={() => setExcluindo(w)}>
              Excluir
            </Botao>
          </PortaoDePermissao>
        </div>
      ),
      larguraPx: 180,
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="estilo-titulo-pagina text-texto-primario">Integrações — Webhooks</h1>
        <PortaoDePermissao permissao="webhooks.criar">
          <Botao
            onClick={() => {
              setEditando(null);
              setDialogoAberto(true);
            }}
          >
            Novo webhook
          </Botao>
        </PortaoDePermissao>
      </header>

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex w-52 flex-col gap-1">
          <Rotulo htmlFor="filtro-status-webhook">Situação</Rotulo>
          <Selecao value={statusFiltro} onValueChange={setStatusFiltro}>
            <SelecaoGatilho id="filtro-status-webhook" className="w-full">
              <SelecaoValor />
            </SelecaoGatilho>
            <SelecaoConteudo>
              <SelecaoItem value={SEM_FILTRO}>Todas</SelecaoItem>
              {OPCOES_STATUS_FILTRO.map((opcao) => (
                <SelecaoItem key={opcao.valor} value={opcao.valor}>
                  {opcao.rotulo}
                </SelecaoItem>
              ))}
            </SelecaoConteudo>
          </Selecao>
        </div>
      </div>

      {consulta.isError ? (
        <Alerta variant="erro">
          <AlertaDescricao>{mensagemDeErroApi(consulta.error)}</AlertaDescricao>
        </Alerta>
      ) : null}

      <TabelaDeDados
        linhas={consulta.data?.dados ?? []}
        colunas={colunas}
        obterId={(w) => w.id ?? ""}
        carregando={consulta.isPending}
        mensagemVazia="Nenhum webhook cadastrado."
      />

      <Dialogo open={dialogoAberto} onOpenChange={setDialogoAberto}>
        <DialogoConteudo className="sm:max-w-2xl">
          <DialogoCabecalho>
            <DialogoTitulo>{editando ? "Editar webhook" : "Novo webhook"}</DialogoTitulo>
          </DialogoCabecalho>
          <FormularioWebhook
            key={editando?.id ?? "novo"}
            webhook={editando}
            salvando={criar.isPending || atualizar.isPending}
            erro={
              criar.isError
                ? mensagemDeErroApi(criar.error)
                : atualizar.isError
                  ? mensagemDeErroApi(atualizar.error)
                  : undefined
            }
            aoSalvar={salvar}
            aoCancelar={() => setDialogoAberto(false)}
          />
        </DialogoConteudo>
      </Dialogo>

      <DialogoSegredoWebhook
        webhookCriado={webhookCriado}
        aoFechar={() => setWebhookCriado(null)}
      />

      <DialogoConfirmacao
        aberto={Boolean(excluindo)}
        aoMudarAberto={(aberto) => {
          if (!aberto) setExcluindo(null);
        }}
        titulo="Excluir webhook"
        descricao={`"${excluindo?.nome ?? excluindo?.id ?? ""}" será removido. Entregas pendentes na fila são canceladas.`}
        rotuloConfirmar="Excluir"
        confirmando={excluir.isPending}
        erro={excluir.isError ? mensagemDeErroApi(excluir.error) : undefined}
        aoConfirmar={() => {
          if (!excluindo?.id) return;
          excluir.mutate(excluindo.id, { onSuccess: () => setExcluindo(null) });
        }}
      />
    </div>
  );
}
