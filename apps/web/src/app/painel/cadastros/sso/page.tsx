"use client";

import { useEffect } from "react";
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
import { AreaDeTexto } from "@/componentes/ui/textarea";
import { mensagemDeErroApi } from "@/componentes/paineis/cadastros/_shared/erro-amigavel";
import { useAtualizarConfiguracaoSso, useConfiguracaoSso } from "@/ganchos/use-sso-provedores";
import { PortaoDePermissao } from "@/lib/permissoes";

/**
 * Configuração do IdP SAML 2.0 próprio do tenant (T22, F13/A10, RFC-018/
 * ADR-013). Vive sob `/painel/cadastros` — prefixo já existente, sem exigir
 * item de navegação novo na casca do painel (PCF da fase, §5.3).
 *
 * SAML não tem app compartilhado: cada tenant aponta para o próprio Identity
 * Provider corporativo (`entityId`/`ssoUrl`/certificado X.509 — dados
 * PÚBLICOS por natureza, um certificado de assinatura é chave pública, nunca
 * segredo, por isso sem máscara nem `type="password"` nos campos abaixo).
 * `GET/PUT /v1/admin/sso/provedores` é uma superfície ÚNICA para os três
 * provedores (google/entra_id/saml); esta tela só edita os três campos
 * `saml*` e preserva os de OIDC (google/entra_id, tela de A9) inalterados —
 * `useAtualizarConfiguracaoSso` sempre reenvia o corpo completo já carregado
 * pela consulta, atualizando só os campos que este formulário controla.
 */

const ESQUEMA = z.object({
  samlEntityId: z.string().trim().optional(),
  samlSsoUrl: z
    .string()
    .trim()
    .optional()
    .refine((valor) => !valor || /^https?:\/\//.test(valor), {
      message: "Informe uma URL http(s) válida.",
    }),
  samlCertificadoX509: z.string().trim().optional(),
});
type FormularioSaml = z.infer<typeof ESQUEMA>;

/** Mesmo resolver mínimo de zod usado por `pagina-de-login.tsx` (T1, F1) —
 * duplicado aqui de propósito: evita acoplar esta tela a um componente de
 * outra fase só por um resolver de dez linhas. */
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
  return resolver as unknown as Resolver<T>;
}

export default function PaginaDeConfiguracaoSaml() {
  return (
    <PortaoDePermissao
      permissao="admin.configurar"
      fallback={
        <Alerta variant="erro">
          <AlertaTitulo>Sem permissão</AlertaTitulo>
          <AlertaDescricao>
            Configurar SSO exige a permissão administrativa do tenant.
          </AlertaDescricao>
        </Alerta>
      }
    >
      <ConteudoDaPagina />
    </PortaoDePermissao>
  );
}

function ConteudoDaPagina() {
  const consulta = useConfiguracaoSso();
  const atualizar = useAtualizarConfiguracaoSso();

  const formulario = useForm<FormularioSaml>({
    resolver: resolverZod(ESQUEMA),
    defaultValues: { samlEntityId: "", samlSsoUrl: "", samlCertificadoX509: "" },
  });

  useEffect(() => {
    if (!consulta.data) return;
    formulario.reset({
      samlEntityId: consulta.data.samlEntityId ?? "",
      samlSsoUrl: consulta.data.samlSsoUrl ?? "",
      samlCertificadoX509: consulta.data.samlCertificadoX509 ?? "",
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- so re-sincroniza quando o dado da consulta muda.
  }, [consulta.data]);

  const configurado = Boolean(
    consulta.data?.samlEntityId && consulta.data?.samlSsoUrl && consulta.data?.samlCertificadoX509,
  );

  async function salvar(valores: FormularioSaml) {
    await atualizar.mutateAsync({
      // Preserva a configuração de OIDC (google/entra_id) já carregada —
      // esta tela nunca edita esses dois campos. `exactOptionalPropertyTypes`
      // exige omitir a chave (não `undefined`) quando não há valor.
      ...(consulta.data?.googleDominiosPermitidos
        ? { googleDominiosPermitidos: consulta.data.googleDominiosPermitidos }
        : {}),
      entraIdTenantId: consulta.data?.entraIdTenantId ?? null,
      samlEntityId: valores.samlEntityId || null,
      samlSsoUrl: valores.samlSsoUrl || null,
      samlCertificadoX509: valores.samlCertificadoX509 || null,
    });
  }

  if (consulta.isPending) {
    return (
      <div className="flex flex-col gap-4">
        <Esqueleto className="h-8 w-64" />
        <Esqueleto className="h-40 w-full" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="estilo-titulo-pagina text-texto-primario">SSO — SAML 2.0</h1>
        <p className="estilo-corpo mt-1 text-texto-secundario">
          Configure o Identity Provider corporativo próprio desta empresa. Login federado via Google
          Workspace e Microsoft Entra ID é configurado separadamente (app compartilhado).
        </p>
      </header>

      {consulta.isError ? (
        <Alerta variant="erro">
          <AlertaDescricao>{mensagemDeErroApi(consulta.error)}</AlertaDescricao>
        </Alerta>
      ) : null}

      <Cartao>
        <CartaoCabecalho>
          <CartaoTitulo>Identity Provider</CartaoTitulo>
          <CartaoDescricao>
            {configurado
              ? "SSO SAML está configurado para este tenant."
              : "Nenhum IdP configurado ainda — login por SAML fica indisponível até os três campos abaixo serem preenchidos."}{" "}
            Estes três dados são públicos (um certificado X.509 de assinatura é chave pública, nunca
            segredo) e não passam por cifra.
          </CartaoDescricao>
        </CartaoCabecalho>
        <CartaoConteudo>
          <form
            className="flex flex-col gap-4"
            noValidate
            onSubmit={(evento) => {
              void formulario.handleSubmit(salvar)(evento);
            }}
          >
            <div className="flex flex-col gap-1.5">
              <Rotulo htmlFor="samlEntityId">Entity ID do IdP</Rotulo>
              <Entrada
                id="samlEntityId"
                placeholder="https://idp.empresa.com.br/metadata"
                autoComplete="off"
                aria-invalid={Boolean(formulario.formState.errors.samlEntityId)}
                {...formulario.register("samlEntityId")}
              />
              <MensagemDeErro>{formulario.formState.errors.samlEntityId?.message}</MensagemDeErro>
            </div>

            <div className="flex flex-col gap-1.5">
              <Rotulo htmlFor="samlSsoUrl">URL do SSO Service</Rotulo>
              <Entrada
                id="samlSsoUrl"
                placeholder="https://idp.empresa.com.br/sso"
                autoComplete="off"
                aria-invalid={Boolean(formulario.formState.errors.samlSsoUrl)}
                {...formulario.register("samlSsoUrl")}
              />
              <MensagemDeErro>{formulario.formState.errors.samlSsoUrl?.message}</MensagemDeErro>
            </div>

            <div className="flex flex-col gap-1.5">
              <Rotulo htmlFor="samlCertificadoX509">Certificado X.509 (PEM, sem cabeçalho)</Rotulo>
              <AreaDeTexto
                id="samlCertificadoX509"
                rows={8}
                placeholder="MIIDpDCCAoygAwIBAgIJAK..."
                className="font-mono text-xs"
                aria-invalid={Boolean(formulario.formState.errors.samlCertificadoX509)}
                {...formulario.register("samlCertificadoX509")}
              />
              <MensagemDeErro>
                {formulario.formState.errors.samlCertificadoX509?.message}
              </MensagemDeErro>
            </div>

            {atualizar.isError ? (
              <Alerta variant="erro">
                <AlertaDescricao>{mensagemDeErroApi(atualizar.error)}</AlertaDescricao>
              </Alerta>
            ) : null}
            {atualizar.isSuccess ? (
              <Alerta variant="sucesso">
                <AlertaDescricao>Configuração salva.</AlertaDescricao>
              </Alerta>
            ) : null}

            <Botao type="submit" disabled={atualizar.isPending} tamanho="toque">
              {atualizar.isPending ? "Salvando…" : "Salvar"}
            </Botao>
          </form>
        </CartaoConteudo>
      </Cartao>
    </div>
  );
}
