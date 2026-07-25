# ADR-004 — Estratégia de recálculo determinista e idempotente da apuração

**Status:** Aceito · 25/07/2026
**Decisores:** SEEG — arquitetura
**Fases afetadas:** F3 (resolvedor e golden dataset), F4 (implementa), F10 (fechamento), F11 (relatórios)

---

## Contexto

A apuração é o coração econômico do produto: dela saem horas extras, adicional
noturno, faltas, DSR, banco de horas e, no fim, o valor que entra na folha. E ela
é constantemente invalidada por fatos retroativos: um atestado entregue dez dias
depois, um ajuste aprovado pelo gestor, uma escala corrigida, um feriado
municipal cadastrado tarde, uma mudança de jornada com vigência no meio do mês.

Um motor que recalcula e produz resultado diferente para os mesmos insumos é
indefensável — o colaborador vê o saldo mudar sem explicação e a empresa perde a
capacidade de justificar o holerite. Um motor que recalcula tudo desde a
admissão a cada evento não termina em tempo útil com 10.000 colaboradores. E um
motor que recalcula um período já fechado corrompe um fechamento assinado.

## Decisão

A apuração é uma **função pura de insumos versionados**, materializada por
vínculo e dia, com recálculo por invalidação de intervalo.

1. **Função pura.** `apurar(vinculo, dia)` recebe um conjunto fechado de
   insumos — marcações do dia (e das bordas, para jornada que cruza a
   meia-noite), jornada vigente, escala, feriados da unidade, tratamentos
   aprovados, afastamentos, políticas do tenant — e devolve `apuracoes_dia` +
   `apuracao_componentes` + `ocorrencias`. Ela **não lê relógio**, não lê
   configuração global mutável e não consulta nada fora do conjunto declarado.
2. **Determinismo imposto na aritmética.** Toda duração é `INTEGER` em minutos;
   ponto flutuante é proibido no motor. Fator de hora extra é razão inteira
   aplicada a minutos, com regra de arredondamento única e explícita. O
   pareamento de marcações usa ordenação estável por `(data_hora, nsr)`, para
   que duas batidas no mesmo segundo tenham ordem definida.
3. **Fuso da unidade, sempre.** A data civil da apuração é derivada do fuso da
   unidade do vínculo, nunca do fuso do servidor nem do cliente.
4. **Hash de insumos.** Cada `apuracoes_dia` guarda o hash do conjunto de
   insumos que a produziu e a versão do motor. Recalcular com o mesmo hash é
   *no-op*: a linha não é reescrita e nenhum evento é publicado. É isso que
   torna o recálculo idempotente na prática, e não só na teoria.
5. **Invalidação por intervalo.** Todo fato retroativo declara o intervalo
   `(vínculo, data_início, data_fim)` que afeta. O worker recalcula só esse
   intervalo, expandido pelas dependências conhecidas — interjornada olha o dia
   anterior, jornada que cruza a meia-noite olha o dia seguinte, banco de horas
   reprocessa lançamentos a partir da data alterada.
6. **Diff auditado.** Toda mudança de resultado grava o *antes* e o *depois* dos
   componentes em `auditoria`, com a causa (qual tratamento, qual regra, qual
   afastamento). Saldo que muda sem diff é bug.
7. **Período fechado não recalcula.** Fato retroativo sobre período fechado gera
   **ocorrência** e fica pendente até reabertura nominal e justificada
   (`PONTO-PER-*`). O motor não decide por conta própria mexer em fechamento.

## Alternativas consideradas

**Cálculo sob demanda, sem materialização.** Elegante e descartado por custo:
espelho, grade de apuração, dashboards e os 24 relatórios leem apuração o tempo
todo; recalcular 31 dias × 500 colaboradores a cada abertura de tela é inviável,
e o resultado passaria a depender do estado do banco no instante da leitura —
inclusive de um tratamento aprovado no meio da paginação.

**Event sourcing puro (reconstruir estado replicando eventos).** Dá auditoria
excelente de graça e foi descartado pela complexidade desproporcional: exige
snapshots, versionamento de eventos e reprocessamento completo a cada mudança de
regra de negócio — que aqui muda o tempo todo, por convenção coletiva. A
combinação escolhida (fato imutável + sobreposição declarativa + materialização
com hash) entrega a mesma rastreabilidade com um modelo mental que um analista
de RH consegue seguir.

**Recalcular tudo do vínculo a cada evento.** Simples e correto, mas o custo é
quadrático no tempo de casa do colaborador. Descartado pelo critério de aceite
da F4: 10.000 colaboradores × 31 dias em menos de 5 minutos.

**Cache com invalidação por TTL.** Descartado por ser não determinístico por
natureza: o resultado passa a depender de quando a tela foi aberta.

## Consequências

**Positivas.** "Recalcular duas vezes dá exatamente o mesmo resultado" vira
teste automatizado, não promessa. O golden dataset da F3 (cenários trabalhistas
com resultado conferido à mão) pode ser escrito **antes** do motor existir, e
vira o critério de pronto da F4. Mudança de regra ganha um caminho seguro:
sobe a versão do motor, o hash de todas as apurações afetadas muda, o
reprocessamento é rastreável e o diff é revisável.

**Negativas e mitigações.** (a) A declaração de intervalo afetado é a nova fonte
de bug — esquecer que interjornada depende do dia anterior produz apuração
desatualizada silenciosamente. Mitigação: o mapa de dependências é explícito e
testado por propriedade ("recalcular o mês inteiro após a invalidação parcial
não muda nada"). (b) Versão do motor no registro significa que apurações antigas
não são comparáveis linha a linha com novas; o relatório de auditoria mostra a
versão. (c) O custo de armazenamento cresce (uma linha por vínculo por dia mais
componentes), aceito em troca da previsibilidade de leitura. (d) A proibição de
ponto flutuante precisa ser vigiada em revisão de código: um `/ 60.0` perdido
reintroduz não determinismo por arredondamento de binário.
