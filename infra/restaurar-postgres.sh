#!/bin/bash
# =============================================================================
# restaurar-postgres.sh — restaura um dump do SEEG Ponto sobre um banco
# =============================================================================
#
#   ############################################################
#   #  OPERACAO DESTRUTIVA. O BANCO ALVO E SOBRESCRITO.        #
#   #  Nao ha "desfazer". Nao ha confirmacao interativa.       #
#   ############################################################
#
# `pg_restore --clean` DERRUBA os objetos existentes antes de recriar: todo dado
# gravado no banco alvo DEPOIS do dump some, sem aviso e sem recuperacao. Em
# producao isso significa apagar marcacao de ponto de gente real — registro com
# consequencia trabalhista, e imutavel por premissa do produto (ADR-002).
#
# Por isso o mesmo portao do deploy-prod.sh: sem `--confirmar` (ou
# CONFIRMAR_RESTAURACAO_POSTGRES=sim), o script sai com codigo 2 sem tocar em
# nada. E producao exige um SEGUNDO portao, uma frase escrita por extenso.
#
# ANTES DE RODAR, confira em voz alta, olhando o comando:
#   - o AMBIENTE alvo e mesmo esse? (`prod` nao se digita por engano)
#   - o DUMP e do ambiente certo e da data certa?
#   - existe um backup FRESCO do estado atual do alvo? Se nao, faca primeiro:
#         /usr/local/sbin/backup-postgres.sh <ambiente>
#
# Uso:
#     restaurar-postgres.sh <caminho-do-dump> <hml|prod|teste> --confirmar
#
#     # restaurar para um banco NOVO em vez de sobrescrever o de producao —
#     # sempre prefira isto quando o objetivo e inspecionar/comparar:
#     restaurar-postgres.sh /var/backups/... teste --banco ponto_teste_restore --confirmar
#
# Variaveis de ambiente aceitas:
#   CONFIRMAR_RESTAURACAO_POSTGRES=sim   equivalente a --confirmar
#   CONFIRMAR_RESTAURACAO_PRODUCAO='restaurar banco de producao'
#                                        segundo portao, obrigatorio so em prod
#   PONTO_BACKUP_CONTAINER=<nome>        sobrescreve o container detectado
#   RESTORE_JOBS=<n>                     paralelismo do pg_restore (default 4)
# =============================================================================
set -euo pipefail

log() { printf '[restaurar-postgres %s] %s\n' "$(date -u +%FT%TZ)" "$*"; }
erro() { printf '[restaurar-postgres ERRO] %s\n' "$*" >&2; }

DUMP=""
AMBIENTE=""
BANCO_ALVO=""
confirmado="nao"
criar_banco="nao"

while [ $# -gt 0 ]; do
  case "$1" in
    --confirmar) confirmado="sim" ;;
    --banco) shift; BANCO_ALVO="${1:-}" ;;
    --criar-banco) criar_banco="sim" ;;
    -*) erro "argumento desconhecido: $1"; exit 2 ;;
    *)
      if [ -z "$DUMP" ]; then DUMP="$1"
      elif [ -z "$AMBIENTE" ]; then AMBIENTE="$1"
      else erro "argumento posicional extra: $1"; exit 2
      fi
      ;;
  esac
  shift
done

if [ -z "$DUMP" ] || [ -z "$AMBIENTE" ]; then
  erro "uso: $0 <caminho-do-dump> <hml|prod|teste> [--banco NOME] [--criar-banco] --confirmar"
  exit 2
fi

case "$AMBIENTE" in
  hml)   CONTAINER_PADRAO="ponto-hml-postgres-1" ;;
  prod)  CONTAINER_PADRAO="ponto-prd-postgres-1" ;;
  teste) CONTAINER_PADRAO="ponto-teste-postgres-1" ;;
  *) erro "ambiente invalido: '$AMBIENTE' (use hml, prod ou teste)"; exit 2 ;;
esac
CONTAINER="${PONTO_BACKUP_CONTAINER:-$CONTAINER_PADRAO}"

# -----------------------------------------------------------------------------
# 1. Portao 1 — confirmacao explicita, igual ao deploy-prod.sh.
# -----------------------------------------------------------------------------
if [ "${CONFIRMAR_RESTAURACAO_POSTGRES:-}" = "sim" ]; then
  confirmado="sim"
fi
if [ "$confirmado" != "sim" ]; then
  erro "restauracao NAO confirmada — nada foi alterado."
  erro "Isto SOBRESCREVE o banco alvo. Se tem certeza, rode com --confirmar."
  exit 2
fi

# -----------------------------------------------------------------------------
# 2. Portao 2 — producao pede a frase por extenso. Um `--confirmar` copiado de
#    um comando de homologacao nao pode virar restauracao em producao.
# -----------------------------------------------------------------------------
if [ "$AMBIENTE" = "prod" ]; then
  if [ "${CONFIRMAR_RESTAURACAO_PRODUCAO:-}" != "restaurar banco de producao" ]; then
    erro "ambiente prod exige o segundo portao. Nada foi alterado."
    erro "Rode com: CONFIRMAR_RESTAURACAO_PRODUCAO='restaurar banco de producao'"
    exit 2
  fi
fi

# -----------------------------------------------------------------------------
# 3. Guardas de sanidade.
# -----------------------------------------------------------------------------
[ -f "$DUMP" ] || { erro "dump nao encontrado: $DUMP"; exit 3; }

if [ -f "${DUMP}.sha256" ]; then
  esperado="$(cat "${DUMP}.sha256")"
  obtido="$(sha256sum "$DUMP" | awk '{print $1}')"
  if [ "$esperado" != "$obtido" ]; then
    erro "sha256 do dump NAO confere — arquivo corrompido. Abortado."
    exit 3
  fi
  log "sha256 confere"
else
  log "aviso: ${DUMP}.sha256 ausente, integridade nao verificada"
fi

estado="$(docker inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null || true)"
[ "$estado" = "running" ] || { erro "container '$CONTAINER' nao esta rodando (estado: '${estado:-inexistente}')"; exit 3; }

# O nome do arquivo carrega o ambiente de origem. Restaurar dump de hml sobre
# prod (ou vice-versa) e quase sempre engano; exige a variavel explicita.
origem="$(basename "$DUMP" | sed -n 's/^ponto-\([a-z]*\)-.*/\1/p')"
if [ -n "$origem" ] && [ "$origem" != "$AMBIENTE" ] && [ "${PERMITIR_CRUZAR_AMBIENTES:-nao}" != "sim" ]; then
  erro "dump e do ambiente '$origem' mas o alvo e '$AMBIENTE'."
  erro "Se e mesmo isso que voce quer, rode com PERMITIR_CRUZAR_AMBIENTES=sim."
  exit 3
fi

# -----------------------------------------------------------------------------
# 4. Banco alvo.
# -----------------------------------------------------------------------------
banco_padrao="$(docker exec "$CONTAINER" printenv POSTGRES_DB)"
BANCO_ALVO="${BANCO_ALVO:-$banco_padrao}"

log "container   : $CONTAINER"
log "ambiente    : $AMBIENTE"
log "dump        : $DUMP ($(stat -c '%s' "$DUMP") bytes)"
log "banco alvo  : $BANCO_ALVO"
if [ "$BANCO_ALVO" = "$banco_padrao" ]; then
  log "*** ESTE E O BANCO EM USO PELA APLICACAO. Todo dado atual sera perdido. ***"
fi

if [ "$criar_banco" = "sim" ]; then
  log "criando banco '$BANCO_ALVO' (se ja existir, e um erro — nao sobrescreve as cegas)"
  docker exec -e ALVO="$BANCO_ALVO" "$CONTAINER" sh -c '
      PGPASSWORD="$POSTGRES_PASSWORD" createdb \
        -h 127.0.0.1 -U "$POSTGRES_USER" -T template0 -E UTF8 "$ALVO"
    '
fi

# -----------------------------------------------------------------------------
# 5. Restore. `--clean --if-exists` derruba o que existe antes de recriar.
#    `--no-owner --no-privileges` porque o dump vem sem dono/ACL (o backup usa
#    as mesmas flags): quem restaura vira dono, e as roles de runtime
#    (`ponto_app_runtime`, `ponto_app_suporte`) sao criadas pelas migrations
#    0004/0005, nao pelo dump.
#    Exit code 1 do pg_restore = "concluiu com avisos ignorados" (tipico:
#    DROP de objeto que nao existia num banco vazio). So >1 e falha real.
#
#    O dump e COPIADO para dentro do container antes (docker cp) em vez de ir
#    por stdin: `pg_restore --jobs` recusa arquivo nao-buscavel ("parallel
#    restore from stdin is not supported"), e um restore serial de um banco com
#    milhoes de linhas custa caro justamente na hora em que o tempo importa.
#    O arquivo temporario e removido no fim, inclusive se der erro (trap).
# -----------------------------------------------------------------------------
TMP_CONTAINER="/tmp/ponto-restore-$$.dump"
limpar() { docker exec "$CONTAINER" rm -f "$TMP_CONTAINER" >/dev/null 2>&1 || true; }
trap limpar EXIT

log "copiando dump para dentro do container"
docker cp "$DUMP" "$CONTAINER:$TMP_CONTAINER"

log "restaurando (isto pode demorar)"
set +e
docker exec -e ALVO="$BANCO_ALVO" -e JOBS="${RESTORE_JOBS:-4}" -e ARQ="$TMP_CONTAINER" "$CONTAINER" sh -c '
      PGPASSWORD="$POSTGRES_PASSWORD" pg_restore \
        -h 127.0.0.1 -U "$POSTGRES_USER" -d "$ALVO" \
        --clean --if-exists --no-owner --no-privileges \
        --jobs="$JOBS" --exit-on-error "$ARQ"
    '
codigo=$?
set -e

if [ "$codigo" -gt 1 ]; then
  erro "pg_restore falhou (codigo $codigo). O banco '$BANCO_ALVO' pode estar INCONSISTENTE."
  erro "Nao suba a aplicacao contra ele antes de investigar."
  exit 5
fi
[ "$codigo" -eq 1 ] && log "aviso: pg_restore terminou com avisos (codigo 1), normal em banco vazio"

# -----------------------------------------------------------------------------
# 6. Prova de que restaurou algo — contagem de linhas por tabela. Compare com a
#    origem antes de considerar a restauracao boa. "Nao deu erro" nao e prova.
# -----------------------------------------------------------------------------
log "analisando e contando (prova de restauracao):"
docker exec -e ALVO="$BANCO_ALVO" "$CONTAINER" sh -c '
      PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$ALVO" \
        -c "ANALYZE;" \
        -c "SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 10;"
    '

log "concluido — banco '$BANCO_ALVO' restaurado de $(basename "$DUMP")"
log "confira as contagens acima contra a origem ANTES de apontar a aplicacao para ele."
