#!/bin/bash
# =============================================================================
# deploy-prod.sh — deploy do stack de PRODUCAO (ponto-prd)
# =============================================================================
# Espelha a estrutura de infra/deploy-hml.sh (fetch/reset, pull, up -d, alembic
# upgrade head), com quatro diferencas deliberadas, porque producao e operacao
# de risco maior:
#
#   1. CONFIRMACAO EXPLICITA obrigatoria. Sem `--confirmar` na linha de comando
#      ou `CONFIRMAR_DEPLOY_PRODUCAO=sim` no ambiente, o script sai com codigo 2
#      sem tocar em nada. hml roda automatico a cada push em main; producao NAO.
#   2. Aponta para docker-compose.prod.yml, projeto `ponto-prd`, .env.prod —
#      nunca para os arquivos de homologacao.
#   3. Guarda de sanidade antes de agir: confere que o diretorio, o compose e o
#      .env.prod existem, que o .env.prod nao esta legivel por outros, e que a
#      TAG pedida nao e `latest` (producao roda tag imutavel).
#   4. Registra a TAG anterior em .tag-anterior ANTES de trocar, para o rollback
#      do runbook ser um comando so.
#
# Uso na VPS (como root, ou via sudoers scoped):
#     /docker/ponto-prd/infra/deploy-prod.sh --confirmar
#     TAG=a1b2c3d /docker/ponto-prd/infra/deploy-prod.sh --confirmar
#
# Uso pelo CI (workflow .github/workflows/deploy-prod.yml, so workflow_dispatch):
#     CONFIRMAR_DEPLOY_PRODUCAO=sim sudo -n /docker/ponto-prd/infra/deploy-prod.sh
#
# Variaveis de ambiente aceitas:
#   CONFIRMAR_DEPLOY_PRODUCAO=sim   equivalente a --confirmar
#   TAG=<sha-curto>                 sobrescreve a TAG do .env.prod neste deploy
#                                   (persistida no .env.prod para o proximo up)
#   PONTO_PRD_DIR=<caminho>         raiz do checkout de producao na VPS
#                                   (default /docker/ponto-prd)
#   PULAR_MIGRATION=sim             sobe os servicos sem rodar alembic
#                                   (use so quando a migration ja foi aplicada
#                                   manualmente em janela separada)
#
# NAO USE ESTE SCRIPT PARA HOMOLOGACAO. hml tem o seu proprio (deploy-hml.sh).
# =============================================================================
set -euo pipefail

PROJETO="ponto-prd"
COMPOSE_ARQ="docker-compose.prod.yml"
ENV_ARQ=".env.prod"
DIR_RAIZ="${PONTO_PRD_DIR:-/docker/ponto-prd}"
BRANCH="${PONTO_PRD_BRANCH:-main}"

log() { printf '[deploy-prod %s] %s\n' "$(date -u +%FT%TZ)" "$*"; }
erro() { printf '[deploy-prod ERRO] %s\n' "$*" >&2; }

# -----------------------------------------------------------------------------
# 0. Confirmacao explicita — o unico portao que separa "rodei sem querer" de
#    "decidi fazer deploy em producao".
# -----------------------------------------------------------------------------
confirmado="nao"
for arg in "$@"; do
  case "$arg" in
    --confirmar) confirmado="sim" ;;
    *) erro "argumento desconhecido: $arg"; exit 2 ;;
  esac
done
if [ "${CONFIRMAR_DEPLOY_PRODUCAO:-}" = "sim" ]; then
  confirmado="sim"
fi

if [ "$confirmado" != "sim" ]; then
  erro "deploy de PRODUCAO nao confirmado — nada foi alterado."
  erro "Para prosseguir, rode com --confirmar ou CONFIRMAR_DEPLOY_PRODUCAO=sim."
  exit 2
fi

# -----------------------------------------------------------------------------
# 1. Guardas de sanidade — falhar aqui e barato; falhar depois do `up` nao e.
# -----------------------------------------------------------------------------
[ -d "$DIR_RAIZ" ] || { erro "diretorio de producao nao existe: $DIR_RAIZ"; exit 3; }
cd "$DIR_RAIZ"

[ -f "infra/$COMPOSE_ARQ" ] || { erro "faltando infra/$COMPOSE_ARQ em $DIR_RAIZ"; exit 3; }
[ -f "infra/$ENV_ARQ" ] || {
  erro "faltando infra/$ENV_ARQ — copie de infra/.env.prod.example e preencha."
  exit 3
}

# .env.prod tem segredo real: nunca legivel por grupo/outros.
perm="$(stat -c '%a' "infra/$ENV_ARQ")"
case "$perm" in
  600|400) : ;;
  *) erro "infra/$ENV_ARQ com permissao $perm — rode: chmod 600 infra/$ENV_ARQ"; exit 3 ;;
esac

# Nao deixar o compose de homologacao ser usado por engano.
if [ "$(basename "$DIR_RAIZ")" = "ponto-eletronico" ]; then
  erro "$DIR_RAIZ e o checkout de HOMOLOGACAO. Producao vive em outro diretorio."
  exit 3
fi

# -----------------------------------------------------------------------------
# 2. Codigo — mesma mecanica do deploy-hml.sh
# -----------------------------------------------------------------------------
log "atualizando arvore para origin/$BRANCH"
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"
sha_curto="$(git rev-parse --short HEAD)"
log "HEAD agora em $sha_curto"

cd infra

# -----------------------------------------------------------------------------
# 3. TAG — producao roda tag imutavel. Guarda a anterior para o rollback.
# -----------------------------------------------------------------------------
tag_atual="$(grep -E '^TAG=' "$ENV_ARQ" | head -1 | cut -d= -f2- || true)"
tag_nova="${TAG:-$tag_atual}"

if [ -z "$tag_nova" ]; then
  erro "TAG vazia. Defina TAG no $ENV_ARQ ou passe TAG=<sha-curto> no ambiente."
  exit 4
fi
if [ "$tag_nova" = "latest" ]; then
  erro "TAG=latest e proibida em producao: o rollback deixa de ser reproduzivel."
  erro "Use o SHA curto do commit publicado pelo CI (ex.: $sha_curto)."
  exit 4
fi

if [ "$tag_nova" != "$tag_atual" ]; then
  log "TAG: $tag_atual -> $tag_nova (anterior salva em .tag-anterior)"
  printf '%s\n' "$tag_atual" > .tag-anterior
  chmod 600 .tag-anterior
  # Reescreve a linha TAG= preservando o resto do arquivo e a permissao.
  tmp="$(mktemp)"
  chmod 600 "$tmp"
  sed "s#^TAG=.*#TAG=${tag_nova}#" "$ENV_ARQ" > "$tmp"
  cat "$tmp" > "$ENV_ARQ"
  rm -f "$tmp"
else
  log "TAG inalterada: $tag_nova"
fi

compose() {
  docker compose -p "$PROJETO" --env-file "$ENV_ARQ" -f "$COMPOSE_ARQ" "$@"
}

# -----------------------------------------------------------------------------
# 4. Validacao da config antes de qualquer mudanca de estado.
#    Toda variavel obrigatoria ausente (`:?` no compose) estoura AQUI.
# -----------------------------------------------------------------------------
log "validando composicao"
compose config --quiet

# -----------------------------------------------------------------------------
# 5. Deploy
# -----------------------------------------------------------------------------
log "baixando imagens $tag_nova"
compose pull

log "subindo servicos"
compose up -d --remove-orphans

# -----------------------------------------------------------------------------
# 6. Migration — credencial ADMINISTRATIVA, so aqui. Os servicos rodam com a
#    role de privilegio minimo `ponto_app_runtime` (ADR-001).
# -----------------------------------------------------------------------------
if [ "${PULAR_MIGRATION:-nao}" = "sim" ]; then
  log "PULAR_MIGRATION=sim — alembic nao foi executado"
else
  log "aplicando migrations (alembic upgrade head)"
  set -a
  # shellcheck disable=SC1090
  source "$ENV_ARQ"
  set +a
  compose run --rm \
    -e DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}" \
    -e POSTGRES_APP_PASSWORD="${POSTGRES_APP_PASSWORD}" \
    api alembic upgrade head
fi

# -----------------------------------------------------------------------------
# 7. Verificacao pos-deploy — informativa. Nao reverte sozinho: rollback em
#    producao e decisao humana (ver docs/runbook-deploy-producao.md).
# -----------------------------------------------------------------------------
log "estado dos servicos:"
compose ps

log "deploy-prod.sh concluido — commit $sha_curto, TAG $tag_nova"
log "valide agora: GET https://api.ponto.\${DOMINIO}/v1/admin/saude"
