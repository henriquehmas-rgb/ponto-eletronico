"use client";

import { useForm } from "react-hook-form";

import { CampoCheckbox, CampoTexto } from "@/componentes/paineis/cadastros/_campos/campos";
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
import { useEncerrarVinculo } from "@/ganchos/use-vinculos";
import type { Esquema } from "@/lib/api";

interface ValoresEncerramento {
  dataFim: string;
  motivoDesligamento: string;
  quitarBancoHoras: boolean;
}

interface DialogoEncerrarVinculoProps {
  vinculo: Esquema<"Vinculo"> | null;
  aoFechar: () => void;
}

/**
 * `POST /v1/vinculos/{id}/encerrar` — desligamento. Dispara acerto do saldo
 * de banco de horas (saldo credor/devedor, conforme a política) e encerra
 * jornada/escala vigentes. As marcações permanecem intocadas.
 */
export function DialogoEncerrarVinculo({ vinculo, aoFechar }: DialogoEncerrarVinculoProps) {
  const encerrar = useEncerrarVinculo();
  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<ValoresEncerramento>({
    defaultValues: { dataFim: "", motivoDesligamento: "", quitarBancoHoras: true },
  });

  function fechar() {
    reset();
    aoFechar();
  }

  function confirmar(valores: ValoresEncerramento) {
    if (!vinculo?.id) return;
    encerrar.mutate(
      {
        id: vinculo.id,
        corpo: {
          dataFim: valores.dataFim,
          ...(valores.motivoDesligamento ? { motivoDesligamento: valores.motivoDesligamento } : {}),
          quitarBancoHoras: valores.quitarBancoHoras,
        },
      },
      { onSuccess: fechar },
    );
  }

  return (
    <Dialogo open={Boolean(vinculo)} onOpenChange={(aberto) => !aberto && fechar()}>
      <DialogoConteudo>
        <DialogoCabecalho>
          <DialogoTitulo>Encerrar vínculo</DialogoTitulo>
          <DialogoDescricao>
            Registra o desligamento. As marcações do colaborador permanecem intocadas e a guarda
            legal de 5 anos continua valendo.
          </DialogoDescricao>
        </DialogoCabecalho>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit(confirmar)}>
          <CampoTexto
            id="encerramento-data-fim"
            rotulo="Último dia do vínculo"
            type="date"
            obrigatorio
            erro={errors.dataFim?.message}
            {...register("dataFim", { required: "Informe a data de encerramento." })}
          />
          <CampoTexto
            id="encerramento-motivo"
            rotulo="Motivo do desligamento"
            {...register("motivoDesligamento")}
          />
          <CampoCheckbox
            id="encerramento-quitar-bh"
            rotulo="Quitar saldo de banco de horas na rescisão"
            name="quitarBancoHoras"
            control={control}
          />
          {encerrar.isError ? (
            <Alerta variant="erro">
              <AlertaDescricao>{mensagemDeErroApi(encerrar.error)}</AlertaDescricao>
            </Alerta>
          ) : null}
          <DialogoRodape>
            <Botao
              type="button"
              variant="secundaria"
              onClick={fechar}
              disabled={encerrar.isPending}
            >
              Cancelar
            </Botao>
            <Botao type="submit" variant="destrutiva" disabled={encerrar.isPending}>
              {encerrar.isPending ? "Encerrando…" : "Encerrar vínculo"}
            </Botao>
          </DialogoRodape>
        </form>
      </DialogoConteudo>
    </Dialogo>
  );
}
