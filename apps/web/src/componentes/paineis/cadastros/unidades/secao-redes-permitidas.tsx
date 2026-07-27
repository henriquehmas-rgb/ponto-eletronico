"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";

import { CampoTexto } from "@/componentes/paineis/cadastros/_campos/campos";
import { mensagemDeErroApi } from "@/componentes/paineis/cadastros/_shared/erro-amigavel";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import { Esqueleto } from "@/componentes/ui/skeleton";
import {
  useCriarRedePermitida,
  useExcluirRedePermitida,
  useRedesPermitidas,
} from "@/ganchos/use-unidades";
import type { Esquema } from "@/lib/api";

interface ValoresRede {
  cidr: string;
  descricao: string;
}

interface SecaoRedesPermitidasProps {
  unidadeId: string;
}

/** Allowlist CIDR da unidade (T4) — sub-recurso do mesmo formulário. */
export function SecaoRedesPermitidas({ unidadeId }: SecaoRedesPermitidasProps) {
  const consulta = useRedesPermitidas(unidadeId);
  const criar = useCriarRedePermitida();
  const excluir = useExcluirRedePermitida();
  const [redeExcluindoId, setRedeExcluindoId] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ValoresRede>({
    defaultValues: { cidr: "", descricao: "" },
  });

  function adicionar(valores: ValoresRede) {
    criar.mutate(
      {
        unidadeId,
        corpo: {
          cidr: valores.cidr,
          ...(valores.descricao ? { descricao: valores.descricao } : {}),
        },
      },
      { onSuccess: () => reset({ cidr: "", descricao: "" }) },
    );
  }

  function remover(rede: Esquema<"RedePermitida">) {
    if (!rede.id) return;
    setRedeExcluindoId(rede.id);
    excluir.mutate({ unidadeId, redeId: rede.id }, { onSettled: () => setRedeExcluindoId(null) });
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="estilo-legenda text-texto-secundario">
        Faixas CIDR autorizadas a registrar ponto por esta unidade (canal web). Uma faixa mal
        cadastrada impede o registro por toda a unidade — a ação fica auditada.
      </p>

      {consulta.isPending ? (
        <Esqueleto className="h-24 w-full" />
      ) : consulta.isError ? (
        <Alerta variant="erro">
          <AlertaDescricao>{mensagemDeErroApi(consulta.error)}</AlertaDescricao>
        </Alerta>
      ) : (consulta.data?.dados ?? []).length === 0 ? (
        <p className="estilo-corpo text-texto-secundario">
          Nenhuma faixa cadastrada para esta unidade.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {(consulta.data?.dados ?? []).map((rede) => (
            <li
              key={rede.id}
              className="flex items-center justify-between gap-3 rounded-pequeno border border-borda-sutil p-2"
            >
              <div>
                <p className="estilo-tabular text-texto-primario">{rede.cidr}</p>
                {rede.descricao ? (
                  <p className="estilo-legenda text-texto-secundario">{rede.descricao}</p>
                ) : null}
              </div>
              <Botao
                variant="destrutiva"
                tamanho="compacto"
                disabled={redeExcluindoId === rede.id}
                onClick={() => {
                  remover(rede);
                }}
              >
                Remover
              </Botao>
            </li>
          ))}
        </ul>
      )}

      <form className="flex flex-wrap items-end gap-3" onSubmit={handleSubmit(adicionar)}>
        <CampoTexto
          id="rede-cidr"
          rotulo="CIDR"
          obrigatorio
          placeholder="200.150.10.0/24"
          erro={errors.cidr?.message}
          {...register("cidr", { required: "Informe a faixa CIDR." })}
        />
        <CampoTexto
          id="rede-descricao"
          rotulo="Descrição"
          placeholder="Link primário"
          {...register("descricao")}
        />
        <Botao type="submit" variant="secundaria" disabled={criar.isPending}>
          {criar.isPending ? "Adicionando…" : "Adicionar"}
        </Botao>
      </form>
      {criar.isError ? (
        <Alerta variant="erro">
          <AlertaDescricao>{mensagemDeErroApi(criar.error)}</AlertaDescricao>
        </Alerta>
      ) : null}
    </div>
  );
}
