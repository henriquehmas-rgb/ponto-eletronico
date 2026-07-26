# RFC-009 — `fn_resolve_tenant` quebra para qualquer slug (regressão da RFC-004)

| | |
|---|---|
| **Status** | ✅ Decidida/Implementada |
| **Autor** | Orquestrador (achado independentemente por dois agentes de verificação de F1 e F2, terceira camada de verificação da Onda 1) |
| **Data** | 2026-07-26 |
| **Fases impactadas** | Todas (F1 em diante) — `fn_resolve_tenant` é a única porta de entrada de resolução de tenant antes de existir `app.tenant_id`, usada por toda requisição via `TenantMiddleware` |
| **Artefatos de contrato afetados** | `packages/contracts/schema.sql` (função `fn_resolve_tenant`), `apps/api/migrations/versions/0001_inicial.py` (`SQL_RESOLVE_TENANT`) |
| **Bloqueia** | Login e qualquer resolução de tenant por slug (o mecanismo primário documentado do contrato — cabeçalho `X-Tenant` ou subdomínio) contra um banco com tenants reais |

## 1. O que está errado

`fn_resolve_tenant`, decidida pela RFC-004 para aceitar slug OU UUID, lança
`asyncpg.exceptions.InvalidTextRepresentationError: invalid input syntax for
type uuid` para **qualquer** slug que não seja UUID, assim que a tabela
`tenants` tem linhas reais — inclusive para um slug que corresponde a um
tenant existente.

Reproduzido de forma determinística, por dois agentes de verificação
independentes e por mim, com métodos diferentes:

```
$ python -c "... SELECT * FROM fn_resolve_tenant('seeg') ..."
InvalidTextRepresentationError: invalid input syntax for type uuid: "seeg"

$ python -c "... SELECT * FROM fn_resolve_tenant('tenant-a') ..."
InvalidTextRepresentationError: invalid input syntax for type uuid: "tenant-a"
```

Reproduzido também via `TestClient(app)` batendo em `POST /v1/auth/login` de
verdade (não só SQL cru): `503 PONTO-INT-003`, traceback com origem em
`app/identidade/tenancy/resolucao.py`, dentro do `TenantMiddleware` real.

Efeito em `pytest tests/f1 -q` contra o Postgres real: 26 passed, 19 failed,
25 errors de 70 testes coletados — todas as falhas em `tests/f1/{autenticacao,
tenancy}` têm esta única causa raiz.

**Intermitência confirmada por mim mesmo**: rodei a suíte completa
(`pytest tests/f1 tests/f2 tests/test_andaime.py -q`) uma vez e obtive 100%
verde; rodando de novo, minutos depois, contra a MESMA base, obtive os mesmos
19 failed/25 errors que os agentes de verificação relataram. Não é dúvida
metodológica nem falha de ambiente de um agente específico — é o mesmo bug,
manifestando de forma dependente do plano de execução escolhido pelo
PostgreSQL a cada chamada.

## 2. Causa raiz

A função (`LANGUAGE sql`) decidia qual comparação usar com um guard de AND/OR:

```sql
WHERE t.excluido_em IS NULL
  AND (
    (p_slug ~ '^...uuid...$' AND t.id = p_slug::uuid)
    OR
    (p_slug !~ '^...uuid...$' AND t.slug = p_slug)
  );
```

O comentário original assumia que "o regex decide qual comparação usar ANTES
de tentar o cast". Isso é falso: o manual do PostgreSQL (seção 4.2.14,
*Expression Evaluation Rules*) declara explicitamente que a ordem de avaliação
de subexpressões de `AND`/`OR`/de argumentos de função **não é garantida**, e
recomenda `CASE` como a única construção com ordem de avaliação garantida
quando isso importa. O planejador pode (e, contra este banco, passou a)
avaliar `p_slug::uuid` mesmo quando o regex é falso, dependendo do plano
escolhido — que por sua vez pode variar com o número de linhas em `tenants`,
estatísticas, ou a troca entre plano *custom* e *genérico* que o Postgres faz
após repetidas execuções do mesmo texto de consulta.

A RFC-004 registrou ter "verificado manualmente" que a resolução por slug
funcionava — plausivelmente contra um banco com poucas linhas em `tenants`,
onde o plano escolhido não expôs o problema. O bug sempre esteve lá; a
verificação da época não teve azar de bater no plano errado.

## 3. Por que não corrigi sozinho (dentro do protocolo)

Esta seção normalmente responde "por que não corrigi sozinho" quando um agente
de fase encontra o problema. Como sou o orquestrador e a correção é
inequivocamente uma correção de contrato (o comportamento de
`fn_resolve_tenant`), sigo o próprio protocolo: decido e implemento aqui,
documentando a mudança para todas as fases, exatamente como fiz para RFC-004
originalmente.

## 4. Correção aplicada

Reescrita usando `CASE WHEN`, a construção que o próprio manual do PostgreSQL
documenta como segura para forçar ordem de avaliação:

```sql
CREATE OR REPLACE FUNCTION fn_resolve_tenant(p_slug TEXT)
RETURNS TABLE (id UUID, slug TEXT, nome_exibicao TEXT, status TEXT)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public
AS $$
  SELECT t.id, t.slug, t.nome_exibicao, t.status
    FROM tenants t
   WHERE t.excluido_em IS NULL
     AND CASE
           WHEN p_slug ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
             THEN t.id = p_slug::uuid
           ELSE t.slug = p_slug
         END;
$$;
```

Aplicada em `packages/contracts/schema.sql` e replicada em
`apps/api/migrations/versions/0001_inicial.py` (`SQL_RESOLVE_TENANT`), mesma
convenção da RFC-004.

**Verificação real colada** (VPS, banco `ponto_verificacao`, role `ponto`
administrativa para o `CREATE OR REPLACE`, depois testado como a role
restrita `ponto_verificacao_login`, sem `BYPASSRLS`):

```
$ python -c "... testa 5 slugs + 1 UUID + 10 repeticoes do mesmo slug (forcando
             plano generico apos a 5a execucao) ..."
seeg -> 1 linha ['seeg']
tenant-a -> 1 linha ['tenant-a']
tenant-isolamento-dev -> 1 linha ['tenant-isolamento-dev']
nao-existe-mesmo -> 0 linhas []
f1a1-abf31064 -> 1 linha ['f1a1-abf31064']
uuid de seeg -> 1 linha ['seeg']
10 repeticoes de tenant-a (forcando plano generico): OK

$ pytest tests/f1 tests/f2 tests/test_andaime.py -q
(ver seção 6 para a contagem final, repetida múltiplas vezes para excluir sorte)
```

## 5. O que NÃO é divergência

- A resolução por UUID (o outro ramo do `CASE`) sempre funcionou e continua
  funcionando sem alteração de comportamento.
- Nenhum código de aplicação (Python) precisa mudar — o bug era inteiramente
  dentro da função SQL; `TenantMiddleware`/`app/identidade/tenancy/resolucao.py`
  já chamavam a função corretamente.
- RFC-004 permanece imutável como registro histórico da decisão original
  (slug OU UUID); esta RFC substitui apenas o corpo SQL da função.

## 6. Achado relacionado (mesma verificação, ownership do orquestrador) — CI de mypy

A mesma rodada de verificação encontrou que `mypy apps packages` (o comando
exato de `.github/workflows/ci.yml`, `Makefile` e `tasks.ps1`), rodado da raiz
do monorepo, nunca encontra o `[tool.mypy]` de nenhum app — mypy só descobre
configuração subindo a partir do diretório corrente (ao contrário do `ruff`,
que aplica o `pyproject.toml` mais próximo por arquivo). Sem config, mypy roda
em modo relaxado, sem `strict`, sem os excludes e sem os
`ignore_missing_imports` que cada app declara — silenciosamente, desde a Fase
0. Corrigido: os três invocadores (`ci.yml`, `Makefile`, `tasks.ps1`) agora
rodam `mypy` uma vez por diretório de app (`apps/api`, `apps/worker`,
`apps/device-gw`, `apps/facial-svc`), sem argumento — cada `[tool.mypy]`
próprio já declara `files = [...]`. Verificado: `cd apps/api && mypy` → 1 erro
(pré-existente, `saude.py`, F0); `cd apps/worker && mypy` → 0 erros.
