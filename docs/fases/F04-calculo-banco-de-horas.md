# F04 — Cálculo e Banco de Horas

| | |
|---|---|
| **Onda** | 3 |
| **Agentes** | 4 · **A1** apuração do dia (pareamento de marcações, tolerância, horas normais/extras por faixa e fator, adicional noturno com hora ficta 52'30" e prorrogação, intrajornada, interjornada, DSR, faltas/atrasos/saídas antecipadas) · **A2** banco de horas (múltiplas contas por colaborador, fatores de crédito/débito, extrato conta-corrente imutável, vencimento FIFO/LIFO, quitação em folha, expiração, tetos, compensação programada, simulador de saldo) · **A3** camada de tratamento (ajustes aprovados, abonos, afastamentos aplicados sobre a apuração sem tocar na marcação, recálculo determinístico e idempotente com diff auditado, trava de período fechado) · **A4** verificação (execução do golden dataset da F3 contra o cálculo real, testes de propriedade, performance) |
| **Duração estimada** | 10 dias |
| **Depende de** | F3 (motor de jornada — resolvedor e golden dataset), F5 (ingestão de marcações e NSR) |
| **Criticidade** | ⭐ Crítica — junto com F3, "a fase onde projetos de ponto morrem" ([FASES-E-AGENTES.md](../../FASES-E-AGENTES.md), F4). F9b (grade de apuração), F10 (fechamento), F11 (relatórios) e F12 (AFD/AEJ) dependem do resultado desta fase para tudo que envolve horas, saldo e correção |
| **Branch** | `f04-calculo-banco-de-horas` |

---

## 1. Objetivo

Ao fim desta fase, **dado um vínculo e um dia, o sistema pareia as marcações imutáveis daquele dia,
aplica a jornada resolvida pela F3 e os tratamentos aprovados, e produz uma apuração determinística
e recalculável (horas normais, extras por faixa e fator, adicional noturno com hora ficta,
intrajornada, interjornada, DSR, faltas/atrasos) que se materializa em `apuracoes_dia` e gera
lançamentos em conta(s) de banco de horas com extrato imutável encadeado por hash** — enquanto as 20
operações das tags `tratamentos`, `apuracoes` (que inclui `ocorrencias`) e `banco-horas` deixam de
responder `501` e passam a implementar a camada completa de correção, cálculo e conta-corrente de
horas descrita em `PROJETO.md` §4.

**O que esta fase explicitamente não faz:** workflow de aprovação de solicitações (tag
`solicitacoes`/`aprovacoes`, F10), fechamento de período e espelho oficial (tags `fechamentos`,
`espelhos`, F10), geração de relatórios (F11) e geração de AFD/AEJ (F12). Esta fase só lê
`periodos`/`fechamentos` para honrar `PONTO-PER-001`, exatamente como a F3 fez para
`vinculo_jornadas`/`escala_atribuicoes`. Se você está prestes a escrever uma tela de conferência do
RH ou um gerador de PDF, pare: não é desta fase (ver §4 e §9).

## 2. Contexto mínimo

**O produto.** Sistema de ponto eletrônico brasileiro **REP-P** (*Registrador Eletrônico de Ponto via
Programa*, Portaria MTP 671/2021), SaaS multi-tenant. Toda tabela desta fase carrega `tenant_id` sob
**Row Level Security** do PostgreSQL; a aplicação já abre cada transação publicando `app.tenant_id`
(`apps/api/app/db/sessao.py::obter_sessao`, real, entregue pela F1). Você não desabilita RLS.

**A sequência canônica do motor — decore-a, ela é o mapa de todo o resto deste documento**
(`packages/contracts/glossario.md` §5):

```
marcações imutáveis (F5)
      ↓
regras da jornada vigente do dia (F3 — resolver_jornada_do_dia)
      ↓
tratamentos aplicáveis (esta fase, A3 — ajustes aprovados · abonos · afastamentos)
      ↓
apuração do dia (esta fase, A1 — apuracoes_dia · apuracao_componentes · ocorrencias)
      ↓
lançamentos de banco de horas (esta fase, A2 — bh_lancamentos)
      ↓
fechamento (F10 — fora do escopo desta fase; você só lê periodos/fechamentos)
```

A seta nunca aponta para trás: nada nesta fase escreve em `marcacoes`, e nada nesta fase reescreve o
que a F3 resolveu. Você **consome** dois insumos de outras fases já concluídas e **produz** o que vem
depois deles na cadeia.

**Marcação, você só lê — e ela não diz "entrada" ou "saída" com certeza.** `marcacoes` (F5, imutável,
particionada por mês) tem `sentido_informado` (`entrada|saida|indefinido|NULL`) preenchido apenas
**quando o coletor informa** (o iDFace informa; o app e a web tipicamente não). Como o próprio
comentário da coluna no `schema.sql` diz: *"o REP-P não registra sentido legalmente: o pareamento
definitivo é feito na apuração."* **É esta fase que faz esse pareamento** — ordenando as marcações do
dia (e das bordas, quando a jornada cruza a meia-noite) por `(datahora_marcacao, nsr)` — ordenação
estável exigida pelo **ADR-004** — e alternando entrada/saída a partir da primeira marcação do dia,
usando `sentido_informado` como dica quando presente e coerente, e nunca como verdade cega quando
ausente ou incoerente (um número ímpar de marcações é a inconsistência `marcacao_impar`, sinalizada
como **ocorrência**, nunca corrigida silenciosamente).

**Tratamento é insumo, nunca marcação — e ele já existe como tabela, só falta o comportamento.** A
tabela `tratamentos` (seção 9 do `schema.sql`, grupo "Tratamento e apuração") já está criada pela
Fase 0; esta fase implementa o CRUD completo sobre ela (tag `tratamentos`) e, principalmente, o
**consumo** do tratamento aprovado pela apuração. Um tratamento se refere a um `data_referencia` e,
opcionalmente, a uma `marcacao_id` existente — mas **nunca a modifica**: ele se soma a ela no momento
do cálculo. `tratamentos.categoria` (via `tipos_tratamento.categoria`) determina o efeito:
`inclusao_marcacao` (o `datahora_proposta` entra no pareamento como se fosse uma marcação, mas nunca
vira uma linha de `marcacoes`), `desconsideracao_marcacao` (a marcação referenciada por `marcacao_id`
é ignorada no pareamento deste dia), `ajuste_intervalo`, `abono` (some com falta/atraso),
`justificativa`, `afastamento` (referenda um afastamento — que já é insumo da F3/resolvedor, não
recriado aqui), `compensacao` e `ajuste_saldo` (afeta diretamente o banco de horas, não a apuração de
minutos trabalhados). **`tipos_tratamento.afeta_afd` é sempre `FALSE`, garantido por `CHECK` no banco**
— nenhum tratamento gera linha no AFD; ele aparece no espelho como lançamento manual e vai para o AEJ
(F12), nunca para o AFD.

**Apuração é função pura, determinística e idempotente — decisão fechada em ADR-004, você a
implementa, não a redecide.** Leia `docs/adr/ADR-004-recalculo-determinista-idempotente.md` por
inteiro antes de escrever qualquer linha de cálculo. Os pontos que mais moldam o código: (1) toda
duração é `INTEGER` em minutos — **ponto flutuante é proibido no motor inteiro**, inclusive em
fatores intermediários (fator é `NUMERIC(6,4)` aplicado sobre inteiro, com arredondamento único e
documentado, nunca uma divisão de ponto flutuante solta); (2) a data civil da apuração é derivada do
**fuso da unidade do vínculo** (o mesmo `fuso_horario` que a F3 já resolve — leia
`unidades.fuso_horario`, ou `empresas.fuso_horario` quando `vinculos.unidade_id` for nulo, exatamente
como a F3 documentou), nunca do fuso do servidor nem do cliente; (3) `apuracoes_dia.hash_entrada`
guarda o hash do conjunto de insumos (marcações do dia, tratamentos aprovados aplicáveis, jornada/
escala/feriado/afastamento resolvidos) — recalcular com o mesmo hash é *no-op*: a linha não é
reescrita e nenhum evento é publicado; (4) todo fato retroativo declara o intervalo `(vínculo,
data_início, data_fim)` afetado, e só esse intervalo é reprocessado, expandido pelas dependências
conhecidas (interjornada olha o dia anterior; jornada que cruza a meia-noite olha o dia seguinte;
banco de horas reprocessa lançamentos a partir da data alterada); (5) toda mudança de resultado grava
o *antes* e o *depois* dos componentes na trilha de auditoria, com a causa; (6) **período fechado não
recalcula** — vira ocorrência pendente até reabertura nominal e justificada (`PONTO-PER-001`/
`PONTO-APUR-003`).

**Quando a F3 não resolve nenhuma regra, o dia não é um erro do motor — é um tipo de dia.** A F3
documentou explicitamente que `apuracoes_dia.tipo_dia = 'nao_apurado'` "não é produzido" pelo
resolvedor e "fica reservado para a F4". **Decisão fixada por este PCF:** quando
`app.jornada.resolvedor.servico.resolver_jornada_do_dia` levanta `ErroDeAplicacao("PONTO-APUR-002",
...)` para um vínculo/data dentro do intervalo sendo apurado, a apuração **não aborta o lote** — ela
grava (ou atualiza) a linha de `apuracoes_dia` daquele dia com `tipo_dia = 'nao_apurado'`, todos os
minutos zerados, `status = 'com_ocorrencia'`, e abre uma ocorrência (ver próximo parágrafo) para que o
RH saiba que falta atribuir jornada/escala àquele vínculo. `PONTO-APUR-002` só chega ao chamador
síncrono (por exemplo, se um dia só existisse essa data) — em lote, ele vira ocorrência, nunca um 500
nem uma falha que impede o resto do intervalo de apurar.

**Ocorrência é o "chamar o humano", nunca "corrigir sozinho".** `ocorrencias` (mesmo grupo de
tabelas) é onde a apuração registra toda inconsistência detectada:
`marcacao_impar`/`sem_marcacao`/`falta`/`atraso`/`saida_antecipada`/`extra_excedida`/
`jornada_excedida`/`intrajornada_suprimida`/`interjornada_violada`/`dsr_violado`/`pausa_nr17` nascem
**dentro** desta fase, durante `apurar_dia`; `fora_geocerca`/`score_baixo`/`marcacao_duplicada`/
`offline_tardio` são insumo de F5/F14 e podem já vir prontas — você as **lê e associa** à apuração via
`apuracao_dia_id`, mas não recalcula o julgamento antifraude; `banco_teto`/`banco_vencendo` nascem
nesta fase (A2); `terminal_offline` é da F6. Resolver uma ocorrência (`atualizarOcorrencia`) **nunca
corrige a jornada por si só** — a correção, se houver, é sempre um `tratamento` que a operação
referencia via `Ocorrencia.resolucao`/`ocorrencias.tratamento_id`.

**Banco de horas é produto dentro do produto — múltiplas contas, extrato append-only, vencimento por
FIFO/LIFO.** `PROJETO.md` §4.3 é a especificação de negócio completa; leia-a. Um vínculo pode ter
várias contas simultâneas (`bh_contas`, por exemplo `normal`, `sobreaviso`, `feriado`, diferenciadas
por `codigo`), cada uma amarrada a uma `bh_politicas` (regime `individual` ≤ 6 meses,
`coletivo`/`convencao` ≤ 12 meses — **limite legal imposto por `CHECK` no banco**,
`ck_bh_politicas_periodo_legal`, você não o recalcula, só o respeita). Todo lançamento
(`bh_lancamentos`) é **append-only e encadeado por hash** (mesmo padrão de `marcacoes`, mesma função
`fn_registro_imutavel`, com uma única exceção: `bh_lancamento_imutavel()` permite `UPDATE` de
**apenas** `consumido_minutos`, exigido pela rotina de consumo FIFO/LIFO — qualquer outra coluna
alterada aborta com `ERRCODE 42501`). Corrigir um lançamento é sempre um `estorno` (linha nova,
`estorna_lancamento_id` apontando para a original), nunca um `UPDATE`/`DELETE`. `bh_contas.
saldo_atual_minutos` é a fotografia materializada; a verdade é a soma de `bh_lancamentos.
minutos_equivalentes` — divergência entre os dois é **defeito**, não arredondamento, e precisa de
teste que prove igualdade em todo cenário.

**Consumo FIFO/LIFO — o que a coluna `consumido_minutos` existe para fazer.** Quando um débito (falta,
folga compensada, quitação) precisa abater saldo credor, a rotina de consumo percorre os lançamentos
de crédito da conta (mais antigos primeiro em FIFO, mais recentes primeiro em LIFO — `bh_politicas.
metodo_consumo`) e incrementa `consumido_minutos` de cada um até esgotar o débito, nunca ultrapassando
`minutos_equivalentes` de cada crédito individual. `bh_lancamentos.vence_em` é a data de vencimento
**daquele crédito específico** — é o que permite FIFO/LIFO reais (por lançamento) em vez de um saldo
único indistinto que não sabe qual parte está prestes a vencer.

**Vencimento é rotina de fundo, não ação do usuário.** O *stub* `worker/scheduler.py::
verificar_banco_horas_vencendo` já está registrado no `montar_cron()` da Fase 0 (diário, 04:10,
depois da virada do dia) — você preenche o **corpo** da função, nunca cria um novo registro de cron.
A rotina precisa **enumerar contas abertas de todos os tenants** (é um cron global, sem
`app.tenant_id` de entrada) para projetar vencimento por antecedência (`bh_politicas.
dias_pre_aviso`, padrão `{30,15,7}`) e publicar `banco_horas.vencendo` uma vez por antecedência e por
conta. Isto é **exatamente** o mesmo problema estrutural que a F6 resolveu para
`verificar_terminal_offline`, documentado e decidido em **RFC-013**: `ponto_app` não tem `BYPASSRLS`
(ADR-001), então `SELECT * FROM bh_contas` sem tenant publicado devolve sempre zero linhas. A RFC-013
já decidiu, para este caso exato ("quando a F4 chegar a `verificar_banco_horas_vencendo`, deve seguir
o mesmo padrão... não reaproveitar `ponto_suporte`"), que a solução é uma função `SECURITY DEFINER`
dedicada — o mesmo padrão de `fn_resolve_tenant`/`fn_resolve_terminal`/
`fn_terminais_para_verificacao_saude` (as três já existem em `packages/contracts/schema.sql`, seções
2 e 7). **Você não reabre essa decisão — você a implementa**, criando o equivalente
`fn_bh_contas_para_verificacao_vencimento()` (ver §5, exceção única ao contrato congelado). Como o
cron roda uma vez por dia e a antecedência é uma data exata (`periodo_fim - N dias = hoje`), o disparo
é idempotente **por construção**: não precisa de uma marca de "já avisado" (diferente do `terminal.
offline`, que é uma transição de estado, não uma data).

**A tolerância legal é dado de configuração, não fórmula fixa no código.** `jornadas.
tolerancia_marcacao_minutos` (padrão 5, art. 58 §1º CLT) e `jornadas.tolerancia_diaria_minutos`
(padrão 10) já são gravadas e expostas pela F3 — você **lê**, nunca grava. `jornadas.
descontar_tudo_se_exceder` diz o que fazer quando a tolerância diária estoura: se `TRUE`, todo o
excedente do dia é computado (não apenas a diferença acima do limite); se `FALSE` (padrão), o
comportamento é o inverso. `jornadas.fatores_extra` (JSONB) define as faixas e percentuais de hora
extra (ex.: primeira e segunda hora a 50%, excedente a 100%); `jornadas.limite_extra_diario_minutos`
(padrão 120) e `jornadas.limite_jornada_diaria_minutos` (padrão 600, teto de 10h) são os limiares de
`extra_excedida`/`jornada_excedida`.

**Adicional noturno, hora ficta e prorrogação — a fórmula fixada, para que A1 e A4 concordem.**
`jornadas.noturno_inicio`/`noturno_fim` (padrão 22:00–05:00) delimitam o período noturno urbano.
Quando `jornadas.hora_ficta_noturna = TRUE` (padrão), cada 52 minutos e 30 segundos de relógio
trabalhados **dentro** do período noturno equivalem a 60 minutos de jornada — ou seja, os minutos de
relógio noturnos são multiplicados por `60/52.5` e o resultado, arredondado para o inteiro mais
próximo (arredondamento único e documentado, nunca truncamento silencioso nem ponto flutuante solto:
calcule em aritmética racional/inteira, por exemplo `minutos_reais * 60 // (5250)` com o numerador em
centissegundos, ou equivalente com `Fraction`/`Decimal`, documentando a escolha no módulo), vira
`apuracoes_dia.noturno_ficta_minutos` (o acréscimo) somado a `apuracoes_dia.noturno_minutos` (os
minutos de relógio efetivamente noturnos). Quando `jornadas.prorrogacao_noturna = TRUE` (padrão),
uma jornada iniciada no período noturno que se estende para depois das 05:00 mantém o tratamento
noturno (hora ficta inclusive) também na prorrogação (Súmula 60, II do TST) — isto é, o corte não é
"parou às 05:00, acabou o noturno", e sim "a jornada começou de noite, então o adicional continua
até o fim dela".

**Intrajornada, interjornada e DSR — o efeito de cada um sobre o cálculo.** `jornadas.
intervalo_minimo_minutos` é o intervalo de descanso mínimo dentro da jornada; supressão total ou
parcial vira `apuracoes_dia.intrajornada_suprimida_minutos`, que gera a indenização de 50% do
período suprimido (art. 71 §4º CLT, categoria `indenizacao` em `apuracao_componentes`) e abre
ocorrência `intrajornada_suprimida` — a indenização **não é hora trabalhada**, é uma rubrica própria.
`jornadas.interjornada_minima_minutos` (padrão 660 = 11h) é o descanso mínimo entre o fim de uma
jornada e o início da seguinte; violação grava `apuracoes_dia.interjornada_violada = TRUE` e
`interjornada_minutos` (o intervalo real observado) e abre ocorrência `interjornada_violada` — isto
exige olhar o dia **anterior** ao que está sendo apurado (a marcação de saída de ontem), é a razão
pela qual ADR-004 diz que o intervalo de recálculo se expande para trás quando o insumo alterado
afeta a borda. **DSR** (`jornada_dias.tipo_dia = 'dsr'`, resolvido pela F3) credita ou debita
`apuracoes_dia.dsr_credito_minutos`/`dsr_debito_minutos` conforme o dia de repouso foi ou não
respeitado e conforme houve falta injustificada na semana (perda de DSR) — a regra de "quais faltas
da semana derrubam o DSR" é configuração de política de tenant a ser lida (não invente uma tabela
nova: se não houver campo para isso na jornada/política existente, registre em `docs/backlog.md`
como achado, não crie coluna).

**O catálogo de permissões já está completo para esta fase — confirmado, não redecidido.**
`apps/api/migrations/seed_dev.py::CATALOGO_PERMISSOES` já semeia `tratamentos.*` (CRUD + `aprovar`),
`apuracoes.{ler,executar,exportar}`, `ocorrencias.{ler,editar}`, `tipos_tratamento.ler`,
`bh_politicas.*`, `bh_contas.{ler,criar,editar}`, `bh_lancamentos.{ler,criar,exportar}`,
`bh_quitacoes.*` (CRUD + `aprovar`) e, no bloco de complemento do catálogo (F1/A3, T8), o recurso
agregado `banco_horas.{configurar,criar,ler}` — que é exatamente o valor de `x-permissao` usado pelas
rotas da tag `banco-horas` no `openapi.yaml` (`banco_horas.ler`, `banco_horas.criar`, `banco_horas.
configurar`; as rotas **não** usam `bh_contas.*`/`bh_politicas.*` como permissão de rota, essas
existem no catálogo para a matriz de perfis granular, você só declara `Depends(exigir_permissao(
"<x-permissao exato>"))` com o valor do contrato). **Você não precisa completar catálogo nenhum.**

**O que esta fase não resolve, mesmo parecendo próximo.** A **API** de fechamento de período
(`periodos`, `fechamentos`, tag ausente do seu escopo) é da F10. Implemente a consulta somente
leitura (nunca escreva nessas tabelas) que verifica um fechamento com `status = 'fechado'` cobrindo a
data e o escopo do vínculo/tratamento/quitação — mesmo padrão exato que a F3 implementou em
`app/jornada/modelagem/fechamento.py` (leia esse arquivo como referência de forma, mas **não o
importe**: é ownership exclusivo da F3; você cria sua própria cópia, ver §5). Workflow de aprovação
de solicitações (`solicitacoes`, `aprovacoes`) é da F10 — um `tratamento` pode referenciar
`solicitacao_id`, mas você não implementa a cadeia de aprovação em si, só o campo de referência e o
`decidirTratamento` (que é a aprovação **do tratamento**, não da solicitação de workflow).

## 3. Leituras obrigatórias (lista fechada)

Leia isto e pare. Não leia `PROJETO.md` além da §4 e §4.3/§4.4 já citadas acima, não leia outras
fases além dos módulos explicitamente listados, não leia o código de F1/F2/F5/F6/F9a.

- `packages/contracts/openapi.yaml` — **apenas** as tags `tratamentos` (7 operações:
  `/v1/tratamentos`, `/v1/tratamentos/{tratamentoId}`, `/v1/tratamentos/{tratamentoId}/decidir`,
  `/v1/tipos-tratamento`), `apuracoes` (5 operações: `/v1/apuracoes`, `/v1/apuracoes/{apuracaoId}`,
  `/v1/apuracoes/recalcular`, `/v1/ocorrencias`, `/v1/ocorrencias/{ocorrenciaId}`) e `banco-horas` (8
  operações: `/v1/banco-horas/{colaboradorId}/extrato`, `/v1/banco-horas/{colaboradorId}/saldo`,
  `/v1/banco-horas/simular`, `/v1/banco-horas/contas`, `/v1/banco-horas/quitacoes`,
  `/v1/banco-horas/politicas`). Preste atenção a quais operações **não** existem: não há
  `excluirTratamento` (é `cancelarTratamento`, `DELETE` que cancela, não apaga), não há
  `atualizarApuracao` (apuração só nasce e é recalculada, nunca editada por PATCH direto — a edição é
  sempre via tratamento), não há `excluirContaBancoHoras`/`atualizarContaBancoHoras`, não há
  `atualizarPoliticaBancoHoras`/`excluirPoliticaBancoHoras`, não há `excluirQuitacaoBancoHoras`; não
  os invente. Leia também, em `components`: `parameters` (`CabecalhoTenant`, `CabecalhoRequestId`,
  `CabecalhoIdempotencia`, `Cursor`, `Limite`, `Ordenar`), `responses` (`Erro400`..`Erro503`), o
  schema `Problema` e os schemas `Tratamento*`, `TipoTratamento*`, `ApuracaoDia`, `ListaApuracaoDia`,
  `ApuracaoComponente`, `Ocorrencia*`, `RecalculoRequisicao`, `ProcessamentoAssincrono`,
  `ExtratoBancoHoras`, `SaldoBancoHoras`, `SimulacaoBancoRequisicao`, `SimulacaoBancoResposta`,
  `BhConta*`, `BhQuitacao*`, `BhPolitica*`, `DecisaoRequisicao`.
- `packages/contracts/schema.sql` — seção **9 (TRATAMENTO E APURACAO)** por inteiro (linhas
  2323–2566): `tipos_tratamento`, `tratamentos`, `apuracoes_dia`, `apuracao_componentes`,
  `ocorrencias`; seção **10 (BANCO DE HORAS)** por inteiro (linhas 2568–2776): `bh_politicas`,
  `bh_contas`, `bh_lancamentos`, `bh_saldos`, `bh_quitacoes`; seção **17 (IMUTABILIDADE PARCIAL DO
  EXTRATO DE BANCO DE HORAS)** por inteiro (linhas 3864–3906) — a função `fn_bh_lancamento_imutavel()`
  e os dois gatilhos. Leia também, **só para ler, nunca escrever**: `marcacoes` (seção 8, colunas
  `id`, `vinculo_id`, `colaborador_id`, `datahora_marcacao`, `sentido_informado`, `nsr`,
  `coletada_offline`); `jornadas`/`jornada_dias` (seção 7, todas as colunas de configuração de
  cálculo citadas na §2 acima); `afastamentos` (seção 7); `vinculos` (seção 5, `unidade_id`,
  `empresa_id`, `colaborador_id`, `apura_ponto`); `unidades`/`empresas` (seção 3, `fuso_horario`);
  `periodos`/`fechamentos` (seção 12, linhas 2988–3056 — **somente os nomes de coluna**, a API é da
  F10); `auditoria` (seção 15, linhas 3521–3577 — para o diff auditado, ver §4); e, na seção 1
  (domínios), `dom_sha256`, `dom_competencia`.
- `packages/contracts/models/tratamento.py` (ou o arquivo equivalente com as classes SQLAlchemy de
  `TipoTratamento`, `Tratamento`, `ApuracaoDia`, `ApuracaoComponente`, `Ocorrencia`) e
  `packages/contracts/models/banco_horas.py` (ou equivalente, `BhPolitica`, `BhConta`,
  `BhLancamento`, `BhSaldo`, `BhQuitacao`) — **confira o nome exato do arquivo lendo o diretório**,
  não adivinhe; os nomes de arquivo podem diferir do agrupamento do `schema.sql`. Mais
  `packages/contracts/models/jornada.py` (apenas `Jornada`, `JornadaDia`, `Afastamento`) e
  `models/marcacao.py` (apenas `Marcacao`) — só para relacionar via ORM, sem editar. Mais
  `packages/contracts/models/base.py`, `models/mixins.py`, `models/tipos.py`.
- `packages/contracts/errors.yaml` — categorias **PER** (001, 003 — 002 e 004 são de fechamento, F10),
  **APUR** (001, 002, 003), **BH** (todos os 6 códigos), **CONF** (001, 003, 004), **VAL** (001, 005,
  006, 007, 009, 010, 011), e os transversais **AUTH-002, 003, 004, 006, 013**, **PERM-001, 002, 004,
  005**, **TEN-002, 003, 004**, **IDEM-001..003**, **RATE-001**, **REC-001**, **INT-001..005**.
- `packages/contracts/events.yaml` — envelope de entrega e os eventos `ajuste.aprovado`,
  `ajuste.reprovado`, `apuracao.recalculada`, `ocorrencia.aberta`, `banco_horas.vencendo`,
  `banco_horas.quitado`. Confirme que **nenhum outro evento** tem origem nesta fase.
- `packages/contracts/glossario.md` — seções **1**, **1.1 (RLS)**, **1.2 (Imutabilidade — vale
  também para o extrato de banco de horas)**; verbetes **Apuração**, **Banco de horas**,
  **Compensação**, **Crédito**, **Débito**, **DSR**, **Expiração**, **Fechamento**, **Hora ficta**,
  **Idempotência** (a do `Idempotency-Key`, distinta da idempotência de recálculo do ADR-004),
  **Interjornada**, **Intrajornada**, **Jornada**, **Ocorrência**, **Período**, **Prontidão**,
  **PTRP**, **Quitação**, **Sobreaviso**, **Soft delete**, **Tolerância**, **Tratamento**, **Vínculo**;
  seção **5 (Sequência canônica do motor)** — releia com atenção redobrada, é o mapa desta fase;
  seção **6 (Termos proibidos)**.
- `docs/adr/ADR-004-recalculo-determinista-idempotente.md` — leia por inteiro. Você **implementa**
  esta decisão, não a redecide.
- `docs/adr/ADR-001-multi-tenancy-row-level-security.md` — só para entender por que
  `verificar_banco_horas_vencendo` precisa de um mecanismo próprio de enumeração cross-tenant (ver
  RFC-013 abaixo) em vez de `BYPASSRLS`.
- `docs/rfc/RFC-013-enumeracao-cross-tenant-para-rotinas-de-manutencao.md` — leia por inteiro,
  **decidida**. É o padrão exato que você replica para `verificar_banco_horas_vencendo` (§5, exceção
  única ao contrato congelado). Não reabra a decisão; implemente a opção (b) que ela já escolheu.
- `docs/rfc/RFC-011-incluirmeta-sem-campo-no-schema-marcacao.md` — só para saber que
  `ListaMarcacao.metas` (não um campo embutido em cada `Marcacao`) é o formato decidido, relevante se
  você precisar montar uma consulta que leia várias marcações de um dia com seus metadados
  antifraude.
- `docs/backlog.md` — procure "F4" na coluna de fase sugerida antes de começar (nenhum item aberto
  específico desta fase até a data deste PCF, além do que a RFC-013 já cobriu).
- `apps/api/app/core/seguranca.py`, `apps/api/app/db/sessao.py`, `apps/api/app/core/erros.py` — o
  andaime pronto (RBAC real, `Sujeito`, `exigir_permissao`, `exigir_alcance`, `tenant_id_ou_erro`,
  `SessaoDb`, `ErroDeAplicacao`). Já implementados pela F1; você só usa.
- `apps/api/app/jornada/resolvedor/servico.py` — **leia a assinatura e o contrato fixado de
  `resolver_jornada_do_dia`** (também descrito em `docs/fases/F03-motor-de-jornada.md` §4, mas o
  código é a fonte definitiva): `async def resolver_jornada_do_dia(sessao: AsyncSession, tenant_id:
  UUID, vinculo_id: UUID, data: date) -> ResolucaoJornada`, levanta `ErroDeAplicacao("PONTO-APUR-002",
  ...)` sem regra vigente. **Você importa esta função; nunca a reescreve nem duplica sua lógica.**
- `apps/api/app/jornada/modelagem/fechamento.py` — leia como referência **de forma** da consulta
  somente leitura de `PONTO-PER-001`/`periodos`/`fechamentos` (função `verificar_periodo_aberto`).
  **Não importe este módulo** (é ownership exclusivo da F3); crie a sua própria cópia equivalente em
  `apps/api/app/apuracao/tratamento/fechamento.py` (§5).
- `apps/api/app/identidade/auditoria/hash_chain.py` — leia a assinatura pública de
  `gravar_auditoria(sessao, *, tenant_id, evento, entidade, acao, entidade_id=None, usuario_id=None,
  ..., valor_anterior=None, valor_novo=None, diferenca=None, metadados=None, resultado="sucesso",
  mensagem=None)`, real, entregue pela F1: grava uma linha em `auditoria` encadeada por hash, dentro
  da mesma transação/sessão da escrita de negócio, sem comitar sozinha. **Você reusa esta função** (é
  código real e testado, não um *stub*) para gravar o diff exigido pelo ADR-004 (ponto 6) a cada
  recálculo que muda o resultado — `entidade = "apuracoes_dia"`, `acao = "recalcular"` (já aceita pelo
  `CHECK` de `auditoria.acao`), `entidade_id = apuracoes_dia.id`, `valor_anterior`/`valor_novo` com os
  componentes antes/depois. Não reescreva a lógica de hash chain; ela já existe e está certa.
- `apps/api/app/routers/tratamentos.py`, `apps/api/app/routers/apuracoes.py`,
  `apps/api/app/routers/banco_horas.py` — os *stubs* gerados pela Fase 0 que você vai preencher (hoje
  respondem `501` com `PONTO-INT-005`). Leia como exemplo de assinatura de handler, parâmetros e tipo
  de retorno — não regere estes arquivos à mão.
- `apps/api/app/routers/contratos.py` — exemplo **vivo** de um router já implementado (F2) sobre este
  mesmo andaime: como abrir sessão, checar permissão, montar paginação, devolver o schema Pydantic
  gerado. Seu router segue exatamente este padrão.
- `apps/api/app/schemas/contrato.py` (gerado) — apenas para confirmar que os modelos Pydantic
  `Tratamento`, `TipoTratamento`, `ApuracaoDia`, `ApuracaoComponente`, `Ocorrencia`, `BhPolitica`,
  `BhConta`, `BhLancamento` (se exposto), `BhQuitacao`, `ExtratoBancoHoras`, `SaldoBancoHoras`,
  `SimulacaoBancoRequisicao`/`Resposta`, `RecalculoRequisicao`, `ProcessamentoAssincrono` (e as
  variantes `*Criar`/`*Atualizar`/`Lista*`) já existem — não os edite, é gerado.
- `apps/api/migrations/seed_dev.py` — apenas para confirmar que `tratamentos.*`, `apuracoes.*`,
  `ocorrencias.*`, `tipos_tratamento.ler`, `bh_politicas.*`, `bh_contas.*`, `bh_lancamentos.*`,
  `bh_quitacoes.*` e `banco_horas.{configurar,criar,ler}` já estão semeados (procure
  `CATALOGO_PERMISSOES`). **Você não edita este arquivo.**
- `apps/worker/worker/tarefas/apuracao.py` — o *stub* de `apurar_dia`/`recalcular_periodo` já
  registrado em `apps/worker/worker/tarefas/__init__.py` (você não toca no catálogo, só preenche o
  corpo destas duas funções, que já têm assinatura fixada por esta fase — ver §4).
- `apps/worker/worker/scheduler.py` — leia o corpo atual de `verificar_banco_horas_vencendo`
  (*stub*), `montar_cron()` (já registra o cron; você não adiciona nova entrada) e a docstring do
  módulo. `apps/worker/worker/terminais_saude.py` — leia como referência **de forma** de um módulo de
  suporte de rotina cross-tenant (mas você **não** replica o padrão de duas conexões: com a função
  `SECURITY DEFINER` já decidida pela RFC-013, uma única conexão `ponto_app` basta — ver §5).
- `docs/rfc/README.md` e `docs/backlog.md` — protocolo de RFC e onde anotar achados fora do escopo.

## 4. Contratos

**Consome** — já existe, esta fase apenas usa:

- Tabela `marcacoes` (F5), **somente leitura**: `id`, `vinculo_id`, `colaborador_id`,
  `datahora_marcacao`, `sentido_informado`, `nsr`, `coletada_offline`. Você nunca escreve nesta
  tabela, nunca a atualiza, nunca a apaga.
- Módulo `app.jornada.resolvedor.servico.resolver_jornada_do_dia` (F3) — função assíncrona
  `(sessao, tenant_id, vinculo_id, data) -> ResolucaoJornada`, que levanta `ErroDeAplicacao(
  "PONTO-APUR-002", ...)` quando não há jornada nem escala vigente. **A dependência mais importante
  desta fase, junto com `marcacoes`.** Assinatura fixada pela F3; se mudar, é RFC.
- Tabelas `jornadas`, `jornada_dias`, `afastamentos` (F3), **somente leitura**, para ler os
  parâmetros de configuração de cálculo citados na §2 (tolerâncias, fatores, hora ficta,
  interjornada, intervalo mínimo).
- Tabelas `empresas`, `unidades` (com `fuso_horario`), `vinculos` (com `unidade_id`, `empresa_id`,
  `colaborador_id`, `apura_ponto`), `colaboradores` — todas da **F2**, sob RLS, **somente leitura**.
- Tabelas `periodos`, `fechamentos` (F0/F10) — **somente leitura**, só para honrar `PONTO-PER-001`.
- Módulo `app.identidade.auditoria.hash_chain.gravar_auditoria` (F1) — função real, assinatura
  descrita na §3, para gravar o diff de todo recálculo que muda o resultado.
- Andaime da API: `app/core/erros.py`, `app/core/catalogo_erros.py`, `app/core/contexto.py`,
  `app/core/seguranca.py` (`Sujeito`, `exigir_permissao`, `exigir_alcance`, `tenant_id_ou_erro` —
  implementação real), `app/db/sessao.py` (`SessaoDb`), modelos Pydantic gerados em
  `app/schemas/contrato.py`.
- Modelos SQLAlchemy do pacote `ponto_contracts` (models de tratamento/apuração/banco de horas, e os
  que você só lê: `marcacao.py`, `jornada.py`, `organizacao.py`, `pessoas.py`).
- Catálogo de permissões já semeado por `migrations/seed_dev.py` (F1) — `tratamentos.*`,
  `apuracoes.*`, `ocorrencias.*`, `tipos_tratamento.ler`, `bh_politicas.*`, `bh_contas.*`,
  `bh_lancamentos.*`, `bh_quitacoes.*`, `banco_horas.{configurar,criar,ler}`.
- `apps/api/app/routers/__init__.py` — **já registra** os três roteadores (`tratamentos`,
  `apuracoes`, `banco_horas`) na ordem correta. Você não toca neste arquivo.
- `apps/worker/worker/tarefas/__init__.py` — já registra `apurar_dia` e `recalcular_periodo` no
  catálogo (`TAREFAS`, `NOMES_DAS_TAREFAS`). Você não toca neste arquivo, só preenche os corpos em
  `apps/worker/worker/tarefas/apuracao.py`.
- `apps/worker/worker/scheduler.py::montar_cron()` — já agenda `verificar_banco_horas_vencendo`
  diariamente às 04:10. Você não adiciona entrada de cron nova, só preenche o corpo da função.

**Produz** — esta fase implementa:

*Endpoints (20 operações; hoje `501`):*

| Tag | Operações | Agente |
|---|---|---|
| `tratamentos` (7) | `criarTratamento`, `listarTratamentos`, `obterTratamento`, `atualizarTratamento`, `cancelarTratamento`, `decidirTratamento`, `listarTiposTratamento` | A3 |
| `apuracoes` (5, inclui `ocorrencias`) | `listarApuracoes`, `obterApuracao`, `listarOcorrencias` | A1 |
| `apuracoes` (recálculo) | `recalcularApuracoes`, `atualizarOcorrencia` | A3 |
| `banco-horas` (8) | `obterExtratoBancoHoras`, `obterSaldoBancoHoras`, `simularBancoHoras`, `listarContasBancoHoras`, `criarContaBancoHoras`, `criarQuitacaoBancoHoras`, `listarPoliticasBancoHoras`, `criarPoliticaBancoHoras` | A2 |

A permissão exigida por operação é o valor de `x-permissao` no `openapi.yaml` (`tratamentos.criar`,
`apuracoes.executar`, `ocorrencias.editar`, `banco_horas.ler`, `banco_horas.configurar`, …). Use
exatamente esse valor.

*Tabelas escritas:* `tipos_tratamento`, `tratamentos`, `apuracoes_dia`, `apuracao_componentes`,
`ocorrencias`, `bh_politicas`, `bh_contas`, `bh_lancamentos`, `bh_saldos`, `bh_quitacoes` — as 10
tabelas dos grupos 8 (Tratamento e apuração) e 9 (Banco de horas) do glossário. Leitura apenas
(nunca escrita) em `marcacoes`, `jornadas`, `jornada_dias`, `afastamentos`, `empresas`, `unidades`,
`vinculos`, `colaboradores`, `periodos`, `fechamentos`, `auditoria` (você só grava nela via
`gravar_auditoria`, nunca via `INSERT` direto).

*Módulos internos publicados para outras fases (assinatura fixada por este PCF):*

- `app.apuracao.dominio.servico.apurar_dia(sessao, tenant_id, vinculo_id, data) -> ApuracaoDia` —
  função assíncrona que executa a sequência canônica completa para um vínculo e um dia (lê marcações
  do dia e da borda anterior/seguinte quando a jornada cruza a meia-noite; chama
  `resolver_jornada_do_dia`; aplica tratamentos aprovados; pareia, calcula e persiste
  `apuracoes_dia`/`apuracao_componentes`/abre `ocorrencias`; devolve o schema Pydantic
  `contrato.ApuracaoDia`, não um tipo novo). É esta função que `worker.tarefas.apuracao.apurar_dia`
  chama.
- `app.apuracao.tratamento.recalculo.recalcular_periodo(sessao, tenant_id, *, vinculo_id=None,
  empresa_id=None, unidade_id=None, departamento_id=None, colaborador_ids=None, inicio, fim, motivo,
  forcar=False) -> ResultadoRecalculo` (dataclass própria do módulo, não um schema do contrato) —
  reprocessa o intervalo, pulando dias com `hash_entrada` inalterado (a menos que `forcar=True`),
  ignorando e reportando dias em período fechado (`PONTO-APUR-003`), gravando diff em `auditoria` a
  cada dia que mudou, e devolvendo contagens (`dias_processados`, `dias_alterados`,
  `dias_ignorados_fechados`) para o handler HTTP e para o worker montarem a resposta/o evento. É esta
  função que `worker.tarefas.apuracao.recalcular_periodo` chama e que
  `POST /v1/apuracoes/recalcular` enfileira.
- **Assinaturas fixadas por este PCF** — se mudarem, atualize os três usos (rota, worker, testes) no
  mesmo commit.

*Eventos publicados:* `ajuste.aprovado`/`ajuste.reprovado` (em `decidirTratamento`, **apenas quando**
`tratamentos.solicitacao_id` não é nulo — o payload de `events.yaml` exige `solicitacaoId`; um
tratamento criado diretamente por RH/gestor sem solicitação de workflow associada não publica estes
dois eventos, só `apuracao.recalculada` quando o dia é reprocessado), `apuracao.recalculada` (ao
final do processamento de recálculo, só quando o resultado realmente mudou — hash diferente),
`ocorrencia.aberta` (durante `apurar_dia`, ao abrir uma ocorrência nova), `banco_horas.vencendo`
(rotina diária do scheduler), `banco_horas.quitado` (em `criarQuitacaoBancoHoras`, na efetivação).
Envelope exato de `events.yaml` (`id, tipo, versao, ocorridoEm, tenantId, dados`) — crie seu próprio
módulo `app/apuracao/eventos.py` com `montar_envelope`/`publicar` (mesmo padrão replicado por F3/F5,
nunca importado de outra fase).

**Não toca** — é de outra fase, mesmo que pareça relacionado:

- **Marcação em si** (criação, ingestão, NSR, CRC-16, comprovante) — **F5**, já concluída. Você só
  lê `marcacoes`.
- **Jornada, escala, turno, feriado, afastamento, e o resolvedor** — **F3**, já concluída. Você
  consome `resolver_jornada_do_dia`; nunca duplica a lógica de precedência jornada/escala/feriado/
  afastamento que ela já resolve.
- Tag `terminais`, `terminal_saude` — **F6**, já concluída.
- Tags `solicitacoes`, `aprovacoes` e as tabelas correspondentes — workflow de aprovação de
  solicitações é da **F10**. `tratamentos.solicitacao_id` é só uma FK de referência.
- Tags `fechamentos`, `espelhos`, tabelas `periodos`, `fechamentos`, `espelhos`,
  `assinaturas_espelho` — **F10**. Você só faz a consulta de leitura para `PONTO-PER-001`/
  `PONTO-APUR-003`, nunca escreve nessas tabelas.
- Tags `relatorios` — **F11**.
- Tags `fiscal` (AFD, AEJ, assinatura CAdES, `rep_ps`) — **F12**. O tratamento nunca gera linha de
  AFD (`tipos_tratamento.afeta_afd = FALSE`, imposto por `CHECK`); ele alimenta o AEJ, que é gerado
  pela F12 a partir de `apuracoes_dia`/`tratamentos`/`bh_lancamentos` — você não gera o arquivo.
- Tag `webhooks` — entrega de webhook (assinatura HMAC, retentativa, DLQ) é da **F13**. Você só
  publica no barramento interno da fase.
- `empresas`, `unidades`, `colaboradores`, `contratos`, `vinculos` — **F2**, já concluída. Você lê;
  não escreve.
- Autenticação, RBAC, resolução de tenant, trilha de auditoria (mecanismo de gravação em si) —
  **F1**, já concluída. Você usa `app/core/seguranca.py` e `app.identidade.auditoria.hash_chain.
  gravar_auditoria`.
- `packages/contracts/**` — **congelado**, com a **única exceção explícita** desta fase (§5): a
  função `fn_bh_contas_para_verificacao_vencimento()`, já pré-aprovada pela RFC-013.
- `apps/web`, `apps/mobile`, `apps/device-gw`, `apps/facial-svc`.

## 5. Ownership de arquivos

Caminhos **exclusivos** desta fase.

| Agente | Caminhos |
|---|---|
| **A1** (apuração do dia) | `apps/api/app/apuracao/dominio/**`<br>`apps/api/tests/f4/dominio/**` |
| **A2** (banco de horas) | `apps/api/app/apuracao/banco_horas/**`<br>`apps/api/app/routers/banco_horas.py`<br>`apps/worker/worker/banco_horas_vencimento.py` (novo)<br>`apps/api/tests/f4/banco_horas/**` |
| **A3** (tratamento) | `apps/api/app/apuracao/tratamento/**`<br>`apps/api/app/routers/tratamentos.py`<br>`apps/api/tests/f4/tratamento/**` |
| **A4** (verificação) | `apps/api/tests/f4/conftest.py`<br>`apps/api/tests/f4/golden/**`<br>`apps/api/tests/f4/propriedade/**`<br>`apps/api/tests/f4/performance/**` |

**Compartilhado dentro da fase** (exige combinação entre os agentes da fase):

| Caminho | Regra |
|---|---|
| `apps/api/app/apuracao/__init__.py` | Criado por **A1** na T1 (primeira tarefa de código da fase), com uma docstring e nada mais. Ninguém acrescenta código aqui. |
| `apps/api/app/routers/apuracoes.py` | Compartilhado **por operationId**, nunca por linha alheia: **A1** edita só `listar_apuracoes`, `obter_apuracao`, `listar_ocorrencias`. **A3** edita só `recalcular_apuracoes`, `atualizar_ocorrencia`. O bloco de imports no topo é comum: acrescente import necessário **em ordem alfabética**, sem remover nem reordenar linha de outro agente. Nenhum agente toca no corpo da função de outro. |
| `apps/worker/worker/tarefas/apuracao.py` | Compartilhado **por função**: **A1** preenche só o corpo de `apurar_dia` (chamando `app.apuracao.dominio.servico.apurar_dia`). **A3** preenche só o corpo de `recalcular_periodo` (chamando `app.apuracao.tratamento.recalculo.recalcular_periodo`). Ninguém edita o corpo da função do outro. |
| `apps/worker/worker/scheduler.py` | Só **A2** edita, e só o **corpo** de `verificar_banco_horas_vencendo` — a entrada em `montar_cron()` já existe (Fase 0) e não muda. |
| `apps/api/tests/f4/conftest.py` | Só **A4** edita (T1). É onde nasce a fixture com tenant + empresa + unidade + colaborador + vínculo com jornada atribuída (via tabelas da F3, só leitura/INSERT direto de massa de teste) + REP-P e uma marcação de exemplo (via tabelas da F5) + uma `bh_politica` de exemplo. A1, A2 e A3 **usam** a fixture nos seus próprios testes; não editam este arquivo — se precisarem de um dado a mais, pedem a A4. |

**Compartilhado com outras fases (contrato congelado) — exceção única e explícita:**

`packages/contracts/schema.sql` (seção 10, logo após `bh_contas`) e
`apps/api/migrations/versions/0001_inicial.py` recebem **uma única adição**, já decidida e aprovada
por **RFC-013** (não é uma nova decisão sua, é a execução da opção (b) que a RFC já escolheu para
este caso exato): a função `SECURITY DEFINER` de enumeração cross-tenant de contas de banco de horas
abertas, no mesmo padrão de `fn_resolve_tenant`/`fn_resolve_terminal`/
`fn_terminais_para_verificacao_saude` (as três já existem em `schema.sql`, seções 2 e 7 — leia-as como
modelo exato de forma):

```sql
-- Enumeracao cross-tenant para o cron verificar_banco_horas_vencendo (RFC-013,
-- mesmo padrao ja decidido para fn_terminais_para_verificacao_saude): o
-- scheduler roda um cron global, sem app.tenant_id, e precisa varrer contas
-- ABERTAS de TODOS os tenants a cada varredura diaria. ponto_app nao tem
-- BYPASSRLS (ADR-001) -- SELECT * FROM bh_contas devolveria sempre zero
-- linhas sem tenant publicado. SECURITY DEFINER expondo so as colunas que a
-- rotina precisa (nunca a tabela inteira nem bh_politicas por join).
CREATE OR REPLACE FUNCTION fn_bh_contas_para_verificacao_vencimento()
RETURNS TABLE (
    id UUID,
    tenant_id UUID,
    vinculo_id UUID,
    colaborador_id UUID,
    codigo TEXT,
    periodo_fim DATE,
    saldo_atual_minutos INTEGER,
    bh_politica_id UUID
)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public
AS $$
  SELECT c.id, c.tenant_id, c.vinculo_id, c.colaborador_id, c.codigo,
         c.periodo_fim, c.saldo_atual_minutos, c.bh_politica_id
    FROM bh_contas c
   WHERE c.status = 'aberta';
$$;

COMMENT ON FUNCTION fn_bh_contas_para_verificacao_vencimento() IS
  'Enumeracao cross-tenant de contas de banco de horas abertas para o cron verificar_banco_horas_vencendo (RFC-013), chamada pela role comum ponto_app sem app.tenant_id publicado. Expoe so as colunas necessarias a rotina, nunca a tabela inteira.';
```

**A2 é quem escreve esta função**, em ambos os arquivos (o `schema.sql` é a fonte de verdade; a
migration replica o mesmo SQL, mesmo padrão das três funções irmãs). Depois de enumerar por essa
função (sem segredo de banco adicional — diferente do interino que a F6 usou antes da RFC-013 ser
decidida, você já nasce com a versão definitiva), o corpo de `verificar_banco_horas_vencendo` abre
uma sessão `ponto_app` normal com `SET LOCAL app.tenant_id` por linha para ler `bh_politicas`
(dias de pré-aviso, ação de vencimento) e publicar o evento — **nenhuma segunda credencial de banco é
necessária**. Nenhuma outra linha de `packages/contracts/**` muda; qualquer outra necessidade de
alteração no contrato é RFC nova, não uma extensão desta.

**Explicitamente fora do seu ownership** (não edite, nem "só para arrumar"):
`packages/contracts/**` (exceto a única função acima), `apps/api/app/schemas/contrato.py` (gerado),
`apps/api/app/core/catalogo_erros.py`, `apps/api/app/core/erros.py`, `apps/api/app/core/seguranca.py`,
`apps/api/app/core/middleware.py`, `apps/api/app/db/sessao.py`, `apps/api/app/main.py`,
`apps/api/app/routers/__init__.py`, `apps/api/app/routers/{auth,tenants,admin,auditoria,empresas,
unidades,organizacao,colaboradores,contratos,biometria,dispositivos,terminais,jornadas,escalas,
feriados,afastamentos,marcacoes,comprovantes,solicitacoes,aprovacoes,fechamentos,espelhos,relatorios,
fiscal,webhooks,integracoes}.py`, `apps/api/app/jornada/**`, `apps/api/app/marcacao/**`,
`apps/api/app/identidade/**`, `apps/api/app/organizacao/**`, `apps/api/app/pessoas/**`,
`apps/api/app/biometria/**`, `apps/api/migrations/**` (inclusive `seed_dev.py`, exceto a migration
citada acima), `apps/api/tests/test_andaime.py`, `apps/worker/worker/tarefas/__init__.py`,
`apps/worker/worker/terminais_saude.py`, `.github/workflows/**`, `infra/**`, `Makefile`, `tasks.ps1`,
`apps/web/**`.

> **Nenhuma migration nova de tabela nesta fase.** As 10 tabelas dos grupos 8 e 9 já existem em
> `0001_inicial.py`. A única alteração de migration permitida é a função `SECURITY DEFINER` acima. Se
> você achar que precisa de outra coisa no schema, o contrato está errado: abra RFC.

## 6. Tarefas (T1..T13)

### T1 — Módulos de fronteira e fixture da fase
**Agentes:** A1 (`__init__.py`) e A4 (fixture) — **primeira tarefa, nada começa antes**
**Descrição:** A1 cria `apps/api/app/apuracao/__init__.py` (docstring e nada mais). A4 cria
`apps/api/tests/f4/conftest.py`: sobe PostgreSQL 16 (mesmo padrão de F3/F5:
`PONTO_TEST_DATABASE_URL`, role de LOGIN não-superusuário, RLS ativa), roda `alembic upgrade head`,
semeia 1 tenant, 1 empresa, 1 unidade (fuso `America/Sao_Paulo`), 1 colaborador com vínculo
`apura_ponto=true`, uma jornada fixa simples atribuída ao vínculo (via `INSERT` direto nas tabelas da
F3 — `jornadas`, `jornada_dias`, `vinculo_jornadas` —, nunca via HTTP), 1 REP-P ativo e um pequeno
conjunto de marcações de exemplo (via `INSERT` direto em `marcacoes`, respeitando NSR sequencial —
não chame a API de ingestão da F5), e uma `bh_politica` de exemplo (regime `individual`,
`periodo_meses=6`). Documente no módulo que o formato de cenário do golden dataset da F3
(`tests/f3/golden/formato.py::Cenario`/`Montagem`) é **reaproveitado, não recriado**, pela T11.
**Pronto quando:** `pytest apps/api/tests/f4 -q` coleta e a fixture sobe e derruba o banco sem erro.

### T2 — Pareamento de marcações e tolerância
**Agente:** A1
**Descrição:** `app/apuracao/dominio/pareamento.py`: função pura `parear_marcacoes(marcacoes:
Sequence[Marcacao]) -> ResultadoPareamento` — ordena por `(datahora_marcacao, nsr)`, alterna
entrada/saída a partir da primeira, usa `sentido_informado` como dica quando presente e coerente com
a alternância, sinaliza `marcacao_impar` quando a contagem é ímpar (o último período fica "aberto",
sem par de saída) e `sem_marcacao` quando o dia esperava trabalho (`tipo_dia` != `folga`/`dsr`) e não
há nenhuma. `app/apuracao/dominio/tolerancia.py`: aplica `jornadas.tolerancia_marcacao_minutos`
(por marcação) e `tolerancia_diaria_minutos` (acumulada), com o comportamento de
`descontar_tudo_se_exceder` documentado na §2.
**Pronto quando:** teste de mesa cobre número par de marcações, número ímpar (ocorrência
`marcacao_impar`), nenhuma marcação em dia útil (ocorrência `sem_marcacao`), `sentido_informado`
presente e coerente, e `sentido_informado` ausente (pareamento só por ordem); teste prova que
atraso de 3 minutos dentro da tolerância de 5 não gera falta/atraso computado e que 12 minutos
(acima da tolerância diária de 10) gera o comportamento certo conforme `descontar_tudo_se_exceder`
nos dois valores.

### T3 — Horas normais, extras por faixa/fator, adicional noturno com hora ficta e prorrogação
**Agente:** A1
**Descrição:** `app/apuracao/dominio/calculo.py`: a partir do pareamento (T2) e da
`ResolucaoJornada` (F3), calcula minutos trabalhados totais, separa normais de extras usando
`jornadas.fatores_extra` (faixas e percentuais) e `limite_extra_diario_minutos`/
`limite_jornada_diaria_minutos` (`extra_excedida`/`jornada_excedida` como ocorrência quando
ultrapassados), e aplica a fórmula de hora ficta noturna e prorrogação fixada na §2
(`jornadas.noturno_inicio`/`noturno_fim`, `hora_ficta_noturna`, `prorrogacao_noturna`) — tudo em
aritmética inteira, arredondamento único e documentado no módulo, **nunca ponto flutuante** (ADR-004,
ponto 2). Popula `apuracao_componentes` com uma linha por rubrica (`codigo`, `categoria`, `minutos`,
`fator`, `minutos_equivalentes`, `origem`, `inicio`/`fim`).
**Pronto quando:** teste de mesa cobre jornada 100% diurna, jornada cruzando o período noturno sem
prorrogação, jornada iniciada no noturno e prorrogada além das 05:00 (Súmula 60, II TST), e extra
acima do limite diário (ocorrência `jornada_excedida`); teste prova que a soma dos
`apuracao_componentes.minutos_equivalentes` de uma apuração bate com os totais agregados em
`apuracoes_dia`.

### T4 — Intrajornada, interjornada, DSR, faltas/atrasos/saídas antecipadas e integração com o resolvedor
**Agente:** A1
**Descrição:** Completa `app/apuracao/dominio/calculo.py` (ou módulo irmão) com intrajornada
(`intervalo_minimo_minutos`, indenização de 50% do suprimido, ocorrência `intrajornada_suprimida`),
interjornada (`interjornada_minima_minutos`, olhando a última marcação do dia **anterior**,
ocorrência `interjornada_violada`), DSR (crédito/débito conforme `tipo_dia = 'dsr'` resolvido pela F3
e faltas da semana) e falta/atraso/saída antecipada. Implementar
`app/apuracao/dominio/servico.py::apurar_dia(sessao, tenant_id, vinculo_id, data) -> ApuracaoDia`
(assinatura fixada na §4): chama `resolver_jornada_do_dia`; em `PONTO-APUR-002`, grava
`tipo_dia='nao_apurado'`, minutos zerados, `status='com_ocorrencia'`, abre ocorrência e **não propaga
a exceção** para o chamador de lote (decisão fixada na §2); aplica tratamentos aprovados do dia (via
`app.apuracao.tratamento`, T7); persiste `apuracoes_dia`/`apuracao_componentes`/`ocorrencias`
(`INSERT ... ON CONFLICT (tenant_id, vinculo_id, data) DO UPDATE` respeitando `uq_apuracoes_dia`);
calcula e grava `hash_entrada`; é *no-op* (não reescreve, não publica evento) se o hash não mudou.
Ligar o corpo de `apurar_dia` em `apps/worker/worker/tarefas/apuracao.py` chamando esta função.
**Pronto quando:** teste prova intrajornada suprimida gerando indenização e ocorrência; teste prova
interjornada violada olhando o dia anterior; teste prova vínculo sem jornada/escala vigente produz
`apuracoes_dia.tipo_dia='nao_apurado'` sem levantar exceção e sem abortar quando chamado em lote;
teste prova que chamar `apurar_dia` duas vezes seguidas sem mudança de insumo não gera segunda
escrita nem segundo evento (idempotência local).

### T5 — CRUD de políticas e contas de banco de horas
**Agente:** A2
**Descrição:** `app/apuracao/banco_horas/politicas.py` e `contas.py`: `listarPoliticasBancoHoras`,
`criarPoliticaBancoHoras` (valida `ck_bh_politicas_periodo_legal` na aplicação também, com mensagem
melhor que o `CHECK` cru, recusando com `PONTO-BH-003`; exige `documentoAcordoId` quando a política
não é `especial`, recusando com `PONTO-BH-006`), `listarContasBancoHoras`, `criarContaBancoHoras`
(deriva `periodo_fim` de `bh_politicas.periodo_meses` a partir de `periodoInicio`, recusa
`ck_bh_contas_periodo`/duplicidade `uq_bh_contas` com `PONTO-CONF-001`).
**Pronto quando:** teste prova que política `individual` com `periodoMeses=12` é recusada
(`PONTO-BH-003`) mas `coletivo` com `periodoMeses=12` é aceita; teste prova que criar política sem
`documentoAcordoId` e regime diferente de `especial` responde `PONTO-BH-006`; teste prova que duas
contas do mesmo vínculo, mesmo `codigo`, mesmo `periodoInicio` colidem (`PONTO-CONF-001`).

### T6 — Extrato, saldo, lançamentos e consumo FIFO/LIFO
**Agente:** A2
**Descrição:** `app/apuracao/banco_horas/lancamentos.py`: função interna
`lancar(sessao, *, bh_conta_id, tipo, origem, minutos, fator, data_competencia, vence_em=None,
descricao, **refs) -> BhLancamento` que aloca `sequencia` (via `bh_contas.ultima_sequencia`, mesmo
padrão transacional de NSR/auditoria: `UPDATE ... RETURNING`, nunca `SEQUENCE`), calcula
`minutos_equivalentes` (inteiro, fator aplicado com arredondamento documentado), `saldo_apos_minutos`
e a cadeia de hash (`hash_anterior`/`hash_registro`, mesma fórmula de canonicalização documentada que
F1/F5 usaram para seus próprios hash chains — fixe e documente a fórmula **desta** cadeia no módulo).
Implementar o consumo FIFO/LIFO: função que, dado um débito, percorre créditos da conta na ordem de
`bh_politicas.metodo_consumo` e incrementa `consumido_minutos` até esgotar (única exceção de `UPDATE`
permitida por `fn_bh_lancamento_imutavel`). `app/apuracao/banco_horas/consulta.py`:
`obterExtratoBancoHoras` (paginado, cursor próprio — crie sua cópia em
`app/apuracao/banco_horas/paginacao.py`, não importe de `app.marcacao.consulta.paginacao` nem de
`app.jornada.modelagem.paginacao`), `obterSaldoBancoHoras` (com `a_vencer_30/15/7_minutos`) e
`simularBancoHoras` (não grava nada — clona o cálculo em memória).
**Pronto quando:** teste prova a cadeia de hash (linha N+1 tem `hash_anterior` == `hash_registro` de
N); teste prova que a soma dos `bh_lancamentos.minutos_equivalentes` de uma conta bate exatamente com
`bh_contas.saldo_atual_minutos`; teste prova consumo FIFO consumindo o crédito mais antigo primeiro e
LIFO o mais recente primeiro, ambos parando exatamente no limite do débito; teste prova que `UPDATE`
direto em qualquer coluna de `bh_lancamentos` além de `consumido_minutos` falha com `ERRCODE 42501`
(conectado como a role de aplicação, não superusuário); teste prova que `simularBancoHoras` não altera
nenhuma linha do banco.

### T7 — Quitação, expiração, tetos e a rotina de vencimento (com a função SECURITY DEFINER)
**Agente:** A2
**Descrição:** `app/apuracao/banco_horas/quitacoes.py::criarQuitacaoBancoHoras`: valida saldo
suficiente (`PONTO-BH-005` se não), respeita a trava de período (`PONTO-PER-001` via a cópia própria
de `verificar_periodo_aberto`, T9/A3 disponibiliza o módulo — combine a assinatura com A3 antes),
efetiva o lançamento de `quitacao`/`expiracao` (T6), publica `banco_horas.quitado`. Implementar os
tetos: `bh_politicas.teto_positivo_minutos`/`teto_negativo_minutos` e `bloqueia_extra_no_teto`
recusando novo crédito com `PONTO-BH-001`/`PONTO-BH-002` quando aplicável, abrindo ocorrência
`banco_teto` quando sinalizado em vez de bloqueado. Criar a função `fn_bh_contas_para_verificacao_
vencimento()` em `packages/contracts/schema.sql` (seção 10) e replicá-la em
`apps/api/migrations/versions/0001_inicial.py` (SQL literal da §5 — exceção única e já aprovada pela
RFC-013). Implementar o corpo de `verificar_banco_horas_vencendo` em
`apps/worker/worker/scheduler.py`, com o módulo de suporte novo
`apps/worker/worker/banco_horas_vencimento.py` (uma única engine `ponto_app`, chama a função acima
sem tenant publicado, depois abre `SET LOCAL app.tenant_id` por linha para ler `bh_politicas.
dias_pre_aviso`/`acao_vencimento` e publicar o evento — sem segunda credencial de banco).
**Pronto quando:** teste prova saldo insuficiente recusado (`PONTO-BH-005`); teste prova quitação
efetivada gera lançamento e publica `banco_horas.quitado` com payload validado campo a campo contra
`events.yaml`; teste prova teto positivo com `bloqueiaExtraNoTeto=true` recusando novo crédito
(`PONTO-BH-001`); teste de migration prova que `fn_bh_contas_para_verificacao_vencimento()` existe e
devolve contas de **dois tenants diferentes** numa única chamada sem `app.tenant_id` publicado (prova
de que o SECURITY DEFINER funciona); teste prova que a rotina publica `banco_horas.vencendo` para uma
conta cujo `periodo_fim` está a exatamente 30/15/7 dias da data simulada, e não publica para outras
distâncias.

### T8 — CRUD de tratamentos e tipos de tratamento
**Agente:** A3
**Descrição:** `app/apuracao/tratamento/servico.py`: `criarTratamento` (valida `motivo` obrigatório,
`ck_tratamentos_marcacao` — `marcacao_id`+`marcacao_datahora` juntos ou nenhum dos dois —, recusa
período fechado com `PONTO-PER-001` via a cópia própria de `verificar_periodo_aberto` — T9),
`listarTratamentos`, `obterTratamento`, `atualizarTratamento` (só em `rascunho`/`pendente`, recusa
transição inválida com `PONTO-CONF-003`), `cancelarTratamento` (`DELETE` que cancela — nunca apaga a
linha; tratamento `aplicado` cancelado gera novo registro de cancelamento e agenda recálculo do dia,
nunca reescreve o original), `listarTiposTratamento` (confirma `afeta_afd=false` sempre, nunca
aceito como `true` na criação de tipo — isso é seed/config, mas se a rota de tipo de tratamento
aceitar edição, recuse mudar essa coluna).
**Pronto quando:** teste prova `ck_tratamentos_marcacao` (informar só `marcacaoId` sem
`marcacaoDatahora`, ou vice-versa, é recusado); teste prova tratamento em dia de período fechado
responde `PONTO-PER-001`; teste prova `cancelarTratamento` de um tratamento `aplicado` preserva a
linha original e cria um registro de cancelamento auditável.

### T9 — Decisão de tratamento e trava de período fechado
**Agente:** A3
**Descrição:** `app/apuracao/tratamento/decisao.py::decidirTratamento`: aprovar marca
`status='aprovado'`, `aprovado_por`/`aprovado_em`, e **agenda o recálculo do dia** (chama
`recalcular_periodo` para o intervalo mínimo daquele `data_referencia`, expandido conforme ADR-004);
reprovar marca `status='reprovado'`, `reprovado_motivo`, sem tocar na apuração. Publica
`ajuste.aprovado`/`ajuste.reprovado` **apenas quando** `tratamentos.solicitacao_id` não é nulo
(payload exige `solicitacaoId`), e sempre publica `apuracao.recalculada` quando a aprovação de fato
mudar o resultado do dia. `app/apuracao/tratamento/fechamento.py::verificar_periodo_aberto` — cópia
própria (não importe de `app.jornada.modelagem.fechamento`), mesma consulta somente leitura de
`periodos`/`fechamentos` que a F3 implementou, usada por T8 (criação/atualização de tratamento), T7
(A2, quitação) e T10 (recálculo).
**Pronto quando:** teste prova aprovação de tratamento sem `solicitacaoId` **não** publica
`ajuste.aprovado` mas publica `apuracao.recalculada` quando o dia muda; teste prova aprovação com
`solicitacaoId` presente publica os dois eventos com payload validado campo a campo; teste prova que
a consulta de `PONTO-PER-001` não derruba nenhuma operação enquanto `fechamentos` estiver vazio
(caminho hoje sempre verdadeiro nesta fase, como a F3 documentou para o caso análogo).

### T10 — Recálculo determinístico e idempotente, com diff auditado
**Agente:** A3
**Descrição:** `app/apuracao/tratamento/recalculo.py::recalcular_periodo` (assinatura fixada na §4):
para cada `(vinculo_id, data)` do escopo pedido, chama `apurar_dia` (A1); se `apuracoes_dia.
hash_entrada` não mudou, pula (no-op, sem escrita, sem evento); se mudou, grava a nova apuração,
incrementa `apuracoes_dia.versao`, chama `gravar_auditoria` (F1) com `entidade="apuracoes_dia"`,
`acao="recalcular"`, `entidade_id`, `valor_anterior` (componentes antigos), `valor_novo` (componentes
novos), `metadados={"motivo": ...}`; dias em período fechado (`verificar_periodo_aberto` de T9
levanta `PONTO-PER-001`) são **pulados e contados**, não abortam o restante do intervalo — reporte
como `PONTO-APUR-003` no resultado agregado. Implementar `POST /v1/apuracoes/recalcular`: valida o
corpo, decide o escopo (vínculos explícitos, ou por empresa/unidade/departamento), **enfileira**
via `ctx["redis"].enqueue_job("recalcular_periodo", ...)` (mesmo padrão de
`app.importadores.servico.criar_importacao_colaboradores`, F2) com um `job_id` gerado no momento da
chamada, e devolve `202` com `ProcessamentoAssincrono{id=job_id, tipo="recalculo",
status="enfileirado"}`. **Achado de contrato, não invenção sua:** a tag `apuracoes` não declara
nenhuma operação de consulta de status por identificador (ao contrário de `relatorios`, que tem
`obterExecucaoRelatorio`) nem existe tabela dedicada para persistir o handle — documente esta lacuna
em `docs/backlog.md` (fase sugerida: quem primeiro precisar de polling de recálculo em produção, ou
F10/F11) e **não invente o endpoint**; a conclusão do recálculo é observável via
`GET /v1/apuracoes?status=...` e via o evento `apuracao.recalculada`, que já bastam para o critério de
aceite desta fase.
**Pronto quando:** teste prova que recalcular o mesmo intervalo duas vezes seguidas, sem mudança de
insumo, produz exatamente o mesmo `apuracoes_dia` (mesma `versao`, mesmo `hash_entrada`, nenhuma linha
nova em `auditoria`); teste prova que alterar um tratamento aprovado e recalcular só o dia afetado
muda **apenas** aquele dia (outros dias do vínculo permanecem com a mesma `versao`) e grava exatamente
uma linha de diff em `auditoria`; teste prova que um dia em período fechado é pulado e contado, sem
abortar os demais dias do intervalo.

### T11 — Golden dataset da F3 executado contra a apuração real
**Agente:** A4
**Descrição:** `apps/api/tests/f4/golden/test_golden_f3_contra_apuracao.py`: importa `CENARIOS` de
`tests.f3.golden.cenarios` (não recria massa nova) e, para cada cenário **sem** `erro_esperado`,
chama `app.apuracao.dominio.servico.apurar_dia(sessao, tenant_id, montagem.vinculo_id,
montagem.data_consulta)` com **zero marcações** inseridas (os cenários da F3 não criam marcações — o
que se prova aqui é que a apuração propaga corretamente os campos derivados da jornada/escala/
feriado/afastamento, não o cálculo de horas trabalhadas, que não tem insumo de marcação nestes
cenários) e compara campo a campo: `apuracoes_dia.tipo_dia` contra `ResolucaoJornada.tipo_dia`
(mapeado 1:1, exceto que o `nao_apurado` desta fase corresponde ao `erro_esperado="PONTO-APUR-002"`
da F3 — ver próximo parágrafo), `jornada_id`, `escala_id`, `turno_id`, `horario_id`, `feriado_id`,
`afastamento_id`, e `previsto_minutos` (derivado de `ResolucaoJornada.carga_prevista_minutos`, quando
o cenário o preenche). Para os cenários **com** `erro_esperado == "PONTO-APUR-002"`, o teste afirma
que `apurar_dia` **não levanta exceção** e produz `apuracoes_dia.tipo_dia == "nao_apurado"` (decisão
fixada na §2). Medir cobertura com `pytest --cov=app.apuracao --cov-report=term-missing`.
**Pronto quando:** `len(CENARIOS) >= 40` (herdado da F3, só confirma que continua verdadeiro);
**100% dos cenários do golden dataset da F3 passam** contra `apurar_dia` real (não contra um duplo);
os cenários de virada de mês do 12x36 e de troca de jornada no meio do mês (já escritos pela F3)
passam sem alteração no arquivo `tests/f3/golden/cenarios.py` (você **não edita** esse arquivo, é
ownership exclusivo e já concluído da F3 — se um campo estiver faltando para o que você precisa
comparar, registre em `docs/backlog.md`, não edite).

### T12 — Testes de propriedade e performance
**Agente:** A4
**Descrição:** Testes de propriedade (`apps/api/tests/f4/propriedade/`): "recalcular o mês inteiro
depois de uma invalidação parcial de um único dia não muda os demais dias" (ADR-004, consequência
negativa (a)); "a soma de `apuracao_componentes.minutos_equivalentes` por categoria bate com os
totais de `apuracoes_dia`" para uma amostra gerada de jornadas/escalas variadas; "a soma de
`bh_lancamentos.minutos_equivalentes` de uma conta é sempre igual a `bh_contas.saldo_atual_minutos`"
sob uma sequência aleatória de créditos/débitos/quitações. Teste de performance
(`apps/api/tests/f4/performance/`): gerar **10.000 vínculos × 31 dias** (dados sintéticos, jornada
fixa simples, sem variação custosa de escala) e medir o tempo de `recalcular_periodo` sobre o
intervalo inteiro — reportar o tempo real no relatório da fase; se rodar em ambiente sem capacidade
para 10.000 × 31 completos em tempo de CI, documente a extrapolação a partir de uma amostra menor
(ex.: 500 vínculos × 31 dias, medido, extrapolado linearmente) e diga isso explicitamente no
relatório — não afirme "deve escalar" sem medir.
**Pronto quando:** as propriedades acima têm teste passando (Hypothesis ou parametrização
equivalente, documentar a escolha); o teste de performance produz um número real de tempo total
para o volume medido, colado no relatório da fase, com a extrapolação (se usada) explicitada como
tal.

### T13 — Fechamento
**Agente:** A1, A2, A3 e A4
**Descrição:** Rodar todos os comandos da §8 e colar a saída real no relatório da fase, item a item
contra a §7.
**Pronto quando:** todos verdes, com saída colada, e `git status --short packages/contracts` mostra
**apenas** `M packages/contracts/schema.sql` (a função da §5), nenhum outro arquivo.

## 7. Critérios de aceite

O relatório final responde item a item, com saída real colada.

1. **CRUD e cálculo conforme o contrato**: as 20 operações das 3 tags deixaram de responder `501`;
   `python tools/conferir_rotas.py` continua dizendo `Inventario identico ao contrato`.
2. **100% do golden dataset da F3 passa** contra `app.apuracao.dominio.servico.apurar_dia` real (não
   contra mock) — os mesmos `tests/f3/golden/cenarios.py`, sem alteração no arquivo.
3. **Recalcular duas vezes o mesmo período, sem mudança de insumo, produz exatamente o mesmo
   resultado**: mesma `versao`, mesmo `hash_entrada`, nenhuma nova linha em `auditoria`, nenhum evento
   publicado na segunda chamada.
4. **Apuração em volume**: o teste de performance (T12) reporta um tempo real medido para o maior
   volume exercitado, com a extrapolação (se houver) explícita, visando o alvo de referência de
   10.000 colaboradores × 31 dias em tempo hábil (`FASES-E-AGENTES.md`, F4: "< 5 min").
5. **Extrato de banco de horas fecha com a soma dos lançamentos**: `bh_contas.saldo_atual_minutos`
   igual à soma de `bh_lancamentos.minutos_equivalentes` em todo cenário testado, incluindo após
   consumo FIFO/LIFO, quitação e estorno.
6. **Alterar regra retroativamente reprocessa só o intervalo afetado e registra o diff**: aprovar um
   tratamento ou alterar um insumo recalcula apenas os dias impactados (comprovado por propriedade em
   T12) e grava exatamente uma linha de diff em `auditoria` por dia que mudou.
7. **Marcação nunca é tocada**: nenhum código desta fase executa `INSERT`/`UPDATE`/`DELETE` em
   `marcacoes` — prova de desenho (grep/análise estática) mais teste que confirma leitura pura.
8. **Extrato e auditoria são imutáveis por execução real**: `UPDATE` direto (fora de
   `consumido_minutos`) e `DELETE` em `bh_lancamentos`, conectado como a role de aplicação (não
   superusuário), falham com `ERRCODE 42501` — evidência colada, não referência a linha de código.
9. **Tratamento nunca afeta o AFD**: `tipos_tratamento.afeta_afd` é sempre `false`, garantido por
   `CHECK` e confirmado por teste que tenta forçar `true` via `INSERT` direto.
10. **Vínculo sem jornada/escala vigente nunca produz 500**: responde com `apuracoes_dia.
    tipo_dia='nao_apurado'` e uma ocorrência aberta, nunca uma exceção não tratada.
11. **Período fechado não recalcula**: tratamento, recálculo e quitação em dia de período fechado
    respondem `PONTO-PER-001`/`PONTO-APUR-003` e nunca escrevem em `apuracoes_dia`/`bh_lancamentos`
    para aquele dia.
12. **`banco_horas.vencendo` é produzido por uma rotina cross-tenant real**, via a função
    `fn_bh_contas_para_verificacao_vencimento()` (RFC-013), comprovada por teste que ela devolve
    contas de tenants diferentes numa única chamada sem `app.tenant_id`.
13. **Toda rota declara `Depends(exigir_permissao(...))`** com exatamente o `x-permissao` do
    contrato — verificável por um teste que percorre o `openapi.yaml` e confere rota a rota.
14. **Eventos publicados batem campo a campo com `events.yaml`**: `ajuste.aprovado`/`reprovado`
    (só com `solicitacaoId` presente), `apuracao.recalculada`, `ocorrencia.aberta`,
    `banco_horas.vencendo`, `banco_horas.quitado`.
15. **Cobertura ≥ 90%** em `app.apuracao` (`--cov=app.apuracao --cov-report=term-missing`), saída
    real colada.
16. **Contrato quase intocado**: `git status --short packages/contracts` mostra somente a função da
    §5 em `schema.sql`; nenhum outro artefato de `packages/contracts` foi tocado.
17. Todos os comandos da §8 verdes, com saída real colada no relatório.

## 8. Comandos de verificação

Rode a partir da **raiz do repositório**, salvo onde indicado. Windows usa `.\tasks.ps1`;
Linux/macOS usa `make`.

Subir o banco:

```bash
docker compose --env-file infra/.env.example -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d postgres redis
```

```powershell
.\tasks.ps1 up
```

Migrar:

```bash
cd apps/api && alembic upgrade head
```

```powershell
cd apps/api; alembic upgrade head
```

Lint, formatação e tipos (versões fixadas no CI: ruff 0.7.4, mypy 1.13.0; `mypy` roda de dentro de
cada diretório de app, sem argumento — RFC-009/§6):

```bash
ruff check apps packages tests
ruff format --check apps packages tests
cd apps/api && mypy
cd apps/worker && mypy
```

```powershell
.\tasks.ps1 lint
.\tasks.ps1 typecheck
```

**Saída esperada:** `All checks passed!`, `NN files already formatted`,
`Success: no issues found in NNN source files`.

Testes da fase, com cobertura do pacote de domínio:

```bash
cd apps/api && pytest tests/f4 -q --cov=app.apuracao --cov-report=term-missing
```

```powershell
cd apps/api; pytest tests/f4 -q --cov=app.apuracao --cov-report=term-missing
```

**Saída esperada:** todos os testes passam; a linha `TOTAL` da cobertura ≥ 90%; nenhum `skip` nos
testes que exigem banco.

Golden dataset da F3 contra a apuração real (o critério de aceite 2):

```bash
cd apps/api && pytest tests/f4/golden -q -v
```

```powershell
cd apps/api; pytest tests/f4/golden -q -v
```

**Saída esperada:** todos os cenários (mesmo total de `tests/f3/golden/cenarios.py`) passam.

Idempotência e imutabilidade, isoladas para evidência no relatório:

```bash
cd apps/api && pytest tests/f4/tratamento -q -k "idempotente or recalculo or diff" -s
```

```bash
cd apps/api && pytest tests/f4/banco_horas -q -k "imutavel or update or delete" -s
```

Performance (o critério de aceite 4):

```bash
cd apps/api && pytest tests/f4/performance -q -s
```

**Saída esperada:** o tempo real medido, impresso no console e colado no relatório.

Regressão do andaime da Fase 0 (não pode quebrar):

```bash
cd apps/api && pytest tests/test_andaime.py -q
```

Inventário de rotas idêntico ao contrato:

```bash
cd apps/api && python tools/conferir_rotas.py
```

**Saída esperada:** `Inventario identico ao contrato (metodo, caminho e operationId).`

Contrato quase intocado (a exceção da §5 é o único diff esperado):

```bash
git status --short packages/contracts
```

**Saída esperada:** apenas `M packages/contracts/schema.sql`.

```bash
git diff packages/contracts/schema.sql
```

**Saída esperada:** diff mostra exclusivamente a criação de
`fn_bh_contas_para_verificacao_vencimento()` e seu `COMMENT ON FUNCTION`; nada além disso.

Migration continua reversível contra banco real:

```bash
cd apps/api && alembic upgrade head && alembic downgrade base && alembic upgrade head
```

## 9. Proibições

1. **Não edite `packages/contracts/`** além da única adição explicitamente autorizada por RFC-013
   (`fn_bh_contas_para_verificacao_vencimento()`, §5). Qualquer outra divergência vira RFC nova em
   `docs/rfc/`, no formato de `docs/rfc/README.md`.
2. **Não crie migration de tabela nova.** As 10 tabelas dos grupos 8 e 9 já existem em
   `0001_inicial.py`; a única alteração de migration permitida é a função da §5.
3. **Não crie código de erro novo.** Se faltar um, é RFC.
4. **Não implemente workflow de aprovação de solicitações** (`solicitacoes`, `aprovacoes`) — é da
   F10. `tratamentos.solicitacao_id` é só uma FK de referência.
5. **Não implemente a API de fechamento de período** (`periodos`, `fechamentos`, `espelhos`) — é da
   F10. Você só lê essas tabelas, nunca escreve, para honrar `PONTO-PER-001`/`PONTO-APUR-003`.
6. **Não implemente relatórios** (F11) nem **AFD/AEJ/assinatura CAdES** (F12). `tipos_tratamento.
   afeta_afd` é sempre `FALSE` — nenhum tratamento gera linha de AFD, ponto final.
7. **Não reescreva `resolver_jornada_do_dia` nem duplique sua lógica de precedência jornada/escala/
   feriado/afastamento.** Importe de `app.jornada.resolvedor.servico`. Se a assinatura não bastar,
   é RFC — não invente um segundo caminho de resolução.
8. **Não escreva em `marcacoes`.** Leitura apenas, sempre.
9. **Não use ponto flutuante no motor de cálculo** (ADR-004, ponto 2). Toda duração é `INTEGER` em
   minutos; fator é `NUMERIC` aplicado sobre inteiro com arredondamento único e documentado.
10. **Não use `ponto_suporte`/`BYPASSRLS` para `verificar_banco_horas_vencendo`.** A RFC-013 já
    decidiu a função `SECURITY DEFINER` como solução definitiva; não reintroduza o padrão interino que
    a F6 usou antes da decisão.
11. **Não invente uma tabela ou endpoint para acompanhar o status de `recalcularApuracoes`.** A
    lacuna (nenhum "obter processamento de recálculo" no contrato) é achado de backlog, não invenção
    sua — a conclusão é observável via `GET /v1/apuracoes` e via `apuracao.recalculada`.
12. **Não invente endpoint que não existe no contrato** — em particular, não adicione
    `excluirTratamento` (é `cancelarTratamento`), `atualizarApuracao`, `atualizarContaBancoHoras`,
    `excluirContaBancoHoras`, `atualizarPoliticaBancoHoras`, `excluirPoliticaBancoHoras`,
    `excluirQuitacaoBancoHoras`. Se a ausência parecer defeito do contrato, é RFC.
13. **Não use os termos proibidos** da seção 6 do glossário: é *marcação* (nunca "batida"),
    *tratamento* (nunca "ajuste de marcação" fora do nome de coluna já existente), *apuração* (nunca
    "cálculo"/"processamento do dia" soltos), *colaborador*/*vínculo* (nunca "funcionário"), *tenant*
    (nunca "empresa" para dizer cliente do SaaS), *saldo credor/devedor* (nunca "banco de horas
    positivo/negativo" como entidade).
14. **Não declare a fase pronta sem rodar os comandos da §8 e colar a saída real.** "Deve funcionar"
    não é evidência — em especial o tempo real de performance (T12) e a saída dos testes de
    imutabilidade/idempotência.
