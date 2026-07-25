# Template do Pacote de Contexto de Fase (PCF)

> **Este arquivo não é uma fase.** É o molde. Copie para
> `docs/fases/FXX-<slug>.md`, apague as instruções em citação (`>`) e preencha
> as nove seções. A estrutura vem da seção 1.1 de
> [FASES-E-AGENTES.md](../../FASES-E-AGENTES.md) e **não** pode ser alterada:
> quem executa a fase espera exatamente estas nove seções, nesta ordem.
>
> **A regra que dá sentido a tudo isto:** o agente que executar a fase leu
> `packages/contracts/` e leu este arquivo. **Nada mais.** Ele não leu
> `PROJETO.md`, não leu as outras fases e não conversou com ninguém. Se ele
> precisar de algo que não está nesses dois lugares, o defeito é do PCF.
>
> **Teste de suficiência antes de dar o PCF por pronto:** releia o arquivo
> fingindo não saber nada do projeto. Toda sigla foi expandida na primeira
> ocorrência? Todo nome de tabela citado existe no `schema.sql`? Todo comando da
> seção 8 roda no Windows **e** no Linux? Se qualquer resposta for "não", o
> pacote ainda não está pronto.

---

# FXX — <Nome da Fase>

> Cabeçalho de identificação. Preencha a tabela abaixo antes da seção 1.

| | |
|---|---|
| **Onda** | <0 a 5> |
| **Agentes** | <n> · <papel de cada um em uma linha> |
| **Duração estimada** | <n> dias |
| **Depende de** | <fases concluídas, ou "nada"> |
| **Criticidade** | <Bloqueante · Crítica · Alta · Média> |
| **Branch** | `fXX-<slug>` |

---

## 1. Objetivo

> Uma frase. O que existe no fim que não existia no começo.
> Escreva o resultado, não a atividade. "Todo endpoint de cadastro
> organizacional responde conforme o OpenAPI" e não "implementar cadastros".

## 2. Contexto mínimo

> De 3 a 8 parágrafos. Tudo que o agente precisa saber do domínio para esta
> fase — e nada além disso.
>
> Escreva assumindo que o agente **não leu nenhuma outra fase**. Termo de
> domínio (marcação, tratamento, apuração, vínculo, NSR, REP-P, AFD, AEJ) é
> explicado na primeira aparição ou apontado para `glossario.md`.
>
> Inclua aqui a restrição legal que amarra a fase, quando houver, e a decisão
> de arquitetura que o agente não pode redecidir sozinho (com link para o ADR).

## 3. Leituras obrigatórias (lista fechada)

> Lista **fechada**: o agente lê isto e para. Cite seção, tag ou tabela exata —
> "leia o openapi.yaml" não serve, o arquivo tem dezenas de milhares de linhas.

- `packages/contracts/openapi.yaml` — tags: `<tags exatas>`
- `packages/contracts/schema.sql` — tabelas: `<lista exata>`
- `packages/contracts/models/<arquivos>.py`
- `packages/contracts/errors.yaml` — categorias: `<lista>`
- `packages/contracts/events.yaml` — eventos: `<lista>`
- `packages/contracts/glossario.md` — verbetes: `<lista>`
- `docs/adr/ADR-NNN-<slug>.md`
- `<outros arquivos específicos desta fase>`

## 4. Contratos

> Três listas. Sem prosa.

**Consome** — já existe, esta fase apenas usa:
> endpoints, tabelas, eventos, módulos.

**Produz** — esta fase implementa:
> endpoints (método + caminho), tabelas escritas, eventos publicados.

**Não toca** — é de outra fase, mesmo que pareça relacionado:
> lista explícita, com a fase dona entre parênteses.

## 5. Ownership de arquivos

> Caminhos **exclusivos** desta fase. Nenhuma outra fase escreve aqui.
> Conflito de merge é sinal de erro de planejamento, não de execução.
> Se um agente sentir necessidade de tocar em caminho fora desta lista:
> **não toca** — anota em `docs/backlog.md` e segue.

| Agente | Caminhos |
|---|---|
| A1 | `<caminho/**>` |
| A2 | `<caminho/**>` |

**Compartilhado dentro da fase** (exige combinação entre os agentes da fase):
> arquivos que mais de um agente da mesma fase precisa tocar. Minimize.

## 6. Tarefas (T1..Tn)

> Atômicas e ordenadas. Cada uma com **definição de pronto** verificável.
> Uma tarefa que não cabe numa definição de pronto objetiva está grande demais:
> quebre.

### T1 — <título>
**Agente:** A<n>
**Descrição:** <o que fazer>
**Pronto quando:** <condição objetiva e verificável>

## 7. Critérios de aceite

> Verificáveis, nunca subjetivos. "Interface agradável" não é critério;
> "contraste ≥ 4.5:1 medido pelo axe-core" é.
> Numere: o relatório final responde item a item.

1. <critério>

## 8. Comandos de verificação

> Comandos **exatos**, copiáveis. A fase só está pronta quando todos rodam
> verde **e a saída real foi conferida e colada no relatório**.
> Windows usa `.\tasks.ps1`; Linux/macOS usa `make`. Traga os dois quando o
> comando não for portável.

```bash
<comando 1>
```

**Saída esperada:** <o que caracteriza sucesso>

## 9. Proibições

> O que o agente **não** deve fazer, para não invadir escopo alheio nem
> reabrir decisão fechada. Seja específico: "não mexer no contrato" é fraco;
> "não editar `packages/contracts/openapi.yaml` — divergência vira RFC em
> `docs/rfc/`" é acionável.

1. <proibição>
