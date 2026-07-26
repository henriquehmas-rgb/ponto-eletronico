# F03 — Motor de Jornada

| | |
|---|---|
| **Onda** | 2 |
| **Agentes** | 4 · **A1** modelagem (horários, jornadas fixas/flexíveis/livres, escalas cíclicas, turnos) · **A2** calendário (feriados nacional/estadual/municipal, feriados móveis, afastamentos) · **A3** resolvedor (dado vínculo + data, devolve jornada vigente/horário previsto/tipo do dia) · **A4** golden dataset e testes (cenários trabalhistas com resultado esperado, escritos antes do resolvedor existir) |
| **Duração estimada** | 8 dias |
| **Depende de** | F0 (contratos congelados e andaime da API), F2 (tabelas `empresas`, `unidades`, `vinculos`, `colaboradores` povoadas e RLS ativo) |
| **Criticidade** | ⭐ Crítica — "esta é a fase onde projetos de ponto morrem" ([FASES-E-AGENTES.md](../../FASES-E-AGENTES.md), F3). F4, F9b, F10, F11, F12 dependem do resolvedor desta fase para saber o que era esperado em cada dia |
| **Branch** | `f03-motor-de-jornada` |

---

## 1. Objetivo

Ao fim desta fase, **dado um vínculo e uma data, o sistema responde de forma determinística qual
jornada ou escala estava vigente, qual o horário previsto (entrada, saída, intervalos), qual a carga
prevista em minutos e qual o tipo do dia (útil, DSR, folga, feriado, ponto facultativo, afastamento
ou "sem regra")** — via `GET /v1/jornadas/resolver` — enquanto as 35 operações das tags `jornadas`,
`escalas`, `feriados` e `afastamentos` deixam de responder `501` e passam a implementar cadastro
completo de horários, jornadas versionadas por vigência, escalas cíclicas (5x2, 6x1, 4x2, 12x36,
espanhola, rotativa de N dias), turnos com revezamento, calendário de feriados (incluindo os móveis,
calculados a partir da Páscoa) e afastamentos — tudo isso provado por um *golden dataset* de pelo
menos 40 cenários trabalhistas escritos **antes** do código do resolvedor existir, com cobertura
≥ 90 % no pacote `app.jornada`.

**O que esta fase explicitamente não faz:** calcular quantas horas o colaborador trabalhou, quanto é
hora extra, se houve violação de intrajornada, ou o saldo de banco de horas. Isso é o motor de
*apuração*, entregue pela **F4** (Onda 3), que consome o resolvedor desta fase como insumo. Se você
está prestes a escrever uma fórmula de hora extra, adicional noturno ou banco de horas, pare: não é
desta fase (ver §4 e §9).

## 2. Contexto mínimo

**O produto.** Sistema de ponto eletrônico brasileiro **REP-P** (*Registrador Eletrônico de Ponto via
Programa*, Portaria MTP 671/2021), SaaS multi-tenant. Todo dado que você escrever carrega `tenant_id`
e está sob **Row Level Security** do PostgreSQL: a aplicação já abre cada transação publicando
`app.tenant_id` (`apps/api/app/db/sessao.py`, entregue e endurecido pela F1). Você não desabilita RLS
e não resolve tenant por conta própria — isso já está pronto.

**A cadeia que já existe e que você só lê.** A F2 já entregou `empresas` (empregador, com fuso
`empresas.fuso_horario`), `unidades` (local físico, com `unidades.fuso_horario` — que **sobrescreve**
o da empresa e é o fuso **efetivo da apuração**, conforme o **ADR-004**: *"a data civil da apuração é
derivada do fuso da unidade do vínculo, nunca do fuso do servidor nem do cliente"*), `colaboradores`
(a pessoa) e `vinculos` (a relação de trabalho operacional — `vinculos.unidade_id`, nullable, é o elo
entre um vínculo e a unidade cujo fuso e calendário de feriados valem para ele; `vinculos.empresa_id`
é sempre presente). **Todo o motor de jornada pendura em `vinculo_id`, nunca em `colaborador_id`** —
um colaborador pode ter vínculos simultâneos em empresas diferentes, cada um com sua própria jornada.
Você não escreve nessas quatro tabelas; só lê.

**Horário, jornada, turno e escala — quatro conceitos que não podem ser confundidos.** Um **horário**
(`horarios`) é o gabarito mais simples: entrada, saída, intervalo, carga em minutos — um bloco de
montagem, nada mais. Uma **jornada** (`jornadas` + `jornada_dias`) é o conjunto de regras de cálculo
(tolerância, tratamento do noturno, limites de extra, política de intervalo) aplicado a um vínculo,
**versionado por vigência**: trocar a regra no meio do mês não reescreve o passado apurado. Um
**turno** (`turnos`) é um horário nomeado e, quando há revezamento, sequenciado (manhã/tarde/noite).
Uma **escala** (`escalas` + `escala_ciclos`) é um padrão cíclico de trabalho e folga (5x2, 6x1, 4x2,
**12x36**, espanhola, rotativa de N dias) que se repete a partir de uma `data_referencia`, resolvido
por **aritmética modular** — nunca materialize um calendário de anos de escala em linhas de banco.

**A relação entre jornada e escala — decisão desta fase, derivada da forma do schema (não está
escrita em prosa em nenhum lugar; é o que faz o modelo fechar).** `escalas.jornada_id` é uma FK
opcional de escala para jornada: a escala aponta para a jornada que **empresta as regras de cálculo**
(tolerância, fatores de extra, tratamento do noturno) ao regime cíclico. Um vínculo pode estar ligado
a uma jornada por vigência (`vinculo_jornadas`, para os tipos `fixa`, `flexivel`, `livre`, `parcial`,
`intermitente`, `teletrabalho`, `motorista` — o horário previsto do dia vem de `jornada_dias`,
indexado pelo dia da semana) **ou** a uma escala por vigência (`escala_atribuicoes`, para os tipos
`escala` e `12x36` — o horário previsto do dia vem de `escala_ciclos`, indexado pela posição do
ciclo). As duas atribuições não são mutuamente exclusivas no schema (nada impede que um vínculo tenha
as duas ao mesmo tempo), mas a **precedência de resolução fixada neste PCF** é: se há
`escala_atribuicoes` vigente na data, a escala manda (o dia vem do ciclo); senão, se há
`vinculo_jornadas` vigente, a jornada manda (o dia vem de `jornada_dias`); se nenhuma das duas está
vigente, o resultado é `PONTO-APUR-002` (nenhuma regra resolvida). Esta precedência — e as fórmulas
de vigência e de posição de ciclo abaixo — é o contrato entre A1 (que grava as tabelas), A3 (que
resolve) e A4 (que escreve o *golden dataset* antes do resolvedor existir): os três precisam seguir
exatamente o mesmo algoritmo, ou o dataset e o código nunca vão bater.

**Fórmula de vigência (idêntica para `vinculo_jornadas` e `escala_atribuicoes`).** Ambas as tabelas
têm uma constraint `EXCLUDE USING gist` que impede vigências sobrepostas para o mesmo vínculo — então
a consulta `WHERE vinculo_id = :v AND vigencia_inicio <= :data AND (vigencia_fim IS NULL OR
vigencia_fim >= :data)` devolve **no máximo uma linha**. Trocar a jornada ou a escala no meio do mês
significa encerrar a atribuição anterior (`vigencia_fim`) e criar a próxima (`vigencia_inicio` no dia
seguinte); o passado já apurado nunca é reescrito porque a consulta acima, para uma data passada,
continua devolvendo a atribuição que valia naquele dia.

**Fórmula de posição do ciclo (o coração do 12x36 e das escalas rotativas).** Dada uma
`escala_atribuicoes` vigente com `vigencia_inicio` e `posicao_inicial`, e uma `escalas.dias_ciclo`:

```
dias_desde_inicio = (data - atribuicao.vigencia_inicio).dias
posicao = ((dias_desde_inicio + atribuicao.posicao_inicial - 1) mod escala.dias_ciclo) + 1
```

Em `data == atribuicao.vigencia_inicio`, `posicao == posicao_inicial` (verificação de sanidade). O
resultado de `posicao` indexa `escala_ciclos.posicao` para aquela escala, que devolve `tipo_dia`
(`trabalho`/`folga`/`dsr`/`compensado`) e `turno_id` (→ `turnos.horario_id` → `horarios`). Use
aritmética inteira de datas (`date - date` em dias, módulo inteiro); a divisão/módulo do Python já
devolve resultado não negativo para módulo positivo mesmo com dividendo negativo — não precisa de
tratamento especial para datas antes de `vigencia_inicio` (que de todo modo a consulta de vigência já
exclui). Este é exatamente o cálculo que a virada de mês do 12x36 exercita: não há nada de especial em
cruzar dia 31/01 → 01/02, porque a aritmética é sobre a diferença de dias, não sobre dia-do-mês.

**Mapeamento de `tipo_dia` para o `tipoDia` da resposta.** `jornada_dias.tipo_dia` usa
`util|dsr|folga|compensado|facultativo`; `escala_ciclos.tipo_dia` usa
`trabalho|folga|dsr|compensado`; a resposta `ResolucaoJornada.tipoDia` usa
`util|dsr|folga|feriado|ponto_facultativo|afastamento|compensado|nao_apurado`. O mapeamento fixado
neste PCF: `escala_ciclos.tipo_dia = 'trabalho'` → `tipoDia = 'util'`; `jornada_dias.tipo_dia =
'facultativo'` → `tipoDia = 'ponto_facultativo'`; os demais valores (`dsr`, `folga`, `compensado`)
correspondem 1:1 pelo nome. `nao_apurado` não é produzido por este PCF (não há caso de uso aqui que o
gere; fica reservado para a F4).

**Como feriado e afastamento entram por cima da jornada/escala resolvida — precedência fixada.**
Depois de resolver a jornada **ou** a escala do dia (parágrafo acima), verifique, nesta ordem: (1)
existe `afastamentos` com `status = 'aprovado'`, `periodo_parcial = false`, cobrindo a data, para o
`colaborador_id` do vínculo? Se sim, `tipoDia = 'afastamento'`, `origem = 'afastamento'`,
`afastamentoId` preenchido. (2) Senão, existe feriado aplicável à unidade do vínculo nesta data (via
`unidade_feriado_conjuntos` → `feriado_conjuntos` → `feriados`, resolvendo os móveis pelo ano da
`data` consultada)? Se sim, `tipoDia` vem de `feriados.tipo` (`feriado` → `'feriado'`,
`ponto_facultativo` → `'ponto_facultativo'`; os demais tipos do catálogo — `data_comemorativa`,
`compensado` — não sobrescrevem o tipo do dia, só ficam disponíveis via `feriadoId`/`feriadoNome`),
`origem = 'feriado'`; se `feriados.integral = false`, `cargaPrevistaMinutos` desta resposta usa
`feriados.carga_reduzida_minutos` no lugar da carga da jornada/escala. (3) Senão, o `tipoDia` e a
`origem` (`'jornada'` ou `'escala'`) vêm do que foi resolvido no parágrafo anterior.
`jornadaId`/`escalaId`/`turnoId`/`horarioId`/`entradaPrevista`/`saidaPrevista` **sempre** refletem o
que a jornada/escala previa para o dia, mesmo quando `origem` é `'feriado'` ou `'afastamento'` — é o
que permite ao consumidor da F4 saber tanto "o que era esperado" quanto "por que não vale hoje".
`PONTO-APUR-002` só é levantado quando **nem** jornada **nem** escala resolveram (passo anterior ao
(1)); a presença de feriado ou afastamento sozinha nunca basta para produzir uma resposta sem jornada
de base.

**Feriados móveis — fórmula fixada, sem ponto flutuante.** `feriados.movel = true` exige
`regra_movel` (`pascoa|carnaval|sexta_santa|corpus_christi|quarta_cinzas|custom`) e a data efetiva é
`ancora(regra_movel, ano) + offset_dias`. As âncoras, relativas ao domingo de Páscoa do `ano`
consultado (calculado por um algoritmo determinístico e inteiro, por exemplo o algoritmo gregoriano
anônimo de Meeus/Jones/Butcher — **não** use bibliotecas de calendário litúrgico de terceiros só para
isto, é aritmética de poucas linhas e testável por si): `pascoa` = a própria data da Páscoa;
`carnaval` (terça-feira) = Páscoa − 47 dias; `quarta_cinzas` = Páscoa − 46 dias; `sexta_santa` =
Páscoa − 2 dias; `corpus_christi` = Páscoa + 60 dias; `custom` = Páscoa (o `offset_dias`, então,
**é obrigatório na prática** para `custom` — sem ele o feriado cairia em cima da própria Páscoa, o
que quase nunca é a intenção; valide isso como `PONTO-VAL-001` na criação). `offset_dias` se soma a
qualquer uma das âncoras acima, inclusive `pascoa`. Feriado fixo (`movel = false`) exige `data`;
`ano` ausente faz o feriado repetir todo ano, presente restringe a um ano específico (vale tanto para
fixo quanto para móvel, embora o caso comum de móvel seja `ano` ausente).

**Feriado municipal só vale na unidade certa — o motivo de `unidade_feriado_conjuntos` existir.** Um
`feriado_conjunto` tem `abrangencia` (`nacional|estadual|municipal|empresa|unidade`) mas **não** se
aplica a nenhuma unidade automaticamente por essa abrangência sozinha: a associação **explícita**
`unidade_feriado_conjuntos (unidade_id, feriado_conjunto_id)` é o que liga um conjunto a uma unidade,
inclusive para conjuntos de abrangência `nacional` (toda unidade precisa ser explicitamente associada
ao conjunto nacional do tenant) ou `empresa` (mesma regra: associe às unidades daquela empresa, uma a
uma). Isso é deliberado — é o que garante que o feriado municipal de Uberlândia não vaze para a
unidade de Belo Horizonte mesmo que as duas pertençam à mesma empresa. `vinculos.unidade_id` é
**opcional** no schema: quando nulo, não há unidade para resolver fuso efetivo nem feriados por
unidade. A decisão adotada neste PCF (não há orientação em prosa em nenhum contrato para este caso):
sem `unidade_id`, use `empresas.fuso_horario` do vínculo como fuso efetivo e trate o vínculo como sem
nenhum `feriado_conjunto` aplicável (nenhuma linha de `unidade_feriado_conjuntos` a considerar) —
documente esta escolha no código do resolvedor exatamente com esta frase, para que ninguém a
redescubra por tentativa e erro.

**Afastamento é insumo, nunca marcação.** `afastamentos` (férias, atestado, licença, INSS, suspensão
— catálogo completo em `tipos_afastamento`) entra na apuração como insumo desta fase; **não** grava
`marcacoes` e **não** é corrigido por `tratamentos` (essa camada é de outra fase). A constraint
`ex_afastamentos_sobreposicao` impede dois afastamentos **integrais aprovados** sobrepostos do mesmo
colaborador (`periodo_parcial = false`); afastamentos parciais (algumas horas do dia, ex. atestado de
consulta médica) ficam fora dessa regra por natureza — podem coexistir. `afastamentos.cid` é dado de
saúde: toda leitura deve gerar linha em `acessos_dados_sensiveis`, exatamente como a F1/F2 fazem para
outros campos sensíveis (`Depends(exigir_permissao(...))` já cuida disso sozinho quando a permissão
exercida é sensível — ver `apps/api/app/core/seguranca.py`, você só precisa declarar a permissão
certa na rota).

**O catálogo de permissões já está completo para esta fase.** A F1 (Onda 1, já concluída) semeou em
`migrations/seed_dev.py` as permissões `horarios.*`, `jornadas.*`, `turnos.*`, `escalas.*`,
`feriados.*`, `afastamentos.*` e `tipos_afastamento.{ler,criar,editar}` com as quatro ações CRUD
completas. Você **não** precisa completar catálogo nenhum: declare
`Depends(exigir_permissao("<x-permissao exato do openapi.yaml>"))` em toda rota e a autorização já
funciona de ponta a ponta.

**O que esta fase não resolve, mesmo parecendo próximo.** `PONTO-PER-001` (período fechado) está
listado como erro possível em `atribuirJornadaVinculo`, `atribuirEscalaVinculo` e
`atualizarAfastamento` — as tabelas `periodos`/`fechamentos` já existem no schema (criadas pela F0),
mas a **API** de fechamento é da F10 (Onda 4, ainda não construída). Implemente a consulta somente
leitura (nunca escreva nessas tabelas) que verificaria um fechamento com `status = 'fechado'`
cobrindo a data e o escopo do vínculo (empresa sempre, unidade/departamento quando o fechamento for
desse escopo); como nenhuma fase anterior a esta popula `fechamentos`, a consulta nunca encontra nada
hoje — mas o código precisa estar correto para quando a F10 existir. Não invente um mecanismo de
"agendar recálculo" ao excluir um afastamento (a descrição de `excluirAfastamento` no contrato
menciona isso, mas não existe evento em `events.yaml` nem fila para isso — é lacuna do contrato, não
sua: registre em `docs/backlog.md`, não implemente um evento novo).

## 3. Leituras obrigatórias (lista fechada)

Leia isto e pare. Não leia `PROJETO.md`, não leia outras fases, não leia o código de F1/F2/F5/F6.

- `packages/contracts/openapi.yaml` — **apenas** as tags `jornadas` (11 operações: `/v1/horarios`,
  `/v1/jornadas`, `/v1/jornadas/{jornadaId}`, `/v1/vinculos/{vinculoId}/jornadas`,
  `/v1/jornadas/resolver`), `escalas` (9 operações: `/v1/escalas`, `/v1/escalas/{escalaId}`,
  `/v1/escalas/{escalaId}/atribuicoes`, `/v1/turnos`, `/v1/turnos/{turnoId}`), `feriados` (7
  operações: `/v1/feriado-conjuntos`, `/v1/feriado-conjuntos/{conjuntoId}`, `/v1/feriados`,
  `/v1/feriados/{feriadoId}`) e `afastamentos` (8 operações: `/v1/tipos-afastamento`,
  `/v1/tipos-afastamento/{tipoId}`, `/v1/afastamentos`, `/v1/afastamentos/{afastamentoId}`). Preste
  atenção a quais operações **não** existem: não há `obterHorario`, nem `excluirHorario`, nem
  `excluirTurno`/`obterTurno`, nem `obterFeriado`/`atualizarFeriado`, nem
  `obterTipoAfastamento`/`excluirTipoAfastamento`, nem uma listagem de histórico de
  `escala_atribuicoes` por vínculo — o contrato deliberadamente não os tem; não os invente. Leia
  também, em `components`: `parameters` (`CabecalhoTenant`, `CabecalhoRequestId`,
  `CabecalhoIdempotencia`, `Cursor`, `Limite`, `Ordenar`), `responses` (`Erro400`..`Erro429`), o
  schema `Problema` e os schemas `Horario*`, `Jornada*`, `JornadaDia`, `VinculoJornada*`, `Turno*`,
  `Escala*`, `EscalaCiclo`, `EscalaAtribuicao*`, `FeriadoConjunto*`, `Feriado*`, `TipoAfastamento*`,
  `Afastamento*` e `ResolucaoJornada`.
- `packages/contracts/schema.sql` — seção **7 (JORNADA, ESCALA E CALENDARIO)** por inteiro (linhas
  1362–1783). Tabelas: `horarios`, `jornadas`, `jornada_dias`, `turnos`, `escalas`, `escala_ciclos`,
  `escala_atribuicoes`, `vinculo_jornadas`, `feriado_conjuntos`, `feriados`,
  `unidade_feriado_conjuntos`, `tipos_afastamento`, `afastamentos` (as 13 tabelas do grupo). Leia
  também, na seção 1 (domínios), `dom_uf`, `dom_ibge`, `dom_fuso`; e, só para saber o que existe e
  não escrever nelas, as definições de `empresas`, `unidades` (seção 3) e `vinculos` (seção 5,
  linhas 929–974) — você lê `fuso_horario` e `unidade_id`/`empresa_id`/`colaborador_id` dessas
  tabelas, nunca escreve.
- `packages/contracts/models/jornada.py` — modelos SQLAlchemy das 13 tabelas acima.
  `packages/contracts/models/organizacao.py` (apenas `Empresa`, `Unidade`) e `models/pessoas.py`
  (apenas `Vinculo`, `Colaborador`) — só para relacionar via ORM, sem editar.
  `packages/contracts/models/base.py`, `models/mixins.py`, `models/tipos.py`.
- `packages/contracts/errors.yaml` — categorias **VAL** (use os códigos 001, 005, 006, 007, 010,
  011), **CONF** (001, 002, 003, 004), **REC** (001), **APUR** (apenas 002 — os demais códigos de
  APUR são de fechamento/recálculo, da F4), **PER** (apenas 001), e os transversais **AUTH-002,
  003, 004, 006, 013**, **PERM-001, 002, 004**, **TEN-002, 003, 004**, **IDEM-001..003**,
  **RATE-001**, **INT-001, 003, 005**.
- `packages/contracts/events.yaml` — confirme que **nenhum** evento tem origem nesta fase (não há
  `jornada.*`, `escala.*`, `feriado.*` nem `afastamento.*` no catálogo). Não publique evento
  nenhum.
- `packages/contracts/glossario.md` — seções **1**, **1.1 (Isolamento por Row Level Security)**;
  verbetes **Adicional noturno**, **Afastamento**, **DSR**, **Escala**, **Feriado**, **Horário**,
  **Hora ficta**, **Interjornada**, **Intrajornada**, **Jornada**, **Tolerância**, **Turno**,
  **Vínculo**, **Soft delete**; seção **3.1** (linha sobre `unidade_feriado_conjuntos` e
  `vinculo_jornadas`); seção **5 (Sequência canônica do motor)** — leia com atenção: a seta nunca
  aponta para trás, e o que fica **acima** de "tratamentos aplicáveis" no diagrama é seu; o que
  fica abaixo (apuração, banco de horas, fechamento) não é; seção **6 (Termos proibidos)**.
- `docs/adr/ADR-004-recalculo-determinista-idempotente.md` — leia por inteiro. Não implementa nada
  dele (é F4), mas fixa que "a data civil da apuração é derivada do fuso da unidade do vínculo" e
  que o *golden dataset* desta fase (A4) é o mesmo que vira critério de pronto da F4 — por isso o
  formato que A4 escolher precisa ser reutilizável, não descartável.
- `docs/adr/ADR-001-multi-tenancy-row-level-security.md` — só para entender por que toda consulta
  sua já vem filtrada pelo banco e por que você não desabilita RLS.
- `apps/api/app/core/seguranca.py`, `apps/api/app/db/sessao.py`, `apps/api/app/core/erros.py` — o
  andaime pronto (RBAC real, `Sujeito`, `exigir_permissao`, `tenant_id_ou_erro`, `SessaoDb`,
  `ErroDeAplicacao`). Já implementados pela F1; você só usa.
- `apps/api/app/routers/jornadas.py`, `apps/api/app/routers/escalas.py`,
  `apps/api/app/routers/feriados.py`, `apps/api/app/routers/afastamentos.py` — os *stubs* gerados
  pela Fase 0 que você vai preencher (hoje respondem `501` com `PONTO-INT-005`). Leia como exemplo
  de assinatura de handler, parâmetros e tipo de retorno — não regere estes arquivos à mão.
- `apps/api/app/routers/contratos.py` — exemplo **vivo** de um router já implementado (F2) sobre
  este mesmo andaime: como abrir sessão, checar permissão, montar paginação, devolver o schema
  Pydantic gerado. Seu router segue exatamente este padrão.
- `apps/api/app/schemas/contrato.py` (gerado) — apenas para confirmar que os modelos Pydantic
  `Horario`, `Jornada`, `JornadaDia`, `VinculoJornada`, `Turno`, `Escala`, `EscalaCiclo`,
  `EscalaAtribuicao`, `FeriadoConjunto`, `Feriado`, `TipoAfastamento`, `Afastamento` e
  `ResolucaoJornada` (e as variantes `*Criar`/`*Atualizar`/`Lista*`) já existem — não os edite, é
  gerado.
- `apps/api/migrations/seed_dev.py` — apenas para confirmar que as permissões `horarios.*`,
  `jornadas.*`, `turnos.*`, `escalas.*`, `feriados.*`, `afastamentos.*` e
  `tipos_afastamento.{ler,criar,editar}` já estão semeadas (procure `CATALOGO_PERMISSOES`). **Você
  não edita este arquivo.**
- `docs/rfc/README.md` e `docs/backlog.md` — protocolo de RFC e onde anotar achados fora do escopo.

## 4. Contratos

**Consome** — já existe, esta fase apenas usa:

- Tabelas `empresas`, `unidades` (com `fuso_horario`, `codigo_ibge_municipio`, `uf`), `vinculos`
  (com `unidade_id`, `empresa_id`, `colaborador_id`), `colaboradores` — todas da **F2**, sob RLS.
- Andaime da API: `app/core/erros.py`, `app/core/catalogo_erros.py`, `app/core/contexto.py`,
  `app/core/seguranca.py` (`Sujeito`, `exigir_permissao`, `exigir_alcance`, `tenant_id_ou_erro` —
  implementação real, não *stub*), `app/db/sessao.py` (`SessaoDb`), modelos Pydantic gerados em
  `app/schemas/contrato.py`.
- Modelos SQLAlchemy do pacote `ponto_contracts` (`models/jornada.py` e os que você só lê).
- Catálogo de permissões já semeado por `migrations/seed_dev.py` (F1) — `horarios.*`, `jornadas.*`,
  `turnos.*`, `escalas.*`, `feriados.*`, `afastamentos.*`, `tipos_afastamento.{ler,criar,editar}`.
- `apps/api/app/routers/__init__.py` — **já registra** os quatro roteadores (`jornadas`, `escalas`,
  `feriados`, `afastamentos`) na ordem correta. Você não toca neste arquivo.

**Produz** — esta fase implementa:

*Endpoints (35 operações; hoje `501`):*

| Tag | Operações |
|---|---|
| `jornadas` (11) | `listarHorarios`, `criarHorario`, `atualizarHorario`, `listarJornadas`, `criarJornada`, `obterJornada`, `atualizarJornada`, `excluirJornada`, `listarJornadasVinculo`, `atribuirJornadaVinculo`, `resolverJornadaDoDia` |
| `escalas` (9) | `listarEscalas`, `criarEscala`, `obterEscala`, `atualizarEscala`, `excluirEscala`, `atribuirEscalaVinculo`, `listarTurnos`, `criarTurno`, `atualizarTurno` |
| `feriados` (7) | `listarFeriadoConjuntos`, `criarFeriadoConjunto`, `atualizarFeriadoConjunto`, `excluirFeriadoConjunto`, `listarFeriados`, `criarFeriado`, `excluirFeriado` |
| `afastamentos` (8) | `listarTiposAfastamento`, `criarTipoAfastamento`, `atualizarTipoAfastamento`, `listarAfastamentos`, `criarAfastamento`, `obterAfastamento`, `atualizarAfastamento`, `excluirAfastamento` |

A permissão exigida por operação é o valor de `x-permissao` no `openapi.yaml`
(`horarios.criar`, `jornadas.editar`, `escalas.excluir`, `turnos.criar`, `feriados.ler`,
`tipos_afastamento.editar`, `afastamentos.criar`, …). Use exatamente esse valor.

*Tabelas escritas:* `horarios`, `jornadas`, `jornada_dias`, `turnos`, `escalas`, `escala_ciclos`,
`escala_atribuicoes`, `vinculo_jornadas`, `feriado_conjuntos`, `feriados`,
`unidade_feriado_conjuntos`, `tipos_afastamento`, `afastamentos` — as 13 tabelas do grupo 6
(Jornada e calendário) do glossário. Leitura apenas (nunca escrita) em `empresas`, `unidades`,
`vinculos`, `colaboradores`.

*Módulo interno publicado para outras fases:* `app.jornada.resolvedor.servico.resolver_jornada_do_dia`
— função assíncrona `(sessao, tenant_id, vinculo_id, data) -> ResolucaoJornada` (o schema Pydantic
gerado, não um tipo novo), que levanta `ErroDeAplicacao("PONTO-APUR-002", ...)` quando não há
jornada nem escala vigente. É esta função que `GET /v1/jornadas/resolver` chama, e é esta função que
o *golden dataset* de A4 chama diretamente (sem passar pela camada HTTP) para comparar contra o
resultado esperado. **Assinatura fixada por este PCF** — se mudar, atualize os três usos (rota, A4,
qualquer teste) no mesmo commit.

*Eventos publicados:* **nenhum.** Confirmado em `events.yaml`: nenhum evento tem origem nesta fase.

**Não toca** — é de outra fase, mesmo que pareça relacionado:

- **Cálculo de horas, hora extra, adicional noturno, intrajornada/interjornada, DSR, faltas e
  banco de horas** — tudo isso é a **F4** (Onda 3). Esta fase resolve "qual é a jornada esperada
  deste vínculo nesta data", nunca "quantas horas ele trabalhou" ou "quanto é devido". As colunas
  de configuração de cálculo em `jornadas` (`tolerancia_marcacao_minutos`,
  `tolerancia_diaria_minutos`, `fatores_extra`, `hora_ficta_noturna`, `limite_extra_diario_minutos`,
  etc.) são **gravadas e expostas** por você — a F4 é quem as **lê para calcular**.
- Tags `marcacoes`, `comprovantes`, `tratamentos`, `apuracoes`, `banco-horas`, `solicitacoes`,
  `aprovacoes`, `fechamentos`, `espelhos`, `relatorios`, `fiscal` e as tabelas correspondentes —
  todas de fases posteriores (F4, F5, F10, F11, F12).
- A **API** de fechamento de período (`periodos`, `fechamentos`, tag ausente do seu escopo) é da
  **F10**. Você só faz uma consulta de leitura a essas duas tabelas para honrar `PONTO-PER-001` nas
  três operações que o exigem (§2, último parágrafo) — nunca escreve nelas.
- `criarDelegacao`/`listarDelegacoes`, tabelas de identidade/RBAC/auditoria — **F1**, já concluída.
- `empresas`, `unidades`, `colaboradores`, `contratos`, `vinculos`, `biometria`, `dispositivos` —
  **F2**, já concluída. Você lê `empresas`, `unidades`, `vinculos`, `colaboradores`; não escreve.
- Tag `terminais` — **F6**, rodando em paralelo nesta onda.
- `packages/contracts/**` — **congelado**.
- `apps/web`, `apps/mobile`, `apps/worker`, `apps/device-gw`, `apps/facial-svc`.

## 5. Ownership de arquivos

Caminhos **exclusivos** desta fase. **F3, F5 e F6 rodam em paralelo** nesta onda; nenhuma outra fase
escreve aqui, e você não escreve fora daqui.

| Agente | Caminhos |
|---|---|
| **A1** (modelagem) | `apps/api/app/jornada/modelagem/**`<br>`apps/api/app/routers/escalas.py`<br>`apps/api/tests/f3/modelagem/**` |
| **A2** (calendário) | `apps/api/app/jornada/calendario/**`<br>`apps/api/app/routers/feriados.py`<br>`apps/api/app/routers/afastamentos.py`<br>`apps/api/tests/f3/calendario/**` |
| **A3** (resolvedor) | `apps/api/app/jornada/resolvedor/**`<br>`apps/api/tests/f3/resolvedor/**` |
| **A4** (golden dataset e testes) | `apps/api/tests/f3/conftest.py`<br>`apps/api/tests/f3/golden/**` |

`apps/api/app/routers/jornadas.py` é **compartilhado entre A1 e A3** porque a tag `jornadas` mistura
as duas responsabilidades (ver tabela abaixo).

**Compartilhado dentro da fase** (exige combinação entre os agentes da fase):

| Caminho | Regra |
|---|---|
| `apps/api/app/jornada/__init__.py` | Criado por **A1** na T2 (primeira tarefa de código da fase — T1 é só fixture/formato, sem código de aplicação), com uma docstring e nada mais. Ninguém acrescenta código aqui. |
| `apps/api/app/routers/jornadas.py` | **A1** implementa as 10 operações de horários/jornadas/vínculo-jornada (`listarHorarios` até `atribuirJornadaVinculo`) e deixa o handler de `resolverJornadaDoDia` como está (stub `501`) até terminar sua T4. **A3** adiciona só o corpo do handler de `resolverJornadaDoDia` (chamando `app.jornada.resolvedor.servico.resolver_jornada_do_dia`) na T7, depois que A1 e A2 entregarem. Ninguém edita a parte do outro depois de entregue — se precisar mudar algo do lado do outro agente, peça, não edite direto. |
| `apps/api/tests/f3/conftest.py` | Só **A4** edita (T1). É onde nasce a fixture com tenant + empresa + duas unidades em municípios diferentes (uma delas com feriado municipal próprio) + vínculos de teste. A1, A2 e A3 **usam** a fixture nos seus próprios testes; não editam este arquivo — se precisarem de um dado a mais na fixture, pedem a A4. |

**Compartilhado com outras fases da Onda 2 (F5, F6) — atenção, risco real de colisão:**

| Caminho | Regra de convivência |
|---|---|
| `apps/api/pyproject.toml` | Se precisar de dependência nova (não deveria: o cálculo de Páscoa e a aritmética de ciclo são poucas linhas de Python puro, sem biblioteca), acrescente **apenas dentro do seu bloco**, delimitado por `# --- F3 ---` e `# --- fim F3 ---` na lista `dependencies`, criando o bloco no fim da lista se não existir. **Nunca reordene, remova ou reformate linha existente, nem toque nos blocos de F1/F2/F5/F6.** Confira antes se a dependência já está declarada em outro bloco. |

**Explicitamente fora do seu ownership** (não edite, nem "só para arrumar"):
`packages/contracts/**`, `apps/api/app/schemas/contrato.py` (gerado),
`apps/api/app/core/catalogo_erros.py`, `apps/api/app/core/erros.py`, `apps/api/app/core/seguranca.py`,
`apps/api/app/core/middleware.py`, `apps/api/app/db/sessao.py`, `apps/api/app/main.py`,
`apps/api/app/routers/__init__.py` (já registra seus quatro roteadores — nada a fazer aqui),
`apps/api/migrations/**` (inclusive `seed_dev.py`), `apps/api/tests/test_andaime.py`,
`apps/api/app/routers/{auth,tenants,admin,auditoria,empresas,unidades,organizacao,colaboradores,contratos,biometria,dispositivos,terminais}.py`,
`.github/workflows/**`, `infra/**`, `Makefile`, `tasks.ps1`, `apps/web/**`.

> **Nenhuma migration nova nesta fase.** `0001_inicial.py` já cria as 13 tabelas do grupo Jornada e
> calendário, seus índices, `CHECK`s e `EXCLUDE`s. Se você achar que precisa de uma migration, o
> contrato está errado: abra RFC.

## 6. Tarefas (T1..T9)

### T1 — Fixture da fase e formato do golden dataset
**Agente:** A4 — **primeira tarefa da fase, nada começa antes**
**Descrição:** Criar `apps/api/tests/f3/conftest.py` com uma fixture que sobe PostgreSQL 16 (via
`docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml`), aplica
`alembic upgrade head`, conecta como a role `ponto_app` (nunca superusuário) e semeia: 1 tenant, 1
empresa, **duas unidades** em municípios diferentes de UFs diferentes (para testar que feriado
municipal não vaza — ver T8), 2+ colaboradores e 2+ vínculos (um por unidade, com `apura_ponto =
true`). Definir, em `apps/api/tests/f3/golden/`, o **formato** do cenário do *golden dataset*: um
cenário é (nome, descrição da massa de dados necessária — jornada/escala/turno/feriados/afastamentos
a criar —, vínculo alvo, data consultada, resultado `ResolucaoJornada` esperado campo a campo). Este
formato é o que A1/A2/A3 devem conseguir ler para saber o que o resolvedor precisa produzir; não é
código de cálculo, é dado.
**Pronto quando:** `pytest apps/api/tests/f3 -q` coleta e a fixture sobe e derruba o banco sem erro;
existe um documento ou módulo Python com o formato do cenário e pelo menos 1 exemplo preenchido à
mão (o restante dos 40+ vem na T8).

### T2 — Horários e jornadas fixas, flexíveis, livres e demais tipos não cíclicos
**Agente:** A1
**Descrição:** CRUD de `horarios` (`listarHorarios`, `criarHorario`, `atualizarHorario` — note que
**não existe** `obterHorario` nem `excluirHorario` no contrato) e de `jornadas`
(`listarJornadas`, `criarJornada`, `obterJornada`, `atualizarJornada`, `excluirJornada`), incluindo o
array `dias` (→ `jornada_dias`) embutido no corpo de criação/atualização. Cobre os tipos `fixa`,
`flexivel`, `livre`, `parcial`, `intermitente`, `teletrabalho`, `motorista` (todos usam
`jornada_dias`; nenhum destes tipos precisa de tratamento especial de código além de gravar o `tipo`
correto — as diferenças de regra de cálculo entre eles são configuração para a F4 ler, não lógica sua).
Validar `cruza_meia_noite` em `horarios` (saída menor que entrada) e `ck_jornadas_vigencia`. Soft
delete (`excluido_em`/`excluido_por`) com `PONTO-CONF-004` para jornada em uso (referenciada por
`vinculo_jornadas` ou `escalas.jornada_id`).
**Pronto quando:** teste prova que `criarHorario` com `saida < entrada` sem `cruzaMeiaNoite = true` é
recusado (`PONTO-VAL-001`); teste prova que dois horários com o mesmo `codigo` na mesma empresa
colidem em `uq_horarios_codigo` (`PONTO-CONF-001`); teste prova que duas jornadas com o mesmo
`codigo` e a mesma `vigenciaInicio` colidem (`uq_jornadas_codigo`, `PONTO-CONF-001`) mas a mesma
`codigo` com `vigenciaInicio` diferente é aceita (é assim que a jornada versiona).

### T3 — Escalas cíclicas e turnos com revezamento
**Agente:** A1
**Descrição:** CRUD de `turnos` (`listarTurnos`, `criarTurno`, `atualizarTurno` — **não existem**
`obterTurno` nem `excluirTurno`) e de `escalas` (`listarEscalas`, `criarEscala`, `obterEscala`,
`atualizarEscala`, `excluirEscala`), incluindo o array `ciclos` (→ `escala_ciclos`) embutido no
corpo. Cobrir 5x2 (`dias_ciclo = 7`), 6x1 (`dias_ciclo = 7`), 4x2 (`dias_ciclo = 6`), 12x36
(`dias_ciclo = 2`), espanhola e rotativa de N dias (`dias_ciclo` livre). Validar que toda posição de
1 até `dias_ciclo` está coberta em `ciclos`, sem posição duplicada nem faltante (`PONTO-VAL-001` se
não estiver). Implementar e expor como função pura testável a fórmula de posição do ciclo da §2
(`posicao_do_ciclo(escala, atribuicao, data) -> int`), reaproveitada pela T4 e pela T7 (A3 importa,
nunca edita).
**Pronto quando:** teste de mesa cobre 5x2, 6x1, 4x2, 12x36 e uma rotativa de N dias com resultado
esperado explícito por posição; teste prova que faltar uma posição do ciclo no corpo de criação é
recusado.

### T4 — Atribuição de jornada e de escala ao vínculo, respeitando vigência
**Agente:** A1
**Descrição:** `listarJornadasVinculo`/`atribuirJornadaVinculo` (sobre `vinculo_jornadas`) e
`atribuirEscalaVinculo` (sobre `escala_atribuicoes`, único verbo desta subrota — não existe listagem
de histórico de atribuição de escala no contrato). Vigência sobreposta responde `PONTO-VAL-010`
(a constraint `EXCLUDE` do banco já impõe isso; seu código traduz a violação para o código do
catálogo). Implemente a consulta somente leitura de `PONTO-PER-001` descrita na §2 (JOIN
`periodos`/`fechamentos`, nunca escreva nessas tabelas) nas duas operações de atribuição.
**Pronto quando:** teste prova que atribuir uma segunda jornada ao mesmo vínculo com vigência
sobreposta à primeira é recusado (`PONTO-VAL-010`) e que encerrar a primeira (`vigenciaFim`) antes
libera a atribuição seguinte; teste prova que a consulta de fechamento não derruba a operação
quando não há nenhum `fechamentos` na base (caminho hoje sempre verdadeiro nesta fase).

### T5 — Feriados: conjuntos, fixos e móveis, associação por unidade
**Agente:** A2
**Descrição:** CRUD de `feriado_conjuntos` (`listarFeriadoConjuntos`, `criarFeriadoConjunto`,
`atualizarFeriadoConjunto`, `excluirFeriadoConjunto`) e de `feriados` (`listarFeriados`,
`criarFeriado`, `excluirFeriado` — **não existem** `obterFeriado` nem `atualizarFeriado`; correção de
um feriado é excluir e recriar). Implementar a função pura `resolver_ancora_movel(regra_movel, ano,
offset_dias) -> date` com as fórmulas fixadas na §2 (Páscoa via algoritmo determinístico e inteiro),
usada tanto na criação (para devolver `dataResolvida`) quanto em `listarFeriados` quando os
parâmetros `unidadeId`/`ano` são informados. Implementar `ck_feriado_conjuntos_abrangencia` (UF
obrigatória para `estadual`, IBGE obrigatório para `municipal`) e `ck_feriados_definicao`/
`ck_feriados_parcial` no nível de validação de aplicação também (mensagem melhor que o `CHECK` cru).
CRUD de `unidade_feriado_conjuntos` acontece implicitamente através de um campo `unidadeIds` no
corpo de `FeriadoConjunto` (ver schema) — trate a lista enviada como o estado desejado da associação
(insere o que falta, remove o que sobra), nunca deixando uma unidade "órfã" de conjunto nacional por
omissão silenciosa do consumidor da API (documente essa semântica no código).
**Pronto quando:** teste de mesa cobre as cinco âncoras móveis (`pascoa`, `carnaval`, `sexta_santa`,
`corpus_christi`, `quarta_cinzas`) para pelo menos dois anos diferentes, com data esperada calculada
à mão e conferida contra calendário oficial; teste prova que um feriado municipal associado só à
unidade A não aparece em `listarFeriados?unidadeId=<B>`.

### T6 — Afastamentos: catálogo de tipos e períodos do colaborador
**Agente:** A2
**Descrição:** CRUD de `tipos_afastamento` (`listarTiposAfastamento`, `criarTipoAfastamento`,
`atualizarTipoAfastamento` — **não existem** `obterTipoAfastamento` nem `excluirTipoAfastamento`) e
de `afastamentos` (`listarAfastamentos`, `criarAfastamento`, `obterAfastamento`,
`atualizarAfastamento`, `excluirAfastamento`). Validar `ck_afastamentos_periodo`,
`ck_afastamentos_parcial` (parcial exige `horaInicio`/`horaFim`) e a constraint `EXCLUDE`
(`ex_afastamentos_sobreposicao`, só para afastamentos integrais aprovados). Implementar a consulta de
`PONTO-PER-001` em `atualizarAfastamento` (mesmo padrão da T4). `atualizarAfastamento` que muda
`status` fora de uma transição válida (ex.: reaprovar um `cancelado`) responde `PONTO-CONF-003`.
Leitura de `afastamentos.cid` deve passar pela permissão `afastamentos.ler` (já marcada `sensivel`
no catálogo semeado pela F1 — confirme, não redeclare) para que `acessos_dados_sensiveis` seja
gravado automaticamente por `exigir_permissao`.
**Pronto quando:** teste prova os dois lados da constraint `EXCLUDE` (dois afastamentos integrais
aprovados sobrepostos do mesmo colaborador são recusados; um afastamento parcial sobreposto a um
integral é aceito); teste prova que `periodoParcial = true` sem `horaInicio`/`horaFim` é recusado;
teste prova que ler um afastamento com `cid` preenchido grava linha em `acessos_dados_sensiveis`.

### T7 — Resolvedor de jornada do dia
**Agente:** A3
**Descrição:** Implementar `app.jornada.resolvedor.servico.resolver_jornada_do_dia` (assinatura
fixada na §4) seguindo **exatamente** o algoritmo de precedência da §2: (1) resolver
`escala_atribuicoes` vigente → posição do ciclo (reaproveitando a função da T3, nunca duplicando);
senão `vinculo_jornadas` vigente → `jornada_dias` pelo dia da semana; senão `PONTO-APUR-002`. (2)
Sobrepor afastamento aprovado integral do colaborador, se houver. (3) Sobrepor feriado aplicável à
unidade do vínculo (via `unidade_feriado_conjuntos`), resolvendo móveis pelo ano da data consultada
(reaproveitando a função da T5). (4) Montar `entradaPrevista`/`saidaPrevista` no fuso efetivo
(`unidades.fuso_horario` do vínculo, ou `empresas.fuso_horario` quando `vinculos.unidade_id` for
nulo — documentar a escolha no código, ver §2). Adicionar o corpo de `resolverJornadaDoDia` em
`app/routers/jornadas.py` chamando esta função (ver regra de convivência da §5). Vínculo de outro
tenant, ou inexistente, responde `PONTO-REC-001`.
**Pronto quando:** o resolvedor devolve corretamente os casos de mesa da T2/T3/T5 combinados (jornada
fixa simples, 12x36 puro, 12x36 atravessando virada de mês, feriado municipal só na unidade certa,
afastamento sobrepondo dia de trabalho); e um teste prova `PONTO-APUR-002` quando o vínculo não tem
nenhuma atribuição vigente.

### T8 — Golden dataset final: 40+ cenários executados contra o resolvedor real
**Agente:** A4
**Descrição:** Expandir `apps/api/tests/f3/golden/` para **pelo menos 40 cenários** cobrindo, no
mínimo: jornada fixa simples (dias úteis, DSR, folga); jornada flexível; jornada livre; escala 5x2;
6x1; 4x2; 12x36 (incluindo pelo menos dois cenários de **virada de mês** — ex. atribuição com
`vigenciaInicio` em janeiro consultada em fevereiro, e um cenário em que a posição do ciclo cruza o
dia 1º do mês); escala espanhola; escala rotativa de N dias com `posicaoInicial` diferente de 1 (duas
equipes desencontradas na mesma escala); troca de jornada no meio do mês respeitando vigência (o dia
14 usa a jornada antiga, o dia 15 a nova, sem reescrever o passado); feriado nacional; feriado
estadual; feriado municipal aplicando **só** na unidade certa (não na outra unidade da fixture);
feriado móvel (pelo menos Páscoa, Carnaval e Corpus Christi, com data conferida à mão); ponto
facultativo; afastamento cobrindo dia de trabalho; afastamento parcial coexistindo com jornada normal;
vínculo sem nenhuma atribuição vigente (`PONTO-APUR-002`). Cada cenário chama
`resolver_jornada_do_dia` diretamente (não via HTTP) e compara campo a campo contra o `ResolucaoJornada`
esperado. Medir e reportar a cobertura de `app.jornada` com `pytest --cov=app.jornada
--cov-report=term-missing`.
**Pronto quando:** `len(CENARIOS) >= 40`; todos os cenários passam contra o resolvedor real (não
contra um duplo/mock); cobertura de `app.jornada` ≥ 90 %, com a saída real colada no relatório.

### T9 — Fechamento
**Agente:** A1, A2, A3 e A4
**Descrição:** Rodar todos os comandos da §8 e colar a saída real no relatório da fase, item a item
contra a §7.
**Pronto quando:** todos verdes, com saída colada, e `git status --short packages/contracts` vazio.

## 7. Critérios de aceite

O relatório final responde item a item, com saída real colada.

1. **CRUD completo conforme o OpenAPI**: as 35 operações das 4 tags deixaram de responder `501`;
   `python tools/conferir_rotas.py` continua dizendo `Inventario identico ao contrato`.
2. **Resolvedor cobre os 40+ cenários do golden dataset**, executados contra o código real (não
   contra mock), com resultado esperado escrito **antes** do resolvedor existir (prova: commits de
   `tests/f3/golden/` anteriores aos de `app/jornada/resolvedor/`, ou declaração equivalente no
   relatório).
3. **Virada de mês em 12x36 correta**: pelo menos dois cenários do golden dataset atravessam
   fronteira de mês com resultado de posição do ciclo conferido à mão.
4. **Troca de jornada no meio do mês respeita vigência**: dia anterior à troca resolve pela jornada
   antiga, dia da troca em diante pela nova; nenhuma reescrita do passado.
5. **Feriado municipal aplica só na unidade certa**: as duas unidades da fixture (municípios
   diferentes) resolvem `tipoDia` de forma diferente na mesma data quando só uma tem o feriado
   municipal associado.
6. **Feriados móveis calculados corretamente**: Páscoa, Carnaval, Sexta-Feira Santa, Corpus Christi
   e Quarta-Feira de Cinzas conferidos à mão contra calendário oficial para pelo menos dois anos.
7. **Cobertura ≥ 90 %** em `app.jornada` (`--cov=app.jornada --cov-report=term-missing`), saída real
   colada.
8. **Vigência sem sobreposição**: `vinculo_jornadas` e `escala_atribuicoes` recusam sobreposição com
   `PONTO-VAL-010`; a constraint `EXCLUDE` do banco é a linha de defesa comprovada por teste
   (violação por `INSERT` direto também recusada).
9. **Escala cíclica resolvida por aritmética modular**, nunca por calendário materializado — prova:
   não existe tabela nem rotina que grave uma linha por dia futuro de escala.
10. **Sem regra vigente responde `PONTO-APUR-002`**, e nunca um 500 nem um resultado inventado.
11. **Afastamento e feriado nunca geram marcação nem tocam a tabela `marcacoes`** (que nem existe
    ainda nesta onda, mas a garantia é de desenho: nenhum código desta fase referencia
    `marcacoes`).
12. **Toda rota declara `Depends(exigir_permissao(...))`** com exatamente o `x-permissao` do
    contrato — verificável por um teste que percorre o `openapi.yaml` e confere rota a rota.
13. **Leitura de `afastamentos.cid` grava `acessos_dados_sensiveis`.**
14. **Contrato intacto**: `git status --short packages/contracts` vazio.
15. Todos os comandos da §8 verdes, com saída real colada no relatório.

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

Lint, formatação e tipos (versões fixadas no CI: ruff 0.7.4, mypy 1.13.0):

```bash
ruff check apps packages tests
ruff format --check apps packages tests
mypy apps packages
```

```powershell
.\tasks.ps1 lint
.\tasks.ps1 typecheck
```

**Saída esperada:** `All checks passed!`, `NN files already formatted`,
`Success: no issues found in NNN source files`.

Testes da fase, com cobertura do pacote de domínio:

```bash
cd apps/api && pytest tests/f3 -q --cov=app.jornada --cov-report=term-missing
```

```powershell
cd apps/api; pytest tests/f3 -q --cov=app.jornada --cov-report=term-missing
```

**Saída esperada:** todos os testes passam; a linha `TOTAL` da cobertura ≥ 90 %; nenhum `skip` nos
testes que exigem banco.

Contagem do golden dataset (o critério de aceite 2):

```bash
cd apps/api && python -c "from tests.f3.golden.cenarios import CENARIOS; assert len(CENARIOS) >= 40; print(len(CENARIOS))"
```

```powershell
cd apps/api; python -c "from tests.f3.golden.cenarios import CENARIOS; assert len(CENARIOS) >= 40; print(len(CENARIOS))"
```

**Saída esperada:** um número inteiro ≥ 40.

Regressão do andaime da Fase 0 (não pode quebrar):

```bash
cd apps/api && pytest tests/test_andaime.py -q
```

Inventário de rotas idêntico ao contrato:

```bash
cd apps/api && python tools/conferir_rotas.py
```

**Saída esperada:** `Inventario identico ao contrato (metodo, caminho e operationId).`

Contrato não foi tocado:

```bash
git status --short packages/contracts
```

**Saída esperada:** nada.

Migration continua reversível contra banco real:

```bash
cd apps/api && alembic upgrade head && alembic downgrade base && alembic upgrade head
```

## 9. Proibições

1. **Não edite `packages/contracts/`** — `openapi.yaml`, `schema.sql`, `models/`, `errors.yaml`,
   `events.yaml`, `design-tokens.json`, `glossario.md`. Divergência vira RFC em `docs/rfc/`, no
   formato de `docs/rfc/README.md`.
2. **Não crie código de erro novo.** Se faltar um, é RFC. Em particular, não invente um erro para o
   "agendamento de recálculo" mencionado na descrição de `excluirAfastamento` — isso não tem
   mecanismo no contrato (nem evento, nem fila); registre em `docs/backlog.md`, não implemente.
3. **Não crie migration nova.** As 13 tabelas do grupo já existem em `0001_inicial.py`.
4. **Não implemente cálculo de horas, hora extra, adicional noturno, intrajornada, interjornada,
   DSR, faltas nem banco de horas.** Isso é a F4. Se você está escrevendo uma fórmula que soma
   minutos trabalhados ou aplica um fator sobre eles, pare — não é desta fase.
5. **Não materialize calendário de escala em linhas de banco.** A posição do ciclo é sempre
   calculada por aritmética modular a partir de `data_referencia`/`vigencia_inicio`, nunca
   pré-gerada dia a dia.
6. **Não deixe feriado de abrangência `nacional` ou `empresa` valer implicitamente para toda
   unidade.** A associação por `unidade_feriado_conjuntos` é sempre explícita, mesmo para
   conjuntos nacionais.
7. **Não implemente a API de fechamento de período** (`periodos`, `fechamentos`) — é da F10. Você
   só lê essas tabelas, nunca escreve, para honrar `PONTO-PER-001`.
8. **Não toque em `app/routers/__init__.py` nem em `app/main.py`** — os quatro roteadores desta
   fase já estão registrados pela Fase 0.
9. **Não altere as assinaturas públicas de `app/core/seguranca.py`.** Você só consome
   `exigir_permissao`/`tenant_id_ou_erro`; a implementação é da F1 e já está pronta.
10. **Não invente endpoint que não existe no contrato** — em particular, não adicione
    `obterHorario`, `excluirHorario`, `obterTurno`, `excluirTurno`, `obterFeriado`,
    `atualizarFeriado`, `obterTipoAfastamento`, `excluirTipoAfastamento` nem uma listagem de
    histórico de `escala_atribuicoes` por vínculo. Se a ausência parecer um defeito do contrato,
    é RFC, não invenção.
11. **Não escreva o *golden dataset* depois do resolvedor** — a ordem importa: A4 escreve os
    cenários com resultado esperado antes ou em paralelo ao código de A3, nunca ajustando o
    resultado esperado para bater com o que o código produziu.
12. **Não use os termos proibidos** da seção 6 do glossário: é *marcação* (nunca "batida"),
    *tratamento* (nunca "ajuste de marcação"), *colaborador* (nunca "funcionário" no código),
    *vínculo* (nunca "contrato" para dizer a chave de apuração), *tenant* (nunca "empresa" para
    dizer cliente do SaaS).
13. **Não declare a fase pronta sem rodar os comandos da §8 e colar a saída real.** "Deve
    funcionar" não é evidência.
