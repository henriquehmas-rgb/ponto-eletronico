"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useForm, type Resolver } from "react-hook-form";
import { z } from "zod";

import { Alerta, AlertaDescricao, AlertaTitulo } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import {
  Cartao,
  CartaoCabecalho,
  CartaoConteudo,
  CartaoDescricao,
  CartaoTitulo,
} from "@/componentes/ui/card";
import { Entrada } from "@/componentes/ui/input";
import { Rotulo } from "@/componentes/ui/label";
import { MensagemDeErro } from "@/componentes/ui/mensagem-de-erro";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { api, ehErroDaApi } from "@/lib/api";
import { ProvedorDeSessao, useSessao, validarRetornoSeguro } from "@/lib/sessao";

/**
 * Dicionário PROVISÓRIO de mensagens de erro (T1). `src/lib/seguranca/
 * dicionario-de-erros.ts` (T13, A3) é o dicionário definitivo, com cobertura
 * de todos os códigos citados na §3 do PCF — até ele existir, esta tela usa um
 * mapa mínimo e cai em `problema.title` como texto temporário para qualquer
 * código fora dele (nunca quebra por um código não mapeado).
 */
function mensagemDeErroDeLogin(erro: unknown): string {
  if (ehErroDaApi(erro)) {
    const mapaProvisorio: Record<string, string> = {
      "PONTO-AUTH-001": "E-mail ou senha incorretos.",
      "PONTO-AUTH-006": "Sessão encerrada. Entre novamente.",
      "PONTO-AUTH-010": "Usuário bloqueado ou inativo. Procure o RH.",
      "PONTO-AUTH-009": "Segundo fator inválido ou expirado.",
      "PONTO-TEN-001": "Tenant não encontrado. Confira o identificador informado.",
      "PONTO-RATE-001": "Muitas tentativas. Aguarde um instante e tente novamente.",
    };
    return (
      mapaProvisorio[erro.codigo ?? ""] ??
      erro.problema?.title ??
      "Não foi possível entrar. Tente novamente."
    );
  }
  return "Não foi possível entrar. Tente novamente.";
}

/** Resolver mínimo de zod para `react-hook-form`, sem depender de `@hookform/resolvers` (não listado no PCF). */
function resolverZod<T extends Record<string, unknown>>(esquema: z.ZodType<T>): Resolver<T> {
  const resolver = async (valores: T) => {
    const resultado = esquema.safeParse(valores);
    if (resultado.success) {
      return { values: resultado.data, errors: {} };
    }
    const erros: Record<string, { type: string; message: string }> = {};
    for (const problema of resultado.error.issues) {
      const campo = problema.path.join(".");
      if (campo && !erros[campo]) {
        erros[campo] = { type: problema.code, message: problema.message };
      }
    }
    return { values: {}, errors: erros };
  };
  // Ver nota equivalente em `src/app/eu/solicitacoes/nova/page.tsx`: o mapa de
  // erros deste resolver mínimo tem, em tempo de execução, a forma que
  // `formState.errors` espera — o cast evita depender de `FieldErrors<T>`
  // exato, que exigiria reimplementar boa parte da tipagem interna da lib.
  return resolver as unknown as Resolver<T>;
}

const ESQUEMA_CREDENCIAIS = z.object({
  email: z.string().min(1, "Informe o e-mail.").email("E-mail inválido."),
  senha: z.string().min(1, "Informe a senha."),
  tenant: z.string().optional(),
});
type FormularioCredenciais = z.infer<typeof ESQUEMA_CREDENCIAIS>;

const ESQUEMA_MFA = z.object({
  codigo: z.string().min(6, "Informe o código de 6 dígitos.").max(12, "Código inválido."),
});
type FormularioMfa = z.infer<typeof ESQUEMA_MFA>;

export function PaginaDeLogin() {
  return (
    <ProvedorDeSessao>
      <ConteudoDeLogin />
    </ProvedorDeSessao>
  );
}

function ConteudoDeLogin() {
  const sessao = useSessao();
  const router = useRouter();
  const parametrosDeBusca = useSearchParams();

  const retornoValidado = useMemo(
    () => validarRetornoSeguro(parametrosDeBusca.get("returnTo")) ?? "/eu",
    [parametrosDeBusca],
  );

  useEffect(() => {
    if (sessao.autenticado && !sessao.carregando) {
      router.replace(retornoValidado);
    }
  }, [sessao.autenticado, sessao.carregando, retornoValidado, router]);

  const consultaTenant = useQuery({
    queryKey: ["tenant-atual"],
    queryFn: async () => {
      const resultado = await api.GET("/v1/tenants/atual");
      if (resultado.error) throw resultado.error;
      return resultado.data;
    },
    retry: false,
    staleTime: Number.POSITIVE_INFINITY,
  });

  const [etapa, definirEtapa] = useState<"credenciais" | "mfa">("credenciais");
  const [erro, definirErro] = useState<string | null>(null);
  const [enviando, definirEnviando] = useState(false);

  const formularioCredenciais = useForm<FormularioCredenciais>({
    resolver: resolverZod(ESQUEMA_CREDENCIAIS),
    defaultValues: { email: "", senha: "", tenant: "" },
  });
  const formularioMfa = useForm<FormularioMfa>({
    resolver: resolverZod(ESQUEMA_MFA),
    defaultValues: { codigo: "" },
  });

  const tenantResolvidoPorSubdominio =
    Boolean(consultaTenant.data?.slug) && !consultaTenant.isError;

  async function aoSubmeterCredenciais(valores: FormularioCredenciais) {
    definirErro(null);
    definirEnviando(true);
    try {
      const tenant = tenantResolvidoPorSubdominio
        ? consultaTenant.data?.slug
        : valores.tenant || undefined;
      const resultado = await sessao.entrar({
        email: valores.email,
        senha: valores.senha,
        ...(tenant ? { tenant } : {}),
      });
      if (resultado.mfaRequerido) {
        definirEtapa("mfa");
      }
      // Quando mfaRequerido é falso, o useEffect acima navega assim que
      // `sessao.autenticado` vira verdadeiro — nada mais a fazer aqui.
    } catch (erroCapturado) {
      definirErro(mensagemDeErroDeLogin(erroCapturado));
    } finally {
      definirEnviando(false);
    }
  }

  async function aoSubmeterMfa(valores: FormularioMfa) {
    definirErro(null);
    definirEnviando(true);
    try {
      await sessao.verificarSegundoFator(valores.codigo);
    } catch (erroCapturado) {
      definirErro(mensagemDeErroDeLogin(erroCapturado));
    } finally {
      definirEnviando(false);
    }
  }

  if (sessao.carregando) {
    return (
      <section className="mx-auto flex w-full max-w-sm flex-col gap-4 px-6 py-16">
        <Esqueleto className="h-8 w-40" />
        <Esqueleto className="h-10 w-full" />
        <Esqueleto className="h-10 w-full" />
      </section>
    );
  }

  if (sessao.autenticado) {
    // A navegação já foi disparada pelo useEffect — evita um flash do formulário.
    return null;
  }

  return (
    <section className="mx-auto flex w-full max-w-sm flex-col gap-6 px-6 py-16">
      <div>
        <p className="estilo-rotulo uppercase text-texto-terciario">SEEG Ponto</p>
        <h1 className="estilo-titulo-pagina mt-2 text-texto-primario">Entrar</h1>
        <p className="estilo-corpo mt-1 text-texto-secundario">
          {tenantResolvidoPorSubdominio
            ? (consultaTenant.data?.nomeExibicao ?? consultaTenant.data?.slug)
            : "Prova justa da jornada."}
        </p>
      </div>

      {erro ? (
        <Alerta variant="erro">
          <AlertaTitulo>Não foi possível entrar</AlertaTitulo>
          <AlertaDescricao>{erro}</AlertaDescricao>
        </Alerta>
      ) : null}

      {etapa === "credenciais" ? (
        <Cartao>
          <CartaoCabecalho>
            <CartaoTitulo>Credenciais de acesso</CartaoTitulo>
            <CartaoDescricao>Use o e-mail e a senha cadastrados pela sua empresa.</CartaoDescricao>
          </CartaoCabecalho>
          <CartaoConteudo>
            <form
              className="flex flex-col gap-4"
              noValidate
              onSubmit={(evento) => {
                void formularioCredenciais.handleSubmit(aoSubmeterCredenciais)(evento);
              }}
            >
              <div className="flex flex-col gap-1.5">
                <Rotulo htmlFor="email">E-mail</Rotulo>
                <Entrada
                  id="email"
                  type="email"
                  autoComplete="username"
                  aria-invalid={Boolean(formularioCredenciais.formState.errors.email)}
                  {...formularioCredenciais.register("email")}
                />
                <MensagemDeErro>
                  {formularioCredenciais.formState.errors.email?.message}
                </MensagemDeErro>
              </div>

              <div className="flex flex-col gap-1.5">
                <Rotulo htmlFor="senha">Senha</Rotulo>
                <Entrada
                  id="senha"
                  type="password"
                  autoComplete="current-password"
                  aria-invalid={Boolean(formularioCredenciais.formState.errors.senha)}
                  {...formularioCredenciais.register("senha")}
                />
                <MensagemDeErro>
                  {formularioCredenciais.formState.errors.senha?.message}
                </MensagemDeErro>
              </div>

              {!tenantResolvidoPorSubdominio ? (
                <div className="flex flex-col gap-1.5">
                  <Rotulo htmlFor="tenant">Identificador da empresa (tenant)</Rotulo>
                  <Entrada
                    id="tenant"
                    autoComplete="off"
                    placeholder="ex.: acme"
                    aria-invalid={Boolean(formularioCredenciais.formState.errors.tenant)}
                    {...formularioCredenciais.register("tenant")}
                  />
                  <MensagemDeErro>
                    {formularioCredenciais.formState.errors.tenant?.message}
                  </MensagemDeErro>
                </div>
              ) : null}

              <Botao type="submit" disabled={enviando} tamanho="toque">
                {enviando ? "Entrando…" : "Entrar"}
              </Botao>
            </form>
          </CartaoConteudo>
        </Cartao>
      ) : (
        <Cartao>
          <CartaoCabecalho>
            <CartaoTitulo>Confirme o segundo fator</CartaoTitulo>
            <CartaoDescricao>Informe o código do seu aplicativo autenticador.</CartaoDescricao>
          </CartaoCabecalho>
          <CartaoConteudo>
            <form
              className="flex flex-col gap-4"
              noValidate
              onSubmit={(evento) => {
                void formularioMfa.handleSubmit(aoSubmeterMfa)(evento);
              }}
            >
              <div className="flex flex-col gap-1.5">
                <Rotulo htmlFor="codigo">Código</Rotulo>
                <Entrada
                  id="codigo"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  aria-invalid={Boolean(formularioMfa.formState.errors.codigo)}
                  {...formularioMfa.register("codigo")}
                />
                <MensagemDeErro>{formularioMfa.formState.errors.codigo?.message}</MensagemDeErro>
              </div>

              <Botao type="submit" disabled={enviando} tamanho="toque">
                {enviando ? "Verificando…" : "Confirmar"}
              </Botao>
              <Botao
                type="button"
                variant="sutil"
                onClick={() => {
                  definirEtapa("credenciais");
                  definirErro(null);
                }}
              >
                Voltar
              </Botao>
            </form>
          </CartaoConteudo>
        </Cartao>
      )}
    </section>
  );
}
