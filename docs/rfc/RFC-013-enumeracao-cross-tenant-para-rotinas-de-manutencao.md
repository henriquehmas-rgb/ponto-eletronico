# RFC-013 — Rotina de cron cross-tenant não tem mecanismo sancionado para enumerar tenants/terminais antes de aplicar RLS por linha

| | |
|---|---|
| **Status** | ✅ Decidida/Implementada |
| **Autor** | F6 / A1 |
| **Data** | 2026-07-26 |
| **Fases impactadas** | F6 (`verificar_terminal_offline`), F4 (`verificar_banco_horas_vencendo` — mesmo problema estrutural, ainda stub) |
| **Artefatos de contrato afetados** | Nenhuma mudança proposta em `openapi.yaml`/`errors.yaml`/`events.yaml`. Possível adição de uma função `SECURITY DEFINER` em `schema.sql`, dependendo da opção escolhida |
| **Bloqueia** | Só a tarefa T9 (`verificar_terminal_offline`) desta fase — implementada com a opção (a) como interino, ver §5 |

## 1. O que está errado

`worker/scheduler.py::verificar_terminal_offline` (T9 do PCF da F6) precisa
comparar `terminais.ultimo_contato_em` de **todos os terminais ativos, de
todos os tenants**, a cada varredura (a cada 5 minutos, `montar_cron()`). Não
há parâmetro `tenant_id` — é um cron global, não uma tarefa enfileirada por
requisição.

Toda tabela de domínio (`terminais` inclusive) está sob
`ENABLE/FORCE ROW LEVEL SECURITY` com a policy
`tenant_id = current_setting('app.tenant_id')` (`packages/contracts/schema.sql`,
seção 19). A única role de aplicação (`ponto_app`) **não** tem `BYPASSRLS`
(ADR-001, decisão 4: "A aplicação conecta com uma role sem BYPASSRLS"). Logo,
com `ponto_app` e sem `app.tenant_id` definido, `SELECT * FROM terminais`
devolve **zero linhas**, sempre — não há como descobrir "quais tenants têm
terminal ativo" nem "listar todos os terminais para comparar contato" a partir
desta role sozinha.

O mesmo vale para `verificar_banco_horas_vencendo` (F4), que precisa
"percorrer as contas abertas por tenant" (docstring do próprio stub) sem
receber uma lista de tenants de lugar nenhum.

## 2. Por que isto importa

Sem uma forma sancionada de enumerar, a única saída dentro do meu ownership
seria conectar com uma role `BYPASSRLS` (`ponto_suporte`, já existe no
catálogo de roles, `schema.sql` seção 20) diretamente do `worker`/`scheduler`.
Isso **não está proibido explicitamente em lugar nenhum**, mas também não foi
decidido para este caso: `ponto_suporte` é descrita em ADR-001 como o canal do
"super admin" (suporte humano da SEEG), não como credencial de processo
automatizado rodando a cada 5 minutos. Usar sem decisão explícita seria
precisamente o tipo de "contorno silencioso" que o protocolo de RFC existe
para evitar (o critério de aceite 10 do meu próprio PCF proíbe **BYPASSRLS
fora do padrão aprovado** para o caso especificamente citado ali — resolução
de terminal antes do tenant, T2 — mas o espírito da proibição é mais amplo, e
prefiro que o orquestrador decida explicitamente em vez de eu escolher
sozinho que este é "outro caso, então não conta").

Sem decisão, T9 fica sem uma forma correta e auditável de saber quais
terminais verificar.

## 3. Por que não corrigi sozinho

A escolha envolve **ou** ampliar o uso da role `ponto_suporte` para um
consumidor novo (processo automatizado, não humano) **ou** acrescentar uma
função nova a `packages/contracts/schema.sql` — ambas fora do meu ownership
sem decisão (a primeira por precedente arquitetural do ADR-001; a segunda por
ser mudança de contrato explícita, proibição 1 do meu PCF).

## 4. Opções

**(a) Reaproveitar `ponto_suporte` (BYPASSRLS, já existe) como credencial do
`scheduler` para a consulta de enumeração, mantendo `ponto_app` +
`app.tenant_id` para toda escrita (`terminal_saude`) e toda leitura que já
sabe o tenant.** O que muda: o worker/scheduler ganha uma SEGUNDA `DATABASE_URL`
(role diferente, credencial diferente, nunca a mesma variável que a API usa),
só para a consulta `SELECT terminais.*, tenant_id ... WHERE status='ativo'`
que abre a varredura; toda linha lida já sai com o próprio `tenant_id`, que
então é usado para abrir uma sessão `ponto_app` normal (com
`SET LOCAL app.tenant_id`) para escrever `terminal_saude`. Custo: dois
segredos de banco no `scheduler` em vez de um; a role de leitura ampla
(`ponto_suporte` já tem `SELECT` em todas as tabelas, inclusive fora do
escopo desta rotina) fica em uso constante, não só sob demanda de suporte.
O que passa a ser verdade: nenhuma migration nova; a leitura cross-tenant é
auditável (é a MESMA role que o ADR-001 já cita para esse propósito) e nunca
grava nada.

**(b) Criar `fn_terminais_para_verificacao_saude() RETURNS TABLE (id, tenant_id,
numero_serie, empresa_id, unidade_id, modo_comunicacao, intervalo_push_segundos,
ultimo_contato_em) SECURITY DEFINER`**, no mesmo padrão de `fn_resolve_tenant`/
`fn_resolve_terminal` (RFC-004/010). O que muda: uma função nova em
`schema.sql`, chamada pela role `ponto_app` comum (sem segredo adicional no
scheduler). Custo: migration nova (o PCF da F6 diz explicitamente "nenhuma
migration nova nesta fase... se você achar que precisa de mais alguma coisa
no schema além do que uma RFC aprovar, o contrato está errado: abra RFC" —
esta é exatamente essa RFC). O que passa a ser verdade: superfície de acesso
mínima (só as colunas que a rotina precisa, nunca a tabela inteira, ao
contrário da opção a), sem introduzir um segundo segredo de banco no
`scheduler`; padrão idêntico ao já aprovado duas vezes (RFC-004, RFC-010).

## 5. Recomendação

**(b)**, por consistência com o padrão já duas vezes aprovado
(`fn_resolve_tenant`/`fn_resolve_terminal`) e por expor superfície mínima em
vez de `SELECT` irrestrito. Enquanto a decisão não sai, implementei T9 com a
opção **(a)** como interino (a rotina funciona hoje, testada contra o banco
real da VPS, mas com uma segunda variável de ambiente,
`WORKER_DATABASE_URL_SUPORTE`, cujo valor de produção real ainda não está em
`infra/.env.example` — fora do meu ownership, ver `docs/backlog.md`): trocar
para a opção (b) depois, se aprovada, é uma mudança confinada a
`worker/scheduler.py` (função `_listar_terminais_ativos_cross_tenant`), sem
tocar no restante da rotina.

## Decisão do orquestrador — 26/07/2026

| # | Decisão | Justificativa |
|---|---|---|
| 1 | Opção **(b)**: `fn_terminais_para_verificacao_saude() RETURNS TABLE (id, tenant_id, numero_serie, empresa_id, unidade_id, modo_comunicacao, intervalo_push_segundos, ultimo_contato_em) SECURITY DEFINER`, criada em `packages/contracts/schema.sql` e replicada em `apps/api/migrations/versions/0001_inicial.py`, mesmo padrão de `fn_resolve_tenant`/`fn_resolve_terminal`. | Consistência com o padrão já duas vezes aprovado; superfície de acesso mínima; evita um segundo segredo de banco (`ponto_suporte`) em uso constante no scheduler. |

**Pendência de implementação** (não deste orquestrador): `verificar_terminal_offline` (F6/A1) hoje usa a opção (a) interina. Trocar para `fn_terminais_para_verificacao_saude()` pela role `ponto_app` comum é tarefa de quem fechar F6 — mudança confinada à função `_listar_terminais_ativos_cross_tenant`. Quando a F4 chegar a `verificar_banco_horas_vencendo`, deve seguir o mesmo padrão (nova função `SECURITY DEFINER` equivalente, não reaproveitar `ponto_suporte`).
