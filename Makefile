# =============================================================================
# Ponto Eletronico — atalhos de desenvolvimento (Linux/macOS/WSL)
# =============================================================================
# O equivalente para Windows PowerShell e ./tasks.ps1 — os dois arquivos
# expoem os MESMOS alvos e devem ser alterados juntos.
#
#   make            lista os alvos
#   make up         sobe a stack local
#   make test       roda a bateria de testes
# =============================================================================

SHELL := /bin/bash
.DEFAULT_GOAL := help
# Sem .ONESHELL de proposito: cada linha de receita e um shell independente,
# que e como as receitas abaixo estao escritas (continuacao explicita com \).

INFRA        := infra
ENV_FILE     := $(INFRA)/.env
ENV_EXEMPLO  := $(INFRA)/.env.example
COMPOSE_PRD  := docker compose --env-file $(ENV_FILE) -f $(INFRA)/docker-compose.yml
COMPOSE      := $(COMPOSE_PRD) -f $(INFRA)/docker-compose.dev.yml
API_DIR      := apps/api
WEB_DIR      := apps/web
KEYS_DIR     := $(INFRA)/keys

.PHONY: help up down restart logs ps migrate migration seed test test-web lint lint-web \
        fmt typecheck build bootstrap keys env validate shell psql redis clean nuke

# -----------------------------------------------------------------------------
help: ## Lista os alvos disponiveis
	@echo ""
	@echo "  Ponto Eletronico — alvos disponiveis"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
	@echo ""

# --- Ciclo de vida da stack ---------------------------------------------------
up: env ## Sobe a stack local (dev: portas publicadas, hot reload)
	$(COMPOSE) up -d --remove-orphans
	@echo ""
	@echo "  web        http://localhost:3000"
	@echo "  api        http://localhost:8000"
	@echo "  docs       http://localhost:8000/docs"
	@echo "  device-gw  http://localhost:8001"
	@echo "  minio      http://localhost:9001"
	@echo ""

down: ## Derruba a stack (preserva volumes)
	$(COMPOSE) down --remove-orphans

restart: ## Reinicia todos os servicos
	$(COMPOSE) restart

logs: ## Segue os logs (make logs s=api para um servico)
	$(COMPOSE) logs -f --tail=200 $(s)

ps: ## Estado e saude dos containers
	$(COMPOSE) ps

# --- Banco de dados -----------------------------------------------------------
migrate: ## Aplica as migrations Alembic ate head
	$(COMPOSE) exec api alembic upgrade head

migration: ## Cria migration autogerada (make migration m="descricao")
	@test -n "$(m)" || { echo "Uso: make migration m=\"descricao\""; exit 1; }
	$(COMPOSE) exec api alembic revision --autogenerate -m "$(m)"

seed: ## Carrega dados sinteticos de desenvolvimento
	$(COMPOSE) exec api python -m app.scripts.seed

psql: ## Abre psql no banco da stack
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-ponto} -d $${POSTGRES_DB:-ponto}

redis: ## Abre redis-cli na stack
	$(COMPOSE) exec redis redis-cli

shell: ## Shell no container da api (make shell s=worker para outro)
	$(COMPOSE) exec $(or $(s),api) /bin/sh

# --- Qualidade ----------------------------------------------------------------
test: ## Testes Python (pytest com cobertura)
	$(COMPOSE) exec -T api pytest -q --cov --cov-report=term-missing

test-web: ## Testes do web
	cd $(WEB_DIR) && pnpm test

lint: ## Lint Python (ruff)
	ruff check apps packages tests
	ruff format --check apps packages tests

lint-web: ## Lint do web (eslint)
	cd $(WEB_DIR) && pnpm lint

typecheck: ## Tipos: mypy (Python, por app -- ver RFC-009) e tsc (web)
	for dir in apps/api apps/worker apps/device-gw apps/facial-svc; do \
		if [ -f "$$dir/pyproject.toml" ]; then \
			echo "== mypy: $$dir =="; \
			(cd $$dir && mypy) || exit 1; \
		fi; \
	done
	cd $(WEB_DIR) && pnpm exec tsc --noEmit

fmt: ## Formata o codigo (ruff + prettier)
	ruff format apps packages tests
	ruff check --fix apps packages tests
	cd $(WEB_DIR) && pnpm exec prettier --write .

validate: ## Valida YAML da infra, compose e contrato OpenAPI
	python -c "import yaml,sys,pathlib; [yaml.safe_load(p.read_text(encoding='utf-8')) for p in pathlib.Path('infra').rglob('*.yml')]; print('infra: YAML ok')"
	$(COMPOSE_PRD) config --quiet && echo "compose prd: ok"
	$(COMPOSE) config --quiet && echo "compose dev: ok"
	@test -f packages/contracts/openapi.yaml \
		&& npx --yes @stoplight/spectral-cli lint packages/contracts/openapi.yaml --fail-severity=warn \
		|| echo "openapi.yaml ainda nao existe; validacao de contrato pulada."

build: ## Constroi as imagens Docker
	$(COMPOSE_PRD) build

# --- Preparacao do ambiente ---------------------------------------------------
env: ## Cria infra/.env a partir do exemplo, se ainda nao existir
	@if [ ! -f $(ENV_FILE) ]; then \
		cp $(ENV_EXEMPLO) $(ENV_FILE); \
		echo "Criado $(ENV_FILE) a partir do exemplo. Revise os valores."; \
	fi

keys: ## Gera o par de chaves JWT RS256 em infra/keys (nunca versionado)
	@mkdir -p $(KEYS_DIR)
	@if [ -f $(KEYS_DIR)/private.pem ]; then \
		echo "Chaves ja existem em $(KEYS_DIR). Apague antes de regerar."; \
	else \
		openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out $(KEYS_DIR)/private.pem; \
		openssl rsa -pubout -in $(KEYS_DIR)/private.pem -out $(KEYS_DIR)/public.pem; \
		chmod 600 $(KEYS_DIR)/private.pem; \
		echo "Chaves geradas em $(KEYS_DIR)."; \
	fi

bootstrap: env keys ## Prepara o ambiente do zero: .env, chaves, imagens, migrations
	$(COMPOSE) build
	$(COMPOSE) up -d postgres redis minio
	$(COMPOSE) up -d
	@echo "Aguardando a api ficar healthy..."
	@until [ "$$($(COMPOSE) ps -q api | xargs -r docker inspect -f '{{.State.Health.Status}}')" = "healthy" ]; do sleep 3; done
	$(MAKE) migrate
	@echo "Ambiente pronto. make logs para acompanhar."

# --- Limpeza ------------------------------------------------------------------
clean: ## Remove caches de build e de ferramentas
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf $(WEB_DIR)/.next $(WEB_DIR)/.turbo

nuke: ## Derruba a stack E APAGA OS VOLUMES (perde o banco local)
	@echo "Isso apaga o banco, o Redis e o MinIO locais."
	@read -p "Digite APAGAR para confirmar: " r; [ "$$r" = "APAGAR" ] || exit 1
	$(COMPOSE) down -v --remove-orphans
