"use client";

import { useForm } from "react-hook-form";
import { z } from "zod";

import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import { DialogoRodape } from "@/componentes/ui/dialog";
import { Rotulo } from "@/componentes/ui/label";
import { AreaDeTexto } from "@/componentes/ui/textarea";
import type { Esquema } from "@/lib/api";

import { CampoListaDeEventos, CampoSelecao, CampoTexto } from "./campos";
import { EVENTOS_PUBLICOS } from "./eventos-publicos";
import { resolverZod } from "./resolver-zod";

const REGEX_UUID = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

const ESQUEMA = z.object({
  nome: z.string().min(1, "Informe o nome do webhook."),
  url: z
    .string()
    .min(1, "Informe a URL de destino.")
    .refine((v) => v.startsWith("https://"), "A URL precisa ser HTTPS (PONTO-WEBH-001)."),
  eventos: z.array(z.string()).min(1, "Selecione ao menos um evento."),
  apiClientId: z
    .string()
    .refine(
      (v) => v === "" || REGEX_UUID.test(v),
      "Informe um identificador válido (UUID) ou deixe em branco.",
    )
    .optional(),
  maxTentativas: z.coerce.number().int().min(1, "Deve ser maior que zero.").optional(),
  timeoutSegundos: z.coerce.number().int().min(1, "Deve ser maior que zero.").optional(),
  status: z.enum(["ativo", "suspenso", "desabilitado_por_falha"]).optional(),
  cabecalhosExtrasTexto: z.string().refine((v) => {
    if (!v || v.trim() === "") return true;
    try {
      JSON.parse(v);
      return true;
    } catch {
      return false;
    }
  }, 'Cabeçalhos extras precisam ser um JSON válido, ex.: {"X-Origem": "seeg"}.'),
});
export type FormularioDeWebhook = z.infer<typeof ESQUEMA>;

const OPCOES_STATUS = [
  { valor: "ativo", rotulo: "Ativo" },
  { valor: "suspenso", rotulo: "Suspenso" },
  { valor: "desabilitado_por_falha", rotulo: "Desabilitado por falha (reativar zera as falhas)" },
];

function valoresIniciais(webhook: Esquema<"Webhook"> | null): FormularioDeWebhook {
  return {
    nome: webhook?.nome ?? "",
    url: webhook?.url ?? "",
    eventos: webhook?.eventos ?? [],
    apiClientId: webhook?.apiClientId ?? "",
    maxTentativas: webhook?.maxTentativas ?? 8,
    timeoutSegundos: webhook?.timeoutSegundos ?? 10,
    status: webhook?.status ?? "ativo",
    cabecalhosExtrasTexto: webhook?.cabecalhosExtras
      ? JSON.stringify(webhook.cabecalhosExtras, null, 2)
      : "",
  };
}

/** Converte os valores do formulário no corpo aceito por `criarWebhook`/`atualizarWebhook`. */
export function paraCorpoDeWebhook(
  valores: FormularioDeWebhook,
): Esquema<"WebhookCriar"> | Esquema<"WebhookAtualizar"> {
  const corpo: Record<string, unknown> = {
    nome: valores.nome,
    url: valores.url,
    eventos: valores.eventos,
  };
  if (valores.apiClientId) corpo.apiClientId = valores.apiClientId;
  if (valores.maxTentativas) corpo.maxTentativas = valores.maxTentativas;
  if (valores.timeoutSegundos) corpo.timeoutSegundos = valores.timeoutSegundos;
  if (valores.status) corpo.status = valores.status;
  if (valores.cabecalhosExtrasTexto && valores.cabecalhosExtrasTexto.trim() !== "") {
    corpo.cabecalhosExtras = JSON.parse(valores.cabecalhosExtrasTexto) as Record<string, unknown>;
  }
  return corpo as Esquema<"WebhookCriar">;
}

interface FormularioWebhookProps {
  webhook: Esquema<"Webhook"> | null;
  salvando: boolean;
  erro?: string | undefined;
  aoSalvar: (valores: FormularioDeWebhook) => void;
  aoCancelar: () => void;
}

/**
 * Formulário de criação/edição de webhook (T14). `status` só é editável em
 * modo de edição — na criação o servidor sempre nasce `ativo` (schema.sql,
 * default da coluna), então expor o seletor ali só confundiria o operador.
 */
export function FormularioWebhook({
  webhook,
  salvando,
  erro,
  aoSalvar,
  aoCancelar,
}: FormularioWebhookProps) {
  const emEdicao = Boolean(webhook);
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<FormularioDeWebhook>({
    defaultValues: valoresIniciais(webhook),
    resolver: resolverZod(ESQUEMA),
  });

  return (
    <form className="flex flex-col gap-4" onSubmit={handleSubmit(aoSalvar)}>
      {erro ? (
        <Alerta variant="erro">
          <AlertaDescricao>{erro}</AlertaDescricao>
        </Alerta>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <CampoTexto
          id="webhook-nome"
          rotulo="Nome"
          obrigatorio
          erro={errors.nome?.message}
          {...register("nome")}
        />
        <CampoTexto
          id="webhook-url"
          rotulo="URL de destino"
          obrigatorio
          dica="Somente HTTPS público — sem faixa privada nem loopback."
          erro={errors.url?.message}
          {...register("url")}
        />
        <CampoTexto
          id="webhook-api-client-id"
          rotulo="Cliente de API (opcional)"
          dica="UUID de um cliente de API já cadastrado. Deixe em branco se não aplicável."
          erro={errors.apiClientId?.message}
          {...register("apiClientId")}
        />
        {emEdicao ? (
          <CampoSelecao
            id="webhook-status"
            rotulo="Situação"
            name="status"
            control={control}
            opcoes={OPCOES_STATUS}
          />
        ) : null}
        <CampoTexto
          id="webhook-max-tentativas"
          rotulo="Máximo de tentativas"
          type="number"
          min={1}
          erro={errors.maxTentativas?.message}
          {...register("maxTentativas")}
        />
        <CampoTexto
          id="webhook-timeout"
          rotulo="Timeout (segundos)"
          type="number"
          min={1}
          erro={errors.timeoutSegundos?.message}
          {...register("timeoutSegundos")}
        />
      </div>

      <CampoListaDeEventos
        name="eventos"
        control={control}
        opcoes={EVENTOS_PUBLICOS}
        erro={errors.eventos?.message}
      />

      <div className="flex flex-col gap-1">
        <Rotulo htmlFor="webhook-cabecalhos-extras">Cabeçalhos extras (opcional, JSON)</Rotulo>
        <AreaDeTexto
          id="webhook-cabecalhos-extras"
          rows={3}
          placeholder='{"X-Origem": "seeg"}'
          aria-invalid={Boolean(errors.cabecalhosExtrasTexto)}
          {...register("cabecalhosExtrasTexto")}
        />
        {errors.cabecalhosExtrasTexto?.message ? (
          <p className="estilo-legenda text-estado-erro-texto">
            {errors.cabecalhosExtrasTexto.message}
          </p>
        ) : null}
      </div>

      <DialogoRodape>
        <Botao type="button" variant="secundaria" onClick={aoCancelar} disabled={salvando}>
          Cancelar
        </Botao>
        <Botao type="submit" disabled={salvando}>
          {salvando ? "Salvando…" : "Salvar"}
        </Botao>
      </DialogoRodape>
    </form>
  );
}
