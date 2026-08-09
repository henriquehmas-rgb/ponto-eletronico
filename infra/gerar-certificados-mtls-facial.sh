#!/bin/bash
# =============================================================================
# gerar-certificados-mtls-facial.sh — CA interna + par de certificados do
# mTLS entre `api` (cliente) e `facial-svc` (servidor)
# =============================================================================
# Fecha o gap #4 registrado em docs/backlog.md (2026-08-09, entrada do motor
# facial conectado): "mTLS api<->facial-svc sem certificado de cliente
# provisionado em lugar nenhum". O lado SERVIDOR ja era configuravel desde a
# F14/A2 (`FACIAL_TLS_CERT_PATH`/`FACIAL_TLS_KEY_PATH`/`FACIAL_MTLS_CA_PATH`
# no servico `facial-svc`), mas nenhum certificado de CLIENTE existia — entao
# `app/biometria/cliente_facial.py` nao tinha como montar o cliente e a API
# falhava fechada em qualquer deploy com mTLS ligado.
#
# -----------------------------------------------------------------------------
# ISTO NAO E, E NUNCA SERA, O CERTIFICADO ICP-Brasil
# -----------------------------------------------------------------------------
# O projeto tem TRES materiais criptograficos distintos, e confundi-los custa
# caro:
#
#   1. TLS publico (api.ponto.<dominio>) ....... Let's Encrypt, emitido e
#      renovado sozinho pelo Traefik da VPS. Nada a fazer aqui.
#   2. ICP-Brasil A1 (`CERT_ICP_*`) ............ COMPRADO de uma AC credenciada,
#      assina AFD/AEJ e espelhos (.p7s). NAO e gerado por script nenhum. Este
#      arquivo nao toca nele.
#   3. mTLS interno api <-> facial-svc ......... E ISTO AQUI. CA propria,
#      autoassinada, usada por exatamente dois containers na rede privada da
#      stack. Ninguem fora dela precisa confiar nesta CA, e por isso ela nao
#      tem (nem deve ter) qualquer relacao com AC publica ou credenciada.
#
# -----------------------------------------------------------------------------
# O QUE E GERADO
# -----------------------------------------------------------------------------
#   <saida>/ca/ca.key .............. chave da CA. NUNCA vai para container
#                                    nenhum; fica so aqui, para reemitir os
#                                    certificados quando vencerem.
#   <saida>/ca/ca.pem .............. certificado da CA (publico).
#   <saida>/servidor/servidor.key .. chave do facial-svc (lado servidor)
#   <saida>/servidor/servidor.pem .. certificado do facial-svc
#   <saida>/servidor/ca.pem ........ copia da CA, para o facial-svc VERIFICAR
#                                    o certificado que a api apresenta
#   <saida>/cliente/cliente.key .... chave da api (lado cliente)
#   <saida>/cliente/cliente.pem .... certificado da api
#   <saida>/cliente/ca.pem ......... copia da CA, para a api VERIFICAR o
#                                    certificado que o facial-svc apresenta
#
# Sao DOIS diretorios de proposito, e nao um so: cada container monta apenas o
# seu, e a chave privada do servidor nunca fica visivel dentro da `api` (nem a
# do cliente dentro do `facial-svc`). A chave da CA nao e montada em lugar
# nenhum — quem a tiver pode emitir um certificado de cliente novo e falar com
# o motor facial.
#
# Os dois diretorios sao montados no MESMO caminho de container
# (`/run/secrets/facial-tls`, somente leitura) porque `FACIAL_MTLS_CA_PATH` e
# uma variavel so, lida pelos dois servicos: com o mesmo ponto de montagem,
# `/run/secrets/facial-tls/ca.pem` vale nos dois lados.
#
# -----------------------------------------------------------------------------
# EXTENSOES DOS CERTIFICADOS (por que sao estas)
# -----------------------------------------------------------------------------
# * SAN do servidor: `facial-svc` (o nome do servico na rede do compose, que e
#   o host de `FACIAL_SVC_URL`), mais `localhost`/`127.0.0.1` — estes dois
#   porque o HEALTHCHECK do proprio container bate em si mesmo, e com mTLS
#   ligado ele passa a falar HTTPS. Sem o SAN local, o healthcheck falharia na
#   verificacao de hostname e o `facial-svc` nunca ficaria `healthy` (a `api`
#   declara `depends_on: service_healthy` sobre ele: a stack inteira travaria).
# * EKU do servidor: `serverAuth` E `clientAuth`. O `clientAuth` existe pelo
#   mesmo motivo: no healthcheck o container e cliente de si mesmo, e o
#   servidor exige certificado de cliente (`CERT_REQUIRED`).
# * EKU do cliente: `clientAuth` apenas. A `api` nunca e servidora deste par.
# * `basicConstraints=CA:FALSE` nas duas folhas: nenhuma delas pode assinar
#   outro certificado.
#
# -----------------------------------------------------------------------------
# VALIDADE E RENOVACAO — LEIA ANTES DE RODAR
# -----------------------------------------------------------------------------
# Padrao: CA 3650 dias (10 anos), folhas 825 dias (~2 anos e 3 meses). Os mesmos
# numeros ja documentados na tabela de expiracoes de
# docs/runbook-deploy-producao.md.
#
# NAO HA RENOVACAO AUTOMATICA. Quando as folhas vencerem, o handshake passa a
# ser recusado e o reconhecimento facial para de responder — enroll falha
# fechado (503) e a marcacao segue sem o sinal facial (ADR-008). Anote a data
# impressa no fim desta execucao. Para renovar, rode este script de novo com
# `--forcar` (a CA e reaproveitada se ja existir: os containers continuam
# confiando nela, so as folhas trocam) e reinicie `api` e `facial-svc`.
#
# -----------------------------------------------------------------------------
# USO
# -----------------------------------------------------------------------------
#     ./gerar-certificados-mtls-facial.sh                 # -> infra/keys/mtls-facial
#     ./gerar-certificados-mtls-facial.sh /caminho/saida
#     ./gerar-certificados-mtls-facial.sh --forcar        # reemite as folhas
#
# Variaveis de ambiente aceitas:
#   DIAS_CA=<n>            validade da CA em dias        (default 3650)
#   DIAS_FOLHA=<n>         validade das folhas em dias   (default 825)
#   NOME_SERVIDOR=<nome>   nome de rede do facial-svc    (default facial-svc)
#   SANS_EXTRA=<lista>     SANs adicionais separados por virgula, ja no formato
#                          do openssl. Ex.: "DNS:facial.interno,IP:10.0.0.7"
#
# A saida fica em infra/keys/, que o .gitignore ja bloqueia por inteiro
# (`infra/keys/`, secao 1). Chave privada NUNCA entra no git.
# =============================================================================
set -euo pipefail

log() { printf '[certs-mtls-facial %s] %s\n' "$(date -u +%FT%TZ)" "$*"; }
erro() { printf '[certs-mtls-facial ERRO] %s\n' "$*" >&2; }

AQUI="$(cd "$(dirname "$0")" && pwd)"

DIAS_CA="${DIAS_CA:-3650}"
DIAS_FOLHA="${DIAS_FOLHA:-825}"
NOME_SERVIDOR="${NOME_SERVIDOR:-facial-svc}"
SANS_EXTRA="${SANS_EXTRA:-}"

FORCAR=0
SAIDA=""
for arg in "$@"; do
  case "$arg" in
    --forcar) FORCAR=1 ;;
    -h|--help) sed -n '1,110p' "$0"; exit 0 ;;
    -*) erro "opcao desconhecida: $arg"; exit 2 ;;
    *) SAIDA="$arg" ;;
  esac
done
SAIDA="${SAIDA:-$AQUI/keys/mtls-facial}"

command -v openssl >/dev/null 2>&1 || { erro "openssl nao encontrado no PATH"; exit 3; }

DIR_CA="$SAIDA/ca"
DIR_SRV="$SAIDA/servidor"
DIR_CLI="$SAIDA/cliente"

# -----------------------------------------------------------------------------
# 1. Portao de sobrescrita. Reemitir por engano quebra a stack em producao:
#    os containers continuam com os arquivos antigos em memoria ate reiniciar,
#    e ai passam a apresentar certificados que a CA nova nao assinou.
# -----------------------------------------------------------------------------
if [ "$FORCAR" != "1" ]; then
  for f in "$DIR_SRV/servidor.pem" "$DIR_CLI/cliente.pem"; do
    if [ -e "$f" ]; then
      erro "ja existe: $f"
      erro "rode com --forcar para reemitir (a CA existente e reaproveitada)."
      exit 4
    fi
  done
fi

umask 077
mkdir -p "$DIR_CA" "$DIR_SRV" "$DIR_CLI"
chmod 700 "$SAIDA" "$DIR_CA" "$DIR_SRV" "$DIR_CLI"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# -----------------------------------------------------------------------------
# 2. CA propria. Reaproveitada se ja existir: trocar a CA obriga a reconfigurar
#    os DOIS lados ao mesmo tempo, e nao ha motivo para isso numa renovacao de
#    rotina das folhas.
# -----------------------------------------------------------------------------
if [ -f "$DIR_CA/ca.pem" ] && [ -f "$DIR_CA/ca.key" ]; then
  log "CA existente reaproveitada: $DIR_CA/ca.pem"
else
  log "gerando CA propria (validade ${DIAS_CA} dias)"
  openssl req -x509 -newkey rsa:4096 -sha256 -nodes \
    -days "$DIAS_CA" \
    -keyout "$DIR_CA/ca.key" \
    -out "$DIR_CA/ca.pem" \
    -subj "/CN=ponto-mtls-facial-ca/O=SEEG Ponto" \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" \
    2>/dev/null
fi

# -----------------------------------------------------------------------------
# 3. Certificado de SERVIDOR (facial-svc)
# -----------------------------------------------------------------------------
SANS="DNS:${NOME_SERVIDOR},DNS:localhost,IP:127.0.0.1"
[ -n "$SANS_EXTRA" ] && SANS="${SANS},${SANS_EXTRA}"

cat > "$TMP/servidor.ext" <<EXT
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth,clientAuth
subjectAltName=${SANS}
EXT

log "gerando certificado de SERVIDOR (CN=${NOME_SERVIDOR}, SAN=${SANS}, ${DIAS_FOLHA} dias)"
openssl req -newkey rsa:4096 -sha256 -nodes \
  -keyout "$DIR_SRV/servidor.key" \
  -out "$TMP/servidor.csr" \
  -subj "/CN=${NOME_SERVIDOR}/O=SEEG Ponto" 2>/dev/null
openssl x509 -req -in "$TMP/servidor.csr" -sha256 \
  -CA "$DIR_CA/ca.pem" -CAkey "$DIR_CA/ca.key" -CAcreateserial \
  -CAserial "$DIR_CA/ca.srl" \
  -days "$DIAS_FOLHA" -extfile "$TMP/servidor.ext" \
  -out "$DIR_SRV/servidor.pem" 2>/dev/null

# -----------------------------------------------------------------------------
# 4. Certificado de CLIENTE (api)
# -----------------------------------------------------------------------------
cat > "$TMP/cliente.ext" <<'EXT'
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=clientAuth
EXT

log "gerando certificado de CLIENTE (CN=ponto-api, ${DIAS_FOLHA} dias)"
openssl req -newkey rsa:4096 -sha256 -nodes \
  -keyout "$DIR_CLI/cliente.key" \
  -out "$TMP/cliente.csr" \
  -subj "/CN=ponto-api/O=SEEG Ponto" 2>/dev/null
openssl x509 -req -in "$TMP/cliente.csr" -sha256 \
  -CA "$DIR_CA/ca.pem" -CAkey "$DIR_CA/ca.key" \
  -CAserial "$DIR_CA/ca.srl" \
  -days "$DIAS_FOLHA" -extfile "$TMP/cliente.ext" \
  -out "$DIR_CLI/cliente.pem" 2>/dev/null

# -----------------------------------------------------------------------------
# 5. Copia da CA em cada diretorio montado + permissoes
# -----------------------------------------------------------------------------
cp "$DIR_CA/ca.pem" "$DIR_SRV/ca.pem"
cp "$DIR_CA/ca.pem" "$DIR_CLI/ca.pem"

chmod 600 "$DIR_CA/ca.key" "$DIR_SRV/servidor.key" "$DIR_CLI/cliente.key"
chmod 644 "$DIR_CA/ca.pem" "$DIR_SRV/ca.pem" "$DIR_CLI/ca.pem" \
          "$DIR_SRV/servidor.pem" "$DIR_CLI/cliente.pem"

# -----------------------------------------------------------------------------
# 5b. DONO dos diretorios que vao virar bind mount.
#
# Achado real desta sessao, verificado na VPS: `api` e `facial-svc` rodam como
# uid/gid 1001 (`ponto`, criado nos Dockerfiles). Um arquivo root:root modo 600
# montado somente-leitura NAO e legivel por esse usuario -- e um diretorio 700
# root nem sequer e atravessavel. O resultado seria um mTLS que passa em
# `docker compose config`, sobe sem erro e falha na PRIMEIRA chamada real, com
# "Permission denied" em vez de qualquer mensagem sobre TLS.
#
# Por isso `servidor/` e `cliente/` passam a pertencer ao usuario do container
# (700 no diretorio, 600 na chave: ninguem mais no host le). `ca/` NAO muda de
# dono -- a chave da CA continua exclusiva do root e nunca e montada.
#
# Sem privilegio (rodando como usuario comum, ex. na maquina de dev), o chown
# falha: e so um aviso, porque nessa situacao os arquivos ja pertencem a quem
# rodou o script e o problema nao existe.
# -----------------------------------------------------------------------------
UID_CONTAINER="${UID_CONTAINER:-1001}"
GID_CONTAINER="${GID_CONTAINER:-1001}"
if chown -R "${UID_CONTAINER}:${GID_CONTAINER}" "$DIR_SRV" "$DIR_CLI" 2>/dev/null; then
  log "servidor/ e cliente/ agora pertencem a ${UID_CONTAINER}:${GID_CONTAINER} (usuario dos containers)"
else
  log "AVISO: nao foi possivel fazer chown para ${UID_CONTAINER}:${GID_CONTAINER}"
  log "AVISO: rode como root na VPS, ou os containers nao vao conseguir ler as chaves"
fi

# -----------------------------------------------------------------------------
# 6. Verificacao real: a cadeia fecha? (barato, e pega erro de extensao)
# -----------------------------------------------------------------------------
openssl verify -CAfile "$DIR_CA/ca.pem" "$DIR_SRV/servidor.pem" >/dev/null
openssl verify -CAfile "$DIR_CA/ca.pem" "$DIR_CLI/cliente.pem" >/dev/null
log "cadeia verificada: as duas folhas sao validas contra a CA gerada"

VENC_SRV="$(openssl x509 -enddate -noout -in "$DIR_SRV/servidor.pem" | cut -d= -f2)"
VENC_CLI="$(openssl x509 -enddate -noout -in "$DIR_CLI/cliente.pem" | cut -d= -f2)"
VENC_CA="$(openssl x509 -enddate -noout -in "$DIR_CA/ca.pem" | cut -d= -f2)"

cat <<RESUMO

=============================================================================
CERTIFICADOS mTLS api <-> facial-svc GERADOS
=============================================================================
Saida: $SAIDA

  CA        $DIR_CA/ca.pem        vence em  $VENC_CA
  servidor  $DIR_SRV/servidor.pem vence em  $VENC_SRV
  cliente   $DIR_CLI/cliente.pem  vence em  $VENC_CLI

ANOTE AS DATAS: nao ha renovacao automatica. Quando as folhas vencerem, o
handshake e recusado e o reconhecimento facial para de responder.

-----------------------------------------------------------------------------
Copie para a VPS (fora do checkout do git) e ajuste o .env do ambiente:
-----------------------------------------------------------------------------
  # no HOST da VPS, como root. O dono ${UID_CONTAINER}:${GID_CONTAINER} e
  # obrigatorio: e o usuario sem privilegio que roda dentro dos containers, e
  # arquivo root:root modo 600 nao e legivel por ele.
  install -d -m 700 -o ${UID_CONTAINER} -g ${GID_CONTAINER} \\
    /docker/ponto-prd/certs-facial /docker/ponto-prd/certs-facial-api
  install -m 644 -o ${UID_CONTAINER} -g ${GID_CONTAINER} \\
    $DIR_SRV/ca.pem $DIR_SRV/servidor.pem /docker/ponto-prd/certs-facial/
  install -m 600 -o ${UID_CONTAINER} -g ${GID_CONTAINER} \\
    $DIR_SRV/servidor.key /docker/ponto-prd/certs-facial/
  install -m 644 -o ${UID_CONTAINER} -g ${GID_CONTAINER} \\
    $DIR_CLI/ca.pem $DIR_CLI/cliente.pem /docker/ponto-prd/certs-facial-api/
  install -m 600 -o ${UID_CONTAINER} -g ${GID_CONTAINER} \\
    $DIR_CLI/cliente.key /docker/ponto-prd/certs-facial-api/

  # infra/.env.prod
  FACIAL_CERTS_DIR=/docker/ponto-prd/certs-facial
  FACIAL_CERTS_CLIENTE_DIR=/docker/ponto-prd/certs-facial-api
  FACIAL_MTLS_CA_PATH=/run/secrets/facial-tls/ca.pem
  FACIAL_TLS_CERT_PATH=/run/secrets/facial-tls/servidor.pem
  FACIAL_TLS_KEY_PATH=/run/secrets/facial-tls/servidor.key
  FACIAL_MTLS_CERT_PATH=/run/secrets/facial-tls/cliente.pem
  FACIAL_MTLS_KEY_PATH=/run/secrets/facial-tls/cliente.key
  FACIAL_SVC_URL=https://${NOME_SERVIDOR}:8000    # https, nao http

A chave da CA ($DIR_CA/ca.key) NAO vai para a VPS: quem a tem pode emitir um
cliente novo e falar com o motor facial. Guarde-a onde voce guarda segredo.
=============================================================================
RESUMO
