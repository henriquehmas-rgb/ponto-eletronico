"use client";

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
import {
  TabelaBase,
  TabelaBaseCabecalho,
  TabelaBaseCabecalhoDeColuna,
  TabelaBaseCelula,
  TabelaBaseCorpo,
  TabelaBaseLinha,
} from "@/componentes/ui/table";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { useEmpresas } from "@/ganchos/use-empresas";
import { useTurnos } from "@/ganchos/use-turnos";
import { PortaoDePermissao } from "@/lib/permissoes";
import type { Esquema } from "@/lib/api";

import { nomeExibidoDaEmpresa } from "./dados-compartilhados";
import { FormularioTurno } from "./formulario-turno";
import { mensagemDeErroApi } from "./mensagem-de-erro-api";

const ROTULO_TIPO_TURNO: Record<NonNullable<Esquema<"Turno">["tipo"]>, string> = {
  diurno: "Diurno",
  noturno: "Noturno",
  misto: "Misto",
  folga: "Folga",
  dsr: "DSR",
  sobreaviso: "Sobreaviso",
  prontidao: "Prontidão",
};

/**
 * Cadastro de turnos (T12). Não existe `GET /v1/turnos/{turnoId}` individual
 * nem exclusão no contrato — a lista é a única fonte do detalhe, e a única
 * ação além de criar é editar (`atualizarTurno`).
 */
export function ListaDeTurnos() {
  const empresas = useEmpresas({ ativo: true });
  const [empresaId, definirEmpresaId] = useState<string | undefined>(undefined);
  const [cursor, definirCursor] = useState<string | undefined>(undefined);
  const turnos = useTurnos({ empresaId, cursor });
  const [formularioAberto, definirFormularioAberto] = useState(false);
  const [turnoEmEdicao, definirTurnoEmEdicao] = useState<Esquema<"Turno"> | null>(null);

  const listaDeEmpresas = empresas.data?.dados ?? [];

  function abrirCriacao() {
    definirTurnoEmEdicao(null);
    definirFormularioAberto(true);
  }

  function abrirEdicao(turno: Esquema<"Turno">) {
    definirTurnoEmEdicao(turno);
    definirFormularioAberto(true);
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
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
        </div>
        <PortaoDePermissao permissao="turnos.criar">
          <Botao type="button" onClick={abrirCriacao}>
            Novo turno
          </Botao>
        </PortaoDePermissao>
      </div>

      {turnos.isPending ? (
        <Esqueleto className="h-48 w-full" />
      ) : turnos.isError ? (
        <p className="estilo-corpo text-estado-erro-texto" role="alert">
          {mensagemDeErroApi(turnos.error)}
        </p>
      ) : (
        <TabelaBase>
          <TabelaBaseCabecalho>
            <TabelaBaseLinha>
              <TabelaBaseCabecalhoDeColuna>Código</TabelaBaseCabecalhoDeColuna>
              <TabelaBaseCabecalhoDeColuna>Nome</TabelaBaseCabecalhoDeColuna>
              <TabelaBaseCabecalhoDeColuna>Natureza</TabelaBaseCabecalhoDeColuna>
              <TabelaBaseCabecalhoDeColuna>Cor</TabelaBaseCabecalhoDeColuna>
              <TabelaBaseCabecalhoDeColuna>Situação</TabelaBaseCabecalhoDeColuna>
              <TabelaBaseCabecalhoDeColuna>
                <span className="sr-only">Ações</span>
              </TabelaBaseCabecalhoDeColuna>
            </TabelaBaseLinha>
          </TabelaBaseCabecalho>
          <TabelaBaseCorpo>
            {(turnos.data?.dados ?? []).length === 0 ? (
              <TabelaBaseLinha>
                <TabelaBaseCelula colSpan={6} className="text-center text-texto-secundario">
                  Nenhum turno cadastrado.
                </TabelaBaseCelula>
              </TabelaBaseLinha>
            ) : (
              (turnos.data?.dados ?? []).map((turno) => (
                <TabelaBaseLinha key={turno.id}>
                  <TabelaBaseCelula className="estilo-tabular">{turno.codigo}</TabelaBaseCelula>
                  <TabelaBaseCelula>{turno.nome}</TabelaBaseCelula>
                  <TabelaBaseCelula>
                    {turno.tipo ? ROTULO_TIPO_TURNO[turno.tipo] : "—"}
                  </TabelaBaseCelula>
                  <TabelaBaseCelula>
                    <span className="inline-flex items-center gap-2">
                      <span
                        aria-hidden="true"
                        className="size-3 shrink-0 rounded-pleno border border-borda-sutil"
                        style={{ backgroundColor: turno.cor }}
                      />
                      <span className="estilo-tabular">{turno.cor}</span>
                    </span>
                  </TabelaBaseCelula>
                  <TabelaBaseCelula>
                    <Selo variant={turno.ativo ? "sucesso" : "neutro"}>
                      {turno.ativo ? "Ativo" : "Inativo"}
                    </Selo>
                  </TabelaBaseCelula>
                  <TabelaBaseCelula>
                    <PortaoDePermissao permissao="turnos.editar">
                      <Botao
                        type="button"
                        variant="secundaria"
                        tamanho="compacto"
                        onClick={() => {
                          abrirEdicao(turno);
                        }}
                      >
                        Editar
                      </Botao>
                    </PortaoDePermissao>
                  </TabelaBaseCelula>
                </TabelaBaseLinha>
              ))
            )}
          </TabelaBaseCorpo>
        </TabelaBase>
      )}

      <div className="flex justify-end">
        <Botao
          type="button"
          variant="secundaria"
          disabled={!turnos.data?.paginacao?.temMais}
          onClick={() => {
            definirCursor(turnos.data?.paginacao?.proximoCursor);
          }}
        >
          Próxima página
        </Botao>
      </div>

      <FormularioTurno
        aberto={formularioAberto}
        aoMudarAberto={definirFormularioAberto}
        turno={turnoEmEdicao}
        empresas={listaDeEmpresas}
        empresaIdPadrao={empresaId}
      />
    </div>
  );
}
