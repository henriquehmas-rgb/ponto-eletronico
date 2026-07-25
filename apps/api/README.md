# apps/api — API REST (FastAPI)

Aplicação FastAPI do **Ponto Eletrônico** (REP-P multiempresa). Esta é a entrega
da **Fase 0: contrato e andaime** — a aplicação sobe, responde de verdade aos
sinais de vida e expõe **todas** as operações de
[`packages/contracts/openapi.yaml`](../../packages/contracts/openapi.yaml) com a
assinatura correta. **Nenhuma regra de negócio existe aqui ainda.**

---

## Estado da implementação

| Item | Número |
|---|---|
| Operações declaradas no contrato | **215** (em 140 caminhos) |
| Operações expostas pela aplicação | **215** — inventário idêntico, verificado por script |
| Operações que respondem `501 PONTO-INT-005` | **214** |
| Operações implementadas de verdade | **1** — `GET /v1/admin/saude` |
| Modelos Pydantic gerados do contrato | 245 |
| Códigos do catálogo de erros espelhados | 112 |

O `detail` do 501 informa **qual fase** implementa a operação, para o integrador
saber o que esperar:

```json
{
  "type": "https://docs.ponto.seeg.com.br/erros/PONTO-INT-005",
  "title": "Operacao ainda nao implementada",
  "status": 501,
  "codigo": "PONTO-INT-005",
  "detail": "A operacao 'listarColaboradores' existe no contrato e sera implementada na fase F2. ...",
  "instance": "/v1/colaboradores",
  "requestId": "req_..."
}
```

### A única exceção

`GET /v1/admin/saude` (`obterSaude`) é implementado. É infraestrutura, não regra
de negócio, e um endpoint de saúde respondendo 501 seria pior que inútil — o
painel de operação da F15 precisa dele desde já. A decisão está registrada em
`tools/gerar_do_contrato.py` (`OPERACOES_IMPLEMENTADAS`) e é verificada por teste.

---

## Estrutura

```
apps/api/
├── app/
│   ├── main.py              montagem da aplicação, middlewares, ciclo de vida
│   ├── core/
│   │   ├── config.py            Configuracao (pydantic-settings), sem segredo em código
│   │   ├── contexto.py          requestId / tenant / usuário em ContextVar
│   │   ├── log.py               log estruturado JSON (uma linha = um evento)
│   │   ├── erros.py             RFC 9457 application/problem+json
│   │   ├── catalogo_erros.py    GERADO de errors.yaml (112 códigos)
│   │   └── middleware.py        request-id, tenant, registro de acesso
│   ├── db/sessao.py         engine async, sessão por requisição, SET app.tenant_id
│   ├── routers/             1 módulo por tag do OpenAPI (30) + saude.py (a mão)
│   ├── schemas/contrato.py  GERADO do OpenAPI (245 modelos Pydantic v2)
│   └── scripts/seed.py      ponte para migrations/seed_dev.py
├── tools/
│   ├── gerar_do_contrato.py gera catálogo, schemas e routers a partir do contrato
│   └── conferir_rotas.py    compara o inventário da app com o contrato
├── tests/test_andaime.py    13 testes do andaime
├── migrations/              (ownership do agente de migrations — não editar aqui)
├── Dockerfile               multi-stage: dependencias → dev → runtime
└── pyproject.toml           dependências + ruff + mypy + pytest
```

### O que é gerado e o que é escrito à mão

**Gerado — nunca editar à mão** (a próxima geração apaga a correção):
`app/core/catalogo_erros.py`, `app/schemas/contrato.py`, `app/routers/*.py`
(exceto `saude.py` e `__init__.py`).

Se o código gerado está errado, o defeito está no contrato ou no gerador. Contrato
errado exige **RFC** (ver `FASES-E-AGENTES.md` §1.3), nunca contorno silencioso.

```bash
pip install -e ".[codegen,dev]"
python tools/gerar_do_contrato.py
```

---

## Convenções que valem para todas as fases seguintes

| Assunto | Regra |
|---|---|
| Nomes | Python em `snake_case`, JSON em `camelCase`. Os modelos gerados já trazem `alias` — `criado_em` serializa como `criadoEm`. |
| Erro | Sempre `application/problem+json` com `codigo` do catálogo. **Nenhum código é inventado**: situação nova exige RFC em `errors.yaml`. |
| Detalhe sensível | Código com `expoe_regra: false` não manda `detail` na resposta. O parâmetro interno vai para o log e para a auditoria, nunca para a tela. |
| Duração | Sempre inteiro em **minutos**. Nunca float, nunca "horas decimais". |
| Tenant | Resolvido pelo middleware (cabeçalho `X-Tenant` ou subdomínio) e publicado em `app.core.contexto`. `app/db/sessao.py` já emite `set_config('app.tenant_id', …, true)` por transação — é o gatilho do RLS. |
| Sessão de banco | `from app.db import SessaoDb` e anote `sessao: SessaoDb`. Commit e rollback são automáticos. |

---

## Rodando

### Local, sem Docker

```bash
cd apps/api
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"     # Windows
.venv/bin/pip install -e '.[dev]'         # Linux/macOS

uvicorn app.main:app --reload
```

- API: <http://localhost:8000>
- Portal OpenAPI: <http://localhost:8000/docs>
- Liveness: <http://localhost:8000/health>
- Readiness: <http://localhost:8000/ready>

Sem PostgreSQL e sem Redis a aplicação **sobe assim mesmo**: `/health` responde
200 e `/ready` responde 503 `PONTO-INT-003` dizendo qual dependência está fora.
Isso é deliberado — subir só quando o banco existe transforma indisponibilidade
de dependência em *crash loop* e ainda tira do ar o endpoint que explicaria o
problema.

### Com a stack completa

```bash
make up          # ou  .\tasks.ps1 up
```

---

## Verificação

```bash
cd apps/api

# a aplicação carrega e expõe o inventário completo
python -c "from app.main import app; e=app.openapi(); print(len(e['paths']),'caminhos', sum(1 for p in e['paths'].values() for m in p if m in ('get','post','put','patch','delete')),'operacoes')"

# inventário idêntico ao contrato (método, caminho e operationId)
python tools/conferir_rotas.py

# qualidade
ruff check . && ruff format --check .
mypy
pytest -q
```

---

## Três endpoints de saúde, três papéis

| Endpoint | Pergunta | Toca dependência? | Quem usa |
|---|---|---|---|
| `GET /health` | O processo está vivo? | **Não** | `healthcheck` do Docker, Traefik |
| `GET /ready` | Dá para mandar tráfego? | Sim (banco, Redis) | orquestrador / balanceador |
| `GET /v1/admin/saude` | Qual o estado detalhado? | Sim | painel de operação (F15) |

`/health` não depende do banco de propósito: se dependesse, uma queda do
PostgreSQL derrubaria os containers da API em cascata — e o restart não
resolveria nada, porque o defeito não está neles.

---

## Proibições desta fase

- Não implementar regra de negócio (cálculo, NSR, AFD, banco de horas).
- Não editar `packages/contracts/` — congelado; mudança exige RFC.
- Não editar `alembic.ini` nem `migrations/` — ownership de outro agente.
- Não versionar segredo. Só `.env.example`.
