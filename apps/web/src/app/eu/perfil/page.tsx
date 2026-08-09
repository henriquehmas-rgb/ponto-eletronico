"use client";

import { useRouter } from "next/navigation";

import { Selo } from "@/componentes/ui/badge";
import { Alerta, AlertaDescricao, AlertaTitulo } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import { Cartao, CartaoCabecalho, CartaoConteudo, CartaoTitulo } from "@/componentes/ui/card";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { AlternadorDeTema } from "@/componentes/tema/alternador-de-tema";
import {
  useColaborador,
  useDispositivos,
  useRevogarSessao,
  useSessoesAtivas,
} from "@/ganchos/use-perfil";
import { ehErroDaApi, type Esquema } from "@/lib/api";
import { formatarDataHora } from "@/lib/formatacao";
import { useSessao } from "@/lib/sessao";

/** Iniciais (até duas letras) a partir do nome — só para o avatar, decorativo. */
function iniciaisDoNome(nome: string | undefined): string {
  if (!nome) return "—";
  const partes = nome.trim().split(/\s+/).filter(Boolean);
  const primeira = partes[0]?.[0] ?? "";
  const ultima = partes.length > 1 ? (partes[partes.length - 1]?.[0] ?? "") : "";
  return `${primeira}${ultima}`.toUpperCase() || "—";
}

export default function PerfilDoColaborador() {
  const sessao = useSessao();
  const router = useRouter();
  const colaborador = useColaborador();
  const dispositivos = useDispositivos();
  const sessoes = useSessoesAtivas();
  const revogar = useRevogarSessao();

  const nomeExibido = colaborador.data?.nomeSocial || colaborador.data?.nomeCompleto;

  async function aoRevogar(sessaoListada: Esquema<"Sessao">) {
    if (!sessaoListada.id) return;
    await revogar.mutateAsync(sessaoListada.id);
    if (sessaoListada.atual) {
      // Revogar a PRÓPRIA sessão desloga: limpa o estado local (mesmo mecanismo de
      // logout, T1) e volta para a tela de entrada — não há mais nada a mostrar aqui.
      await sessao.sair();
      router.replace("/");
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="estilo-titulo-pagina text-texto-primario">Perfil</h1>

      <div className="flex items-center gap-4">
        {colaborador.isPending ? (
          <Esqueleto className="size-14 shrink-0 rounded-pleno" />
        ) : (
          <span className="flex size-14 shrink-0 items-center justify-center rounded-pleno bg-acao-sutil-fundo text-xl font-semibold text-acao-sutil-texto">
            {iniciaisDoNome(nomeExibido)}
          </span>
        )}
        <div className="min-w-0">
          <p className="estilo-titulo-secao truncate text-texto-primario">
            {colaborador.isPending ? "…" : (nomeExibido ?? "—")}
          </p>
          <p className="estilo-legenda text-texto-terciario">
            {colaborador.data?.matricula ? `Matrícula ${colaborador.data.matricula}` : "—"}
          </p>
        </div>
      </div>

      <Cartao className="rounded-suave shadow-flutuante-cartao">
        <CartaoCabecalho>
          <CartaoTitulo>Dados cadastrais</CartaoTitulo>
        </CartaoCabecalho>
        <CartaoConteudo>
          {colaborador.isPending ? (
            <Esqueleto className="h-24 w-full" />
          ) : colaborador.isError ? (
            <Alerta variant="erro">
              <AlertaTitulo>Não foi possível carregar seus dados</AlertaTitulo>
              <AlertaDescricao>
                {ehErroDaApi(colaborador.error)
                  ? colaborador.error.problema?.title
                  : "Tente novamente em instantes."}
              </AlertaDescricao>
            </Alerta>
          ) : colaborador.data ? (
            <dl className="grid gap-3 sm:grid-cols-2">
              <div>
                <dt className="estilo-legenda uppercase text-texto-terciario">Nome</dt>
                <dd className="estilo-corpo text-texto-primario">
                  {colaborador.data.nomeSocial || colaborador.data.nomeCompleto || "—"}
                </dd>
              </div>
              <div>
                <dt className="estilo-legenda uppercase text-texto-terciario">Matrícula</dt>
                <dd className="estilo-corpo text-texto-primario">
                  {colaborador.data.matricula ?? "—"}
                </dd>
              </div>
              <div>
                <dt className="estilo-legenda uppercase text-texto-terciario">E-mail</dt>
                <dd className="estilo-corpo text-texto-primario">
                  {colaborador.data.email ?? "—"}
                </dd>
              </div>
              <div>
                <dt className="estilo-legenda uppercase text-texto-terciario">Situação</dt>
                <dd className="estilo-corpo text-texto-primario">
                  {colaborador.data.status ?? "—"}
                </dd>
              </div>
            </dl>
          ) : null}
        </CartaoConteudo>
      </Cartao>

      <Cartao className="rounded-suave shadow-flutuante-cartao">
        <CartaoCabecalho>
          <CartaoTitulo>Dispositivos vinculados</CartaoTitulo>
        </CartaoCabecalho>
        <CartaoConteudo>
          {dispositivos.isPending ? (
            <Esqueleto className="h-24 w-full" />
          ) : dispositivos.isError ? (
            <Alerta variant="erro">
              <AlertaTitulo>Não foi possível carregar seus dispositivos</AlertaTitulo>
              <AlertaDescricao>
                {ehErroDaApi(dispositivos.error)
                  ? dispositivos.error.problema?.title
                  : "Tente novamente em instantes."}
              </AlertaDescricao>
            </Alerta>
          ) : (dispositivos.data?.dados ?? []).length === 0 ? (
            <p className="estilo-corpo text-texto-secundario">Nenhum dispositivo vinculado.</p>
          ) : (
            <ul className="flex flex-col divide-y divide-borda-sutil">
              {(dispositivos.data?.dados ?? []).map((dispositivo) => (
                <li key={dispositivo.id} className="flex items-center justify-between gap-3 py-2">
                  <div>
                    <p className="estilo-corpo text-texto-primario">
                      {dispositivo.nome ?? dispositivo.identificador ?? "Dispositivo"}
                    </p>
                    <p className="estilo-legenda text-texto-terciario">
                      {dispositivo.plataforma ?? "—"} · último acesso{" "}
                      {dispositivo.ultimoAcessoEm
                        ? formatarDataHora(dispositivo.ultimoAcessoEm)
                        : "—"}
                    </p>
                  </div>
                  <Selo variant={dispositivo.status === "ativo" ? "sucesso" : "neutro"}>
                    {dispositivo.status ?? "—"}
                  </Selo>
                </li>
              ))}
            </ul>
          )}
        </CartaoConteudo>
      </Cartao>

      <Cartao className="rounded-suave shadow-flutuante-cartao">
        <CartaoCabecalho>
          <CartaoTitulo>Sessões ativas</CartaoTitulo>
        </CartaoCabecalho>
        <CartaoConteudo>
          {sessoes.isPending ? (
            <Esqueleto className="h-24 w-full" />
          ) : sessoes.isError ? (
            <Alerta variant="erro">
              <AlertaTitulo>Não foi possível carregar suas sessões</AlertaTitulo>
              <AlertaDescricao>
                {ehErroDaApi(sessoes.error)
                  ? sessoes.error.problema?.title
                  : "Tente novamente em instantes."}
              </AlertaDescricao>
            </Alerta>
          ) : (
            <ul className="flex flex-col divide-y divide-borda-sutil">
              {(sessoes.data?.dados ?? []).map((sessaoListada) => (
                <li key={sessaoListada.id} className="flex items-center justify-between gap-3 py-2">
                  <div>
                    <p className="estilo-corpo text-texto-primario">
                      {sessaoListada.canal ?? "—"}{" "}
                      {sessaoListada.atual ? (
                        <span className="estilo-legenda text-acao-sutil-texto">(esta sessão)</span>
                      ) : null}
                    </p>
                    <p className="estilo-legenda text-texto-terciario">
                      {sessaoListada.ip ?? "IP desconhecido"} · última atividade{" "}
                      {sessaoListada.ultimaAtividadeEm
                        ? formatarDataHora(sessaoListada.ultimaAtividadeEm)
                        : "—"}
                    </p>
                  </div>
                  <Botao
                    type="button"
                    variant="destrutiva"
                    tamanho="compacto"
                    disabled={revogar.isPending}
                    onClick={() => {
                      void aoRevogar(sessaoListada);
                    }}
                  >
                    Revogar
                  </Botao>
                </li>
              ))}
            </ul>
          )}
        </CartaoConteudo>
      </Cartao>

      <Cartao className="rounded-suave shadow-flutuante-cartao">
        <CartaoCabecalho>
          <CartaoTitulo>Preferências</CartaoTitulo>
        </CartaoCabecalho>
        <CartaoConteudo>
          <div className="flex items-center justify-between gap-3 py-2">
            <span className="estilo-corpo font-semibold text-texto-primario">
              Tema da interface
            </span>
            <AlternadorDeTema />
          </div>
        </CartaoConteudo>
      </Cartao>
    </div>
  );
}
