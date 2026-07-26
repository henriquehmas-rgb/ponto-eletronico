# RFC-010 — Falta função de resolução de terminal e valor de enum para sincronização

| | |
|---|---|
| **Status** | ✅ Decidida/Implementada |
| **Autor** | Orquestrador (achado pelo agente que redigiu o PCF de F6, ao pesquisar o contrato para a Onda 2) |
| **Data** | 2026-07-26 |
| **Fases impactadas** | F6 (Integração Control iD) |
| **Artefatos de contrato afetados** | `packages/contracts/schema.sql` (nova função), `apps/api/migrations/versions/0001_inicial.py` (mesma função), `packages/contracts/openapi.yaml` (enum `ProcessamentoAssincrono.tipo`) |
| **Bloqueia** | F6/A1 (T2 — autenticação Push/Monitor) e F6/A2 (T-sincronização manual de terminal) não têm como começar sem isto |

## 1. O que está errado

**(a) Falta resolução de terminal antes de existir `app.tenant_id`.** Quando o iDFace chama o
`device-gw` (modo Push, ou o servidor Monitor recebe um evento), a única informação que o
protocolo Control iD carrega é o que o próprio equipamento envia — não um JWT, não um `X-Tenant`.
A tabela `terminais` tem `numero_serie` único **por tenant**
(`CREATE UNIQUE INDEX uq_terminais_serie ON terminais (tenant_id, numero_serie) ...`), está sob RLS
como qualquer tabela de domínio, e não existe nenhuma função `SECURITY DEFINER` equivalente a
`fn_resolve_tenant` para descobrir `tenant_id` a partir do `numero_serie` antes de `app.tenant_id`
existir. Sem isso, o `device-gw` não tem como abrir uma sessão de banco (mesma regra de
`obter_sessao`, F1) nem publicar RLS para processar o evento do terminal.

**(b) Falta valor de enum para sincronização de terminal.** `sincronizarTerminal` (operação de F6)
devolve `202` com um `ProcessamentoAssincrono`, cujo campo `tipo` é um enum fechado:
`recalculo | afd | aej | relatorio | importacao | exportacao_folha | espelho`. Nenhum descreve
"sincronizar cadastro/config para um terminal físico".

## 2. Por que importa

Sem (a), a fase inteira de ingestão via Control iD (T2 de A1) não tem como autenticar o terminal
que está falando com o `device-gw` — bloqueia toda a fase, não uma tarefa isolada. Sem (b),
`sincronizarTerminal` não tem como preencher um campo obrigatório da resposta sem inventar um valor
fora do enum (que o Pydantic geraria rejeitaria) ou reutilizar um valor que mente sobre a natureza
do trabalho (ex.: `importacao`, que já significa outra coisa em `Importacao.tipo`).

## 3. Por que não corrigi sozinho (pelo agente que encontrou)

Ambos exigem editar `packages/contracts/`, congelado desde a Fase 0. O agente que escreveu o PCF de
F6 sinalizou os dois como bloqueio de contrato, sem contornar (não usou `BYPASSRLS` fora de
`ponto_suporte`, não inventou valor de enum fora do catálogo).

## 4. Decisão do orquestrador — 26/07/2026

| # | Decisão | Justificativa |
|---|---|---|
| 1 | Nova função `fn_resolve_terminal(p_numero_serie TEXT)`, `SECURITY DEFINER`, expondo apenas `id`, `tenant_id`, `status` — mesma filosofia de exposição mínima de `fn_resolve_tenant`. Não precisa do padrão `CASE WHEN` da RFC-009 (não há ambiguidade de formato slug/UUID aqui: é sempre `numero_serie` literal), mas a query é escrita para nunca devolver mais de uma linha mesmo que uma anomalia futura de dados viole a unicidade por-tenant (`LIMIT 2` + a aplicação trata 2 linhas como erro, nunca escolhe a primeira em silêncio). | Mesma classe de problema que a RFC-004 resolveu para tenant; resolvida com o mesmo padrão, já revisado pela RFC-009. |
| 2 | Acrescentado `sincronizacao_terminal` ao enum `ProcessamentoAssincrono.tipo` em `openapi.yaml`. Mudança aditiva, não quebra nenhum consumidor existente do enum. | Menor mudança possível; nenhuma fase além de F6 usa este valor. |

**Implementação:**

```sql
-- Resolucao de terminal por numero de serie ANTES de existir app.tenant_id
-- (RFC-010, mesma classe de problema que fn_resolve_tenant/RFC-004/RFC-009).
-- SECURITY DEFINER porque `terminais` esta sob RLS e, na chegada de um evento
-- Push/Monitor do iDFace, ainda nao ha app.tenant_id. Expoe so tres colunas.
-- numero_serie e unico POR TENANT (uq_terminais_serie), nao globalmente -- a
-- query nunca devolve mais de uma linha por engano: LIMIT 2 e a aplicacao
-- trata 2 linhas como ambiguidade (erro), nunca escolhe a primeira.
CREATE OR REPLACE FUNCTION fn_resolve_terminal(p_numero_serie TEXT)
RETURNS TABLE (id UUID, tenant_id UUID, status TEXT)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public
AS $$
  SELECT t.id, t.tenant_id, t.status
    FROM terminais t
   WHERE t.numero_serie = p_numero_serie
     AND t.excluido_em IS NULL
   LIMIT 2;
$$;

COMMENT ON FUNCTION fn_resolve_terminal(TEXT) IS
  'Unica porta de entrada para descobrir tenant_id e id de um terminal a partir do numero de serie (RFC-010), antes de app.tenant_id existir. Devolve ate 2 linhas de proposito: a aplicacao deve tratar mais de uma linha como ambiguidade (erro), nunca escolher a primeira.';
```

Aplicada em `packages/contracts/schema.sql` (seção de terminais) e replicada em
`apps/api/migrations/versions/0001_inicial.py` (mesma convenção de `SQL_RESOLVE_TENANT`).

`ProcessamentoAssincrono.tipo` em `openapi.yaml` ganha `sincronizacao_terminal` no enum.

## 5. O que NÃO é divergência

Nenhuma tabela muda de estrutura; nenhum endpoint muda de assinatura. `fn_resolve_tenant` não é
tocada por esta RFC — é só o padrão de implementação que ela referencia.
