# =============================================================================
# apps/worker - workers ARQ do Ponto Eletronico (worker e scheduler)
# =============================================================================
# O CONTEXTO DE BUILD E A RAIZ DO MONOREPO, nao esta pasta:
#
#     docker build -f apps/worker/Dockerfile .
#
# E o que `infra/docker-compose.yml` faz (`context: ..`) e o que o job `docker`
# do CI faz (`context: .`). O motivo e `packages/contracts`: a partir da F4 o
# worker le e escreve pelos models do contrato, e um build com contexto em
# `apps/worker` nao os enxerga.
#
# APPS/API COMO BIBLIOTECA (ADR-009). A partir da F4 o motor de calculo mora em
# `apps/api/app/apuracao/**` (e depende transitivamente de `app.core.*` e
# `app.jornada.*`), mas quem executa recalculo em lote e o worker, nao a API.
# Este Dockerfile instala o pacote `apps/api` (so `app/`, sem `tests/`,
# `migrations/` nem `tools/`) na mesma imagem, exatamente como ja faz para
# `packages/contracts` logo abaixo. O worker NUNCA sobe `uvicorn` nem serve
# HTTP: ele so importa modulos de `app.apuracao.*`, `app.jornada.*`,
# `app.core.*` e `app.identidade.auditoria.*` como biblioteca de logica de
# negocio. Decisao de Henrique (dono do produto) — ver
# `docs/adr/ADR-009-worker-instala-apps-api-como-biblioteca.md` para o
# contexto completo e as alternativas descartadas (pacote compartilhado novo,
# chamada HTTP interna).
#
# UMA IMAGEM, DOIS PROCESSOS. Os servicos `worker` e `scheduler` do compose
# apontam para este mesmo Dockerfile e para a mesma imagem; o que muda e o
# `command`:
#
#     worker     arq worker.main.WorkerSettings
#     scheduler  arq worker.scheduler.SchedulerSettings
#
# Os dois caminhos de importacao vem de `infra/.env.example`
# (`ARQ_WORKER_SETTINGS` e `ARQ_SCHEDULER_SETTINGS`) e sao usados tambem pelo
# healthcheck (`arq --check`).
#
# Alvos:
#   dependencias  camada de dependencias de terceiro, cacheada por pyproject.toml
#   dev           + ferramental de teste e `watchfiles` (exigido por `arq --watch`)
#   runtime       (padrao) imagem enxuta, usuario sem privilegio, sem tooling
#
# Producao:   docker build -f apps/worker/Dockerfile -t ponto-worker .
# Dev local:  docker compose -f docker-compose.yml -f docker-compose.dev.yml up
# =============================================================================

ARG PYTHON_IMAGEM=python:3.12-slim-bookworm

# -----------------------------------------------------------------------------
# base - interpretador, venv e fuso. Comum a todos os alvos.
# -----------------------------------------------------------------------------
FROM ${PYTHON_IMAGEM} AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    TZ=America/Sao_Paulo

# tzdata nao e opcional aqui: o cron do scheduler roda no relogio LOCAL do
# processo (ver `worker/scheduler.py`, funcao `montar_cron`). Container sem
# tzdata dispara a rotina das 04:10 no horario errado e nao avisa.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python -m venv "$VIRTUAL_ENV" \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime

WORKDIR /app

# -----------------------------------------------------------------------------
# dependencias - so o que muda pouco, para o cache de camada valer a pena.
# -----------------------------------------------------------------------------
FROM base AS dependencias

# Instala as dependencias de terceiro com um pacote `worker` vazio: a lista de
# dependencias vive no pyproject.toml, e so ela invalida esta camada. Copiar o
# codigo aqui faria toda edicao de tarefa reinstalar o SQLAlchemy.
COPY apps/worker/pyproject.toml apps/worker/README.md ./
RUN mkdir -p worker/tarefas \
    && : > worker/__init__.py \
    && : > worker/tarefas/__init__.py \
    && pip install --no-cache-dir .

# Contrato de dados (models SQLAlchemy que espelham schema.sql). Camada
# separada: muda mais que as dependencias e menos que o codigo do worker.
COPY packages/contracts /contratos
RUN pip install --no-cache-dir /contratos

# apps/api como biblioteca (ADR-009): o motor de calculo da F4 vive em
# `app.apuracao.*` e depende transitivamente de `app.core.*`/`app.jornada.*`,
# entao o worker precisa do pacote `ponto-api` instalado no mesmo venv para
# poder importar esses modulos em `worker/tarefas/apuracao.py`. So `app/` +
# metadados de empacotamento — `tests/`, `migrations/` e `tools/` ficam de
# fora de proposito, pelo mesmo motivo que ficam de fora da imagem da propria
# API: nao rodam em producao e so aumentam a superficie. O `pip install .` de
# apps/api ja traz fastapi/sqlalchemy/etc. como dependencia transitiva
# (declaradas no pyproject.toml dele); nada e listado manualmente aqui.
COPY apps/api/pyproject.toml apps/api/README.md /api-src/
COPY apps/api/app /api-src/app
RUN pip install --no-cache-dir /api-src

# -----------------------------------------------------------------------------
# dev - alvo usado por docker-compose.dev.yml (codigo vem por bind mount)
# -----------------------------------------------------------------------------
FROM dependencias AS dev

ENV AMBIENTE=dev \
    LOG_FORMATO=texto

COPY apps/worker/ /app/
# Editavel: o bind mount do compose substitui /app pelo codigo do host, e a
# instalacao editavel continua apontando para o mesmo lugar. `watchfiles` vem
# junto porque `arq --watch /app` (o command do override de dev) importa a
# biblioteca em tempo de execucao e falha com ImportError sem ela.
RUN pip install --no-cache-dir -e ".[dev]"

CMD ["arq", "worker.main.WorkerSettings", "--watch", "/app"]

# -----------------------------------------------------------------------------
# runtime - imagem final. Sem compilador, sem teste, sem ferramenta de geracao.
# -----------------------------------------------------------------------------
FROM dependencias AS runtime

ARG AMBIENTE=prd
ARG COMMIT=""
ENV AMBIENTE=${AMBIENTE} \
    COMMIT=${COMMIT} \
    LOG_FORMATO=json \
    ARQ_WORKER_SETTINGS=worker.main.WorkerSettings

# Codigo da aplicacao. `tests/` fica de fora de proposito: nao roda em producao
# e so aumenta a superficie.
COPY apps/worker/worker /app/worker
COPY apps/worker/pyproject.toml apps/worker/README.md /app/

# O `pip install .` da camada "dependencias" rodou contra um pacote `worker`
# VAZIO (so para cachear a resolucao de dependencias) e deixou para tras
# `*.egg-info` com o SOURCES.txt daquele momento. Sem remove-lo, este segundo
# install REUTILIZA aquela lista de arquivos em vez de reescanear o `worker`
# real que acabou de ser copiado, e instala silenciosamente os modulos vazios
# no site-packages — foi assim que `NOMES_DAS_TAREFAS` sumiu e o worker
# entrou em crash loop (ImportError na subida).
RUN rm -rf *.egg-info build \
    && pip install --no-cache-dir --no-deps . \
    && groupadd --system --gid 1001 ponto \
    && useradd --system --uid 1001 --gid ponto --home /app --shell /usr/sbin/nologin ponto \
    && chown -R ponto:ponto /app

USER ponto

# Redundante com o healthcheck do compose, e proposital: `docker run` avulso e
# `docker ps` de emergencia continuam mostrando a saude do container. O ARQ
# grava um batimento no Redis a cada 20 s (`health_check_interval`) e
# `arq --check` devolve 0 enquanto a chave estiver fresca. O servico
# `scheduler` sobrescreve ARQ_WORKER_SETTINGS com o caminho do SchedulerSettings,
# e o mesmo comando passa a checar o processo certo.
HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=5 \
    CMD arq --check "$ARQ_WORKER_SETTINGS"

# Padrao da imagem. Os dois servicos do compose sobrescrevem o `command`:
# `worker` repete este, `scheduler` troca por worker.scheduler.SchedulerSettings.
CMD ["arq", "worker.main.WorkerSettings"]
