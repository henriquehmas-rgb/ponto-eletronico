import { ehErroDaApi } from "@/lib/api";

/**
 * Mensagem amigável a partir de um erro de mutação/consulta desta área.
 *
 * Regra do contrato (`src/lib/api/erros.ts`, releia o comentário da classe
 * `ErroDaApi`): a mensagem exibida deriva de `codigo` (estável, catalogado em
 * `packages/contracts/errors.yaml`), NUNCA de `title`/`detail` (podem mudar
 * sem quebrar contrato). Por isso este helper mapeia o PREFIXO da categoria
 * do código para uma frase em português, e nunca lê `title`/`detail`.
 */
export function mensagemDeErroApi(erro: unknown): string {
  if (!ehErroDaApi(erro)) {
    return "Não foi possível concluir a operação. Tente novamente em instantes.";
  }
  const codigo = erro.codigo;
  if (!codigo) return `Não foi possível concluir a operação (HTTP ${erro.status}).`;

  if (codigo.startsWith("PONTO-VAL-")) {
    return "Dados inválidos. Confira os campos destacados e tente novamente.";
  }
  if (codigo.startsWith("PONTO-CONF-")) {
    return "Conflito: o registro já existe, foi alterado por outra pessoa ou está em uso.";
  }
  if (codigo.startsWith("PONTO-PERM-")) {
    return "Você não tem permissão para executar esta ação.";
  }
  if (codigo.startsWith("PONTO-AUTH-")) {
    return "Sessão expirada ou inválida. Entre novamente.";
  }
  if (codigo.startsWith("PONTO-REC-")) {
    return "Registro não encontrado — pode ter sido removido por outra pessoa.";
  }
  if (codigo.startsWith("PONTO-TEN-")) {
    return "Não foi possível identificar o tenant desta requisição.";
  }
  if (codigo.startsWith("PONTO-RATE-")) {
    return "Muitas requisições em pouco tempo. Aguarde um instante e tente novamente.";
  }
  if (codigo.startsWith("PONTO-IDEM-")) {
    return "Requisição duplicada detectada. Recarregue a tela e tente novamente.";
  }
  return `Não foi possível concluir a operação (código ${codigo}).`;
}
