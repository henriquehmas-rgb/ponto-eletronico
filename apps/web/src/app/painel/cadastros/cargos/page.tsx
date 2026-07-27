"use client";

import { useState } from "react";

import { mensagemDeErroApi } from "@/componentes/paineis/cadastros/_shared/erro-amigavel";
import {
  FormularioCargo,
  paraCorpoDeCargo,
  type ValoresFormularioCargo,
} from "@/componentes/paineis/cadastros/cargos/formulario-cargo";
import { type ColunaDeTabela, TabelaDeDados } from "@/componentes/dominio/tabela-de-dados";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Selo } from "@/componentes/ui/badge";
import { Botao } from "@/componentes/ui/button";
import { Dialogo, DialogoCabecalho, DialogoConteudo, DialogoTitulo } from "@/componentes/ui/dialog";
import { Entrada } from "@/componentes/ui/input";
import { useAtualizarCargo, useCargos, useCriarCargo } from "@/ganchos/use-cargos";
import { useEmpresas } from "@/ganchos/use-empresas";
import { PortaoDePermissao } from "@/lib/permissoes";
import type { Esquema } from "@/lib/api";

type Cargo = Esquema<"Cargo">;

export default function PaginaDeCargos() {
  const [busca, setBusca] = useState("");
  const consulta = useCargos({ busca: busca || undefined, incluirExcluidos: false });
  const empresas = useEmpresas({ ativo: true });

  const [dialogoAberto, setDialogoAberto] = useState(false);
  const [editando, setEditando] = useState<Cargo | null>(null);

  const criar = useCriarCargo();
  const atualizar = useAtualizarCargo();

  function salvar(valores: ValoresFormularioCargo) {
    const corpo = paraCorpoDeCargo(valores);
    if (editando?.id) {
      atualizar.mutate({ id: editando.id, corpo }, { onSuccess: () => setDialogoAberto(false) });
    } else {
      criar.mutate(corpo as Esquema<"CargoCriar">, { onSuccess: () => setDialogoAberto(false) });
    }
  }

  const colunas: ColunaDeTabela<Cargo>[] = [
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
      larguraPx: 220,
    },
    { id: "codigo", cabecalho: "Código", renderizarCelula: (c) => c.codigo ?? "—", larguraPx: 100 },
    { id: "cbo", cabecalho: "CBO", renderizarCelula: (c) => c.cbo ?? "—", larguraPx: 100 },
    { id: "nivel", cabecalho: "Nível", renderizarCelula: (c) => c.nivel ?? "—", larguraPx: 130 },
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
        <h1 className="estilo-titulo-pagina text-texto-primario">Cargos</h1>
        <PortaoDePermissao permissao="cargos.criar">
          <Botao
            onClick={() => {
              setEditando(null);
              setDialogoAberto(true);
            }}
          >
            Novo cargo
          </Botao>
        </PortaoDePermissao>
      </header>

      <Entrada
        placeholder="Buscar por nome ou código…"
        value={busca}
        onChange={(evento) => setBusca(evento.target.value)}
        className="max-w-sm"
        aria-label="Buscar cargos"
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
        mensagemVazia="Nenhum cargo cadastrado."
      />

      <Dialogo open={dialogoAberto} onOpenChange={setDialogoAberto}>
        <DialogoConteudo className="sm:max-w-2xl">
          <DialogoCabecalho>
            <DialogoTitulo>{editando ? "Editar cargo" : "Novo cargo"}</DialogoTitulo>
          </DialogoCabecalho>
          <FormularioCargo
            key={editando?.id ?? "novo"}
            cargo={editando}
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
    </div>
  );
}
