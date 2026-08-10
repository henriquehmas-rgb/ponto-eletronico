"use client";

import { Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { DialogoConfirmacao } from "@/componentes/paineis/cadastros/_shared/dialogo-confirmacao";
import { mensagemDeErroApi } from "@/componentes/paineis/cadastros/_shared/erro-amigavel";
import { DialogoImportarColaboradores } from "@/componentes/paineis/cadastros/colaboradores/dialogo-importar-colaboradores";
import {
  FormularioColaborador,
  paraCorpoDeColaborador,
  type ValoresFormularioColaborador,
} from "@/componentes/paineis/cadastros/colaboradores/formulario-colaborador";
import { type ColunaDeTabela, TabelaDeDados } from "@/componentes/dominio/tabela-de-dados";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Selo } from "@/componentes/ui/badge";
import { Botao } from "@/componentes/ui/button";
import { Dialogo, DialogoCabecalho, DialogoConteudo, DialogoTitulo } from "@/componentes/ui/dialog";
import { Entrada } from "@/componentes/ui/input";
import {
  useAtualizarColaborador,
  useColaboradores,
  useCriarColaborador,
  useExcluirColaborador,
} from "@/ganchos/use-colaboradores";
import { useEmpresas } from "@/ganchos/use-empresas";
import { mascararCpf } from "@/lib/formatacao";
import { PortaoDePermissao } from "@/lib/permissoes";
import { cn } from "@/lib/utils";
import type { Esquema } from "@/lib/api";

type Colaborador = Esquema<"Colaborador">;

const SELO_POR_STATUS: Record<string, "sucesso" | "atencao" | "erro" | "neutro" | "info"> = {
  ativo: "sucesso",
  pre_admissao: "info",
  afastado: "atencao",
  ferias: "info",
  suspenso: "atencao",
  desligado: "neutro",
};

type FiltroDeStatus = "todos" | "ativo" | "afastado";

const STATUS_POR_FILTRO: Record<FiltroDeStatus, Esquema<"Colaborador">["status"] | undefined> = {
  todos: undefined,
  ativo: "ativo",
  afastado: "afastado",
};

const CHIPS_DE_FILTRO: { id: FiltroDeStatus; rotulo: string }[] = [
  { id: "todos", rotulo: "Todos" },
  { id: "ativo", rotulo: "Ativos" },
  { id: "afastado", rotulo: "Afastados" },
];

export default function PaginaDeColaboradores() {
  const [busca, setBusca] = useState("");
  const [filtroStatus, setFiltroStatus] = useState<FiltroDeStatus>("todos");
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [itens, setItens] = useState<Colaborador[]>([]);
  const consulta = useColaboradores({
    busca: busca || undefined,
    status: STATUS_POR_FILTRO[filtroStatus],
    cursor,
  });
  const empresas = useEmpresas({ ativo: true });

  useEffect(() => {
    setCursor(undefined);
    setItens([]);
    // Reinicia a paginação acumulada sempre que o filtro de busca ou de status muda.
  }, [busca, filtroStatus]);

  useEffect(() => {
    if (!consulta.data) return;
    setItens((atual) =>
      cursor ? [...atual, ...(consulta.data.dados ?? [])] : (consulta.data.dados ?? []),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [consulta.data]);

  const [dialogoAberto, setDialogoAberto] = useState(false);
  const [editando, setEditando] = useState<Colaborador | null>(null);
  const [importarAberto, setImportarAberto] = useState(false);
  const [excluindo, setExcluindo] = useState<Colaborador | null>(null);

  const criar = useCriarColaborador();
  const atualizar = useAtualizarColaborador();
  const excluir = useExcluirColaborador();

  function salvar(valores: ValoresFormularioColaborador) {
    const corpo = paraCorpoDeColaborador(valores);
    if (editando?.id) {
      atualizar.mutate({ id: editando.id, corpo }, { onSuccess: () => setDialogoAberto(false) });
    } else {
      criar.mutate(corpo as Esquema<"ColaboradorCriar">, {
        onSuccess: () => setDialogoAberto(false),
      });
    }
  }

  const colunas: ColunaDeTabela<Colaborador>[] = [
    {
      id: "nomeCompleto",
      cabecalho: "Nome",
      renderizarCelula: (c) => {
        const nomeExibido = c.nomeSocial ?? c.nomeCompleto ?? "";
        const iniciais =
          nomeExibido
            .trim()
            .split(/\s+/)
            .filter(Boolean)
            .slice(0, 2)
            .map((parte) => parte[0]?.toUpperCase())
            .join("") || "—";
        return (
          <Link
            href={`/painel/cadastros/colaboradores/${c.id}`}
            className="flex min-w-0 items-center gap-2.5 hover:underline"
          >
            <span
              aria-hidden="true"
              className="flex size-7 shrink-0 items-center justify-center rounded-pleno bg-gradient-to-br from-acao-primaria-fundo to-acao-primaria-fundo-ativo text-[11px] font-semibold text-texto-inverso"
            >
              {iniciais}
            </span>
            <span className="truncate">{nomeExibido}</span>
          </Link>
        );
      },
      valorDeOrdenacao: (c) => c.nomeCompleto ?? "",
      ordenavel: true,
      larguraPx: 240,
    },
    {
      id: "matricula",
      cabecalho: "Matrícula",
      renderizarCelula: (c) => <span className="estilo-tabular">{c.matricula ?? "—"}</span>,
      larguraPx: 120,
    },
    {
      id: "cpf",
      cabecalho: "CPF",
      renderizarCelula: (c) => (
        <span className="estilo-tabular">{c.cpf ? mascararCpf(c.cpf) : "—"}</span>
      ),
      larguraPx: 160,
    },
    {
      id: "status",
      cabecalho: "Situação",
      renderizarCelula: (c) => (
        <Selo variant={SELO_POR_STATUS[c.status ?? ""] ?? "neutro"}>{c.status ?? "—"}</Selo>
      ),
      larguraPx: 140,
    },
    {
      id: "acoes",
      cabecalho: "Ações",
      renderizarCelula: (c) => (
        <div className="flex gap-2">
          <Botao
            variant="secundaria"
            tamanho="compacto"
            onClick={() => {
              setEditando(c);
              setDialogoAberto(true);
            }}
          >
            Editar
          </Botao>
          <PortaoDePermissao permissao="colaboradores.excluir">
            <Botao
              variant="destrutiva"
              tamanho="compacto"
              onClick={() => {
                setExcluindo(c);
              }}
            >
              Excluir
            </Botao>
          </PortaoDePermissao>
        </div>
      ),
      larguraPx: 220,
    },
  ];

  const totalCadastrado = consulta.data?.paginacao.total;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="estilo-titulo-pagina text-texto-primario">Colaboradores</h1>
          {totalCadastrado !== undefined ? (
            <p className="estilo-corpo text-texto-terciario">
              {totalCadastrado} colaborador(es) cadastrado(s)
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative">
            <Search
              aria-hidden="true"
              className="pointer-events-none absolute top-1/2 left-3.5 size-[13px] -translate-y-1/2 text-texto-terciario"
            />
            <Entrada
              placeholder="Buscar por nome, matrícula ou CPF…"
              value={busca}
              onChange={(evento) => setBusca(evento.target.value)}
              className="w-64 rounded-pleno border-transparent bg-fundo-superficie pl-9 shadow-flutuante-chip"
              aria-label="Buscar colaboradores"
            />
          </div>
          <div className="flex gap-2">
            <PortaoDePermissao permissao="colaboradores.criar">
              <Botao
                variant="secundaria"
                onClick={() => {
                  setImportarAberto(true);
                }}
              >
                Importar em lote
              </Botao>
            </PortaoDePermissao>
            <PortaoDePermissao permissao="colaboradores.criar">
              <Botao
                className="rounded-pleno"
                onClick={() => {
                  setEditando(null);
                  setDialogoAberto(true);
                }}
              >
                Novo colaborador
              </Botao>
            </PortaoDePermissao>
          </div>
        </div>
      </header>

      <div className="flex flex-wrap gap-2" role="group" aria-label="Filtrar por situação">
        {CHIPS_DE_FILTRO.map((chip) => (
          <button
            key={chip.id}
            type="button"
            aria-pressed={filtroStatus === chip.id}
            onClick={() => setFiltroStatus(chip.id)}
            className={cn(
              "estilo-legenda rounded-pleno px-3 py-1.5 font-semibold shadow-flutuante-chip transition-colors",
              filtroStatus === chip.id
                ? "bg-fundo-inverso text-texto-inverso"
                : "bg-fundo-superficie text-texto-secundario",
            )}
          >
            {chip.rotulo}
          </button>
        ))}
      </div>

      {consulta.isError ? (
        <Alerta variant="erro">
          <AlertaDescricao>{mensagemDeErroApi(consulta.error)}</AlertaDescricao>
        </Alerta>
      ) : null}

      <div className="rounded-suave bg-fundo-superficie p-[var(--espacamento-3)] shadow-flutuante-cartao">
        <TabelaDeDados
          linhas={itens}
          colunas={colunas}
          obterId={(c) => c.id ?? ""}
          carregando={consulta.isPending && itens.length === 0}
          mensagemVazia="Nenhum colaborador cadastrado."
          alturaContainerPx={480}
        />
      </div>

      {consulta.data?.paginacao.temMais ? (
        <div className="flex justify-center">
          <Botao
            variant="secundaria"
            disabled={consulta.isFetching}
            onClick={() => {
              setCursor(consulta.data.paginacao.proximoCursor);
            }}
          >
            {consulta.isFetching ? "Carregando…" : "Carregar mais"}
          </Botao>
        </div>
      ) : null}

      <Dialogo open={dialogoAberto} onOpenChange={setDialogoAberto}>
        <DialogoConteudo className="sm:max-w-2xl">
          <DialogoCabecalho>
            <DialogoTitulo>{editando ? "Editar colaborador" : "Novo colaborador"}</DialogoTitulo>
          </DialogoCabecalho>
          <FormularioColaborador
            key={editando?.id ?? "novo"}
            colaborador={editando}
            empresas={empresas.data?.dados ?? []}
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

      <DialogoImportarColaboradores
        aberto={importarAberto}
        aoMudarAberto={setImportarAberto}
        empresas={empresas.data?.dados ?? []}
      />

      <DialogoConfirmacao
        aberto={Boolean(excluindo)}
        aoMudarAberto={(aberto) => {
          if (!aberto) setExcluindo(null);
        }}
        titulo="Excluir colaborador"
        descricao={`"${excluindo?.nomeCompleto ?? ""}" será removido das listagens. O histórico é preservado para auditoria.`}
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
