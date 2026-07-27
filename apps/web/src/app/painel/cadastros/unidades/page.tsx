"use client";

import { useState } from "react";

import { DialogoConfirmacao } from "@/componentes/paineis/cadastros/_shared/dialogo-confirmacao";
import { mensagemDeErroApi } from "@/componentes/paineis/cadastros/_shared/erro-amigavel";
import {
  FormularioUnidade,
  paraCorpoDeUnidade,
  type ValoresFormularioUnidade,
} from "@/componentes/paineis/cadastros/unidades/formulario-unidade";
import { SecaoGeocerca } from "@/componentes/paineis/cadastros/unidades/secao-geocerca";
import { SecaoRedesPermitidas } from "@/componentes/paineis/cadastros/unidades/secao-redes-permitidas";
import { type ColunaDeTabela, TabelaDeDados } from "@/componentes/dominio/tabela-de-dados";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import { Abas, AbaGatilho, ConteudoDaAba, ListaDeAbas } from "@/componentes/ui/tabs";
import { Dialogo, DialogoCabecalho, DialogoConteudo, DialogoTitulo } from "@/componentes/ui/dialog";
import { Entrada } from "@/componentes/ui/input";
import { Selo } from "@/componentes/ui/badge";
import { useEmpresas } from "@/ganchos/use-empresas";
import {
  useAtualizarUnidade,
  useCriarUnidade,
  useExcluirUnidade,
  useUnidades,
} from "@/ganchos/use-unidades";
import { PortaoDePermissao } from "@/lib/permissoes";
import type { Esquema } from "@/lib/api";

type Unidade = Esquema<"Unidade">;

export default function PaginaDeUnidades() {
  const [busca, setBusca] = useState("");
  const consulta = useUnidades({ busca: busca || undefined, incluirExcluidos: false });
  const empresas = useEmpresas({ ativo: true });

  const [dialogoAberto, setDialogoAberto] = useState(false);
  const [unidadeEditando, setUnidadeEditando] = useState<Unidade | null>(null);
  const [unidadeExcluindo, setUnidadeExcluindo] = useState<Unidade | null>(null);

  const criar = useCriarUnidade();
  const atualizar = useAtualizarUnidade();
  const excluir = useExcluirUnidade();

  function abrirNovo() {
    setUnidadeEditando(null);
    setDialogoAberto(true);
  }

  function abrirEdicao(unidade: Unidade) {
    setUnidadeEditando(unidade);
    setDialogoAberto(true);
  }

  function salvar(valores: ValoresFormularioUnidade) {
    const corpo = paraCorpoDeUnidade(valores);
    if (unidadeEditando?.id) {
      atualizar.mutate(
        { id: unidadeEditando.id, corpo },
        { onSuccess: (dados) => setUnidadeEditando(dados) },
      );
    } else {
      criar.mutate(corpo as Esquema<"UnidadeCriar">, {
        onSuccess: (dados) => setUnidadeEditando(dados),
      });
    }
  }

  const colunas: ColunaDeTabela<Unidade>[] = [
    {
      id: "nome",
      cabecalho: "Nome",
      renderizarCelula: (u) => (
        <button type="button" className="text-left hover:underline" onClick={() => abrirEdicao(u)}>
          {u.nome}
        </button>
      ),
      valorDeOrdenacao: (u) => u.nome ?? "",
      ordenavel: true,
      larguraPx: 220,
    },
    { id: "codigo", cabecalho: "Código", renderizarCelula: (u) => u.codigo ?? "—", larguraPx: 120 },
    {
      id: "tipo",
      cabecalho: "Tipo",
      renderizarCelula: (u) => <Selo variant="neutro">{u.tipo ?? "—"}</Selo>,
      larguraPx: 120,
    },
    {
      id: "geocerca",
      cabecalho: "Geocerca",
      renderizarCelula: (u) =>
        u.geocercaPoligono && Object.keys(u.geocercaPoligono).length > 0 ? (
          <Selo variant="info">Poligonal</Selo>
        ) : u.geocercaLatitude != null ? (
          <Selo variant="info">Circular</Selo>
        ) : (
          <Selo variant="neutro">Sem geocerca</Selo>
        ),
      larguraPx: 130,
    },
    {
      id: "ativo",
      cabecalho: "Situação",
      renderizarCelula: (u) => (
        <Selo variant={u.ativo ? "sucesso" : "neutro"}>{u.ativo ? "Ativa" : "Inativa"}</Selo>
      ),
      larguraPx: 100,
    },
    {
      id: "acoes",
      cabecalho: "Ações",
      renderizarCelula: (u) => (
        <PortaoDePermissao permissao="unidades.excluir">
          <Botao variant="destrutiva" tamanho="compacto" onClick={() => setUnidadeExcluindo(u)}>
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
        <h1 className="estilo-titulo-pagina text-texto-primario">Unidades</h1>
        <PortaoDePermissao permissao="unidades.criar">
          <Botao onClick={abrirNovo}>Nova unidade</Botao>
        </PortaoDePermissao>
      </header>

      <Entrada
        placeholder="Buscar por nome ou código…"
        value={busca}
        onChange={(evento) => setBusca(evento.target.value)}
        className="max-w-sm"
        aria-label="Buscar unidades"
      />

      {consulta.isError ? (
        <Alerta variant="erro">
          <AlertaDescricao>{mensagemDeErroApi(consulta.error)}</AlertaDescricao>
        </Alerta>
      ) : null}

      <TabelaDeDados
        linhas={consulta.data?.dados ?? []}
        colunas={colunas}
        obterId={(u) => u.id ?? ""}
        carregando={consulta.isPending}
        mensagemVazia="Nenhuma unidade cadastrada."
      />

      <Dialogo open={dialogoAberto} onOpenChange={setDialogoAberto}>
        <DialogoConteudo className="sm:max-w-3xl">
          <DialogoCabecalho>
            <DialogoTitulo>
              {unidadeEditando ? `Editar unidade — ${unidadeEditando.nome}` : "Nova unidade"}
            </DialogoTitulo>
          </DialogoCabecalho>
          <Abas defaultValue="dados">
            <ListaDeAbas>
              <AbaGatilho value="dados">Dados</AbaGatilho>
              <AbaGatilho value="geocerca" disabled={!unidadeEditando?.id}>
                Geocerca
              </AbaGatilho>
              <AbaGatilho value="redes" disabled={!unidadeEditando?.id}>
                Redes permitidas
              </AbaGatilho>
            </ListaDeAbas>
            <ConteudoDaAba value="dados">
              <FormularioUnidade
                key={unidadeEditando?.id ?? "novo"}
                unidade={unidadeEditando}
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
            </ConteudoDaAba>
            <ConteudoDaAba value="geocerca">
              {unidadeEditando?.id ? (
                <SecaoGeocerca unidade={unidadeEditando} />
              ) : (
                <p className="estilo-corpo text-texto-secundario">
                  Salve a unidade primeiro para configurar a geocerca.
                </p>
              )}
            </ConteudoDaAba>
            <ConteudoDaAba value="redes">
              {unidadeEditando?.id ? (
                <SecaoRedesPermitidas unidadeId={unidadeEditando.id} />
              ) : (
                <p className="estilo-corpo text-texto-secundario">
                  Salve a unidade primeiro para cadastrar redes permitidas.
                </p>
              )}
            </ConteudoDaAba>
          </Abas>
        </DialogoConteudo>
      </Dialogo>

      <DialogoConfirmacao
        aberto={Boolean(unidadeExcluindo)}
        aoMudarAberto={(aberto) => {
          if (!aberto) setUnidadeExcluindo(null);
        }}
        titulo="Excluir unidade"
        descricao={`"${unidadeExcluindo?.nome ?? ""}" será removida das listagens. O histórico é preservado para auditoria.`}
        rotuloConfirmar="Excluir"
        confirmando={excluir.isPending}
        erro={excluir.isError ? mensagemDeErroApi(excluir.error) : undefined}
        aoConfirmar={() => {
          if (!unidadeExcluindo?.id) return;
          excluir.mutate(unidadeExcluindo.id, { onSuccess: () => setUnidadeExcluindo(null) });
        }}
      />
    </div>
  );
}
