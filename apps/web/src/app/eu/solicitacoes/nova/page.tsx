"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { useForm, type Resolver } from "react-hook-form";
import { z } from "zod";

import { Alerta, AlertaDescricao, AlertaTitulo } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import { Cartao, CartaoConteudo } from "@/componentes/ui/card";
import { Entrada } from "@/componentes/ui/input";
import { Rotulo } from "@/componentes/ui/label";
import { MensagemDeErro } from "@/componentes/ui/mensagem-de-erro";
import {
  Selecao,
  SelecaoConteudo,
  SelecaoGatilho,
  SelecaoItem,
  SelecaoValor,
} from "@/componentes/ui/select";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { AreaDeTexto } from "@/componentes/ui/textarea";
import { useCriarSolicitacao } from "@/ganchos/use-solicitacoes";
import { useSessaoAtual } from "@/ganchos/use-sessao";
import { useTiposSolicitacao } from "@/ganchos/use-tipos-solicitacao";
import { ehErroDaApi, type Esquema } from "@/lib/api";
import { paramsSemUndefined } from "@/lib/formatacao-f8/parametros-de-consulta";

/** Categorias cujo pedido é por INTERVALO (dataInicio/dataFim); as demais usam um único dia (dataReferencia). */
const CATEGORIAS_DE_INTERVALO = new Set(["ferias", "folga", "compensacao", "afastamento"]);

/** `PONTO-INT-005` = handler ainda não implementado (F10 pendente, §2 do PCF) — não é erro comum, é estado próprio. */
function ehIndisponivel(erro: unknown): boolean {
  return ehErroDaApi(erro) && erro.codigo === "PONTO-INT-005";
}

function resolverZod<T extends Record<string, unknown>>(esquema: z.ZodType<T>): Resolver<T> {
  const resolver = async (valores: T) => {
    const resultado = esquema.safeParse(valores);
    if (resultado.success) return { values: resultado.data, errors: {} };
    const erros: Record<string, { type: string; message: string }> = {};
    for (const problema of resultado.error.issues) {
      const campo = problema.path.join(".");
      if (campo && !erros[campo]) erros[campo] = { type: problema.code, message: problema.message };
    }
    return { values: {}, errors: erros };
  };
  // `react-hook-form` espera `FieldErrors<T>` (tipagem específica por campo);
  // nosso resolver mínimo (sem `@hookform/resolvers`, não listado no PCF) usa
  // um mapa mais simples que, na prática, tem exatamente a forma que
  // `formState.errors` precisa em tempo de execução — daí o cast.
  return resolver as unknown as Resolver<T>;
}

const ESQUEMA = z
  .object({
    tipoSolicitacaoId: z.string().min(1, "Selecione um tipo de solicitação."),
    dataReferencia: z.string().optional(),
    dataInicio: z.string().optional(),
    dataFim: z.string().optional(),
    descricao: z.string().min(1, "Descreva o motivo do pedido."),
  })
  .refine((valores) => valores.dataReferencia ?? (valores.dataInicio && valores.dataFim), {
    message: "Informe a data do pedido.",
    path: ["dataReferencia"],
  });
type FormularioNovaSolicitacao = z.infer<typeof ESQUEMA>;

export default function NovaSolicitacao() {
  const tipos = useTiposSolicitacao({ ativo: true });
  const criar = useCriarSolicitacao();
  const { data: sessaoAtual } = useSessaoAtual();
  const colaboradorId = sessaoAtual?.colaboradorId;
  const [protocolo, definirProtocolo] = useState<string | undefined>(undefined);

  const formulario = useForm<FormularioNovaSolicitacao>({
    resolver: resolverZod(ESQUEMA),
    defaultValues: {
      tipoSolicitacaoId: "",
      dataReferencia: "",
      dataInicio: "",
      dataFim: "",
      descricao: "",
    },
  });

  const tipoSelecionadoId = formulario.watch("tipoSolicitacaoId");
  const tipoSelecionado = useMemo(
    () => (tipos.data?.dados ?? []).find((tipo) => tipo.id === tipoSelecionadoId),
    [tipos.data, tipoSelecionadoId],
  );
  const ehIntervalo = tipoSelecionado?.categoria
    ? CATEGORIAS_DE_INTERVALO.has(tipoSelecionado.categoria)
    : false;

  async function aoSubmeter(valores: FormularioNovaSolicitacao) {
    if (!colaboradorId) return;

    const corpo: Esquema<"SolicitacaoCriar"> = {
      tipoSolicitacaoId: valores.tipoSolicitacaoId,
      colaboradorId,
      descricao: valores.descricao,
      ...(ehIntervalo
        ? paramsSemUndefined({
            dataInicio: valores.dataInicio || undefined,
            dataFim: valores.dataFim || undefined,
          })
        : paramsSemUndefined({ dataReferencia: valores.dataReferencia || undefined })),
    };

    try {
      const resultado = await criar.mutateAsync(corpo);
      definirProtocolo(resultado.protocolo);
    } catch (erroCapturado) {
      if (ehIndisponivel(erroCapturado)) {
        // Estado próprio (renderizado abaixo via `criar.isError` + `ehIndisponivel`) —
        // nada mais a fazer aqui, só não deixar a exceção subir sem tratamento.
        return;
      }
      if (ehErroDaApi(erroCapturado)) {
        for (const erroDeCampo of erroCapturado.problema?.errosCampo ?? []) {
          if (erroDeCampo.campo && erroDeCampo.mensagem) {
            formulario.setError(erroDeCampo.campo as keyof FormularioNovaSolicitacao, {
              message: erroDeCampo.mensagem,
            });
          }
        }
      }
    }
  }

  if (protocolo) {
    return (
      <div className="flex flex-col gap-6">
        <h1 className="estilo-titulo-pagina text-texto-primario">Nova solicitação</h1>
        <Alerta variant="sucesso">
          <AlertaTitulo>Solicitação registrada</AlertaTitulo>
          <AlertaDescricao>
            Protocolo {protocolo}. Acompanhe o andamento em Solicitações.
          </AlertaDescricao>
        </Alerta>
        <Botao asChild variant="secundaria" className="w-fit rounded-grande">
          <Link href="/eu/solicitacoes">Voltar para solicitações</Link>
        </Botao>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <Botao
          asChild
          variant="secundaria"
          tamanho="icone-toque"
          className="rounded-pleno shadow-flutuante-chip"
          aria-label="Voltar para solicitações"
        >
          <Link href="/eu/solicitacoes">
            <ArrowLeft className="size-4" />
          </Link>
        </Botao>
        <h1 className="estilo-titulo-pagina text-texto-primario">Nova solicitação</h1>
      </div>

      {criar.isError && ehIndisponivel(criar.error) ? (
        <Alerta variant="info">
          <AlertaTitulo>Disponível em breve</AlertaTitulo>
          <AlertaDescricao>
            O processamento de solicitações ainda está em implementação nesta versão. Você pode
            enviar o pedido normalmente — assim que o fluxo de aprovação for lançado, ele será
            processado automaticamente.
          </AlertaDescricao>
        </Alerta>
      ) : null}

      {criar.isError && !ehIndisponivel(criar.error) ? (
        <Alerta variant="erro">
          <AlertaTitulo>Não foi possível enviar sua solicitação</AlertaTitulo>
          <AlertaDescricao>
            {ehErroDaApi(criar.error)
              ? criar.error.problema?.title
              : "Tente novamente em instantes."}
          </AlertaDescricao>
        </Alerta>
      ) : null}

      <Cartao className="rounded-pronunciado shadow-flutuante-alta">
        <CartaoConteudo>
          {tipos.isPending ? (
            <Esqueleto className="h-48 w-full" />
          ) : (
            <form
              className="flex flex-col gap-4"
              noValidate
              onSubmit={(evento) => {
                void formulario.handleSubmit(aoSubmeter)(evento);
              }}
            >
              <div className="flex flex-col gap-1.5">
                <Rotulo htmlFor="tipoSolicitacaoId">Tipo de solicitação</Rotulo>
                <Selecao
                  value={formulario.watch("tipoSolicitacaoId")}
                  onValueChange={(valor) => {
                    formulario.setValue("tipoSolicitacaoId", valor, { shouldValidate: true });
                  }}
                >
                  <SelecaoGatilho id="tipoSolicitacaoId" aria-label="Tipo de solicitação">
                    <SelecaoValor placeholder="Selecione…" />
                  </SelecaoGatilho>
                  <SelecaoConteudo>
                    {(tipos.data?.dados ?? []).map((tipo) => (
                      <SelecaoItem key={tipo.id} value={tipo.id ?? ""}>
                        {tipo.nome}
                      </SelecaoItem>
                    ))}
                  </SelecaoConteudo>
                </Selecao>
                <MensagemDeErro>
                  {formulario.formState.errors.tipoSolicitacaoId?.message}
                </MensagemDeErro>
              </div>

              {tipoSelecionado?.exigeAnexo ? (
                <Alerta variant="atencao">
                  <AlertaTitulo>Anexo não é suportado nesta versão</AlertaTitulo>
                  <AlertaDescricao>
                    Este tipo de pedido normalmente exige um documento anexado. Por enquanto,
                    prossiga só com a justificativa textual — o anexo poderá ser adicionado depois
                    de outra forma.
                  </AlertaDescricao>
                </Alerta>
              ) : null}

              {ehIntervalo ? (
                <div className="grid grid-cols-2 gap-4">
                  <div className="flex flex-col gap-1.5">
                    <Rotulo htmlFor="dataInicio">Data de início</Rotulo>
                    <Entrada id="dataInicio" type="date" {...formulario.register("dataInicio")} />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Rotulo htmlFor="dataFim">Data de fim</Rotulo>
                    <Entrada id="dataFim" type="date" {...formulario.register("dataFim")} />
                  </div>
                </div>
              ) : (
                <div className="flex flex-col gap-1.5">
                  <Rotulo htmlFor="dataReferencia">Data de referência</Rotulo>
                  <Entrada
                    id="dataReferencia"
                    type="date"
                    {...formulario.register("dataReferencia")}
                  />
                </div>
              )}
              <MensagemDeErro>{formulario.formState.errors.dataReferencia?.message}</MensagemDeErro>

              <div className="flex flex-col gap-1.5">
                <Rotulo htmlFor="descricao">Justificativa</Rotulo>
                <AreaDeTexto
                  id="descricao"
                  aria-invalid={Boolean(formulario.formState.errors.descricao)}
                  {...formulario.register("descricao")}
                />
                <MensagemDeErro>{formulario.formState.errors.descricao?.message}</MensagemDeErro>
              </div>

              <Botao
                type="submit"
                tamanho="toque"
                className="rounded-grande"
                disabled={criar.isPending}
              >
                {criar.isPending ? "Enviando…" : "Enviar solicitação"}
              </Botao>
            </form>
          )}
        </CartaoConteudo>
      </Cartao>
    </div>
  );
}
