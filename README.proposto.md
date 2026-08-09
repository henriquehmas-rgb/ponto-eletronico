# Ponto Eletrônico

> **PROPOSTA — não é o README ativo.**
> Este arquivo é uma revisão sugerida do `README.md` para o momento em que o
> repositório se tornar público. Ele **não substitui** nada automaticamente.
> Os trechos marcados `<!-- DECISÃO: ... -->` dependem de escolha do dono do
> produto. Depois de revisado, o conteúdo abaixo (sem este bloco e sem os
> comentários de decisão) pode virar o `README.md` da raiz.

---

# SEEG Ponto — Ponto Eletrônico REP-P

Sistema de ponto eletrônico **REP-P** multiempresa (SaaS), em conformidade com a
Portaria MTP 671/2021. Registra jornada por cinco canais — terminal facial
Control iD, aplicativo móvel, navegador, totem/quiosque e API — e entrega o que
um software de ponto precisa entregar de fato: marcação imutável com NSR sem
lacunas, motor de jornada e cálculo, banco de horas completo, workflow de
aprovações, mais de 20 relatórios gerenciais e os arquivos fiscais AFD e AEJ
assinados digitalmente em CAdES.

A arquitetura é multi-tenant desde a primeira tabela, com isolamento por Row
Level Security no PostgreSQL além do filtro de aplicação. Marcação é
append-only: nenhum endpoint altera ou apaga um registro — correções vivem numa
camada separada de tratamento, sempre auditada, porque é isso que a Portaria
exige e é isso que torna o sistema defensável numa fiscalização. Biometria é
tratada como dado pessoal sensível (LGPD art. 5º, II): o motor facial é
self-hosted, o template fica cifrado com chave separada da base, e imagem crua
não trafega para a nuvem quando há processamento na borda.

<!-- DECISÃO: confirmar o estado real do projeto antes de publicar.
     O README atual ainda diz "Fase 0 — Contrato e Andaime", o que está
     desatualizado (F1–F6 e F8–F14 implementadas; F7/mobile pendente).
     Ajustar o bloco abaixo para o estado verdadeiro na data da publicação. -->

> **Estado atual: em desenvolvimento ativo.**
> As fases de backend, web e conformidade estão implementadas; o aplicativo
> móvel (Flutter) ainda não. O sistema **não** está homologado no INPI e ainda
> depende de certificado e-CNPJ A1 ICP-Brasil para assinar os arquivos fiscais
> em produção. Não use como REP-P oficial sem completar esses passos.

---

## Stack

| Camada | Tecnologia |
|---|---|
| API | Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · Pydantic v2 |
| Banco | PostgreSQL 16 (RLS multi-tenant, particionamento mensal de marcações) |
| Fila e cache | Redis 7 · ARQ (worker e scheduler) |
| Objetos | MinIO (S3-compatível) |
| Web | Next.js 15 (App Router) · TypeScript · Tailwind v4 · shadcn/ui · TanStack Query |
| Mobile | Flutter · Riverpod · Drift (SQLite) |
| Facial | Motor próprio self-hosted (`facial-svc`, ArcFace/ONNX) |
| Terminais | `device-gw` — protocolo Control iD (Push + Monitor) |
| Proxy | Traefik (esperado como já existente no host; este projeto não sobe outro nas portas 80/443) |
| Observabilidade | OpenTelemetry · Prometheus · Grafana · Loki · Sentry |
| CI/CD | GitHub Actions |

---

## Como subir localmente

### Pré-requisitos

- Docker Desktop (ou Docker Engine) com o daemon **rodando**
- Git
- Opcional, para rodar lint/testes fora do container: Python 3.12, Node 24, pnpm

### Passo a passo

**1. Clone e entre no diretório**

```bash
git clone https://github.com/henriquehmas-rgb/ponto-eletronico.git
cd ponto-eletronico
```

**2. Crie o arquivo de variáveis de ambiente**

```bash
# Linux/macOS
cp infra/.env.example infra/.env

# Windows PowerShell
Copy-Item infra\.env.example infra\.env
```

Abra `infra/.env` e ajuste no mínimo `DOMINIO`, `POSTGRES_PASSWORD`,
`REDIS_PASSWORD` e `MINIO_ROOT_PASSWORD`. Todas as variáveis estão comentadas no
arquivo de exemplo. **`infra/.env` nunca vai para o git.**

**3. Gere o par de chaves JWT**

```bash
make keys          # Linux/macOS
.\tasks.ps1 keys   # Windows
```

Gera `infra/keys/private.pem` e `infra/keys/public.pem` (RSA 4096, RS256). O
diretório é ignorado pelo git.

**4. Suba a stack**

```bash
make up            # Linux/macOS
.\tasks.ps1 up     # Windows
```

Isso usa `infra/docker-compose.yml` combinado com o override
`infra/docker-compose.dev.yml`: portas publicadas em `localhost`, hot reload
ligado e Traefik desabilitado (em desenvolvimento não há proxy na máquina).

**5. Aplique as migrations**

```bash
make migrate            # Linux/macOS
.\tasks.ps1 migrate     # Windows
```

**6. Confira**

| Serviço | URL local |
|---|---|
| Web (Next.js) | http://localhost:3000 |
| API (FastAPI) | http://localhost:8000 |
| Portal OpenAPI | http://localhost:8000/docs |
| device-gw | http://localhost:8001 |
| Console MinIO | http://localhost:9001 |

`make ps` (ou `.\tasks.ps1 ps`) mostra o estado de saúde de todos os
containers. Todos devem chegar a `healthy`.

**Atalho:** `make bootstrap` executa os passos 2 a 5 de uma vez.

### Comandos do dia a dia

| Objetivo | Linux/macOS | Windows |
|---|---|---|
| Subir a stack | `make up` | `.\tasks.ps1 up` |
| Derrubar | `make down` | `.\tasks.ps1 down` |
| Logs | `make logs s=api` | `.\tasks.ps1 logs -Servico api` |
| Migrations | `make migrate` | `.\tasks.ps1 migrate` |
| Nova migration | `make migration m="..."` | `.\tasks.ps1 migration -Mensagem "..."` |
| Testes | `make test` | `.\tasks.ps1 test` |
| Lint | `make lint` | `.\tasks.ps1 lint` |
| Formatar | `make fmt` | `.\tasks.ps1 fmt` |
| Validar infra e contrato | `make validate` | `.\tasks.ps1 validate` |
| Listar tudo | `make` | `.\tasks.ps1` |

---

## Estrutura do monorepo

```
ponto-eletronico/
├── packages/
│   └── contracts/       Fonte da verdade congelada: OpenAPI, schema, erros, eventos, tokens, glossário
├── apps/
│   ├── api/             API REST FastAPI — recurso público /v1 e backend do web e do app
│   ├── worker/          Workers ARQ — apuração, geração de AFD/AEJ, relatórios, webhooks
│   ├── device-gw/       Gateway dos terminais Control iD (Push e Monitor), isolado da API
│   ├── facial-svc/      Motor facial self-hosted; biometria não sai da rede interna
│   ├── web/             Portal Next.js — colaborador, gestor, RH e diretoria
│   └── mobile/          Aplicativo Flutter — batida com facial, GPS, antifraude e fila offline
├── infra/               docker-compose de produção e de dev, labels do Traefik, .env.example
├── docs/                ADRs, runbooks e os Pacotes de Contexto de Fase que cada agente lê
├── tests/               e2e, carga e fixtures legais (AFD/AEJ de referência)
├── .github/workflows/   CI (lint, tipos, testes, build, OpenAPI) e pipeline de segurança
├── Makefile             Atalhos de desenvolvimento no Linux/macOS
└── tasks.ps1            Os mesmos atalhos no Windows PowerShell
```

O `scheduler` não tem diretório próprio: é o mesmo código de `apps/worker/`
executado com outras settings do ARQ (jobs cron).

---

## Deploy

O deploy de referência é em VPS Ubuntu com Docker e um **Traefik global já
existente**. Este projeto **não** publica as portas 80/443 e **não** sobe outro
proxy — apenas anexa os serviços expostos à rede externa do Traefik e declara as
rotas por label:

| Host | Serviço |
|---|---|
| `ponto.<dominio>` | web |
| `api.ponto.<dominio>` | api |
| `dev.ponto.<dominio>` | device-gw (Push/Monitor Control iD) |
| `docs.ponto.<dominio>` | portal OpenAPI |

Postgres, Redis, MinIO e `facial-svc` vivem apenas na rede interna e não são
alcançáveis de fora. O console do MinIO não é publicado em produção: o acesso é
por túnel SSH.

Validação da configuração sem subir nada:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml config --quiet
```

---

## Segurança e segredos

- **Nenhum segredo entra no git.** Só existe `infra/.env.example`, com valores
  de exemplo óbvios. `.env`, `*.pem`, `*.p12`, `*.pfx`, `*.key`,
  `local.properties` e mídia biométrica estão bloqueados no `.gitignore`, e o
  pipeline de segurança reprova se algum deles aparecer versionado.
- O workflow `.github/workflows/security.yml` roda Semgrep (SAST), auditoria de
  dependências Python e Node, e varredura de segredos no histórico.
- Chaves JWT, certificado ICP-Brasil e credenciais de terminal são montados por
  volume, nunca embutidos em imagem.

<!-- DECISÃO: criar SECURITY.md e apontar aqui. Sugestão de texto no relatório. -->

**Encontrou uma vulnerabilidade?** Veja [SECURITY.md](SECURITY.md) — reporte de
forma privada, não abra uma issue pública.

---

## Licença

<!-- DECISÃO PENDENTE — escolher uma das opções e apagar as demais:

  (a) Sem licença open source / todos os direitos reservados:
      "Este repositório é público apenas para leitura. Nenhuma licença de uso,
       cópia, modificação ou redistribuição é concedida. © SEEG Serviços de
       Tecnologia da Informação. Todos os direitos reservados."

  (b) Permissiva (MIT ou Apache 2.0):
      "Distribuído sob a licença MIT — veja LICENSE."

  (c) Copyleft (AGPL-3.0 / GPL-3.0):
      "Distribuído sob a licença AGPL-3.0 — veja LICENSE."

  Enquanto não houver arquivo LICENSE, vale o padrão do (a) por omissão legal,
  mas o GitHub não exibe isso de forma explícita para o visitante.
-->

_A definir._

---

## Contribuições

<!-- DECISÃO PENDENTE — escolher uma das duas:

  (a) Não aceita contribuições externas:
      "Este repositório é publicado para transparência e consulta. Issues e
       pull requests de terceiros não são aceitos no momento."

  (b) Aceita contribuições:
      "Contribuições são bem-vindas — veja CONTRIBUTING.md e
       CODE_OF_CONDUCT.md antes de abrir um PR."
-->

_A definir._

---

## Documentação

- **[PROJETO.md](PROJETO.md)** — especificação de produto e arquitetura:
  decisões fundadoras, canais de registro, motor de jornada, banco de horas,
  segurança e antifraude, conformidade REP-P, catálogo de relatórios, API
  pública, riscos.
- **[FASES-E-AGENTES.md](FASES-E-AGENTES.md)** — plano de execução: as fases, o
  mecanismo que permite N agentes em paralelo sem quebrar contexto, ownership de
  arquivos, critérios de aceite e o protocolo de RFC.
- **[docs/adr/](docs/adr/)** — decisões de arquitetura registradas (ADRs).
- **[packages/contracts/README.md](packages/contracts/README.md)** — por que o
  contrato é congelado e como propor mudança.

> Boa parte de `docs/` é documentação de **processo interno de construção**
> (relatórios de fase, RFCs, backlog de débito técnico). É útil para entender
> como as decisões foram tomadas, mas não é manual de uso do produto.

---

Desenvolvido pela **SEEG Serviços de Tecnologia da Informação**.

<!-- DECISÃO: o README atual expõe o CNPJ da empresa no rodapé
     (60.258.502/0001-49). CNPJ é dado público de registro, então não é
     vazamento — mas avaliar se faz sentido mantê-lo num repositório público
     ou se basta o nome da empresa. Removido nesta proposta; reincluir se for
     desejado para fins de identificação do desenvolvedor do REP-P (a Portaria
     671/2021 exige identificação do desenvolvedor nos arquivos fiscais, o que
     é diferente de exigir no README). -->
