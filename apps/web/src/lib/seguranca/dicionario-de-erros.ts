/**
 * Dicionário de mensagens de erro — T13 do PCF F08.
 *
 * Mapa `codigo (PONTO-XXX-NNN) -> mensagem em pt-BR` mostrada ao colaborador.
 * Cobre exatamente os códigos listados na §3 do PCF (a lista fechada de
 * leitura de `packages/contracts/errors.yaml`), parafraseando `titulo`/
 * `acao_sugerida` do catálogo — nunca inventando texto para um código que não
 * está lá (`apps/web/src/testes/f8/seguranca/dicionario-de-erros.teste.ts`
 * prova a cobertura contra a mesma lista fechada).
 *
 * REGRA DE OURO (`errors.yaml`, convenção 4): quando o catálogo marca
 * `expoe_regra: false` para um código, a mensagem aqui NUNCA cita o parâmetro
 * interno (faixa CIDR, limiar de score, geocerca configurada) — mesmo que o
 * `detail` da resposta um dia venha a incluir algo. Isto é defesa em
 * profundidade do lado do cliente, não confiança cega no servidor (§9,
 * proibição 12). Cada entrada abaixo comenta o `expoe_regra` de origem.
 */

export const DICIONARIO_DE_ERROS: Readonly<Record<string, string>> = {
  // --- AUTH ---------------------------------------------------------------
  // expoe_regra: false — nunca dizer QUAL dos dois casos (senha errada vs.
  // usuário inexistente) ocorreu, para não permitir enumeração de contas.
  "PONTO-AUTH-001": "E-mail ou senha incorretos. Confira os dados e tente novamente.",
  // expoe_regra: true
  "PONTO-AUTH-002": "Não encontramos sua sessão. Faça login novamente.",
  // expoe_regra: true
  "PONTO-AUTH-003":
    "Sua sessão expirou. Renovando automaticamente — se o problema continuar, faça login novamente.",
  // expoe_regra: false — não expõe detalhe de assinatura/emissor/ambiente do token.
  "PONTO-AUTH-004": "Não foi possível validar sua sessão. Faça login novamente.",
  // expoe_regra: true
  "PONTO-AUTH-006": "Sua sessão foi encerrada. Faça login novamente.",
  // expoe_regra: true
  "PONTO-AUTH-010": "Seu usuário está inativo ou bloqueado. Procure o RH.",
  // expoe_regra: true — o próprio catálogo pede para orientar a reautenticação.
  "PONTO-AUTH-011": "Por segurança, confirme sua senha para continuar.",
  // expoe_regra: false
  "PONTO-AUTH-013": "Sua credencial de acesso é inválida. Procure o suporte.",

  // --- SCORE ---------------------------------------------------------------
  // expoe_regra: false — nunca mostrar o score nem o limiar configurado.
  "PONTO-SCORE-001":
    "Não foi possível confirmar este registro por este canal. Use um canal alternativo e avise seu gestor.",
  // expoe_regra: false
  "PONTO-SCORE-002":
    "Não foi possível confirmar sua presença. Repita a captura com boa iluminação e o rosto bem visível.",
  // expoe_regra: false
  "PONTO-SCORE-003": "Não foi possível confirmar sua identidade. Tente novamente ou procure o RH.",
  // expoe_regra: true — o próprio catálogo autoriza citar a causa.
  "PONTO-SCORE-004":
    "Câmera virtual detectada. Encerre o software de câmera virtual e repita usando sua webcam física.",

  // --- REDE ------------------------------------------------------------------
  // expoe_regra: false — nunca citar a faixa CIDR configurada.
  "PONTO-REDE-001":
    "O registro não é permitido a partir desta rede. Tente de uma rede autorizada ou use outro canal.",
  // expoe_regra: true
  "PONTO-REDE-002":
    "Origem por VPN, proxy ou datacenter bloqueada. Desligue a VPN e tente novamente.",

  // --- GEO -------------------------------------------------------------------
  // expoe_regra: false — nunca citar a geocerca configurada.
  "PONTO-GEO-001":
    "Você está fora da área permitida para registrar o ponto. Aproxime-se do local de trabalho.",
  // expoe_regra: true
  "PONTO-GEO-002":
    "A precisão da localização está baixa demais. Aguarde o sinal do GPS estabilizar e tente novamente.",
  // expoe_regra: true
  "PONTO-GEO-003":
    "Localização simulada detectada. Desative o aplicativo de localização simulada e tente novamente.",

  // --- DISP ------------------------------------------------------------------
  // expoe_regra: true
  "PONTO-DISP-001":
    "Este aparelho ainda não está vinculado a você. Solicite o vínculo e aguarde a aprovação do RH.",
  // expoe_regra: true
  "PONTO-DISP-002":
    "Este aparelho está bloqueado. Use o aparelho ativo ou peça ao RH a reativação.",

  // --- MARC (núcleo legal — vocabulário obrigatório: marcação/tratamento) -----
  // expoe_regra: true
  "PONTO-MARC-001":
    "Marcação é definitiva por exigência legal e não pode ser alterada. Abra um tratamento para ajustar a apuração.",
  // expoe_regra: true
  "PONTO-MARC-002":
    "Marcação é definitiva por exigência legal e não pode ser excluída. Abra um tratamento para desconsiderá-la.",
  // expoe_regra: true
  "PONTO-MARC-003": "Esta marcação já havia sido registrada. Nenhum novo registro foi criado.",
  // expoe_regra: true
  "PONTO-MARC-004":
    "O horário informado está fora da janela aceita para registro. Verifique o relógio do seu dispositivo.",
  // expoe_regra: true
  "PONTO-MARC-005":
    "Este registro chegou fora do prazo de sincronização. Abra uma solicitação de ajuste.",
  // expoe_regra: false
  "PONTO-MARC-006": "Não foi possível validar este registro pendente. Refaça o registro.",
  // expoe_regra: false
  "PONTO-MARC-007":
    "Não foi possível validar este registro. Refaça o vínculo do dispositivo e tente novamente.",
  // expoe_regra: true
  "PONTO-MARC-008": "Não foi possível concluir o registro agora. Tente novamente.",
  // expoe_regra: true
  "PONTO-MARC-009": "Você não possui vínculo ativo nesta data. Procure o RH.",
  // expoe_regra: true
  "PONTO-MARC-010": "O registrador desta empresa ainda não está configurado. Procure o RH.",

  // --- IDEM ------------------------------------------------------------------
  // expoe_regra: true
  "PONTO-IDEM-001": "Falha técnica ao enviar o registro. Tente novamente.",
  // expoe_regra: true
  "PONTO-IDEM-002":
    "Uma tentativa anterior desta operação já foi enviada com dados diferentes. Recarregue a página e tente novamente.",
  // expoe_regra: true
  "PONTO-IDEM-003":
    "Sua última tentativa ainda está sendo processada. Aguarde alguns instantes e tente novamente.",

  // --- CONF / REC --------------------------------------------------------------
  // expoe_regra: true
  "PONTO-CONF-001":
    "Já existe um registro com estes dados. Verifique a lista antes de tentar novamente.",
  // expoe_regra: false
  "PONTO-REC-001": "Não encontramos o que você está procurando.",

  // --- RATE --------------------------------------------------------------------
  // expoe_regra: true
  "PONTO-RATE-001": "Muitas tentativas em pouco tempo. Aguarde alguns instantes e tente novamente.",

  // --- PERM ----------------------------------------------------------------------
  // expoe_regra: true
  "PONTO-PERM-001": "Você não tem permissão para realizar esta ação.",
  // expoe_regra: false
  "PONTO-PERM-002": "Você não tem acesso a este registro.",
  // expoe_regra: true
  "PONTO-PERM-004": "Seu perfil é somente leitura e não permite esta ação.",
  // expoe_regra: true
  "PONTO-PERM-005": "A delegação usada não está mais válida. Confira com quem delegou a ação.",

  // --- TEN -------------------------------------------------------------------------
  // expoe_regra: true
  "PONTO-TEN-001": "Não encontramos a empresa informada. Verifique o endereço de acesso.",
  // expoe_regra: false
  "PONTO-TEN-002": "Sua sessão não corresponde a esta empresa. Faça login novamente.",
  // expoe_regra: true
  "PONTO-TEN-003": "O acesso desta empresa está suspenso. Procure o suporte.",
  // expoe_regra: false
  "PONTO-TEN-004": "Não foi possível concluir esta ação.",

  // --- VAL -----------------------------------------------------------------------
  // expoe_regra: true
  "PONTO-VAL-001": "Alguns campos precisam de atenção. Verifique os destaques no formulário.",
  // expoe_regra: true
  "PONTO-VAL-005": "Um dos filtros informados é inválido. Verifique os valores e tente novamente.",
  // expoe_regra: true
  "PONTO-VAL-006":
    "A lista precisa ser recarregada. Volte para a primeira página e tente novamente.",
  // expoe_regra: true
  "PONTO-VAL-007": "O período informado é inválido. Verifique as datas.",
  // expoe_regra: true
  "PONTO-VAL-009": "O formato enviado não é aceito por esta operação.",
  // expoe_regra: true
  "PONTO-VAL-010":
    "Já existe um período vigente que conflita com este. Encerre o período atual antes de criar outro.",
  // expoe_regra: true
  "PONTO-VAL-011":
    "Uma informação obrigatória não foi enviada. Recarregue a página e tente novamente.",

  // --- LGPD ------------------------------------------------------------------------
  // expoe_regra: true
  "PONTO-LGPD-001": "É necessário um consentimento para uso de biometria. Procure o RH.",
};

/** Mensagem genérica para código ausente do dicionário — nunca quebra a tela
 *  por um código novo do catálogo que este arquivo ainda não conhece. */
export const MENSAGEM_DE_ERRO_PADRAO =
  "Não foi possível concluir a operação. Tente novamente em instantes.";

/**
 * Traduz um `codigo` do catálogo (`Problema.codigo`) para a mensagem em
 * pt-BR mostrada ao colaborador. Nunca deriva de `title`/`detail` (regra do
 * contrato, ver `src/lib/api/erros.ts`) — só do `codigo` estável.
 */
export function mensagemDoErro(codigo: string | undefined): string {
  if (!codigo) return MENSAGEM_DE_ERRO_PADRAO;
  return DICIONARIO_DE_ERROS[codigo] ?? MENSAGEM_DE_ERRO_PADRAO;
}
