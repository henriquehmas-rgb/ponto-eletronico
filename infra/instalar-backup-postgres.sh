#!/bin/bash
# =============================================================================
# instalar-backup-postgres.sh — instala o backup do Postgres como systemd timer
# =============================================================================
# Roda UMA VEZ na VPS, como root. Idempotente: rodar de novo so atualiza os
# arquivos e recarrega o systemd.
#
# Por que systemd timer e nao cron: todo o resto da automacao desta VPS ja e
# systemd (o runner self-hosted do GitHub Actions e
# `actions.runner.henriquehmas-rgb-ponto-eletronico.ponto-vps.service`, ver
# docs/backlog.md 2026-08-07). Timer da, de graca, o que cron nao da: log
# unificado em `journalctl -u`, `Persistent=true` (recupera a execucao perdida
# se a VPS estava desligada na hora), estado consultavel (`systemctl status`,
# `list-timers`) e `RandomizedDelaySec` para nao competir com outros jobs.
#
# O que instala:
#   /usr/local/sbin/backup-postgres.sh           (copia, root:root 700)
#   /usr/local/sbin/restaurar-postgres.sh        (copia, root:root 700)
#   /etc/systemd/system/ponto-backup@.service    (unit template, %i = ambiente)
#   /etc/systemd/system/ponto-backup@.timer      (timer template)
#
# Os scripts sao COPIADOS para /usr/local/sbin em vez de referenciados no
# checkout de proposito: `deploy-hml.sh`/`deploy-prod.sh` fazem
# `git reset --hard`, e o backup nao pode depender de qual commit esta na
# arvore no momento em que o timer dispara. Rode este instalador de novo
# depois de atualizar os scripts no repo.
#
# Uso:
#     sudo /docker/ponto-eletronico/infra/instalar-backup-postgres.sh hml
#     sudo /docker/ponto-prd/infra/instalar-backup-postgres.sh prod
#     sudo ... instalar-backup-postgres.sh hml prod      # os dois
#
# Sem argumento, instala os arquivos mas NAO habilita timer nenhum.
# =============================================================================
set -euo pipefail

log() { printf '[instalar-backup %s] %s\n' "$(date -u +%FT%TZ)" "$*"; }
erro() { printf '[instalar-backup ERRO] %s\n' "$*" >&2; }

[ "$(id -u)" = "0" ] || { erro "precisa rodar como root (use sudo)"; exit 3; }

AQUI="$(cd "$(dirname "$0")" && pwd)"
for f in backup-postgres.sh restaurar-postgres.sh; do
  [ -f "$AQUI/$f" ] || { erro "faltando $AQUI/$f"; exit 3; }
done

# Horario padrao. O relogio da VPS e UTC; 06:30 UTC = 03:30 America/Sao_Paulo,
# fora do pico e depois do fechamento do dia anterior de apuracao.
HORARIO="${PONTO_BACKUP_ONCALENDAR:-*-*-* 06:30:00}"

# -----------------------------------------------------------------------------
# 1. Scripts
# -----------------------------------------------------------------------------
install -m 700 -o root -g root "$AQUI/backup-postgres.sh"    /usr/local/sbin/backup-postgres.sh
install -m 700 -o root -g root "$AQUI/restaurar-postgres.sh" /usr/local/sbin/restaurar-postgres.sh
log "scripts instalados em /usr/local/sbin"

install -d -m 700 -o root -g root /var/backups/ponto

# -----------------------------------------------------------------------------
# 2. Unit template. `%i` e o ambiente (hml/prod/teste).
# -----------------------------------------------------------------------------
cat > /etc/systemd/system/ponto-backup@.service <<'UNIT'
[Unit]
Description=Backup do Postgres do SEEG Ponto (ambiente %i)
Documentation=file:///docker/ponto-eletronico/docs/runbook-deploy-producao.md
# Sem Docker nao ha o que fazer; nao adianta tentar e falhar.
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/backup-postgres.sh %i
User=root
# Dump de banco = dado pessoal. Arquivos nascem 600 (o script tambem faz umask).
UMask=0077
# Backup nao pode competir com a aplicacao por I/O.
IOSchedulingClass=idle
Nice=10
# Um dump que trava nao pode ficar pendurado ate o proximo timer.
TimeoutStartSec=2h

# Para ligar copia externa (DESLIGADA por padrao, ver secao 6 do
# backup-postgres.sh), crie um override — NAO edite esta unit:
#     systemctl edit ponto-backup@prod
# e escreva la, com a credencial ja provisionada na VPS:
#     [Service]
#     Environment=PONTO_BACKUP_UPLOAD_CMD=rclone copy "$1" remoto:ponto-backups/
# Nenhuma credencial de armazenamento externo existe hoje neste projeto.

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/ponto-backup@.timer <<UNIT
[Unit]
Description=Backup diario do Postgres do SEEG Ponto (ambiente %i)

[Timer]
OnCalendar=$HORARIO
# Se a VPS estava desligada na hora marcada, roda assim que voltar.
Persistent=true
# Espalha o disparo para nao bater de frente com outros jobs da VPS.
RandomizedDelaySec=600
Unit=ponto-backup@%i.service

[Install]
WantedBy=timers.target
UNIT

chmod 644 /etc/systemd/system/ponto-backup@.service /etc/systemd/system/ponto-backup@.timer
systemctl daemon-reload
log "units instaladas (OnCalendar=$HORARIO, horario da VPS: $(date +%Z))"

# -----------------------------------------------------------------------------
# 3. Habilitar por ambiente
# -----------------------------------------------------------------------------
if [ $# -eq 0 ]; then
  log "nenhum ambiente passado — nada foi habilitado."
  log "para habilitar: systemctl enable --now ponto-backup@hml.timer"
  exit 0
fi

for amb in "$@"; do
  case "$amb" in
    hml|prod|teste) : ;;
    *) erro "ambiente invalido: '$amb' (use hml, prod ou teste)"; exit 2 ;;
  esac
  systemctl enable --now "ponto-backup@$amb.timer"
  log "timer habilitado: ponto-backup@$amb.timer"
done

echo
systemctl list-timers --all --no-pager 'ponto-backup@*' || true
echo
log "primeiro backup manual (recomendado, nao espere o timer):"
for amb in "$@"; do
  log "    systemctl start ponto-backup@$amb.service && journalctl -u ponto-backup@$amb -n 30 --no-pager"
done
