# Migrations — Ponto Eletrônico

Ambiente Alembic da API. O `target_metadata` é a `Base.metadata` do pacote
**`ponto-contracts`** (`packages/contracts/models`), que espelha
`packages/contracts/schema.sql` — a fonte da verdade do modelo de dados.

```
apps/api/
├── alembic.ini              # configuração (SEM url; resolvida em env.py)
└── migrations/
    ├── env.py               # resolve a URL e aponta para Base.metadata
    ├── script.py.mako       # template das revisões novas
    ├── seed_dev.py          # dados mínimos de desenvolvimento
    └── versions/
        └── 0001_inicial.py  # schema completo (92 tabelas + RLS + triggers)
```

---

## 1. Pré-requisito

O pacote de contratos precisa estar instalado no ambiente:

```bash
pip install -e packages/contracts
```

Sem ele, `env.py` cai no fallback por `sys.path` e importa
`packages/contracts/models` diretamente — funciona em checkout cru, mas a
instalação é o caminho suportado.

---

## 2. URL do banco

Resolvida em `env.py`, nesta ordem — a primeira que existir vence:

| Ordem | Origem | Exemplo |
|---|---|---|
| 1 | `alembic -x url=...` | `alembic -x url=postgresql+psycopg://ponto:***@localhost/ponto upgrade head` |
| 2 | `DATABASE_URL_SYNC` | `postgresql+psycopg://ponto:***@postgres:5432/ponto` |
| 3 | `DATABASE_URL` | `postgresql+asyncpg://...` → convertido para `+psycopg` automaticamente |

**Nenhum segredo entra no repositório.** `alembic.ini` tem `sqlalchemy.url`
vazio de propósito. Ver `infra/.env.example`.

---

## 3. Comandos

```bash
cd apps/api

alembic upgrade head            # aplica
alembic downgrade base          # reverte tudo
alembic current                 # revisão aplicada
alembic history                 # linha do tempo

# Gera o SQL sem tocar em banco algum (útil para revisão e para CI sem serviço)
alembic upgrade head --sql
alembic downgrade 0001_inicial:base --sql

# Nova revisão a partir da diferença entre os models e o banco
alembic revision --autogenerate -m "descricao curta"
```

---

## 4. O que o autogenerate **não** enxerga

Escrito à mão em `0001_inicial.py`, e que precisa ser mantido à mão em toda
revisão que mexer nesses objetos:

| Objeto | Onde está |
|---|---|
| Extensões (`pgcrypto`, `uuid-ossp`, `btree_gist`, `pg_trgm`) | `SQL_EXTENSOES` |
| Funções PL/pgSQL e `SECURITY DEFINER` | `SQL_FUNCOES`, `SQL_RESOLVE_TENANT` |
| Domínios de formato (`dom_cpf`, `dom_cnpj`, …) | `DOMINIOS` |
| Particionamento mensal de `marcacoes` | `SQL_PARTICIONAMENTO` |
| Gatilhos de imutabilidade (append-only) | `GATILHOS_IMUTABILIDADE` |
| Gatilhos de `atualizado_em` | `SQL_GATILHOS_TIMESTAMP` |
| Policies de Row Level Security | `SQL_RLS` |
| Roles e privilégios | `SQL_ROLES` |

As partições mensais de `marcacoes` são ignoradas pelo autogenerate através de
`include_object()` em `env.py` — elas nascem em tempo de execução via
`fn_cria_particao_marcacoes()`, chamada pelo scheduler, e sem esse filtro cada
revisão nova proporia um `drop_table` por mês.

### Checklist para toda revisão nova

- [ ] Tabela nova com `tenant_id` sai com `ENABLE` + `FORCE ROW LEVEL SECURITY`
      e a policy `pol_isolamento_tenant`.
- [ ] Tabela append-only sai com os gatilhos de `fn_registro_imutavel()` e com
      `REVOKE UPDATE, DELETE, TRUNCATE` para `ponto_app`.
- [ ] Tabela com `atualizado_em` sai com o gatilho `fn_atualiza_timestamp()`.
- [ ] `downgrade()` desfaz inclusive o DDL escrito à mão.
- [ ] Mudança de contrato? Então é **RFC** antes (ver
      `packages/contracts/README.md`, §3).

---

## 5. Seed de desenvolvimento

```bash
cd apps/api
export PONTO_SEED_ADMIN_SENHA='...'      # obrigatória, mínimo 12 caracteres
python migrations/seed_dev.py

python migrations/seed_dev.py --secar     # faz tudo e desfaz (rollback) — validação
python migrations/seed_dev.py --help      # demais opções
```

Semeia 1 tenant, 1 empresa, 1 unidade, o catálogo global de permissões, os 7
perfis de fábrica com a matriz de desenvolvimento, 1 usuário administrador, os
tipos de tratamento, os tipos de solicitação e o conjunto de feriados
nacionais. É idempotente.

**A senha do administrador vem exclusivamente de `PONTO_SEED_ADMIN_SENHA`.** Não
há valor padrão nem no código nem em arquivo versionado; sem a variável o script
recusa rodar. O script também recusa rodar quando `AMBIENTE` indica produção,
salvo `--forcar` explícito.

---

## 6. Verificação embutida

O bloco final de `0001_inicial.py` **falha a migration** se alguma invariante do
contrato estiver quebrada:

1. RLS habilitada **e forçada** em toda tabela com `tenant_id`;
2. policy `pol_isolamento_tenant` presente em todas elas;
3. `marcacoes` com os gatilhos de bloqueio de `UPDATE` e `DELETE`;
4. toda tabela de domínio com `COMMENT ON TABLE`.

É deliberado: melhor a migration falhar do que subir um banco silenciosamente
inseguro.
