# RFC-001 — Divergências encontradas na verificação da Fase 0

| | |
|---|---|
| **Status** | ✅ **Decidida** em 25/07/2026 pelo orquestrador — ver §Decisão no fim |
| **Autor** | Agente de Verificação da Fase 0 |
| **Data** | 2026-07-25 |
| **Fases impactadas** | F0 (fechamento), Onda 1 inteira (F1, F2, F9a), F6, F7, F8 |
| **Relatório completo** | [docs/fases/F00-RELATORIO.md](../fases/F00-RELATORIO.md) |

Este documento registra apenas as divergências que **exigem decisão de
arquitetura ou de escopo** e que, por isso, o agente de verificação
deliberadamente **não corrigiu**. As divergências triviais já foram corrigidas e
estão listadas no relatório da fase, não aqui.

O protocolo de RFC está em `FASES-E-AGENTES.md` §1.3.

---

## D-01 · Quatro das seis apps do monorepo não existem 🔴 Bloqueante

**O que está errado.** `FASES-E-AGENTES.md` (F0, entrega 4) pede "esqueletos
executáveis de todas as apps (sobem e respondem healthcheck com stubs)".
Existem apenas `apps/api/` e `apps/worker/`. Não existem:

| Caminho | Referenciado por | Consequência |
|---|---|---|
| `apps/web/` | `infra/docker-compose.yml:469-474`, `ci.yml` (job `web`), `Makefile` (`lint-web`, `test-web`, `typecheck`) | `docker compose build web` falha; comando de aceite `npx tsc --noEmit` impossível |
| `apps/device-gw/` | `infra/docker-compose.yml:421-425` | `docker compose build device-gw` falha |
| `apps/facial-svc/` | `infra/docker-compose.yml:227-231` | `docker compose build facial-svc` falha |
| `apps/mobile/` | `PROJETO.md` §11.3 | esqueleto Flutter previsto para a F0 não existe |

`docker compose config` **passa** mesmo assim, porque `config` só resolve
interpolação de variáveis — ele não confere a existência do `dockerfile`. O
erro só apareceria em `docker compose build`, que não pôde rodar aqui (daemon
parado).

**Por que não corrigi.** Criar quatro aplicações é entrega, não conserto de
defeito. Fora do mandato do agente de verificação.

**Decisão pedida.** Uma das três:

1. Reabrir a F0 com o agente de plataforma para entregar os quatro esqueletos.
2. Mover os quatro esqueletos para o começo da Onda 1 e aceitar a F0 parcial —
   com a ressalva de que **F9a (Design System) e F8 dependem de `apps/web`** e
   ficam bloqueadas até que exista.
3. Reduzir o escopo declarado da F0 (e ajustar `FASES-E-AGENTES.md`), assumindo
   explicitamente que `device-gw` nasce na F6, `facial-svc` na F7 e `mobile` na
   F7.

**Recomendação.** Opção 1 para `apps/web` (bloqueia três fases da Onda 1) e
opção 3 para `device-gw`, `facial-svc` e `mobile`, cujas fases donas estão nas
Ondas 2 e 3. Se a opção 3 for aceita, os serviços correspondentes precisam sair
do `docker-compose.yml` ou ganhar `profiles:` para não quebrar `build`.

---

## D-02 · `apps/worker` não tem ponto de entrada 🔴 Bloqueante

**O que está errado.** O pacote `worker` declara na própria docstring
(`worker/__init__.py`) que dois processos saem dele:

```
worker    -> arq worker.main.WorkerSettings
scheduler -> arq worker.scheduler.SchedulerSettings
```

Nenhum dos dois módulos existe. Também não existe `apps/worker/Dockerfile`.
Ambos são referenciados por:

* `infra/docker-compose.yml:338` e `:383` — `dockerfile: apps/worker/Dockerfile`
* `infra/docker-compose.yml:344` — `command: ["arq", "${ARQ_WORKER_SETTINGS:-worker.main.WorkerSettings}"]`
* `infra/docker-compose.yml:389` — `command: ["arq", "${ARQ_SCHEDULER_SETTINGS:-worker.scheduler.SchedulerSettings}"]`
* `infra/.env.example:190-193` — os dois valores padrão

**Consequência prática.** Os serviços `worker` e `scheduler` não sobem. Dois
eventos do catálogo (`banco_horas.vencendo` e `terminal.offline`) declaram
`origem: scheduler` e portanto **não têm produtor possível** enquanto o
`scheduler` não existir.

**O que corrigi.** Apenas o defeito que já existia dentro do que foi entregue:
`worker/tarefas/__init__.py` importava `worker.tarefas.integracoes` e
`worker.tarefas.lgpd`, ambos inexistentes, o que tornava o pacote inteiro
impossível de importar. Criei os dois módulos de andaime seguindo exatamente o
padrão dos três já entregues (`resultado_nao_implementado` com
`PONTO-INT-005`). As 8 tarefas do catálogo agora importam.

**Por que não corrigi o resto.** `main.py`, `scheduler.py` e `Dockerfile` são
os pontos de entrada da aplicação — entrega do agente de plataforma, não
conserto pontual. Além disso, criar só o `main.py` não tornaria o serviço
funcional, já que o `Dockerfile` continuaria faltando.

**Decisão pedida.** Mesma da D-01: completar na F0 ou realocar formalmente.

---

## D-03 · O comando de aceite `docker compose config` falha como está escrito 🟡

**O que está errado.** `FASES-E-AGENTES.md` (F0, Aceite) diz
"`docker compose config` válido". Rodado literalmente, ele **falha**:

```
error while interpolating services.api.environment.REDIS_URL:
required variable REDIS_PASSWORD is missing a value: defina REDIS_PASSWORD
```

A causa não é defeito do compose: é a sintaxe `${VAR:?mensagem}`, deliberada,
que recusa subir sem segredo definido. O `ci.yml` já sabe disso e roda
`docker compose --env-file infra/.env.example -f ... config --quiet`, que passa.

**Por que não corrigi.** Há duas saídas legítimas e a escolha muda a postura de
segurança do projeto:

* **(a)** Corrigir o texto do critério de aceite para incluir
  `--env-file infra/.env.example`, mantendo o *fail-fast* dos segredos.
* **(b)** Dar valor padrão às variáveis de segredo no compose, tornando o
  comando cru válido — ao custo de permitir que a stack suba com senha padrão.

**Recomendação.** (a). O *fail-fast* é a decisão certa; o critério de aceite é
que está desatualizado. Alterar `FASES-E-AGENTES.md` é ownership do
orquestrador, por isso não toquei.

---

## D-04 · `apps/api/pyproject.toml` aponta para um arquivo gerado que não existe 🟡

**O que está errado.** Três blocos de configuração isentam `app/schemas/gerado.py`:

| Linha | Bloco | Efeito pretendido |
|---|---|---|
| `pyproject.toml:100` | `[tool.ruff] extend-exclude` | não formatar o arquivo gerado |
| `pyproject.toml:162` | `[[tool.mypy.overrides]] module = "app.schemas.gerado"` | afrouxar tipos no arquivo gerado |
| `pyproject.toml:187` | `[tool.coverage.run] omit` | não cobrar cobertura do arquivo gerado |

O gerador (`tools/gerar_do_contrato.py:228`) escreve em
**`app/schemas/contrato.py`**, não em `gerado.py`. O arquivo `gerado.py` não
existe. As três isenções, portanto, não têm efeito: o arquivo gerado de 14.700
linhas está hoje sob `ruff format`, `mypy --strict` e cobertura.

**Situação atual: passa.** `ruff check`, `ruff format --check` e `mypy` estão
verdes sobre `contrato.py`. Ou seja, isto **não quebra nada hoje**.

**Por que não corrigi.** As duas saídas têm consequências opostas:

* **(a)** Apagar as três referências mortas — o arquivo gerado continua sob
  verificação estrita, que é o comportamento atual e mais rigoroso.
* **(b)** Trocar `gerado.py` por `contrato.py` — cumpre a intenção original,
  mas **afrouxa** um gate que hoje está verde.

Trocar um gate que passa por um gate mais frouxo não é conserto de defeito, é
decisão de política de qualidade. Fica para o dono da `apps/api`.

**Recomendação.** (a).

---

## D-05 · `docs/rfc/README.md` é referenciado por três documentos e não existe 🟢

`packages/contracts/design-tokens.json` (`$description`),
`docs/adr/README.md:29` e
`docs/adr/ADR-005-versionamento-api-publica-depreciacao.md:95` apontam para
`docs/rfc/README.md` como o lugar onde vive o protocolo de RFC. O arquivo não
existe — o protocolo está em `FASES-E-AGENTES.md` §1.3 e, resumido, em
`packages/contracts/README.md`.

**Por que não corrigi.** Escrever o protocolo de RFC do projeto é definição de
processo, ownership do agente de contratos / do orquestrador — não é conserto.
Criei apenas o diretório `docs/rfc/` ao depositar esta RFC.

**Decisão pedida.** Escrever `docs/rfc/README.md`, ou corrigir os três ponteiros
para `FASES-E-AGENTES.md` §1.3.

---

## D-06 · Artefatos de processo previstos e ausentes 🟢

| Ausente | Quem referencia | Impacto |
|---|---|---|
| `docs/fases/F00-*.md` (o PCF da própria F0) | `FASES-E-AGENTES.md` §1.1 exige PCF por fase; existe só `docs/fases/_TEMPLATE.md` | a F0 foi executada sem o próprio pacote de contexto |
| `docs/backlog.md` | `FASES-E-AGENTES.md` §1.2 e `docs/fases/_TEMPLATE.md:87` mandam anotar escopo fora do PCF ali | agente que encontra escopo alheio não tem onde registrar |
| PCFs das fases da Onda 1 (F1, F2, F9a) | `FASES-E-AGENTES.md` §1 — "cada agente lê exatamente duas coisas" | **a Onda 1 não pode começar sem eles** |

**Decisão pedida.** Escrever os PCFs da Onda 1 antes de disparar a Onda 1. Isto
é pré-requisito duro, não recomendação: sem PCF o mecanismo anti-quebra-de-contexto
descrito em `FASES-E-AGENTES.md` §1 simplesmente não opera.

---

## D-07 · Divergência cosmética de nomenclatura entre API e banco 🟢

O contrato expõe `Comprovante.datahoraMarcacao`; a coluna correspondente em
`schema.sql` é `comprovantes.marcacao_datahora` (ordem das palavras invertida).
As duas pontas são internamente consistentes e nada quebra — mas o mapeamento
deixa de ser mecânico justamente numa entidade de valor legal.

Levantada aqui para registro. Corrigir exige mexer em `openapi.yaml` **ou** em
`schema.sql`, ambos congelados; por isso não toquei.

**Recomendação.** Deixar como está e documentar no glossário. O custo de mexer
em contrato congelado é maior que o benefício.

---

## O que **não** é divergência (verificado e conferido)

Registro explícito para que ninguém reabra o que já foi conferido:

* `schema.sql` × `models/`: **92 tabelas e 1.808 colunas, zero divergência** de
  nome; 1.798 colunas com tipo idêntico após compilação no dialeto PostgreSQL e
  10 diferenças que são apenas `TIME` × `TIME WITHOUT TIME ZONE` (sinônimos).
* `openapi.yaml` × routers: **215 operações, 140 caminhos, zero divergência** de
  método, caminho ou `operationId`.
* `openapi.yaml` × `errors.yaml`: **112 códigos**, todos citados no contrato e no
  código, nenhum órfão, nenhum pendurado.
* Migration inicial × `schema.sql`: paridade exata em 182 índices, 21 gatilhos,
  7 funções, 11 domínios, 96 *constraints* nomeadas.
* Vedação legal (T2): nenhum endpoint de UPDATE/DELETE de marcação; gatilhos de
  imutabilidade presentes nos dois artefatos; unicidade de NSR garantida.

---

## Decisão do orquestrador — 25/07/2026

| # | Decisão | Justificativa |
|---|---|---|
| **D-01** | **Opção 1 para as quatro.** Reabrir a F0 e entregar `apps/web`, `apps/device-gw` e `apps/facial-svc` como esqueletos executáveis. `apps/mobile` fica só com o `README.md` (Flutter não está instalado). | Divirjo em parte da recomendação. `apps/web` é consenso — bloqueia F9a e F8. Mas realocar `device-gw` e `facial-svc` para F6/F7 exigiria mexer no `docker-compose.yml` para adicionar `profiles:`, e aí o `docker compose build` só cobriria parte da stack pelas próximas 5 semanas. Um stub FastAPI de healthcheck custa pouco e mantém compose, CI e critério de aceite honestos desde já. |
| **D-02** | **Completar na F0**: `worker/main.py`, `worker/scheduler.py`, `apps/worker/Dockerfile`. | Sem eles dois serviços do compose não sobem e dois eventos do catálogo (`banco_horas.vencendo`, `terminal.offline`) ficam sem produtor possível. |
| **D-03** | **Opção (a)**, como recomendado. O critério de aceite em `FASES-E-AGENTES.md` já foi corrigido para incluir `--env-file infra/.env.example`, e ganhou `docker compose build` e o Alembic contra PostgreSQL real. | O *fail-fast* dos segredos é a postura certa. O texto do critério é que estava errado, não o compose. |
| **D-04** | **Opção (a)**, como recomendado: apagar as três referências mortas a `app/schemas/gerado.py`. | Não se troca um gate verde por um mais frouxo. O arquivo gerado continua sob `ruff`, `mypy --strict` e cobertura. |
| **D-05** | **Escrever `docs/rfc/README.md`** com o protocolo completo e um template de RFC. Os três ponteiros existentes ficam como estão. | Três documentos já apontam para lá; é mais barato criar o alvo que reescrever os ponteiros. |
| **D-06** | **Pré-requisito duro confirmado.** Escrever os PCFs de F1, F2 e F9a e o `docs/backlog.md` **antes** de disparar a Onda 1. PCF retroativo da própria F0 não será escrito. | Concordo integralmente: sem PCF o mecanismo anti-quebra-de-contexto não opera. O PCF da F0 seria arqueologia — o `F00-RELATORIO.md` já cumpre o papel de registro. |
| **D-07** | **Deixar como está**, documentando no glossário. | Concordo. Mexer em contrato congelado por questão cosmética custa mais que o benefício, e as duas pontas são internamente consistentes. |

**Nota sobre a verificação.** O relatório da F0 foi escrito com o repositório
ainda incompleto, porque dois agentes da Onda C caíram por erro de rede
(`ENOTFOUND`) — não por defeito do trabalho. O agente de verificação relatou a
incompletude corretamente, em vez de mascará-la, e essa é a razão de esta RFC
existir. Após a conclusão das entregas acima, a verificação será executada de
novo por inteiro.
