# RFC — Protocolo de mudança de contrato

Uma **RFC** (*Request for Comments*) é o único caminho legítimo para alterar
algo que foi congelado, ou para registrar formalmente uma divergência que exige
decisão de quem tem alçada para tomá-la.

O projeto é construído por agentes trabalhando **em paralelo**, cada um lendo
apenas `packages/contracts/` e o Pacote de Contexto da sua fase
(`docs/fases/FXX-*.md`). Isso só funciona enquanto o contrato for realmente o
mesmo para todo mundo. No instante em que um agente "resolve" uma incoerência do
contrato dentro do próprio código, o vocabulário comum se parte em dois e a
integração das fases deixa de fechar — normalmente semanas depois, longe da
causa. **Contorno silencioso é como o sistema se desintegra.** A RFC existe para
que a divergência apareça, seja decidida uma vez e seja comunicada a todos.

O protocolo canônico está em [`FASES-E-AGENTES.md`](../../FASES-E-AGENTES.md)
§1.3. Este documento é a versão operacional dele.

---

## 1. Quando abrir uma RFC

Abra uma RFC quando **qualquer** das condições abaixo for verdadeira:

| Situação | Exemplo real |
|---|---|
| O contrato está **errado** | O `openapi.yaml` declara um campo obrigatório que o `schema.sql` não tem coluna para guardar |
| O contrato está **incompleto** | A fase precisa de um código de erro que não existe em `errors.yaml` |
| O contrato está **ambíguo** | Duas leituras possíveis do mesmo campo produzem comportamentos incompatíveis |
| A mudança pedida atinge `packages/contracts/` | Qualquer edição em `openapi.yaml`, `schema.sql`, `models/`, `errors.yaml`, `events.yaml`, `design-tokens.json` ou `glossario.md` |
| A mudança **reabre um ADR aceito** | A fase quer trocar RLS por filtro de aplicação (ADR-001) |
| Duas fases disputam o mesmo caminho de arquivo | Ownership sobreposto entre PCFs — é erro de planejamento, e o orquestrador precisa saber |
| Um critério de aceite do PCF é **impossível** de cumprir como está escrito | O comando de verificação não roda no ambiente-alvo |

**Não** abra RFC — e sim registre em [`docs/backlog.md`](../backlog.md) — quando:

* o achado é **fora do escopo da sua fase** mas não bloqueia o seu trabalho
  (código feio na fase vizinha, teste faltando em outro módulo, documentação
  desatualizada);
* é uma sugestão de melhoria que não muda contrato nenhum;
* é dívida técnica que a fase dona resolve depois.

A régua é simples: **RFC quando o contrato precisa mudar ou alguém precisa
decidir agora. Backlog quando é só anotação para depois.**

Também **não** abra RFC para corrigir um defeito que está inteiramente dentro do
seu próprio ownership e não muda contrato — isso é só trabalho, faça e reporte.

---

## 2. O que fazer enquanto a RFC não é decidida

1. **Pare a tarefa afetada.** Só ela. As demais tarefas da fase continuam.
2. **Não contorne.** Não crie um campo paralelo, não invente um código de erro,
   não renomeie nada "só no seu lado", não comente o teste que falha.
3. Escreva a RFC (§3) e siga trabalhando no resto.
4. Se **toda** a fase estiver bloqueada pela RFC, reporte isso explicitamente ao
   orquestrador no relatório da fase, com a palavra "bloqueado" e o número da
   RFC.

---

## 3. Como escrever

### 3.1 Nome do arquivo

```
docs/rfc/RFC-NNN-<slug-curto-em-portugues>.md
```

* `NNN` é o próximo número livre, com três dígitos (`001`, `002`, …).
  **Numeração nunca é reaproveitada**, nem quando a RFC é rejeitada.
* O `slug` descreve o assunto, não a solução: `RFC-002-campo-cpf-em-vinculos`,
  não `RFC-002-adicionar-coluna`.
* Consulte o índice (§6) antes de escolher o número. Se dois agentes escolherem
  o mesmo número em paralelo, o orquestrador renumera na hora de decidir.

### 3.2 Template

Copie o bloco abaixo inteiro.

````markdown
# RFC-NNN — <Título em uma linha>

| | |
|---|---|
| **Status** | Proposta |
| **Autor** | <fase e agente, por exemplo "F2 / A3"> |
| **Data** | AAAA-MM-DD |
| **Fases impactadas** | <lista, ou "só a fase de origem"> |
| **Artefatos de contrato afetados** | <arquivos exatos em packages/contracts/, ou "nenhum"> |
| **Bloqueia** | <o que para de andar enquanto isto não for decidido> |

## 1. O que está errado

Fatos verificáveis, com caminho de arquivo e número de linha. Cole a saída real
do comando que expõe o problema. Sem adjetivo, sem "acho que".

## 2. Por que isto importa

O que quebra, quando quebra e para quem. Se a resposta for "nada quebra hoje",
diga isso — muda a urgência da decisão, não a validade da RFC.

## 3. Por que não corrigi sozinho

Toda RFC responde a esta pergunta. Normalmente: o artefato está congelado, a
correção invade ownership de outra fase, ou existem duas saídas legítimas com
consequências opostas.

## 4. Opções

Pelo menos duas. Para cada uma: o que muda, o que custa, o que passa a ser
verdade depois.

**(a)** …
**(b)** …

## 5. Recomendação

Uma das opções, nomeada, com o motivo em uma frase.

## 6. O que NÃO é divergência

Opcional, mas útil: o que foi conferido e está correto, para ninguém reabrir.
````

### 3.3 Como escrever bem

* **Fato antes de opinião.** Saída de comando, linha de arquivo, mensagem de
  erro. Uma RFC que começa em "seria melhor se" costuma ser backlog disfarçado.
* **Duas opções, no mínimo.** Se você só enxerga uma saída, provavelmente é
  conserto — e conserto dentro do seu ownership você faz sem RFC.
* **Diga quem fica bloqueado.** É o que define a ordem em que o orquestrador
  decide.
* **Uma RFC, um assunto.** Duas divergências independentes viram duas RFCs. A
  exceção é a RFC de fechamento de fase, que consolida os achados de uma
  verificação inteira — é o caso da RFC-001.

---

## 4. Quem decide

**O orquestrador decide.** Nenhum agente de fase decide RFC, nem a própria, nem
a de outra fase — inclusive quando a RFC é obviamente correta e a solução é
óbvia. O motivo não é hierarquia: é que a decisão precisa ser **comunicada a
todas as fases impactadas**, e só o orquestrador tem essa visão.

A decisão é registrada **dentro do próprio arquivo da RFC**, em uma seção final
chamada `## Decisão do orquestrador — DD/MM/AAAA`, com uma tabela de
`# | Decisão | Justificativa`. O `Status` do cabeçalho passa a
`✅ Decidida em DD/MM/AAAA`. Veja
[RFC-001](RFC-001-divergencias-fase-0.md) como referência de formato.

### Ciclo de vida

```
Proposta ──► Decidida ──► Implementada
    │                          │
    └──► Rejeitada             └──► (opcional) vira ADR novo
```

| Status | Significado |
|---|---|
| `Proposta` | Escrita, aguardando decisão. A tarefa afetada está parada |
| `Decidida` | O orquestrador escolheu uma opção. A implementação pode começar |
| `Implementada` | A mudança foi aplicada e verificada; a RFC vira registro histórico |
| `Rejeitada` | Fica no repositório, com o motivo. Numeração não é reaproveitada |

**RFC decidida é imutável**, como o ADR. Mudou de ideia depois? Nova RFC.

---

## 5. Depois da decisão

1. O orquestrador (ou quem ele designar) atualiza `packages/contracts/` — **é a
   única circunstância em que o contrato muda depois da Fase 0**.
2. O orquestrador atualiza os PCFs de **todas** as fases impactadas. PCF
   desatualizado é a mesma falha que RFC não escrita.
3. Se a decisão altera uma escolha estrutural de longo prazo, ela **gera um ADR
   novo** em `docs/adr/`. A RFC registra o incidente; o ADR registra a
   arquitetura resultante.
4. Quem abriu a RFC implementa e **cola a saída real** dos comandos de
   verificação no relatório da fase.

---

## 6. Índice de RFCs

| RFC | Título | Status | Decidida em | Fases impactadas |
|---|---|---|---|---|
| [001](RFC-001-divergencias-fase-0.md) | Divergências encontradas na verificação da Fase 0 | ✅ Decidida | 25/07/2026 | F0, F1, F2, F9a, F6, F7, F8 |
| [002](RFC-002-acoes-de-permissao-fora-do-check.md) | Quatro `x-permissao` do OpenAPI usam ações que o `CHECK` de `permissoes.acao` recusa | ✅ Decidida | 25/07/2026 | F1, F4, F5, F10 |
| [003](RFC-003-identidade-visual-oficial.md) | Identidade visual oficial: nome "SEEG Ponto", tipografia de três vozes | ✅ Decidida | 26/07/2026 | F9a, F7, F8, F11, F12 |
| [004](RFC-004-resolucao-de-tenant-por-uuid.md) | `fn_resolve_tenant` não resolve tenant por UUID, só por slug | ✅ Decidida | 26/07/2026 | F1 |
| [005](RFC-005-andaime-fase0-fica-obsoleto-por-fase.md) | `tests/test_andaime.py` fica obsoleto conforme as fases implementam rotas reais | ✅ Decidida | 26/07/2026 | F1..F15 (todas) |
| [006](RFC-006-acao-permissao-fora-do-enum-openapi.md) | O schema `Permissao.acao` do `openapi.yaml` não aceita as três ações que a RFC-002 liberou no banco | ✅ Decidida | 26/07/2026 | F1, F4, F5, F10 |
| [007](RFC-007-importacaocriar-sem-conteudoref.md) | `ImportacaoCriar` não declara `conteudoRef`, embora o próprio exemplo do contrato e o schema de resposta `Importacao` o usem | ✅ Decidida/Implementada | 26/07/2026 | F2, F13 |
| [008](RFC-008-precedencia-erro-contexto-vs-formato-de-caminho.md) | Erro de contexto (tenant/autenticação) tem precedência sobre validação de formato de parâmetro de caminho em toda rota real com `SessaoDb`/`exigir_permissao` | ✅ Decidida/Implementada | 26/07/2026 | F1..F15 (todas) |
| [009](RFC-009-fn-resolve-tenant-quebra-com-slug.md) | `fn_resolve_tenant` (RFC-004) lança erro de cast para qualquer slug não-UUID, de forma intermitente — regressão crítica que bloqueia login/resolução de tenant pelo mecanismo primário documentado | ✅ Decidida/Implementada | 26/07/2026 | F1..F15 (todas) |
| [010](RFC-010-resolucao-de-terminal-e-tipo-sincronizacao.md) | Falta `fn_resolve_terminal` (resolução de terminal por número de série antes de existir tenant) e falta valor de enum para sincronização de terminal em `ProcessamentoAssincrono.tipo` | ✅ Decidida/Implementada | 26/07/2026 | F6 |
| [011](RFC-011-incluirmeta-sem-campo-no-schema-marcacao.md) | `incluirMeta` de `listarMarcacoes` não tem campo no schema `Marcacao`/`ListaMarcacao` para embutir o resultado | ✅ Decidida | 26/07/2026 | F5 |
| [012](RFC-012-fila-offline-sem-contrato-de-chave-simetrica.md) | Fila offline (`ItemFilaOffline.hmac`/AES-256-GCM) não tem contrato de material de chave simétrica no servidor | ✅ Decidida (adiada) | 26/07/2026 | F5, F6, F12, F14 |
| [013](RFC-013-enumeracao-cross-tenant-para-rotinas-de-manutencao.md) | Rotina de cron cross-tenant (`verificar_terminal_offline`, `verificar_banco_horas_vencendo`) não tem mecanismo sancionado para enumerar tenants/terminais antes do RLS por linha | ✅ Decidida/Implementada | 26/07/2026 | F6, F4 |
| [014](RFC-014-enumeracao-cross-tenant-para-verificar-notificacoes-pendentes.md) | Terceiro caso do mesmo problema da RFC-013 (`verificar_notificacoes_pendentes`) — estende o precedente e o pré-aprova para futuras rotinas equivalentes | ✅ Decidida/Implementada | 27/07/2026 | F10 |
| [015](RFC-015-preferencias-colunas-sem-endpoint.md) | `preferencias_colunas` existe no schema desde a Fase 0 mas não tem nenhum schema OpenAPI nem rota HTTP | ✅ Decidida | 30/07/2026 | F11 |
| [016](RFC-016-chaves-de-api-sem-endpoint.md) | `api_keys` tem tabela e primitivas de emissão/verificação prontas desde F0/F1, mas nenhum endpoint HTTP para emitir, listar ou revogar | ✅ Decidida | 03/08/2026 | F13 |
| [017](RFC-017-tag-integracoes-sem-endpoint-de-item-unico.md) | A tag `integracoes` não tem endpoint de item único: sem `GET /v1/importacoes/{id}` e sem forma de recuperar o resultado de uma exportação de folha | ✅ Decidida | 03/08/2026 | F13 |
| [018](RFC-018-sso-sem-superficie-de-contrato.md) | SSO (Google Workspace, Entra ID, SAML 2.0) não tem nenhuma superfície de contrato: nem tag, nem caminho, nem escopo | ✅ Decidida | 03/08/2026 | F13 |
| [019](RFC-019-vinculo-de-navegador-no-state-oidc.md) | `state` do OIDC não é vinculado ao navegador que iniciou o fluxo — login-CSRF (achado de revisão adversarial) | ✅ Decidida | 03/08/2026 | F13 |
| [020](RFC-020-fila-revisao-marcacoes-suspeitas-sem-endpoint.md) | Fila de revisão do gestor (marcações suspeitas) não tem superfície HTTP no contrato — `marcacoes_meta.revisao_status` existe desde a Fase 0, mas não há filtro de listagem nem operação de decisão | ✅ Decidida | 06/08/2026 | F14 |

> Ao abrir uma RFC nova, acrescente a linha aqui **no mesmo commit**. Um índice
> desatualizado faz o próximo agente escolher um número já usado.

---

## 7. Perguntas frequentes

**"O contrato está errado mas eu consigo trabalhar em volta. Preciso mesmo abrir
RFC?"**
Sim. "Trabalhar em volta" é exatamente o contorno silencioso que este protocolo
existe para impedir. A próxima fase vai ler o contrato, não o seu contorno.

**"É uma vírgula. Sério?"**
Se está em `packages/contracts/`, sim. A RFC pode ser curta — três parágrafos
resolvem — mas precisa existir, porque a mudança precisa alcançar todas as
fases.

**"Achei um problema em código de outra fase, não no contrato."**
Isso é [`docs/backlog.md`](../backlog.md), não RFC. Anote com fase de origem e
fase sugerida e siga.

**"Minha RFC vai demorar a ser decidida e a fase inteira depende dela."**
Escreva a RFC, marque `Bloqueia: fase inteira` no cabeçalho e diga isso no
relatório. Fase bloqueada e reportada é um estado legítimo do projeto; fase
"pronta" com contorno escondido não é.
