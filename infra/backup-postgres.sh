#!/bin/bash
# =============================================================================
# backup-postgres.sh — dump periodico do Postgres de um stack do SEEG Ponto
# =============================================================================
# Fecha o achado bloqueante registrado em docs/backlog.md (2026-08-08, scaffold
# de producao): o cenario de rollback "Caso C — restaurar backup do banco" do
# runbook era inexecutavel porque nao existia backup nenhum.
#
# Decisoes deliberadas:
#
#   1. FORMATO CUSTOM (`pg_dump -Fc`). Ja sai comprimido (zlib) e permite
#      restore SELETIVO (`pg_restore -t tabela`, `-n schema`, `--list`) — coisa
#      que um `.sql.gz` nao permite. O comando do runbook antigo (`pg_dump |
#      gzip`) so servia para restaurar tudo ou nada.
#   2. RODA DENTRO DO CONTAINER, via `docker exec`. A imagem `postgres:16-alpine`
#      ja traz `pg_dump`/`pg_restore` da MESMA versao do servidor; instalar um
#      cliente no host so criaria um segundo lugar para desatualizar.
#   3. SEGREDO NUNCA NA LINHA DE COMANDO. A senha e lida de dentro do container
#      (`$POSTGRES_PASSWORD`, que o proprio compose ja injeta), expandida pelo
#      shell de la — nunca aparece no `ps` do host nem no log.
#   4. TODO DUMP E VERIFICADO. Depois de gravar, `pg_restore --list` le o
#      arquivo inteiro; um dump truncado (disco cheio, container morto no meio)
#      falha AQUI e nao seis meses depois, na hora do desastre.
#
# Uso:
#     /usr/local/sbin/backup-postgres.sh hml
#     /usr/local/sbin/backup-postgres.sh prod
#     /usr/local/sbin/backup-postgres.sh teste
#
# Variaveis de ambiente aceitas:
#   PONTO_BACKUP_DIR=<caminho>     raiz dos backups (default /var/backups/ponto)
#   RETENCAO_DIARIOS=<n>           quantos diarios manter (default 14)
#   RETENCAO_SEMANAIS=<n>          quantos semanais manter (default 4)
#   PONTO_BACKUP_CONTAINER=<nome>  sobrescreve o container detectado (raro)
#   PONTO_BACKUP_UPLOAD_CMD=<cmd>  passo OPCIONAL de copia externa, DESLIGADO
#                                  por padrao — ver secao 6.
#
# ATENCAO — LIMITACAO CONHECIDA: sem PONTO_BACKUP_UPLOAD_CMD, o backup fica
# APENAS no disco da propria VPS. Isso protege contra `DROP TABLE`, migration
# ruim e corrupcao logica, mas NAO protege contra perda da VPS inteira (disco,
# datacenter, conta suspensa). Copia externa continua sendo uma pendencia.
# =============================================================================
set -euo pipefail

log() { printf '[backup-postgres %s] %s\n' "$(date -u +%FT%TZ)" "$*"; }
erro() { printf '[backup-postgres ERRO] %s\n' "$*" >&2; }

# -----------------------------------------------------------------------------
# 1. Ambiente alvo -> container. Um mapa explicito, nao string montada: errar o
#    container aqui significa fazer backup do banco errado (ou de outro projeto
#    qualquer que compartilha a VPS).
# -----------------------------------------------------------------------------
AMBIENTE="${1:-}"
case "$AMBIENTE" in
  hml)   CONTAINER_PADRAO="ponto-hml-postgres-1" ;;
  prod)  CONTAINER_PADRAO="ponto-prd-postgres-1" ;;
  teste) CONTAINER_PADRAO="ponto-teste-postgres-1" ;;
  *)
    erro "uso: $0 {hml|prod|teste}"
    erro "ambiente recebido: '${AMBIENTE}'"
    exit 2
    ;;
esac
CONTAINER="${PONTO_BACKUP_CONTAINER:-$CONTAINER_PADRAO}"

BASE="${PONTO_BACKUP_DIR:-/var/backups/ponto}/$AMBIENTE"
DIR_DIARIO="$BASE/diario"
DIR_SEMANAL="$BASE/semanal"
RETENCAO_DIARIOS="${RETENCAO_DIARIOS:-14}"
RETENCAO_SEMANAIS="${RETENCAO_SEMANAIS:-4}"

# -----------------------------------------------------------------------------
# 2. Guardas — falhar antes de escrever qualquer byte.
# -----------------------------------------------------------------------------
command -v docker >/dev/null 2>&1 || { erro "docker nao encontrado no PATH"; exit 3; }

estado="$(docker inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null || true)"
if [ -z "$estado" ]; then
  erro "container '$CONTAINER' nao existe nesta VPS (ambiente $AMBIENTE)."
  erro "confira com: docker ps --format '{{.Names}}' | grep postgres"
  exit 3
fi
if [ "$estado" != "running" ]; then
  erro "container '$CONTAINER' esta '$estado', nao 'running'. Nada foi feito."
  exit 3
fi

mkdir -p "$DIR_DIARIO" "$DIR_SEMANAL"
chmod 700 "${PONTO_BACKUP_DIR:-/var/backups/ponto}" "$BASE" "$DIR_DIARIO" "$DIR_SEMANAL"

# Dump de banco = copia integral de dado pessoal (LGPD). 700/600, sempre.
umask 077

# Espaco livre: um dump pela metade e pior que dump nenhum, porque parece que
# existe backup. 2 GiB e piso arbitrario, mas suficiente para o volume atual.
livre_kb="$(df -Pk "$BASE" | awk 'NR==2 {print $4}')"
if [ "${livre_kb:-0}" -lt 2097152 ]; then
  erro "menos de 2 GiB livres em $BASE (${livre_kb} KiB). Abortado."
  exit 4
fi

# -----------------------------------------------------------------------------
# 3. Dump
# -----------------------------------------------------------------------------
CARIMBO="$(date -u +%Y%m%d-%H%M%S)"
ARQ="$DIR_DIARIO/ponto-${AMBIENTE}-${CARIMBO}.dump"
PARCIAL="${ARQ}.parcial"

log "ambiente=$AMBIENTE container=$CONTAINER destino=$ARQ"

# `sh -c` roda DENTRO do container: POSTGRES_USER/DB/PASSWORD sao as variaveis
# que o compose ja injetou la. Nada disso transita pelo host.
# -h 127.0.0.1 forca a conexao TCP autenticada, em vez do socket local (que a
# imagem oficial deixa em `trust`) — o dump falha alto se a credencial estiver
# errada, em vez de silenciosamente funcionar so por ser local.
if ! docker exec "$CONTAINER" sh -c '
      set -e
      PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
        -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        --format=custom --compress=6 --no-owner --no-privileges
    ' > "$PARCIAL"; then
  erro "pg_dump falhou. Removendo dump parcial."
  rm -f "$PARCIAL"
  exit 5
fi

tamanho="$(stat -c '%s' "$PARCIAL")"
if [ "$tamanho" -lt 10240 ]; then
  erro "dump com $tamanho bytes — pequeno demais para ser valido. Removido."
  rm -f "$PARCIAL"
  exit 5
fi

# -----------------------------------------------------------------------------
# 4. Verificacao — le o arquivo inteiro de volta. Barato e nao-negociavel.
#
#    Feita num container DESCARTAVEL da mesma imagem, com o diretorio de backup
#    montado somente-leitura, e nao por stdin do container do banco: `pg_restore
#    --list` lendo de `/dev/stdin` num pipe falha com "did not find magic string
#    in file header" (confirmado empiricamente na VPS, 2026-08-09) — ele precisa
#    de arquivo buscavel. Vantagem extra: `--list` nao conecta em banco nenhum,
#    entao esta verificacao nao toca no Postgres em producao nem precisa de
#    credencial.
# -----------------------------------------------------------------------------
log "verificando integridade do arquivo ($tamanho bytes)"
IMAGEM="$(docker inspect -f '{{.Config.Image}}' "$CONTAINER")"
if ! docker run --rm --network none \
      -v "$DIR_DIARIO:/verificar:ro" "$IMAGEM" \
      pg_restore --list "/verificar/$(basename "$PARCIAL")" > /dev/null; then
  erro "pg_restore --list recusou o arquivo: dump corrompido ou truncado. Removido."
  rm -f "$PARCIAL"
  exit 5
fi

mv "$PARCIAL" "$ARQ"
chmod 600 "$ARQ"
sha256sum "$ARQ" | awk '{print $1}' > "${ARQ}.sha256"
chmod 600 "${ARQ}.sha256"
log "dump OK: $ARQ ($(numfmt --to=iec --suffix=B "$tamanho" 2>/dev/null || echo "$tamanho bytes"))"

# -----------------------------------------------------------------------------
# 5. Retencao — esquema GFS reduzido: 14 diarios + 4 semanais.
#
#    Por que esses numeros: 14 dias cobre o cenario realista de "alguem so
#    percebeu o estrago duas semanas depois" (erro de apuracao so aparece no
#    fechamento do mes seguinte) sem virar arquivo morto; 4 semanais estendem o
#    alcance para ~1 mes de historico com custo marginal quase zero, porque o
#    semanal e um HARD LINK para o diario de domingo — o mesmo inode. So quando
#    o diario de domingo e podado (dia 15) e que o semanal passa a ocupar
#    espaco proprio. Teto de disco: 14 + 4 = 18 copias no pior caso.
#
#    Nao ha mensal/anual de proposito: retencao legal de marcacao de ponto e
#    problema do expurgo LGPD e do AFD assinado (registro fiscal), nao do
#    backup operacional. Backup aqui existe para RESTAURAR, nao para arquivar.
# -----------------------------------------------------------------------------
if [ "$(date -u +%u)" = "7" ]; then
  ln -f "$ARQ" "$DIR_SEMANAL/$(basename "$ARQ")"
  ln -f "${ARQ}.sha256" "$DIR_SEMANAL/$(basename "$ARQ").sha256"
  log "domingo: promovido a semanal (hard link, sem custo de disco)"
fi

podar() {
  local dir="$1" manter="$2" nome
  # shellcheck disable=SC2012  # nomes sao gerados por este script: sem surpresa.
  ls -1t "$dir"/*.dump 2>/dev/null | tail -n "+$((manter + 1))" | while read -r nome; do
    log "retencao: removendo $(basename "$nome")"
    rm -f "$nome" "${nome}.sha256"
  done
}
podar "$DIR_DIARIO" "$RETENCAO_DIARIOS"
podar "$DIR_SEMANAL" "$RETENCAO_SEMANAIS"

# -----------------------------------------------------------------------------
# 6. Copia externa — OPCIONAL, DESLIGADA, NAO CONFIGURADA.
#
#    Nao existe credencial de S3/B2/rclone provisionada para este projeto, e
#    inventar uma seria pior que nao ter: daria falsa sensacao de off-site.
#    Para ligar de verdade, o operador precisa (a) escolher o destino, (b)
#    provisionar a credencial na VPS, (c) exportar PONTO_BACKUP_UPLOAD_CMD no
#    override do systemd (ver instalar-backup-postgres.sh). O comando recebe o
#    caminho do dump como $1. Exemplo do que ficaria la:
#
#        PONTO_BACKUP_UPLOAD_CMD='rclone copy "$1" remoto:ponto-backups/'
#
#    Enquanto isso nao acontecer, vale a limitacao do cabecalho: backup local
#    nao protege contra perda da VPS inteira.
# -----------------------------------------------------------------------------
if [ -n "${PONTO_BACKUP_UPLOAD_CMD:-}" ]; then
  log "copia externa: executando PONTO_BACKUP_UPLOAD_CMD"
  if sh -c "$PONTO_BACKUP_UPLOAD_CMD" _ "$ARQ"; then
    log "copia externa concluida"
  else
    # Nao invalida o backup local, que ja esta gravado e verificado — mas o
    # exit code precisa ser diferente de 0 para o systemd marcar `failed`.
    erro "copia externa FALHOU (o backup local em $ARQ esta integro)"
    exit 6
  fi
else
  log "copia externa nao configurada (PONTO_BACKUP_UPLOAD_CMD vazio) — backup APENAS local"
fi

# Marcador para monitoramento: `stat -c %Y` deste arquivo responde "quando foi o
# ultimo backup que deu certo?" sem precisar interpretar log.
date -u +%FT%TZ > "$BASE/ULTIMO_SUCESSO"
chmod 600 "$BASE/ULTIMO_SUCESSO"
log "concluido"
