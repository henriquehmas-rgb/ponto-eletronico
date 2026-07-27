"use client";

import { useState } from "react";

import { DialogoConfirmacao } from "@/componentes/paineis/cadastros/_shared/dialogo-confirmacao";
import { mensagemDeErroApi } from "@/componentes/paineis/cadastros/_shared/erro-amigavel";
import {
  FormularioDepartamento,
  paraCorpoDeDepartamento,
  type ValoresFormularioDepartamento,
} from "@/componentes/paineis/cadastros/departamentos/formulario-departamento";
import { type ColunaDeTabela, TabelaDeDados } from "@/componentes/dominio/tabela-de-dados";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Selo } from "@/componentes/ui/badge";
import { Botao } from "@/componentes/ui/button";
import { Dialogo, DialogoCabecalho, DialogoConteudo, DialogoTitulo } from "@/componentes/ui/dialog";
import { Entrada } from "@/componentes/ui/input";
import { useColaboradores } from "@/ganchos/use-colaboradores";
import {
  useAtualizarDepartamento,
  useCriarDepartamento,
  useDepartamentos,
  useExcluirDepartamento,
} from "@/ganchos/use-departamentos";
import { useEmpresas } from "@/ganchos/use-empresas";
import { PortaoDePermissao } from "@/lib/permissoes";
import type { Esquema } from "@/lib/api";

type Departamento = Esquema<"Departamento">;

export default function PaginaDeDepartamentos() {
  const [busca, setBusca] = useState("");
  const consulta = useDepartamentos({ busca: busca || undefined, incluirExcluidos: false });
  const empresas = useEmpresas({ ativo: true });
  const colaboradores = useColaboradores({ limite: 200 });

  const [dialogoAberto, setDialogoAberto] = useState(false);
  const [editando, setEditando] = useState<Departamento | null>(null);
  const [excluindo, setExcluindo] = useState<Departamento | null>(null);

  const criar = useCriarDepartamento();
  const atualizar = useAtualizarDepartamento();
  const excluir = useExcluirDepartamento();

  function salvar(valores: ValoresFormularioDepartamento) {
    const corpo = paraCorpoDeDepartamento(valores);
    if (editando?.id) {
      atualizar.mutate({ id: editando.id, corpo }, { onSuccess: () => setDialogoAberto(false) });
    } else {
      criar.mutate(corpo as Esquema<"DepartamentoCriar">, {
        onSuccess: () => setDialogoAberto(false),
      });
    }
  }

  const colunas: ColunaDeTabela<Departamento>[] = [
    {
      id: "nome",
      cabecalho: "Nome",
      renderizarCelula: (d) => (
        <button
          type="button"
          className="text-left hover:underline"
          onClick={() => {
            setEditando(d);
            setDialogoAberto(true);
          }}
        >
          {d.nome}
        </button>
      ),
      valorDeOrdenacao: (d) => d.nome ?? "",
      ordenavel: true,
      larguraPx: 240,
    },
    { id: "codigo", cabecalho: "Código", renderizarCelula: (d) => d.codigo ?? "—", larguraPx: 120 },
    {
      id: "ativo",
      cabecalho: "Situação",
      renderizarCelula: (d) => (
        <Selo variant={d.ativo ? "sucesso" : "neutro"}>{d.ativo ? "Ativo" : "Inativo"}</Selo>
      ),
      larguraPx: 110,
    },
    {
      id: "acoes",
      cabecalho: "Ações",
      renderizarCelula: (d) => (
        <PortaoDePermissao permissao="departamentos.excluir">
          <Botao variant="destrutiva" tamanho="compacto" onClick={() => setExcluindo(d)}>
            Excluir
          </Botao>
        </PortaoDePermissao>
      ),
      larguraPx: 120,
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="estilo-titulo-pagina text-texto-primario">Departamentos</h1>
        <PortaoDePermissao permissao="departamentos.criar">
          <Botao
            onClick={() => {
              setEditando(null);
              setDialogoAberto(true);
            }}
          >
            Novo departamento
          </Botao>
        </PortaoDePermissao>
      </header>

      <Entrada
        placeholder="Buscar por nome ou código…"
        value={busca}
        onChange={(evento) => setBusca(evento.target.value)}
        className="max-w-sm"
        aria-label="Buscar departamentos"
      />

      {consulta.isError ? (
        <Alerta variant="erro">
          <AlertaDescricao>{mensagemDeErroApi(consulta.error)}</AlertaDescricao>
        </Alerta>
      ) : null}

      <TabelaDeDados
        linhas={consulta.data?.dados ?? []}
        colunas={colunas}
        obterId={(d) => d.id ?? ""}
        carregando={consulta.isPending}
        mensagemVazia="Nenhum departamento cadastrado."
      />

      <Dialogo open={dialogoAberto} onOpenChange={setDialogoAberto}>
        <DialogoConteudo className="sm:max-w-2xl">
          <DialogoCabecalho>
            <DialogoTitulo>{editando ? "Editar departamento" : "Novo departamento"}</DialogoTitulo>
          </DialogoCabecalho>
          <FormularioDepartamento
            key={editando?.id ?? "novo"}
            departamento={editando}
            empresas={empresas.data?.dados ?? []}
            departamentosDaEmpresa={consulta.data?.dados ?? []}
            colaboradores={colaboradores.data?.dados ?? []}
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

      <DialogoConfirmacao
        aberto={Boolean(excluindo)}
        aoMudarAberto={(aberto) => {
          if (!aberto) setExcluindo(null);
        }}
        titulo="Excluir departamento"
        descricao={`"${excluindo?.nome ?? ""}" será removido das listagens. O histórico é preservado para auditoria.`}
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
