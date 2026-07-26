/**
 * Mascaramento de documentos para exibição em tela (LGPD: minimizar exposição
 * de dado pessoal na interface). O valor mascarado mantém o formato
 * reconhecível do documento, mas esconde os dígitos do meio. Isto é
 * apresentação — o valor íntegro continua no registro legal (`marcacoes.cpf`,
 * por exemplo) e nunca é alterado por esta camada.
 */

const MASCARA = "•";

function apenasDigitos(valor: string): string {
  return valor.replace(/\D/g, "");
}

function exigirDigitos(valor: string, tamanho: number, rotulo: string): string {
  const digitos = apenasDigitos(valor);
  if (digitos.length !== tamanho) {
    throw new Error(
      `${rotulo} invalido: esperado ${tamanho} digitos, recebido ${digitos.length} ("${valor}").`,
    );
  }
  return digitos;
}

/** `"12345678901"` → `"123.•••.•••-01"` (mostra os 3 primeiros e os 2 últimos). */
export function mascararCpf(cpf: string): string {
  const digitos = exigirDigitos(cpf, 11, "CPF");
  const grupo1 = digitos.slice(0, 3);
  const grupo4 = digitos.slice(9, 11);
  return `${grupo1}.${MASCARA.repeat(3)}.${MASCARA.repeat(3)}-${grupo4}`;
}

/** `"12345678000199"` → `"12.•••.•••/••••-99"` (mostra os 2 primeiros e os 2 últimos). */
export function mascararCnpj(cnpj: string): string {
  const digitos = exigirDigitos(cnpj, 14, "CNPJ");
  const grupo1 = digitos.slice(0, 2);
  const grupo5 = digitos.slice(12, 14);
  return `${grupo1}.${MASCARA.repeat(3)}.${MASCARA.repeat(3)}/${MASCARA.repeat(4)}-${grupo5}`;
}

/** `"12345678901"` → `"123.•••••.••-1"` (mostra os 3 primeiros e o último dígito verificador). */
export function mascararPis(pis: string): string {
  const digitos = exigirDigitos(pis, 11, "PIS/NIT");
  const grupo1 = digitos.slice(0, 3);
  const digitoVerificador = digitos.slice(10, 11);
  return `${grupo1}.${MASCARA.repeat(5)}.${MASCARA.repeat(2)}-${digitoVerificador}`;
}
