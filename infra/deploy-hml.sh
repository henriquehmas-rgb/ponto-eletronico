#!/bin/bash
# Deploy restrito do stack ponto-hml (gerado pela sessao de fechamento da F14).
# So pode ser disparado pela chave SSH dedicada com forced-command em
# /root/.ssh/authorized_keys -- nunca chamado manualmente fora de teste.
set -euo pipefail

cd /docker/ponto-eletronico
git fetch origin main
git reset --hard origin/main

cd infra
docker compose -p ponto-hml pull
docker compose -p ponto-hml up -d --remove-orphans

set -a
source .env
set +a
docker compose -p ponto-hml run --rm   -e DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}"   -e POSTGRES_APP_PASSWORD="${POSTGRES_APP_PASSWORD}"   api alembic upgrade head

echo "deploy-hml.sh concluido em $(date -u +%FT%TZ)"
