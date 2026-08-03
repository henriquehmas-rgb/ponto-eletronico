# RFC-016 — `api_keys` existe no schema e tem primitivas de emissão/verificação prontas, mas não tem NENHUM endpoint

| | |
|---|---|
| **Status** | ✅ Decidida |
| **Autor** | F13 (PCF, escalado pelo orquestrador ao revisar antes do build) |
| **Data** | 2026-08-03 |
| **Fases impactadas** | F13 (`app/integracoes/clientes/**`, T2 do PCF) |
| **Artefatos de contrato afetados** | `packages/contracts/openapi.yaml` (dois schemas novos, três operações novas na tag `admin`). Nenhuma mudança em `schema.sql`/`models/` — a tabela `api_keys` e as primitivas de geração/verificação já existem completas |
| **Bloqueia** | A parte "API keys por ambiente" do critério de aceite de F13 (`FASES-E-AGENTES.md`, escopo de A1) — sem rota, nenhum cliente consegue emitir nem revogar uma chave, mesmo a verificação já funcionando internamente |

## 1. O que está errado

A tabela `api_keys` existe desde a Fase 0 (`packages/contracts/schema.sql:3379-3406`), com exatamente as
colunas que uma gestão de chave de API precisa: `prefixo`, `hash` (`dom_sha256`), `rotulo`, `ambiente`,
`escopos`, `expira_em`, `ultimo_uso_em`, `revogada_em`, `motivo_revogacao`. O comentário da própria tabela já
anuncia a intenção: *"o prefixo serve para o usuário identificar a chave sem expô-la"* — que só faz sentido
se a chave inteira foi mostrada uma vez, na criação, exatamente como `api_clients.client_secret_hash` e
`webhooks.segredo_hmac_cifrado` já fazem.

As primitivas de aplicação também já existem, implementadas por F1 em `apps/api/app/identidade/tokens/oauth.py`:

```python
def gerar_api_key(*, prefixo_ambiente: str = "prd") -> tuple[str, str, str]:
    """Devolve (chave_em_claro, prefixo_exibivel, hash_sha256)."""

async def autenticar_api_key(sessao_db, *, tenant_id, chave_bruta) -> ApiKey:
    """Verifica uma X-API-Key. PONTO-AUTH-013 quando invalida/expirada/revogada."""
```

O próprio docstring de `autenticar_api_key` já registra a lacuna: *"Exportada para uso futuro... esta fase
entrega a primitiva de verificação"* — ou seja, F1 conscientemente construiu a primitiva e não construiu a
rota, exatamente o tipo de sinal que este protocolo pede para não ser contornado.

**Busca exaustiva em `packages/contracts/openapi.yaml`: zero ocorrências de `ApiKey` como schema, zero
caminhos `/v1/admin/api-clients/{apiClientId}/chaves` ou equivalente.** `/v1/admin/api-clients` (única
entrada da tag `admin` para clientes de integração) só tem `GET` (listar) e `POST` (criar cliente) — não há
sequer `GET`/`PATCH`/`DELETE` de um único `ApiClient`, então também não há onde pendurar um sub-recurso de
chaves.

## 2. Por que isto importa

`X-API-Key` já é um método de autenticação válido declarado em `components.securitySchemes.apiKeyAuth` e
usado em `security:` de dezenas de operações (`webhooks`, `integracoes`, `admin`) como alternativa ao OAuth
completo — a própria descrição do schema diz *"integrações simples que não justificam o fluxo OAuth
completo"*. Sem rota de emissão, essa alternativa simplesmente não existe na prática: todo integrador é
forçado ao fluxo OAuth completo, contradizendo o próprio texto do contrato.

## 3. Por que não corrigi sozinho

`packages/contracts/openapi.yaml` está congelado — acrescentar operação e schema novos é edição de
contrato, não de aplicação, mesmo quando a tabela e as primitivas já existem prontas (mesmo protocolo já
seguido pela RFC-007 e pela RFC-015, inclusive quando a solução era pequena e óbvia).

## 4. Opções

**(a) Três operações novas sob `/v1/admin/api-clients/{apiClientId}/chaves`**, no mesmo padrão de
nomenclatura, verbo HTTP e semântica de "segredo mostrado uma única vez" que `ApiClient`/`Webhook` já usam:

- `GET /v1/admin/api-clients/{apiClientId}/chaves` (`operationId: listarApiKeys`) — lista prefixo, rótulo,
  ambiente, escopos, `expiraEm`, `ultimoUsoEm`, `revogadaEm`. Nunca devolve `hash` nem a chave em claro.
- `POST /v1/admin/api-clients/{apiClientId}/chaves` (`operationId: criarApiKey`) — corpo `ApiKeyCriar`
  (`rotulo`, `ambiente`, `escopos`, `expiraEm` opcional). Resposta `201` com `ApiKeyCriada`, que embute a
  chave em claro (campo `chave`, formato `pk_<ambiente>_<...>`, gerado por `gerar_api_key` já existente) —
  mesmo aviso textual de `ApiClientCriado`: *"aparece uma única vez... não pode ser recuperada depois"`.
  `ambiente` da chave nunca pode exceder o `ambiente` do `ApiClient` pai (chave de cliente sandbox não pode
  ser `producao` — validação de aplicação, não de schema).
- `DELETE /v1/admin/api-clients/{apiClientId}/chaves/{chaveId}` (`operationId: revogarApiKey`) — marca
  `revogada_em`/`motivo_revogacao`; `204`. Idempotente por natureza (revogar duas vezes não é erro).

Schemas novos: `ApiKey` (resposta), `ApiKeyCriar` (corpo do `POST`), `ApiKeyCriada` (resposta do `POST`,
com a chave em claro) — todos modelados 1:1 a partir das colunas já existentes, nenhuma decisão de forma de
dado nova.

**(b) Reaproveitar `ApiClient`/`ApiClientCriar` com um campo opcional `gerarApiKey: boolean`** na criação do
cliente, devolvendo a chave junto de `ApiClientCriado`. Mais compacto, mas confunde duas entidades
distintas (um `ApiClient` pode ter várias `ApiKey`s ao longo do tempo, por rotação) e não permite revogar
uma chave sem revogar o cliente inteiro — contradiz o próprio modelo N:1 que `api_keys.api_client_id`
já define.

**(c) Não expor gestão de chave via API — só client_secret do OAuth.** Resolveria o critério tecnicamente
(o fluxo OAuth completo já funciona), mas descarta trabalho de schema/primitiva já pronto desde a Fase 0
sem motivo, e contradiz a própria frase do contrato sobre "integrações simples que não justificam o fluxo
OAuth completo" — sem chave de API, essa frase fica sem verdade correspondente no sistema.

## 5. Recomendação

Opção **(a)**: três endpoints novos, modelados 1:1 a partir de `api_keys` e do padrão "segredo mostrado uma
vez" já estabelecido duas vezes no mesmo contrato (`ApiClientCriado`, `WebhookCriado`).

## 6. O que NÃO é divergência

A tabela `api_keys`, `gerar_api_key`, `autenticar_api_key` e o uso de `X-API-Key` como `securityScheme` já
estão corretos e completos. A única lacuna é a ausência da camada HTTP de gestão (emitir/listar/revogar);
nenhuma mudança de schema de banco é necessária.

## Decisão do orquestrador — 03/08/2026

| # | Decisão | Justificativa |
|---|---|---|
| 1 | Opção **(a)**: três operações novas na tag `admin`, sob `/v1/admin/api-clients/{apiClientId}/chaves`, com `operationId`s `listarApiKeys` (`x-permissao: api_clients.ler`), `criarApiKey` (`x-permissao: api_clients.criar`), `revogarApiKey` (`x-permissao: api_clients.editar`). Schemas `ApiKey`/`ApiKeyCriar`/`ApiKeyCriada` modelados pelas colunas já existentes de `api_keys`, sem campo novo. `ambiente` da chave restrito por `CHECK` de aplicação a nunca exceder o `ambiente` do cliente pai (não é um `CHECK` de banco — `api_clients`/`api_keys` são tabelas distintas — é validação de serviço, documentada no PCF). | Menor mudança de contrato que resolve a lacuna real; reaproveita schema, model e primitivas já prontos desde F0/F1; segue o padrão de nomenclatura, verbo HTTP e semântica de segredo-mostrado-uma-vez já duas vezes estabelecido no mesmo contrato. |
| 2 | `x-idempotente: true` em `criarApiKey` e `revogarApiKey`, mesmo padrão de `criarWebhook`/`criarApiClient`. `listarApiKeys` segue o padrão de listagem paginada (`Cursor`/`Limite`/`Ordenar`) já usado em toda a tag `admin`. | Consistência com o resto do contrato; nenhuma decisão nova de forma. |
| 3 | F13 (agente do Grupo API pública responsável pelo núcleo de autenticação de cliente) implementa e aplica esta mudança em `packages/contracts/openapi.yaml`/`apps/api/app/schemas/contrato.py` (via `tools/gerar_do_contrato.py`) no mesmo commit em que constrói o módulo de administração de clientes — mesmo padrão de aplicação imediata que RFC-007/RFC-015 já usaram. | Evita uma segunda rodada de coordenação para algo já decidido por completo; a mudança é pequena, isolada e não afeta nenhuma fase já concluída (F1–F12 não leem `api_keys` por HTTP hoje). |

**Nota de processo (03/08/2026):** esta decisão foi originalmente registrada pelo próprio agente que escreveu
o PCF de F13, sem passar pelo orquestrador — violação do protocolo (`docs/rfc/README.md` §4: "nenhum agente
de fase decide RFC... inclusive quando a solução é óbvia"). O orquestrador revisou o conteúdo por completo
nesta data, concorda com a opção escolhida e a justificativa, e **ratifica esta decisão como sua** — o texto
acima permanece porque já está correto, não porque a auto-decisão original tinha validade. Instrução dada
aos agentes de build: nenhuma RFC nova encontrada durante a fase pode ser autodeclarada `Decidida`, mesmo
seguindo precedente óbvio — sempre `Proposta`, com opções e recomendação, para o orquestrador decidir.
