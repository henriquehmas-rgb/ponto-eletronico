"use client";

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

export default function PaginaDeColaboradores() {
  const [busca, setBusca] = useState("");
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [itens, setItens] = useState<Colaborador[]>([]);
  const consulta = useColaboradores({ busca: busca || undefined, cursor });
  const empresas = useEmpresas({ ativo: true });

  useEffect(() => {
    setCursor(undefined);
    setItens([]);
    // Reinicia a paginação acumulada sempre que o filtro de busca muda.
  }, [busca]);

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
      renderizarCelula: (c) => (
        <Link href={`/painel/cadastros/colaboradores/${c.id}`} className="hover:underline">
          {c.nomeSocial ?? c.nomeCompleto}
        </Link>
      ),
      valorDeOrdenacao: (c) => c.nomeCompleto ?? "",
      ordenavel: true,
      larguraPx: 240,
    },
    {
      id: "matricula",
      cabecalho: "Matrícula",
      renderizarCelula: (c) => c.matricula ?? "—",
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

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="estilo-titulo-pagina text-texto-primario">Colaboradores</h1>
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
              onClick={() => {
                setEditando(null);
                setDialogoAberto(true);
              }}
            >
              Novo colaborador
            </Botao>
          </PortaoDePermissao>
        </div>
      </header>

      <Entrada
        placeholder="Buscar por nome, matrícula ou CPF…"
        value={busca}
        onChange={(evento) => setBusca(evento.target.value)}
        className="max-w-sm"
        aria-label="Buscar colaboradores"
      />

      {consulta.isError ? (
        <Alerta variant="erro">
          <AlertaDescricao>{mensagemDeErroApi(consulta.error)}</AlertaDescricao>
        </Alerta>
      ) : null}

      <TabelaDeDados
        linhas={itens}
        colunas={colunas}
        obterId={(c) => c.id ?? ""}
        carregando={consulta.isPending && itens.length === 0}
        mensagemVazia="Nenhum colaborador cadastrado."
        alturaContainerPx={480}
      />

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
