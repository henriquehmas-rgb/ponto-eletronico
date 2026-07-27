"use client";

import { useState } from "react";

import {
  FormularioEmpresa,
  paraCorpoDeEmpresa,
  type ValoresFormularioEmpresa,
} from "@/componentes/paineis/cadastros/empresas/formulario-empresa";
import { mensagemDeErroApi } from "@/componentes/paineis/cadastros/_shared/erro-amigavel";
import { DialogoConfirmacao } from "@/componentes/paineis/cadastros/_shared/dialogo-confirmacao";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import { Dialogo, DialogoCabecalho, DialogoConteudo, DialogoTitulo } from "@/componentes/ui/dialog";
import { Entrada } from "@/componentes/ui/input";
import { Selo } from "@/componentes/ui/badge";
import { type ColunaDeTabela, TabelaDeDados } from "@/componentes/dominio/tabela-de-dados";
import { PortaoDePermissao } from "@/lib/permissoes";
import {
  useAtualizarEmpresa,
  useCriarEmpresa,
  useEmpresas,
  useExcluirEmpresa,
} from "@/ganchos/use-empresas";
import { mascararCnpj } from "@/lib/formatacao";
import type { Esquema } from "@/lib/api";

type Empresa = Esquema<"Empresa">;

export default function PaginaDeEmpresas() {
  const [busca, setBusca] = useState("");
  const consulta = useEmpresas({ busca: busca || undefined, incluirExcluidos: false });
  const matrizes = useEmpresas({ tipo: "matriz" });

  const [dialogoAberto, setDialogoAberto] = useState(false);
  const [empresaEditando, setEmpresaEditando] = useState<Empresa | null>(null);
  const [empresaExcluindo, setEmpresaExcluindo] = useState<Empresa | null>(null);

  const criar = useCriarEmpresa();
  const atualizar = useAtualizarEmpresa();
  const excluir = useExcluirEmpresa();

  function abrirNovo() {
    setEmpresaEditando(null);
    setDialogoAberto(true);
  }

  function abrirEdicao(empresa: Empresa) {
    setEmpresaEditando(empresa);
    setDialogoAberto(true);
  }

  function salvar(valores: ValoresFormularioEmpresa) {
    const corpo = paraCorpoDeEmpresa(valores);
    if (empresaEditando?.id) {
      atualizar.mutate(
        { id: empresaEditando.id, corpo },
        { onSuccess: () => setDialogoAberto(false) },
      );
    } else {
      criar.mutate(corpo as Esquema<"EmpresaCriar">, { onSuccess: () => setDialogoAberto(false) });
    }
  }

  const colunas: ColunaDeTabela<Empresa>[] = [
    {
      id: "razaoSocial",
      cabecalho: "Razão social",
      renderizarCelula: (e) => (
        <button
          type="button"
          className="text-left hover:underline"
          onClick={() => {
            abrirEdicao(e);
          }}
        >
          {e.razaoSocial}
        </button>
      ),
      valorDeOrdenacao: (e) => e.razaoSocial ?? "",
      ordenavel: true,
      larguraPx: 260,
    },
    {
      id: "cnpj",
      cabecalho: "CNPJ",
      renderizarCelula: (e) => (
        <span className="estilo-tabular">{e.cnpj ? mascararCnpj(e.cnpj) : "—"}</span>
      ),
      larguraPx: 180,
    },
    {
      id: "tipo",
      cabecalho: "Tipo",
      renderizarCelula: (e) => (
        <Selo variant={e.tipo === "matriz" ? "info" : "neutro"}>
          {e.tipo === "matriz" ? "Matriz" : "Filial"}
        </Selo>
      ),
      larguraPx: 100,
    },
    {
      id: "municipio",
      cabecalho: "Município/UF",
      renderizarCelula: (e) => (e.municipio ? `${e.municipio}/${e.uf ?? ""}` : "—"),
      larguraPx: 160,
    },
    {
      id: "ativo",
      cabecalho: "Situação",
      renderizarCelula: (e) => (
        <Selo variant={e.ativo ? "sucesso" : "neutro"}>{e.ativo ? "Ativa" : "Inativa"}</Selo>
      ),
      larguraPx: 100,
    },
    {
      id: "acoes",
      cabecalho: "Ações",
      renderizarCelula: (e) => (
        <PortaoDePermissao permissao="empresas.excluir">
          <Botao
            variant="destrutiva"
            tamanho="compacto"
            onClick={() => {
              setEmpresaExcluindo(e);
            }}
          >
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
        <h1 className="estilo-titulo-pagina text-texto-primario">Empresas</h1>
        <PortaoDePermissao permissao="empresas.criar">
          <Botao onClick={abrirNovo}>Nova empresa</Botao>
        </PortaoDePermissao>
      </header>

      <Entrada
        placeholder="Buscar por razão social, nome fantasia ou CNPJ…"
        value={busca}
        onChange={(evento) => {
          setBusca(evento.target.value);
        }}
        className="max-w-sm"
        aria-label="Buscar empresas"
      />

      {consulta.isError ? (
        <Alerta variant="erro">
          <AlertaDescricao>{mensagemDeErroApi(consulta.error)}</AlertaDescricao>
        </Alerta>
      ) : null}

      <TabelaDeDados
        linhas={consulta.data?.dados ?? []}
        colunas={colunas}
        obterId={(e) => e.id ?? ""}
        carregando={consulta.isPending}
        mensagemVazia="Nenhuma empresa cadastrada."
      />

      <Dialogo open={dialogoAberto} onOpenChange={setDialogoAberto}>
        <DialogoConteudo className="sm:max-w-2xl">
          <DialogoCabecalho>
            <DialogoTitulo>{empresaEditando ? "Editar empresa" : "Nova empresa"}</DialogoTitulo>
          </DialogoCabecalho>
          <FormularioEmpresa
            key={empresaEditando?.id ?? "novo"}
            empresa={empresaEditando}
            matrizes={matrizes.data?.dados ?? []}
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
        aberto={Boolean(empresaExcluindo)}
        aoMudarAberto={(aberto) => {
          if (!aberto) setEmpresaExcluindo(null);
        }}
        titulo="Excluir empresa"
        descricao={`"${empresaExcluindo?.razaoSocial ?? ""}" será removida das listagens. O histórico é preservado para auditoria.`}
        rotuloConfirmar="Excluir"
        confirmando={excluir.isPending}
        erro={excluir.isError ? mensagemDeErroApi(excluir.error) : undefined}
        aoConfirmar={() => {
          if (!empresaExcluindo?.id) return;
          excluir.mutate(empresaExcluindo.id, { onSuccess: () => setEmpresaExcluindo(null) });
        }}
      />
    </div>
  );
}
