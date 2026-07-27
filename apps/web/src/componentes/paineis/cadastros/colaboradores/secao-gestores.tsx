"use client";

import { useForm } from "react-hook-form";

import { CampoSelecao, CampoTexto } from "@/componentes/paineis/cadastros/_campos/campos";
import { mensagemDeErroApi } from "@/componentes/paineis/cadastros/_shared/erro-amigavel";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Selo } from "@/componentes/ui/badge";
import { Botao } from "@/componentes/ui/button";
import { Esqueleto } from "@/componentes/ui/skeleton";
import {
  useDefinirGestorDoColaborador,
  useGestoresDoColaborador,
} from "@/ganchos/use-colaboradores";
import { formatarData } from "@/lib/formatacao";
import type { Esquema } from "@/lib/api";

interface ValoresGestor {
  gestorColaboradorId: string;
  tipo: Esquema<"ColaboradorGestorCriar">["tipo"] | "";
  vigenciaInicio: string;
}

interface SecaoGestoresProps {
  colaborador: Esquema<"Colaborador">;
  colaboradores: Esquema<"Colaborador">[];
}

const OPCOES_TIPO = [
  { valor: "imediato", rotulo: "Imediato" },
  { valor: "substituto", rotulo: "Substituto" },
  { valor: "matricial", rotulo: "Matricial" },
  { valor: "rh", rotulo: "RH" },
];

/**
 * `GET`/`PUT /v1/colaboradores/{id}/gestores` (T7). `definirGestoresColaborador`
 * substitui a vigência do TIPO informado (no máximo um gestor IMEDIATO
 * vigente por colaborador) — não é uma lista em lote de todos os gestores de
 * uma vez.
 */
export function SecaoGestores({ colaborador, colaboradores }: SecaoGestoresProps) {
  const gestores = useGestoresDoColaborador(colaborador.id);
  const definir = useDefinirGestorDoColaborador();
  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<ValoresGestor>({
    defaultValues: { gestorColaboradorId: "", tipo: "imediato", vigenciaInicio: "" },
  });

  function salvar(valores: ValoresGestor) {
    if (!colaborador.id || !valores.gestorColaboradorId || !valores.tipo || !valores.vigenciaInicio)
      return;
    definir.mutate(
      {
        colaboradorId: colaborador.id,
        corpo: {
          gestorColaboradorId: valores.gestorColaboradorId,
          tipo: valores.tipo,
          vigenciaInicio: valores.vigenciaInicio,
        },
      },
      { onSuccess: () => reset({ gestorColaboradorId: "", tipo: "imediato", vigenciaInicio: "" }) },
    );
  }

  const outrosColaboradores = colaboradores.filter((c) => c.id !== colaborador.id);

  return (
    <div className="flex flex-col gap-4">
      {gestores.isPending ? (
        <Esqueleto className="h-20 w-full" />
      ) : gestores.isError ? (
        <Alerta variant="erro">
          <AlertaDescricao>{mensagemDeErroApi(gestores.error)}</AlertaDescricao>
        </Alerta>
      ) : (gestores.data?.dados ?? []).length === 0 ? (
        <p className="estilo-corpo text-texto-secundario">Nenhum gestor vigente cadastrado.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {(gestores.data?.dados ?? []).map((gestor) => {
            const nomeGestor = outrosColaboradores.find(
              (c) => c.id === gestor.gestorColaboradorId,
            )?.nomeCompleto;
            return (
              <li
                key={gestor.id}
                className="flex items-center justify-between rounded-pequeno border border-borda-sutil p-3"
              >
                <div>
                  <p className="estilo-corpo text-texto-primario">
                    {nomeGestor ?? gestor.gestorColaboradorId}
                  </p>
                  <p className="estilo-legenda text-texto-secundario">
                    Desde {gestor.vigenciaInicio ? formatarData(gestor.vigenciaInicio) : "—"}
                    {gestor.vigenciaFim
                      ? ` até ${formatarData(gestor.vigenciaFim)}`
                      : " · vigência aberta"}
                  </p>
                </div>
                <Selo variant="neutro">{gestor.tipo}</Selo>
              </li>
            );
          })}
        </ul>
      )}

      <form className="flex flex-wrap items-end gap-3" onSubmit={handleSubmit(salvar)}>
        <CampoSelecao
          id="gestor-colaborador"
          rotulo="Gestor"
          obrigatorio
          name="gestorColaboradorId"
          control={control}
          erro={errors.gestorColaboradorId?.message}
          opcoes={outrosColaboradores.map((c) => ({
            valor: c.id ?? "",
            rotulo: c.nomeCompleto ?? c.id ?? "",
          }))}
        />
        <CampoSelecao
          id="gestor-tipo"
          rotulo="Tipo"
          name="tipo"
          control={control}
          opcoes={OPCOES_TIPO}
        />
        <CampoTexto
          id="gestor-vigencia"
          rotulo="Vigência a partir de"
          type="date"
          obrigatorio
          erro={errors.vigenciaInicio?.message}
          {...register("vigenciaInicio", { required: "Informe a data de início." })}
        />
        <Botao type="submit" variant="secundaria" disabled={definir.isPending}>
          {definir.isPending ? "Salvando…" : "Definir gestor"}
        </Botao>
      </form>
      {definir.isError ? (
        <Alerta variant="erro">
          <AlertaDescricao>{mensagemDeErroApi(definir.error)}</AlertaDescricao>
        </Alerta>
      ) : null}
    </div>
  );
}
