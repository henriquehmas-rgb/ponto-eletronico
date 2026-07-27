import { execFile } from "node:child_process";
import { promisify } from "node:util";

import { expect, test, type APIRequestContext } from "@playwright/test";

/**
 * E2E da grade de apuração (T9/T10/T11) — ponta a ponta contra API real
 * (PCF F9b §7 critério 13, §8). Mesmo padrão de `e2e/escalas/escalas.spec.ts`
 * (A4): dados de apoio (empresa/colaborador/vínculo) criados DIRETO na API —
 * essas telas são ownership de A2, fora do escopo desta seção — e o fluxo
 * sob teste (T9/T10/T11) exercitado pela UI de verdade.
 *
 * `PONTO_SEED_ADMIN_SENHA` precisa ser a MESMA senha usada em
 * `python migrations/seed_dev.py` para o tenant informado — sem ela, o teste
 * inteiro é pulado (`test.skip` com motivo explícito no relatório).
 *
 * ACHADO (relatado no relatório da fase, não corrigido aqui — fora do
 * ownership de A3, `apps/api/**`): `POST /v1/apuracoes/recalcular` sempre
 * devolve `202 enfileirado`, mas `enfileirar_recalculo`
 * (`apps/api/app/apuracao/tratamento/recalculo.py`) chama
 * `create_pool(RedisSettings.from_dsn(redis_url))` SEM `default_queue_name`,
 * então o job cai na fila padrão do ARQ (`arq:queue`) — nunca na fila que o
 * worker realmente escuta (`WorkerSettings.queue_name = "ponto:padrao"`,
 * `apps/worker/worker/main.py`). Na prática, todo recálculo fica órfão e
 * nunca processa (mesmo problema provável em `app/importadores/servico.py` e
 * `app/terminais/servico.py`, que também chamam `enqueue_job` sem
 * `default_queue_name`). Este spec não depende do endpoint HTTP para obter a
 * apuração de apoio (`enfileirarRecalculoDeApoioViaFilaCorreta` abaixo
 * enfileira DIRETO no Redis, na fila certa, chamando a MESMA tarefa
 * `recalcular_periodo` que o worker real já executa) — é só para montar o
 * cenário; o corpo do teste (mais abaixo, seção "T11") ainda clica em
 * "Recalcular" na UI de verdade, exercitando `POST /v1/apuracoes/recalcular`
 * de fato — só não afirma que o resultado é reprocessado, porque não é.
 */

const TENANT = process.env.PONTO_E2E_TENANT ?? "seeg";
const EMAIL_ADMIN = process.env.PONTO_E2E_ADMIN_EMAIL ?? "admin@seeg.com.br";
const SENHA_ADMIN = process.env.PONTO_SEED_ADMIN_SENHA;
const URL_API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const URL_REDIS =
  process.env.PONTO_E2E_REDIS_URL ??
  "redis://:18286d9fc9bc1b4979f081871c11f878632be6db6d6ad1b8@127.0.0.1:16379/0";
const PYTHON_DA_API = process.env.PONTO_E2E_PYTHON ?? "python";

const execFileAsync = promisify(execFile);

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

/** `AAAA-MM-DD` do quinto dia do mês corrente — sempre dentro do "mês atual" que a grade abre por padrão. */
function quintoDiaDoMesAtual(): string {
  const hoje = new Date();
  const ano = hoje.getFullYear();
  const mes = String(hoje.getMonth() + 1).padStart(2, "0");
  return `${ano}-${mes}-05`;
}

async function autenticarViaApi(
  request: APIRequestContext,
): Promise<{ token: string; tenantId: string }> {
  const resposta = await request.post(`${URL_API}/v1/auth/login`, {
    headers: { "X-Tenant": TENANT, "Idempotency-Key": novaChaveDeIdempotencia() },
    data: { email: EMAIL_ADMIN, senha: SENHA_ADMIN, tenant: TENANT },
  });
  expect(resposta.ok(), await resposta.text()).toBeTruthy();
  const corpo = await resposta.json();
  expect(corpo.mfaRequerido, "MFA inesperado para a credencial de seed_dev.py").toBeFalsy();
  return { token: corpo.accessToken as string, tenantId: corpo.usuario.tenantId as string };
}

/**
 * Enfileira a MESMA tarefa (`recalcular_periodo`) que
 * `POST /v1/apuracoes/recalcular` enfileiraria, mas na fila que o worker
 * real escuta (`ponto:padrao`) — contorna só o ACHADO acima (nome de fila
 * ausente no enfileiramento HTTP), sem tocar `apps/api/**`/`apps/worker/**`.
 * Usa o mesmo `python`/pacotes já instalados de `apps/api` (`arq`), via
 * subprocesso — só para montar o cenário de apoio, nunca para afirmar que o
 * endpoint HTTP funciona (essa afirmação NÃO é feita em lugar nenhum deste
 * spec).
 */
async function enfileirarRecalculoDeApoioViaFilaCorreta(parametros: {
  tenantId: string;
  vinculoId: string;
  data: string;
}): Promise<void> {
  const script = [
    "import asyncio",
    "from arq import create_pool",
    "from arq.connections import RedisSettings",
    "async def main():",
    `    pool = await create_pool(RedisSettings.from_dsn(${JSON.stringify(URL_REDIS)}), default_queue_name="ponto:padrao")`,
    "    await pool.enqueue_job(",
    '        "recalcular_periodo",',
    `        tenant_id=${JSON.stringify(parametros.tenantId)},`,
    `        vinculo_id=${JSON.stringify(parametros.vinculoId)},`,
    `        inicio=${JSON.stringify(parametros.data)},`,
    `        fim=${JSON.stringify(parametros.data)},`,
    '        motivo="manual",',
    "    )",
    "    await pool.aclose()",
    "asyncio.run(main())",
  ].join("\n");
  await execFileAsync(PYTHON_DA_API, ["-c", script]);
}

/**
 * Cria empresa + colaborador + vínculo, e garante uma apuração real (via
 * `enfileirarRecalculoDeApoioViaFilaCorreta`) para o dia de apoio — sem
 * nenhuma linha apurada a grade não mostra o vínculo: `GET /v1/apuracoes`
 * só devolve dias já processados (ownership de A2, fora desta seção;
 * consumido aqui só como dado de apoio via `request`, nunca pela UI).
 *
 * Sem jornada atribuída de propósito: o motor de apuração (F3/F4) já lida
 * com "sem jornada resolvida" produzindo um dia `nao_apurado`/
 * `com_ocorrencia` em vez de falhar — o suficiente para a célula aparecer
 * na grade e o ciclo de tratamento (T10) ser exercitado. Atribuir uma
 * jornada de verdade não é possível neste ambiente: `POST /v1/jornadas`
 * (`criarJornada`, ownership de A1/F3, fora desta seção) devolve sempre
 * `500` — `_montar_jornada` (`apps/api/app/routers/jornadas.py`) valida a
 * resposta contra `contrato.Jornada`, que exige `noturnoInicio`/
 * `noturnoFim` como `string`, mas a coluna do banco é `TIME` e o SQLAlchemy
 * devolve `datetime.time` — nunca convertido para `"HH:MM"` antes da
 * validação. ACHADO relatado, não corrigido (fora do ownership de A3).
 */
async function criarVinculoApuradoDeApoio(
  request: APIRequestContext,
  token: string,
  tenantId: string,
) {
  const cabecalhos = { Authorization: `Bearer ${token}`, "X-Tenant": TENANT };
  const comIdempotencia = () => ({ ...cabecalhos, "Idempotency-Key": novaChaveDeIdempotencia() });

  const empresa = await request.post(`${URL_API}/v1/empresas`, {
    headers: comIdempotencia(),
    data: { cnpj: gerarCnpjValido(), razaoSocial: `Empresa E2E Apuração ${Date.now()}` },
  });
  expect(empresa.ok(), await empresa.text()).toBeTruthy();
  const empresaId = (await empresa.json()).id as string;

  const matricula = `E2E-AP-${Date.now()}`;
  const nomeColaborador = `Colaborador E2E Apuração ${Date.now()}`;
  const colaborador = await request.post(`${URL_API}/v1/colaboradores`, {
    headers: comIdempotencia(),
    data: { empresaId, matricula, cpf: gerarCpfValido(), nomeCompleto: nomeColaborador },
  });
  expect(colaborador.ok(), await colaborador.text()).toBeTruthy();
  const colaboradorId = (await colaborador.json()).id as string;

  const vinculo = await request.post(`${URL_API}/v1/vinculos`, {
    headers: comIdempotencia(),
    data: { colaboradorId, empresaId, matriculaEsocial: matricula, dataInicio: "2020-01-01" },
  });
  expect(vinculo.ok(), await vinculo.text()).toBeTruthy();
  const vinculoId = (await vinculo.json()).id as string;

  const dia = quintoDiaDoMesAtual();
  await enfileirarRecalculoDeApoioViaFilaCorreta({ tenantId, vinculoId, data: dia });

  // Recálculo é assíncrono (worker ARQ) — espera até a apuração aparecer, sem
  // inventar um endpoint de status (não existe, PCF §2/§9/T11).
  await expect
    .poll(
      async () => {
        const apuracoes = await request.get(`${URL_API}/v1/apuracoes`, {
          headers: cabecalhos,
          params: { vinculoId, de: dia, ate: dia },
        });
        if (!apuracoes.ok()) return 0;
        return ((await apuracoes.json()).dados ?? []).length;
      },
      { message: "apuração do dia de apoio nunca apareceu (worker processou?)", timeout: 30_000 },
    )
    .toBeGreaterThan(0);

  return { empresaId, colaboradorId, vinculoId, nomeColaborador, dia };
}

test.describe("Apuração (T9/T10/T11) — grade, tratamento e recálculo, ponta a ponta", () => {
  test("abre a grade, registra e aprova um tratamento a partir da célula, e dispara um recálculo", async ({
    page,
    request,
  }) => {
    test.setTimeout(120_000);

    // Arrange: dados de apoio direto na API (fora do ownership desta seção).
    const { token, tenantId } = await autenticarViaApi(request);
    const { vinculoId, nomeColaborador, dia } = await criarVinculoApuradoDeApoio(
      request,
      token,
      tenantId,
    );

    // Login pela UI de verdade (`/`, F8) — prova que `?returnTo=/painel/apuracao`
    // funciona de ponta a ponta com esta seção, mesmo critério de T1/A1.
    await page.goto(`/?returnTo=${encodeURIComponent("/painel/apuracao")}`);
    await page.getByLabel("E-mail").fill(EMAIL_ADMIN);
    await page.getByLabel("Senha").fill(SENHA_ADMIN ?? "");
    const campoTenant = page.getByLabel("Identificador da empresa (tenant)");
    if (await campoTenant.isVisible().catch(() => false)) {
      await campoTenant.fill(TENANT);
    }
    await page.getByRole("button", { name: "Entrar" }).click();
    await expect(page).toHaveURL(/\/painel\/apuracao$/, { timeout: 15_000 });

    // Filtra pelo colaborador de apoio para não depender do resto da base.
    // `getByRole("combobox", { name: "Colaborador" })` (não `getByLabel`, que
    // também casaria com o rótulo "Colaborador" do painel de colunas de
    // `TabelaDeDados` e os botões "Mover Colaborador para a esquerda/direita").
    const filtroColaborador = page.getByRole("combobox", { name: "Colaborador", exact: true });
    await filtroColaborador.click();
    await page.getByRole("option", { name: nomeColaborador }).click();

    const linhaDoVinculo = page.locator('[role="row"]', { hasText: nomeColaborador });
    await expect(linhaDoVinculo).toBeVisible({ timeout: 15_000 });

    const diaDoMes = String(Number(dia.slice(8, 10)));
    const celulaDoDia = linhaDoVinculo.getByRole("button", {
      name: new RegExp(`^${diaDoMes} \\(`),
    });
    await celulaDoDia.click();

    const dialogo = page.getByRole("dialog");
    await expect(dialogo).toBeVisible();
    // Nenhum controle deste diálogo sugere "editar marcação" — prova em tempo de execução, além da varredura estática.
    await expect(dialogo).not.toContainText(/editar marcação|corrigir marcação/i);

    // Novo tratamento: categoria "justificativa" não exige campo condicional (marcação/minutos), simplifica o E2E.
    await dialogo.getByRole("combobox", { name: /tipo de tratamento/i }).click();
    await page.getByRole("option", { name: "Justificativa de atraso" }).click();
    await dialogo.getByLabel("Motivo").fill("Justificativa registrada via E2E Playwright (T10).");
    await dialogo.getByRole("button", { name: "Registrar tratamento" }).click();

    // O tratamento criado nasce "pendente" (tipo exige aprovação) e aparece na lista do dia.
    await expect(dialogo.getByText("Pendente de aprovação")).toBeVisible({ timeout: 10_000 });

    // Aprova — completa o ciclo de tratamento (criar → decidir) exigido pelo critério 13.
    await dialogo.getByRole("button", { name: "Aprovar" }).click();
    await expect(dialogo.getByText("Aprovado")).toBeVisible({ timeout: 10_000 });

    // Cancelamento nunca remove da lista (mesmo depois de fechar/reabrir o diálogo) — confere via API.
    const tratamentosNaApi = await request.get(`${URL_API}/v1/tratamentos`, {
      headers: { Authorization: `Bearer ${token}`, "X-Tenant": TENANT },
      params: { vinculoId, de: dia, ate: dia },
    });
    expect(tratamentosNaApi.ok()).toBeTruthy();
    const tratamentoCriado = (await tratamentosNaApi.json()).dados.find(
      (item: { motivo?: string }) =>
        item.motivo === "Justificativa registrada via E2E Playwright (T10).",
    );
    expect(
      tratamentoCriado,
      "tratamento criado pela UI não apareceu em GET /v1/tratamentos",
    ).toBeTruthy();
    expect(["aprovado", "aplicado"]).toContain(tratamentoCriado.status);

    await page.getByRole("button", { name: "Fechar" }).click();
    await expect(dialogo).toBeHidden();

    // T11 — recálculo sob demanda: dispara para o vínculo selecionado (nenhuma
    // tentativa de consultar status por identificador, endpoint inexistente).
    await page.getByRole("button", { name: /^Recalcular/ }).click();
    const dialogoRecalculo = page.getByRole("dialog");
    await expect(dialogoRecalculo).toBeVisible();
    await dialogoRecalculo.getByRole("button", { name: "Recalcular", exact: true }).click();
    await expect(dialogoRecalculo.getByText(/recálculo solicitado/i)).toBeVisible({
      timeout: 10_000,
    });
  });
});
