# =============================================================================
# apps/facial-svc - motor facial self-hosted (wrapper HTTP)
# =============================================================================
# O CONTEXTO DE BUILD E A RAIZ DO MONOREPO, nao esta pasta:
#
#     docker build -f apps/facial-svc/Dockerfile .
#
# E o que `infra/docker-compose.yml` faz (`context: ..`) e o que o job `docker`
# do CI faz (`context: .`), por uniformidade com os demais servicos Python.
#
# ---------------------------------------------------------------------------
# ALIAS `app.main` — leia antes de mexer
# ---------------------------------------------------------------------------
# `infra/docker-compose.dev.yml` chama `uvicorn app.main:app` neste servico
# (o mesmo comando dos tres servicos Python). O pacote deste repositorio, no
# entanto, se chama `facial`: o CI roda `mypy apps packages` a partir da raiz do
# monorepo, e dois pacotes de mesmo nome em arvores diferentes fazem o mypy
# abortar a coleta inteira com "Duplicate module named 'app'" — e `apps/api` ja
# e dono do nome. Como `apps/facial-svc` tem hifen, nao existe `__init__.py`
# intermediario capaz de desempatar.
#
# A saida e um alias que vive SO NA IMAGEM: um pacote `app` minimo, num
# diretorio proprio adicionado ao PYTHONPATH, cujo modulo `main` reexporta
# `facial.main:app`. Com isso o compose continua valendo palavra por palavra, o
# repositorio nunca tem dois pacotes `app` e o hot reload continua funcionando.
#
# ---------------------------------------------------------------------------
# PESOS DO MODELO — build-time vs runtime, e por que a escolha e esta
# ---------------------------------------------------------------------------
# Os arquivos `.onnx` NAO entram na imagem e NAO entram no git: sao grandes
# (`buffalo_l` = ~326 MB descompactado) e tem ciclo de vida proprio. Eles chegam
# pelo volume `facial-models`, montado em `/models` (`FACIAL_MODEL_DIR`). Imagem
# sem pesos sobe, responde `/health` e reprova em `/ready` — que e exatamente o
# comportamento desejado.
#
# O InsightFace, por padrao, baixa `buffalo_l` do GitHub na PRIMEIRA execucao.
# Aqui isso e desligado (`FACIAL_BAIXAR_MODELO` e falso por padrao, e a propria
# `Configuracao` RECUSA liga-lo em hml/prd). As tres opcoes e o motivo da
# escolha:
#
#   (a) baixar em runtime .... rejeitado. Faz uma marcacao de ponto depender de
#       um repositorio de terceiro estar no ar, adiciona ~30 s ao primeiro
#       request depois de cada restart, e aceita como valido o peso que aquele
#       repositorio servir naquele dia — inclusive um substituido.
#   (b) baixar no build ...... rejeitado como padrao. Coloca 326 MB em CADA
#       camada/tag da imagem, faz o `docker build` do CI depender de rede
#       externa, e amarra o ciclo de vida dos pesos ao das releases de codigo,
#       que sao muito mais frequentes.
#   (c) volume, populado por passo explicito de deploy .... ESCOLHIDO. Os pesos
#       viram artefato versionado e verificavel por hash, a imagem continua
#       enxuta, e trocar o motor (que e uma decisao rastreada por
#       `FACIAL_MODEL_VERSAO`) deixa de exigir rebuild de imagem.
#
# Em `dev`/`ci` a conveniencia vale mais que a cerimonia: ligue
# `FACIAL_BAIXAR_MODELO=1` e o InsightFace popula `/models` sozinho na primeira
# captura. Ver o README do app para o passo de deploy.
#
# Alvos:
#   dependencias  camada de dependencias de terceiro, cacheada por pyproject.toml
#   dev           + ferramental de teste, instalacao editavel, uvicorn --reload
#   runtime       (padrao) imagem enxuta, usuario sem privilegio, sem tooling
#
# Producao:   docker build -f apps/facial-svc/Dockerfile -t ponto-facial-svc .
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
        'deste servico chama-se `facial` (ver apps/facial-svc/facial/__init__.py).' \
        '"""' \
        '' \
        'from facial.main import app' \
        '' \
        '__all__ = ["app"]' \
        > /opt/alias/app/main.py

WORKDIR /app

# -----------------------------------------------------------------------------
# dependencias - so o que muda pouco, para o cache de camada valer a pena.
# -----------------------------------------------------------------------------
FROM base AS dependencias

# `insightface` publica sdist com extensao Cython: sem compilador o `pip install`
# falha. O `build-essential` e removido no fim da MESMA camada — ele existe para
# compilar e nao pode sobrar numa imagem que recebe imagem de rosto pela rede.
# `libgomp1` fica: e o OpenMP que o ONNX Runtime usa para paralelizar em CPU.
# `libxcb1`/`libgl1`/`libglib2.0-0` ficam: mesmo `opencv-python-headless` (a
# variante sem GUI, ja usada aqui) e publicado com o wheel do manylinux
# linkando dinamicamente contra essas libs -- sem elas o processo nem sobe
# (`ImportError: libxcb.so.1`, depois `libGL.so.1`), achado real no primeiro
# deploy real deste servico com o motor de verdade (09/08/2026), corrigido
# iterativamente reproduzindo o erro num build isolado ate o import limpar.
# Nao e dependencia de GUI/X11 de fato -- nenhum servidor X roda em runtime,
# e so um residuo do build do wheel headless que a distro publica.
COPY apps/facial-svc/pyproject.toml apps/facial-svc/README.md ./
RUN mkdir -p facial/motor facial/rotas \
    && : > facial/__init__.py \
    && : > facial/motor/__init__.py \
    && : > facial/rotas/__init__.py \
    && apt-get update \
    && apt-get install -y --no-install-recommends build-essential libgomp1 libxcb1 libgl1 libglib2.0-0 \
    && pip install --no-cache-dir . \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

# -----------------------------------------------------------------------------
# dev - alvo usado por docker-compose.dev.yml (codigo vem por bind mount)
# -----------------------------------------------------------------------------
FROM dependencias AS dev

ENV AMBIENTE=dev \
    LOG_FORMATO=texto

COPY apps/facial-svc/ /app/
RUN pip install --no-cache-dir -e ".[dev]"

EXPOSE 8000
CMD ["uvicorn", "facial.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# -----------------------------------------------------------------------------
# runtime - imagem final. Sem compilador, sem teste, sem ferramenta de geracao.
# -----------------------------------------------------------------------------
FROM dependencias AS runtime

ARG AMBIENTE=prd
ARG COMMIT=""
ENV AMBIENTE=${AMBIENTE} \
    COMMIT=${COMMIT} \
    LOG_FORMATO=json \
    FACIAL_MODEL_DIR=/models \
    UVICORN_WORKERS=2

COPY apps/facial-svc/facial /app/facial
COPY apps/facial-svc/pyproject.toml apps/facial-svc/README.md /app/

# O `pip install .` da camada "dependencias" rodou contra um pacote `facial`
# VAZIO (so para cachear a resolucao de dependencias) e deixou para tras
# `*.egg-info` com o SOURCES.txt daquele momento. Sem remove-lo, este segundo
# install REUTILIZA aquela lista de arquivos em vez de reescanear o `facial`
# real que acabou de ser copiado, e instala silenciosamente os modulos vazios
# no site-packages, sem erro nenhum.
RUN rm -rf *.egg-info build \
    && pip install --no-cache-dir --no-deps . \
    && mkdir -p /models \
    && groupadd --system --gid 1001 ponto \
    && useradd --system --uid 1001 --gid ponto --home /app --shell /usr/sbin/nologin ponto \
    && chown -R ponto:ponto /app /models

USER ponto

EXPOSE 8000

# Redundante com o healthcheck do compose, e proposital. Note que bate em
# `/health`, e nao em `/ready`: um volume de modelos vazio nao pode derrubar o
# container em cascata — a `api` declara `depends_on: service_healthy` sobre
# este servico, e a stack inteira ficaria presa sem subir para dizer por que.
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=5 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).status == 200 else 1)"

# Sem `--proxy-headers`: este servico nao fica atras do Traefik e nao deve
# aceitar cabecalho de encaminhamento de ninguem. Ele so e alcancavel pela rede
# interna, e o IP de origem que interessa e o do container que chamou.
#
# `python -m facial.servidor` (F14/A2, hardening) em vez de `uvicorn` cru:
# liga TLS/mTLS de verdade quando FACIAL_TLS_CERT_PATH/FACIAL_TLS_KEY_PATH/
# FACIAL_MTLS_CA_PATH estao todos configurados (ver facial/servidor.py) --
# sem eles, sobe em HTTP puro, comportamento identico ao `uvicorn` cru de
# antes desta fase.
CMD ["python", "-m", "facial.servidor"]
