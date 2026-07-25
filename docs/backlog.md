# Backlog — o que foi encontrado fora do escopo

Este arquivo existe por causa de uma regra do projeto: **se está fora do seu
Pacote de Contexto de Fase, você não faz** ([`FASES-E-AGENTES.md`](../FASES-E-AGENTES.md)
§1.2, "Sem invenção de escopo"). Um agente que encontra um problema alheio tem
exatamente duas saídas legítimas — anotar aqui e seguir, ou abrir uma RFC — e
nenhuma delas é "aproveitar que está aberto e consertar".

O motivo é concreto: fases rodam em paralelo, com ownership de arquivo
mutuamente exclusivo. Uma correção "rápida" fora do seu ownership vira conflito
de merge com um agente que você não conhece, num arquivo que ele está reescrevendo
neste momento. E some do radar de quem planeja, porque ninguém registrou.

## Backlog ou RFC?

| Anote **aqui** quando… | Abra **RFC** ([protocolo](rfc/README.md)) quando… |
|---|---|
| O achado não bloqueia o seu trabalho | O achado bloqueia a sua tarefa |
| Nada em `packages/contracts/` precisa mudar | O contrato está errado, incompleto ou ambíguo |
| É dívida técnica, cobertura de teste faltando, documentação desatualizada, código morto | A decisão muda o comportamento de outras fases |
| A fase dona resolve depois, sem urgência | Alguém precisa decidir **agora** |

Na dúvida: se você precisa de uma **decisão** para continuar, é RFC. Se você só
precisa que **alguém saiba**, é backlog.

## Como registrar

Acrescente uma linha na tabela da seção correspondente. Formato fixo, quatro
colunas:

| Campo | Regra |
|---|---|
| **Data** | `AAAA-MM-DD` do dia em que você encontrou |
| **Origem** | A fase e o agente que encontraram — `F2 / A3`, `F0 / verificação` |
| **Descrição** | O que é, **com caminho de arquivo e linha**. Uma frase objetiva. Sem adjetivo e sem "seria bom" |
| **Fase sugerida** | Quem deveria resolver. `?` quando você não sabe — o orquestrador aloca |

Regras de convivência:

1. **Só acrescente linhas.** Não reescreva nem apague linha de outro agente.
2. **Não priorize por conta própria.** Prioridade é do orquestrador.
3. Ao resolver um item, **não apague a linha**: mova para a seção
   [Resolvidos](#resolvidos) com a data e a fase que resolveu. O histórico de
   "isto já foi visto e tratado" evita que o próximo agente reabra o assunto.
4. Item que virou RFC sai daqui e vira linha no índice de
   [`docs/rfc/README.md`](rfc/README.md), com referência cruzada.

---

## Aberto — herdado da Fase 0

Itens levantados pela verificação da Fase 0 e registrados na seção 9 de
[`docs/fases/F00-RELATORIO.md`](fases/F00-RELATORIO.md). Nenhum deles é defeito
do que foi entregue: são obrigações que a Fase 0 identificou e que pertencem a
fases posteriores.

| Data | Origem | Descrição | Fase sugerida |
|---|---|---|---|
| 2026-07-25 | F0 / verificação | Teste adversarial de imutabilidade: `UPDATE` e `DELETE` diretos em `marcacoes` devem falhar com `ERRCODE 42501`. A vedação está provada por leitura de código nos dois artefatos (`packages/contracts/schema.sql:1901-1907` e `apps/api/migrations/versions/0001_inicial.py:355-356`), **nunca por execução** — o daemon do Docker estava parado. | F5 |
| 2026-07-25 | F0 / verificação | Teste de concorrência do NSR: 10.000 marcações concorrentes devem produzir NSR de 1 a 10.000, sem buraco e sem repetição. As constraints existem (`uq_nsr_emissoes`, `uq_marcacoes_nsr`, `ck_nsr_sequencias_coerencia`), mas não foram exercitadas sob carga. | F5 |
| 2026-07-25 | F0 / verificação | Teste de Row Level Security provando que o tenant A não lê dado do tenant B **nem por SQL direto**. O laço da seção 19 do `schema.sql` cobre toda tabela com `tenant_id` e o bloco de verificação da seção 21 aborta a migração se alguma escapar, mas a cobertura efetiva depende de execução contra PostgreSQL real. | F1 |
| 2026-07-25 | F0 / verificação | `webhook.desabilitado` é o único evento de `packages/contracts/events.yaml` que não é citado em nenhum outro lugar — nem no `openapi.yaml`. É interno (`webhook_publico: false`) e o produtor está previsto para a F13. Registrado para não se perder. | F13 |
| 2026-07-25 | F0 / verificação | Conferir o leiaute do AFD e do AEJ **campo a campo** contra os anexos da Portaria MTP 671/2021 **antes** de codificar o gerador, e documentar em `docs/leiaute-afd-aej.md`. Nada da verificação da Fase 0 toca nisso — ela conferiu coerência interna do contrato, não conformidade com a norma. | F12 |
| 2026-07-25 | F0 / verificação | Migration inicial do Alembic verificada apenas em modo *offline* (`alembic upgrade head --sql` e `alembic downgrade head:base --sql`, ambos exit 0). Isso prova que **gera** SQL nos dois sentidos, não que **aplica**: o modo offline não executa `DO $$`, não cria partição e não impõe constraint. Falta `alembic upgrade head && alembic downgrade base` contra PostgreSQL 16 real. | F0 (fechamento) |
| 2026-07-25 | F0 / verificação | Nenhum serviço foi observado `healthy` em `docker ps` e `docker compose build` nunca rodou: o daemon do Docker estava parado no ambiente de verificação. | F0 (fechamento) |
| 2026-07-25 | F0 / verificação | "CI verde no primeiro push" continua sendo previsão, não fato: `git log` está vazio, o branch `main` não tem commit e o GitHub Actions nunca executou. Todos os gates foram reproduzidos localmente com as versões fixadas no CI (ruff 0.7.4, spectral 6.14.2, mypy 1.13.0). | F0 (fechamento) |
| 2026-07-25 | F0 / verificação | Dependências externas que não bloqueiam código e **bloqueiam homologação**: certificado e-CNPJ A1 ICP-Brasil da SEEG, registro do programa no INPI, um iDFace físico para os testes da F6 e a formalização jurídica do acordo de banco de horas da SEEG (individual escrito ou via CCT). | fora do código |

## Aberto — demais itens

| Data | Origem | Descrição | Fase sugerida |
|---|---|---|---|
| 2026-07-25 | F0 / W3 (processo) | Das **142** permissões exigidas pelo `openapi.yaml` (valores de `x-permissao`), **30 não são semeadas** por `apps/api/migrations/seed_dev.py`, que gera 200 códigos a partir de 55 recursos: `auditoria.executar`, `banco_horas.{configurar,criar,ler}`, `biometrias.aprovar`, `fechamentos.reabrir`, `fiscal.{assinar,criar,executar,exportar,ler}`, `integracoes.{criar,executar,ler}`, `lgpd.{criar,excluir,ler}`, `marcacoes.ler_sensivel`, `relatorios.criar`, `tenants.{configurar,criar,editar,ler}`, `tipos_afastamento.{criar,editar,ler}`, `tipos_solicitacao.{criar,ler}`, `tipos_tratamento.ler`, `webhooks.executar`. Não é defeito: o próprio arquivo declara que a matriz definitiva é da F1/A3. Endereçado na T8 do PCF da F1. **Quatro desses códigos são impossíveis de semear como estão** — ver RFC-002. | F1 (já endereçado no PCF) |
| 2026-07-25 | F0 / W3 (processo) | `packages/contracts/design-tokens.json` declara `pontoQuebra` com a mesma escala do Tailwind, mas o arquivo não traz o mapeamento token → utilitário do Tailwind v4. A F9a vai ter de estabelecer essa correspondência ao gerar o tema; se o resultado divergir do esperado por F8 e F9b, vira RFC. | F9a |
| 2026-07-25 | F0 / W3 (processo) | `apps/worker/worker/tarefas/__init__.py` declara na docstring que "as oito tarefas abaixo são o conjunto completo previsto para a v1", mas `packages/contracts/events.yaml` declara `importacao.concluida` com `origem: worker` e **não existe tarefa de importação** — o evento não teria produtor possível. O PCF da F2 autoriza explicitamente a criação da nona tarefa (`importar_colaboradores`, fila `ponto:integracoes`) e a atualização da docstring, porque o contrato congelado prevalece sobre a afirmação do arquivo de aplicação. Registrado para que ninguém trate o acréscimo como invenção de escopo. | F2 (já endereçado no PCF) |
| 2026-07-25 | F0 / W3 (processo) | Não existe verificador automático de que `packages/contracts/` permanece congelado. Um agente de fase pode editar `openapi.yaml` sem que nada falhe até o próximo confronto manual. Um job de CI comparando o hash dos seis artefatos contra um valor fixado fecharia a brecha. | F15 |

---

## Resolvidos

| Data | Resolvido por | Descrição | Como |
|---|---|---|---|

> Vazio por enquanto. Ao resolver um item, mova a linha para cá com a data e a
> fase que resolveu, em vez de apagá-la.
