import { useState } from "react";

/**
 * Estado que funciona tanto **não controlado** (o componente guarda o
 * próprio estado, uso simples) quanto **controlado** (o chamador passa o
 * valor e uma função de mudança, uso quando precisa persistir ou sincronizar
 * externamente — ex.: a F11 vai controlar `preferencias_colunas` da
 * `TabelaDeDados` por fora, sem que este componente saiba de persistência).
 *
 * Padrão clássico do React (mesmo usado por `<input value / defaultValue>`):
 * se `valorControlado` for `undefined`, o hook administra o próprio estado
 * interno; caso contrário, `valorControlado` sempre vence.
 *
 * Nome com o prefixo `use` em inglês (não `usar`) de propósito: é convenção
 * mecânica do React — e do próprio `eslint-plugin-react-hooks`, que só
 * reconhece uma função como Hook por este prefixo — já seguida por
 * `useTema` em `componentes/tema/provedor-de-tema.tsx`.
 */
export function useEstadoControlavel<T>(
  valorControlado: T | undefined,
  valorPadrao: T,
  aoMudar?: (valor: T) => void,
): [T, (valor: T) => void] {
  const [valorInterno, setValorInterno] = useState<T>(valorPadrao);
  const estaControlado = valorControlado !== undefined;
  const valorAtual = estaControlado ? valorControlado : valorInterno;

  function definir(novoValor: T): void {
    if (!estaControlado) {
      setValorInterno(novoValor);
    }
    aoMudar?.(novoValor);
  }

  return [valorAtual, definir];
}
