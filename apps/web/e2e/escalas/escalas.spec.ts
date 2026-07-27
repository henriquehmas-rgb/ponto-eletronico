import { expect, test, type APIRequestContext } from "@playwright/test";

/**
 * E2E de turnos, escalas e atribuição (T12) — ponta a ponta contra API real
 * (PCF F9b §7 critério 13, §8). Ao contrário de `e2e/registro-webcam.spec.ts`
 * (F8, T10 — que mocka toda a rede de propósito), este spec depende de um
 * backend real de verdade rodando: exporte `NEXT_PUBLIC_API_URL`/
 * `API_INTERNAL_URL` apontando para a instância local do seu agente antes de
 * `pnpm dev`/`pnpm build` (ver PCF §"Ambiente de verificação").
 *
 * `PONTO_SEED_ADMIN_SENHA` precisa ser a MESMA senha usada em
 * `python migrations/seed_dev.py` para o tenant informado — sem ela, o teste
 * inteiro é pulado (não falha silenciosamente, `test.skip` com motivo
 * explícito no relatório do Playwright).
 */

const TENANT = process.env.PONTO_E2E_TENANT ?? "seeg";
const EMAIL_ADMIN = process.env.PONTO_E2E_ADMIN_EMAIL ?? "admin@seeg.com.br";
const SENHA_ADMIN = process.env.PONTO_SEED_ADMIN_SENHA;
const URL_API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

test.skip(
  !SENHA_ADMIN,
  "PONTO_SEED_ADMIN_SENHA ausente — defina a mesma senha usada em `python migrations/seed_dev.py` " +
    "para rodar este spec contra a API real do seu agente.",
);

function novaChaveDeIdempotencia(): string {
  return `e2e-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

function digitoVerificador(digitos: number[], pesos: number[]): number {
  const soma = digitos.reduce(
    (acumulado, digito, indice) => acumulado + digito * (pesos[indice] ?? 0),
    0,
  );
  const resto = soma % 11;
  return resto < 2 ? 0 : 11 - resto;
}

function gerarCnpjValido(): string {
  const base = Array.from({ length: 12 }, () => Math.floor(Math.random() * 10));
  const dv1 = digitoVerificador(base, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]);
  const dv2 = digitoVerificador([...base, dv1], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]);
  return [...base, dv1, dv2].join("");
}

function gerarCpfValido(): string {
  const base = Array.from({ length: 9 }, () => Math.floor(Math.random() * 10));
  const dv1 = digitoVerificador(base, [10, 9, 8, 7, 6, 5, 4, 3, 2]);
  const dv2 = digitoVerificador([...base, dv1], [11, 10, 9, 8, 7, 6, 5, 4, 3, 2]);
  return [...base, dv1, dv2].join("");
}

/**
 * Dados de apoio (empresa/colaborador/vínculo) criados DIRETO na API — essas
 * três telas são ownership de A2 (cadastros), fora do escopo desta seção;
 * criar por `request` (não pela UI) evita depender do estado delas para
 * este spec, que só prova T12 (turnos/escalas/atribuição).
 */
async function criarVinculoDeApoio(request: APIRequestContext, token: string) {
  const cabecalhos = { Authorization: `Bearer ${token}`, "X-Tenant": TENANT };
  const comIdempotencia = () => ({ ...cabecalhos, "Idempotency-Key": novaChaveDeIdempotencia() });

  const nomeEmpresa = `Empresa E2E Escalas ${Date.now()}`;
  const empresa = await request.post(`${URL_API}/v1/empresas`, {
    headers: comIdempotencia(),
    data: { cnpj: gerarCnpjValido(), razaoSocial: nomeEmpresa },
  });
  expect(empresa.ok(), await empresa.text()).toBeTruthy();
  const empresaId = (await empresa.json()).id as string;

  const matricula = `E2E-${Date.now()}`;
  // Nome com timestamp, de propósito: um nome estático colidiria com
  // colaboradores de execuções anteriores do mesmo spec (mesmo tenant/banco
  // reaproveitado entre execuções locais) e violaria o modo estrito do
  // Playwright em `getByRole("option", { name: nomeColaborador })` — mesmo
  // padrão que `e2e/apuracao/apuracao.spec.ts` já usa.
  const nomeColaborador = `Colaborador E2E Escalas ${Date.now()}`;
  const colaborador = await request.post(`${URL_API}/v1/colaboradores`, {
    headers: comIdempotencia(),
    data: { empresaId, matricula, cpf: gerarCpfValido(), nomeCompleto: nomeColaborador },
  });
  expect(colaborador.ok(), await colaborador.text()).toBeTruthy();
  const colaboradorId = (await colaborador.json()).id as string;

  const vinculo = await request.post(`${URL_API}/v1/vinculos`, {
    headers: comIdempotencia(),
    data: { colaboradorId, empresaId, matriculaEsocial: matricula, dataInicio: "2026-01-01" },
  });
  expect(vinculo.ok(), await vinculo.text()).toBeTruthy();
  const vinculoJson = await vinculo.json();
  return {
    empresaId,
    nomeEmpresa,
    colaboradorId,
    nomeColaborador,
    vinculoId: vinculoJson.id as string,
  };
}

async function autenticarViaApi(request: APIRequestContext): Promise<string> {
  const resposta = await request.post(`${URL_API}/v1/auth/login`, {
    headers: { "X-Tenant": TENANT, "Idempotency-Key": novaChaveDeIdempotencia() },
    data: { email: EMAIL_ADMIN, senha: SENHA_ADMIN, tenant: TENANT },
  });
  expect(resposta.ok(), await resposta.text()).toBeTruthy();
  const corpo = await resposta.json();
  expect(corpo.mfaRequerido, "MFA inesperado para a credencial de seed_dev.py").toBeFalsy();
  return corpo.accessToken as string;
}

test.describe("Escalas (T12) — turnos, escala 12x36 e atribuição, ponta a ponta", () => {
  test("cria turno, cria escala 12x36, atribui a um vínculo e reflete na listagem", async ({
    page,
    request,
  }) => {
    // Arrange: dados de apoio direto na API (fora do ownership desta seção).
    const token = await autenticarViaApi(request);
    const { vinculoId, nomeEmpresa, nomeColaborador } = await criarVinculoDeApoio(request, token);

    // Login pela UI de verdade (`/`, F8) — prova que `?returnTo=/painel/escalas/turnos`
    // funciona de ponta a ponta com esta seção, mesmo critério de T1/A1.
    await page.goto(`/?returnTo=${encodeURIComponent("/painel/escalas/turnos")}`);
    await page.getByLabel("E-mail").fill(EMAIL_ADMIN);
    await page.getByLabel("Senha").fill(SENHA_ADMIN ?? "");
    const campoTenant = page.getByLabel("Identificador da empresa (tenant)");
    if (await campoTenant.isVisible().catch(() => false)) {
      await campoTenant.fill(TENANT);
    }
    await page.getByRole("button", { name: "Entrar" }).click();
    await expect(page).toHaveURL(/\/painel\/escalas\/turnos$/, { timeout: 15_000 });

    // Turnos: cria um turno novo pela UI.
    const codigoTurno = `T-E2E-${Date.now()}`;
    await page.getByRole("button", { name: "Novo turno" }).click();
    const dialogoDeTurno = page.getByRole("dialog");
    // `empresaId` é obrigatório no formulário (`formulario-turno.tsx`,
    // `ESQUEMA.empresaId = z.string().min(1, "Selecione a empresa.")`) e não
    // tem valor padrão quando o filtro "Filtrar por empresa" da lista está em
    // "Todas as empresas" (estado inicial) — sem selecionar aqui, o envio
    // falha na validação client-side e "Salvar turno" nunca fecha o diálogo.
    await dialogoDeTurno.getByRole("combobox", { name: "Empresa" }).click();
    await page.getByRole("option", { name: nomeEmpresa }).click();
    // Sem `exact: true` de propósito: `CampoTexto` acrescenta " *" ao rótulo
    // de campo obrigatório (`campos.tsx`), então o nome acessível real é
    // "Código *"/"Nome *" — a correspondência por substring (padrão do
    // Playwright) casa com os dois.
    // Nome com timestamp também: colide com turnos de execuções anteriores
    // no seletor "Turno" da posição do ciclo (abaixo) sem isto.
    const nomeTurno = `Turno E2E Playwright ${Date.now()}`;
    await dialogoDeTurno.getByLabel("Código").fill(codigoTurno);
    await dialogoDeTurno.getByLabel("Nome").fill(nomeTurno);
    await dialogoDeTurno.getByRole("button", { name: "Salvar turno" }).click();
    await expect(page.getByText(codigoTurno)).toBeVisible({ timeout: 10_000 });

    // Escalas: cria uma escala 12x36 com dois ciclos (trabalho 720min / folga).
    await page.goto("/painel/escalas/padroes");
    const codigoEscala = `12X36-E2E-${Date.now()}`;
    await page.getByRole("button", { name: "Nova escala" }).click();
    const dialogoDeEscala = page.getByRole("dialog");
    // Mesma exigência de `empresaId` do formulário de turno acima — e aqui
    // duplamente necessária: o combobox "Turno" da posição do ciclo (abaixo)
    // só lista turnos da empresa selecionada (`formulario-escala.tsx`,
    // `useTurnos({ empresaId: empresaSelecionada || undefined, ... })`), sem
    // isto o turno criado acima nunca aparece como opção.
    await dialogoDeEscala.getByRole("combobox", { name: "Empresa" }).click();
    await page.getByRole("option", { name: nomeEmpresa }).click();
    await dialogoDeEscala.getByLabel("Código").fill(codigoEscala);
    await dialogoDeEscala.getByLabel("Nome").fill("Escala 12x36 E2E Playwright");
    await dialogoDeEscala.getByLabel("Dias do ciclo").fill("2");
    await dialogoDeEscala.getByLabel("Data-âncora (posição 1)").fill("2026-01-01");

    // Duas posições do ciclo: a primeira (trabalho) referencia o turno criado acima.
    await dialogoDeEscala.getByRole("button", { name: "Adicionar posição" }).click();
    await dialogoDeEscala.getByRole("button", { name: "Adicionar posição" }).click();
    // Cada posição nova nasce com `tipoDia: "folga"` por padrão
    // (`formulario-escala.tsx`, `arrayDeCiclos.append({ tipoDia: "folga", ... })`)
    // — sem trocar explicitamente a posição 1 para "Trabalho", as duas
    // posições ficam "folga" e o ciclo 12x36 nunca é o esperado. O seletor de
    // "Tipo do dia" é o primeiro combobox com esse nome.
    await dialogoDeEscala.getByRole("combobox", { name: "Tipo do dia" }).first().click();
    await page.getByRole("option", { name: "Trabalho", exact: true }).click();
    // Posição 1: turno + carga 720. O seletor de turno é o primeiro combobox "Turno".
    await dialogoDeEscala.getByRole("combobox", { name: "Turno" }).first().click();
    await page.getByRole("option", { name: nomeTurno }).click();
    await dialogoDeEscala.getByLabel("Carga (min)").first().fill("720");

    await dialogoDeEscala.getByRole("button", { name: "Salvar escala" }).click();
    await expect(page.getByText(codigoEscala)).toBeVisible({ timeout: 10_000 });

    // Atribuição: atribui a escala recém-criada ao vínculo de apoio.
    const linhaDaEscala = page.locator("tr", { hasText: codigoEscala });
    await linhaDaEscala.getByRole("button", { name: "Atribuir" }).click();
    await page.getByRole("combobox", { name: "Vínculo" }).click();
    await page.getByRole("option", { name: nomeColaborador }).click();
    await page.getByLabel("Vigência — início").fill("2026-09-01");
    await page.getByRole("button", { name: "Atribuir", exact: true }).click();
    await expect(page.getByRole("dialog")).toBeHidden({ timeout: 10_000 });

    // Confirma contra a API real: a escala tem os dois ciclos esperados.
    const escalas = await request.get(`${URL_API}/v1/escalas`, {
      headers: { Authorization: `Bearer ${token}`, "X-Tenant": TENANT },
      params: { ordenar: "criadoEm:desc", limite: 50 },
    });
    expect(escalas.ok()).toBeTruthy();
    const escalaCriada = (await escalas.json()).dados.find(
      (item: { codigo?: string }) => item.codigo === codigoEscala,
    );
    expect(escalaCriada, "escala criada pela UI não apareceu em GET /v1/escalas").toBeTruthy();
    expect(escalaCriada.ciclos).toHaveLength(2);
    expect(escalaCriada.ciclos.find((c: { posicao?: number }) => c.posicao === 1)?.tipoDia).toBe(
      "trabalho",
    );
    expect(escalaCriada.ciclos.find((c: { posicao?: number }) => c.posicao === 2)?.tipoDia).toBe(
      "folga",
    );

    void vinculoId; // usado só no arrange — mantém o vínculo vivo até o fim do teste.
  });
});
