# ADR-003 — Geração de NSR sequencial sem lacunas sob concorrência

**Status:** Aceito · 25/07/2026
**Decisores:** SEEG — arquitetura
**Fases afetadas:** F5 (implementa), F6 e F7 (produzem eventos), F12 (consome no AFD)

---

## Contexto

O Número Sequencial de Registro é o identificador de cada linha do AFD. A
Portaria MTP 671/2021 exige que ele comece em 1, seja **sequencial, sem lacunas
e sem reuso**, por REP-P. Um buraco na sequência é interpretado como registro
suprimido — é o achado que um auditor procura primeiro, e não há explicação
técnica que o resolva depois do fato.

O problema é que o NSR precisa ser alocado sob concorrência real: cinco canais
(terminal, app, navegador, totem, API) gravam ao mesmo tempo, o pico é a entrada
e a saída do turno, e o `device-gw` faz *catch-up* de centenas de `access_logs`
acumulados quando um terminal volta da queda de rede. Ao mesmo tempo, marcações
coletadas offline chegam **dias depois** do instante em que ocorreram.

A armadilha clássica: `SEQUENCE` do PostgreSQL (e portanto `SERIAL` e
`GENERATED AS IDENTITY`) é **não transacional por projeto**. Ela não volta atrás
em `ROLLBACK`, e é isso que a torna rápida. Qualquer transação abortada — falha
de validação, deadlock, timeout, restart do processo — consome um valor e deixa
um buraco permanente. Para chave primária isso é irrelevante; para NSR é
reprovação.

## Decisão

O NSR é alocado por **contador transacional com bloqueio de linha**, na mesma
transação que insere a marcação.

1. `nsr_sequencias` guarda uma linha por REP-P, com o próximo valor a emitir.
2. A alocação é
   `UPDATE nsr_sequencias SET proximo = proximo + 1 WHERE rep_p_id = :id RETURNING proximo - 1`,
   que toma o bloqueio de linha e serializa apenas os concorrentes **daquele
   REP-P**.
3. O `INSERT` em `marcacoes` acontece na mesma transação. Commit publica os dois;
   rollback desfaz os dois. **Lacuna passa a ser impossível por construção**, não
   por convenção.
4. `nsr_emissoes` registra cada emissão (NSR, marcação, momento, origem) como
   trilha independente, permitindo o verificador de continuidade
   (`GET /v1/marcacoes/nsr/verificar`) provar a ausência de buracos sem
   varrer a tabela particionada inteira.
5. **O NSR é ordem de gravação, não ordem cronológica.** Uma batida offline de
   terça que chega na quinta recebe o NSR da quinta e carrega a data/hora real
   no campo próprio do registro tipo 7. A Portaria exige sequência sem lacunas,
   não monotonicidade temporal — e forçar a segunda tornaria o offline
   impossível de atender honestamente.
6. Marcações importadas de AFD de outro fabricante (F13) vivem em **namespace
   de NSR separado** e nunca tocam a sequência do nosso REP-P.

## Alternativas consideradas

**`SEQUENCE` nativa (`SERIAL`/`IDENTITY`).** Descartada pelo motivo central do
Contexto: gera lacuna em qualquer rollback. `CACHE 1` reduz mas não elimina, e
não protege contra transação abortada.

**`MAX(nsr) + 1` na inserção.** Sofre de condição de corrida clássica: dois
concorrentes leem o mesmo máximo. Só funciona sob `SERIALIZABLE` com retentativa,
o que troca um bloqueio previsível por uma taxa de aborto imprevisível — pior
justamente no pico do turno. Além disso, exige varredura ou índice dedicado numa
tabela particionada que cresce indefinidamente.

**Advisory lock (`pg_advisory_xact_lock`) com contador em tabela.** Funciona,
mas adiciona um mecanismo de bloqueio paralelo ao do MVCC sem ganho: o `UPDATE
... RETURNING` já serializa exatamente o mesmo escopo, com semântica mais simples
de raciocinar e sem risco de colisão de chave de lock entre módulos.

**Alocação assíncrona por worker (fila serializando a numeração).** Removeria
contenção do caminho da requisição, mas o comprovante entregue ao trabalhador
precisa conter o NSR **no momento da batida** — a Portaria dispensa a impressão
porque garantimos acesso eletrônico ao comprovante, e um comprovante sem NSR não
serve. Também introduziria a possibilidade de perder a alocação se a fila
falhasse depois do commit da marcação.

**Serviço externo de sequência (Redis `INCR`, snowflake).** Cria uma segunda
fonte de verdade fora do banco: se o Redis perder estado ou for restaurado de um
snapshot, a sequência regride e há **reuso** de NSR, que é ainda pior que lacuna.

## Consequências

**Positivas.** A propriedade legal mais crítica do sistema vira invariante do
banco. O teste adversarial é direto e binário: 10.000 inserções concorrentes têm
que produzir 1..10.000, sem buraco e sem repetição, com uma fração das transações
abortando de propósito.

**Negativas e mitigações.** (a) Todas as gravações de um mesmo REP-P serializam
naquela linha. É aceitável: um REP-P atende dezenas a centenas de batidas por
minuto, não dezenas de milhares por segundo, e o `UPDATE` é de microssegundos.
A mitigação estrutural é que cada empresa (CNPJ) tem seu próprio REP-P, então a
contenção nunca é global. (b) A transação de marcação precisa ser **curta**:
chamada ao motor facial, gravação de imagem no MinIO e publicação de evento
acontecem **fora** dela. (c) Um `INSERT` em lote de 500 eventos de catch-up
mantém o bloqueio por mais tempo; a F6 processa catch-up em lotes limitados, com
commit por lote. (d) Como o NSR não é cronológico, todo relatório e todo espelho
ordenam por data/hora da marcação, nunca por NSR — regra que precisa estar
explícita no PCF de quem escreve relatório.
