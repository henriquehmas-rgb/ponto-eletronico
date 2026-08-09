"use client";

import { FileText } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Alerta, AlertaDescricao, AlertaTitulo } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { useComprovantes } from "@/ganchos/use-comprovantes";
import { ehErroDaApi } from "@/lib/api";
import { formatarDataHora } from "@/lib/formatacao";
import { paramsSemUndefined } from "@/lib/formatacao-f8/parametros-de-consulta";

export default function ListaDeComprovantes() {
  const [cursor, definirCursor] = useState<string | undefined>(undefined);
  const comprovantes = useComprovantes(paramsSemUndefined({ cursor }));

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
      ) : (comprovantes.data?.dados ?? []).length === 0 ? (
        <div className="rounded-suave border border-dashed border-borda-padrao p-6 text-center">
          <p className="estilo-corpo font-semibold text-texto-secundario">
            Nenhum comprovante emitido ainda.
          </p>
        </div>
      ) : (
        <>
          <div className="flex flex-col gap-2">
            {(comprovantes.data?.dados ?? []).map((comprovante) => (
              <div
                key={comprovante.id ?? comprovante.numero}
                className="flex items-center gap-3 rounded-suave bg-fundo-superficie p-4 shadow-flutuante-cartao"
              >
                <span className="flex size-8 shrink-0 items-center justify-center rounded-medio bg-fundo-sutil text-texto-secundario">
                  <FileText className="size-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="estilo-corpo truncate font-semibold text-texto-primario">
                    Comprovante {comprovante.numero ?? "—"}
                  </p>
                  <p className="estilo-identificador text-texto-terciario">
                    NSR {comprovante.nsr ?? "—"} ·{" "}
                    {comprovante.datahoraMarcacao
                      ? formatarDataHora(comprovante.datahoraMarcacao)
                      : "—"}
                  </p>
                </div>
                <Botao
                  asChild
                  variant="secundaria"
                  tamanho="compacto"
                  className="shrink-0 rounded-pleno"
                >
                  <Link href={`/eu/comprovantes/${comprovante.id}`}>Ver</Link>
                </Botao>
              </div>
            ))}
          </div>
          <div className="flex justify-end">
            <Botao
              type="button"
              variant="secundaria"
              className="rounded-grande"
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
