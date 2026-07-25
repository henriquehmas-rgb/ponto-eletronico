# ADR-001 — Multi-tenancy com Row Level Security no PostgreSQL

**Status:** Aceito · 25/07/2026
**Decisores:** SEEG — arquitetura
**Fases afetadas:** F1 (implementa), F2 a F15 (consomem), F14 (verifica adversarialmente)

---

## Contexto

O produto nasce SaaS multiempresa (decisão D1 de `PROJETO.md`). Uma única
instância atende N clientes, e cada cliente é um `tenant` com seus
colaboradores, marcações, apurações e arquivos fiscais. Vazamento cruzado aqui
não é bug de usabilidade: é exposição de dado pessoal de terceiro sob a LGPD,
com dever de comunicação à ANPD, e é o tipo de falha que encerra um produto de
RH comercialmente.

O modo como quase todo sistema resolve isso é filtrar por `tenant_id` na camada
de aplicação — `WHERE tenant_id = :atual` em cada consulta. Isso funciona até o
dia em que alguém escreve um `JOIN` novo e esquece a cláusula, ou usa um
repositório genérico, ou executa um relatório com SQL montado dinamicamente, ou
roda um job de worker fora do contexto da requisição. É uma defesa que depende
de disciplina humana **em todos os pontos de acesso, para sempre**, incluindo os
pontos que serão escritos por dezenas de agentes trabalhando em paralelo em
fases diferentes. Esse é exatamente o modelo de falha deste projeto.

Havia também a alternativa estrutural: um banco (ou um schema) por cliente.

## Decisão

Isolamento por **Row Level Security nativo do PostgreSQL 16**, em banco único e
schema único, **somado** ao filtro de aplicação — defesa em profundidade, não
substituição.

Concretamente:

1. Toda tabela de domínio carrega `tenant_id UUID NOT NULL` e tem
   `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY`. O `FORCE` é o que
   impede o dono da tabela de escapar da política.
2. A aplicação abre cada transação com `SET LOCAL app.tenant_id = '<uuid>'`.
   `SET LOCAL` (e não `SET`) porque a conexão volta ao pool ao fim da transação
   e não pode carregar o tenant anterior.
3. As policies usam `app_tenant_atual()` (`packages/contracts/schema.sql`), que
   lê `current_setting('app.tenant_id', true)` e retorna `NULL` quando a
   variável não foi definida. **Sem tenant definido, nenhuma linha é visível** —
   o comportamento seguro é o padrão, não a exceção.
4. A aplicação conecta com uma role **sem** `BYPASSRLS`. Migrations e rotinas de
   plataforma usam outra role, com credencial separada.
5. O `tenant_id` do JWT nunca vem do corpo da requisição: é resolvido por
   subdomínio ou cabeçalho e conferido contra a sessão.

## Alternativas consideradas

**Banco por cliente.** Isolamento mais forte que existe, e descartado por
custo operacional: 200 clientes viram 200 bancos para migrar, monitorar,
backupear e restaurar. Uma migration com erro passa a ter 200 chances de falhar
parcialmente, e o estado "metade migrado" é o pior estado possível num sistema
com obrigação fiscal. Também inviabiliza consulta cross-tenant do super admin
(suporte, faturamento, telemetria) sem uma camada de federação inteira.

**Schema por cliente.** Custo operacional menor que banco por cliente, mas o
`search_path` vira a nova superfície de erro — e ele é ainda mais fácil de
esquecer que um `WHERE`. Além disso, o `pg_catalog` cresce linearmente com o
número de clientes multiplicado por 92 tabelas, degradando o planejador.

**Só filtro de aplicação.** Descartado pelo motivo do Contexto: exige acerto
100 % das vezes por N agentes ao longo de 16 fases. RLS transforma "esqueci o
filtro" de vazamento em resultado vazio.

**RLS sem filtro de aplicação.** Descartado por observabilidade e desempenho: o
predicado explícito permite ao planejador usar os índices compostos que começam
por `tenant_id`, e um `EXPLAIN` sem `tenant_id` visível é muito mais difícil de
diagnosticar.

## Consequências

**Positivas.** Vazamento cross-tenant deixa de ser uma consequência de esquecer
código e passa a exigir uma falha explícita de configuração de banco.
Rotinas de manutenção, workers e relatórios ganham a mesma proteção que os
endpoints, de graça. O super admin pode operar cross-tenant por uma role
específica e auditada, em vez de por uma flag na aplicação.

**Negativas e mitigações.** (a) O worker ARQ e o `device-gw` não têm requisição
HTTP e precisam definir `app.tenant_id` explicitamente no início de cada job —
tratado com um *context manager* obrigatório na camada de sessão. (b) `COPY` em
massa e importações grandes sofrem com o predicado por linha; a mitigação é
importar em transação única com o tenant fixado e índices compostos com
`tenant_id` à esquerda. (c) Testes precisam de um caso adversarial permanente:
a F1 entrega um teste que se conecta ao banco com a role da aplicação, sem
`app.tenant_id` e com o tenant errado, e prova que a leitura volta vazia. Esse
teste é bloqueante no CI. (d) Uma linha órfã com `tenant_id` errado fica
invisível para sempre, inclusive para o dono — daí `tenant_id` ser `NOT NULL` e
toda FK ser composta com ele.
