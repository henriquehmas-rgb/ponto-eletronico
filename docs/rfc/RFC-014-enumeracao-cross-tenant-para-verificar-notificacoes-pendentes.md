# RFC-014 — Rotina de cron cross-tenant de F10 precisa da mesma enumeração mínima já decidida pela RFC-013, para um terceiro caso

| | |
|---|---|
| **Status** | ✅ Decidida/Implementada |
| **Autor** | Orquestrador, ao revisar o PCF de F10 antes do build |
| **Data** | 2026-07-27 |
| **Fases impactadas** | F10 (`verificar_notificacoes_pendentes`, worker/scheduler.py, T11 do PCF) |
| **Artefatos de contrato afetados** | Uma função `SECURITY DEFINER` nova em `packages/contracts/schema.sql` e em `apps/api/migrations/versions/0001_inicial.py`. Nenhuma mudança em `openapi.yaml`/`errors.yaml`/`events.yaml` |
| **Bloqueia** | Só a tarefa T11 (`verificar_notificacoes_pendentes`) do PCF de F10 |

## 1. O que está errado

`verificar_notificacoes_pendentes` (F10/A3, cron a cada 10 min) precisa
enumerar **quais tenants existem** antes de abrir uma sessão `ponto_app` por
tenant (com `SET LOCAL app.tenant_id`) e consultar `ocorrencias`/
`solicitacoes`/`aprovacoes` sob RLS normal. É exatamente o mesmo problema
estrutural que a RFC-013 já decidiu duas vezes (`verificar_terminal_offline`,
F6; `verificar_banco_horas_vencendo`, F4): `ponto_app` não tem `BYPASSRLS`
(ADR-001), e sem `app.tenant_id` publicado nenhuma tabela de domínio devolve
linha nenhuma — inclusive `tenants`, que também está sob RLS.

A diferença desta vez: RFC-013 decidiu a **forma** (função `SECURITY
DEFINER` mínima, opção b) mas sua "Decisão do orquestrador" nomeou
explicitamente só os dois casos já conhecidos na época (F6 e F4) — não é uma
pré-aprovação genérica para qualquer rotina futura. F10 é um terceiro
consumidor real do mesmo padrão, então, para manter o protocolo (mudança de
`packages/contracts/` sempre passa por decisão registrada do orquestrador),
esta RFC existe para estender formalmente o precedente, não para reabri-lo.

## 2. Por que isto importa

Sem uma forma sancionada de enumerar tenants, `verificar_notificacoes_
pendentes` não tem como saber por quais tenants iterar — a rotina simplesmente
não roda, ou alguém reintroduz um segredo de banco `BYPASSRLS` sem decisão
(o mesmo contorno que a RFC-013 já rejeitou nas suas próprias palavras: "seria
precisamente o tipo de contorno silencioso que o protocolo de RFC existe para
evitar").

## 3. Por que não decidi implicitamente (via só o PCF)

O PCF de F10 (`docs/fases/F10-workflows-aprovacoes-fechamento.md`, §2.10 e
§5) já identifica o problema, já propõe a função `fn_tenants_ativos()` exata
e já marca com honestidade que **isto não é uma RFC pré-aprovada como a de
F4/RFC-013, mas segue o mesmo padrão de forma** — ou seja, o próprio agente
que escreveu o PCF reconheceu corretamente que não tinha autoridade para
decidir uma mudança de contrato sozinho, mesmo sendo uma extensão óbvia do
precedente. Esta RFC é o registro formal que falta para o protocolo continuar
íntegro: mudança em `packages/contracts/` sempre com decisão explícita do
orquestrador, nunca por "é claramente o mesmo padrão, não precisa perguntar".

## 4. Opções

As mesmas duas da RFC-013 (não repito a análise completa, só o resultado
aplicado a este terceiro caso):

**(a) Reaproveitar `ponto_suporte`/segunda credencial.** Mesmo custo já
rejeitado pela RFC-013 (segundo segredo de banco em uso constante, superfície
de leitura irrestrita). Descartada pela mesma razão.

**(b) Criar `fn_tenants_ativos() RETURNS TABLE (id, slug) SECURITY DEFINER`**,
no mesmo padrão de `fn_resolve_tenant`/`fn_terminais_para_verificacao_saude`/
`fn_bh_contas_para_verificacao_vencimento` (as três já existem em
`schema.sql`, seções 2, 7 e 10). Diferença desta função em relação às três
irmãs: em vez de expor colunas de UM domínio específico, expõe só a
identidade do tenant (`id`, `slug`) — o cron abre `SET LOCAL app.tenant_id`
por tenant e faz consultas comuns, sob RLS, no domínio que precisar
(`ocorrencias`/`solicitacoes`/`aprovacoes`), sem precisar de uma função
`SECURITY DEFINER` por domínio consultado. Superfície de acesso ainda mais
mínima que as três anteriores.

## 5. Decisão do orquestrador — 27/07/2026

| # | Decisão | Justificativa |
|---|---|---|
| 1 | Opção **(b)**: `fn_tenants_ativos() RETURNS TABLE (id UUID, slug TEXT) LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$ SELECT t.id, t.slug FROM tenants t WHERE t.status = 'ativo'; $$`, criada em `packages/contracts/schema.sql` (seção 2, junto das demais funções `SECURITY DEFINER`) e replicada em `apps/api/migrations/versions/0001_inicial.py`. Texto exato já fixado no PCF de F10, §5 — o agente A3 confirma o nome real da coluna de status em `tenants` antes de implementar (o PCF já avisa disso). | Terceira aplicação consistente do padrão já duas vezes aprovado pela RFC-013; superfície de acesso ainda menor que as três funções irmãs (só identidade do tenant, nenhum dado de domínio); evita reabrir a discussão de `ponto_suporte` como credencial de processo automatizado, já descartada. |
| 2 | Este precedente (opção b, função `SECURITY DEFINER` mínima e read-only, exposta só com as colunas que a rotina específica precisa) fica **pré-aprovado para qualquer rotina de cron cross-tenant futura** com a mesma necessidade estrutural — RFC-013 nomeava só os dois casos conhecidos na época; esta decisão generaliza explicitamente, para que a quarta ocorrência não precise de uma quarta RFC idêntica. Uma fase futura que precisar do mesmo padrão registra a nova função no seu próprio PCF, citando RFC-013 e esta RFC-014 como precedente, e pode implementar diretamente — mas continua sendo obrigatório listar a função nova na seção de "exceção ao contrato congelado" do PCF correspondente, nunca uma edição silenciosa. | Evita RFCs repetitivas para o mesmo padrão já validado três vezes, sem abrir mão do registro formal por fase (rastreabilidade de qual função existe e por quê continua exigida). |
