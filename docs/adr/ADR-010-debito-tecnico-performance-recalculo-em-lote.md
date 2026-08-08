# ADR-010 — Débito técnico aceito: performance do recálculo em lote abaixo do alvo

**Status:** Aceito 26/07/2026 · **Parcialmente otimizado 08/08/2026** (ver "Atualização" no fim do documento — critério 4 continua NÃO atendido, débito parcialmente reduzido, não fechado)
**Decisores:** Henrique Matias (dono do produto) — decisão de aceitar débito
técnico versus investir tempo de engenharia adicional nesta fase, escalada
pelo orquestrador da F4 dado o tamanho do desvio frente à meta
**Fases afetadas:** F4 (onde o desvio foi medido), F3 (resolvedor de jornada,
provável causa raiz), F10 e F11 (fechamento e relatórios, que também disparam
recálculo em lote e herdam o mesmo custo por dia)

---

## Contexto

O critério de aceite 4 do PCF da F4 (`docs/fases/F04-calculo-banco-de-horas.md`,
§7) e o alvo de referência de `FASES-E-AGENTES.md` para a fase pedem que
`recalcular_periodo` processe **10.000 vínculos × 31 dias em menos de 5
minutos**. Medido diretamente na VPS (mesma máquina do Postgres de teste,
portanto sem custo de rede/túnel SSH somado à medição — ver
`apps/api/tests/f4/performance/test_performance_recalculo.py`), uma amostra
real de **1.000 vínculos × 31 dias (31.000 apurações) levou 3.575,7 segundos
(59,6 min), 115,35 ms por apuração**. Extrapolação linear (mesmo modelo que o
próprio teste já documenta e usa) para o volume-alvo de 10.000 × 31 dá **≈
596 minutos (≈ 9,9 h)** — cerca de **120× acima do alvo de 5 minutos**.

**Diagnóstico preliminar (leitura de código, não instrumentado a fundo).**
`recalcular_periodo` (`apps/api/app/apuracao/tratamento/recalculo.py`) itera
`vínculo × dia` sequencialmente em Python; para cada par, `apurar_dia`
(`apps/api/app/apuracao/dominio/servico.py`) chama
`app.jornada.resolvedor.servico.resolver_jornada_do_dia` (F3) do zero — sem
nenhum cache de resolução entre dias consecutivos do mesmo vínculo, mesmo
quando a jornada vigente não muda dia a dia (o cenário mais comum: jornada
fixa por meses). Cada chamada de `apurar_dia` soma, no mínimo, as consultas
do resolvedor mais leitura de marcações/tratamentos mais
`INSERT`/`UPDATE ON CONFLICT` de `apuracoes_dia`/`apuracao_componentes` —
tudo em round-trips separados, sem batch entre dias nem entre vínculos. Isto
é consistente com um padrão N+1 clássico (uma amplificação de consultas por
unidade de trabalho, aqui por dia apurado), mas **não foi instrumentado com
`EXPLAIN ANALYZE`/contagem real de queries** — é a hipótese mais provável a
partir da leitura do código, não uma causa comprovada.

**O motor em si está correto.** O achado de performance é isolado: golden
dataset da F3 contra `apurar_dia` real (47/47 cenários), idempotência do
recálculo, imutabilidade do extrato de banco de horas, RLS cross-tenant e os
demais 15 critérios de aceite do PCF passam com evidência real (ver relatório
de verificação da fase). O problema é exclusivamente de **volume × tempo**,
não de corretude.

## Decisão

**A F4 é aceita e commitada com este débito técnico registrado formalmente,
em vez de bloquear a fase para uma otimização agora.**

1. O critério de aceite 4 do PCF fica marcado como **não atendido** nesta
   entrega — não escondido, não reclassificado como "atendido com ressalva".
2. Este ADR é a fonte de verdade sobre o estado real de performance até que
   uma otimização dedicada resolva ou revise o critério.
3. Nenhuma mudança de código foi feita para tentar mitigar isto na F4 — não
   é uma correção parcial nem um ajuste de configuração paliativo. O código
   de `recalcular_periodo`/`apurar_dia` entregue pela F4 é exatamente o
   mesmo que foi medido.
4. Candidatos de otimização para a fase dedicada futura (não implementados
   agora, só registrados como direção provável): cache de resolução de
   jornada por vínculo dentro de uma mesma chamada de `recalcular_periodo`
   (quando `jornada_id`/`escala_id` resolvidos não mudam de um dia para o
   seguinte); paralelizar vínculos independentes (hoje inteiramente
   sequencial); reduzir round-trips por dia (`_estado_anterior` +
   `apurar_dia` + `gravar_auditoria` fazem no mínimo 4-6 idas ao banco por
   dia, algumas delas potencialmente combináveis); medir com
   `EXPLAIN ANALYZE`/`pg_stat_statements` antes de qualquer mudança, para não
   otimizar às cegas.

## Alternativas consideradas

**Investir agora numa otimização (cache de resolução de jornada por
vínculo).** Resolveria o problema sem deixar dívida, mas exigiria: mexer em
`recalcular_periodo`/`apurar_dia` (ownership de A1/A3, já entregue e
verificado), reverificar idempotência e todos os 17 critérios de aceite de
novo depois da mudança, e um ciclo de diagnóstico real (instrumentação,
`EXPLAIN ANALYZE`) antes de qualquer alteração para não arriscar otimizar o
lugar errado. Descartada **para agora** por alongar uma fase já longa
(2 ondas de build + reparo) sem garantia de que a causa raiz diagnosticada
por leitura de código é de fato a dominante — decisão do dono do produto,
não do orquestrador.

**Reduzir o alvo de aceite** (aceitar, por exemplo, "< 5 min para 1.000 × 31"
como o novo critério oficial). Descartada: mascararia o desvio real em vez de
registrá-lo, e o volume de referência (10.000 colaboradores) não é arbitrário
— é o público-alvo real do produto (`FASES-E-AGENTES.md`). Mudar a meta sem
mudar a realidade do cliente não resolve nada.

## Consequências

**Positivas.** A F4 fecha sem bloquear F5-F13 esperando uma otimização de
performance que não tem escopo nem instrumentação definidos ainda. O achado
fica registrado com números reais e hipótese de causa, não como "parece
lento" informal — quem otimizar no futuro começa de um diagnóstico, não do
zero.

**Negativas e mitigações.** (a) Em produção, hoje, um recálculo em lote de
10.000 vínculos × 31 dias literalmente não terminaria em tempo hábil (nem
perto de 5 min) — se `POST /v1/apuracoes/recalcular` for chamado com esse
escopo antes da otimização, o job do ARQ vai rodar por horas; mitigação
recomendada até a otimização existir: limitar o escopo de recálculo em lote
na operação (por empresa/unidade pequena, não o tenant inteiro de uma vez) e
comunicar isso como limitação operacional conhecida, não deixar o RH descobrir
sozinho. (b) F10 (fechamento) e F11 (relatórios) provavelmente disparam
recálculo em volume parecido ou maior — herdam o mesmo teto de performance
até a otimização acontecer; quem planejar essas fases deve ler este ADR antes
de assumir que o recálculo em lote é rápido o bastante para rodar em request
síncrona ou em janela curta de manutenção. (c) Nenhum número de performance
é reavaliado automaticamente — a próxima vez que alguém tocar
`recalcular_periodo`/`apurar_dia`/`resolver_jornada_do_dia`, o teste de
`apps/api/tests/f4/performance/` deve rodar de novo (preferencialmente a
partir de uma máquina com acesso local ao Postgres, não por túnel SSH, para
não confundir latência de rede com custo real de computação) antes de
declarar a otimização resolvida.

## Atualização — 08/08/2026, diagnóstico real + otimização parcial

**Diagnóstico instrumentado (não mais hipótese de leitura de código)**:
contador de statements SQL (`before_cursor_execute`) + cronômetros por fase,
rodando 100 vínculos × 31 dias = 3.100 apurações direto na VPS (Postgres de
teste local, sem túnel — mesma metodologia da medição original). Achados:

- **78.918 statements SQL = 25,45 queries por apuração**, 93,09s dentro do
  driver de ~165s de parede (56% em SQL, 44% em Python/ORM). Piso de
  round-trip medido isoladamente: 0,53 ms.
- `resolver_jornada_do_dia` (F3): 27.100 statements, **34,3% do total**,
  13,10 ms/apuração — 8,74 queries por dia (`vinculos`, `unidades`,
  `escala_atribuicoes`, `vinculo_jornadas`, `jornadas`, `jornada_dias`,
  `horarios`, `afastamentos`, `unidade_feriado_conjuntos`), todas relidas do
  zero a cada dia mesmo quando a jornada vigente não muda.
- `gravar_auditoria` (F1, reaproveitada): 12.400 statements, ~15% do tempo
  (`pg_advisory_xact_lock` + `MAX(sequencia)` + hash anterior + `INSERT`) —
  bloco que o diagnóstico original de 26/07 não tinha isolado.
- `_sincronizar_ocorrencia`: 9.200 statements, ~9%.

**Veredito sobre a hipótese original**: parcialmente confirmada. O
resolvedor de F3 é o maior bloco isolado, mas **não é dominante** — a causa
real é um N+1 uniforme de ~25 round-trips por dia apurado (~1 ms cada),
espalhado por vários módulos, não um único gargalo.

**Otimização implementada**: `CacheResolucao` (`app/jornada/resolvedor/
servico.py`) — cache opcional, somente-leitura, de vida curta (uma única
chamada de `recalcular_periodo`), passado por um parâmetro NOMEADO opcional
acrescentado a `resolver_jornada_do_dia`/`apurar_dia` (os parâmetros
posicionais fixados pelo PCF não mudaram; ausente o cache, o comportamento é
byte a byte o de antes). Guarda linhas inteiras e filtra por data em Python
com o MESMO predicado do SQL, inclusive replicando `MultipleResultsFound`
nos mesmos casos em que o banco levantaria. Mais um ganho pequeno e seguro:
`_upsert_apuracao_dia` passa a devolver se a linha é uma criação (via
`RETURNING versao`, sem consulta extra), permitindo `_sincronizar_ocorrencia`
pular a checagem de "já existe uma ocorrência aberta?" quando a apuração
acabou de nascer (não pode haver ocorrência apontando pra um id novo).
`calcular_dia` (função pura, 17 critérios já verificados) não foi tocada.

**Resultado medido** (mesmo volume, mesma máquina, 5 pares alternados
ANTES/DEPOIS pra cancelar ruído de carga da VPS): mediana 169,6s → 116,9s
(**1,45×**; ganho médio par-a-par 1,57×). Métrica determinística (statements
SQL, livre de ruído de carga): **25,45 → 14,36 queries/apuração (−43,6%)**;
`resolver_jornada_do_dia` especificamente: **13,10 → 0,34 ms/apuração
(−97%)**. Extrapolação linear para 10.000×31: **283 min → 195 min** (meta:
< 5 min — **continua ~39× acima, critério 4 permanece NÃO atendido**).

**Os 17 critérios de aceite de F4 foram reverificados** (suíte completa de
`apps/api` contra Postgres real, não só F3/F4): 16/17 verdes, incluindo
idempotência do hash (recalcular 2× = 0 dias alterados), recálculo parcial,
cobertura de `app.apuracao` em 94%, `conferir_rotas.py` batendo com o
contrato, `ruff`/`mypy` limpos. Só o critério 4 (performance) continua não
atendido, como já era esperado — o ganho reduz o problema, não o resolve.

**Achados adicionais, não corrigidos agora (fora do escopo desta rodada)**:
(a) bug latente pré-existente encontrado de passagem: `_upsert_apuracao_dia`
pode devolver um objeto ORM desatualizado da identity map da sessão num
segundo `apurar_dia` para o mesmo `(vínculo, dia)` na mesma sessão (mesma
causa que gerou uma regressão nos testes de `tests/f10/afastamentos_workflow`
durante o desenvolvimento desta otimização, já corrigida usando `RETURNING`
em vez de reler o objeto — mas o `_montar_schema_resposta`/leitura de
`versao` fora deste caminho específico ainda tem o risco residual); fix
sugerido: `.execution_options(populate_existing=True)` no re-`SELECT`. (b)
Direções de otimização maiores, ainda não tentadas: memoizar
`(sequência, hash)` da última linha de auditoria por tenant dentro da mesma
transação (a `pg_advisory_xact_lock` já serializa, ~15% do tempo, mas mexe
em módulo de F1/cadeia de integridade); paralelizar vínculos independentes
(hoje 100% sequencial, e com ~14 queries/dia a ~1 ms cada o processo é
dominado por espera de I/O — é o caminho mais realista para chegar perto da
meta de 5 min); processar em lote entre dias (ler marcações/tratamentos do
intervalo inteiro de uma vez, `executemany` em vez de round-trip por dia) —
mudança estrutural maior na forma de `apurar_dia`, fora do escopo de um
parâmetro opcional.

**Decisão**: aceitar o ganho de 1,45-1,57× como redução parcial do débito,
mantendo o critério 4 como não atendido — não é uma correção completa nem
finge ser. Direções (b) ficam registradas como candidatos para uma próxima
rodada dedicada, não implementadas agora pelo mesmo motivo original (decisão
de investimento de engenharia é do dono do produto).
