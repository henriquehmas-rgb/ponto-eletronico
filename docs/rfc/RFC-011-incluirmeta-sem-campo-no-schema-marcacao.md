# RFC-011 — `incluirMeta` de `listarMarcacoes` não tem campo no schema `Marcacao`/`ListaMarcacao` para embutir o resultado

| | |
|---|---|
| **Status** | ✅ Decidida |
| **Autor** | F5 / A3 |
| **Data** | 2026-07-26 |
| **Fases impactadas** | F5 |
| **Artefatos de contrato afetados** | `packages/contracts/openapi.yaml` |
| **Bloqueia** | Só o sub-comportamento "embutir `MarcacaoMeta` em cada linha de `listarMarcacoes`" da T10 do PCF da F5. Todo o resto da operação (filtros, paginação por cursor, bloqueio de `incluirMeta` sem `marcacoes.ler_sensivel`) segue implementado e testado. |

## 1. O que está errado

`packages/contracts/openapi.yaml`, operação `listarMarcacoes` (`GET /v1/marcacoes`,
por volta da linha 9640), declara o parâmetro de query:

```yaml
- name: incluirMeta
  in: query
  required: false
  description: Inclui o contexto antifraude de cada marcacao. Exige permissao
    sensivel e gera registro de acesso a dado sensivel.
  schema:
    type: boolean
```

e o PCF da fase (`docs/fases/F05-ingestao-marcacoes-nsr.md`, T10) descreve o
comportamento esperado como "`incluirMeta=true` embute `MarcacaoMeta` de cada
linha". Mas o schema `Marcacao` (`components.schemas.Marcacao`, por volta da
linha 31834) **não tem nenhuma propriedade** para carregar esse objeto — a
lista de propriedades vai de `id` até `criadoPor` e termina ali, sem `meta`
nem qualquer chave equivalente. O schema `ListaMarcacao`
(`components.schemas.ListaMarcacao`, por volta da linha 38967) também não tem
um array irmão de metas: só `dados: Marcacao[]` e `paginacao`.

Os modelos Pydantic gerados (`apps/api/app/schemas/contrato.py`, classes
`Marcacao` e `ListaMarcacao`) confirmam a ausência: nenhuma tem
`model_config` com `extra="allow"` (só `populate_by_name=True`), e o
comportamento padrão do Pydantic v2 para `BaseModel` sem `extra` declarado é
**ignorar** chaves desconhecidas na validação/serialização. Ou seja: mesmo que
o código do servidor tentasse anexar uma chave `"meta": {...}` a cada item de
`dados`, o FastAPI serializa a resposta através do `response_model` declarado
(`contrato.ListaMarcacao`) e a chave extra desapareceria silenciosamente antes
de chegar ao cliente. Não há como cumprir a descrição da operação como está
escrita.

## 2. Por que isto importa

Nada quebra "no ar" — não há regressão de contrato existente, porque a
operação inteira respondia `501` até esta fase. Mas se eu implementar
`incluirMeta` embutindo a chave extra do jeito descrito, o comportamento
observável é "o parâmetro não faz nada" (a chave é descartada na
serialização), o que é pior do que não implementar: parece que funciona nos
testes que só olham o objeto Python antes da serialização, e falha
silenciosamente na resposta HTTP real. Quem depender de `incluirMeta` para
evitar uma segunda chamada a `GET /v1/marcacoes/{marcacaoId}/meta` por linha
não vai perceber até inspecionar o JSON de verdade.

## 3. Por que não corrigi sozinho

A correção está inteiramente em `packages/contracts/openapi.yaml`, congelado.
Adicionar um campo ao schema `Marcacao` ou `ListaMarcacao` é uma decisão de
forma de contrato (nome do campo, se fica em cada item ou em um array irmão,
se é sempre presente ou só quando pedido) que outras fases que leem
`Marcacao`/`ListaMarcacao` (F4, F9b, F10, F14) também precisam enxergar da
mesma forma.

## 4. Opções

**(a) Adicionar `meta: MarcacaoMeta` (nullable) a `components.schemas.Marcacao`.**
*Muda:* uma propriedade nova em `openapi.yaml`, regerar `contrato.py`.
*Custa:* todo consumidor de `Marcacao` (inclusive `GET /v1/marcacoes/{id}` e o
payload embutido em `MarcacaoCriada.marcacao`) ganha um campo quase sempre
`null` (só populado por `listarMarcacoes?incluirMeta=true`), o que é um pouco
estranho para um recurso que não pediu o parâmetro.
*Passa a ser verdade:* a descrição da operação passa a ser implementável ao
pé da letra, com o menor número de conceitos novos (reaproveita o schema
`MarcacaoMeta` que já existe).

**(b) Adicionar `metas: Record<marcacaoId, MarcacaoMeta>` a `ListaMarcacao`
(objeto irmão de `dados`, não uma propriedade por item).**
*Muda:* uma propriedade nova em `ListaMarcacao`, regerar `contrato.py`.
*Custa:* o cliente precisa correlacionar por `marcacaoId` em vez de ler
`dados[i].meta` diretamente — uma indireção a mais na hora de consumir.
*Passa a ser verdade:* `Marcacao` continua sempre com a mesma forma em toda
operação que a usa (não ganha um campo condicional), e o objeto extra só
existe quando pedido, no lugar onde ele realmente pertence (a página, não a
linha).

**(c) Remover a promessa de embutir e manter `incluirMeta` só como um "atalho
de permissão"** — quando `true`, a chamada roda a MESMA checagem de
`marcacoes.ler_sensivel` (e o mesmo registro de acesso sensível em
`acessos_dados_sensiveis`) que `GET /v1/marcacoes/{id}/meta` já roda, mas a
resposta continua sendo só `Marcacao[]`, sem o contexto embutido; o cliente
que precisar do contexto por linha chama `obterMetaMarcacao` linha a linha
(operação que já existe e já entrega o schema completo).
*Muda:* a descrição da operação em `openapi.yaml` (só o texto), sem novo
campo em nenhum schema.
*Custa:* perde o ganho de performance de uma única chamada trazer tudo; para
telas que precisam do contexto de muitas linhas (ex.: fila de revisão do
gestor), o cliente faz N chamadas.
*Passa a ser verdade:* nenhum schema muda, e o comportamento de
"exige permissão sensível e registra acesso" continua cumprido de verdade
(é a parte que os critérios de aceite do PCF realmente testam).

## 5. Recomendação

**(b).** Preserva `Marcacao` estável em toda operação que a reutiliza
(inclusive dentro de `MarcacaoCriada`), entrega o ganho de performance de uma
única chamada (que é presumivelmente o motivo de o parâmetro existir — ex.:
fila de revisão do gestor olhando N marcações de uma vez) e não obriga a
decidir uma forma de "campo condicional quase sempre nulo" em `Marcacao`.

## 6. O que fiz enquanto a decisão não sai

Implementei e testei tudo o que a T10 pede e que **não** depende desta
decisão: os filtros da operação, a paginação por cursor com as duas
ordenações do contrato (`nsr`, `datahoraMarcacao`) e a rejeição
`PONTO-VAL-006` de cursor trocado de ordenação, e o bloqueio de
`incluirMeta=true` sem `marcacoes.ler_sensivel` respondendo `PONTO-PERM-001`
(a permissão é checada de verdade, com o mesmo registro de acesso sensível
que `obterMetaMarcacao` já produz — só a chamada explícita ao verificador é
duplicada, a checagem em si é a mesma da opção (c) acima). O que **não**
implementei é embutir o conteúdo de `MarcacaoMeta` na resposta quando
`incluirMeta=true` e a permissão está presente: a chamada aceita o parâmetro,
autoriza (ou recusa) corretamente, mas a resposta de `GET /v1/marcacoes` hoje
não carrega o contexto — o cliente com permissão precisa buscá-lo por
`GET /v1/marcacoes/{marcacaoId}/meta`, operação que este PCF também implementa
(T10) e que já entrega o schema completo. Assim que a decisão sair eu (ou
quem o orquestrador designar) aplico a opção escolhida e removo esta lacuna.

## Decisão do orquestrador — 26/07/2026

| # | Decisão | Justificativa |
|---|---|---|
| 1 | Opção **(b)**: `metas` (mapa `marcacaoId -> MarcacaoMeta`) acrescentado como propriedade irmã de `dados` em `components.schemas.ListaMarcacao`, em `packages/contracts/openapi.yaml`. `Marcacao` não muda. | Mantém `Marcacao` estável em todo consumidor (inclusive `MarcacaoCriada.marcacao`); o objeto extra só existe quando pedido, no lugar (a página) onde pertence. |

`apps/api/app/schemas/contrato.py` já regenerado. Pendência de implementação (não
deste orquestrador): quem fechar F5 precisa popular `metas` em `listarMarcacoes`
quando `incluirMeta=true` e a permissão estiver presente.
