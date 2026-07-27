"use client";

import { useState } from "react";

import { mensagemDeErroApi } from "@/componentes/paineis/cadastros/_shared/erro-amigavel";
import {
  FormularioCentroCusto,
  paraCorpoDeCentroCusto,
  type ValoresFormularioCentroCusto,
} from "@/componentes/paineis/cadastros/centros-custo/formulario-centro-custo";
import { type ColunaDeTabela, TabelaDeDados } from "@/componentes/dominio/tabela-de-dados";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Selo } from "@/componentes/ui/badge";
import { Botao } from "@/componentes/ui/button";
import { Dialogo, DialogoCabecalho, DialogoConteudo, DialogoTitulo } from "@/componentes/ui/dialog";
import { Entrada } from "@/componentes/ui/input";
import {
  useAtualizarCentroCusto,
  useCentrosCusto,
  useCriarCentroCusto,
} from "@/ganchos/use-centros-custo";
import { useEmpresas } from "@/ganchos/use-empresas";
import { PortaoDePermissao } from "@/lib/permissoes";
import type { Esquema } from "@/lib/api";

type CentroCusto = Esquema<"CentroCusto">;

export default function PaginaDeCentrosCusto() {
  const [busca, setBusca] = useState("");
  const consulta = useCentrosCusto({ busca: busca || undefined, incluirExcluidos: false });
  const empresas = useEmpresas({ ativo: true });

  const [dialogoAberto, setDialogoAberto] = useState(false);
  const [editando, setEditando] = useState<CentroCusto | null>(null);

  const criar = useCriarCentroCusto();
  const atualizar = useAtualizarCentroCusto();

  function salvar(valores: ValoresFormularioCentroCusto) {
    const corpo = paraCorpoDeCentroCusto(valores);
    if (editando?.id) {
      atualizar.mutate({ id: editando.id, corpo }, { onSuccess: () => setDialogoAberto(false) });
    } else {
      criar.mutate(corpo as Esquema<"CentroCustoCriar">, {
        onSuccess: () => setDialogoAberto(false),
      });
    }
  }

  const colunas: ColunaDeTabela<CentroCusto>[] = [
    {
      id: "nome",
      cabecalho: "Nome",
      renderizarCelula: (c) => (
        <button
          type="button"
          className="text-left hover:underline"
          onClick={() => {
            setEditando(c);
            setDialogoAberto(true);
          }}
        >
          {c.nome}
        </button>
      ),
      valorDeOrdenacao: (c) => c.nome ?? "",
      ordenavel: true,
      larguraPx: 240,
    },
    { id: "codigo", cabecalho: "Código", renderizarCelula: (c) => c.codigo ?? "—", larguraPx: 120 },
    {
      id: "ativo",
      cabecalho: "Situação",
      renderizarCelula: (c) => (
        <Selo variant={c.ativo ? "sucesso" : "neutro"}>{c.ativo ? "Ativo" : "Inativo"}</Selo>
      ),
      larguraPx: 110,
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="estilo-titulo-pagina text-texto-primario">Centros de custo</h1>
        <PortaoDePermissao permissao="centros_custo.criar">
          <Botao
            onClick={() => {
              setEditando(null);
              setDialogoAberto(true);
            }}
          >
            Novo centro de custo
          </Botao>
        </PortaoDePermissao>
      </header>

      <Entrada
        placeholder="Buscar por nome ou código…"
        value={busca}
        onChange={(evento) => setBusca(evento.target.value)}
        className="max-w-sm"
        aria-label="Buscar centros de custo"
      />

      {consulta.isError ? (
        <Alerta variant="erro">
          <AlertaDescricao>{mensagemDeErroApi(consulta.error)}</AlertaDescricao>
        </Alerta>
      ) : null}

      <TabelaDeDados
        linhas={consulta.data?.dados ?? []}
        colunas={colunas}
        obterId={(c) => c.id ?? ""}
        carregando={consulta.isPending}
        mensagemVazia="Nenhum centro de custo cadastrado."
      />

      <Dialogo open={dialogoAberto} onOpenChange={setDialogoAberto}>
        <DialogoConteudo className="sm:max-w-2xl">
          <DialogoCabecalho>
            <DialogoTitulo>
              {editando ? "Editar centro de custo" : "Novo centro de custo"}
            </DialogoTitulo>
          </DialogoCabecalho>
          <FormularioCentroCusto
            key={editando?.id ?? "novo"}
            centro={editando}
            empresas={empresas.data?.dados ?? []}
            centrosDaEmpresa={consulta.data?.dados ?? []}
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
    </div>
  );
}
