# ADR-009 — Worker instala apps/api como biblioteca

**Status:** Aceito · 26/07/2026
**Decisores:** Henrique Matias (dono do produto) — decisão de arquitetura de
deploy/empacotamento cross-cutting, escalada pelo orquestrador da F4 dado o
impacto nas duas imagens Docker do sistema
**Fases afetadas:** F4 (implementa e é a razão da decisão), F3 (motor de
jornada, também consumido pelo worker), F10 e F11 (fechamento e relatórios,
que também recalculam em lote via worker)

---

## Contexto

`apps/api` e `apps/worker` são empacotados como duas imagens Docker
independentes, cada uma com o próprio `pyproject.toml` e o próprio
`Dockerfile`. Essa separação existia sem atrito até a F4: `apps/worker`
instalava só `packages/contracts` (os models SQLAlchemy do contrato de dados)
além das próprias dependências, e `apps/api` instalava a mesma base de
contrato mais o `FastAPI`. Nenhum dos dois dependia do código de aplicação do
outro.

A F4 quebra essa independência. O PCF da fase manda o worker chamar
diretamente `app.apuracao.dominio.servico.apurar_dia` e
`app.apuracao.tratamento.recalculo.recalcular_periodo` a partir de
`apps/worker/worker/tarefas/apuracao.py` — são essas funções que carregam o
motor de cálculo determinístico da apuração (ADR-004) e o executam em lote
para milhares de vínculos. Esse motor mora em `apps/api/app/apuracao/**` e
depende transitivamente de `app.core.*` (segurança, sessão de banco, erros),
`app.jornada.*` (F3, resolução de jornada vigente) e
`app.identidade.auditoria.*` (cadeia de hash da trilha de auditoria) — nenhum
desses módulos está instalado na imagem de produção do worker
(`apps/worker/Dockerfile` histórico só instala `apps/worker` +
`packages/contracts`).

Rodar o motor de cálculo em dois lugares (API síncrona para consulta pontual,
worker assíncrono para recálculo em lote e para os jobs agendados do
scheduler) é a arquitetura já decidida em fases anteriores — não é isto que
está em discussão aqui. O que faltava era: **onde o código do motor deveria
morar fisicamente para que os dois processos consigam importá-lo sem duplicar
lógica de negócio.**

Por ser uma decisão que muda a superfície de build de duas imagens de
produção simultaneamente — não uma escolha de fronteira de módulo dentro de
uma única aplicação —, o orquestrador da F4 levou as alternativas ao dono do
produto em vez de decidir sozinho.

## Decisão

`apps/worker` instala `apps/api` como biblioteca Python no mesmo venv da
imagem, ao lado de `packages/contracts`.

1. **Instalação, não cópia de código.** O Dockerfile do worker copia
   `apps/api/pyproject.toml`, `apps/api/README.md` e o diretório `apps/api/app`
   para um diretório de build próprio (`/api-src`) e roda
   `pip install --no-cache-dir /api-src`, na mesma camada `dependencias` e
   pelo mesmo mecanismo já usado para `packages/contracts`. `apps/api/tests`,
   `apps/api/migrations` e `apps/api/tools` ficam de fora: não rodam em
   produção e só aumentam a superfície da imagem do worker.
2. **O worker nunca serve HTTP.** Ele importa `app.apuracao.*`,
   `app.jornada.*`, `app.core.*` e `app.identidade.auditoria.*` como
   biblioteca de lógica de negócio pura. Não sobe `uvicorn`, não expõe porta,
   não registra rota. O binário do processo continua sendo `arq
   worker.main.WorkerSettings` / `worker.scheduler.SchedulerSettings`, como
   antes.
3. **`pip install .` de `apps/api` já resolve as dependências transitivas**
   (FastAPI, SQLAlchemy, Pydantic etc.) porque estão declaradas no
   `pyproject.toml` de `apps/api` — nada é listado manualmente no
   `pyproject.toml` do worker.
4. **A imagem da API não muda.** `apps/api/Dockerfile` continua exatamente
   como está: só a imagem do worker ganha essa instalação adicional.

## Alternativas consideradas

**Instalar `apps/api` no worker (escolhida).** Custo imediato baixo — duas
linhas de `COPY` e um `pip install` a mais, seguindo um padrão que o
Dockerfile já usa para `packages/contracts` — e nenhuma mudança de import em
código já escrito e testado (A1 e A3 já chamam `app.apuracao.*` diretamente,
por ownership do PCF da F4). O custo aceito: a imagem do worker cresce (traz
FastAPI/Starlette mesmo nunca os usando) e as duas imagens passam a precisar
de rebuild coordenado quando `apps/api/app` muda, mesmo em mudanças que não
tocam o motor de cálculo.

**Extrair um pacote compartilhado novo** (ex.: `packages/apuracao` ou
`packages/dominio`, no mesmo padrão de `packages/contracts`), movendo
`app.apuracao.*`, `app.jornada.*`, `app.core.*` e `app.identidade.auditoria.*`
para lá e fazendo `apps/api` e `apps/worker` dependerem dele. Tecnicamente a
opção mais limpa a longo prazo — reduz a imagem do worker ao mínimo e explicita
a fronteira do domínio compartilhado — mas descartada **para esta fase**: exige
mover e testar novamente código de três agentes (A1, A2, A3) que acabou de ser
implementado e parcialmente validado, decidir uma nova estrutura de pacote sob
pressão de prazo, e revisar todo import relativo em `apps/api` e
`apps/worker`. Fica registrado como refatoração candidata para quando a F4
estiver estável e outra fase (F10/F11) também precisar do mesmo motor —
reavaliar então, não agora.

**Worker chamar a API por HTTP interno** (o worker faz uma requisição para um
endpoint interno da API em vez de importar o módulo Python). Descartada por
três motivos: (a) introduz rede como dependência de um caminho que hoje é
função pura e determinística (ADR-004) — timeout, retry e serialização viram
fonte de não-determinismo exatamente onde o produto promete que não há; (b) a
apuração em lote da F10/F11 processa 10.000 vínculos × 31 dias como critério
de aceite da F4 — isso via HTTP vira 310.000 requisições ou um endpoint em
lote novo, que ainda precisaria existir e ser mantido; (c) adiciona uma
dependência de disponibilidade (a API precisa estar de pé para o worker
processar o scheduler noturno) onde hoje não existe nenhuma.

## Consequências

**Positivas.** Nenhum código de A1/A2/A3 precisa mudar — as chamadas diretas a
`app.apuracao.dominio.servico.apurar_dia` e
`app.apuracao.tratamento.recalculo.recalcular_periodo` já escritas no PCF da
F4 funcionam sem alteração. O padrão de instalação (`COPY` para diretório
próprio + `pip install`) é idêntico ao já usado para `packages/contracts`,
então não introduz um mecanismo novo de build para revisar. O motor de
cálculo continua existindo em um único lugar físico (`apps/api/app/apuracao`)
— não há duplicação de lógica de negócio entre API e worker.

**Negativas e mitigações.** (a) A imagem do worker cresce (ganha FastAPI,
Starlette e as demais dependências de `apps/api` mesmo sem nunca usá-las via
HTTP); aceito porque o alvo `runtime` continua enxuto (sem compilador, sem
teste, sem ferramental de geração) e o custo de imagem é secundário ao custo
de manter dois motores de cálculo sincronizados. (b) As duas imagens deixam de
poder ser buildadas e implantadas de forma totalmente independente: uma
mudança em `apps/api/app/apuracao/**` ou em `app.core.*` invalida o cache de
build do worker e exige rebuild coordenado das duas imagens no mesmo deploy
— o pipeline de CI/CD precisa disso como regra explícita, não como
acidente descoberto em produção. (c) Se `apps/api` crescer em uma direção que
o worker não deveria carregar (ex.: uma dependência pesada só usada por uma
rota HTTP), essa dependência entra na imagem do worker sem que ninguém
decida isso explicitamente; mitigação: revisão de código deve tratar qualquer
adição ao `pyproject.toml` de `apps/api` como uma adição também à imagem do
worker. (d) Esta decisão é reavaliada quando uma fase futura (candidata:
F10/F11) tocar o mesmo motor de cálculo de novo — nesse ponto, a alternativa
de extrair um pacote compartilhado deve ser reconsiderada com o motor já
estável, não descartada de novo por padrão.
