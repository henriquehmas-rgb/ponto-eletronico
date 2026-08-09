"use client";

import { LayoutGrid } from "lucide-react";
import { useState } from "react";

import { Selo } from "@/componentes/ui/badge";
import { Botao } from "@/componentes/ui/button";
import {
  Selecao,
  SelecaoConteudo,
  SelecaoGatilho,
  SelecaoItem,
  SelecaoValor,
} from "@/componentes/ui/select";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { useEmpresas } from "@/ganchos/use-empresas";
import { useEscalas, useExcluirEscala } from "@/ganchos/use-escalas";
import { PortaoDePermissao } from "@/lib/permissoes";
import type { Esquema } from "@/lib/api";

import { nomeExibidoDaEmpresa, useEquipeVisivel } from "./dados-compartilhados";
import { DialogoConfirmacao } from "./dialogo-confirmacao";
import { FormularioAtribuicao } from "./formulario-atribuicao";
import { FormularioEscala } from "./formulario-escala";
import { mensagemDeErroApi } from "./mensagem-de-erro-api";

/**
 * Cadastro de escalas — padrões cíclicos de trabalho/folga — e atribuição a
 * vínculo (T12). `excluirEscala` é exclusão LÓGICA e é recusada
 * (`PONTO-CONF-004`) quando há atribuições vigentes — o diálogo de
 * confirmação mostra esse erro tal como o servidor devolve, nunca finge que
 * a exclusão sempre funciona.
 */
export function ListaDeEscalas() {
  const empresas = useEmpresas({ ativo: true });
  const equipe = useEquipeVisivel();
  const [empresaId, definirEmpresaId] = useState<string | undefined>(undefined);
  const [cursor, definirCursor] = useState<string | undefined>(undefined);
  const escalas = useEscalas({ empresaId, cursor });
  const excluir = useExcluirEscala();

  const [formularioAberto, definirFormularioAberto] = useState(false);
  const [escalaEmEdicao, definirEscalaEmEdicao] = useState<Esquema<"Escala"> | null>(null);
  const [escalaParaExcluir, definirEscalaParaExcluir] = useState<Esquema<"Escala"> | null>(null);
  const [escalaParaAtribuir, definirEscalaParaAtribuir] = useState<Esquema<"Escala"> | null>(null);
  const [atribuicaoAberta, definirAtribuicaoAberta] = useState(false);

  const listaDeEmpresas = empresas.data?.dados ?? [];

  function abrirCriacao() {
    definirEscalaEmEdicao(null);
    definirFormularioAberto(true);
  }

  function abrirEdicao(escala: Esquema<"Escala">) {
    definirEscalaEmEdicao(escala);
    definirFormularioAberto(true);
  }

  function abrirAtribuicao(escala: Esquema<"Escala">) {
    definirEscalaParaAtribuir(escala);
    definirAtribuicaoAberta(true);
  }

  async function confirmarExclusao() {
    if (!escalaParaExcluir?.id) return;
    try {
      await excluir.mutateAsync(escalaParaExcluir.id);
      definirEscalaParaExcluir(null);
    } catch {
      // Erro exibido no próprio diálogo via `excluir.isError`.
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Selecao
          {...(empresaId ? { value: empresaId } : {})}
          onValueChange={(valor) => {
            definirEmpresaId(valor === "__todas__" ? undefined : valor);
            definirCursor(undefined);
          }}
        >
          <SelecaoGatilho aria-label="Filtrar por empresa" tamanho="compacto">
            <SelecaoValor placeholder="Todas as empresas" />
          </SelecaoGatilho>
          <SelecaoConteudo>
            <SelecaoItem value="__todas__">Todas as empresas</SelecaoItem>
            {listaDeEmpresas.map((empresa) => (
              <SelecaoItem key={empresa.id} value={empresa.id ?? ""}>
                {nomeExibidoDaEmpresa(empresa)}
              </SelecaoItem>
            ))}
          </SelecaoConteudo>
        </Selecao>
        <PortaoDePermissao permissao="escalas.criar">
          <Botao type="button" className="rounded-pleno" onClick={abrirCriacao}>
            Nova escala
          </Botao>
        </PortaoDePermissao>
      </div>

      {escalas.isPending ? (
        <Esqueleto className="h-48 w-full" />
      ) : escalas.isError ? (
        <p className="estilo-corpo text-estado-erro-texto" role="alert">
          {mensagemDeErroApi(escalas.error)}
        </p>
      ) : (escalas.data?.dados ?? []).length === 0 ? (
        <div className="rounded-suave border border-dashed border-borda-padrao p-6 text-center">
          <p className="estilo-corpo text-texto-secundario">Nenhuma escala cadastrada.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {(escalas.data?.dados ?? []).map((escala) => (
            <div
              key={escala.id}
              className="flex flex-wrap items-center gap-3 rounded-suave bg-fundo-superficie p-[var(--espacamento-3)] shadow-flutuante-cartao"
            >
              <span className="flex size-9 shrink-0 items-center justify-center rounded-suave bg-acao-sutil-fundo text-acao-sutil-texto">
                <LayoutGrid aria-hidden="true" className="size-[18px]" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[14px] font-medium text-texto-primario">
                  {escala.nome}
                  <span className="ml-2 estilo-tabular text-[12px] text-texto-terciario">
                    {escala.codigo}
                  </span>
                </p>
                <p className="truncate text-[12px] text-texto-terciario">
                  {escala.tipo} · {escala.diasCiclo} dias de ciclo
                </p>
              </div>
              <Selo variant={escala.ativo ? "sucesso" : "neutro"}>
                {escala.ativo ? "Ativa" : "Inativa"}
              </Selo>
              <div className="flex gap-2">
                <PortaoDePermissao permissao="escalas.editar">
                  <Botao
                    type="button"
                    variant="secundaria"
                    tamanho="compacto"
                    onClick={() => {
                      abrirEdicao(escala);
                    }}
                  >
                    Editar
                  </Botao>
                  <Botao
                    type="button"
                    variant="secundaria"
                    tamanho="compacto"
                    onClick={() => {
                      abrirAtribuicao(escala);
                    }}
                  >
                    Atribuir
                  </Botao>
                </PortaoDePermissao>
                <PortaoDePermissao permissao="escalas.excluir">
                  <Botao
                    type="button"
                    variant="destrutiva"
                    tamanho="compacto"
                    onClick={() => {
                      definirEscalaParaExcluir(escala);
                    }}
                  >
                    Excluir
                  </Botao>
                </PortaoDePermissao>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="flex justify-end">
        <Botao
          type="button"
          variant="secundaria"
          disabled={!escalas.data?.paginacao?.temMais}
          onClick={() => {
            definirCursor(escalas.data?.paginacao?.proximoCursor);
          }}
        >
          Próxima página
        </Botao>
      </div>

      <FormularioEscala
        aberto={formularioAberto}
        aoMudarAberto={definirFormularioAberto}
        escala={escalaEmEdicao}
        empresas={listaDeEmpresas}
        empresaIdPadrao={empresaId}
      />

      <FormularioAtribuicao
        aberto={atribuicaoAberta}
        aoMudarAberto={definirAtribuicaoAberta}
        escala={escalaParaAtribuir}
        equipe={equipe.membros}
      />

      <DialogoConfirmacao
        aberto={Boolean(escalaParaExcluir)}
        aoMudarAberto={(aberto) => {
          if (!aberto) definirEscalaParaExcluir(null);
        }}
        titulo="Excluir escala"
        descricao={`A escala "${escalaParaExcluir?.nome ?? ""}" será removida das listagens (exclusão lógica). Recusada se houver atribuições vigentes.`}
        rotuloConfirmar="Excluir"
        confirmando={excluir.isPending}
        erro={excluir.isError ? mensagemDeErroApi(excluir.error) : undefined}
        aoConfirmar={() => {
          void confirmarExclusao();
        }}
      />
    </div>
  );
}
