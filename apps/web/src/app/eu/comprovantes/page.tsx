"use client";

import Link from "next/link";
import { useState } from "react";

import { type ColunaDeTabela, TabelaDeDados } from "@/componentes/dominio/tabela-de-dados";
import { Alerta, AlertaDescricao, AlertaTitulo } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { useComprovantes } from "@/ganchos/use-comprovantes";
import { ehErroDaApi, type Esquema } from "@/lib/api";
import { formatarDataHora } from "@/lib/formatacao";
import { paramsSemUndefined } from "@/lib/formatacao-f8/parametros-de-consulta";

export default function ListaDeComprovantes() {
  const [cursor, definirCursor] = useState<string | undefined>(undefined);
  const comprovantes = useComprovantes(paramsSemUndefined({ cursor }));

  const colunas: ColunaDeTabela<Esquema<"Comprovante">>[] = [
    { id: "numero", cabecalho: "Número", renderizarCelula: (linha) => linha.numero ?? "—" },
    {
      id: "nsr",
      cabecalho: "NSR",
      renderizarCelula: (linha) => (linha.nsr !== undefined ? String(linha.nsr) : "—"),
    },
    {
      id: "datahoraMarcacao",
      cabecalho: "Marcação",
      renderizarCelula: (linha) =>
        linha.datahoraMarcacao ? formatarDataHora(linha.datahoraMarcacao) : "—",
    },
    {
      id: "acao",
      cabecalho: "",
      renderizarCelula: (linha) => (
        <Link
          className="estilo-corpo text-acao-sutil-texto underline"
          href={`/eu/comprovantes/${linha.id}`}
        >
          Ver comprovante
        </Link>
      ),
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <h1 className="estilo-titulo-pagina text-texto-primario">Comprovantes</h1>

      {comprovantes.isPending ? (
        <Esqueleto className="h-40 w-full" />
      ) : comprovantes.isError ? (
        <Alerta variant="erro">
          <AlertaTitulo>Não foi possível carregar seus comprovantes</AlertaTitulo>
          <AlertaDescricao>
            {ehErroDaApi(comprovantes.error)
              ? comprovantes.error.problema?.title
              : "Tente novamente em instantes."}
          </AlertaDescricao>
        </Alerta>
      ) : (
        <>
          <TabelaDeDados
            linhas={comprovantes.data?.dados ?? []}
            colunas={colunas}
            obterId={(linha) => linha.id ?? linha.numero ?? String(Math.random())}
            mensagemVazia="Nenhum comprovante emitido ainda."
          />
          <div className="flex justify-end">
            <Botao
              type="button"
              variant="secundaria"
              disabled={!comprovantes.data?.paginacao?.temMais}
              onClick={() => {
                definirCursor(comprovantes.data?.paginacao?.proximoCursor);
              }}
            >
              Próxima página
            </Botao>
          </div>
        </>
      )}
    </div>
  );
}
