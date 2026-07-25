# F00 — Relatório de Verificação da Fase 0

| | |
|---|---|
| **Fase** | F0 — Fundação e Contratos (🔒 bloqueante) |
| **Autor** | Agente de Reverificação da Fase 0 (2ª passada, integral) |
| **Data** | 2026-07-25 |
| **Ambiente** | Windows 11 · Python 3.12.10 · Node v24.14.0 · pnpm 10.33.0 · Docker CLI / Compose v5.1.0 (**daemon parado**) · Flutter ausente |
| **Veredito** | ✅ **Fase 0 pode ser dada como concluída**, com três reservas nomeadas na §10 que só um Docker no ar resolve. |

> Este relatório mostra saída real de comando. Onde algo não pôde ser
> verificado, está escrito que não pôde ser verificado e por quê. Não há
> nenhum "ok" sem evidência.
>
> Esta é a **segunda** verificação da Fase 0. A primeira reprovou. O registro do
> que aconteceu está preservado na §2, porque é memória útil do projeto.

---

## 1. Veredito em uma tela

| Bloco | Estado | Evidência |
|---|---|---|
| `packages/contracts/` (openapi, schema, models, erros, eventos, tokens, glossário) | 🟢 **Íntegro e coerente** | §8 — reconfirmado por amostragem, zero divergência |
| Vedação legal REP-P (imutabilidade + NSR) | 🟢 **Provada por leitura**, não por execução | §8.2 |
| As 7 decisões da RFC-001 | 🟢 **7 de 7 implementadas** | §3 |
| Dockerfiles citados pelo compose | 🟢 **6 de 6 existem**, com o *stage* `dev` do overlay | §4 |
| PCFs de F1, F2 e F9a | 🟢 **Zero referência inventada, zero colisão de ownership** | §5 |
| `apps/api` · `apps/worker` · `apps/device-gw` · `apps/facial-svc` · `apps/web` | 🟢 **Todas carregam e respondem** | §6.10 |
| `apps/mobile` | 🟡 **Só `README.md`** — conforme decisão D-01 (Flutter ausente) | §3, D-01 |
| Gates do CI reproduzidos localmente | 🟢 **Todos verdes** nas versões fixadas no CI | §6 |
| Segredos fora do git | 🟢 **Limpo** — 209 arquivos no commit, nenhum segredo | §7 |
| `docker compose build` · serviços `healthy` | ⚪ **Não verificável** — daemon parado | §9 |
| Alembic contra PostgreSQL 16 real | ⚪ **Não verificável** — só o modo *offline* rodou | §9 |
| CI verde no primeiro push | ⚪ **Não verificável** — não há commit no repositório | §9 |

**A leitura honesta.** O que faltava foi entregue e o que foi entregue é
coerente. As quatro apps que não existiam existem, sobem e respondem
healthcheck; o `worker` ganhou os dois pontos de entrada e o Dockerfile; os três
Pacotes de Contexto de Fase da Onda 1 foram auditados referência por referência
e **não citam um único artefato inexistente**. Não encontrei nenhum defeito que
exigisse correção — este relatório não corrige nada porque não havia o que
corrigir.

O que continua em aberto não é entrega faltando: é **verificação que exige
infraestrutura de verdade**. Está na §9 e na §10, nomeada uma a uma.

---

## 2. Histórico — a primeira verificação e por que ela reprovou

Registro deliberado. A Fase 0 foi verificada uma primeira vez em 25/07/2026 e
**reprovada**. O motivo não foi defeito de trabalho, e sim interrupção:

> **Dois agentes da onda de construção caíram por erro de rede (`ENOTFOUND`)**
> no meio da execução, deixando entregas pela metade. O agente de plataforma
> entregou `apps/api` completa e parou dentro de `apps/worker`; quatro das seis
> apps do monorepo (`apps/web`, `apps/device-gw`, `apps/facial-svc`,
> `apps/mobile`) simplesmente não chegaram a existir.

O primeiro relatório apontou isso corretamente, em vez de mascarar, e essa é a
razão de a [RFC-001](../rfc/RFC-001-divergencias-fase-0.md) existir. O que a
primeira passada registrou, e que continua valendo:

**Sete correções aplicadas naquela passada** (todas com defeito comprovado
antes e verificação depois — nenhuma é "melhoria"):

| # | Divergência | Onde | Situação |
|---|---|---|---|
| C-01 | `EmailStr` sem `email-validator` — a API não importava | `apps/api/pyproject.toml` | ✅ corrigida |
| C-02 | `ruff format` reprovava 16 arquivos (faltava `[tool.ruff]`) | `packages/contracts/pyproject.toml` + models | ✅ corrigida |
| C-03 | `tarefas/__init__.py` importava 2 módulos inexistentes | `apps/worker/worker/tarefas/` | ✅ corrigida |
| C-04 | `ruff ... tests` abortava com `E902` | `tests/` | ✅ corrigida |
| C-05a | defeito de tipo por reuso de variável | `apps/api/tools/gerar_do_contrato.py` | ✅ corrigida |
| C-05b | o CI não instalava `packages/contracts` | `.github/workflows/ci.yml` | ✅ corrigida |
| C-05c | `type: ignore` estreito demais | `apps/api/migrations/env.py` | ✅ corrigida |

**Sete divergências estruturais** que aquele agente deliberadamente **não**
corrigiu, por exigirem decisão de escopo, viraram a RFC-001 (D-01 a D-07). O
orquestrador as decidiu em 25/07/2026. A verificação de que cada decisão virou
código está na §3 deste relatório.

Nada do que foi verificado na primeira passada foi tomado como verdade aqui: a
coerência dos contratos foi **reconfirmada por amostragem** (§8) e todos os
comandos de aceite foram **reexecutados** (§6).

---

## 3. T1 — As sete decisões da RFC-001, uma a uma

| Decisão | Estado | Evidência |
|---|---|---|
| **D-01** | ✅ implementada | §3.1 |
| **D-02** | ✅ implementada | §3.2 |
| **D-03** | ✅ implementada | §3.3 |
| **D-04** | ✅ implementada | §3.4 |
| **D-05** | ✅ implementada | §3.5 |
| **D-06** | ✅ implementada | §3.6 |
| **D-07** | ✅ implementada | §3.7 |

### 3.1 D-01 — as quatro apps ausentes

Decisão: entregar `apps/web`, `apps/device-gw` e `apps/facial-svc` como
esqueletos executáveis; `apps/mobile` fica só com o `README.md`.

```
$ python -c "carrega cada app e conta as operacoes do proprio OpenAPI"
OK  apps/api         app.main:app      titulo='Ponto Eletronico - API v1'                operacoes=215  caminhos=140
OK  apps/device-gw   gateway.main:app  titulo='Ponto Eletronico - Gateway Control iD'    operacoes=13   caminhos=13
OK  apps/facial-svc  facial.main:app   titulo='Ponto Eletronico - Servico Facial'        operacoes=5    caminhos=5
```

As três **sobem e respondem healthcheck**, que é exatamente o que
`FASES-E-AGENTES.md` (F0, entrega 4) pede:

```
  api         GET /health   -> 200  {'status': 'ok', 'servico': 'ponto-api', 'versao': '0.1.0', 'ambiente': 'dev'}
  device-gw   GET /health   -> 200  {'status': 'ok', 'servico': 'ponto-device-gw', 'versao': '0.1.0', 'ambiente': 'dev'}
  facial-svc  GET /health   -> 200  {'status': 'ok', 'servico': 'ponto-facial-svc', 'versao': '0.1.0', ...}

  api         GET /ready    -> 503  PONTO-INT-003  dependencias: ["banco","redis"]
  device-gw   GET /ready    -> 503  PONTO-INT-003  dependencias: ["api","redis"]
  facial-svc  GET /ready    -> 503  PONTO-INT-003  "pesos do motor facial ausentes"
```

> O `503` em `/ready` **não é defeito**: é *fail-closed* correto. Sem banco, sem
> Redis e sem os pesos `.onnx`, a instância não está pronta e diz isso com o
> código do catálogo. O `healthcheck` do compose aponta para `/health`, não para
> `/ready` — decisão certa, senão nenhum contêiner ficaria `healthy` antes das
> dependências.

`apps/web` é Next.js 15 + React 19 + TypeScript 5.7 + Tailwind v4 (39 arquivos
versionáveis), e **constrói**:

```
$ pnpm build
   ▲ Next.js 15.5.x
   Creating an optimized production build ...
 ✓ Compiled successfully in 2.4s
   Checking validity of types ...
 ✓ Generating static pages (6/6)

Route (app)                                 Size  First Load JS
┌ ○ /                                      134 B         103 kB
├ ○ /_not-found                            992 B         104 kB
├ ƒ /api/health                            134 B         103 kB
├ ○ /eu                                    134 B         103 kB
└ ○ /painel                                134 B         103 kB
+ First Load JS shared by all             103 kB
BUILD_EXIT=0
```

`apps/mobile` tem exatamente 1 arquivo — `README.md`, 189 linhas — que declara
por que o projeto Flutter não foi criado (SDK ausente + decisão D-01) e registra
que `apps/mobile` **não é referenciado pelo compose nem por nenhum job do CI**.
Conferido: é verdade.

### 3.2 D-02 — pontos de entrada do worker

```
OK  apps/worker      worker.main.WorkerSettings / worker.scheduler.SchedulerSettings importam
    funcoes do worker   : 8
    cron do scheduler   : 2
```

Os **2 `cron_jobs`** do scheduler são exatamente os dois eventos do catálogo que
declaram `origem: scheduler` (`banco_horas.vencendo` e `terminal.offline`) e que,
na primeira passada, **não tinham produtor possível**. `apps/worker/Dockerfile`
existe (5.800 bytes) e tem os *stages* `base`, `dependencias`, `dev` e `runtime`.

### 3.3 D-03 — texto do critério de aceite

Decisão: corrigir o texto em `FASES-E-AGENTES.md` para incluir `--env-file`.
Conferido — `FASES-E-AGENTES.md:126`:

```
`docker compose --env-file infra/.env.example -f infra/docker-compose.yml config` válido
*(o `--env-file` é obrigatório: os segredos usam `${VAR:?}` e recusam resolver sem valor —
fail-fast deliberado, ver RFC-001 D-03)* · `docker compose build` sem erro ·
todos os serviços `healthy` em `docker ps` · `spectral lint openapi.yaml` sem erro ·
`alembic upgrade head && alembic downgrade base` contra PostgreSQL 16 real · CI verde no primeiro push.
```

### 3.4 D-04 — referências mortas a `app/schemas/gerado.py`

Decisão: apagar as três. Conferido:

```
$ grep -n "gerado" apps/api/pyproject.toml
95:# RFC-001 D-04: as tres isencoes de `app/schemas/gerado.py` (aqui, em
97:# nunca existiu: o gerador (tools/gerar_do_contrato.py) escreve em
133:# Routers da Fase 0: stubs longos, gerados a partir do OpenAPI.
```

As três diretivas (`[tool.ruff] extend-exclude`, `[[tool.mypy.overrides]]
module = "app.schemas.gerado"`, `[tool.coverage.run] omit`) **sumiram**. O que
restou é um comentário documentando a remoção — que é o registro certo. O
arquivo gerado continua sob `ruff`, `mypy` e cobertura, como a decisão pedia.

### 3.5 D-05 — `docs/rfc/README.md`

Existe, 218 linhas, com protocolo completo e template:

```
1:# RFC — Protocolo de mudança de contrato
21:## 1. Quando abrir uma RFC          63:## 3. Como escrever
51:## 2. O que fazer enquanto a RFC não é decidida
78:### 3.2 Template                    141:## 4. Quem decide
```

Os três ponteiros que apontavam para o arquivo (`design-tokens.json`,
`docs/adr/README.md:29`, `ADR-005:95`) agora têm alvo.

### 3.6 D-06 — PCFs da Onda 1 e `docs/backlog.md`

Existem os quatro artefatos: `docs/fases/F01-identidade-multitenant-rbac.md`
(732 linhas), `docs/fases/F02-cadastros-organizacionais-pessoas.md` (729),
`docs/fases/F09a-design-system.md` (552) e `docs/backlog.md` (86). A auditoria
de conteúdo — que é o item de maior valor desta verificação — está na §5.

Apareceu também uma **RFC-002** que não existia antes
([`docs/rfc/RFC-002-acoes-de-permissao-fora-do-check.md`](../rfc/RFC-002-acoes-de-permissao-fora-do-check.md)),
aberta pelo agente de processo ao escrever os PCFs. Ela é legítima e sua
premissa foi **verificada de forma independente** nesta passada (§5.3).

### 3.7 D-07 — nota no glossário

Decisão: deixar a divergência `datahoraMarcacao` × `marcacao_datahora` como está
e documentá-la. Conferido em `packages/contracts/glossario.md:425-437` — nota
nova na seção 3.2, puramente aditiva, referenciando a decisão:

> **`Comprovante.datahoraMarcacao` (API) × `comprovantes.marcacao_datahora` (banco).**
> Divergência de nomenclatura **deliberadamente mantida** — decisão do orquestrador em
> RFC-001 D-07, 25/07/2026. […] **este é o único campo do contrato em que a
> conversão camelCase → snake_case não é mecânica** […]

> ⚠️ **Registro de transparência.** `packages/contracts/` é congelado, e esta
> nota é uma **edição em artefato congelado**. Ela foi autorizada explicitamente
> pela decisão D-07 ("deixar como está, documentando no glossário") e é
> **aditiva**: não altera nenhuma definição existente, nenhum nome e nenhum
> comportamento. Os `mtime` confirmam que nada mais em `packages/contracts/` foi
> tocado durante as entregas novas — o glossário é de 14:25, os models de 14:05,
> e as entregas são de 14:34 a 14:47.

---

## 4. T2 — Todo Dockerfile citado pelo compose existe?

Esta era a **ressalva principal** da verificação anterior: `docker compose
config` valida interpolação, não a existência dos `Dockerfile`. Levantamento
feito sobre a configuração **resolvida** (`docker compose config`), serviço por
serviço, com o caminho já composto a partir do `context`:

```
===== base — 9 servicos =====
servico      build?  dockerfile                       target   existe?
api          sim     apps/api/Dockerfile              -        SIM
device-gw    sim     apps/device-gw/Dockerfile        -        SIM
facial-svc   sim     apps/facial-svc/Dockerfile       -        SIM
minio        nao     (imagem: minio/minio:RELEASE...) -        n/a
postgres     nao     (imagem: postgres:16-alpine)     -        n/a
redis        nao     (imagem: redis:7-alpine)         -        n/a
scheduler    sim     apps/worker/Dockerfile           -        SIM
web          sim     apps/web/Dockerfile              -        SIM
worker       sim     apps/worker/Dockerfile           -        SIM

===== base + overlay dev — 9 servicos =====
api          sim     apps/api/Dockerfile              dev      SIM | stage OK
device-gw    sim     apps/device-gw/Dockerfile        dev      SIM | stage OK
facial-svc   sim     apps/facial-svc/Dockerfile       dev      SIM | stage OK
scheduler    sim     apps/worker/Dockerfile           dev      SIM | stage OK
web          sim     apps/web/Dockerfile              dev      SIM | stage OK
worker       sim     apps/worker/Dockerfile           dev      SIM | stage OK
```

**6 de 6 serviços com `build` têm Dockerfile existente.** O overlay de
desenvolvimento pede `target: dev` nos seis, e **os seis Dockerfiles têm o
*stage* `dev`** — verificado procurando `AS dev` em cada arquivo, não presumido:

```
apps/api/Dockerfile:68          FROM dependencias AS dev
apps/worker/Dockerfile:83       FROM dependencias AS dev
apps/device-gw/Dockerfile:106   FROM dependencias AS dev
apps/facial-svc/Dockerfile:99   FROM dependencias AS dev
apps/web/Dockerfile:57          FROM base AS dev
```

A ressalva anterior está **fechada**. `docker compose build` deixaria de falhar
por arquivo ausente — o que ele fará de fato só se sabe com o daemon no ar (§9).

Como consequência, o job `docker` do CI passa a cobrir a stack inteira.
Simulação da lógica do job `deteccao` contra a árvore atual:

```
tem_python=true
tem_web=true
tem_openapi=true
tem_dockerfile=true
dockerfiles=["api","worker","device-gw","facial-svc","web"]

=> jobs que ficariam PULADOS: nenhum
```

---

## 5. T3 — Auditoria dos três PCFs da Onda 1

Este é o item de maior valor desta verificação: um PCF ruim só aparece quando a
Onda 1 já falhou. Cada PCF foi conferido contra os contratos, não lido por alto.

### 5.1 (a) As nove seções estão preenchidas com substância?

| PCF | Linhas | Palavras | 9 seções | Cabeçalho | Tarefas | "Pronto quando" | Aceite | Proibições |
|---|---|---|---|---|---|---|---|---|
| F01 | 732 | 5.284 | ✅ 9/9 | ✅ 6/6 | 11 | ✅ 11/11 | 14 | 13 |
| F02 | 729 | 5.161 | ✅ 9/9 | ✅ 6/6 | 11 | ✅ 11/11 | 14 | 14 |
| F09a | 552 | 4.375 | ✅ 9/9 | ✅ 6/6 | 10 | ✅ 10/10 | 13 | 15 |

Nenhuma seção abaixo de 79 palavras; nenhuma instrução em citação (`>`) do
`_TEMPLATE.md` sobrou por apagar; **toda** tarefa tem definição de pronto
objetiva. A seção 2 (contexto mínimo) tem 1.209–1.506 palavras nos três — dentro
da faixa de "3 a 8 parágrafos" densos que o template pede.

### 5.2 (b) Toda referência citada existe?

Esta é a verificação que importa: **referência inventada em PCF manda o agente
da Onda 1 procurar o que não existe.** Confrontei tudo programaticamente contra
`packages/contracts/`.

**Operações e permissões do `openapi.yaml`:**

```
===== F01: tabela de 29 operacoes (metodo + caminho + operationId + x-permissao) =====
  linhas conferidas: 29 | divergencias: 0

===== F02: operationIds por tag =====
  OK  empresas        PCF= 5 contrato= 5
  OK  unidades        PCF= 8 contrato= 8
  OK  organizacao     PCF=18 contrato=18
  OK  colaboradores   PCF= 8 contrato= 8
  OK  contratos       PCF= 8 contrato= 8
  OK  biometria       PCF= 5 contrato= 5
  OK  dispositivos    PCF= 6 contrato= 6
  operationIds inexistentes citados: 0
```

A tabela de 29 linhas da F01 confere **método, caminho, `operationId` e a
permissão `x-permissao`** de cada operação — as 29 batem exatamente com o
contrato, inclusive as permissões. A F02 declara 58 operações em 7 tags: a soma
real é 58. A F01 diz "29 operações + `GET /v1/admin/saude`, que já está
implementada e você não toca": a tag `admin` tem 9 operações, sendo uma
`obterSaude`, e a soma das quatro tags é 30. Confere.

**Schemas e componentes:**

```
  OK  Marcacao · ApuracaoDia · SaldoBancoHoras · ExtratoBancoHoras · Escala · EscalaCiclo · Turno
  OK  Problema · Importacao · ImportacaoCriar
  OK  components.parameters.{CabecalhoTenant, CabecalhoRequestId, CabecalhoIdempotencia}
  OK  components.responses.{Erro400, Erro401, Erro403, Erro404, Erro409, Erro422, Erro429}
  OK  components.securitySchemes.{bearerAuth, oauth2, apiKeyAuth}
```

**`schema.sql` — tabelas, domínios, constraints, funções, policies, roles, seções e colunas:**

```
schema.sql: 92 tabelas, 11 dominios, 7 funcoes, 182 indices

===== F01 =====
  OK  tabelas: 17 citados        OK  funcoes: 4 citados
  OK  policy: 1 citados          OK  roles: 3 citados
===== F02 =====
  OK  tabelas: 18 citados        OK  dominios: 10 citados
  OK  constraints: 7 citados     OK  indices: 2 citados
  OK  tabelas F6/F14 citadas em 'nao toca': 6 citados

===== secoes de schema.sql citadas =====
  OK secao 1 FUNCOES AUXILIARES E DOMINIOS     OK secao 5  PESSOAS
  OK secao 2 TENANCY                           OK secao 6  BIOMETRIA E DISPOSITIVOS
  OK secao 3 ORGANIZACAO                       OK secao 14 INTEGRACAO E API PUBLICA
  OK secao 4 IDENTIDADE, ACESSO E RBAC         OK secao 19 ROW LEVEL SECURITY
                                               OK secao 20 ROLES E PRIVILEGIOS
                                               OK secao 21 VERIFICACAO DO CONTRATO

===== 79 colunas citadas em 19 tabelas =====
  todas existem — TOTAL de referencias inexistentes em schema.sql: 0
```

Foram conferidas nominalmente, entre outras, `ck_empresas_matriz`,
`ck_unidades_geocerca_ponto`, `ck_contratos_dispensa`, `ex_vinculos_sobreposicao`,
`ex_colaborador_gestores_imediato`, `uq_dispositivo_vinculos_ativo`,
`uq_biometria_templates_versao`, `ix_colaboradores_nome_trgm`,
`pol_isolamento_tenant`, `fn_resolve_tenant`, `app_tenant_atual`,
`app_usuario_atual`, `fn_registro_imutavel`, e as roles `ponto_app`,
`ponto_leitura`, `ponto_suporte`. **Todas existem.**

**Catálogo de erros e eventos:**

```
codigos no catalogo errors.yaml: 112

  OK  F01 diz AUTH=13 | catalogo tem 13      OK  F02 diz DISP=6  | catalogo tem 6
  OK  F01 diz PERM=6  | catalogo tem 6       OK  F02 diz IMP=3   | catalogo tem 3
  OK  F01 diz TEN=5   | catalogo tem 5       OK  F02 diz LGPD=4  | catalogo tem 4
  OK  F02 diz VAL=11  | catalogo tem 11      OK  F02 diz GEO=3   | catalogo tem 3
  OK  F02 diz CONF=4  | catalogo tem 4       OK  F02 diz REDE=2  | catalogo tem 2
  OK  F02 diz REC=2   | catalogo tem 2

  OK  F01: 22 codigos PONTO-* citados — todos existem
  OK  F02: 19 codigos PONTO-* citados — todos existem
  OK  40 transversais citados em forma abreviada — todos existem

eventos: OK colaborador.admitido · colaborador.demitido · importacao.concluida
         OK banco_horas.vencendo · terminal.offline · webhook.desabilitado
```

**Glossário** — as 6 seções citadas (1, 1.1, 1.2, 3.1, 3.2, 6) existem; os 34
verbetes citados pelos três PCFs existem. A citação "nunca *banco
positivo/negativo*" corresponde à linha real da seção 6 ("banco de horas
negativo / positivo (como entidade) → **saldo devedor / saldo credor**").

**`design-tokens.json` — a F09a faz afirmações numéricas verificáveis, e todas conferem:**

```
  OK  $extensions: metodo · temas · contraste · paletaCategorica · acessibilidade
  pares de contraste: 124  (PCF afirma 124)    pares nao aprovados: 0
  menor ratio com exigido=4.5: 4.67  (PCF afirma 4.67)
  menor ratio com exigido=3  : 3.01  (PCF afirma 3.01)
  camada (z-index): 10 niveis — base, elevado, cabecalho, navegacao, sobreposicao,
                    dialogo, suspenso, dica, notificacao, depuracao   (PCF afirma 10)
  tema.claro : {fundo:8, texto:8, borda:5, acao:14, estado:24, grafico:11, sombra:3}
  tema.escuro: {fundo:8, texto:8, borda:5, acao:14, estado:24, grafico:11, sombra:3}
       (PCF afirma exatamente esses sete números, e os mesmos caminhos nos dois temas)
  series de grafico: 8 + grade/eixo/rotulo   (PCF afirma 8)
  estilos tipograficos compostos: 10         (PCF afirma 10)
```

Também conferidas as afirmações da F09a sobre o esqueleto `apps/web`:
`tokens.gerado.css` tem **967 linhas** e **84 primitivos** (exatamente o que o
PCF diz); as 10 classes `.estilo-*` são emitidas a partir da linha 537, em
`kebab-case`, dentro de `@layer components`; `--dimensao-altura-controle` é
36px, `-compacta` 28px e `-toque` 44px; **não existe `tailwind.config.js`**;
Storybook **não** está instalado (o PCF diz que instalá-lo é entrega da fase).

**Caminhos de arquivo.** Dos 91 caminhos literais citados nos três PCFs, 79
existem hoje. Os 12 restantes foram examinados um a um e **nenhum é referência
inventada**:

| Caminho | Natureza |
|---|---|
| `apps/api/app/core/seguranca.py`, `app/identidade/__init__.py`, `tests/f1/conftest.py`, `app/comum/__init__.py`, `app/comum/documentos.py`, `tests/f2/conftest.py`, `apps/worker/worker/tarefas/importacoes.py` | **arquivos que a própria fase cria** — citados na T1/T10 com conteúdo ou assinatura fixada |
| `migrations/seed_dev.py`, `migrations/versions/0001_inicial.py` | citados em caminho **relativo a `apps/api`**, onde existem |
| `apps/web/playwright.config.ts` | marcado no próprio PCF como *"(novo, se o test-runner exigir)"* |

**Conclusão de (b): zero referência inventada nos três PCFs.**

### 5.3 A RFC-002 confere

O PCF da F1 manda o agente **parar** a operação `definirConfiguracaoTenant` por
causa da RFC-002. Verifiquei a premissa de forma independente, porque um
bloqueio falso custa uma operação a menos na fase:

```
x-permissao distintos no contrato: 142   (PCF F01 T8 afirma 142)
fora do CHECK de permissoes.acao: ['banco_horas.configurar', 'fechamentos.reabrir',
                                   'marcacoes.ler_sensivel', 'tenants.configurar']
```

A RFC-002 está correta: são 142 valores, e exatamente 4 usam ação que o `CHECK`
de `permissoes.acao` recusa. **A RFC-002 continua sem decisão** — ver §10.

### 5.4 O `docs/backlog.md` é preciso

A T8 da F1 manda o agente completar "os 30" e diz que a lista está no backlog.
Se essa lista estivesse errada, a fase começaria com dado ruim. Reconstruí o
catálogo semeado a partir de `seed_dev.py` e confrontei com o contrato:

```
recursos no CATALOGO_PERMISSOES : 55   (backlog afirma 55)
codigos gerados pelo seed       : 200  (backlog afirma 200)
x-permissao exigidas pelo contrato: 142

EXIGIDAS E NAO SEMEADAS: 30  (backlog afirma 30)

  no backlog mas NAO faltam de fato    : nenhum
  faltam de fato mas AUSENTES do backlog: nenhum

  as 4 da RFC-002 estao entre as nao semeadas   : True
  as 4 citadas na T8 da F1 estao entre as nao semeadas: True
```

**A lista dos 30 no backlog está exata**, item por item.

### 5.5 (c) Os ownerships são mutuamente exclusivos?

Cruzei as oito listas de ownership exclusivo das três fases, par a par, tratando
`/**` como prefixo:

```
===== cruzamento dos ownerships exclusivos (F1 x F2 x F9a) =====
  colisoes encontradas nas listas exclusivas: 0

===== distribuicao por arvore =====
  apps/api        -> ['F01', 'F02']
  apps/web        -> ['F09a']
  apps/worker     -> ['F02']
```

**Zero colisão.** Dentro de `apps/api`, F1 e F2 se dividem por módulo e por
router sem sobreposição: a F1 fica em `app/identidade/**` e nos routers
`auth/tenants/admin/auditoria`; a F2 em `app/organizacao/**`, `app/pessoas/**`,
`app/biometria/**`, `app/importadores/**`, `app/comum/**` e nos outros sete
routers. `apps/web` é exclusivamente da F9a; `apps/worker` só é tocado pela F2.

Existem **exatamente dois** caminhos compartilhados entre fases, e os dois são
**declarados nos dois PCFs**, com regra de convivência explícita:

| Caminho | Regra declarada |
|---|---|
| `apps/api/pyproject.toml` | blocos delimitados `# --- F1 ---` / `# --- F2 ---`; proibido reordenar ou reformatar linha existente |
| `apps/api/app/core/seguranca.py` | conteúdo literal inicial fixado; quem chegar primeiro cria; só a F1/A3 preenche os corpos; mudança de assinatura exige RFC |

O segundo é o ponto mais delicado do desenho da Onda 1 — dois agentes criando o
"mesmo" arquivo. Verifiquei que o bloco literal é **byte a byte idêntico** nos
dois PCFs, e que ele é código válido que passa nos gates do CI:

```
$ sha256 do bloco ```python``` com 'class Sujeito'
sha256 F01: caaf1d72391cbec1db3d34e9007502055bd9e6bc530a003cdb5b11793c2d93f3
sha256 F02: caaf1d72391cbec1db3d34e9007502055bd9e6bc530a003cdb5b11793c2d93f3
IDENTICOS

$ python -c "ast.parse(bloco)"          -> sintaxe OK
$ ruff check  (line-length 100, py312)  -> All checks passed!
$ ruff format --check                   -> 1 file already formatted
```

As três "sobreposições" restantes detectadas pelo cruzamento são o mesmo arquivo
aparecendo na tabela exclusiva **e** na tabela "compartilhado dentro da fase" do
**mesmo** PCF (`app/comum/documentos.py`, `tests/f2/conftest.py`,
`componentes/ui/**`), cada uma com regra de quem edita. É esclarecimento, não
colisão.

### 5.6 (d) Os comandos da §8 são executáveis neste repositório?

Testei os que não dependem de infraestrutura ausente, e verifiquei a existência
dos alvos dos demais:

| Comando (§8) | PCF | Estado |
|---|---|---|
| `python tools/conferir_rotas.py` | F01, F02 | ✅ **executado** — `Inventario identico ao contrato (metodo, caminho e operationId).` |
| `from worker.tarefas import NOMES_DAS_TAREFAS` | F02 | ✅ **executado** — devolve 8 tarefas; o símbolo existe |
| `ruff check` / `ruff format --check` / `mypy` | F01, F02 | ✅ **executados** — §6.6 |
| `pytest tests/test_andaime.py` | F01, F02 | ✅ **executado** — §6.7 |
| `pnpm tokens:check` / `lint` / `typecheck` / `test` / `build` | F09a | ✅ **executados** — §6.5; os 5 scripts existem no `package.json` |
| `git status --short packages/contracts` | os três | ✅ executável |
| `.\tasks.ps1 up / lint / typecheck / lint-web / test-web` | os três | ✅ os 5 alvos existem em `tasks.ps1` |
| `make lint-web / test-web / typecheck` | F09a | ✅ os 3 alvos existem no `Makefile` |
| `docker compose ... up -d postgres redis` | F01, F02 | ✅ sintaxe válida, serviços `postgres` e `redis` existem nos dois arquivos — ⚪ **exige daemon** |
| `alembic upgrade head && alembic downgrade base` | F01 | ⚪ **exige PostgreSQL real** |
| `pnpm build-storybook` / `pnpm test:storybook` | F09a | ⚪ scripts a criar na T1 da própria fase — correto |

> Nota sobre a F02: a saída esperada declarada para `NOMES_DAS_TAREFAS` é **9**
> (as 8 do andaime **mais** `importar_colaboradores`). Hoje são 8. Isso está
> **certo**: a nona tarefa é entrega da T10 da própria F02.

### 5.7 Observações de julgamento (não são defeitos)

Não corrigi nada aqui — são pontos de estilo, registrados para o orquestrador
decidir se quer mexer:

1. **F01, §7**: a numeração dos critérios vai `1..6`, depois `6.1`, depois
   `7..13` — 14 itens numerados até 13. Como a §7 pede que "o relatório final
   responda item a item", um `6.1` intercalado pode gerar confusão de contagem.
   Não é ambíguo, apenas incomum.
2. **F09a, §8**: não traz bloco `powershell`, ao contrário dos outros dois. O
   próprio PCF explica por quê ("os comandos são idênticos no Windows e no
   Linux/macOS porque tudo passa por `pnpm`") e nomeia os alvos equivalentes de
   `make` e `tasks.ps1`. Está em conformidade com o template.
3. **F01, T1 e F02, T1**: as duas *fixtures* mandam subir PostgreSQL via
   `docker compose`. **A Onda 1 não começa sem o daemon do Docker no ar** — o
   que hoje não é o caso neste ambiente. Isso não é defeito de PCF; é
   dependência operacional, e está na §10.

---

## 6. T4 — Aceite integral, saída real de cada comando

### 6.1 `docker compose config` — 🟢

```
$ docker compose --env-file infra/.env.example -f infra/docker-compose.yml config
EXIT=0   (585 linhas de configuracao resolvida, stderr vazio)

$ docker compose --env-file infra/.env.example \
    -f infra/docker-compose.yml -f infra/docker-compose.dev.yml config --quiet
EXIT=0

$ docker compose --env-file infra/.env.example -f infra/docker-compose.yml config --services
facial-svc · minio · postgres · redis · api · device-gw · scheduler · web · worker   (9)
```

Sem `--env-file` o comando **continua falhando de propósito**
(`required variable REDIS_PASSWORD is missing a value`), que é o *fail-fast*
deliberado dos segredos — e o texto do critério de aceite já reflete isso (D-03).

### 6.2 Validação do `openapi.yaml` — 🟢

```
$ python -m openapi_spec_validator packages/contracts/openapi.yaml
packages/contracts/openapi.yaml: OK
EXIT=0
```

O CI usa spectral e **não há `.spectral.yaml` no repositório**, então ele cai no
*fallback* `extends: ["spectral:oas"]`. Reproduzido exatamente assim, na mesma
versão e severidade:

```
$ npx @stoplight/spectral-cli@6.14.2 lint packages/contracts/openapi.yaml \
    --ruleset /tmp/spectral-padrao.yaml --fail-severity=warn --format=pretty

0 Unique Issue(s)
✖
No results with a severity of 'warn' or higher found!
SPECTRAL_EXIT=0
```

### 6.3 `python -m json.tool design-tokens.json` — 🟢

```
$ python -m json.tool packages/contracts/design-tokens.json
EXIT=0        (3.795 linhas, formato W3C Design Tokens)
```

### 6.4 Importação do pacote de models — 🟢

```
$ python -c "import ponto_contracts as c; ..."
pacote instalado : ponto_contracts 0.1.0
tabelas          : 92
colunas          : 1808
indices          : 182
constraints      : 708
EXIT=0
```

### 6.5 `apps/web` — 🟢 (era impossível de rodar na passada anterior)

```
$ pnpm install --frozen-lockfile
Lockfile is up to date, resolution step is skipped
Done in 1.1s using pnpm v10.33.0
INSTALL_EXIT=0

$ npx tsc --noEmit
TSC_EXIT=0

$ pnpm lint            # eslint . --max-warnings=0
LINT_EXIT=0

$ pnpm tokens:check    # node scripts/tokens-para-css.mjs --check
tokens.gerado.css em dia (sha256:3a23f37a0c46).
TOKENS_EXIT=0

$ pnpm test            # vitest run
 ✓ src/testes/andaime.teste.tsx (4 tests) 97ms
 Test Files  1 passed (1)
      Tests  4 passed (4)
TEST_EXIT=0

$ pnpm build           # next build
 ✓ Compiled successfully in 2.4s
 ✓ Generating static pages (6/6)
BUILD_EXIT=0
```

### 6.6 `ruff` e `mypy` a partir da raiz — 🟢

```
$ ruff --version
ruff 0.7.4                                    (versao fixada no CI)

$ ruff check apps packages tests
All checks passed!
RUFF_CHECK_EXIT=0

$ ruff format --check apps packages tests
105 files already formatted                   (eram 81; +24 das apps novas)
RUFF_FMT_EXIT=0

$ mypy --version
mypy 1.13.0 (compiled: yes)                   (versao fixada no CI)

$ mypy apps packages
Success: no issues found in 125 source files  (eram 101; +24 das apps novas)
MYPY_EXIT=0
```

> As três apps novas entraram no `mypy --strict` e no `ruff` **sem uma única
> exceção nova**. Instalei `apps/worker`, `apps/device-gw` e `apps/facial-svc` no
> ambiente reproduzindo o laço de instalação do CI, senão o `mypy` reprovaria por
> dependência ausente e não por defeito.

### 6.7 `pytest` — 🟢

```
$ pytest -q                                   (a partir da raiz, como o job test-python)
.......................................................                  [100%]
55 passed, 1 warning in 11.79s
PYTEST_RAIZ_EXIT=0
```

Distribuição por app:

```
     13 apps/api
     21 apps/device-gw
     10 apps/facial-svc
     11 apps/worker
```

Regressão do andaime (`apps/api`), isolada:

```
$ cd apps/api && pytest -q
.............                                                            [100%]
PYTEST_API_EXIT=0
```

E o inventário de rotas contra o contrato:

```
$ cd apps/api && python tools/conferir_rotas.py
contrato : 215 operacoes em 140 caminhos
aplicacao: 215 operacoes em 140 caminhos
Inventario identico ao contrato (metodo, caminho e operationId).
EXIT=0
```

### 6.8 Alembic nos dois sentidos (modo *offline*) — 🟢

O comando cru **falha**, e isso é correto:

```
$ cd apps/api && alembic upgrade head --sql
RuntimeError: URL do banco nao definida. Informe DATABASE_URL_SYNC, DATABASE_URL
ou rode com `alembic -x url=postgresql+psycopg://usuario:senha@host/base`.
```

Mesmo *fail-fast* do compose: `migrations/env.py` recusa adivinhar destino. Com a
URL publicada por variável de ambiente (nada versionado — o modo *offline* não
abre conexão):

```
$ DATABASE_URL_SYNC=... alembic upgrade head --sql
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Generating static SQL
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_inicial
EXIT=0        3.812 linhas de DDL — 95 CREATE TABLE, 182 indices, 22 CREATE TRIGGER

$ DATABASE_URL_SYNC=... alembic downgrade head:base --sql
INFO  [alembic.runtime.migration] Running downgrade 0001_inicial ->
EXIT=0        254 linhas — 93 DROP TABLE

$ alembic heads
0001_inicial (head)
```

> **`--sql` prova que a migration *gera* SQL nos dois sentidos. Não prova que
> aplica.** O modo *offline* não executa `DO $$`, não cria partição e não impõe
> constraint. O critério de aceite real é `alembic upgrade head && alembic
> downgrade base` contra um PostgreSQL 16 de verdade. Ver §9.

### 6.9 Validação YAML de todo o repositório — 🟢

```
OK    .github/workflows/ci.yml
OK    .github/workflows/security.yml
OK    apps/web/pnpm-lock.yaml
OK    infra/docker-compose.dev.yml
OK    infra/docker-compose.yml
OK    packages/contracts/errors.yaml
OK    packages/contracts/events.yaml
OK    packages/contracts/openapi.yaml

Total: 8 arquivos | OK: 8 | Falhas: 0
EXIT=0
```

### 6.10 Carga de cada app — 🟢

```
OK  apps/api         app.main:app       operacoes=215  caminhos=140
OK  apps/device-gw   gateway.main:app   operacoes=13   caminhos=13
OK  apps/facial-svc  facial.main:app    operacoes=5    caminhos=5
OK  apps/worker      worker.main.WorkerSettings / worker.scheduler.SchedulerSettings importam
    funcoes do worker   : 8
    cron do scheduler   : 2
    tarefas registradas : ('apurar_dia', 'recalcular_periodo', 'gerar_afd', 'gerar_aej',
                           'executar_relatorio', 'enviar_webhook', 'sincronizar_terminal',
                           'expurgo_lgpd')
```

Healthchecks declarados no compose conferidos contra os endpoints reais: `api`,
`device-gw` e `facial-svc` apontam para `/health` (que responde 200 sem
dependência); `web` para `/api/health`, que existe em
`apps/web/src/app/api/health/route.ts`; `worker` e `scheduler` usam
`arq --check $ARQ_WORKER_SETTINGS`.

> Detalhe que parece defeito e não é: o serviço `scheduler` define
> `ARQ_WORKER_SETTINGS: ${ARQ_SCHEDULER_SETTINGS:-worker.scheduler.SchedulerSettings}`.
> Ou seja, dentro do contêiner do scheduler a variável `ARQ_WORKER_SETTINGS`
> carrega o caminho **do scheduler**, o que faz uma única expressão de
> healthcheck servir aos dois serviços. Nomenclatura confusa, comportamento
> correto.

---

## 7. T5 — Segredos

### 7.1 Varredura do repositório inteiro

211 arquivos varridos (excluídos `.git`, `node_modules`, `.venv` e caches), 13
padrões: chave privada PEM, certificado, PKCS12, AWS (id e secret), GitHub,
Slack, Google, Stripe, OpenAI/Anthropic, JWT, URL com credencial e atribuição
literal de senha/token.

**12 ocorrências, todas conferidas uma a uma, nenhuma é segredo:**

| Onde | O quê | Julgamento |
|---|---|---|
| `.github/workflows/ci.yml:231-232` | `ponto:ponto_ci@localhost` | senha do contêiner efêmero de teste do CI, descartado ao fim do job |
| `apps/api/app/core/config.py:54` | `ponto:ponto@localhost` | valor padrão de desenvolvimento local |
| `apps/worker/worker/config.py:53` | `ponto:ponto@localhost` | idem |
| `apps/device-gw/gateway/config.py:62` | `ponto:ponto@localhost` | idem — **ocorrência nova**, da app nova; mesmo padrão das demais |
| `apps/api/migrations/{env.py:99, README.md:40-41, seed_dev.py:41}` | `usuario:senha@host`, `ponto:***@` | exemplos em docstring |
| `infra/.env.example:95` | `ponto:troque-me@localhost` | placeholder do arquivo de exemplo |
| `packages/contracts/openapi.yaml:22448,22499` | JWT de exemplo | decodificado abaixo — sintético |

O JWT foi decodificado, não presumido:

```
{'alg': 'RS256', 'kid': 'k1'}
{'sub': 'usr', 'tenant': 'seeg'}
```

`infra/.env.example` conferido linha a linha: todo valor sensível é
`troque-me`, `troque-me-tambem`, `troque-me-no-minio`, `troque-me-no-terminal`
ou `troque-me-token-push`; as chaves reais apontam para caminhos montados em
runtime (`/run/secrets/jwt/private.pem`, `/run/secrets/jwt/public.pem`). O único
item que a heurística marcou — `JWT_KEYS_DIR = ./keys` — é caminho de diretório,
não segredo.

Nenhum arquivo `.pem`, `.key`, `.pfx`, `.p12` ou `.env` existe no disco.
`infra/keys/` não existe (só nasce com `make keys`).

**Nenhum segredo removido, porque nenhum foi encontrado.**

### 7.2 Prova exigida

```
$ git check-ignore -v infra/.env
.gitignore:11:*.env     infra/.env
```

Cobertura do `.gitignore` conferida item a item, incluindo os artefatos novos:

```
  IGNORADO   .env                              -> .gitignore:11:*.env
  IGNORADO   infra/.env                        -> .gitignore:11:*.env
  IGNORADO   .env.local                        -> .gitignore:10:.env.*
  IGNORADO   chave.pem                         -> .gitignore:15:*.pem
  IGNORADO   segredo.key                       -> .gitignore:16:*.key
  IGNORADO   certs/ecnpj.pfx                   -> .gitignore:18:*.pfx
  IGNORADO   id_rsa                            -> .gitignore:33:id_rsa
  IGNORADO   infra/keys/private.pem            -> .gitignore:39:infra/keys/
  IGNORADO   apps/api/.venv/                   -> .gitignore:151:.venv/
  IGNORADO   apps/device-gw/.mypy_cache/       -> .gitignore:169:.mypy_cache/
  IGNORADO   apps/web/node_modules/            -> apps/web/.gitignore:3:node_modules/
  IGNORADO   apps/web/.next/                   -> apps/web/.gitignore:4:.next/
  IGNORADO   apps/web/tsconfig.tsbuildinfo     -> apps/web/.gitignore:8:*.tsbuildinfo
  VERSIONADO apps/web/pnpm-lock.yaml                    (correto: lockfile entra)
  VERSIONADO apps/web/src/estilos/tokens.gerado.css     (correto: `tokens:check` o confere)
  VERSIONADO apps/web/src/lib/api/tipos.gerado.ts       (correto: gerado e versionado)
```

Conteúdo real do commit, medido com `git ls-files --others --exclude-standard`
em vez de deduzido das regras:

```
total: 209 arquivos

--- infra/.env.example esta na lista? ---
177:infra/.env.example                     (SIM — versionado, como deve)

--- algum .env real, .pem, .key, .pfx entraria? ---
NENHUM

--- distribuicao ---
    149 apps        (api 60 · web 39 · worker 18 · device-gw 17 · facial-svc 14 · mobile 1)
     28 packages     18 docs      3 infra      2 .github      1 tests
```

> ⚠️ **`git log` continua vazio: o branch `main` não tem nenhum commit.**
> Nada foi versionado ainda — coerente com a regra de que o orquestrador cuida
> do git, mas significa que "CI verde no primeiro push" segue sendo previsão.

---

## 8. Reconfirmação por amostragem dos contratos

A primeira passada confrontou os contratos exaustivamente e achou zero
divergência. Aqui a checagem foi **por amostragem**, para confirmar que nada
regrediu:

```
=== schema.sql x models (nomes de tabela) ===
  schema.sql: 92 | models: 92
  so no schema.sql: []          so nos models: []

=== vedacao legal REP-P ===
  OK  trg_marcacoes_bloqueia_update   (schema.sql e migration 0001)
  OK  trg_marcacoes_bloqueia_delete   (schema.sql e migration 0001)
  OK  fn_registro_imutavel            (22x em schema.sql)
  OK  uq_nsr_emissoes / uq_marcacoes_nsr / ck_nsr_sequencias_coerencia
  OK  pol_isolamento_tenant           (8x)
  OK  ERRCODE 42501 presente

=== nenhum endpoint muta marcacao ===
  operacoes PUT/PATCH/DELETE sobre /marcacoes: 0
  total de PUT/PATCH/DELETE no contrato: 41

=== fechamento errors.yaml x openapi x codigo ===
  catalogo: 112 | openapi cita: 112 | codigo apps/ cita: 112
  citados no openapi FORA do catalogo: nenhum
  citados no codigo  FORA do catalogo: nenhum
  do catalogo nunca citados          : nenhum
```

Fechamento perfeito nos dois sentidos, com as três apps novas já dentro da
contagem de código. **Nada regrediu.**

---

## 9. O que NÃO pôde ser verificado, e por quê

| Critério de aceite | Por que não foi verificado | Como verificar |
|---|---|---|
| `docker compose build` sem erro | **Daemon parado**: `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine`. Os 6 Dockerfiles agora **existem** e têm o *stage* `dev` (§4), o que remove a causa conhecida de falha — mas build não executado é build não provado. | Subir o Docker Desktop e `make build` |
| Todos os serviços `healthy` em `docker ps` | mesma causa | `make up && docker ps` |
| `alembic upgrade head && alembic downgrade base` **contra PostgreSQL 16 real** | precisa do serviço `postgres` no ar. O modo *offline* roda (§6.8), mas não executa `DO $$`, não cria partição e não impõe constraint. | `make up && make migrate` |
| Gatilho de imutabilidade **em execução** | precisa de banco. Provado por leitura nos dois artefatos (§8), não por `UPDATE` que falha. | teste da F5 |
| RLS isolando tenant A de tenant B **em execução** | precisa de banco. | T3 da F1 — o PCF já especifica o teste adversarial |
| Sequência de NSR sob concorrência | precisa de banco. | teste da F5 |
| `CI verde no primeiro push` | não há commit (`git log` vazio) e o GitHub Actions nunca rodou. Todos os gates foram reproduzidos localmente nas versões fixadas no CI (ruff 0.7.4, mypy 1.13.0, spectral 6.14.2, Node 24, pnpm 10.33). | primeiro push |
| Esqueleto Flutter | Flutter não instalado — e a decisão D-01 dispensou `apps/mobile` de ter projeto nesta fase. | F7 |

---

## 10. Pendências

### Bloqueiam o *fechamento formal* da Fase 0 (só dependem de infraestrutura)

1. **Subir o Docker e rodar `docker compose build`** para as 5 imagens, mais
   `docker ps` com todos os serviços `healthy`.
2. **`alembic upgrade head && alembic downgrade base` contra PostgreSQL 16
   real.** É o único critério de aceite da F0 que o modo *offline* não substitui.
3. **Primeiro commit e primeiro push**, para transformar "CI reproduzido
   localmente" em "CI verde".

> Nenhum dos três depende de escrever código. São execuções.

### Precisam de decisão antes ou durante a Onda 1

4. **Decidir a [RFC-002](../rfc/RFC-002-acoes-de-permissao-fora-do-check.md).**
   Quatro `x-permissao` do contrato usam ações que o `CHECK` de
   `permissoes.acao` recusa. O PCF da F1 já instrui o agente a **parar** a
   operação `definirConfiguracaoTenant` e seguir — então a Onda 1 **pode
   começar** sem essa decisão, mas ela custa 1 operação da F1 enquanto não vier,
   e as outras três caem em F4, F5 e F10.
5. **Docker no ar é pré-requisito da Onda 1**, não só do fechamento da F0: a T1
   da F1 e a T1 da F2 sobem PostgreSQL nas *fixtures*, e os PCFs proíbem
   explicitamente pular teste de RLS por falta de banco ("teste de RLS pulado
   por falta de banco **não conta como verde**").
6. **Concessão temporária do CI.** `.github/workflows/ci.yml:31-32` diz:
   *"REMOVER após o fim da Fase 0: com o monorepo completo, os `if:` devem
   cair"*. As cinco condicionais `if: needs.deteccao...` hoje **avaliam todas
   como verdadeiras** (§4), então nada é pulado — mas o gatilho de remoção é
   exatamente este momento. Não removi: alterar o CI é ownership do
   orquestrador, e a mudança é de política, não conserto de defeito.

### Herdadas para as fases donas (já registradas em `docs/backlog.md`)

7. **F5** — teste adversarial de imutabilidade (`UPDATE`/`DELETE` em `marcacoes`
   devem falhar com `42501`) e NSR de 1 a 10.000 sem buraco sob concorrência.
8. **F1** — teste de RLS provando isolamento inclusive por SQL direto; e
   completar as **30** permissões não semeadas (lista exata e conferida em
   `docs/backlog.md`).
9. **F2** — nona tarefa do worker (`importar_colaboradores`), sem a qual
   `importacao.concluida` não tem produtor.
10. **F13** — `webhook.desabilitado` é o único evento do catálogo sem citação
    fora do `events.yaml`; garantir que ganhe produtor.
11. **F12** — conferir o leiaute do AFD/AEJ campo a campo contra os anexos da
    Portaria 671/2021 antes de codificar. **Nada nesta verificação toca nisso**:
    ela conferiu coerência interna do contrato, não conformidade com a norma.
12. **F15** — não existe verificador automático de que `packages/contracts/`
    permanece congelado. Um job comparando o hash dos seis artefatos fecharia a
    brecha.
13. **Fora do código** — e-CNPJ A1 ICP-Brasil, registro INPI, um iDFace físico e
    a formalização do acordo de banco de horas da SEEG. Nenhum bloqueia código;
    os quatro bloqueiam homologação.

---

## 11. Correções aplicadas nesta passada

**Nenhuma.**

Meu mandato permitia corrigir qualquer arquivo, desde que o defeito fosse real e
comprovado. Procurei defeito em sete frentes — decisões da RFC-001, caminhos de
Dockerfile, referências dos PCFs, exclusividade de ownership, executabilidade
dos comandos, os dez comandos de aceite e a varredura de segredos — e **não
encontrei nenhum que exigisse correção**. Registrar isso é mais honesto do que
inventar uma melhoria para parecer produtivo.

As três observações de julgamento da §5.7 e a concessão do CI da §10.6 foram
deliberadamente **não** alteradas: são decisão de estilo ou de política, não
conserto.

O ambiente foi alterado (instalei `apps/worker`, `apps/device-gw`,
`apps/facial-svc`, `apps/api` e `openapi-spec-validator` no `.venv`, reproduzindo
o laço de instalação do CI). **Nenhum arquivo versionável do repositório foi
tocado por esta verificação** — confirmado por `mtime` contra os 209 arquivos que
entrariam no commit.

---

## 12. Veredito final

✅ **A Fase 0 pode ser dada como concluída.**

O que a Fase 0 existia para produzir — um contrato congelado, coerente e
completo, mais um andaime executável para todas as apps — **existe e está
verificado**:

- os contratos fecham em 92 tabelas, 1.808 colunas, 215 operações, 140 caminhos,
  112 códigos de erro e 22 eventos, sem uma divergência;
- as seis apps do monorepo existem; cinco sobem e respondem healthcheck, e a
  sexta (`apps/mobile`) está formalmente dispensada pela decisão D-01;
- os 6 Dockerfiles citados pelo compose existem, com o *stage* `dev` do overlay —
  a ressalva principal da verificação anterior está fechada;
- as 7 decisões da RFC-001 viraram código, todas verificadas com evidência;
- os 10 comandos de aceite rodam verdes, com saída real colada na §6;
- nenhum segredo entraria no commit;
- e os três PCFs da Onda 1 — o mecanismo que impede o agente de fase de ler o
  repositório inteiro — foram auditados referência por referência: **zero
  referência inventada, zero colisão de ownership, comandos executáveis**.

**O que ainda depende de Docker/PostgreSQL reais, exatamente:**

| # | Pendência | Depende de |
|---|---|---|
| 1 | `docker compose build` das 5 imagens | daemon do Docker |
| 2 | Todos os serviços `healthy` em `docker ps` | daemon do Docker |
| 3 | `alembic upgrade head && alembic downgrade base` **aplicado** | PostgreSQL 16 no ar |
| 4 | Gatilho de imutabilidade falhando de verdade com `42501` | PostgreSQL 16 no ar *(teste é da F5)* |
| 5 | RLS recusando leitura cross-tenant de verdade | PostgreSQL 16 no ar *(teste é da F1)* |
| 6 | "CI verde no primeiro push" | um commit e um push |

**A ressalva que separa "concluída" de "homologada".** Os seis itens acima não
são entrega faltando: são **execuções pendentes**, todas bloqueadas por
infraestrutura ausente no ambiente de verificação, não por trabalho não feito.
Recomendo aprovar a Fase 0 e disparar a Onda 1 **assim que o daemon do Docker
estiver no ar** — porque os itens 3, 4 e 5 são também pré-requisito da própria
Onda 1: a T1 da F1 e a T1 da F2 sobem PostgreSQL nas *fixtures*, e os dois PCFs
proíbem explicitamente contar como verde um teste de banco que foi pulado.

Se o Docker subir e os itens 1 a 3 passarem, a Fase 0 estará **integralmente**
verificada, sem nenhuma ressalva.
