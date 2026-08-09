# Runbook — deploy de PRODUÇÃO (SEEG Ponto)

> **Estado deste documento: SCAFFOLD.** Nada aqui foi executado. Toda a
> infraestrutura de produção existe hoje só como arquivo de configuração; não há
> domínio, certificado, banco nem stack de produção provisionado. Este runbook
> descreve o que **o dono do produto precisa fazer**, na ordem, antes do primeiro
> deploy real — e o processo de rotina depois disso.

## Sumário

- [0. O que já existe e o que não existe](#0-o-que-já-existe-e-o-que-não-existe)
- [Parte I — Antes do PRIMEIRO deploy (uma vez só)](#parte-i--antes-do-primeiro-deploy-uma-vez-só)
  - [Passo 1 — Domínio e DNS](#passo-1--domínio-e-dns)
  - [Passo 2 — Certificado TLS público](#passo-2--certificado-tls-público)
  - [Passo 3 — Diretório e checkout de produção na VPS](#passo-3--diretório-e-checkout-de-produção-na-vps)
  - [Passo 4 — Segredos locais da VPS: JWT, mTLS facial, ICP-Brasil](#passo-4--segredos-locais-da-vps-jwt-mtls-facial-icp-brasil)
  - [Passo 5 — Preencher o `.env.prod`](#passo-5--preencher-o-envprod)
  - [Passo 6 — GitHub: environment, sudoers e runner](#passo-6--github-environment-sudoers-e-runner)
  - [Passo 7 — Primeiro `up` e migration inicial](#passo-7--primeiro-up-e-migration-inicial)
  - [Passo 8 — Validação de aceite](#passo-8--validação-de-aceite)
- [Parte II — Deploy de rotina](#parte-ii--deploy-de-rotina)
- [Parte III — Rollback](#parte-iii--rollback)
- [Parte IV — Operações do dia a dia](#parte-iv--operações-do-dia-a-dia)
- [Parte V — Backup do banco](#parte-v--backup-do-banco)
- [Anexo — Diferenças hml × prd](#anexo--diferenças-hml--prd)

---

## 0. O que já existe e o que não existe

**Existe e funciona hoje (homologação):**

| Item | Onde |
| --- | --- |
| Stack de hml | `infra/docker-compose.yml` + `infra/.env` (na VPS) |
| Deploy de hml | `infra/deploy-hml.sh` — **mora só na VPS**, em `/docker/ponto-eletronico/infra/`, **não é versionado** |
| CI/CD de hml | `.github/workflows/ci.yml`, jobs `deploy-hml` e `deploy-hml-aplicar` — automático a cada push em `main` |
| Runner | self-hosted na própria VPS, usuário `ghrunner`, label `ponto-vps` |
| Traefik | já roda na VPS, é quem escuta 80/443, rede Docker `traefik` |

**Criado agora, como scaffold (nada aplicado):**

| Arquivo | Papel |
| --- | --- |
| `infra/docker-compose.prod.yml` | stack de produção, exclusiva dela |
| `infra/.env.prod.example` | modelo das variáveis de produção, sem nenhum valor real |
| `infra/deploy-prod.sh` | deploy de produção, com confirmação explícita obrigatória |
| `.github/workflows/deploy-prod.yml` | job de deploy de prd, **só `workflow_dispatch` manual** |
| este runbook | o que fazer antes e depois |

**Criado depois, e este já foi executado de verdade (2026-08-09):**

| Arquivo | Papel |
| --- | --- |
| `infra/backup-postgres.sh` | dump `pg_dump -Fc`, verificação e retenção — ver [Parte V](#parte-v--backup-do-banco) |
| `infra/restaurar-postgres.sh` | restore com dois portões de confirmação (**destrutivo**) |
| `infra/instalar-backup-postgres.sh` | instala unit + timer do systemd na VPS |

Ciclo completo (backup → banco novo → restore → conferência de contagens)
validado contra o Postgres de **teste** da VPS. Em `prod` nada foi executado,
porque o stack de produção ainda não existe.

**Não existe:** domínio de produção, registros DNS, certificado TLS, certificado
ICP-Brasil, CA interna de mTLS, banco de produção, `infra/.env.prod`,
`/docker/ponto-prd` na VPS, environment `producao` no GitHub.

> ⚠️ **Nota de contexto (2026-08-08):** o CI/CD do GitHub está bloqueado por
> billing desde 08/08. Enquanto isso não for resolvido, o `deploy-prod.yml` não
> vai conseguir rodar — o caminho manual (SSH + `deploy-prod.sh --confirmar`)
> continua válido e é inclusive o recomendado para o **primeiro** deploy.

---

## Parte I — Antes do PRIMEIRO deploy (uma vez só)

### Passo 1 — Domínio e DNS

**Responsável: dono do produto. Não é decisão técnica delegável.**

1. Escolha/registre o domínio de produção. Ele **precisa ser diferente** do
   domínio usado hoje em homologação — os dois stacks convivem na mesma VPS e o
   Traefik roteia por `Host()`.
2. Crie **quatro** registros `A` (e `AAAA`, se a VPS tiver IPv6) apontando para
   o IP da VPS:

   | Host | Serviço |
   | --- | --- |
   | `ponto.SEU-DOMINIO` | web (Next.js) |
   | `api.ponto.SEU-DOMINIO` | api (FastAPI) |
   | `dev.ponto.SEU-DOMINIO` | device-gw (Push/Monitor Control iD) |
   | `docs.ponto.SEU-DOMINIO` | portal OpenAPI |

3. Espere a propagação e confirme **antes** de seguir:

   ```bash
   for h in ponto api.ponto dev.ponto docs.ponto; do
     dig +short "$h.SEU-DOMINIO"
   done
   ```

   Todos precisam devolver o IP da VPS. Se o DNS não estiver resolvendo, o
   Let's Encrypt falha no desafio HTTP-01 e o stack sobe sem certificado.

**Decisão pendente:** `docs.ponto.*` publica o Swagger UI da API na internet.
Se o portal OpenAPI não deve ser público em produção, remova o router
`ponto-prd-docs` das labels do serviço `api` em `infra/docker-compose.prod.yml`
antes do primeiro `up` (e não crie o registro DNS correspondente).

### Passo 2 — Certificado TLS público

**Não há arquivo de certificado a instalar.** O Traefik global da VPS já roda
com um *certificate resolver* ACME (Let's Encrypt) e emite/renova sozinho para
cada `Host()` que aparecer nas labels.

O que conferir:

```bash
# Nome do resolver configurado no Traefik da VPS:
docker inspect <container-do-traefik> | grep -i certresolver
```

Se o resolver não se chamar `letsencrypt`, ajuste `TRAEFIK_CERTRESOLVER` no
`.env.prod`. Se o Traefik da VPS não tiver resolver ACME configurado, **pare
aqui**: emitir certificado é responsabilidade dele, não deste stack.

> Não confundir com os outros dois certificados do projeto, que **não** são
> Let's Encrypt e não são emitidos automaticamente:
> - **mTLS do motor facial** (`FACIAL_TLS_*` / `FACIAL_MTLS_*`) — CA interna
>   própria, emitida por `infra/gerar-certificados-mtls-facial.sh`, passo 4b.
> - **ICP-Brasil A1** (`CERT_ICP_*`) — comprado de uma AC credenciada, assina
>   AFD/AEJ e espelhos `.p7s`, passo 4.

### Passo 3 — Diretório e checkout de produção na VPS

Produção mora em diretório **separado** do de homologação
(`/docker/ponto-eletronico`). O `deploy-prod.sh` inclusive se recusa a rodar se
apontado para o diretório de hml.

```bash
ssh vps
sudo mkdir -p /docker/ponto-prd
sudo git clone <url-do-repo> /docker/ponto-prd
sudo git -C /docker/ponto-prd checkout main
sudo chown -R root:root /docker/ponto-prd
sudo chmod 700 /docker/ponto-prd
```

### Passo 4 — Segredos locais da VPS: JWT, mTLS facial, ICP-Brasil

Nenhum destes vem do GitHub: são arquivos que vivem só na VPS.

**4a. Par de chaves JWT (próprio de produção — nunca reaproveite o de hml):**

```bash
cd /docker/ponto-prd
sudo make keys                     # gera infra/keys/{private,public}.pem (RSA 4096)
sudo mkdir -p /docker/ponto-prd/keys
sudo cp infra/keys/*.pem /docker/ponto-prd/keys/
sudo chmod 700 /docker/ponto-prd/keys
sudo chmod 600 /docker/ponto-prd/keys/private.pem
```

**4b. mTLS `api` ↔ `facial-svc` (F14/A2) — obrigatório em produção.**
São **dois** certificados de uma CA interna própria, não um: o `facial-svc` é o
servidor (apresenta `servidor.pem`) e a `api` é o cliente (apresenta
`cliente.pem`). Sem o certificado de cliente, `app/biometria/cliente_facial.py`
se recusa a montar o cliente em produção (`MtlsNaoConfigurado` →
`PONTO-INT-001`) e **toda** operação facial falha — enroll e verificação.

Em dev/hml, deixar os caminhos vazios faz `facial/servidor.py` subir em **HTTP
puro**. Em produção isso significaria biometria trafegando em claro entre
containers, então `docker-compose.prod.yml` exige todas (`:?`) e o `up` falha se
faltar alguma.

Não confundir com o ICP-Brasil do passo 4c: são materiais completamente
diferentes, e esta CA aqui é interna, autoassinada e só precisa ser conhecida
por estes dois containers.

Emita com o script versionado — ele já gera a CA, as duas folhas com as
extensões certas (SAN `facial-svc`/`localhost`/`127.0.0.1` e
`extendedKeyUsage=serverAuth,clientAuth` no servidor, exigidos pelo healthcheck
do próprio container, que passa a falar HTTPS quando o mTLS liga), verifica a
cadeia e imprime as datas de expiração:

```bash
cd /docker/ponto-prd
sudo ./infra/gerar-certificados-mtls-facial.sh
# saída: infra/keys/mtls-facial/{ca,servidor,cliente}/

# instale FORA do checkout do git, em dois diretórios separados.
# Dono 1001:1001 é OBRIGATÓRIO: é o usuário sem privilégio (`ponto`) que roda
# dentro dos containers. Arquivo root:root modo 600 num bind mount NÃO é
# legível por ele, e o sintoma seria "Permission denied" na primeira chamada
# real — nada que mencione TLS.
sudo install -d -m 700 -o 1001 -g 1001 \
  /docker/ponto-prd/certs-facial /docker/ponto-prd/certs-facial-api
sudo install -m 644 -o 1001 -g 1001 \
  infra/keys/mtls-facial/servidor/{ca.pem,servidor.pem} /docker/ponto-prd/certs-facial/
sudo install -m 600 -o 1001 -g 1001 \
  infra/keys/mtls-facial/servidor/servidor.key /docker/ponto-prd/certs-facial/
sudo install -m 644 -o 1001 -g 1001 \
  infra/keys/mtls-facial/cliente/{ca.pem,cliente.pem} /docker/ponto-prd/certs-facial-api/
sudo install -m 600 -o 1001 -g 1001 \
  infra/keys/mtls-facial/cliente/cliente.key /docker/ponto-prd/certs-facial-api/
```

Dois diretórios de propósito: a chave privada do servidor nunca fica visível
dentro do container da `api`, nem a do cliente dentro do `facial-svc`. Os dois
são montados no **mesmo** ponto (`/run/secrets/facial-tls`, só leitura), cada um
com sua cópia de `ca.pem` — é isso que permite `FACIAL_MTLS_CA_PATH` ser um
valor só, válido dos dois lados.

**A chave da CA (`infra/keys/mtls-facial/ca/ca.key`) não vai para nenhum
container.** Quem a tiver pode emitir um certificado de cliente novo e falar com
o motor facial. Guarde-a onde você guarda segredo — e é ela que você vai
precisar para renovar as folhas sem reconfigurar os dois lados.

Renovação: **manual**, sem automação nenhuma. Anote as datas que o script
imprime (folhas: 825 dias). Quando vencerem, o handshake é recusado e o
reconhecimento facial para de responder. Para renovar, rode o script de novo com
`--forcar` na mesma pasta (a CA existente é reaproveitada, só as folhas trocam),
recopie os arquivos e reinicie `api` e `facial-svc`.

Com mTLS ligado, `FACIAL_SVC_URL` precisa ser `https://facial-svc:8000` — já é o
default do compose de produção.

**4c. Certificado ICP-Brasil A1 (`.pfx`/`.p12`).**
Comprado pelo dono do produto junto a uma AC credenciada. Não é gerável.

```bash
sudo mkdir -p /docker/ponto-prd/certs-icp
sudo cp certificado.pfx /docker/ponto-prd/certs-icp/
sudo chmod 700 /docker/ponto-prd/certs-icp
sudo chmod 600 /docker/ponto-prd/certs-icp/certificado.pfx
```

### Passo 5 — Preencher o `.env.prod`

```bash
cd /docker/ponto-prd/infra
sudo cp .env.prod.example .env.prod
sudo chmod 600 .env.prod            # o deploy-prod.sh recusa qualquer outra permissão
sudo nano .env.prod
```

Toda linha marcada `PREENCHER-...` no exemplo precisa virar valor real. Senhas:
aleatórias, 32+ caracteres, **diferentes das de homologação**:

```bash
openssl rand -base64 32
```

Descobrir o CIDR do Traefik para `PROXIES_CONFIAVEIS` (sem isso, o IP gravado na
auditoria de cada marcação é o do proxy, não o do usuário):

```bash
docker network inspect traefik -f '{{(index .IPAM.Config 0).Subnet}}'
```

`TAG`: o SHA curto do commit cujas imagens o CI publicou. **Nunca `latest`** —
o script e o workflow recusam. Rollback depende de a tag anterior continuar
apontando para o mesmo binário.

Valide sem subir nada:

```bash
cd /docker/ponto-prd/infra
sudo docker compose -p ponto-prd --env-file .env.prod -f docker-compose.prod.yml config --quiet
```

Toda variável obrigatória faltando aparece aqui, uma por vez.

### Passo 6 — GitHub: environment, sudoers e runner

Só necessário para o deploy **pelo CI**. O primeiro deploy pode (e deve) ser
manual.

1. **Environment `producao`** — GitHub → Settings → Environments → New
   environment → `producao` → *Required reviewers* (você mesmo já basta). O job
   `deploy-prod-aplicar` fica na fila até alguém aprovar. Sem esse environment,
   o job falha ao iniciar.
2. **Sudoers scoped** — o `ghrunner` não é root; precisa poder executar
   exatamente um caminho, e mais nada:

   ```bash
   sudo tee /etc/sudoers.d/ghrunner-deploy-prod >/dev/null <<'EOF'
   ghrunner ALL=(root) NOPASSWD: /docker/ponto-prd/infra/deploy-prod.sh
   EOF
   sudo chmod 440 /etc/sudoers.d/ghrunner-deploy-prod
   sudo visudo -c
   ```

   Modele pelo `/etc/sudoers.d/ghrunner-deploy-hml` que já existe.
3. **Permissão do script:**

   ```bash
   sudo chown root:root /docker/ponto-prd/infra/deploy-prod.sh
   sudo chmod 700 /docker/ponto-prd/infra/deploy-prod.sh
   ```

4. O runner self-hosted (`ponto-vps`) já existe e é compartilhado com o deploy
   de hml — nada a criar.

### Passo 7 — Primeiro `up` e migration inicial

**Faça este primeiro deploy manualmente, pela SSH, não pelo CI.** Você quer ver
cada passo.

```bash
ssh vps
sudo /docker/ponto-prd/infra/deploy-prod.sh --confirmar
```

O script, na ordem: exige a confirmação → confere diretório, compose, `.env.prod`
e sua permissão → `git fetch` + `reset --hard origin/main` → valida a TAG (recusa
`latest`) e salva a anterior em `.tag-anterior` → `docker compose config` →
`pull` → `up -d --remove-orphans` → `alembic upgrade head` → `ps`.

A migration inicial roda com a credencial **administrativa**
(`POSTGRES_USER`/`POSTGRES_PASSWORD`) e cria, entre outras coisas, a role de
login de privilégio mínimo `ponto_app_runtime` (migration `0004_role_login_app`)
— é essa role que os serviços usam em runtime, porque RLS não se aplica a
superusuário (ADR-001).

Se a migration falhar, os containers já estão de pé mas o banco está
inconsistente: **não tente de novo às cegas**. Leia o erro, veja
[Parte III — Rollback](#parte-iii--rollback).

### Passo 8 — Validação de aceite

```bash
# 1. Todos healthy?
sudo docker compose -p ponto-prd --env-file /docker/ponto-prd/infra/.env.prod \
  -f /docker/ponto-prd/infra/docker-compose.prod.yml ps

# 2. Saúde pela rede interna (não depende de DNS nem de certificado)
docker run --rm --network ponto-prd-interna curlimages/curl:latest \
  -sS http://api:8000/v1/admin/saude | python3 -m json.tool
```

O JSON precisa trazer `"ambiente": "prd"` e todas as dependências
(postgres, redis, minio, facial) em estado saudável. `"ambiente"` diferente de
`prd` significa que o compose errado foi usado — pare e investigue.

```bash
# 3. Saúde pela internet, já com TLS
curl -sS https://api.ponto.SEU-DOMINIO/v1/admin/saude | python3 -m json.tool
curl -sSI https://ponto.SEU-DOMINIO | head -1        # web responde
curl -sSI https://dev.ponto.SEU-DOMINIO/health       # device-gw responde
```

```bash
# 4. Certificado emitido e válido
echo | openssl s_client -connect api.ponto.SEU-DOMINIO:443 \
  -servername api.ponto.SEU-DOMINIO 2>/dev/null | openssl x509 -noout -dates -issuer
```

```bash
# 5. Nada de produção escapou para a rede pública
sudo docker compose -p ponto-prd ... ps --format '{{.Names}} {{.Ports}}'
# Nenhuma porta pode aparecer publicada no host. Quem escuta 80/443 é o Traefik.

# 6. Console do MinIO não existe em prd (o compose desliga MINIO_BROWSER)
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9001   # deve falhar
```

```bash
# 7. Isolamento de dados entre stacks — nenhum volume compartilhado
docker volume ls --format '{{.Name}}' | grep -E 'ponto-(hml|prd)'
# Precisam ser conjuntos disjuntos: ponto-prd-* e ponto-hml-* separados.
```

Só depois disso cadastre o primeiro tenant real.

---

## Parte II — Deploy de rotina

Produção **não tem deploy automático**, e isso é decisão registrada, não
esquecimento. Homologação sobe sozinha a cada push em `main`; errar em hml custa
um redeploy. Errar em produção custa marcação de ponto de gente real, com
consequência trabalhista.

**Pelo GitHub (caminho normal, depois do passo 6):**

1. Confirme que o CI de `main` está verde.
2. Actions → **Deploy · producao** → *Run workflow*.
3. Preencha:
   - `tag`: SHA curto do commit (ex.: `a1b2c3d`);
   - `confirmacao`: exatamente `implantar em producao`;
   - `pular_migration`: deixe desmarcado (só marque se a migration já foi
     aplicada numa janela separada).
4. O job `guarda` valida a frase, a tag e que o disparo partiu de `main`.
5. `deploy-prod` constrói e publica as imagens com a tag imutável.
6. `deploy-prod-aplicar` **para na fila** esperando aprovação do environment
   `producao`. Aprove.
7. Ao final, o próprio workflow faz o teste de fumaça em `/v1/admin/saude`.

**Pela SSH (fallback, e obrigatório enquanto o billing do GitHub estiver
bloqueado):**

```bash
ssh vps
sudo TAG=a1b2c3d /docker/ponto-prd/infra/deploy-prod.sh --confirmar
```

Sem `--confirmar` (ou `CONFIRMAR_DEPLOY_PRODUCAO=sim`), o script sai com código
2 sem tocar em nada.

---

## Parte III — Rollback

### Caso A — deploy subiu, aplicação está ruim, banco **não** mudou

Volte para a tag anterior. O `deploy-prod.sh` salvou em
`/docker/ponto-prd/infra/.tag-anterior`:

```bash
ssh vps
ANTERIOR=$(sudo cat /docker/ponto-prd/infra/.tag-anterior)
echo "voltando para $ANTERIOR"
sudo TAG="$ANTERIOR" PULAR_MIGRATION=sim /docker/ponto-prd/infra/deploy-prod.sh --confirmar
```

`PULAR_MIGRATION=sim` é essencial: Alembic não desfaz sozinho, e rodar
`upgrade head` de novo não ajuda.

### Caso B — a migration mudou o schema

Rollback de código sozinho **não resolve**: o binário antigo pode não entender o
schema novo. Antes de qualquer coisa, decida com o banco em mãos.

```bash
cd /docker/ponto-prd/infra
sudo docker compose -p ponto-prd --env-file .env.prod -f docker-compose.prod.yml \
  run --rm api alembic current
sudo docker compose -p ponto-prd --env-file .env.prod -f docker-compose.prod.yml \
  run --rm api alembic history | head -20
```

Se — e somente se — a migration tiver `downgrade` testado:

```bash
sudo docker compose -p ponto-prd --env-file .env.prod -f docker-compose.prod.yml \
  run --rm api alembic downgrade -1
```

Caso contrário, restaure do backup (Caso C). **Nunca improvise `DROP`/`ALTER`
manual em produção**: marcação de ponto é registro legal e a imutabilidade da
marcação é premissa do produto (ADR-002).

### Caso C — restaurar backup do banco

Este caso deixou de ser teórico: a rotina de backup existe e está descrita em
[Parte V — Backup do banco](#parte-v--backup-do-banco). Leia a Parte V antes,
principalmente a limitação em destaque (backup **só local**).

> ⚠️ **Restaurar é DESTRUTIVO e não tem desfazer.** `pg_restore --clean` derruba
> os objetos existentes antes de recriar: todo dado gravado depois do dump
> escolhido some. Em produção isso é marcação de ponto de gente real, com
> consequência trabalhista, e a imutabilidade da marcação é premissa do produto
> (ADR-002). Confira o **ambiente** e a **data do dump** antes de digitar.

**1. Antes de qualquer coisa, congele o estado atual.** Mesmo o banco quebrado é
evidência, e pode ser a única cópia de algo que o backup escolhido não tem:

```bash
ssh vps
sudo /usr/local/sbin/backup-postgres.sh prod
```

**2. Escolha o dump** (o mais recente anterior ao estrago):

```bash
sudo ls -lt /var/backups/ponto/prod/diario /var/backups/ponto/prod/semanal
# Ver o que tem dentro sem restaurar nada:
sudo docker run --rm --network none -v /var/backups/ponto/prod/diario:/b:ro \
  postgres:16-alpine pg_restore --list /b/ponto-prod-AAAAMMDD-HHMMSS.dump | head -40
```

**3. Sempre que der, restaure primeiro para um banco NOVO e compare** — é o que
transforma "o comando não deu erro" em prova:

```bash
sudo /usr/local/sbin/restaurar-postgres.sh \
  /var/backups/ponto/prod/diario/ponto-prod-AAAAMMDD-HHMMSS.dump prod \
  --banco ponto_prd_conferencia --criar-banco --confirmar
```

O script termina imprimindo as contagens por tabela. Compare com o banco em uso
antes de decidir sobrescrever.

**4. Restauração sobre o banco de produção de verdade** — dois portões, de
propósito: `--confirmar` **e** a frase por extenso. Pare os serviços que
escrevem antes, para não restaurar por baixo de uma aplicação viva:

```bash
cd /docker/ponto-prd/infra
sudo docker compose -p ponto-prd --env-file .env.prod -f docker-compose.prod.yml \
  stop api worker scheduler device-gw

sudo CONFIRMAR_RESTAURACAO_PRODUCAO='restaurar banco de producao' \
  /usr/local/sbin/restaurar-postgres.sh \
  /var/backups/ponto/prod/diario/ponto-prod-AAAAMMDD-HHMMSS.dump prod --confirmar

sudo docker compose -p ponto-prd --env-file .env.prod -f docker-compose.prod.yml \
  start api worker scheduler device-gw
```

**5. Depois de restaurar**, confirme em qual migration o banco ficou — o dump é
do schema daquele momento, não do `head`:

```bash
sudo docker compose -p ponto-prd --env-file .env.prod -f docker-compose.prod.yml \
  run --rm api alembic current
```

Se o código implantado for mais novo que o schema restaurado, ou você aplica as
migrations que faltam (`alembic upgrade head`), ou volta o código para a tag
correspondente (Caso A). Não deixe os dois em desacordo.

### Caso D — parada de emergência

```bash
cd /docker/ponto-prd/infra
sudo docker compose -p ponto-prd --env-file .env.prod -f docker-compose.prod.yml stop
```

`stop` (não `down`): preserva volumes e a rede. **Nunca use `down -v` em
produção** — apaga os dados.

Atenção: os serviços de produção usam `restart: always`. Um container parado com
`stop` fica parado, mas um `docker restart` ou um reboot da VPS traz tudo de
volta. Para uma parada que sobreviva a reboot, pare e comunique — não confie no
`stop` sozinho.

---

## Parte IV — Operações do dia a dia

**Logs:**

```bash
cd /docker/ponto-prd/infra
sudo docker compose -p ponto-prd --env-file .env.prod -f docker-compose.prod.yml \
  logs -f --tail 200 api
```

**Administração do MinIO** (o console web não existe em prd). Túnel SSH até a
API S3 na rede interna e cliente `mc`:

```bash
# de dentro da VPS
docker run --rm -it --network ponto-prd-interna --entrypoint sh minio/mc
# > mc alias set prd http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
# > mc ls prd/ponto
```

**Renovações com data marcada** (anote em calendário — nenhuma é automática):

| Item | Prazo típico | Sintoma se vencer |
| --- | --- | --- |
| Certificado mTLS de servidor do `facial-svc` | 825 dias | reconhecimento facial para de responder |
| Certificado mTLS de cliente da `api` | 825 dias | idem (enroll falha 503, marcação segue sem o sinal facial) |
| CA interna do mTLS | 3650 dias | idem |
| Certificado ICP-Brasil A1 | 1 ano | AFD/AEJ e espelhos deixam de ser assinados |
| TLS público (Let's Encrypt) | 90 dias | **automático** pelo Traefik — só monitorar |

---

## Parte V — Backup do banco

> 🔴 **A limitação que importa: o backup fica APENAS no disco da própria VPS.**
> Isso cobre `DROP TABLE` acidental, migration ruim e corrupção lógica — que é
> a maioria dos incidentes reais. **Não cobre perda da VPS inteira**: disco,
> datacenter, conta suspensa. Se a VPS sumir, os backups somem junto. Cópia
> externa (S3/B2/rclone) está **preparada, desligada e não configurada** — não
> existe credencial provisionada; ver "Cópia externa" no fim desta seção.
> Enquanto isso não for resolvido, o plano de recuperação tem esse buraco, e
> ele é conhecido.

### O que existe

| Arquivo | Papel |
| --- | --- |
| `infra/backup-postgres.sh` | faz o dump (`pg_dump -Fc`), verifica e aplica retenção |
| `infra/restaurar-postgres.sh` | restaura um dump — **destrutivo**, dois portões de confirmação |
| `infra/instalar-backup-postgres.sh` | instala scripts + unit + timer do systemd (rode uma vez) |

Formato **custom** (`-Fc`), não `.sql.gz`: já sai comprimido e permite restore
seletivo (`pg_restore -t tabela`, `-n schema`, `--list`) — o `pg_dump | gzip`
que este runbook sugeria antes só permitia restaurar tudo ou nada.

O dump roda **dentro do container** (`docker exec`), com o `pg_dump` da mesma
versão do servidor; nada é instalado no host. A senha é lida de dentro do
container, nunca aparece na linha de comando do host.

Todo dump é **verificado** logo depois de gravado (`pg_restore --list` num
container descartável): dump truncado falha na hora, não seis meses depois.

### Instalar (uma vez, na VPS)

```bash
ssh vps
sudo /docker/ponto-prd/infra/instalar-backup-postgres.sh prod
# homologação, se quiser:
sudo /docker/ponto-eletronico/infra/instalar-backup-postgres.sh hml
```

O instalador copia os scripts para `/usr/local/sbin/` (de propósito: o deploy
faz `git reset --hard`, e o backup não pode depender do commit que estiver na
árvore na hora do disparo — **rode o instalador de novo depois de atualizar os
scripts no repo**), cria `/var/backups/ponto` (modo 700) e instala:

- `ponto-backup@.service` — unit template, `%i` é o ambiente;
- `ponto-backup@.timer` — `OnCalendar=*-*-* 06:30:00` (relógio da VPS é UTC ⇒
  03:30 em `America/Sao_Paulo`), `Persistent=true`, `RandomizedDelaySec=600`.

systemd e não cron porque o resto da automação da VPS já é systemd (o runner
self-hosted é um serviço); e porque timer dá log unificado, `Persistent=true`
(recupera a execução perdida se a VPS estava desligada) e estado consultável.

Não espere o primeiro disparo — force um agora e leia o log:

```bash
sudo systemctl start ponto-backup@prod.service
sudo journalctl -u ponto-backup@prod -n 30 --no-pager
```

### Onde os backups ficam

```
/var/backups/ponto/<ambiente>/
├── diario/    ponto-<ambiente>-AAAAMMDD-HHMMSS.dump  (+ .sha256)
├── semanal/   idem, hard link do dump de domingo
└── ULTIMO_SUCESSO   carimbo do último backup que deu certo
```

Tudo `root:root`, diretórios 700 e arquivos 600 — dump de banco é cópia
integral de dado pessoal (LGPD).

### Retenção: 14 diários + 4 semanais

GFS reduzido, e os números têm motivo:

- **14 diários** cobrem o caso realista de "só perceberam o estrago duas semanas
  depois" — erro de apuração costuma aparecer no fechamento do mês seguinte.
- **4 semanais** estendem o alcance para ~1 mês com custo de disco quase zero:
  o semanal é um **hard link** para o diário de domingo, o mesmo inode. Só
  passa a ocupar espaço próprio quando o diário correspondente é podado.
- Teto: 18 cópias no pior caso. Ajustável por `RETENCAO_DIARIOS` /
  `RETENCAO_SEMANAIS`.
- **Não há mensal/anual de propósito.** Retenção legal de marcação é problema do
  expurgo LGPD e do AFD assinado (registro fiscal), não do backup operacional.
  Backup aqui existe para **restaurar**, não para arquivar.

### Verificar se está rodando

```bash
# Próximo disparo e último disparo
systemctl list-timers --all 'ponto-backup@*'

# Última execução deu certo?
systemctl status ponto-backup@prod.service
journalctl -u ponto-backup@prod --since '2 days ago' --no-pager

# Resposta mais direta: quando foi o último sucesso, e o que tem no disco
sudo cat /var/backups/ponto/prod/ULTIMO_SUCESSO
sudo ls -lh /var/backups/ponto/prod/diario | tail -5
sudo du -sh /var/backups/ponto
```

Um backup que nunca foi restaurado não é backup. **Ensaie o Caso C num banco
descartável** (`--banco ... --criar-banco`) periodicamente e compare contagens —
é o único jeito de saber que funciona antes de precisar que funcione.

### Cópia externa (opcional, **desligada, não configurada**)

Nenhuma credencial de S3/B2/rclone existe neste projeto, e inventar uma seria
pior que não ter: daria falsa sensação de off-site. O gancho está pronto e
inerte — `PONTO_BACKUP_UPLOAD_CMD`, vazio por padrão, recebe o caminho do dump
em `$1`. Para ligar de verdade, o operador precisa (a) escolher o destino,
(b) provisionar a credencial na VPS, (c) declarar o comando num override do
systemd (nunca editando a unit):

```bash
sudo systemctl edit ponto-backup@prod
# [Service]
# Environment=PONTO_BACKUP_UPLOAD_CMD=rclone copy "$1" remoto:ponto-backups/
```

Se o upload falhar, o backup local continua íntegro, mas o serviço termina em
`failed` — o alarme não pode ser silencioso.

---

## Anexo — Diferenças hml × prd

| | homologação | produção |
| --- | --- | --- |
| Compose | `infra/docker-compose.yml` | `infra/docker-compose.prod.yml` |
| Env | `infra/.env` | `infra/.env.prod` (modo 600 obrigatório) |
| Projeto Compose | `ponto-hml` | `ponto-prd` |
| Volumes | `ponto-hml-*` (via `COMPOSE_PROJECT_NAME`) | `ponto-prd-*` **literais**, não deriváveis de variável |
| Rede interna | `ponto-hml-interna` | `ponto-prd-interna` (literal) |
| `AMBIENTE` | variável | **fixo `prd`** no arquivo |
| Restart | `unless-stopped` | `always` |
| Console MinIO | disponível na 9001 (não roteado) | **inexistente**: `MINIO_BROWSER=off`, 9001 não exposta, sem labels nem comentadas |
| `build:` | sim (constrói na VPS se preciso) | **não existe** — só consome imagem do registry |
| `TAG` | `latest` | SHA curto imutável; `latest` é recusada |
| mTLS facial | opcional (degrada para HTTP) | **obrigatório** (`:?` no compose) |
| `CONTROLID_SIMULADOR` | variável | **fixo `false`** |
| Sentry | opcional | obrigatório (`:?`) |
| Deploy | automático a cada push em `main` | **manual**, `workflow_dispatch` + frase de confirmação + aprovação de environment |
| Script | `infra/deploy-hml.sh` (só na VPS, não versionado) | `infra/deploy-prod.sh` (versionado, exige `--confirmar`) |

### Dívida conhecida

1. **`deploy-hml.sh` não é versionado.** Vive só em
   `/docker/ponto-eletronico/infra/` na VPS. Sobrevive ao `git reset --hard`
   por ser arquivo não rastreado, mas não tem histórico, revisão nem backup —
   se a VPS for perdida, o script vai junto. O `deploy-prod.sh` nasceu
   versionado de propósito. Vale trazer o de hml para o repo também.
2. **Backup do banco existe, mas só no disco da própria VPS.** O mecanismo está
   pronto e testado ponta a ponta (ver [Parte V](#parte-v--backup-do-banco));
   o que falta é a cópia **externa** — enquanto ela não existir, perder a VPS
   inteira significa perder os backups junto. Deixou de ser bloqueante para o
   primeiro cliente, continua sendo dívida real.
3. **`RETENCAO_MARCACOES_DIAS` / `RETENCAO_IMAGENS_DIAS`** aparecem nos dois
   `.env*.example` mas **nenhum** dos composes as injeta nos containers.
   Confirmar de onde o código de expurgo LGPD lê a retenção antes do primeiro
   deploy real.
4. **CI/CD bloqueado por billing do GitHub** desde 2026-08-08 — validação e
   deploy por SSH direto enquanto isso.
