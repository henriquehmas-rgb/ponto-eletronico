# RFC-002 — Quatro `x-permissao` do OpenAPI usam ações que o `CHECK` de `permissoes.acao` recusa

| | |
|---|---|
| **Status** | ✅ **Decidida** em 25/07/2026 pelo orquestrador — opção (a) implementada |
| **Autor** | F0 / W3 (agente de processo, ao escrever os PCFs da Onda 1) |
| **Data** | 2026-07-25 |
| **Fases impactadas** | **F1** (bloqueia 1 operação), F4, F5, F10 |
| **Artefatos de contrato afetados** | `packages/contracts/openapi.yaml` **ou** `packages/contracts/schema.sql` (um dos dois) |
| **Bloqueia** | `PUT /v1/tenants/{tenantId}/configuracoes/{chave}` na F1, se resolvido ao pé da letra. As outras três caem em F4, F5 e F10 |

## 1. O que está errado

`packages/contracts/schema.sql:645-660` define a tabela `permissoes` com a ação
restrita por `CHECK`:

```sql
acao TEXT NOT NULL
     CHECK (acao IN ('ler','criar','editar','excluir','aprovar','exportar',
                     'executar','assinar','administrar')),
```

e documenta `codigo` como *"Identificador estavel usado no codigo e no OpenAPI,
por exemplo marcacoes.ler"* — ou seja, a convenção declarada é
`codigo = recurso + '.' + acao`.

O `openapi.yaml`, porém, declara **142 valores distintos de `x-permissao`**, e
**4 deles usam ações que o `CHECK` não aceita**:

```
banco_horas.configurar     POST   /v1/banco-horas/politicas                     criarPoliticaBancoHoras
fechamentos.reabrir        POST   /v1/fechamentos/{fechamentoId}/reabrir        reabrirFechamento
marcacoes.ler_sensivel     GET    /v1/marcacoes/{marcacaoId}/meta               obterMetaMarcacao
tenants.configurar         PUT    /v1/tenants/{tenantId}/configuracoes/{chave}  definirConfiguracaoTenant
```

`configurar`, `reabrir` e `ler_sensivel` não estão no conjunto aceito. Comando
que reproduz (a partir da raiz do repositório):

```
$ python - <<'PY'
import yaml
d = yaml.safe_load(open('packages/contracts/openapi.yaml', encoding='utf-8'))
ACOES_OK = {'ler','criar','editar','excluir','aprovar','exportar','executar','assinar','administrar'}
for p, it in d['paths'].items():
    for m, op in it.items():
        if isinstance(op, dict) and op.get('x-permissao'):
            c = op['x-permissao']
            if c.rpartition('.')[2] not in ACOES_OK:
                print(c, m.upper(), p, op.get('operationId'))
PY
banco_horas.configurar POST /v1/banco-horas/politicas criarPoliticaBancoHoras
fechamentos.reabrir POST /v1/fechamentos/{fechamentoId}/reabrir reabrirFechamento
marcacoes.ler_sensivel GET /v1/marcacoes/{marcacaoId}/meta obterMetaMarcacao
tenants.configurar PUT /v1/tenants/{tenantId}/configuracoes/{chave} definirConfiguracaoTenant
```

Registro complementar, do mesmo levantamento: das 142 permissões exigidas pelo
contrato, **30 não são semeadas** por `apps/api/migrations/seed_dev.py` (que
gera 200 códigos a partir de 55 recursos). Isso **não** é divergência de
contrato — o próprio arquivo diz que a matriz definitiva é da F1/A3 — e está
registrado em `docs/backlog.md`, não aqui. As 4 acima estão aqui porque são
impossíveis de semear **como estão**.

## 2. Por que isto importa

A linha da permissão simplesmente **não entra na tabela**: o `INSERT` viola o
`CHECK` e a transação aborta. Sem a linha em `permissoes`, não há
`perfil_permissoes`, e a operação correspondente fica sem forma de ser
autorizada pelo RBAC.

`tenants.configurar` cai dentro da **F1**, que começa agora. As outras três caem
em F4 (`banco_horas.configurar`), F5 (`marcacoes.ler_sensivel`) e F10
(`fechamentos.reabrir`) — mas a decisão precisa ser a mesma para as quatro, ou o
vocabulário de permissão se parte.

**Nada quebra hoje**, porque nenhuma operação está implementada e o seed atual
não tenta inserir esses quatro códigos. O custo de decidir agora é baixo; o de
decidir na F10 é reescrever perfis já em uso.

## 3. Por que não corrigi sozinho

As duas pontas estão em `packages/contracts/`, congelado. E a escolha entre as
opções muda o vocabulário de autorização de todo o produto, o que é decisão de
arquitetura, não conserto. Além disso, `x-permissao` aparece em `openapi.yaml`,
que é o artefato com maior número de dependentes.

## 4. Opções

**(a) Ampliar o `CHECK` de `permissoes.acao`** para incluir `configurar`,
`reabrir` e `ler_sensivel`.
*Muda:* uma linha de `schema.sql` e a linha equivalente de
`apps/api/migrations/versions/0001_inicial.py`.
*Custa:* mexer no `schema.sql` congelado e regerar/ajustar a migration.
*Passa a ser verdade:* a convenção `codigo = recurso.acao` vale para as 142
permissões, sem exceção. O conjunto de ações vira 12 e continua fechado.

**(b) Trocar os 4 `x-permissao` do `openapi.yaml`** por ações já aceitas —
por exemplo `tenants.editar`, `banco_horas.editar`, `fechamentos.executar`,
`marcacoes.ler`.
*Muda:* quatro linhas do `openapi.yaml`.
*Custa:* perde-se granularidade justamente onde ela importa mais — reabrir um
período fechado e ler o *meta* antifraude de uma marcação passam a exigir a
mesma permissão de operações rotineiras, e as duas são exatamente as que uma
auditoria vai querer ver separadas.

**(c) Manter `codigo` livre e desacoplá-lo de `recurso`/`acao`** — inserir
`codigo='tenants.configurar', recurso='tenants', acao='administrar'`.
*Muda:* nenhum arquivo de contrato; muda o `COMMENT ON COLUMN permissoes.codigo`
deixar de ser verdade.
*Custa:* a convenção documentada passa a ter exceção silenciosa, e
`uq_permissoes_recurso_acao` obriga a escolher ações diferentes para códigos que
compartilham recurso — `tenants.editar` e `tenants.configurar` não poderiam
ambos mapear para `acao='administrar'`. É a opção que parece barata e cobra
depois.

## 5. Recomendação

**(a).** É a única que preserva a granularidade de autorização e a convenção
`codigo = recurso.acao` ao mesmo tempo, e é a menor mudança em superfície
exposta: `permissoes.acao` é lida pela aplicação e por nenhuma integração
externa, enquanto `x-permissao` está no contrato público. As três ações novas
são justamente as sensíveis — configurar tenant, reabrir período fechado e ler
o *meta* antifraude de uma marcação — e merecem nome próprio.

## 6. Decisão do orquestrador — 25/07/2026

**Opção (a)**, como recomendado. `permissoes.acao` ganhou `'configurar'`,
`'reabrir'` e `'ler_sensivel'`, sincronizado nos três lugares que precisavam
concordar: `packages/contracts/schema.sql` (CHECK), `packages/contracts/models/identidade.py`
(CheckConstraint do SQLAlchemy) e `apps/api/migrations/versions/0001_inicial.py`
(migration). Reverificado após a mudança: `ruff check`/`format --check` verdes
em `apps packages tests`, e o pacote `ponto_contracts` continua importando com
92 tabelas.

`PUT /v1/tenants/{tenantId}/configuracoes/{chave}` (`tenants.configurar`) está
desbloqueado para a F1. As outras três ações ficam disponíveis para F4, F5 e F10
quando chegar a vez delas.

## 7. O que **não** é divergência

* Os outros **138** valores de `x-permissao` respeitam o `CHECK` e a convenção.
* As 30 permissões não semeadas por `seed_dev.py` são lacuna de semeadura, não
  de contrato: o próprio arquivo declara que a matriz definitiva é entrega da
  F1/A3. Estão em `docs/backlog.md`.
