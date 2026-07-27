"use client";

import { useState } from "react";

import { mensagemDeErroApi } from "@/componentes/paineis/cadastros/_shared/erro-amigavel";
import {
  FormularioEquipe,
  paraCorpoDeEquipe,
  type ValoresFormularioEquipe,
} from "@/componentes/paineis/cadastros/equipes/formulario-equipe";
import { SecaoMembrosEquipe } from "@/componentes/paineis/cadastros/equipes/secao-membros-equipe";
import { type ColunaDeTabela, TabelaDeDados } from "@/componentes/dominio/tabela-de-dados";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Selo } from "@/componentes/ui/badge";
import { Botao } from "@/componentes/ui/button";
import { Abas, AbaGatilho, ConteudoDaAba, ListaDeAbas } from "@/componentes/ui/tabs";
import { Dialogo, DialogoCabecalho, DialogoConteudo, DialogoTitulo } from "@/componentes/ui/dialog";
import { Entrada } from "@/componentes/ui/input";
import { useColaboradores } from "@/ganchos/use-colaboradores";
import { useDepartamentos } from "@/ganchos/use-departamentos";
import { useAtualizarEquipe, useCriarEquipe, useEquipes } from "@/ganchos/use-equipes";
import { useEmpresas } from "@/ganchos/use-empresas";
import { useUnidades } from "@/ganchos/use-unidades";
import { PortaoDePermissao } from "@/lib/permissoes";
import type { Esquema } from "@/lib/api";

type Equipe = Esquema<"Equipe">;

export default function PaginaDeEquipes() {
  const [busca, setBusca] = useState("");
  const consulta = useEquipes({ busca: busca || undefined, incluirExcluidos: false });
  const empresas = useEmpresas({ ativo: true });
  const unidades = useUnidades({ ativo: true });
  const departamentos = useDepartamentos({ ativo: true });
  const colaboradores = useColaboradores({ limite: 200 });

  const [dialogoAberto, setDialogoAberto] = useState(false);
  const [editando, setEditando] = useState<Equipe | null>(null);

  const criar = useCriarEquipe();
  const atualizar = useAtualizarEquipe();

  function abrirEdicao(equipe: Equipe) {
    setEditando(equipe);
    setDialogoAberto(true);
  }

  function salvar(valores: ValoresFormularioEquipe) {
    const corpo = paraCorpoDeEquipe(valores);
    if (editando?.id) {
      atualizar.mutate({ id: editando.id, corpo }, { onSuccess: (dados) => setEditando(dados) });
    } else {
      criar.mutate(corpo as Esquema<"EquipeCriar">, { onSuccess: (dados) => setEditando(dados) });
    }
  }

  const colunas: ColunaDeTabela<Equipe>[] = [
    {
      id: "nome",
      cabecalho: "Nome",
      renderizarCelula: (e) => (
        <button type="button" className="text-left hover:underline" onClick={() => abrirEdicao(e)}>
          {e.nome}
        </button>
      ),
      valorDeOrdenacao: (e) => e.nome ?? "",
      ordenavel: true,
      larguraPx: 220,
    },
    { id: "codigo", cabecalho: "Código", renderizarCelula: (e) => e.codigo ?? "—", larguraPx: 100 },
    {
      id: "cor",
      cabecalho: "Cor",
      renderizarCelula: (e) => (
        <span
          className="inline-block size-4 rounded-pleno border border-borda-sutil"
          style={{ backgroundColor: e.cor ?? "transparent" }}
          aria-hidden="true"
        />
      ),
      larguraPx: 60,
    },
    {
      id: "ativo",
      cabecalho: "Situação",
      renderizarCelula: (e) => (
        <Selo variant={e.ativo ? "sucesso" : "neutro"}>{e.ativo ? "Ativa" : "Inativa"}</Selo>
      ),
      larguraPx: 110,
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="estilo-titulo-pagina text-texto-primario">Equipes</h1>
        <PortaoDePermissao permissao="equipes.criar">
          <Botao
            onClick={() => {
              setEditando(null);
              setDialogoAberto(true);
            }}
          >
            Nova equipe
          </Botao>
        </PortaoDePermissao>
      </header>

      <Entrada
        placeholder="Buscar por nome ou código…"
        value={busca}
        onChange={(evento) => setBusca(evento.target.value)}
        className="max-w-sm"
        aria-label="Buscar equipes"
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
        mensagemVazia="Nenhuma equipe cadastrada."
      />

      <Dialogo open={dialogoAberto} onOpenChange={setDialogoAberto}>
        <DialogoConteudo className="sm:max-w-2xl">
          <DialogoCabecalho>
            <DialogoTitulo>
              {editando ? `Editar equipe — ${editando.nome}` : "Nova equipe"}
            </DialogoTitulo>
          </DialogoCabecalho>
          <Abas defaultValue="dados">
            <ListaDeAbas>
              <AbaGatilho value="dados">Dados</AbaGatilho>
              <AbaGatilho value="membros" disabled={!editando?.id}>
                Membros
              </AbaGatilho>
            </ListaDeAbas>
            <ConteudoDaAba value="dados">
              <FormularioEquipe
                key={editando?.id ?? "novo"}
                equipe={editando}
                empresas={empresas.data?.dados ?? []}
                unidades={unidades.data?.dados ?? []}
                departamentos={departamentos.data?.dados ?? []}
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
            </ConteudoDaAba>
            <ConteudoDaAba value="membros">
              {editando?.id ? (
                <SecaoMembrosEquipe
                  equipeId={editando.id}
                  colaboradores={colaboradores.data?.dados ?? []}
                />
              ) : (
                <p className="estilo-corpo text-texto-secundario">
                  Salve a equipe primeiro para adicionar membros.
                </p>
              )}
            </ConteudoDaAba>
          </Abas>
        </DialogoConteudo>
      </Dialogo>
    </div>
  );
}
