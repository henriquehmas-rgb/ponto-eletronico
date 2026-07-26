# RFC-004 — `fn_resolve_tenant` não resolve tenant por UUID

| | |
|---|---|
| **Status** | ✅ **Decidida** em 26/07/2026 pelo orquestrador — opção (a) implementada |
| **Autor** | F1 / A2 |
| **Data** | 2026-07-25 |
| **Fases impactadas** | F1 (implementa `TenantMiddleware`), qualquer fase cujo cliente envie `X-Tenant` como UUID |
| **Artefatos de contrato afetados** | `packages/contracts/schema.sql` (função `fn_resolve_tenant`), `apps/api/migrations/versions/0001_inicial.py` (mesma função) |
| **Bloqueia** | Resolução do cabeçalho `X-Tenant` quando o valor enviado é um UUID (em vez de slug), antes de existir sessão autenticada |

## 1. O que está errado

`packages/contracts/openapi.yaml`, parâmetro `CabecalhoTenant` (linha ~21559):

```
description: Slug ou UUID do tenant alvo. Obrigatorio quando o host nao
  identifica o tenant [...]
```

O cabeçalho `X-Tenant` aceita **slug ou UUID** por contrato. Mas
`packages/contracts/schema.sql` (seção 2, função `fn_resolve_tenant`, também
replicada em `apps/api/migrations/versions/0001_inicial.py`) só resolve por
slug:

```sql
CREATE OR REPLACE FUNCTION fn_resolve_tenant(p_slug TEXT)
RETURNS TABLE (id UUID, slug TEXT, nome_exibicao TEXT, status TEXT)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public
AS $$
  SELECT t.id, t.slug, t.nome_exibicao, t.status
    FROM tenants t
   WHERE t.slug = p_slug
     AND t.excluido_em IS NULL;
$$;
```

`WHERE t.slug = p_slug` nunca casa com um UUID, porque o formato de slug
(`^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$`) e o de UUID (`xxxxxxxx-xxxx-...`) não se
sobrepõem na prática (um UUID literal só bateria com slug se, por acaso,
contivesse apenas `[a-z0-9-]`, o que nunca é garantido).

A tabela `tenants` está sob `FORCE ROW LEVEL SECURITY`, comparando `id` com
`current_setting('app.tenant_id', true)`. No momento em que o `TenantMiddleware`
resolve o tenant, essa configuração de sessão ainda não existe — é exatamente
o problema que `fn_resolve_tenant` resolve para slug, com `SECURITY DEFINER`.
Não há hoje nenhuma porta de entrada equivalente para resolver por `id`: uma
consulta direta `SELECT ... FROM tenants WHERE id = :uuid` feita pela role
`ponto_app` (sem `BYPASSRLS`, por decisão do ADR-001) sempre devolve zero
linhas nesse momento, indistinguível de "tenant inexistente".

## 2. Por que isto importa

Um cliente de integração que já obteve o `id` do tenant (por exemplo, via
`GET /v1/tenants/atual` numa chamada anterior) e passa a enviar
`X-Tenant: <uuid>` para evitar nova resolução por slug recebe sempre
`PONTO-TEN-001` (tenant não encontrado), mesmo com tenant válido e ativo. Hoje
isso não quebra nada em produção porque não há produção ainda; quebra o caso de
uso documentado no próprio `openapi.yaml` assim que o primeiro cliente de API
tentar usar UUID no cabeçalho.

## 3. Por que não corrigi sozinho

`packages/contracts/schema.sql` e `apps/api/migrations/versions/0001_inicial.py`
estão fora do meu ownership (o segundo é explicitamente listado como "não
toca" no meu PCF, e o primeiro é o contrato congelado). Qualquer correção exige
alterar a função `fn_resolve_tenant` ou criar uma nova função `SECURITY
DEFINER` equivalente — mudança de contrato, não de aplicação.

## 4. Opções

**(a)** Estender `fn_resolve_tenant(p_slug TEXT)` para, quando `p_slug` casar
com o formato de UUID (`p_slug ~ '^[0-9a-fA-F-]{36}$'` ou
`p_slug::uuid` bem-sucedido), comparar por `t.id = p_slug::uuid` em vez de
`t.slug = p_slug`. Mantém a assinatura (`TEXT` → mesmas 4 colunas), mantém o
comportamento para slug idêntico, e não expõe nada que a rota já não expusesse
por slug (mesmas 4 colunas, mesma ausência de enumeração). Custo: uma migration
nova só para alterar o corpo da função (`CREATE OR REPLACE FUNCTION`, sem
`ALTER TABLE`), o que o meu PCF proíbe eu mesmo criar.

**(b)** Criar uma função irmã `fn_resolve_tenant_por_id(p_id UUID)`, mesmo
formato de retorno, mesma marca `SECURITY DEFINER`. Mais explícito que (a),
mas duplica a função e exige que o `TenantMiddleware` decida qual chamar (o que
ele já precisa fazer para decidir o formato do cabeçalho).

**(c)** Não mudar o contrato: documentar que `X-Tenant` só aceita slug na
prática, apesar do que diz `openapi.yaml`, e depender exclusivamente da
comparação feita depois da autenticação (`PONTO-TEN-002`, tenant do token vs.
tenant do cabeçalho) para o caso de UUID. Mais barato, mas contradiz o texto do
próprio contrato e deixa o cabeçalho documentado como aceitando um valor que na
prática sempre falha antes da autenticação.

## 5. Recomendação

Opção **(a)**: menor superfície nova, mesma assinatura, mesmo formato de
retorno, e resolve o caso descrito na descrição do parâmetro sem duplicar
função.

## 6. O que NÃO é divergência

A resolução por **slug** (cabeçalho ou subdomínio) funciona corretamente com a
função como está hoje — verificado manualmente contra o Postgres de teste
(`fn_resolve_tenant('tenant-a')` devolve a linha esperada). Este RFC cobre
apenas o caso em que o valor do cabeçalho já é um UUID.

## Decisão do orquestrador — 26/07/2026

| # | Decisão | Justificativa |
|---|---|---|
| 1 | Opção **(a)**: estender `fn_resolve_tenant(p_slug TEXT)` para comparar por `t.id` quando `p_slug` casa com o formato de UUID, e por `t.slug` caso contrário | Menor superfície nova, mesma assinatura, mesmo formato de retorno (4 colunas), sem duplicar função |
| 2 | Aplicada dentro de `0001_inicial.py` (ainda a única migration da fase) e de `packages/contracts/schema.sql`, sem migration nova | A Fase 0 ainda não tinha sido usada para gerar nenhum banco real fora dos efêmeros de teste; alterar o corpo da função `CREATE OR REPLACE` in-place no artefato único é mais barato do que uma migration `0002` só para isto, e não muda nenhuma tabela/índice/policy já auditados |

## 7. Implementação (F1 / A2)

`packages/contracts/schema.sql` (função `fn_resolve_tenant`) e
`apps/api/migrations/versions/0001_inicial.py` (mesmo corpo, `CREATE OR REPLACE
FUNCTION`) comparam por `t.id = p_slug::uuid` quando `p_slug` casa com
`^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$`,
e por `t.slug = p_slug` caso contrário. `apps/api/app/identidade/tenancy/resolucao.py`
não precisou de nenhuma mudança de lógica: já delega inteiramente à função SQL.
Verificado contra o PostgreSQL de teste (ver relatório da fase para a saída
real colada): `fn_resolve_tenant('tenant-a')` e `fn_resolve_tenant(<uuid de
tenant-a>)` devolvem a mesma linha.
