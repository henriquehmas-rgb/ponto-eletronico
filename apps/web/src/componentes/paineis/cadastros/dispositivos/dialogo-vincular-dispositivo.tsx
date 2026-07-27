"use client";

import { useForm } from "react-hook-form";

import {
  CampoCheckbox,
  CampoSelecao,
  CampoTexto,
} from "@/componentes/paineis/cadastros/_campos/campos";
import { mensagemDeErroApi } from "@/componentes/paineis/cadastros/_shared/erro-amigavel";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import {
  Dialogo,
  DialogoCabecalho,
  DialogoConteudo,
  DialogoDescricao,
  DialogoRodape,
  DialogoTitulo,
} from "@/componentes/ui/dialog";
import { useVincularDispositivo } from "@/ganchos/use-dispositivos";
import type { Esquema } from "@/lib/api";

interface ValoresVinculo {
  colaboradorId: string;
  aprovarImediatamente: boolean;
  revogarAnterior: boolean;
  motivo: string;
}

interface DialogoVincularDispositivoProps {
  dispositivo: Esquema<"Dispositivo"> | null;
  colaboradores: Esquema<"Colaborador">[];
  aoFechar: () => void;
}

export function DialogoVincularDispositivo({
  dispositivo,
  colaboradores,
  aoFechar,
}: DialogoVincularDispositivoProps) {
  const vincular = useVincularDispositivo();
  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<ValoresVinculo>({
    defaultValues: {
      colaboradorId: "",
      aprovarImediatamente: false,
      revogarAnterior: false,
      motivo: "",
    },
  });

  function fechar() {
    reset();
    aoFechar();
  }

  function confirmar(valores: ValoresVinculo) {
    if (!dispositivo?.id || !valores.colaboradorId) return;
    vincular.mutate(
      {
        id: dispositivo.id,
        corpo: {
          colaboradorId: valores.colaboradorId,
          aprovarImediatamente: valores.aprovarImediatamente,
          revogarAnterior: valores.revogarAnterior,
          ...(valores.motivo ? { motivo: valores.motivo } : {}),
        },
      },
      { onSuccess: fechar },
    );
  }

  return (
    <Dialogo open={Boolean(dispositivo)} onOpenChange={(aberto) => !aberto && fechar()}>
      <DialogoConteudo>
        <DialogoCabecalho>
          <DialogoTitulo>Vincular dispositivo a colaborador</DialogoTitulo>
          <DialogoDescricao>
            Um único dispositivo ativo por colaborador — havendo outro, é preciso revogar o
            anterior.
          </DialogoDescricao>
        </DialogoCabecalho>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit(confirmar)}>
          <CampoSelecao
            id="vincular-colaborador"
            rotulo="Colaborador"
            obrigatorio
            name="colaboradorId"
            control={control}
            erro={errors.colaboradorId?.message}
            opcoes={colaboradores.map((c) => ({
              valor: c.id ?? "",
              rotulo: c.nomeCompleto ?? c.id ?? "",
            }))}
          />
          <CampoTexto id="vincular-motivo" rotulo="Motivo (auditoria)" {...register("motivo")} />
          <div className="flex flex-wrap gap-6">
            <CampoCheckbox
              id="vincular-aprovar"
              rotulo="Aprovar imediatamente (restrito ao RH)"
              name="aprovarImediatamente"
              control={control}
            />
            <CampoCheckbox
              id="vincular-revogar-anterior"
              rotulo="Revogar vínculo anterior do colaborador"
              name="revogarAnterior"
              control={control}
            />
          </div>
          {vincular.isError ? (
            <Alerta variant="erro">
              <AlertaDescricao>{mensagemDeErroApi(vincular.error)}</AlertaDescricao>
            </Alerta>
          ) : null}
          <DialogoRodape>
            <Botao
              type="button"
              variant="secundaria"
              onClick={fechar}
              disabled={vincular.isPending}
            >
              Cancelar
            </Botao>
            <Botao type="submit" disabled={vincular.isPending}>
              {vincular.isPending ? "Vinculando…" : "Vincular"}
            </Botao>
          </DialogoRodape>
        </form>
      </DialogoConteudo>
    </Dialogo>
  );
}
