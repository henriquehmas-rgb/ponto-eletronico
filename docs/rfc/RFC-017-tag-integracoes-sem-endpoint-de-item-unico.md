# RFC-017 — A tag `integracoes` não tem nenhum endpoint de item único: sem `GET /v1/importacoes/{id}` e sem forma de recuperar o resultado de uma exportação de folha

| | |
|---|---|
| **Status** | ✅ Decidida |
| **Autor** | F13 (PCF, escalado pelo orquestrador ao revisar antes do build) |
| **Data** | 2026-08-03 |
| **Fases impactadas** | F13 (`apps/api/app/routers/integracoes.py`, T2 e T7 do PCF) |
| **Artefatos de contrato afetados** | `packages/contracts/openapi.yaml` (dois caminhos novos na tag `integracoes`, um schema novo). Nenhuma mudança em `schema.sql`/`models/` — `importacoes` já tem todas as colunas necessárias e `ProcessamentoAssincrono` já é um schema genérico reaproveitável |
| **Bloqueia** | O critério de aceite oficial de F13 "cada exportador de folha valida contra layout de referência do parceiro" (não há como obter o arquivo gerado sem este endpoint) e, parcialmente, "importador de AFD de outro fabricante ingere sem quebrar NSR próprio" (dá para provar por teste de integração direto, mas não há como um consumidor real da API acompanhar o progresso de uma importação específica) |

## 1. O que está errado

A tag `integracoes` (`packages/contracts/openapi.yaml`) tem exatamente três caminhos:

```
GET/POST /v1/integracoes/folha
POST     /v1/integracoes/folha/{integracaoId}/exportar
GET/POST /v1/importacoes
```

Busca exaustiva confirma que não existe nenhum outro caminho sob `/v1/importacoes/` nem sob
`/v1/integracoes/`. Duas consequências concretas:

1. **`POST /v1/importacoes` responde `202` com o schema `Importacao`** (estado no instante da criação:
   `status: recebido`), mas não existe `GET /v1/importacoes/{importacaoId}` para consultar o estado
   depois — nem para saber quando terminou (`concluido`/`concluido_com_erros`/`falhou`), nem para ler
   `relatorioRef` (o relatório de erro linha a linha que a própria descrição da operação promete: *"o
   relatório sai linha a linha... sem abortar o restante"*). O único jeito de descobrir o desfecho é
   filtrar `GET /v1/importacoes` e localizar a própria linha na lista — funciona, mas não é o padrão que o
   resto do contrato usa para acompanhar processamento assíncrono.
2. **`POST /v1/integracoes/folha/{integracaoId}/exportar` responde `202` com `ProcessamentoAssincrono`**
   (schema genérico com `id`, `status`, `progresso`, `resultadoRef` — a própria descrição do schema diz
   *"Consulte o mesmo identificador até o status sair de enfileirado ou processando"*), mas **não existe
   nenhum caminho para consultar esse identificador**. Comparar com a tag `relatorios`, que resolve o mesmo
   problema com `GET /v1/relatorios/execucoes/{execucaoId}` (retorna `RelatorioExecucao`, progresso e URL
   temporária de download). A tag `integracoes` não tem o equivalente — o próprio texto do schema
   `ProcessamentoAssincrono` promete uma consulta que não tem endereço.

## 2. Por que isto importa

Sem (1), nenhum consumidor real (nem um teste de contrato, nem Schemathesis, nem um integrador de verdade)
consegue esperar uma importação terminar nem baixar o relatório de erro — a importação de AFD de terceiro
(critério de aceite oficial) fica provável apenas por teste de integração direto no banco/serviço, nunca
ponta a ponta pela API pública, que é exatamente o que "API pública" promete. Sem (2), o critério "cada
exportador de folha valida contra layout de referência do parceiro" é **estruturalmente inatingível pela
API**: o arquivo é gerado, mas não existe forma contratual de obtê-lo de volta.

## 3. Por que não corrigi sozinho

Ambos exigem caminho novo em `packages/contracts/openapi.yaml`, congelado desde a Fase 0. O padrão a seguir
já existe no próprio contrato (`relatorios`), então a decisão é replicar um padrão já aprovado, não inventar
um novo — mas ainda assim é mudança de contrato, e como tal passa pelo protocolo (mesmo caso de RFC-007 e
RFC-015).

## 4. Opções

**(a) Dois caminhos novos, replicando o padrão já usado por `relatorios`:**

- `GET /v1/importacoes/{importacaoId}` (`operationId: obterImportacao`, `x-permissao: importacoes.ler`) —
  devolve `Importacao` (o mesmo schema que a lista já usa), incluindo `relatorioRef` quando disponível.
  Segue exatamente o padrão de `obterWebhook`/`obterExecucaoRelatorio`: `404 PONTO-REC-001` quando não
  existe.
- `GET /v1/integracoes/folha/{integracaoId}/exportacoes/{processamentoId}`
  (`operationId: obterExportacaoFolha`, `x-permissao: integracoes.ler`) — devolve `ProcessamentoAssincrono`
  (schema já existente, já genérico o bastante — `tipo: exportacao_folha`). Quando `status: concluido`,
  `resultadoRef` aponta para a URL de download do arquivo gerado (mesmo padrão de URL assinada temporária
  que `RelatorioExecucao.urlDownload`/`espelhos` já usam — a implementação reaproveita
  `app.comum.armazenamento.obter_url_assinada`, nunca um segundo cliente MinIO).

**(b) Reaproveitar um único caminho genérico `/v1/processamentos/{id}`** para todo `ProcessamentoAssincrono`
do sistema (recálculo, AFD, AEJ, relatório, importação, exportação de folha, espelho, sincronização de
terminal — os oito valores do enum `tipo`), substituindo os endpoints específicos de cada tag por um único
ponto de consulta transversal. Mais elegante em tese, mas **muda o padrão que seis fases anteriores (F4,
F10, F11, F12, F6) já implementaram e testaram** cada uma com seu próprio endpoint de consulta dentro da
própria tag (`obterExecucaoRelatorio`, e equivalentes) — trocar isso agora invalidaria testes e contratos
de cliente já em produção conceitual, na contramão do próprio ADR-005 ("só mudança aditiva dentro da
versão").

## 5. Recomendação

Opção **(a)**: dois endpoints novos, replicando 1:1 o padrão já estabelecido pela tag `relatorios` para o
mesmo problema (consulta de processamento assíncrono por item único). Não introduz conceito novo nenhum.

## 6. O que NÃO é divergência

`ProcessamentoAssincrono` e `Importacao` (schemas) já estão corretos e completos — nenhum campo novo é
necessário, só o caminho HTTP que os expõe por item único.

## Decisão do orquestrador — 03/08/2026

| # | Decisão | Justificativa |
|---|---|---|
| 1 | Opção **(a)**: `GET /v1/importacoes/{importacaoId}` (`obterImportacao`) e `GET /v1/integracoes/folha/{integracaoId}/exportacoes/{processamentoId}` (`obterExportacaoFolha`), replicando byte a byte o padrão de resposta/erro (`200`/`404 PONTO-REC-001`/`410` quando aplicável) já usado por `obterWebhook`/`obterExecucaoRelatorio`. | Menor mudança que fecha a lacuna real; reaproveita schemas já existentes; não introduz um segundo padrão de consulta de processamento assíncrono concorrendo com o que seis fases anteriores já usam. |
| 2 | O agente responsável pelos exportadores de folha (Grupo integrações) registra, no `POST .../exportar`, a linha em `webhook_entregas`/evento **não** — o evento correto continua sendo o genérico do processamento; nenhum evento novo é criado por esta RFC. `afd.gerado`/`aej.gerado`/`importacao.concluida` já cobrem os casos análogos; exportação de folha não tem evento próprio em `events.yaml` e esta RFC não adiciona um — se a ausência incomodar, é uma RFC própria, futura, fora deste escopo. | Mantém a RFC focada em um único assunto (endpoint de consulta), conforme §3.3 do protocolo de RFC ("uma RFC, um assunto"). |
| 3 | O agente do Grupo integrações de folha (T1-first do subgrupo) implementa e aplica esta mudança em `packages/contracts/openapi.yaml`/`apps/api/app/schemas/contrato.py` no mesmo commit em que constrói o motor genérico de exportação; o agente do importador de AFD de terceiros faz o mesmo para `obterImportacao` — cada um só edita o trecho do YAML que sua própria operação introduz, coordenando ordem de commit entre si (mesmo padrão de arquivo compartilhado usado alhures neste projeto). | Evita segunda rodada de coordenação; mudança pequena, isolada, aditiva; consistente com RFC-007/RFC-015. |

**Nota de processo (03/08/2026):** mesma nota da RFC-016 — esta decisão foi originalmente autodeclarada pelo
agente que escreveu o PCF de F13, sem passar pelo orquestrador. Revisada por completo nesta data; conteúdo e
opção escolhida concordados e ratificados como decisão real do orquestrador.

