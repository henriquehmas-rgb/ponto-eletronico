/**
 * Validação de `returnTo` (T1, §2 do PCF F8) — proteção contra *open redirect*.
 *
 * A tela de login (`/`) navega para `returnTo` após autenticar com sucesso,
 * porque a F9b (fase irmã) redireciona para `/?returnTo=/painel` quando não há
 * sessão. Sem validação, um link malicioso `/?returnTo=https://evil.com`
 * levaria o colaborador, já autenticado, para um site externo.
 *
 * Regra: só um caminho relativo que comece com EXATAMENTE uma "/" é aceito.
 * `//evil.com` (URL protocol-relative) e qualquer esquema absoluto
 * (`http:`, `https:`, `javascript:`...) são rejeitados e tratados como ausentes.
 */
export function validarRetornoSeguro(valor: string | null | undefined): string | null {
  if (!valor) return null;
  if (!valor.startsWith("/")) return null;
  // "//evil.com" e "/\evil.com" são interpretados por alguns navegadores como
  // URL protocol-relative (o "host" vira "evil.com") — barrado antes de
  // qualquer outra checagem.
  if (valor.startsWith("//") || valor.startsWith("/\\")) return null;

  try {
    // Resolver contra uma base fixa e comparar a origem é a forma robusta de
    // detectar host embutido via caracteres codificados ou variações que um
    // `startsWith` textual não pega. Se `valor` de fato só é caminho, a
    // origem resolvida bate com a da base.
    const base = "https://verificacao-de-retorno.invalid";
    const resolvido = new URL(valor, base);
    if (resolvido.origin !== base) return null;
  } catch {
    return null;
  }

  return valor;
}
