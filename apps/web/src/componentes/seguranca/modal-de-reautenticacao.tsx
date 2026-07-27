"use client";

import { useState, type FormEvent } from "react";

import { Botao } from "@/componentes/ui/button";
import {
  Dialogo,
  DialogoCabecalho,
  DialogoConteudo,
  DialogoDescricao,
  DialogoRodape,
  DialogoTitulo,
} from "@/componentes/ui/dialog";
import { Entrada } from "@/componentes/ui/input";
import { Rotulo } from "@/componentes/ui/label";
import { MensagemDeErro } from "@/componentes/ui/mensagem-de-erro";
import { useReautenticacao } from "@/ganchos/use-reautenticacao";

/**
 * Modal de reautenticação — T12 do PCF F08.
 *
 * Consome o `Dialogo` da F9a (foco preso e retorno de foco ao gatilho são
 * comportamento nativo do Radix — este componente não reimplementa nada
 * disso, só estiliza o conteúdo). Abre sozinho quando `comAcessoControlado`
 * (T13) intercepta `PONTO-AUTH-011`, via `useReautenticacao`.
 *
 * Monte este componente uma única vez, alto na árvore de `/eu` (dentro do
 * layout autenticado, T1 de A1) — ele não sabe QUEM pediu a reautenticação,
 * só que alguém pediu.
 */
export function ModalDeReautenticacao() {
  const { aberto, mfaNecessario, carregando, erro, confirmar, cancelar } = useReautenticacao();
  const [senha, setSenha] = useState("");
  const [codigoMfa, setCodigoMfa] = useState("");

  function limparCampos(): void {
    setSenha("");
    setCodigoMfa("");
  }

  function aoMudarAberto(novoAberto: boolean): void {
    if (novoAberto) return;
    cancelar();
    limparCampos();
  }

  function aoSubmeter(evento: FormEvent<HTMLFormElement>): void {
    evento.preventDefault();
    void confirmar({ senha, ...(mfaNecessario && codigoMfa ? { codigoMfa } : {}) });
  }

  return (
    <Dialogo open={aberto} onOpenChange={aoMudarAberto}>
      <DialogoConteudo>
        <DialogoCabecalho>
          <DialogoTitulo>Confirme sua senha</DialogoTitulo>
          <DialogoDescricao>
            Por segurança, confirme sua identidade antes de continuar com esta ação.
          </DialogoDescricao>
        </DialogoCabecalho>
        <form onSubmit={aoSubmeter} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Rotulo htmlFor="reautenticacao-senha">Senha</Rotulo>
            <Entrada
              id="reautenticacao-senha"
              name="senha"
              type="password"
              autoComplete="current-password"
              autoFocus
              required
              value={senha}
              aria-invalid={Boolean(erro)}
              onChange={(evento) => setSenha(evento.target.value)}
            />
          </div>
          {mfaNecessario && (
            <div className="flex flex-col gap-2">
              <Rotulo htmlFor="reautenticacao-codigo-mfa">Código de verificação</Rotulo>
              <Entrada
                id="reautenticacao-codigo-mfa"
                name="codigoMfa"
                inputMode="numeric"
                autoComplete="one-time-code"
                required
                value={codigoMfa}
                onChange={(evento) => setCodigoMfa(evento.target.value)}
              />
            </div>
          )}
          <MensagemDeErro>{erro}</MensagemDeErro>
          <DialogoRodape>
            <Botao type="button" variant="secundaria" onClick={() => aoMudarAberto(false)}>
              Cancelar
            </Botao>
            <Botao type="submit" disabled={carregando}>
              {carregando ? "Confirmando…" : "Confirmar"}
            </Botao>
          </DialogoRodape>
        </form>
      </DialogoConteudo>
    </Dialogo>
  );
}
