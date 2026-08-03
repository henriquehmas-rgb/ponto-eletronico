"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { type ColunaDeTabela, TabelaDeDados } from "@/componentes/dominio/tabela-de-dados";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Selo } from "@/componentes/ui/badge";
import { Botao } from "@/componentes/ui/button";
import {
  Cartao,
  CartaoCabecalho,
  CartaoConteudo,
  CartaoDescricao,
  CartaoTitulo,
} from "@/componentes/ui/card";
import { Dialogo, DialogoCabecalho, DialogoConteudo, DialogoTitulo } from "@/componentes/ui/dialog";
import { Esqueleto } from "@/componentes/ui/skeleton";
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
  useEntregasWebhook,
  useExcluirWebhook,
  useReenviarEntregaWebhook,
  useWebhook,
} from "@/ganchos/use-webhooks";
import { formatarDataHora } from "@/lib/formatacao";
import { PortaoDePermissao } from "@/lib/permissoes";
import type { Esquema } from "@/lib/api";

import { DialogoConfirmacao } from "./dialogo-confirmacao";
import {
  FormularioWebhook,
  paraCorpoDeWebhook,
  type FormularioDeWebhook,
} from "./formulario-webhook";
import { mensagemDeErroApi } from "./mensagem-de-erro-api";

type WebhookEntrega = Esquema<"WebhookEntrega">;

const SELO_POR_STATUS_WEBHOOK: Record<string, "sucesso" | "atencao" | "erro" | "neutro"> = {
  ativo: "sucesso",
  suspenso: "atencao",
  desabilitado_por_falha: "erro",
};

const SELO_POR_STATUS_ENTREGA: Record<string, "sucesso" | "atencao" | "erro" | "neutro" | "info"> =
  {
    pendente: "neutro",
    enviando: "info",
    sucesso: "sucesso",
    falha: "erro",
    dlq: "erro",
    cancelada: "neutro",
  };

// Reenvio manual (`reenviarEntregaWebhook`, T13) faz sentido para entregas que
// já pararam de tentar sozinhas — inclui `dlq` (o caso central do critério de
// aceite 2) e `falha` (uma tentativa isolada que ainda não esgotou, mas o
// operador quer forçar agora). `pendente`/`enviando` já estão em curso;
// `sucesso`/`cancelada` não têm o que reenviar.
const STATUS_REENVIAVEIS = new Set<string>(["falha", "dlq"]);

const OPCOES_STATUS_ENTREGA = [
  { valor: "pendente", rotulo: "Pendente" },
  { valor: "enviando", rotulo: "Enviando" },
  { valor: "sucesso", rotulo: "Sucesso" },
  { valor: "falha", rotulo: "Falha" },
  { valor: "dlq", rotulo: "Dead letter queue" },
  { valor: "cancelada", rotulo: "Cancelada" },
];

const SEM_FILTRO = "__todas__";

interface DetalheWebhookProps {
  webhookId: string;
}

/**
 * Detalhe de um webhook: configuração + histórico de entregas com filtro por
 * status e reenvio manual (T14). Consome só as operações da tag `webhooks`
 * já publicadas por A3 (`obterWebhook`, `atualizarWebhook`, `excluirWebhook`,
 * `listarEntregasWebhook`, `reenviarEntregaWebhook`) — nenhuma lógica de
 * entrega mora aqui.
 */
export function DetalheWebhook({ webhookId }: DetalheWebhookProps) {
  const router = useRouter();
  const webhook = useWebhook(webhookId);

  const [statusFiltro, setStatusFiltro] = useState<string>(SEM_FILTRO);
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const entregas = useEntregasWebhook(webhookId, {
    cursor,
    status:
      statusFiltro === SEM_FILTRO
        ? undefined
        : (statusFiltro as NonNullable<WebhookEntrega["status"]>),
  });

  const [dialogoEdicaoAberto, setDialogoEdicaoAberto] = useState(false);
  const [excluindo, setExcluindo] = useState(false);

  const atualizar = useAtualizarWebhook();
  const excluir = useExcluirWebhook();
  const reenviar = useReenviarEntregaWebhook();
  const [entregaComErroDeReenvio, setEntregaComErroDeReenvio] = useState<string | null>(null);

  function mudarFiltro(valor: string) {
    setStatusFiltro(valor);
    setCursor(undefined);
  }

  function salvarEdicao(valores: FormularioDeWebhook) {
    const corpo = paraCorpoDeWebhook(valores) as Esquema<"WebhookAtualizar">;
    atualizar.mutate({ id: webhookId, corpo }, { onSuccess: () => setDialogoEdicaoAberto(false) });
  }

  const colunasEntregas: ColunaDeTabela<WebhookEntrega>[] = [
    { id: "evento", cabecalho: "Evento", renderizarCelula: (e) => e.evento ?? "—", larguraPx: 180 },
    {
      id: "tentativa",
      cabecalho: "Tentativa",
      renderizarCelula: (e) => e.tentativa ?? "—",
      larguraPx: 90,
    },
    {
      id: "status",
      cabecalho: "Situação",
      renderizarCelula: (e) => (
        <Selo variant={SELO_POR_STATUS_ENTREGA[e.status ?? ""] ?? "neutro"}>{e.status ?? "—"}</Selo>
      ),
      larguraPx: 130,
    },
    {
      id: "httpStatus",
      cabecalho: "HTTP",
      renderizarCelula: (e) => e.httpStatus ?? "—",
      larguraPx: 70,
    },
    {
      id: "duracaoMs",
      cabecalho: "Duração",
      renderizarCelula: (e) => (e.duracaoMs != null ? `${e.duracaoMs} ms` : "—"),
      larguraPx: 100,
    },
    {
      id: "erro",
      cabecalho: "Erro",
      renderizarCelula: (e) => <span className="truncate">{e.erro ?? "—"}</span>,
      larguraPx: 220,
    },
    {
      id: "proximaTentativaEm",
      cabecalho: "Próxima tentativa",
      renderizarCelula: (e) =>
        e.proximaTentativaEm ? formatarDataHora(e.proximaTentativaEm) : "—",
      larguraPx: 160,
    },
    {
      id: "criadoEm",
      cabecalho: "Criada em",
      renderizarCelula: (e) => (e.criadoEm ? formatarDataHora(e.criadoEm) : "—"),
      larguraPx: 160,
    },
    {
      id: "acoes",
      cabecalho: "Ações",
      renderizarCelula: (e) =>
        e.status && STATUS_REENVIAVEIS.has(e.status) ? (
          <PortaoDePermissao permissao="webhooks.executar">
            <Botao
              variant="secundaria"
              tamanho="compacto"
              disabled={reenviar.isPending}
              onClick={() => {
                setEntregaComErroDeReenvio(null);
                if (!e.id) return;
                reenviar.mutate(
                  { webhookId, entregaId: e.id },
                  { onError: (erro) => setEntregaComErroDeReenvio(mensagemDeErroApi(erro)) },
                );
              }}
            >
              Reenviar
            </Botao>
          </PortaoDePermissao>
        ) : null,
      larguraPx: 120,
    },
  ];

  if (webhook.isPending) {
    return <Esqueleto className="h-64 w-full rounded-medio" />;
  }
  if (webhook.isError || !webhook.data) {
    return (
      <div className="flex flex-col gap-4">
        <Link
          href="/painel/integracoes"
          className="estilo-corpo text-acao-sutil-texto hover:underline"
        >
          ← Voltar para webhooks
        </Link>
        <Alerta variant="erro">
          <AlertaDescricao>{mensagemDeErroApi(webhook.error)}</AlertaDescricao>
        </Alerta>
      </div>
    );
  }

  const dados = webhook.data;

  return (
    <div className="flex flex-col gap-6">
      <Link
        href="/painel/integracoes"
        className="estilo-corpo text-acao-sutil-texto hover:underline"
      >
        ← Voltar para webhooks
      </Link>

      <Cartao>
        <CartaoCabecalho>
          <CartaoTitulo>{dados.nome ?? dados.id}</CartaoTitulo>
          <CartaoDescricao>{dados.url}</CartaoDescricao>
        </CartaoCabecalho>
        <CartaoConteudo className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <Selo variant={SELO_POR_STATUS_WEBHOOK[dados.status ?? ""] ?? "neutro"}>
              {dados.status ?? "—"}
            </Selo>
            <span className="estilo-legenda text-texto-terciario">
              {dados.falhasConsecutivas ?? 0} falha(s) consecutiva(s)
            </span>
            {dados.ultimaEntregaEm ? (
              <span className="estilo-legenda text-texto-terciario">
                Última entrega: {formatarDataHora(dados.ultimaEntregaEm)}
              </span>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            {(dados.eventos ?? []).map((evento) => (
              <Selo key={evento} variant="neutro">
                {evento}
              </Selo>
            ))}
          </div>
          <div className="flex gap-2">
            <PortaoDePermissao permissao="webhooks.editar">
              <Botao
                variant="secundaria"
                tamanho="compacto"
                onClick={() => setDialogoEdicaoAberto(true)}
              >
                Editar
              </Botao>
            </PortaoDePermissao>
            <PortaoDePermissao permissao="webhooks.excluir">
              <Botao variant="destrutiva" tamanho="compacto" onClick={() => setExcluindo(true)}>
                Excluir
              </Botao>
            </PortaoDePermissao>
          </div>
        </CartaoConteudo>
      </Cartao>

      <div className="flex flex-col gap-3">
        <h2 className="estilo-titulo-secao text-texto-primario">Entregas</h2>

        <div className="flex w-56 flex-col gap-1">
          <Rotulo htmlFor="filtro-status-entrega">Situação</Rotulo>
          <Selecao value={statusFiltro} onValueChange={mudarFiltro}>
            <SelecaoGatilho id="filtro-status-entrega" className="w-full">
              <SelecaoValor />
            </SelecaoGatilho>
            <SelecaoConteudo>
              <SelecaoItem value={SEM_FILTRO}>Todas</SelecaoItem>
              {OPCOES_STATUS_ENTREGA.map((opcao) => (
                <SelecaoItem key={opcao.valor} value={opcao.valor}>
                  {opcao.rotulo}
                </SelecaoItem>
              ))}
            </SelecaoConteudo>
          </Selecao>
        </div>

        {entregas.isError ? (
          <Alerta variant="erro">
            <AlertaDescricao>{mensagemDeErroApi(entregas.error)}</AlertaDescricao>
          </Alerta>
        ) : null}
        {entregaComErroDeReenvio ? (
          <Alerta variant="erro">
            <AlertaDescricao>{entregaComErroDeReenvio}</AlertaDescricao>
          </Alerta>
        ) : null}

        <TabelaDeDados
          linhas={entregas.data?.dados ?? []}
          colunas={colunasEntregas}
          obterId={(e) => e.id ?? ""}
          carregando={entregas.isPending}
          mensagemVazia="Nenhuma entrega registrada para este filtro."
        />

        <div className="flex justify-end">
          <Botao
            type="button"
            variant="secundaria"
            disabled={!entregas.data?.paginacao?.temMais}
            onClick={() => setCursor(entregas.data?.paginacao?.proximoCursor)}
          >
            Próxima página
          </Botao>
        </div>
      </div>

      <Dialogo open={dialogoEdicaoAberto} onOpenChange={setDialogoEdicaoAberto}>
        <DialogoConteudo className="sm:max-w-2xl">
          <DialogoCabecalho>
            <DialogoTitulo>Editar webhook</DialogoTitulo>
          </DialogoCabecalho>
          <FormularioWebhook
            webhook={dados}
            salvando={atualizar.isPending}
            erro={atualizar.isError ? mensagemDeErroApi(atualizar.error) : undefined}
            aoSalvar={salvarEdicao}
            aoCancelar={() => setDialogoEdicaoAberto(false)}
          />
        </DialogoConteudo>
      </Dialogo>

      <DialogoConfirmacao
        aberto={excluindo}
        aoMudarAberto={setExcluindo}
        titulo="Excluir webhook"
        descricao={`"${dados.nome ?? dados.id ?? ""}" será removido. Entregas pendentes na fila são canceladas.`}
        rotuloConfirmar="Excluir"
        confirmando={excluir.isPending}
        erro={excluir.isError ? mensagemDeErroApi(excluir.error) : undefined}
        aoConfirmar={() => {
          excluir.mutate(webhookId, {
            onSuccess: () => router.push("/painel/integracoes"),
          });
        }}
      />
    </div>
  );
}
