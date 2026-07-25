# =============================================================================
# apps/api - API FastAPI do Ponto Eletronico (REP-P)
# =============================================================================
# O CONTEXTO DE BUILD E A RAIZ DO MONOREPO, nao esta pasta:
#
#     docker build -f apps/api/Dockerfile .
#
# E o que `infra/docker-compose.yml` faz (`context: ..`) e o que o job `docker`
# do CI faz (`context: .`). O motivo e `packages/contracts`: a API precisa dos
# models do contrato, e um build com contexto em `apps/api` nao os enxerga.
#
# Alvos:
#   dependencias  camada de dependencias de terceiro, cacheada por pyproject.toml
#   dev           + ferramental de teste, instalacao editavel, uvicorn --reload
#   runtime       (padrao) imagem enxuta, usuario sem privilegio, sem tooling
#
# Producao:   docker build -f apps/api/Dockerfile -t ponto-api .
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

# tzdata: a jornada de trabalho e calculada em America/Sao_Paulo, com horario
# de verao historico. Container sem tzdata calcula errado e nao avisa.
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

# Instala as dependencias de terceiro com um pacote `app` vazio: a lista de
# dependencias vive no pyproject.toml, e so ela invalida esta camada. Copiar o
# codigo aqui faria toda edicao de rota reinstalar o SQLAlchemy.
COPY apps/api/pyproject.toml apps/api/README.md ./
RUN mkdir -p app && : > app/__init__.py \
    && pip install --no-cache-dir .

# Contrato de dados (models SQLAlchemy que espelham schema.sql). Camada
# separada: muda mais que as dependencias e menos que o codigo da API.
COPY packages/contracts /contratos
RUN pip install --no-cache-dir /contratos

# -----------------------------------------------------------------------------
# dev - alvo usado por docker-compose.dev.yml (codigo vem por bind mount)
# -----------------------------------------------------------------------------
FROM dependencias AS dev

ENV AMBIENTE=dev \
    LOG_FORMATO=texto

COPY apps/api/ /app/
# Editavel: o bind mount do compose substitui /app pelo codigo do host, e a
# instalacao editavel continua apontando para o mesmo lugar.
RUN pip install --no-cache-dir -e ".[dev]"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# -----------------------------------------------------------------------------
# runtime - imagem final. Sem compilador, sem teste, sem ferramenta de geracao.
# -----------------------------------------------------------------------------
FROM dependencias AS runtime

ARG AMBIENTE=prd
ARG COMMIT=""
ENV AMBIENTE=${AMBIENTE} \
    COMMIT=${COMMIT} \
    LOG_FORMATO=json \
    UVICORN_WORKERS=4

# Codigo da aplicacao e o que o Alembic precisa. `tools/` e `tests/` ficam de
# fora de proposito: nao rodam em producao e so aumentam a superficie.
COPY apps/api/app /app/app
COPY apps/api/migrations /app/migrations
COPY apps/api/alembic.ini apps/api/pyproject.toml apps/api/README.md /app/

# O `pip install .` da camada "dependencias" rodou contra um pacote `app`
# VAZIO (so para cachear a resolucao de dependencias) e deixou para tras
# `*.egg-info` com o SOURCES.txt daquele momento. Sem remove-lo, este segundo
# install REUTILIZA aquela lista de arquivos em vez de reescanear o `app`
# real que acabou de ser copiado, e instala silenciosamente os modulos vazios
# no site-packages — sem erro, sem aviso. Some/facial-svc/api so nao travam
# por acidente (uvicorn roda com WorkingDir /app, e o cwd resolve antes do
# site-packages); o worker trava porque `arq` nao tem essa rede de seguranca.
# Sem `rm -rf *.egg-info`, o pacote instalado fica quebrado nos quatro.
RUN rm -rf *.egg-info build \
    && pip install --no-cache-dir --no-deps . \
    && groupadd --system --gid 1001 ponto \
    && useradd --system --uid 1001 --gid ponto --home /app --shell /usr/sbin/nologin ponto \
    && chown -R ponto:ponto /app

USER ponto

EXPOSE 8000

# Redundante com o healthcheck do compose, e proposital: `docker run` avulso e
# `docker ps` de emergencia continuam mostrando a saude do container.
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=5 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).status == 200 else 1)"

# Forma shell para expandir UVICORN_WORKERS. `--proxy-headers` porque quem
# termina TLS e ve o IP real do cliente e o Traefik da VPS; sem isso, toda
# marcacao por navegador chegaria com o IP do proxy e a allowlist CIDR da F8
# barraria todo mundo.
CMD uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers ${UVICORN_WORKERS} \
    --proxy-headers \
    --forwarded-allow-ips='*' \
    --no-access-log
