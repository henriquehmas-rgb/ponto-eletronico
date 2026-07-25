# =============================================================================
# apps/device-gw - gateway dos terminais Control iD (iDFace / iDBlock)
# =============================================================================
# O CONTEXTO DE BUILD E A RAIZ DO MONOREPO, nao esta pasta:
#
#     docker build -f apps/device-gw/Dockerfile .
#
# E o que `infra/docker-compose.yml` faz (`context: ..`) e o que o job `docker`
# do CI faz (`context: .`). O motivo e `packages/contracts`: a partir da F6 o
# gateway converte `access_log` em marcacao canonica usando os models do
# contrato, e um build com contexto em `apps/device-gw` nao os enxerga.
#
# ---------------------------------------------------------------------------
# ALIAS `app.main` — leia antes de mexer
# ---------------------------------------------------------------------------
# `infra/docker-compose.dev.yml` chama `uvicorn app.main:app` neste servico
# (o mesmo comando dos tres servicos Python). O pacote deste repositorio, no
# entanto, se chama `gateway`: o CI roda `mypy apps packages` a partir da raiz
# do monorepo, e dois pacotes de mesmo nome em arvores diferentes fazem o mypy
# abortar a coleta inteira com "Duplicate module named 'app'" — e `apps/api` ja
# e dono do nome. Como `apps/device-gw` tem hifen, nao existe `__init__.py`
# intermediario capaz de desempatar.
#
# A saida e um alias que vive SO NA IMAGEM: um pacote `app` minimo, num
# diretorio proprio adicionado ao PYTHONPATH, cujo modulo `main` reexporta
# `gateway.main:app`. Com isso o compose continua valendo palavra por palavra,
# o repositorio nunca tem dois pacotes `app` e o hot reload continua
# funcionando (o uvicorn observa /app, onde o bind mount coloca o codigo).
#
# Alvos:
#   dependencias  camada de dependencias de terceiro, cacheada por pyproject.toml
#   dev           + ferramental de teste, instalacao editavel, uvicorn --reload
#   runtime       (padrao) imagem enxuta, usuario sem privilegio, sem tooling
#
# Producao:   docker build -f apps/device-gw/Dockerfile -t ponto-device-gw .
# Dev local:  docker compose -f docker-compose.yml -f docker-compose.dev.yml up
# =============================================================================

ARG PYTHON_IMAGEM=python:3.12-slim-bookworm

# -----------------------------------------------------------------------------
# base - interpretador, venv, fuso e o alias de modulo. Comum a todos os alvos.
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
    PYTHONPATH=/opt/alias \
    TZ=America/Sao_Paulo

# tzdata: o `access_log` do terminal chega com epoch do relogio do equipamento e
# e comparado com o relogio do servidor. Container sem tzdata compara errado e
# nao avisa — e a comparacao dos dois relogios e o que detecta terminal com data
# adulterada.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python -m venv "$VIRTUAL_ENV" \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime

# Alias `app.main` exigido pelo override de desenvolvimento. Ver o cabecalho.
RUN mkdir -p /opt/alias/app \
    && : > /opt/alias/app/__init__.py \
    && printf '%s\n' \
        '"""Alias de compatibilidade: `uvicorn app.main:app`.' \
        '' \
        'Criado pelo Dockerfile, existe apenas dentro da imagem. O pacote real' \
        'deste servico chama-se `gateway` (ver apps/device-gw/gateway/__init__.py).' \
        '"""' \
        '' \
        'from gateway.main import app' \
        '' \
        '__all__ = ["app"]' \
        > /opt/alias/app/main.py

WORKDIR /app

# -----------------------------------------------------------------------------
# dependencias - so o que muda pouco, para o cache de camada valer a pena.
# -----------------------------------------------------------------------------
FROM base AS dependencias

# Instala as dependencias de terceiro com um pacote `gateway` vazio: a lista de
# dependencias vive no pyproject.toml, e so ela invalida esta camada. Copiar o
# codigo aqui faria toda edicao de rota reinstalar o SQLAlchemy.
COPY apps/device-gw/pyproject.toml apps/device-gw/README.md ./
RUN mkdir -p gateway/rotas \
    && : > gateway/__init__.py \
    && : > gateway/rotas/__init__.py \
    && pip install --no-cache-dir .

# Contrato de dados (models SQLAlchemy que espelham schema.sql). Camada
# separada: muda mais que as dependencias e menos que o codigo do gateway.
COPY packages/contracts /contratos
RUN pip install --no-cache-dir /contratos

# -----------------------------------------------------------------------------
# dev - alvo usado por docker-compose.dev.yml (codigo vem por bind mount)
# -----------------------------------------------------------------------------
FROM dependencias AS dev

ENV AMBIENTE=dev \
    LOG_FORMATO=texto \
    CONTROLID_SIMULADOR=true

COPY apps/device-gw/ /app/
# Editavel: o bind mount do compose substitui /app pelo codigo do host, e a
# instalacao editavel continua apontando para o mesmo lugar.
RUN pip install --no-cache-dir -e ".[dev]"

EXPOSE 8000
CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# -----------------------------------------------------------------------------
# runtime - imagem final. Sem compilador, sem teste, sem ferramenta de geracao.
# -----------------------------------------------------------------------------
FROM dependencias AS runtime

ARG AMBIENTE=prd
ARG COMMIT=""
ENV AMBIENTE=${AMBIENTE} \
    COMMIT=${COMMIT} \
    LOG_FORMATO=json \
    UVICORN_WORKERS=2

# Codigo da aplicacao. `tests/` fica de fora de proposito: nao roda em producao
# e so aumenta a superficie de um servico que vive exposto na borda.
COPY apps/device-gw/gateway /app/gateway
COPY apps/device-gw/pyproject.toml apps/device-gw/README.md /app/

# O `pip install .` da camada "dependencias" rodou contra um pacote `gateway`
# VAZIO (so para cachear a resolucao de dependencias) e deixou para tras
# `*.egg-info` com o SOURCES.txt daquele momento. Sem remove-lo, este segundo
# install REUTILIZA aquela lista de arquivos em vez de reescanear o `gateway`
# real que acabou de ser copiado, e instala silenciosamente os modulos vazios
# no site-packages, sem erro nenhum.
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
# termina TLS e ve o IP real e o Traefik da VPS; sem isso, todo terminal
# chegaria com o IP do proxy e a allowlist por origem que a F6 vai instalar
# barraria todos os equipamentos de uma vez.
CMD uvicorn gateway.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers ${UVICORN_WORKERS} \
    --proxy-headers \
    --forwarded-allow-ips='*' \
    --no-access-log
