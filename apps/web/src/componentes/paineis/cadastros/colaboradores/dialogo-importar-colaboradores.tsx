"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";

import { CampoSelecao, CampoTexto } from "@/componentes/paineis/cadastros/_campos/campos";
import { mensagemDeErroApi } from "@/componentes/paineis/cadastros/_shared/erro-amigavel";
import { Alerta, AlertaDescricao, AlertaTitulo } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import {
  Dialogo,
  DialogoCabecalho,
  DialogoConteudo,
  DialogoDescricao,
  DialogoRodape,
  DialogoTitulo,
} from "@/componentes/ui/dialog";
import { Selo } from "@/componentes/ui/badge";
import { useImportarColaboradores } from "@/ganchos/use-colaboradores";
import type { Esquema } from "@/lib/api";

interface ValoresImportacao {
  empresaId: string;
  origem: Esquema<"ImportacaoCriar">["origem"] | "";
  nomeArquivo: string;
  conteudoRef: string;
}

interface DialogoImportarColaboradoresProps {
  aberto: boolean;
  aoMudarAberto: (aberto: boolean) => void;
  empresas: Esquema<"Empresa">[];
}

/**
 * `POST /v1/colaboradores/importar` (`importarColaboradores`, T7) —
 * processamento assíncrono (`Importacao.status`). **Achado de contrato,
 * registrado em `docs/backlog.md`**: não existe, em nenhuma tag do
 * `openapi.yaml`, um endpoint de upload de arquivo para obter `conteudoRef`
 * a partir de um CSV/XLSX real — a mesma lacuna que `worker/tarefas/
 * importacoes.py` já documenta para F2/F6. Por isso o campo é um texto que
 * pressupõe uma referência já existente no armazenamento de objetos, não um
 * seletor de arquivo — esta tela não inventa um protocolo de upload próprio.
 */
export function DialogoImportarColaboradores({
  aberto,
  aoMudarAberto,
  empresas,
}: DialogoImportarColaboradoresProps) {
  const importar = useImportarColaboradores();
  const [resultado, setResultado] = useState<Esquema<"Importacao"> | null>(null);
  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<ValoresImportacao>({
    defaultValues: { empresaId: "", origem: "csv", nomeArquivo: "", conteudoRef: "" },
  });

  function enviar(valores: ValoresImportacao) {
    if (!valores.empresaId || !valores.origem) return;
    importar.mutate(
      {
        empresaId: valores.empresaId,
        tipo: "colaboradores",
        origem: valores.origem,
        ...(valores.nomeArquivo ? { nomeArquivo: valores.nomeArquivo } : {}),
        conteudoRef: valores.conteudoRef,
      },
      { onSuccess: (dados) => setResultado(dados) },
    );
  }

  function fechar() {
    setResultado(null);
    reset();
    aoMudarAberto(false);
  }

  return (
    <Dialogo open={aberto} onOpenChange={(valor) => (valor ? aoMudarAberto(true) : fechar())}>
      <DialogoConteudo className="sm:max-w-xl">
        <DialogoCabecalho>
          <DialogoTitulo>Importar colaboradores em lote</DialogoTitulo>
          <DialogoDescricao>
            Processamento assíncrono, com relatório linha a linha em caso de erro.
          </DialogoDescricao>
        </DialogoCabecalho>

        {resultado ? (
          <div className="flex flex-col gap-4">
            <Alerta variant="info">
              <AlertaTitulo>Importação enfileirada</AlertaTitulo>
              <AlertaDescricao>
                Status atual: <Selo variant="info">{resultado.status}</Selo>. Acompanhe pela lista
                de colaboradores — ela é atualizada automaticamente quando o processamento concluir.
              </AlertaDescricao>
            </Alerta>
            <DialogoRodape>
              <Botao onClick={fechar}>Fechar</Botao>
            </DialogoRodape>
          </div>
        ) : (
          <form className="flex flex-col gap-4" onSubmit={handleSubmit(enviar)}>
            <Alerta variant="atencao">
              <AlertaDescricao>
                O contrato ainda não expõe um endpoint de upload de arquivo (achado registrado em
                `docs/backlog.md`) — informe a referência (`conteudoRef`) de um arquivo já enviado
                ao armazenamento de objetos por outro canal.
              </AlertaDescricao>
            </Alerta>
            <CampoSelecao
              id="importacao-empresa"
              rotulo="Empresa"
              obrigatorio
              name="empresaId"
              control={control}
              erro={errors.empresaId?.message}
              opcoes={empresas.map((e) => ({
                valor: e.id ?? "",
                rotulo: e.razaoSocial ?? e.id ?? "",
              }))}
            />
            <CampoSelecao
              id="importacao-origem"
              rotulo="Formato do arquivo"
              name="origem"
              control={control}
              opcoes={[
                { valor: "csv", rotulo: "CSV" },
                { valor: "xlsx", rotulo: "XLSX" },
              ]}
            />
            <CampoTexto
              id="importacao-nome-arquivo"
              rotulo="Nome do arquivo"
              {...register("nomeArquivo")}
            />
            <CampoTexto
              id="importacao-conteudo-ref"
              rotulo="Referência do arquivo (conteudoRef)"
              obrigatorio
              erro={errors.conteudoRef?.message}
              {...register("conteudoRef", {
                required: "Informe a referência do arquivo já enviado.",
              })}
            />
            {importar.isError ? (
              <Alerta variant="erro">
                <AlertaDescricao>{mensagemDeErroApi(importar.error)}</AlertaDescricao>
              </Alerta>
            ) : null}
            <DialogoRodape>
              <Botao
                type="button"
                variant="secundaria"
                onClick={fechar}
                disabled={importar.isPending}
              >
                Cancelar
              </Botao>
              <Botao type="submit" disabled={importar.isPending}>
                {importar.isPending ? "Enviando…" : "Importar"}
              </Botao>
            </DialogoRodape>
          </form>
        )}
      </DialogoConteudo>
    </Dialogo>
  );
}
