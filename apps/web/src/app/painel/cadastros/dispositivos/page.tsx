"use client";

import { Globe, MonitorSmartphone, Plug, Smartphone, Tablet } from "lucide-react";
import { useState } from "react";
import type { ComponentType } from "react";

import { DialogoConfirmacao } from "@/componentes/paineis/cadastros/_shared/dialogo-confirmacao";
import { mensagemDeErroApi } from "@/componentes/paineis/cadastros/_shared/erro-amigavel";
import { DialogoVincularDispositivo } from "@/componentes/paineis/cadastros/dispositivos/dialogo-vincular-dispositivo";
import {
  FormularioDispositivo,
  paraCorpoDeDispositivo,
  type ValoresFormularioDispositivo,
} from "@/componentes/paineis/cadastros/dispositivos/formulario-dispositivo";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Selo } from "@/componentes/ui/badge";
import { Botao } from "@/componentes/ui/button";
import { Dialogo, DialogoCabecalho, DialogoConteudo, DialogoTitulo } from "@/componentes/ui/dialog";
import { Esqueleto } from "@/componentes/ui/skeleton";
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

const ICONE_POR_TIPO: Record<string, ComponentType<{ className?: string; "aria-hidden"?: boolean }>> = {
  terminal: MonitorSmartphone,
  totem: MonitorSmartphone,
  celular: Smartphone,
  tablet: Tablet,
  navegador: Globe,
  integracao: Plug,
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

  const dispositivos = consulta.data?.dados ?? [];

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="estilo-titulo-pagina text-texto-primario">Dispositivos</h1>
          <p className="estilo-corpo text-texto-terciario">
            {dispositivos.length} dispositivo(s) cadastrado(s)
          </p>
        </div>
        <PortaoDePermissao permissao="dispositivos.criar">
          <Botao
            className="rounded-pleno"
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

      {consulta.isPending ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 3 }).map((_, indice) => (
            <Esqueleto key={indice} className="h-[74px] w-full rounded-suave" />
          ))}
        </div>
      ) : dispositivos.length === 0 ? (
        <div className="rounded-suave border border-dashed border-borda-padrao p-6 text-center">
          <p className="estilo-corpo text-texto-secundario">Nenhum dispositivo cadastrado.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {dispositivos.map((d) => {
            const Icone = ICONE_POR_TIPO[d.tipo ?? ""] ?? MonitorSmartphone;
            return (
              <div
                key={d.id}
                className="flex flex-wrap items-center gap-3 rounded-suave bg-fundo-superficie p-[var(--espacamento-3)] shadow-flutuante-cartao"
              >
                <span className="flex size-9 shrink-0 items-center justify-center rounded-suave bg-acao-sutil-fundo text-acao-sutil-texto">
                  <Icone aria-hidden className="size-[18px]" />
                </span>
                <div className="min-w-0 flex-1">
                  <button
                    type="button"
                    className="truncate text-left text-[14px] font-medium text-texto-primario hover:underline"
                    onClick={() => {
                      setEditando(d);
                      setDialogoAberto(true);
                    }}
                  >
                    {d.nome ?? d.identificador ?? d.id}
                  </button>
                  <p className="truncate text-[12px] text-texto-terciario">
                    {d.tipo ?? "—"} · {d.plataforma ?? "—"}
                  </p>
                </div>
                {d.identificador ? (
                  <span className="estilo-tabular text-[11.5px] text-texto-desabilitado">
                    {d.identificador}
                  </span>
                ) : null}
                <Selo variant={SELO_POR_STATUS[d.status ?? ""] ?? "neutro"}>{d.status ?? "—"}</Selo>
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
              </div>
            );
          })}
        </div>
      )}

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
