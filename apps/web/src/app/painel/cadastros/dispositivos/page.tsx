"use client";

import { useState } from "react";

import { DialogoConfirmacao } from "@/componentes/paineis/cadastros/_shared/dialogo-confirmacao";
import { mensagemDeErroApi } from "@/componentes/paineis/cadastros/_shared/erro-amigavel";
import { DialogoVincularDispositivo } from "@/componentes/paineis/cadastros/dispositivos/dialogo-vincular-dispositivo";
import {
  FormularioDispositivo,
  paraCorpoDeDispositivo,
  type ValoresFormularioDispositivo,
} from "@/componentes/paineis/cadastros/dispositivos/formulario-dispositivo";
import { type ColunaDeTabela, TabelaDeDados } from "@/componentes/dominio/tabela-de-dados";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Selo } from "@/componentes/ui/badge";
import { Botao } from "@/componentes/ui/button";
import { Dialogo, DialogoCabecalho, DialogoConteudo, DialogoTitulo } from "@/componentes/ui/dialog";
import { useColaboradores } from "@/ganchos/use-colaboradores";
import {
  useAtualizarDispositivo,
  useCriarDispositivo,
  useDispositivosCadastro,
  useExcluirDispositivo,
} from "@/ganchos/use-dispositivos";
import { useEmpresas } from "@/ganchos/use-empresas";
import { useUnidades } from "@/ganchos/use-unidades";
import { PortaoDePermissao } from "@/lib/permissoes";
import type { Esquema } from "@/lib/api";

type Dispositivo = Esquema<"Dispositivo">;

const SELO_POR_STATUS: Record<string, "sucesso" | "atencao" | "erro" | "neutro"> = {
  ativo: "sucesso",
  pendente: "atencao",
  bloqueado: "erro",
  revogado: "neutro",
  substituido: "neutro",
};

export default function PaginaDeDispositivos() {
  const consulta = useDispositivosCadastro({});
  const empresas = useEmpresas({ ativo: true });
  const unidades = useUnidades({ ativo: true });
  const colaboradores = useColaboradores({ limite: 200 });

  const [dialogoAberto, setDialogoAberto] = useState(false);
  const [editando, setEditando] = useState<Dispositivo | null>(null);
  const [excluindo, setExcluindo] = useState<Dispositivo | null>(null);
  const [vinculando, setVinculando] = useState<Dispositivo | null>(null);

  const criar = useCriarDispositivo();
  const atualizar = useAtualizarDispositivo();
  const excluir = useExcluirDispositivo();

  function salvar(valores: ValoresFormularioDispositivo) {
    const corpo = paraCorpoDeDispositivo(valores);
    if (editando?.id) {
      atualizar.mutate(
        { id: editando.id, corpo: corpo as Esquema<"DispositivoAtualizar"> },
        { onSuccess: () => setDialogoAberto(false) },
      );
    } else {
      criar.mutate(corpo as Esquema<"DispositivoCriar">, {
        onSuccess: () => setDialogoAberto(false),
      });
    }
  }

  const colunas: ColunaDeTabela<Dispositivo>[] = [
    {
      id: "nome",
      cabecalho: "Dispositivo",
      renderizarCelula: (d) => (
        <button
          type="button"
          className="text-left hover:underline"
          onClick={() => {
            setEditando(d);
            setDialogoAberto(true);
          }}
        >
          {d.nome ?? d.identificador ?? d.id}
        </button>
      ),
      larguraPx: 220,
    },
    { id: "tipo", cabecalho: "Tipo", renderizarCelula: (d) => d.tipo ?? "—", larguraPx: 110 },
    {
      id: "plataforma",
      cabecalho: "Plataforma",
      renderizarCelula: (d) => d.plataforma ?? "—",
      larguraPx: 110,
    },
    {
      id: "status",
      cabecalho: "Situação",
      renderizarCelula: (d) => (
        <Selo variant={SELO_POR_STATUS[d.status ?? ""] ?? "neutro"}>{d.status ?? "—"}</Selo>
      ),
      larguraPx: 120,
    },
    {
      id: "acoes",
      cabecalho: "Ações",
      renderizarCelula: (d) => (
        <div className="flex gap-2">
          <PortaoDePermissao permissao="dispositivos.editar">
            <Botao variant="secundaria" tamanho="compacto" onClick={() => setVinculando(d)}>
              Vincular
            </Botao>
          </PortaoDePermissao>
          <PortaoDePermissao permissao="dispositivos.excluir">
            <Botao variant="destrutiva" tamanho="compacto" onClick={() => setExcluindo(d)}>
              Excluir
            </Botao>
          </PortaoDePermissao>
        </div>
      ),
      larguraPx: 200,
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="estilo-titulo-pagina text-texto-primario">Dispositivos</h1>
        <PortaoDePermissao permissao="dispositivos.criar">
          <Botao
            onClick={() => {
              setEditando(null);
              setDialogoAberto(true);
            }}
          >
            Novo dispositivo
          </Botao>
        </PortaoDePermissao>
      </header>

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
        mensagemVazia="Nenhum dispositivo cadastrado."
      />

      <Dialogo open={dialogoAberto} onOpenChange={setDialogoAberto}>
        <DialogoConteudo className="sm:max-w-2xl">
          <DialogoCabecalho>
            <DialogoTitulo>{editando ? "Editar dispositivo" : "Novo dispositivo"}</DialogoTitulo>
          </DialogoCabecalho>
          <FormularioDispositivo
            key={editando?.id ?? "novo"}
            dispositivo={editando}
            empresas={empresas.data?.dados ?? []}
            unidades={unidades.data?.dados ?? []}
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

      <DialogoVincularDispositivo
        dispositivo={vinculando}
        colaboradores={colaboradores.data?.dados ?? []}
        aoFechar={() => setVinculando(null)}
      />

      <DialogoConfirmacao
        aberto={Boolean(excluindo)}
        aoMudarAberto={(aberto) => {
          if (!aberto) setExcluindo(null);
        }}
        titulo="Excluir dispositivo"
        descricao={`"${excluindo?.nome ?? excluindo?.identificador ?? ""}" será removido das listagens.`}
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
