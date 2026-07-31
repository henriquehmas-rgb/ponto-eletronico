# RFC-015 — `preferencias_colunas` existe no schema desde a Fase 0 mas não tem nenhum schema OpenAPI nem rota HTTP

| | |
|---|---|
| **Status** | ✅ Decidida |
| **Autor** | F11 (PCF, escalado pelo orquestrador ao revisar antes do build) |
| **Data** | 30/07/2026 |
| **Fases impactadas** | F11 (`app/relatorios/preferencias.py`, T1) |
| **Artefatos de contrato afetados** | `packages/contracts/openapi.yaml` (dois schemas novos, duas operações novas na tag `relatorios`). Nenhuma mudança em `schema.sql`/`models/` — a tabela e o model SQLAlchemy já existem completos |
| **Bloqueia** | Só a parte HTTP do critério de aceite oficial de F11 "colunas configuradas persistem por usuário" — o motor interno de persistência (T1 do PCF de F11) não depende desta decisão e prossegue de qualquer forma |

## 1. O que está errado

A tabela `preferencias_colunas` existe desde a Fase 0 (`packages/contracts/schema.sql`, criada em
`0001_inicial.py`, linha ~2853), com exatamente as colunas que a engine de relatórios da F11 precisa:

```sql
CREATE TABLE preferencias_colunas (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id              UUID NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
    usuario_id             UUID NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    relatorio_definicao_id UUID REFERENCES relatorio_definicoes (id) ON DELETE CASCADE,
    tela                   TEXT,
    nome                   TEXT NOT NULL DEFAULT 'padrao',
    colunas                JSONB NOT NULL,
    ordenacao              JSONB,
    filtros                JSONB,
    larguras               JSONB,
    padrao                 BOOLEAN NOT NULL DEFAULT FALSE,
    criado_em              TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por             UUID,
    atualizado_em          TIMESTAMPTZ,
    atualizado_por         UUID,
    CONSTRAINT ck_preferencias_colunas_alvo CHECK (relatorio_definicao_id IS NOT NULL OR tela IS NOT NULL)
);
```

com `CONSTRAINT ck_preferencias_colunas_alvo` já modelando corretamente as duas formas de uso (preferência
de um relatório do catálogo, ou preferência de uma grade de tela como `grade_apuracao`), um índice único
já correto (`uq_preferencias_colunas`, por `tenant_id`/`usuario_id`/alvo/`nome`), e até o comentário da
própria tabela já declarando a intenção: *"É o que faz a configuração do espelho de jornada persistir
entre sessões."* O model SQLAlchemy `PreferenciaColunas` (`packages/contracts/models/relatorio.py:221`)
também já existe, gerado a partir dessas colunas.

**Busca exaustiva em `packages/contracts/openapi.yaml` (arquivo inteiro): zero ocorrências de
`PreferenciaColuna`.** Não existe schema `PreferenciaColunas`/`PreferenciaColunasCriar`, não existe
nenhuma rota `GET`/`PUT`/`POST` sob `/v1/relatorios/preferencias-colunas` ou qualquer caminho equivalente,
em nenhuma tag do contrato.

## 2. Por que isto importa

O critério de aceite oficial da F11 (`FASES-E-AGENTES.md`, seção F11) é literal: *"colunas configuradas
persistem por usuário."* Sem uma rota HTTP, a interface (`apps/web`) não tem como salvar nem reler a
preferência de um usuário real através de uma sessão de navegador — o dado ficaria preso a uma chamada
interna que só o próprio backend pode fazer. Não é uma limitação cosmética: é a ausência do único
mecanismo que tornaria esse critério de aceite verificável ponta a ponta, para o produto real, não só em
teste de integração direto no banco.

## 3. Por que não corrigi sozinho

`packages/contracts/` está congelado desde a Fase 0 — nenhuma fase decide sozinha adicionar uma rota nova,
mesmo quando a tabela e o model já existem prontos e a necessidade é óbvia (mesmo protocolo que toda RFC
anterior já seguiu, inclusive quando a solução parecia certa e pequena, como a RFC-010/RFC-011). Como o
PCF da F11 identificou isto ANTES do build começar (revisão do orquestrador), esta RFC evita que o agente
A1 decida sozinho no meio da fase, ou pior, contorne silenciosamente salvando a preferência só em
`localStorage` sem documentar que isso era um substituto temporário de uma lacuna de contrato real.

## 4. Opções

**(a) Dois endpoints novos na tag `relatorios`**, no mesmo padrão de nomeação e verbo HTTP já usado pelo
resto do contrato:

- `GET /v1/relatorios/preferencias-colunas` — lista as preferências do usuário autenticado (o próprio
  `usuario_id` do sujeito, nunca um parâmetro livre — evita que um usuário liste a preferência de outro),
  filtrável por `relatorioDefinicaoId` ou `tela` (query, mutuamente exclusivos, mesma regra do
  `CHECK ck_preferencias_colunas_alvo`).
- `PUT /v1/relatorios/preferencias-colunas` — cria ou substitui uma preferência (idempotente por natureza:
  o corpo inteiro descreve o estado final, então não precisa de `Idempotency-Key` como os `POST`
  transacionais do resto do contrato — mesmo raciocínio que already se aplica a outros `PUT` do sistema).
  Corpo: `relatorioDefinicaoId` OU `tela` (não os dois), `nome` (default `"padrao"`), `colunas` (array,
  obrigatório), `ordenacao`/`filtros`/`larguras` (opcionais), `padrao` (boolean, default `false`).

Schemas novos: `PreferenciaColunas` (resposta) e `PreferenciaColunasCriar` (corpo do `PUT`), modelados
diretamente a partir das colunas já existentes na tabela — nenhum campo novo, nenhuma decisão de forma de
dado que a tabela não já tenha resolvido.

**(b) Reaproveitar um mecanismo genérico de "preferência de usuário"** (uma tabela chave-valor mais
solta, tipo `usuario_preferencias(usuario_id, chave, valor JSONB)`) em vez de expor `preferencias_colunas`
diretamente. Mais flexível para qualquer preferência futura (não só coluna de relatório), mas exige uma
tabela nova (migration nova, ownership de qual fase?), duplica a validação que `preferencias_colunas` já
tem via `CHECK`/índice único, e não é a estrutura que o comentário da tabela já anunciava como intenção
original. Rejeitaria trabalho de schema já pronto desde a Fase 0 sem motivo que justifique o retrabalho.

**(c) Não expor via API — aceitar `localStorage` como solução definitiva**, não temporária. Resolveria o
critério de aceite tecnicamente (preferência "persiste", só que no navegador, não no servidor), mas perde
a preferência ao trocar de dispositivo/navegador/limpar cache, e o comentário da própria tabela já deixa
claro que a intenção original era persistência real no servidor. Rejeitada — não é o que o produto
promete a um RH que configura colunas do relatório de folha uma vez e espera que continue assim em
qualquer computador que use depois.

## 5. Recomendação

**Opção (a)**: dois endpoints novos, modelados 1:1 a partir das colunas que `preferencias_colunas` já
tem. É a menor mudança de contrato que resolve o critério de aceite de verdade, reaproveita schema e
model já prontos desde a Fase 0, e segue exatamente o padrão de nomeação/verbo já usado pelo resto da tag
`relatorios`.

## 6. O que NÃO é divergência

A tabela em si, o model SQLAlchemy, o `CHECK`/índice único e o comentário de intenção da coluna — tudo
isso já está correto e completo desde a Fase 0. A única lacuna é a ausência da camada HTTP; nenhuma
mudança de schema de banco é necessária.

---

## Decisão do orquestrador — 30/07/2026

| # | Decisão | Justificativa |
|---|---|---|
| 1 | Opção **(a)**: dois endpoints novos na tag `relatorios` — `GET /v1/relatorios/preferencias-colunas` (`operationId: listarPreferenciasColunas`, `x-permissao: relatorios.ler`) e `PUT /v1/relatorios/preferencias-colunas` (`operationId: salvarPreferenciaColunas`, `x-permissao: relatorios.ler` — salvar a própria preferência de visualização não é uma ação de escrita de negócio, é personalização da própria sessão do usuário; não exige `relatorios.criar`). Schemas `PreferenciaColunas`/`PreferenciaColunasCriar` modelados exatamente pelas colunas da tabela já existente, sem campo novo. `GET` filtra sempre pelo `usuario_id` do sujeito autenticado (nunca aceita um `usuarioId` de query — evita um usuário listar a preferência de outro sem precisar de checagem de permissão adicional). | Menor mudança de contrato que resolve o critério de aceite oficial de F11 de verdade; reaproveita schema/model/constraints já prontos desde a Fase 0; segue o padrão de nomeação e verbo HTTP já estabelecido pelo resto da tag `relatorios`. |
| 2 | `PUT /v1/relatorios/preferencias-colunas` não exige `Idempotency-Key` — o corpo descreve o estado final completo (substituição, não incremento), então reenviar a mesma requisição produz o mesmo resultado sem risco de duplicata, ao contrário de um `POST` que cria uma linha nova a cada chamada. | Consistente com o próprio desenho da tabela (`uq_preferencias_colunas` já impede duplicata por natureza — o `PUT` faz `INSERT ... ON CONFLICT ... DO UPDATE` sobre esse índice), sem precisar do mecanismo de idempotência do resto do contrato. |
| 3 | F11/A1 (T1 do PCF) implementa e aplica esta mudança em `packages/contracts/openapi.yaml`/`schemas/contrato.py` no mesmo commit em que constrói o módulo interno de preferências — não é necessário esperar por um agente separado, já que a mudança é pequena, isolada e já está totalmente especificada nesta decisão. | Evita o atraso de uma segunda rodada de coordenação para algo já decidido por completo; mantém o princípio de que só o orquestrador decide, não que só o orquestrador aplica. |

