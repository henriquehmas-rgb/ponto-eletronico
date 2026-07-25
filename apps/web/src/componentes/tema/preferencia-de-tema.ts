/**
 * Vocabulario da troca de tema, compartilhado entre o script inline (que roda
 * antes da primeira pintura) e o provedor React. Os dois PRECISAM concordar na
 * chave do armazenamento e no nome do atributo, senao o tema pisca.
 */

export const CHAVE_ARMAZENAMENTO = "ponto.tema";
export const ATRIBUTO_TEMA = "data-tema";

/** O que o usuario escolheu. `sistema` = seguir o sistema operacional. */
export type PreferenciaDeTema = "claro" | "escuro" | "sistema";

/** O que efetivamente esta pintado na tela. */
export type TemaResolvido = "claro" | "escuro";

export const PREFERENCIAS: readonly PreferenciaDeTema[] = ["claro", "escuro", "sistema"];

export const ROTULO_DA_PREFERENCIA: Record<PreferenciaDeTema, string> = {
  claro: "Tema claro",
  escuro: "Tema escuro",
  sistema: "Seguir o sistema",
};

export function ehPreferencia(valor: unknown): valor is PreferenciaDeTema {
  return valor === "claro" || valor === "escuro" || valor === "sistema";
}

/**
 * Script executado de forma sincrona no `<head>`, ANTES do primeiro paint.
 *
 * Ele existe por um motivo so: sem ele, o navegador pinta o tema claro, o React
 * hidrata e troca para o escuro — o "flash" branco. Como e sincrono e esta
 * antes de qualquer conteudo, o atributo ja esta no `<html>` quando o primeiro
 * pixel aparece.
 *
 * Escrito como string (e nao como funcao serializada) porque precisa ser ES5
 * legivel, minusculo e sem dependencia nenhuma.
 */
export const SCRIPT_ANTI_FLASH = `(function(){try{
var d=document.documentElement;
var p=localStorage.getItem(${JSON.stringify(CHAVE_ARMAZENAMENTO)});
var s=window.matchMedia("(prefers-color-scheme: dark)").matches?"escuro":"claro";
var t=(p==="claro"||p==="escuro")?p:s;
d.setAttribute(${JSON.stringify(ATRIBUTO_TEMA)},t);
d.style.colorScheme=(t==="escuro")?"dark":"light";
}catch(e){}})();`
  .replace(/\n/g, "")
  .trim();
