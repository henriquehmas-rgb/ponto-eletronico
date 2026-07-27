import { expect, test, type APIRequestContext } from "@playwright/test";

/**
 * E2E de um CRUD de cadastro completo (T6, A2) — ponta a ponta contra API real
 * (PCF F9b §7 critério 13, §8: "E2E ponta a ponta contra API real cobre, no
 * mínimo: login, um CRUD de cadastro completo, um ciclo de tratamento na
 * grade de apuração, e uma atribuição de escala"). Mesmo padrão de
 * `e2e/escalas/escalas.spec.ts`/`e2e/apuracao/apuracao.spec.ts`: exporte
 * `NEXT_PUBLIC_API_URL`/`API_INTERNAL_URL` apontando para a instância local
 * do seu agente antes de `pnpm dev`/`pnpm build`.
 *
 * Escolhido `departamentos` (não `empresas`/`unidades`/`cargos`/...) porque é
 * a única entidade de cadastro desta fase com as CINCO operações completas
 * do CRUD no contrato — `listar`/`criar`/`obter`/`atualizar`/`excluir` (T6,
 * PCF §2: `centros-custo`/`cargos` não têm exclusão; `vinculos` não têm
 * atualização) — então é o candidato mais direto para provar "um CRUD de
 * cadastro completo" sem composição.
 *
 * `PONTO_SEED_ADMIN_SENHA` precisa ser a MESMA senha usada em
 * `python migrations/seed_dev.py` para o tenant informado — sem ela, o teste
 * inteiro é pulado (`test.skip` com motivo explícito no relatório).
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

/**
 * Empresa de apoio criada DIRETO na API — o campo "Empresa" do formulário de
 * departamento (T6) é obrigatório, mas a tela de empresas (T4) é ownership de
 * outra seção deste mesmo agente; criar por `request` evita depender do
 * estado dela para este spec, que só prova o CRUD de departamentos.
 */
async function criarEmpresaDeApoio(request: APIRequestContext, token: string): Promise<string> {
  const empresa = await request.post(`${URL_API}/v1/empresas`, {
    headers: {
      Authorization: `Bearer ${token}`,
      "X-Tenant": TENANT,
      "Idempotency-Key": novaChaveDeIdempotencia(),
    },
    data: { cnpj: gerarCnpjValido(), razaoSocial: `Empresa E2E Cadastros ${Date.now()}` },
  });
  expect(empresa.ok(), await empresa.text()).toBeTruthy();
  return (await empresa.json()).id as string;
}

test.describe("Cadastros — CRUD completo de departamentos (T6), ponta a ponta", () => {
  test("cria, edita e exclui um departamento pela UI, refletindo na API real", async ({
    page,
    request,
  }) => {
    test.setTimeout(90_000);

    // Arrange: empresa de apoio direto na API (fora do escopo deste CRUD).
    const token = await autenticarViaApi(request);
    const empresaId = await criarEmpresaDeApoio(request, token);
    const nomeEmpresa = (
      await (
        await request.get(`${URL_API}/v1/empresas/${empresaId}`, {
          headers: { Authorization: `Bearer ${token}`, "X-Tenant": TENANT },
        })
      ).json()
    ).razaoSocial as string;

    // Login pela UI de verdade (`/`, F8) — prova que `?returnTo=/painel/cadastros/departamentos`
    // funciona de ponta a ponta com esta seção, mesmo critério de T1/A1.
    await page.goto(`/?returnTo=${encodeURIComponent("/painel/cadastros/departamentos")}`);
    await page.getByLabel("E-mail").fill(EMAIL_ADMIN);
    await page.getByLabel("Senha").fill(SENHA_ADMIN ?? "");
    const campoTenant = page.getByLabel("Identificador da empresa (tenant)");
    if (await campoTenant.isVisible().catch(() => false)) {
      await campoTenant.fill(TENANT);
    }
    await page.getByRole("button", { name: "Entrar" }).click();
    await expect(page).toHaveURL(/\/painel\/cadastros\/departamentos$/, { timeout: 15_000 });

    // CREATE — cria um departamento novo pela UI.
    const codigoDepartamento = `DEP-E2E-${Date.now()}`;
    const nomeDepartamento = `Departamento E2E Playwright ${Date.now()}`;
    await page.getByRole("button", { name: "Novo departamento" }).click();
    const dialogo = page.getByRole("dialog");
    await expect(dialogo).toBeVisible();

    await dialogo.getByRole("combobox", { name: "Empresa" }).click();
    await page.getByRole("option", { name: nomeEmpresa }).click();
    // Sem `exact: true` de propósito: `CampoTexto` acrescenta " *" ao rótulo de
    // campo obrigatório (`campos.tsx`), então o nome acessível real é
    // "Código *"/"Nome *" — a correspondência por substring (padrão do
    // Playwright) casa com os dois.
    await dialogo.getByLabel("Código").fill(codigoDepartamento);
    await dialogo.getByLabel("Nome").fill(nomeDepartamento);
    await dialogo.getByRole("button", { name: "Salvar" }).click();
    await expect(dialogo).toBeHidden({ timeout: 10_000 });
    await expect(page.getByText(nomeDepartamento)).toBeVisible({ timeout: 10_000 });

    // Confirma contra a API real: o departamento existe com os dados esperados.
    // `busca` filtra só por `nome` (`app/organizacao/estrutura.py::listar_departamentos`,
    // `Departamento.nome.ilike(...)`) — nunca por `codigo`, apesar do placeholder
    // da busca na UI dizer "por nome ou código" (achado à parte, não bloqueante).
    const listaAposCriar = await request.get(`${URL_API}/v1/departamentos`, {
      headers: { Authorization: `Bearer ${token}`, "X-Tenant": TENANT },
      params: { busca: nomeDepartamento },
    });
    expect(listaAposCriar.ok()).toBeTruthy();
    const departamentoCriado = (await listaAposCriar.json()).dados.find(
      (item: { codigo?: string }) => item.codigo === codigoDepartamento,
    );
    expect(
      departamentoCriado,
      "departamento criado pela UI não apareceu em GET /v1/departamentos",
    ).toBeTruthy();
    const departamentoId = departamentoCriado.id as string;

    // UPDATE — abre o mesmo registro pelo nome (link da linha) e renomeia.
    const nomeAtualizado = `${nomeDepartamento} (editado)`;
    await page.getByRole("button", { name: nomeDepartamento }).click();
    const dialogoDeEdicao = page.getByRole("dialog");
    await expect(dialogoDeEdicao).toBeVisible();
    const campoNome = dialogoDeEdicao.getByLabel("Nome");
    await campoNome.fill("");
    await campoNome.fill(nomeAtualizado);
    await dialogoDeEdicao.getByRole("button", { name: "Salvar" }).click();
    await expect(dialogoDeEdicao).toBeHidden({ timeout: 10_000 });
    await expect(page.getByText(nomeAtualizado)).toBeVisible({ timeout: 10_000 });

    // Confirma a atualização contra a API real.
    const departamentoAtualizado = await request.get(
      `${URL_API}/v1/departamentos/${departamentoId}`,
      { headers: { Authorization: `Bearer ${token}`, "X-Tenant": TENANT } },
    );
    expect(departamentoAtualizado.ok()).toBeTruthy();
    expect((await departamentoAtualizado.json()).nome).toBe(nomeAtualizado);

    // DELETE — exclusão lógica pela UI, confirmada no diálogo de confirmação.
    const linhaDoDepartamento = page.locator('[role="row"]', { hasText: nomeAtualizado });
    await linhaDoDepartamento.getByRole("button", { name: "Excluir" }).click();
    const dialogoDeConfirmacao = page.getByRole("dialog");
    await expect(dialogoDeConfirmacao).toBeVisible();
    await dialogoDeConfirmacao.getByRole("button", { name: "Excluir", exact: true }).click();
    await expect(dialogoDeConfirmacao).toBeHidden({ timeout: 10_000 });
    await expect(page.getByText(nomeAtualizado)).not.toBeVisible({ timeout: 10_000 });

    // Confirma a exclusão lógica contra a API real: some da listagem padrão
    // (`incluirExcluidos=false`, default de `useDepartamentos`), mas o
    // histórico é preservado (nunca um DELETE físico) — mesma garantia que
    // o restante da fase já exige para tratamento (nunca apaga, só marca).
    const listaAposExcluir = await request.get(`${URL_API}/v1/departamentos`, {
      headers: { Authorization: `Bearer ${token}`, "X-Tenant": TENANT },
      params: { busca: nomeAtualizado },
    });
    expect(listaAposExcluir.ok()).toBeTruthy();
    const aindaNaListaPadrao = (await listaAposExcluir.json()).dados.some(
      (item: { id?: string }) => item.id === departamentoId,
    );
    expect(
      aindaNaListaPadrao,
      "departamento excluído ainda aparece na listagem padrão",
    ).toBeFalsy();

    // `listarDepartamentos` não referencia o parâmetro compartilhado
    // `IncluirExcluidos` no contrato (só `empresas`/`unidades` o fazem,
    // `openapi.yaml`) — `app/organizacao/estrutura.py::listar_departamentos`
    // nem aceita esse parâmetro, e `obter_departamento` também não passa
    // `incluir_excluidos` para `crud_base.obter_ou_404` (default `False`).
    // Não há, hoje, nenhuma forma de consultar o registro excluído por esta
    // API — a garantia de exclusão lógica (nunca física) é uma propriedade
    // de schema (`departamentos.excluido_em`), não algo verificável por este
    // endpoint. O que É verificável e contratual: o registro deixa de ser
    // alcançável por id (`obterDepartamento`), consistente com "removido das
    // listagens" (texto do diálogo de confirmação).
    const obterAposExcluir = await request.get(`${URL_API}/v1/departamentos/${departamentoId}`, {
      headers: { Authorization: `Bearer ${token}`, "X-Tenant": TENANT },
    });
    expect(
      obterAposExcluir.status(),
      "departamento excluído ainda é alcançável por GET /v1/departamentos/{id}",
    ).toBe(404);
  });
});
