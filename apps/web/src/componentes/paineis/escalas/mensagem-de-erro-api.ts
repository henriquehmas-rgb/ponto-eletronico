import { ehErroDaApi } from "@/lib/api";

/**
 * Mensagem amigável a partir de um erro de consulta/mutação desta seção
 * (turnos, escalas, atribuições, resolução de jornada).
 *
 * Regra do contrato (`packages/contracts/openapi.yaml`, "Convenções", e
 * `apps/web/src/lib/api/erros.ts`): a mensagem exibida deriva do `codigo`
 * estável (`packages/contracts/errors.yaml`), NUNCA de `title`/`detail`, que
 * podem mudar sem quebrar contrato. Cobre os códigos de `x-erros` das
 * operações que esta seção chama (`escalas`, `turnos`, `jornadas.resolver`).
 * Mesmo padrão independentemente adotado por `paineis/apuracao/utilitarios.ts`
 * (A3) e `paineis/cadastros/_shared/erro-amigavel.ts` (A2) — cópia local, não
 * import cruzado, porque nenhum dos dois é ownership desta seção.
 */
const MENSAGEM_POR_CODIGO: Record<string, string> = {
  "PONTO-AUTH-002": "Sessão ausente. Entre novamente.",
  "PONTO-AUTH-003": "Sessão expirada. Entre novamente.",
  "PONTO-AUTH-004": "Sessão inválida. Entre novamente.",
  "PONTO-AUTH-006": "Sessão encerrada ou revogada. Entre novamente.",
  "PONTO-AUTH-013": "Credencial de integração inválida ou revogada.",
  "PONTO-PERM-001": "Você não tem permissão para esta ação.",
  "PONTO-PERM-002": "Este registro está fora do seu alcance hierárquico.",
  "PONTO-PERM-004": "Seu perfil tem acesso somente leitura a este recurso.",
  "PONTO-TEN-002": "Sessão de outro tenant. Entre novamente.",
  "PONTO-TEN-003": "Tenant suspenso ou cancelado.",
  "PONTO-TEN-004": "Acesso entre tenants negado.",
  "PONTO-VAL-001": "Dados inválidos no formulário. Revise os campos.",
  "PONTO-VAL-005": "Parâmetro de busca inválido.",
  "PONTO-VAL-006": "A ordenação mudou durante a navegação. Volte ao início da lista.",
  "PONTO-VAL-010": "Data fora da vigência permitida.",
  "PONTO-VAL-011": "Requisição incompleta. Tente novamente.",
  "PONTO-REC-001": "Registro não encontrado — pode ter sido removido nesse meio-tempo.",
  "PONTO-RATE-001": "Muitas requisições em sequência. Aguarde um instante e tente novamente.",
  "PONTO-IDEM-001": "Falha ao identificar a requisição. Tente novamente.",
  "PONTO-IDEM-002": "Essa ação já foi enviada com dados diferentes. Recarregue e tente de novo.",
  "PONTO-IDEM-003": "Uma requisição igual a esta ainda está em processamento.",
  "PONTO-INT-001": "Erro interno. Tente novamente em instantes.",
  "PONTO-INT-003": "Serviço temporariamente indisponível. Tente novamente.",
  "PONTO-INT-005": "Esta operação ainda não está disponível.",
  "PONTO-CONF-001": "Já existe um registro com este código.",
  "PONTO-CONF-002": "Este registro foi alterado por outra pessoa. Recarregue e tente novamente.",
  "PONTO-CONF-003": "Esta alteração não é permitida no estado atual do registro.",
  "PONTO-CONF-004": "Não é possível excluir: há atribuições vigentes usando este registro.",
  "PONTO-PER-001": "Sobreposição de vigência para este vínculo. Ajuste as datas e tente novamente.",
  "PONTO-APUR-002":
    "Não há jornada nem escala resolvida para o vínculo nesta data — atribua uma escala antes de consultar.",
};

/** Deriva a mensagem exibível de um erro capturado de uma chamada à API. */
export function mensagemDeErroApi(erro: unknown): string {
  if (!ehErroDaApi(erro)) return "Não foi possível concluir a operação. Tente novamente.";
  // `noUncheckedIndexedAccess` (tsconfig, strict): o acesso indexado devolve
  // `string | undefined`, mesmo com a checagem de `erro.codigo` acima — daí a
  // variável intermediária, em vez de indexar duas vezes.
  const mensagem = erro.codigo ? MENSAGEM_POR_CODIGO[erro.codigo] : undefined;
  if (mensagem) return mensagem;
  return `Não foi possível concluir a operação (código ${erro.codigo ?? erro.status}).`;
}
