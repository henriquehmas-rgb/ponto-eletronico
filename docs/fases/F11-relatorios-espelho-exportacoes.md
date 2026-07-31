# F11 — Relatórios, espelho e exportações

| | |
|---|---|
| **Onda** | 4 |
| **Agentes** | 4 · **A1** engine de relatórios (catálogo, colunas configuráveis e salvas por usuário, filtros compostos, agrupamentos, totalizadores, paginação/virtualização, execução síncrona/assíncrona) + tela genérica de relatórios em `apps/web` · **A2** relatórios operacionais (catálogo PROJETO.md §9, itens 2–12) · **A3** relatórios gerenciais/fiscais (itens 13–24) + exportadores CSV/XLSX/PDF + conversão decimal + agendamento por e-mail/webhook · **A4** relatório do espelho de ponto oficial (item 1, dataset de leitura sobre a F10), refino visual do PDF do espelho, dataviz dos dashboards de F9b |
| **Duração estimada** | 9 dias |
| **Depende de** | F4 (cálculo e banco de horas, concluída, commit `6350709`), F9a (design system, concluída), F10 (workflows/fechamento/espelho, concluída, commit `d8673a9`) |
| **Criticidade** | Alta — F13 (API pública) depende do catálogo de relatórios existir; RH/diretoria não têm visão gerencial sem esta fase |
| **Branch** | `f11-relatorios-espelho-exportacoes` |

---

## 1. Objetivo

Ao fim desta fase, os quatro dashboards descritos em `PROJETO.md` §9 (RH, gestor, colaborador, diretoria)
têm acesso a um **catálogo de 24 relatórios** — semeado por tenant, com colunas configuráveis e salvas
por usuário, filtros compostos, agrupamentos e totalizadores — executável de forma síncrona (relatórios
leves) ou assíncrona com progresso (relatórios pesados), exportável em **CSV, XLSX e PDF**, com conversão
opcional de minutos para horas decimais; o **espelho de ponto oficial** (já gerado funcionalmente pela
F10) ganha o layout visual de designer que a F10 deliberadamente não fez, mais agendamento de envio por
e-mail; e os dashboards de RH/gestor de F9b ganham visualizações gráficas (dataviz) sobre os mesmos dados
— enquanto as operações da tag `relatorios` deixam de responder `501` e passam a implementar o motor
completo descrito em `PROJETO.md` §9 e `packages/contracts/openapi.yaml`.

**O que esta fase explicitamente não faz:** cálculo de apuração, banco de horas ou qualquer recálculo
(F4, concluída — esta fase **só lê** o que já foi materializado, nunca chama `apurar_dia`/
`recalcular_periodo`, ver §2.3); geração ou assinatura de um novo espelho de ponto, fechamento de
período, workflow de solicitação/aprovação (F10, concluída — esta fase **lê** `espelhos`/
`assinaturas_espelho`/`fechamentos`, nunca escreve neles, exceto a única exceção documentada de
ownership sobre um arquivo de renderização, §5); AFD, AEJ, assinatura CAdES ou qualquer arquivo fiscal
oficial (F12, ainda não construída — um relatório desta fase pode **listar o histórico** de arquivos já
gerados por F12, nunca gerá-los); entrega de webhook com HMAC/retentativa/DLQ do domínio de integrações
(F13); exportação de folha de pagamento para sistemas de terceiros via integração (permissão
`integracoes_folha`, fora desta fase). Se você está prestes a recalcular um dia, gerar um espelho novo,
reabrir um período fechado ou assinar um arquivo fiscal, pare: não é desta fase.

## 2. Contexto mínimo

**O produto.** Sistema de ponto eletrônico brasileiro **REP-P** (Portaria MTP 671/2021), SaaS
multi-tenant. Toda tabela desta fase carrega `tenant_id` sob **Row Level Security**; a aplicação abre
cada transação publicando `app.tenant_id` (`apps/api/app/db/sessao.py::obter_sessao`, real, F1). Você
não desabilita RLS, e um relatório nunca vaza dado de outro tenant — é uma consulta como qualquer outra
sob a mesma sessão.

### 2.1 A arquitetura real do catálogo — não são 24 endpoints, é um catálogo de dados executado por um motor genérico

**Confirmado lendo `packages/contracts/openapi.yaml` por inteiro na tag `relatorios`:** existem **seis**
operações, não 24:

| Operação | Rota | O que faz |
|---|---|---|
| `listarRelatorios` | `GET /v1/relatorios` | Lista o catálogo (paginado, filtra por `categoria`/`sistema`/`ativo`) |
| `obterRelatorio` | `GET /v1/relatorios/{codigo}` | Devolve a definição completa (colunas, filtros, agrupamentos, formatos) de **um** relatório |
| `executarRelatorio` | `GET /v1/relatorios/{codigo}/executar` | Executa **qualquer** relatório do catálogo pelo `codigo`; síncrono (`200`) ou assíncrono (`202` + acompanhamento) |
| `obterExecucaoRelatorio` | `GET /v1/relatorios/execucoes/{execucaoId}` | Progresso e URL de download de uma execução assíncrona |
| `listarAgendamentosRelatorio` | `GET /v1/relatorios/agendamentos` | Lista envios recorrentes configurados |
| `criarAgendamentoRelatorio` | `POST /v1/relatorios/agendamentos` | Agenda o envio recorrente de **um** relatório do catálogo por e-mail, webhook ou MinIO |

Os 24 relatórios são **linhas de dado** na tabela `relatorio_definicoes` (`schema.sql` §16, já existe
desde a Fase 0/`0001_inicial.py`, confirmado lendo a migration), semeadas por tenant com `sistema =
true`, cada uma com `codigo`, `dataset` (identificador interno resolvido no backend — "NUNCA SQL cru
vindo do usuário", comentário da própria coluna), `colunas_disponiveis`/`filtros_disponiveis`/
`agrupamentos` (JSON livre, `additionalProperties: true` no schema — **você define o formato interno
dessas três estruturas nesta fase**, não é um contrato fixado em `openapi.yaml`) e `formatos` (subconjunto
de `csv`/`xlsx`/`pdf`). `executarRelatorio` é o **único** ponto de entrada de execução: ele resolve
`codigo` → `RelatorioDefinicao` → `dataset` → a função de consulta registrada para aquele dataset no
motor (A1), aplica filtros/colunas/agrupamento pedidos na query string, e devolve o resultado no formato
pedido. **Você nunca cria uma rota nova por relatório** — os 24 relatórios são 24 linhas semeadas mais 24
implementações de função de consulta registradas num dicionário interno, não 24 `operationId`.

### 2.2 O catálogo de 24 nomes — resolvido a partir de `PROJETO.md` §9, não inventado

O `openapi.yaml` exemplifica **um único** dos 24 códigos (`espelho-jornada`, em
`ExemploListaRelatorioDefinicao`/`ExemploRelatorioDefinicao`, com `dataset: apuracao_dia`) — os outros 23
não estão em lugar nenhum do contrato. Isto por si só seria um achado de contrato incompleto. Mas
`PROJETO.md` §9 ("9. Relatórios", linhas 259-294) **já lista os 24 nomes exatos**, com a coluna detalhada
do relatório 2 (30+ colunas) por extenso. Este PCF fixa o catálogo a partir dali, resolvendo uma
divergência de numeração com `FASES-E-AGENTES.md` (documentada abaixo, não escondida):

**A divergência:** `FASES-E-AGENTES.md` (F11) atribui "relatórios 1–12" a A2 e "13–24" a A3, tratando o
"espelho de ponto oficial" como escopo de A4 numa linha separada. Mas `PROJETO.md` §9 numera o **próprio**
"Espelho de ponto oficial" como item **1** da lista de 24. As duas fontes não fecham: se A4 fica com o
item 1 e A2 fica literalmente com "1–12", ou A2 tem 12 itens que incluem o espelho oficial (que não é
dela) ou A2 tem só 11 itens nomeados (2–12) e a conta de "12" da `FASES-E-AGENTES.md` está contando por
aproximação, não por numeração literal do catálogo de `PROJETO.md`.

**Decisão fixada por este PCF:** a numeração de `PROJETO.md` §9 é a fonte de verdade dos **nomes**; a
distribuição por agente segue o **conteúdo** de cada linha de `FASES-E-AGENTES.md` (que nomeia
literalmente jornada/espelho prévio, banco de horas, horas extras, adicional noturno, absenteísmo,
atrasos, faltas, tempo real, ocorrências, abonos, férias/afastamentos — exatamente os itens 2–12 de
`PROJETO.md`, nesta ordem, **11 itens**), não a contagem "1–12" tomada ao pé da letra. **A2 fica com 11
relatórios (itens 2–12); A4 fica com o item 1; A3 fica com os itens 13–24 (12 relatórios) mais os
exportadores.** Total 1 + 11 + 12 = 24. Nenhum relatório fica sem dono, nenhum agente ganha trabalho
inventado. Se o orquestrador preferir outra distribuição, é troca de duas linhas nesta tabela, não uma
re-arquitetura — registre a divergência no relatório de fechamento da fase se a decisão mudar.

| # | Nome (`PROJETO.md` §9) | `codigo` (`relatorio_definicoes`) | Categoria | Dataset (interno) | Dono |
|---|---|---|---|---|---|
| 1 | Espelho de ponto oficial | `espelho-oficial` | operacional | `espelho_oficial` (lê `espelhos`/`assinaturas_espelho`, F10) | **A4** |
| 2 | Jornada / espelho prévio — 30+ colunas | `espelho-jornada` | operacional | `apuracao_dia` | A2 |
| 3 | Banco de horas — saldo, extrato, projeção de vencimento | `banco-de-horas` | operacional | `bh_lancamentos` | A2 |
| 4 | Horas extras — por fator, período, centro de custo | `horas-extras` | operacional | `apuracao_componentes` (categoria `extra`) | A2 |
| 5 | Adicional noturno | `adicional-noturno` | operacional | `apuracao_componentes` (categoria `noturno`) | A2 |
| 6 | Absenteísmo — índice, ranking, evolução | `absenteismo` | operacional | `apuracao_dia` (agregado) | A2 |
| 7 | Atrasos e saídas antecipadas | `atrasos-saidas-antecipadas` | operacional | `apuracao_dia` (`atraso_minutos`, `saida_antecipada_minutos`) | A2 |
| 8 | Faltas (justificadas e injustificadas) | `faltas` | operacional | `apuracao_dia` (`falta_minutos`) + `tratamentos` (abono) | A2 |
| 9 | Tempo real — quem está trabalhando agora | `tempo-real` | operacional | `marcacoes` (**exceção**, §2.3) | A2 |
| 10 | Ocorrências e inconsistências | `ocorrencias` | operacional | `ocorrencias` | A2 |
| 11 | Abonos e justificativas | `abonos-justificativas` | operacional | `tratamentos` (categoria `abono`/`justificativa`) | A2 |
| 12 | Férias e afastamentos | `ferias-afastamentos` | operacional | `afastamentos` | A2 |
| 13 | Escalas — previsto x realizado | `escalas-previsto-realizado` | gerencial | `apuracoes_dia` × `escalas`/`turnos` | A3 |
| 14 | Violações de intrajornada | `violacoes-intrajornada` | fiscal | `apuracao_dia` (`intrajornada_suprimida_minutos`) + `ocorrencias` (`intrajornada_suprimida`) | A3 |
| 15 | Violações de interjornada | `violacoes-interjornada` | fiscal | `apuracao_dia` (`interjornada_violada`) + `ocorrencias` (`interjornada_violada`) | A3 |
| 16 | Horas por centro de custo / projeto / cliente | `horas-por-centro-custo` | gerencial | `apuracao_dia` (agrupado por `centro_custo_id`) | A3 |
| 17 | Extrato para folha (layout por parceiro) | `extrato-para-folha` | financeiro | `apuracao_componentes` (agregado mensal) | A3 |
| 18 | Movimentação — admissões, demissões, aniversariantes | `movimentacao-pessoal` | gerencial | `colaboradores`/`contratos`/`vinculos` | A3 |
| 19 | Auditoria — quem alterou o quê, quando, de onde | `auditoria` | gerencial | `auditoria` (F1) | A3 |
| 20 | Dispositivos e canais | `dispositivos-canais` | gerencial | `dispositivos`/`marcacoes.canal`/`terminais` | A3 |
| 21 | Custo de horas extras (financeiro, valor-hora) | `custo-horas-extras` | financeiro | `apuracao_componentes` × `cargos.salario_base` | A3 |
| 22 | Produtividade / headcount por área | `headcount-por-area` | gerencial | `vinculos`/`departamentos` | A3 |
| 23 | Arquivos fiscais — histórico de geração e download | `arquivos-fiscais-historico` | fiscal | `afd_arquivos`/`aej_arquivos` (F12, leitura; §2.7) | A3 |
| 24 | LGPD — acessos e solicitações de titular | `lgpd-acessos-e-titulares` | lgpd | `acessos_dados_sensiveis`/`solicitacoes_titular` | A3 |

**Evidência que ancora cada dataset menos óbvio** (para você não precisar adivinhar coluna): `cargos.
salario_base` tem o comentário literal "Referencia salarial usada apenas no relatorio de custo de horas
extras" (`openapi.yaml`, três ocorrências) — é a prova de que o relatório 21 já era esperado pelo
desenhista do contrato. `ocorrencias.codigo` (`schema.sql` linha 2561) tem exatamente os valores
`intrajornada_suprimida`/`interjornada_violada` usados pelos relatórios 14/15. `colaboradores.
pessoa_com_deficiencia` tem o comentário "Influencia cota legal e relatorios, nao o calculo de jornada"
— se o orquestrador preferir um relatório de cota PCD dedicado no lugar de um dos gerenciais acima
(nenhum item de `PROJETO.md` §9 nomeia isto explicitamente), é troca de uma linha da tabela, registre a
troca.

**O relatório 23 pode devolver zero linhas durante esta fase, e está correto assim.** F12 (AFD/AEJ) roda
na mesma onda que F11, sem dependência entre as duas (`FASES-E-AGENTES.md`: "F11 depende de F4, F9a,
F10"; "F12 depende de F5, F4, F10" — nenhuma cita a outra). As tabelas `afd_arquivos`/`aej_arquivos` já
existem no schema congelado desde a Fase 0; você lê o que houver. Para testar o relatório sem depender do
código de F12 (ownership alheio, ainda não escrito), semeie linhas sintéticas por `INSERT` direto na
fixture de teste desta fase — mesmo padrão que outras fases já usaram para depender de dado de fase
paralela sem depender do *código* dela.

### 2.3 Estratégia de performance — por que o critério de <60s é alcançável apesar do ADR-010

**Leitura obrigatória antes de prometer qualquer número:** `docs/adr/ADR-010-debito-tecnico-performance-
recalculo-em-lote.md`. Resumo do achado: `recalcular_periodo`/`apurar_dia` (F4) processam 1.000 vínculos
× 31 dias em ~3.576s medidos (115ms por dia-vínculo, ~120× acima da meta), com causa provável em
`resolver_jornada_do_dia` (F3) chamado do zero a cada dia, sem cache, em loop Python síncrono por dia. O
ADR lista **F11 entre as fases afetadas**, com o aviso: "quem planejar essas fases deve ler este ADR antes
de assumir que o recálculo em lote é rápido o bastante". `docs/backlog.md` (2026-07-26, "F10/F11 herdam o
mesmo teto de performance ao recalcular em lote") repete o mesmo alerta.

**A leitura correta do alerta, e a decisão fixada por este PCF: o alerta se aplica a quem RECALCULA em
lote. Esta fase nunca recalcula.** `docs/adr/ADR-004-recalculo-determinista-idempotente.md` já declarava
isto antes mesmo de F11 existir, na seção "Alternativas consideradas": *"Cálculo sob demanda, sem
materialização... espelho, grade de apuração, dashboards **e os 24 relatórios** leem apuração o tempo
todo; recalcular 31 dias × 500 colaboradores a cada abertura de tela é inviável"* — o motor de F4
materializa `apuracoes_dia`/`apuracao_componentes` **exatamente** para que consultas de leitura em massa
(como um relatório) nunca paguem o custo do resolvedor de jornada. O ADR-010 mede o custo de **escrever**
uma apuração (loop Python, resolvedor, `INSERT`/`UPDATE`); um relatório desta fase só **lê** o que já foi
escrito, com `SELECT`/`GROUP BY` agregados em SQL, sob os índices que já existem
(`ix_apuracoes_dia_periodo`, `ix_apuracoes_dia_colaborador`, `schema.sql` linhas 2513-2517) — uma ordem de
grandeza de trabalho completamente diferente, sem nenhuma chamada a `resolver_jornada_do_dia` nem a
`apurar_dia`.

**Regra fixada, vale para todo dataset dos 24 (proibição 1, §9):** nenhuma função de consulta desta fase
chama `app.apuracao.dominio.servico.apurar_dia` nem `app.apuracao.tratamento.recalculo.
recalcular_periodo`, nem qualquer código que dispare o resolvedor de jornada de F3. Um dia sem linha em
`apuracoes_dia` (ainda não apurado) aparece no relatório como está — vazio, ou com o `tipo_dia` que houver
— exatamente como `app/workflow/fechamento/espelho.py::_montar_conteudo` (F10) já faz para o espelho
(`"tipoDia": "nao_apurado"` quando `apuracao is None`, linha 206 do módulo): você **reaproveita esse
mesmo padrão**, nunca dispara um cálculo síncrono para "completar" o relatório.

**Como o motor atinge <60s para 12 meses × 1.000 colaboradores na prática:**

1. **Agregação empurrada para o SQL, nunca em loop Python por linha.** Um relatório que soma/agrupa
   (horas extras por mês, absenteísmo por departamento) usa `SUM`/`COUNT`/`GROUP BY` do PostgreSQL sobre
   o intervalo pedido — uma única consulta (ou um número pequeno e constante de consultas), não uma
   consulta por dia por vínculo. É o oposto do padrão N+1 que o próprio ADR-010 diagnostica como causa
   provável do desvio de F4.
2. **Relatórios detalhados (uma linha por dia, como o espelho prévio) usam cursor do lado do servidor e
   escrevem no arquivo em streaming**, nunca materializam 372.000 linhas (12 meses × ~31 dias × 1.000
   vínculos) em memória Python de uma vez — nem para checagem de contagem, nem para montar o XLSX. O
   exportador (A3, §2.5) escreve linha a linha no arquivo conforme o cursor entrega, e faz upload do
   arquivo pronto ao MinIO ao final.
3. **Execução assíncrona por padrão para o volume do critério de aceite.** `RelatorioDefinicao.
   assincrono=true` para todo dataset detalhado (item 2, por exemplo); o parâmetro `assincrono=true` da
   query força o caminho assíncrono mesmo em relatórios leves; e a descrição do próprio `openapi.yaml`
   já fixa a regra: *"Um relatorio de 12 meses por 1.000 colaboradores cai sempre nesse caminho"*
   (`executarRelatorio`, linha 14162). Síncrono existe só para relatórios pequenos (um vínculo, um mês).
4. **Prova de performance sem depender do motor de cálculo de F4.** O teste do critério de aceite (§7)
   semeia ~372.000 linhas de `apuracoes_dia`/`apuracao_componentes` sintéticas por `INSERT` em lote
   direto no banco (nunca via `apurar_dia`), e então mede só o tempo do relatório. Isto isola o que esta
   fase controla (a consulta) do que ela não controla (o custo de gerar a apuração, ADR-010) — mesmo
   raciocínio de isolamento que o próprio teste de performance de F4 já documenta em
   `apps/api/tests/f4/performance/test_performance_recalculo.py`.

**Consequência que você não deve esconder:** se um tenant real tem menos de 12 meses de apuração
materializada (porque o recálculo em lote de F4/F10 ainda não rodou até o fim, ADR-010), o relatório
retorna rápido, mas **incompleto** (dias sem linha aparecem como não apurados) — isto não é bug desta
fase, é reflexo fiel do estado real da apuração, e o próprio ADR-010 já avisa que o recálculo em lote
pode não ter terminado. Não compense isto calculando nada aqui.

### 2.4 A lacuna que bloqueia o critério "colunas configuradas persistem por usuário" — RFC necessária

**Confirmado lendo `packages/contracts/openapi.yaml` por inteiro, `packages/contracts/models/relatorio.py`
e `packages/contracts/schema.sql` §16:** a tabela `preferencias_colunas` existe desde a Fase 0
(`0001_inicial.py`, linha ~2853), o model SQLAlchemy `PreferenciaColunas` existe
(`packages/contracts/models/relatorio.py:221`), com exatamente as colunas que a engine precisa
(`usuario_id`, `relatorio_definicao_id` **ou** `tela`, `nome`, `colunas`, `ordenacao`, `filtros`,
`larguras`, `padrao`) — mas **nenhum schema `PreferenciaColunas`/`PreferenciaColunaCriar` e nenhuma rota
`/v1/relatorios/.../preferencias` ou equivalente existe em `openapi.yaml`** (busca exaustiva: zero
ocorrências de `PreferenciaColuna` no arquivo inteiro). O comentário da própria tabela ("`preferencias_
colunas`... é o que faz a configuração do espelho de jornada persistir entre sessões") deixa claro que a
intenção sempre foi expor isto por API — só não foi contratado.

**Isto não é um achado de backlog comum: bloqueava literalmente o critério de aceite oficial "colunas
configuradas persistem por usuário"** (`FASES-E-AGENTES.md`, F11). Sem uma rota HTTP, a interface não
teria como salvar nem reler a preferência do usuário. Pelo protocolo de `docs/rfc/README.md` ("Um
critério de aceite do PCF é impossível de cumprir como está escrito" → RFC), isto virou RFC — **já
decidida pelo orquestrador antes do build começar: `docs/rfc/RFC-015-preferencias-colunas-sem-
endpoint.md`, ✅ Decidida em 30/07/2026.**

**Decisão já tomada, para A1 não precisar decidir nem propor nada — só implementar:**

1. **T1 de A1 aplica a RFC-015 diretamente em `packages/contracts/openapi.yaml`/`schemas/contrato.py`**
   (não abre RFC nova, não propõe — a decisão já existe): dois endpoints novos na tag `relatorios` —
   `GET /v1/relatorios/preferencias-colunas` (`operationId: listarPreferenciasColunas`,
   `x-permissao: relatorios.ler`, filtra sempre pelo `usuario_id` do sujeito autenticado, nunca aceita
   `usuarioId` de query) e `PUT /v1/relatorios/preferencias-colunas` (`operationId:
   salvarPreferenciaColunas`, `x-permissao: relatorios.ler`, sem `Idempotency-Key` — o corpo descreve o
   estado final completo, `INSERT ... ON CONFLICT ... DO UPDATE` sobre `uq_preferencias_colunas`).
   Schemas `PreferenciaColunas`/`PreferenciaColunasCriar` modelados exatamente pelas colunas já
   existentes na tabela (`usuarioId`, `relatorioDefinicaoId` OU `tela`, `nome`, `colunas`, `ordenacao`,
   `filtros`, `larguras`, `padrao`) — nenhum campo novo. Ver RFC-015 §"Decisão do orquestrador" para o
   texto exato já aprovado.
2. **T1 também constrói o módulo interno** (`app/relatorios/preferencias.py`: `salvar_preferencia`,
   `obter_preferencia`, `listar_preferencias`, todas operando direto sobre `preferencias_colunas` sob
   RLS), consumido pelos dois handlers HTTP novos. O teste do critério de aceite prova o caminho HTTP
   real (`PUT` seguido de `GET` numa sessão nova devolve exatamente a mesma configuração), não só a
   leitura direta da tabela — a RFC já decidida elimina a necessidade do fallback via `localStorage`
   documentado numa versão anterior deste PCF.
3. Isto é a **única** mudança de `packages/contracts/openapi.yaml` que este PCF autoriza nesta fase —
   já decidida, aplicação direta. Qualquer outra necessidade de mudança de contrato encontrada durante a
   fase segue o protocolo normal (RFC nova, ou backlog se não bloquear).

### 2.5 Exportadores e bibliotecas — o que já existe, o que você adiciona

`apps/api/pyproject.toml` já tem `reportlab>=4.2` (PDF, adicionado por F10 para o espelho) e `minio>=7.2`
(armazenamento de objetos, idem) — **reaproveite as duas**, não escolha biblioteca diferente para manter
uma imagem só. `apps/worker/pyproject.toml` já tem `openpyxl>=3.1` (adicionado por F2 para **ler**
planilhas de importação) — a mesma biblioteca **escreve** XLSX (`openpyxl.Workbook()`), então reaproveite-
a para exportação em vez de escolher outra. CSV usa o módulo nativo `csv` da stdlib (streaming, sem
dependência nova).

**Uma adição real de dependência é necessária, com justificativa documentada no `pyproject.toml` (mesmo
padrão que F10 documentou reportlab/minio):**

- `apps/api/pyproject.toml` **não tem** `openpyxl` (só o worker tem, porque só o worker lia planilha até
  agora). Como `executarRelatorio` responde `200` com o arquivo **direto na API** para relatórios leves
  (`formato=xlsx` síncrono), a API também precisa escrever XLSX. Adicione `openpyxl>=3.1` a `apps/api/
  pyproject.toml`, bloco `# --- F11 ---`, com o comentário explicando por que a mesma biblioteca do
  worker aparece de novo aqui (dois processos, duas imagens, mesma necessidade).
- `apps/worker/pyproject.toml` **não tem** biblioteca de expressão cron. O agendamento
  (`relatorio_agendamentos.cron`) precisa calcular `proxima_execucao_em` a partir de uma expressão tipo
  `0 8 1 * *`. Adicione `croniter>=2.0` a `apps/worker/pyproject.toml`, ownership de A3 (T11, §6),
  justificativa: é a biblioteca padrão de mercado para isto em Python, pura (sem dependência de sistema),
  e nenhuma alternativa já está no projeto.
- `apps/worker/pyproject.toml` **não tem** `httpx` (só a API tem). O canal `webhook` de
  `relatorio_agendamentos` (§2.8) faz um `POST` HTTP simples de entrega — não a assinatura HMAC/
  retentativa/DLQ completa da tag `webhooks` (F13, fora de escopo, §1). Adicione `httpx>=0.27` a `apps/
  worker/pyproject.toml`, mesma versão mínima que a API já usa, ownership de A3.

**Conversão decimal** (`converterDecimal=true` na query de `executarRelatorio`): função pura,
`minutos / 60` com casas decimais fixas (documente quantas — sugestão: 2), aplicada **só na
apresentação/exportação**, nunca gravada em lugar nenhum — a descrição do próprio parâmetro já fixa isto:
"Internamente tudo é minuto inteiro" (`openapi.yaml`, linha 14262). Isto é regra de renderização, não de
domínio: nenhum dataset (A2/A3) devolve duração em qualquer unidade que não seja minuto inteiro; a
conversão acontece exclusivamente dentro do exportador (A3, `app/relatorios/exportadores/decimal.py`),
como uma transformação de última milha sobre as colunas numéricas marcadas como "duração" no catálogo.

### 2.6 `apps/web` é tocado nesta fase — ownership de frontend explícito

Ao contrário da F10 (backend puro), esta fase **toca `apps/web`**, por três razões que a própria
`FASES-E-AGENTES.md` já implica e que este PCF confirma lendo o código real de F9a/F9b antes de decidir:

1. **"Colunas configuráveis e salvas por usuário" não existe sem uma tela que as configure.** Um backend
   que salva preferência de coluna sem interface para escolher a coluna não cumpre o critério de aceite
   na prática, só no banco.
2. **"Dataviz dos dashboards" é, pela própria descrição da `FASES-E-AGENTES.md`, uma extensão da
   interface** dos dashboards de F9b (`apps/web/src/componentes/paineis/dashboard/**`, já commitado em
   `a3f5af5`), não uma área nova. **Confirmado lendo o código real:** o dashboard atual
   (`painel-de-indicadores.tsx` + `secao-apuracao.tsx`/`secao-banco-de-horas.tsx`/`secao-colaboradores.
   tsx`/`secao-ocorrencias.tsx`) mostra **cartões de KPI** (números agregados), sem nenhum gráfico — e o
   projeto já tem uma biblioteca de gráficos pronta e não usada por F9b:
   `apps/web/src/componentes/graficos/graficos.tsx` (F9a, design system, `recharts` como dependência já
   declarada em `apps/web/package.json`), com `GraficoDeBarras`, `GraficoDeLinha`/`AreaChart`,
   `GraficoDePizza` já implementados sobre a paleta do design system (`paleta.ts`, `COR_EIXO`/`COR_GRADE`/
   `corDaSerie`). **Você reaproveita esses componentes — não cria uma segunda biblioteca de gráficos.**
3. **O espelho de ponto oficial já tem hook e tela no portal do colaborador** (`apps/web/src/ganchos/
   use-espelho-de-ponto.ts`, F8, já commitado) apontando para `/v1/espelhos/*` — o refino visual do PDF
   (A4) é **inteiramente de backend** (o mesmo hook, o mesmo contrato, só o PDF fica mais bonito), não
   toca nesse arquivo.

**Ownership de frontend fixado:**

- **A1** cria a área genérica nova `apps/web/src/app/painel/relatorios/**` e `apps/web/src/componentes/
  paineis/relatorios/**`: catálogo (lista os 24, filtra por categoria), execução (formulário dinâmico de
  filtros/colunas/agrupamento **construído a partir do `RelatorioDefinicao` devolvido por
  `obterRelatorio`** — uma única tela genérica serve aos 24 relatórios, porque o backend já é
  autodescritivo; nenhum relatório precisa de tela própria), acompanhamento de progresso (poll de
  `obterExecucaoRelatorio`) e download. O seletor de colunas (drag-to-reorder, mostrar/ocultar, salvar
  como padrão) é desta mesma tela, consumindo o módulo de preferências (§2.4). Gancho novo:
  `apps/web/src/ganchos/use-relatorios.ts`.
- **A4** estende as seções já existentes do dashboard de F9b (`secao-apuracao.tsx`,
  `secao-banco-de-horas.tsx`, `secao-ocorrencias.tsx`, e um novo componente de tendência se fizer sentido)
  com gráficos usando `GraficoDeBarras`/`GraficoDeLinha`/`GraficoDePizza` já existentes, alimentados pelos
  datasets do catálogo (`executarRelatorio` com `formato=json`, agrupamento mensal, por exemplo). **Não
  cria arquivo de gráfico novo em `apps/web/src/componentes/graficos/`** — esse diretório é de F9a
  (design system, congelado); só consome. Gancho novo, próprio (não edita `use-indicadores-dashboard.ts`,
  que é ownership exclusivo de F9b/A1 conforme o próprio comentário do arquivo — mesmo padrão de
  fronteira que aquele arquivo já documenta para si mesmo): `apps/web/src/ganchos/use-dataviz-dashboard.
  ts`.
- **A2 e A3 não tocam `apps/web` em nenhuma linha.** O trabalho deles é inteiramente as definições de
  dataset (backend) — a tela genérica de A1 já serve qualquer relatório que exista no catálogo, sem
  precisar de código de tela por relatório.

### 2.7 A ressalva do fechamento — `apuracoes_dia.fechamento_id` nunca é preenchida

`docs/backlog.md` (2026-07-28, achado de F10/A2) documenta que `apps/worker/worker/tarefas/fechamento.
py::processar_fechamento` **só lê** `apuracoes_dia` para compor o hash do fechamento — **nunca grava**
`apuracoes_dia.fechamento_id`/`apuracoes_dia.status`, porque `verificar_periodo_aberto` (a trava real) só
consulta `Fechamento.status`/`Periodo`, nunca essas duas colunas. **Consequência direta para você:**
nenhum dataset desta fase pode filtrar ou fazer `JOIN` por `apuracoes_dia.fechamento_id` para saber se um
dia está "fechado" — a coluna está sempre `NULL`. Se um relatório (por exemplo, o 13, escalas previsto x
realizado, ou qualquer relatório gerencial que precise distinguir período fechado de aberto) precisa
dessa informação, resolva por **intervalo de data e escopo contra a tabela `fechamentos`** (mesmo padrão
que `app/workflow/fechamento/espelho.py::_montar_conteudo`, F10, já usa para ler `apuracoes_dia` por
`periodo.data_inicio`/`data_fim`, nunca por FK), nunca pela coluna `fechamento_id`.

### 2.8 Achados de contrato herdados — registrados, não corrigidos silenciosamente

1. **`preferencias_colunas` sem endpoint** — tratado como RFC bloqueante, §2.4. Não repita aqui.
2. **`relatorio_agendamentos` não tem operação de atualizar, pausar ou excluir** (confirmado: só
   `listarAgendamentosRelatorio`/`criarAgendamentoRelatorio` existem na tag). Um agendamento criado com
   `cron` errado só pode ser desativado recriando-o com `ativo=false` via... não há `PATCH` para isso
   também. **Decisão fixada:** você implementa exatamente as duas operações que existem; para desativar
   um agendamento, documente como limitação conhecida (o cliente precisa que o suporte da SEEG desative
   via acesso direto, ou aguarde a expiração natural do agendamento) e registre em `docs/backlog.md` como
   candidato a RFC futura (`atualizarAgendamentoRelatorio`/`excluirAgendamentoRelatorio`) — não invente as
   rotas.
3. **A permissão `relatorio.agendamentos` (CRUD completo) está semeada no catálogo (`seed_dev.py` linha
   199) mas nenhuma rota da tag `relatorios` usa `agendamentos.criar`/`agendamentos.editar`/etc.** — todas
   usam `relatorios.ler`/`relatorios.executar`/`relatorios.criar` (confirmado: `grep` por `x-permissao`
   na seção `relatorios` do `openapi.yaml` não devolve nenhum valor prefixado por `agendamentos.`). Mesmo
   padrão do achado que F10 já documentou para `afastamentos.aprovar` (permissão semeada, nunca usada por
   nenhuma rota) — não é bug seu, é dado de fábrica mais amplo que o contrato atual usa. Use
   `relatorios.criar` exatamente como o `x-permissao` de `criarAgendamentoRelatorio` já fixa.
4. **`ProcessamentoAssincrono.tipo` tem os valores `relatorio` e `exportacao_folha`** no enum, mas
   `executarRelatorio`/`obterExecucaoRelatorio` devolvem `RelatorioExecucao`, um schema próprio e mais
   rico (progresso, `totalLinhas`, `hashSha256`, `expiraEm`) — **você nunca devolve
   `ProcessamentoAssincrono` em nenhuma rota desta fase.** Os dois valores do enum ficam vestigiais (mesmo
   padrão de "contrato mais amplo que a implementação atual" que outras fases já encontraram); não é
   defeito seu, não precisa de RFC.
5. **Não existe categoria de erro `REL` em `errors.yaml`.** Confirmado lendo a lista completa de
   categorias (`errors.yaml` linhas 34-101): 22 categorias, nenhuma para relatórios. Você **reaproveita**
   `PONTO-VAL-001` (corpo/filtro inválido), `PONTO-VAL-005` (parâmetro de query fora do domínio),
   `PONTO-VAL-007` (intervalo de datas inválido — já usado por `executarRelatorio` no `x-erros`),
   `PONTO-REC-001` (`codigo` de relatório ou `execucaoId` inexistente), `PONTO-REC-002` (artefato
   expirado — já documentado na descrição de `obterExecucaoRelatorio`, `openapi.yaml` linha 14330),
   `PONTO-CONF-003` (transição de estado inválida — por exemplo, tentar baixar uma execução que ainda não
   concluiu), `PONTO-RATE-001` (limite geral de requisições). **Você não cria código de erro novo.**

## 3. Leituras obrigatórias (lista fechada)

Leia isto e pare. Não leia código de F1/F2/F3/F5/F6/F8 além dos módulos explicitamente listados.

- `PROJETO.md` §9 (linhas 259-294) — a fonte de verdade dos 24 nomes de relatório, já processada no §2.2
  deste PCF; leia mesmo assim, para ver a frase completa de cada item (algumas têm sub-descrição que a
  tabela do §2.2 resume).
- `FASES-E-AGENTES.md`, a seção `#### F11` (linhas ~301-311) e a linha da tabela-resumo (linha 390).
- `packages/contracts/openapi.yaml` — **apenas** a tag `relatorios` (seis operações, linhas ~13997-14560)
  e os schemas `RelatorioDefinicao`, `RelatorioExecucao`, `RelatorioAgendamento`,
  `RelatorioAgendamentoCriar`, `ListaRelatorioDefinicao`, `ListaRelatorioAgendamento` (linhas
  ~36061-36405) e os quatro exemplos correspondentes (`Exemplo...`, linhas ~25126-25300). Leia também,
  **só como referência de dado que você consome**: os schemas `ApuracaoDia`, `ApuracaoComponente`,
  `Ocorrencia`, `Tratamento`, `Afastamento`, `Espelho`, `AssinaturaEspelho`, `Fechamento`,
  `Vinculo`/`Colaborador`/`Cargo`/`Empresa`/`Unidade`/`Departamento`/`CentroCusto`/`Equipe` (para os nomes
  exatos de campo dos datasets), `Auditoria`, `AcessoDadosSensiveis`/`SolicitacaoTitular` (nomes exatos
  podem divergir do texto deste PCF — confirme lendo o schema real, não adivinhe), `AfdArquivo`,
  `AejArquivo`, `Dispositivo`, `ProcessamentoAssincrono` (só para confirmar que você **não** o usa, §2.8
  item 4), `Problema`.
- `packages/contracts/schema.sql` — seção **16 (RELATÓRIOS)** por inteiro (`relatorio_definicoes`,
  `relatorio_agendamentos`, `relatorio_execucoes`, `preferencias_colunas`). Leia também, **só leitura,
  nunca escrita**: seção 9 (`apuracoes_dia`, `apuracao_componentes`, `ocorrencias`, `tratamentos`), seção
  12 (`espelhos`, `assinaturas_espelho`, `fechamentos`, `periodos`), o trecho de `bh_lancamentos`/
  `bh_contas` (seção do banco de horas), `afastamentos`/`tipos_afastamento` (F3), `auditoria` (seção 15),
  `acessos_dados_sensiveis`, `consentimentos`, `solicitacoes_titular` (seção LGPD), `afd_arquivos`,
  `aej_arquivos` (seção fiscal, F12), `dispositivos`, `terminais`, `cargos` (coluna `salario_base`),
  `colaboradores` (coluna `pessoa_com_deficiencia`).
- `packages/contracts/models/relatorio.py` — `RelatorioDefinicao`, `RelatorioExecucao`,
  `RelatorioAgendamento`, `PreferenciaColunas` (SQLAlchemy). Confirme os nomes exatos de coluna/atributo
  antes de escrever qualquer query.
- `packages/contracts/errors.yaml` — a lista de categorias (linhas 34-101, confirme que `REL` não existe,
  §2.8 item 5) e os códigos `PONTO-VAL-001/005/007`, `PONTO-REC-001/002`, `PONTO-CONF-003`,
  `PONTO-RATE-001/003` por inteiro.
- `packages/contracts/events.yaml` — confirme que **nenhum** evento de domínio corresponde a execução ou
  agendamento de relatório (busca por `relatorio`/`espelho` no arquivo inteiro — os únicos achados são
  `espelho.assinado`, de F10, e menções a "relatório" dentro de descrições de outros eventos, não um
  evento próprio). **Você não publica evento novo nesta fase** — o acompanhamento de progresso é por
  polling de `obterExecucaoRelatorio`, não por evento.
- `docs/adr/ADR-004-recalculo-determinista-idempotente.md` — a base da estratégia de performance (§2.3).
- `docs/adr/ADR-010-debito-tecnico-performance-recalculo-em-lote.md` — o débito que você **não herda**,
  precisamente porque não recalcula (§2.3). Leia por inteiro, não só o resumo.
- `docs/adr/ADR-011-tratamento-afastamento-retroativo-sem-efeito-numerico.md` — um `Tratamento` de
  categoria `afastamento` (retroativo) **não** altera `apuracoes_dia`/`apuracao_componentes` hoje (débito
  conhecido de F4, herdado por F10). Os relatórios 8 (faltas) e 12 (férias/afastamentos) vão refletir
  esta lacuna fielmente (um afastamento retroativo aprovado não zera a falta no relatório) — **isto é
  esperado, não um bug seu; não invente uma correção compensatória no dataset do relatório** (proibição
  4, §9).
- `docs/adr/ADR-009-worker-instala-apps-api-como-biblioteca.md` — confirma que `apps/worker` importa
  `apps/api/app/**` como biblioteca; a tarefa `executar_relatorio` (§2.9) importa `app.relatorios.*`
  exatamente como `apurar_dia`/`processar_fechamento` já importam `app.apuracao.*`/`app.workflow.*`. Já
  cita F11 como fase afetada por esta decisão.
- `docs/adr/ADR-002-imutabilidade-marcacao-camada-tratamento.md` — contexto de por que o relatório
  "tempo real" (item 9, §2.3) lê `marcacoes` diretamente (única exceção ao padrão "sempre leia apuração
  materializada", porque o dia ainda não foi apurado no momento em que o relatório é consultado) sem
  jamais escrever nela.
- `docs/backlog.md` — procure e leia por inteiro as três entradas com "F11" na coluna "Fase sugerida"
  (débito de performance do ADR-010, a tensão de leitura de `apuracoes_dia` resolvida por F10/A2 §2.7
  deste PCF, e o achado do endpoint de notificações — este último **não é desta fase**, §2.10). Releia
  também o achado de F10 sobre `afastamentos.aprovar` semeada e não usada — mesmo padrão do §2.8 item 3.
- `docs/rfc/README.md` — protocolo de RFC, e releia **RFC-013**/**RFC-014** (precedente de função
  `SECURITY DEFINER` cross-tenant que você **reaproveita sem criar uma nova**, §2.9/§5).
- `docs/fases/F10-workflows-aprovacoes-fechamento.md` — leia **só** §2.4 (fórmula de hash/canonicalização
  que você reaproveita se precisar comparar hash), §2.5 (fronteira exata entre o PDF funcional de F10 e o
  refino visual desta fase — leia por inteiro, é a base da sua tarefa de A4), §2.7 item 1 (precedente do
  padrão "motor pronto, endpoint pendente de RFC" que você replica para preferências de colunas), e a
  linha de ownership da tag `espelhos`/`fechamentos` em §5 (para confirmar que **só** `pdf.py` é exceção
  de ownership desta fase, nunca `espelho.py` nem os demais arquivos do pacote).
- `apps/api/app/workflow/fechamento/espelho.py` — leia o módulo inteiro, **só leitura, você não edita**.
  É o padrão de "ler apuração materializada por período/vínculo, sem recalcular" que todo dataset desta
  fase replica, e é de onde vem `saldoBancoMinutos` (reaproveitando `obter_saldo_banco_horas`).
- `apps/api/app/workflow/fechamento/pdf.py` — leia o módulo inteiro. É o **único** arquivo de F10 que você
  edita (A4, exceção de ownership, §5). A docstring já anuncia isto ("a F11 refina a identidade visual
  depois").
- `apps/api/app/apuracao/banco_horas/consulta.py` — `obter_extrato_banco_horas`, `obter_saldo_banco_
  horas`, `simular_banco_horas` (F4, só leitura). O dataset do relatório 3 (banco de horas) reaproveita
  `obter_extrato_banco_horas`; confirme a assinatura real antes de chamar.
- `apps/api/app/apuracao/dominio/consulta.py` — `listar_apuracoes`, `obter_apuracao`, `listar_ocorrencias`
  (F4, só leitura). **Não são wrappers que você reusa diretamente** (são paginadas para uma tela, não
  construídas para agregação/exportação em massa) — leia como referência de forma de consulta sob RLS,
  não como função a chamar.
- `apps/api/app/identidade/auditoria/hash_chain.py` — só para o dataset do relatório 19 (auditoria), que
  lê a tabela `auditoria` diretamente (não precisa da função de gravação, só de leitura simples).
- `apps/worker/worker/tarefas/relatorios.py` — leia o módulo inteiro. **Já existe, já está registrado**
  em `apps/worker/worker/tarefas/__init__.py`/`apps/worker/worker/filas.py` desde a Fase 0 (assinatura de
  `executar_relatorio` já fixada: `(ctx, *, tenant_id, execucao_id, codigo, parametros=None,
  formato="xlsx", solicitante_id=None)`). **Você preenche o corpo desta função, não cria uma tarefa
  nova, não toca em `__init__.py` nem em `filas.py`** — os dois já têm a entrada `executar_relatorio`/
  `FILA_RELATORIOS` prontas (§2.9).
- `apps/worker/worker/filas.py` — confirme `FILA_RELATORIOS = "ponto:relatorios"` e a nota já documentada
  no próprio arquivo de que o enfileiramento real usa `default_queue_name=FILA_PADRAO` (não
  `FILA_RELATORIOS`) porque um único processo `worker` consome `FILA_PADRAO` hoje — mesma observação que
  `app/workflow/fechamento/espelho.py::criar_espelhos_assincrono` (F10) já aplica. Replique o padrão, não
  invente um segundo.
- `apps/worker/worker/scheduler.py` — leia por inteiro (curto). Você acrescenta uma rotina nova
  (`verificar_agendamentos_relatorio`, §2.9/§6 T11), no mesmo padrão de `verificar_notificacoes_
  pendentes` (F10).
- `apps/api/app/core/filas.py` — leia a docstring inteira (curta): explica por que `default_queue_name=
  FILA_PADRAO` é obrigatório em todo `create_pool(...)` desta base de código, com o achado real de F9b/A3
  sobre job órfão. Você segue a mesma disciplina.
- `apps/api/app/routers/relatorios.py` — o *stub* gerado pela Fase 0 (hoje responde `501` com
  `PONTO-INT-005`). Leia como exemplo de assinatura de handler — não regere este arquivo à mão.
- `apps/api/app/schemas/contrato.py` (gerado) — confirme que `RelatorioDefinicao`, `RelatorioExecucao`,
  `RelatorioAgendamento`, `RelatorioAgendamentoCriar` já existem como modelos Pydantic. **Não edite**, é
  gerado.
- `apps/web/src/componentes/paineis/dashboard/**` (F9b, já commitado) — leia `painel-de-indicadores.tsx`
  e as cinco seções (`secao-*.tsx`) por inteiro, para saber exatamente onde o dataviz de A4 entra.
- `apps/web/src/componentes/graficos/graficos.tsx` e `paleta.ts` (F9a, design system) — leia por inteiro.
  É o que A4 reaproveita para dataviz; **não recrie estes componentes**.
- `apps/web/src/ganchos/use-indicadores-dashboard.ts` — leia a docstring de topo por inteiro: já documenta
  por que cada gancho de dashboard tem nome de arquivo próprio por agente, para não colidir. A4 segue o
  mesmo padrão com `use-dataviz-dashboard.ts`.
- `apps/web/src/ganchos/use-espelho-de-ponto.ts` (F8, já commitado) — leia para confirmar que o refino de
  PDF de A4 não exige nenhuma mudança neste arquivo (mesmo contrato, mesmo hook, só o PDF muda no
  servidor).
- `apps/api/pyproject.toml`, `apps/worker/pyproject.toml` — confirme por si mesmo o que já existe
  (`reportlab`, `minio`, `openpyxl`) e o que falta (`openpyxl` na API, `croniter`/`httpx` no worker),
  §2.5.
- `apps/api/tests/f4/performance/test_performance_recalculo.py` — leia como referência de forma para o
  teste de performance desta fase (§7/§8), sem reaproveitar nenhuma fixture que dependa de `apurar_dia`.

## 4. Contratos

**Consome** — já existe, esta fase apenas usa:

- Tabelas `relatorio_definicoes`, `relatorio_agendamentos`, `relatorio_execucoes`, `preferencias_colunas`
  — todas já existem desde a Fase 0 (`schema.sql` §16, `0001_inicial.py`). Você faz o CRUD/execução
  completos sobre elas, incluindo `PreferenciaColunas` via HTTP (RFC-015, já decidida).
- Tabelas `apuracoes_dia`, `apuracao_componentes`, `ocorrencias`, `tratamentos`, `afastamentos`,
  `bh_lancamentos`, `bh_contas`, `espelhos`, `assinaturas_espelho`, `fechamentos`, `periodos`,
  `auditoria`, `acessos_dados_sensiveis`, `consentimentos`, `solicitacoes_titular`, `afd_arquivos`,
  `aej_arquivos`, `dispositivos`, `terminais`, `colaboradores`, `vinculos`, `contratos`, `cargos`,
  `empresas`, `unidades`, `departamentos`, `centros_custo`, `equipes`, `escalas`, `turnos`, `marcacoes`
  (só o dataset do relatório 9, §2.3) — **somente leitura, em todas**. Nenhuma linha desta fase escreve
  em qualquer uma delas.
- Módulo `app.apuracao.banco_horas.consulta.obter_extrato_banco_horas`/`obter_saldo_banco_horas` (F4) —
  leitura, reaproveitada pelo dataset do relatório 3. Assinatura real conforme o código.
- Módulo `app.identidade.auditoria.hash_chain._json_canonico` (F1) — só se você precisar comparar hash em
  algum dataset (por exemplo, conferir que o espelho listado no relatório 1 não foi adulterado); não é
  obrigatório para a maioria dos datasets.
- Andaime da API (`app/core/erros.py`, `app/core/catalogo_erros.py`, `app/core/contexto.py`, `app/core/
  seguranca.py`, `app/db/sessao.py`, `app/core/config.py`, `app/core/filas.py`), modelos Pydantic gerados
  em `app/schemas/contrato.py`, modelos SQLAlchemy do pacote `ponto_contracts`.
- Catálogo de permissões já semeado — `relatorios.{ler,executar,criar,exportar}` (`agendamentos.*` está
  semeado mas vestigial, §2.8 item 3).
- `apps/api/app/routers/__init__.py` — **já registra** o roteador `relatorios` na ordem correta. Você não
  toca neste arquivo.
- `apps/worker/worker/tarefas/__init__.py`, `apps/worker/worker/filas.py` — **já têm** a entrada
  `executar_relatorio`/`FILA_RELATORIOS` desde a Fase 0. Você não acrescenta nem remove linha aqui; só
  preenche o corpo de `apps/worker/worker/tarefas/relatorios.py`.
- `apps/worker/worker/scheduler.py::montar_cron()` — você **acrescenta** uma entrada nova
  (`verificar_agendamentos_relatorio`), nunca remove ou reordena as existentes (F4/F6/F10).
- Função `fn_tenants_ativos()` (`schema.sql`, criada por F10/A3, RFC-014) — **reaproveitada, sem criar
  nova função `SECURITY DEFINER`**, pela rotina de cron de agendamento (§2.9/§6 T11).

**Produz** — esta fase implementa:

*Endpoints (6 operações; hoje `501`):*

| Operação | Agente |
|---|---|
| `listarRelatorios`, `obterRelatorio` | A1 |
| `executarRelatorio` (caminho síncrono) | A1 |
| `obterExecucaoRelatorio` | A1 |
| `listarAgendamentosRelatorio`, `criarAgendamentoRelatorio` | A3 |

A permissão exigida por operação é o valor de `x-permissao` no `openapi.yaml` (§2.1/§2.8). Use exatamente
esse valor.

*Tarefa assíncrona preenchida:* `executar_relatorio` (`apps/worker/worker/tarefas/relatorios.py`), A1
(esqueleto/roteamento por dataset) + A3 (exportação/streaming/entrega de agendamento).

*Tabelas escritas:* `relatorio_execucoes` (uma linha por execução, síncrona ou assíncrona),
`relatorio_agendamentos` (CRUD via `criarAgendamentoRelatorio`), `preferencias_colunas` (via o módulo
interno do §2.4, exposto pelas rotas HTTP da RFC-015). Nenhuma outra tabela é escrita por esta fase —
`relatorio_definicoes` é **semeada** (uma vez, pelas 24 linhas do §2.2, por tenant, no mesmo padrão de
dado de fábrica que `seed_dev.py` já usa para tipos — decida com o orquestrador se isto entra em
`seed_dev.py` ou num script de seed próprio de tenant novo, já que `seed_dev.py` é dado de fábrica de
**um** tenant de desenvolvimento, não o mecanismo de provisionamento de tenant novo em produção; se não
existir um mecanismo de "semear catálogo de fábrica para tenant novo" ainda no sistema, isto é achado de
contrato/arquitetura — registre em `docs/backlog.md`, não invente um novo caminho de provisionamento
nesta fase), nunca escrita por uma rota HTTP desta fase.

*Módulos internos publicados para outras fases (assinatura fixada por este PCF):*

- `app.relatorios.motor.executar_dataset(sessao, tenant_id, definicao: RelatorioDefinicao, *, filtros,
  colunas, agrupamento, cursor, limite) -> ResultadoRelatorio` (dataclass própria do módulo) — o coração
  do motor genérico (A1), chamado tanto pelo caminho síncrono da API quanto pela tarefa assíncrona do
  worker.
- `app.relatorios.catalogo.registrar_dataset(nome: str, funcao: Callable) -> None` /
  `app.relatorios.catalogo.obter_dataset(nome: str) -> Callable` — o registro de datasets (A1 cria o
  mecanismo; A2/A3/A4 registram os 24 datasets nele, cada um em seu próprio módulo).
- `app.relatorios.exportadores.{csv,xlsx,pdf}.exportar(linhas: Iterable[dict], colunas, *, destino) ->
  None` (A3) — streaming para arquivo; reaproveitado por A2/A4 sem duplicar lógica de formatação.
- `app.relatorios.preferencias.{salvar_preferencia,obter_preferencia,listar_preferencias}` (A1, §2.4).
- **Assinaturas fixadas por este PCF** — se mudarem, atualize todos os usos no mesmo commit.

*Eventos publicados:* nenhum (§3, confirmado que não existe evento de domínio para relatório/agendamento
em `events.yaml`).

**Não toca** — é de outra fase, mesmo que pareça relacionado:

- **Cálculo, apuração, banco de horas, recálculo** — F4, já concluída. Você só lê `apuracoes_dia`/
  `apuracao_componentes`/`bh_lancamentos`; nunca chama `apurar_dia`/`recalcular_periodo` (§2.3, proibição
  1).
- **Marcação em si** — F5, já concluída. Você só lê `marcacoes`, e só no dataset do relatório 9 (§2.3).
- **Workflow de solicitação/aprovação, fechamento, geração/assinatura de espelho** — F10, já concluída.
  Você só lê `espelhos`/`assinaturas_espelho`/`fechamentos`/`periodos`/`solicitacoes`/`aprovacoes`;
  **nunca** chama `gerar_espelho_do_vinculo`, `criarFechamento`, `assinarEspelho` ou qualquer rota da tag
  `espelhos`/`fechamentos`/`solicitacoes`/`aprovacoes`. A única exceção de ownership (não de leitura) é
  `apps/api/app/workflow/fechamento/pdf.py`, §5.
- **AFD, AEJ, assinatura CAdES, `rep_ps`** — F12, ainda não construída. Você só lê `afd_arquivos`/
  `aej_arquivos` para o dataset 23 (histórico); nunca gera nem assina um arquivo fiscal.
- **Entrega de webhook com HMAC/retentativa/DLQ, a tag `webhooks`** — F13. O canal `webhook` de
  `relatorio_agendamentos` (§2.8) é um `POST` simples de notificação de conclusão, não o mesmo mecanismo.
- **Exportação de folha para sistema de terceiros via integração** (`integracoes_folha`, permissão
  semeada) — fora desta fase; o relatório 17 ("Extrato para folha") é um **relatório exportável**
  (CSV/XLSX/PDF pelo mecanismo genérico), não uma integração ativa com sistema de terceiro.
- **Painel RH/gestor existente** (`apps/web/src/componentes/paineis/dashboard/**`, F9b) — você **estende**
  (A4, dataviz), nunca reescreve as seções existentes nem os cartões de KPI já entregues.
- `packages/contracts/**` — **congelado**, exceto os dois endpoints de preferências de colunas já
  decididos pela RFC-015 (§2.4), que T1 aplica diretamente. Qualquer outra mudança de contrato segue o
  protocolo normal (RFC nova).
- `apps/mobile`, `apps/device-gw`, `apps/facial-svc`.

## 5. Ownership de arquivos

Caminhos **exclusivos** desta fase.

| Agente | Caminhos |
|---|---|
| **A1** (engine + tela genérica) | `apps/api/app/relatorios/__init__.py`, `motor.py`, `catalogo.py`, `execucao.py`, `preferencias.py`, `paginacao.py` (novo pacote)<br>`apps/api/app/routers/relatorios.py` (as quatro operações do §4)<br>`apps/api/tests/f11/motor/**`, `apps/api/tests/f11/preferencias/**`<br>`apps/web/src/app/painel/relatorios/**` (novo)<br>`apps/web/src/componentes/paineis/relatorios/**` (novo)<br>`apps/web/src/ganchos/use-relatorios.ts` (novo) |
| **A2** (relatórios operacionais, itens 2-12) | `apps/api/app/relatorios/datasets/operacionais.py` (novo — os 11 datasets, cada um uma função registrada em `catalogo.py` de A1)<br>`apps/api/tests/f11/datasets_operacionais/**` |
| **A3** (relatórios gerenciais/fiscais, exportadores, agendamento) | `apps/api/app/relatorios/datasets/gerenciais.py` (novo — os 12 datasets dos itens 13-24)<br>`apps/api/app/relatorios/exportadores/**` (novo: `csv.py`, `xlsx.py`, `pdf.py`, `decimal.py`)<br>`apps/api/app/relatorios/agendamentos.py` (novo — CRUD de `relatorio_agendamentos`)<br>`apps/api/app/relatorios/entrega/**` (novo: `email.py`, `webhook.py`, `minio.py` — canais de entrega do agendamento)<br>`apps/api/app/routers/relatorios.py` (as duas operações de agendamento, §4 — **arquivo compartilhado com A1**, ver linha abaixo)<br>`apps/worker/worker/tarefas/relatorios.py` (preenche o stub existente — parte de exportação/entrega; a parte de roteamento por dataset é de A1, combine a fronteira exata entre os dois antes de escrever, mesmo padrão de combinação que F10 usou entre A1/A4 para `afastamentos.py`)<br>`apps/worker/worker/scheduler.py` (acrescenta `verificar_agendamentos_relatorio`)<br>`apps/api/tests/f11/datasets_gerenciais/**`, `apps/api/tests/f11/exportadores/**`, `apps/api/tests/f11/agendamentos/**` |
| **A4** (espelho oficial, PDF, dataviz) | `apps/api/app/relatorios/datasets/espelho_oficial.py` (novo — o dataset do item 1)<br>`apps/api/app/workflow/fechamento/pdf.py` (**exceção de ownership**, arquivo de F10/A2 — só este arquivo, só refino visual, ver nota abaixo)<br>`apps/api/app/relatorios/entrega/espelho_email.py` (novo — agendamento de envio do espelho por e-mail; reaproveita `app/relatorios/entrega/email.py` de A3 se a fronteira permitir, combine antes de escrever)<br>`apps/web/src/componentes/paineis/dashboard/**` (**só os arquivos `secao-*.tsx` já existentes, para adicionar gráfico** — não cria seção nova sem necessidade, não toca `painel-de-indicadores.tsx`/`cartao-de-kpi.tsx`/`seletor-de-escopo.tsx` a menos que precise passar um parâmetro novo, combine com o dono original se precisar)<br>`apps/web/src/ganchos/use-dataviz-dashboard.ts` (novo)<br>`apps/api/tests/f11/espelho_oficial/**`, `apps/api/tests/f11/pdf_espelho/**` |

**Compartilhado dentro da fase** (exige combinação entre os agentes da fase):

| Caminho | Regra |
|---|---|
| `apps/api/app/relatorios/__init__.py` | Criado por **A1** na T1 (primeira tarefa de código da fase), docstring e nada mais. Ninguém acrescenta código aqui. |
| `apps/api/app/routers/relatorios.py` | **A1** implementa as quatro operações de catálogo/execução; **A3** implementa as duas de agendamento. Mesmo arquivo, seções claramente separadas por comentário — combine a ordem exata (a mesma ordem do `openapi.yaml`) antes de qualquer um dos dois commitar. |
| `apps/worker/worker/tarefas/relatorios.py` | **A1** define o roteamento (`codigo` → dataset → chama `executar_dataset`); **A3** define a exportação para arquivo, upload ao MinIO e (quando `agendamento_id` não é nulo) a entrega pelo canal configurado. Combine a assinatura interna exata entre os dois antes de escrever — mesmo padrão de fronteira que F10 usou entre A1/A2 em `apps/worker/worker/tarefas/fechamento.py`. |
| `apps/api/app/relatorios/catalogo.py` | **A1** cria o mecanismo de registro (T2); **A2**, **A3** e **A4** só **chamam** `registrar_dataset(...)` dos próprios módulos (`datasets/operacionais.py`, `datasets/gerenciais.py`, `datasets/espelho_oficial.py`) — ninguém edita `catalogo.py` além de A1. |
| `apps/api/app/relatorios/entrega/email.py` (A3) vs. `apps/api/app/relatorios/entrega/espelho_email.py` (A4) | Dois arquivos distintos de propósito: A3 entrega **relatórios exportados** (arquivo genérico) por e-mail; A4 entrega **o espelho oficial já assinado** (PDF específico do vínculo, pode incluir lógica de "pegar a versão mais recente assinada") por e-mail. Se a lógica de baixo nível de envio SMTP for idêntica, A4 importa uma função utilitária exposta por A3 (combine o nome exato antes de escrever); nenhum dos dois duplica o adaptador provisório de e-mail (§2.9). |
| `apps/api/tests/f11/conftest.py` | Só **A1** edita (T1). Fixture com tenant + empresa + unidade + colaborador com vínculo + jornada simples + as 24 linhas de `relatorio_definicoes` semeadas (dado de fábrica desta fixture, mesmo padrão de `seed_dev.py`) + um `Periodo` fechado com `apuracoes_dia`/`apuracao_componentes`/`ocorrencias`/`tratamentos` sintéticos inseridos **por `INSERT` em lote, nunca via `apurar_dia`** (§2.3). A2, A3 e A4 **usam** a fixture; não editam — se precisarem de um dado a mais, pedem a A1. |

**Compartilhado com outras fases (arquivo congelado) — exceção única e explícita:**

`apps/api/app/workflow/fechamento/pdf.py` (F10/A2). A própria docstring do arquivo já anuncia esta
exceção ("a F11 refina a identidade visual depois, sobre os mesmos dados"), e a proibição 9 do PCF de F10
confirma que investir em layout ali "é desperdício desta fase" — dela, não desta. **A4 edita apenas este
arquivo**, nunca `espelho.py` (montagem de dados, continua congelado, você só lê `conteudo`/`hash_sha256`
já prontos), nunca `assinatura.py`, `conferencia.py`, `periodos.py`, `servico.py`, `escopo.py`,
`paginacao.py`, `eventos.py`, `erros_bd.py` do mesmo pacote. A assinatura da função `gerar_pdf_espelho`
(`conteudo, *, hash_sha256, versao, tipo, assinaturas=None`) é o contrato entre os dois arquivos — não
mude a assinatura sem verificar que `espelho.py` (que você não edita) continua chamando-a exatamente
assim.

**Explicitamente fora do seu ownership** (não edite, nem "só para arrumar"):
`packages/contracts/**` (exceto os dois endpoints da RFC-015, §2.4, já decidida), `apps/api/app/schemas/
contrato.py` (gerado), `apps/api/app/core/**`, `apps/api/app/db/sessao.py`, `apps/api/app/main.py`,
`apps/api/app/routers/__init__.py`, qualquer outro roteador (`apuracoes.py`, `tratamentos.py`,
`banco_horas.py`, `espelhos.py`, `fechamentos.py`, `solicitacoes.py`, `aprovacoes.py`, `afastamentos.py`,
`fiscal.py`, `webhooks.py`, `integracoes.py`, etc.), `apps/api/app/apuracao/**` (F4, só leitura),
`apps/api/app/workflow/**` exceto a única exceção acima (F10, só leitura), `apps/api/app/notificacao/**`
(F10), `apps/api/app/identidade/**`, `apps/api/app/jornada/**`, `apps/api/app/marcacao/**`,
`apps/api/app/organizacao/**`, `apps/api/app/pessoas/**`, `apps/api/app/biometria/**`,
`apps/api/migrations/**`, `apps/api/tests/test_andaime.py`, `apps/worker/worker/tarefas/apuracao.py`,
`fechamento.py` (exceto a linha compartilhada acima), `fiscal.py`, `notificacoes.py`, `importacoes.py`,
`integracoes.py`, `lgpd.py`, `apps/worker/worker/main.py`, `.github/workflows/**`, `infra/**`, `Makefile`,
`tasks.ps1`, `apps/web/**` exceto os diretórios explicitamente listados na tabela acima,
`apps/mobile/**`.

> **Nenhuma migration nova nesta fase.** As quatro tabelas do grupo 16 já existem em `0001_inicial.py`.
> A RFC-015 (§2.4) muda só `openapi.yaml`/`schemas`, nunca `schema.sql` — a tabela `preferencias_colunas`
> já existe e já tem todas as colunas necessárias.

## 6. Tarefas (T1..T16)

### T1 — Aplicar a RFC-015, módulos de fronteira e fixture da fase
**Agente:** A1 (código) — todos os demais dependem desta tarefa
**Descrição:** Aplica a RFC-015 (já decidida, §2.4) em `packages/contracts/openapi.yaml`/`schemas/
contrato.py`: os dois endpoints de preferências de colunas, exatamente como especificado na seção
"Decisão do orquestrador" da RFC. Cria `apps/api/app/relatorios/__init__.py` (docstring e nada mais),
`apps/api/tests/f11/conftest.py` (fixture descrita em §5, incluindo as 24 linhas de `relatorio_
definicoes` do §2.2 e dados sintéticos de apuração inseridos por `INSERT` em lote). Cria o módulo interno
de preferências (`app/relatorios/preferencias.py`) com as três funções fixadas em §4, e os dois handlers
HTTP novos em `app/routers/relatorios.py` que os consomem.
**Pronto quando:** `pytest apps/api/tests/f11 -q` coleta e a fixture sobe/derruba o banco sem erro; a
RFC-015 está marcada `Implementada` no seu cabeçalho; teste de integração prova que `PUT` seguido de
`GET` numa sessão nova devolve exatamente a mesma configuração por `usuario_id` + `relatorio_
definicao_id`, e que a constraint `uq_preferencias_colunas` recusa duplicata.

### T2 — Motor genérico: catálogo de datasets, filtros, colunas, agrupamento, paginação
**Agente:** A1
**Descrição:** `app/relatorios/catalogo.py`: `registrar_dataset`/`obter_dataset` (§4). `app/relatorios/
motor.py::executar_dataset` — recebe a `RelatorioDefinicao`, resolve o dataset, aplica filtros compostos
(período, empresa/unidade/departamento/colaborador, mais os específicos de cada relatório, declarados em
`filtros_disponiveis`), projeta só as colunas pedidas (`colunas` da query, na ordem pedida — decida e
documente o formato interno de `colunas_disponiveis`, por exemplo uma lista de `{chave, rotulo, tipo,
duracao: bool}`), aplica agrupamento quando `agrupamento` for informado (SQL `GROUP BY`, nunca em
Python), pagina com cursor (mesmo padrão de `app/workflow/fechamento/paginacao.py`, F10, reaproveite a
FORMA, não importe o módulo de outra fase — replique). **Toda consulta é SQLAlchemy Core/`select()`
parametrizado — nunca SQL cru montado por concatenação de string, mesmo que `dataset` já garanta que o
valor não vem do usuário.**
**Pronto quando:** teste prova que o motor aplica filtro de período + escopo corretamente contra um
dataset de exemplo; teste prova que pedir colunas fora de `colunas_disponiveis` responde `PONTO-VAL-005`;
teste de propriedade prova que agrupar por `departamento` soma corretamente contra dado sintético
conhecido (soma calculada à mão).

### T3 — Execução síncrona/assíncrona, `RelatorioExecucao`, handlers HTTP de catálogo
**Agente:** A1
**Descrição:** `app/relatorios/execucao.py`: decide síncrono vs. assíncrono (regra fixada: `assincrono=true`
explícito, **ou** `RelatorioDefinicao.assincrono=true`, **ou** intervalo de datas pedido acima de um
limiar configurável — documente o valor escolhido e a justificativa) — síncrono chama `executar_dataset`
direto e devolve o resultado no formato pedido; assíncrono cria `RelatorioExecucao(status='enfileirado')`
e enfileira `executar_relatorio` no worker com `default_queue_name=FILA_PADRAO` (§2.9, nunca
`FILA_RELATORIOS` sozinho, mesmo padrão de `espelho.py::criar_espelhos_assincrono`). `app/routers/
relatorios.py`: `listarRelatorios`, `obterRelatorio`, `executarRelatorio`, `obterExecucaoRelatorio`.
**Pronto quando:** teste prova que um relatório pequeno (um vínculo, um mês) responde `200` síncrono;
teste prova que pedir 12 meses × 1.000 vínculos sintéticos (fixture de T1) responde `202` com
`RelatorioExecucao(status='enfileirado')`; teste prova que `obterExecucaoRelatorio` de uma execução
inexistente responde `PONTO-REC-001` e de uma expirada responde `PONTO-REC-002`.

### T4 — Tela genérica de relatórios em `apps/web`
**Agente:** A1
**Descrição:** `apps/web/src/app/painel/relatorios/**`: catálogo (lista os 24, filtro por categoria),
página de execução com formulário **construído dinamicamente a partir de `RelatorioDefinicao`**
(filtros/colunas/agrupamento/formato), seletor de colunas com arrastar-para-reordenar e "salvar como
padrão" (consumindo `use-relatorios.ts`, que por sua vez chama os dois endpoints reais de preferências de
colunas da RFC-015, §2.4 — já decidida e implementada por T1, sem fallback de `localStorage`),
acompanhamento de progresso (poll de `obterExecucaoRelatorio` a cada N segundos) e botão de download.
**Pronto quando:** a tela roda os 24 relatórios do catálogo (mesmo componente, dados diferentes) sem
código condicional por `codigo` específico; teste de componente prova que o seletor de colunas reflete
exatamente `colunasDisponiveis` da definição carregada.

### T5 — Exportadores genéricos (CSV, XLSX, PDF) e conversão decimal
**Agente:** A3
**Descrição:** `app/relatorios/exportadores/csv.py` (módulo `csv` nativo, streaming linha a linha para um
arquivo/buffer), `xlsx.py` (`openpyxl`, escreve em streaming usando `write_only=True` do próprio
`openpyxl` para não materializar a planilha inteira em memória), `pdf.py` (`reportlab`, layout tabular
simples — cabeçalho com nome do relatório/período/filtros aplicados, tabela paginada, rodapé com data de
geração; **não** é o mesmo módulo nem o mesmo layout do espelho, é um relatório tabular genérico),
`decimal.py` (conversão minutos→horas decimais, aplicada só na coluna marcada como duração no catálogo,
nunca no dado bruto). Todos expõem a assinatura `exportar(linhas, colunas, *, destino) -> None` (§4).
**Pronto quando:** teste prova que exportar um dataset sintético de 10.000 linhas em XLSX não estoura
memória (medição de pico de RSS do processo de teste, ou prova indireta por streaming comprovado via
mock de escrita incremental); teste prova que `converterDecimal=true` produz `2.50` para 150 minutos e
que o dado interno continua em minutos inteiros.

### T6 — Tarefa assíncrona do worker: roteamento, streaming para MinIO, progresso
**Agentes:** A1 (roteamento) + A3 (exportação/upload/entrega) — combinar a fronteira exata antes de
escrever (§5)
**Descrição:** Preenche `apps/worker/worker/tarefas/relatorios.py::executar_relatorio` substituindo
`resultado_nao_implementado(...)`: resolve `codigo` → `RelatorioDefinicao` → dataset (A1), executa via
`executar_dataset` com cursor do servidor, escreve no exportador certo conforme `formato` (A3) atualizando
`RelatorioExecucao.progresso` periodicamente (por exemplo, a cada lote de N linhas), faz upload ao MinIO
(`app/comum/armazenamento.py`, reaproveitado de F10 — só leitura desse módulo, você não o edita), grava
`conteudo_ref`/`tamanho_bytes`/`hash_sha256`/`total_linhas`/`duracao_ms`/`concluido_em`, `status=
'concluido'`; em erro, `status='falhou'` com `erro` preenchido, nunca deixa a linha presa em
`'processando'`. Se `agendamento_id` não é nulo, chama a entrega do canal configurado (A3, T11) ao final.
**Pronto quando:** teste (com fixture de worker, reaproveitando o padrão que F4/F10 já estabeleceram)
prova que uma execução de 372.000 linhas sintéticas conclui com `progresso=100`, `status='concluido'`,
hash correto; teste prova que uma falha no meio do processamento marca `status='falhou'` sem deixar
`'processando'` pendurado.

### T7 — Datasets operacionais, parte 1 (relatórios 2-6)
**Agente:** A2
**Descrição:** `app/relatorios/datasets/operacionais.py` (início do arquivo): funções de consulta para
`espelho-jornada` (30+ colunas, ver a lista literal de `PROJETO.md` §9 item 2 — nome, matrícula, cargo,
equipe, turno, gestor, horário previsto, previsto/trabalhado, normais, extras diurnas/noturnas por fator,
intrajornada, sobreaviso, faltas, intervalos, horas faltantes, adicional noturno, crédito/débito DSR,
banco de horas, pausas NR-17, feriados, motivos/observações, marcações), `banco-de-horas` (reaproveita
`obter_extrato_banco_horas` de F4), `horas-extras` (`apuracao_componentes` filtrado por `categoria=
'extra'`), `adicional-noturno` (`categoria='noturno'`), `absenteismo` (agregação de `falta_minutos`/dias
não trabalhados por colaborador/período, com índice = faltas/dias úteis previstos). Registra cada um em
`catalogo.py` de A1 (`registrar_dataset`).
**Pronto quando:** cada um dos cinco datasets tem teste próprio contra a fixture de T1, provando que a
soma das colunas numéricas bate com a soma direta em `apuracoes_dia`/`apuracao_componentes` para o mesmo
escopo (prova de que a agregação do dataset não diverge da fonte).

### T8 — Datasets operacionais, parte 2 (relatórios 7-12)
**Agente:** A2
**Descrição:** Continua `operacionais.py`: `atrasos-saidas-antecipadas` (`atraso_minutos`/`saida_
antecipada_minutos`), `faltas` (`falta_minutos` + join com `tratamentos` categoria `abono`/`justificativa`
para mostrar se a falta já tem tratamento associado), `tempo-real` (**único dataset que lê `marcacoes`
diretamente, não `apuracoes_dia`** — para cada vínculo do escopo, a última marcação do dia sem par de
saída ainda registrado = "trabalhando agora"; documente explicitamente esta exceção no docstring da
função, citando §2.3 deste PCF), `ocorrencias` (todos os 18 códigos de `ocorrencias.codigo`, com filtro
por `codigo`/`severidade`/`status`), `abonos-justificativas` (`tratamentos` categoria `abono`/
`justificativa`), `ferias-afastamentos` (`afastamentos`, todas as categorias de `tipos_afastamento`).
**Pronto quando:** teste prova que o dataset `tempo-real` nunca lê `apuracoes_dia` (prova por análise
estática/grep do módulo, mesmo padrão de prova que F10 já usou para "nenhuma escrita direta em
apuracoes_dia"); teste prova que `faltas` reflete corretamente a lacuna do ADR-011 (uma falta com
tratamento `afastamento` retroativo aprovado continua aparecendo como falta, não é escondida) — teste que
documenta o comportamento real, não o esconde, mesmo padrão que F10/A4 já fez para o mesmo achado.

### T9 — Datasets gerenciais/fiscais, parte 1 (relatórios 13-19)
**Agente:** A3
**Descrição:** `app/relatorios/datasets/gerenciais.py` (início): `escalas-previsto-realizado` (join
`apuracoes_dia`/`escalas`/`turnos` por `jornada_id`/`escala_id`/`turno_id`), `violacoes-intrajornada`
(`intrajornada_suprimida_minutos` + `ocorrencias` código `intrajornada_suprimida`), `violacoes-
interjornada` (`interjornada_minutos`/`interjornada_violada` + ocorrência `interjornada_violada`),
`horas-por-centro-custo` (agrupamento por `centro_custo_id`), `extrato-para-folha` (agregação mensal de
`apuracao_componentes` por colaborador — layout simples, sem integração real com parceiro de folha, §4),
`movimentacao-pessoal` (admissões/desligamentos via `contratos`/`vinculos`, aniversariantes via
`colaboradores.data_nascimento` se existir — confirme o nome exato do campo), `auditoria` (leitura direta
de `auditoria`, sem usar `gravar_auditoria`, só consulta).
**Pronto quando:** cada um dos sete datasets tem teste próprio; teste do dataset `auditoria` prova que
filtrar por `entidade`/`acao`/período funciona contra linhas sintéticas conhecidas.

### T10 — Datasets gerenciais/fiscais/financeiro/lgpd, parte 2 (relatórios 20-24)
**Agente:** A3
**Descrição:** Continua `gerenciais.py`: `dispositivos-canais` (uso por canal de `marcacoes.canal`,
terminais offline via `terminais`/`dispositivos`), `custo-horas-extras` (`apuracao_componentes` categoria
`extra` × `cargos.salario_base`, valor-hora × minutos_equivalentes/60 — documente a fórmula exata),
`headcount-por-area` (contagem de `vinculos` ativos por `departamento_id`), `arquivos-fiscais-historico`
(leitura de `afd_arquivos`/`aej_arquivos`, pode devolver zero linhas nesta fase, §2.2), `lgpd-acessos-e-
titulares` (leitura de `acessos_dados_sensiveis` + `solicitacoes_titular`, respeitando qualquer RLS/
sensibilidade já imposta por essas tabelas — você não adiciona controle de acesso novo, herda o que já
existe).
**Pronto quando:** cada um dos cinco datasets tem teste próprio; teste do dataset `custo-horas-extras`
prova o cálculo contra um caso de mesa (cargo com salário conhecido, X minutos de hora extra a fator
1.5 → valor esperado calculado à mão).

### T11 — Agendamento: CRUD, cron, scheduler e canais de entrega
**Agente:** A3
**Descrição:** `app/relatorios/agendamentos.py`: `listarAgendamentosRelatorio`, `criarAgendamentoRelatorio`
(valida `cron` com `croniter`, calcula `proxima_execucao_em` na criação; recusa `relatorioDefinicaoId`
inexistente com `PONTO-REC-001`). `app/relatorios/entrega/{email,webhook,minio}.py`: `entregar(execucao,
agendamento) -> bool` (interface fixada) — `email.py` usa o adaptador provisório "log + marca como
entregue" (mesmo tratamento documentado em `docs/fases/F10-workflows-aprovacoes-fechamento.md` §2.8, sem
credencial SMTP real disponível, `# TODO F11+N: trocar por SMTP real quando houver credencial`; **não
importa** `app/notificacao/canais/email.py` de F10 diretamente — módulo próprio, mesma disciplina, §5);
`webhook.py` faz um `POST` HTTP simples (via `httpx`) com a URL de download e metadados, sem HMAC/
retentativa/DLQ (isso é F13, tag `webhooks`, fora de escopo); `minio.py` é um no-op documentado (o arquivo
já está no MinIO ao final da execução, "entregar" por este canal só confirma). `apps/worker/worker/
scheduler.py`: acrescenta `verificar_agendamentos_relatorio` a `ROTINAS`/`montar_cron()`/`__all__`
(reaproveitando `fn_tenants_ativos()`, sem criar função `SECURITY DEFINER` nova) — por tenant, busca
`relatorio_agendamentos` com `ativo=true AND proxima_execucao_em <= now()`, enfileira `executar_relatorio`
com `agendamento_id` preenchido, recalcula `proxima_execucao_em` via `croniter` e atualiza a linha.
**Pronto quando:** teste prova que criar um agendamento com `cron` inválido responde `PONTO-VAL-001`;
teste prova que a rotina de varredura não duplica execução para o mesmo agendamento na mesma janela
(idempotência); teste prova que os três canais chamam `entregar` com o payload certo (mock de rede para
`webhook`/`email`, verificação de objeto real para `minio`).

### T12 — Dataset do espelho oficial (relatório 1) e refino visual do PDF
**Agente:** A4
**Descrição:** `app/relatorios/datasets/espelho_oficial.py::espelho_oficial` — lê `espelhos`/
`assinaturas_espelho` (F10, só leitura) filtrados por período/escopo/`tipo='oficial'` ou `'retificado'`,
devolve uma linha por espelho encontrado (vínculo, período, versão, status de assinatura, URL de
download). **Não gera nenhum espelho novo** — se o filtro não encontrar nenhum espelho para o escopo
pedido, o relatório devolve zero linhas (não é erro, é reflexo do que ainda não foi fechado/gerado por
F10). `apps/api/app/workflow/fechamento/pdf.py` (exceção de ownership, §5): refina o layout visual
(tipografia do design system de F9a, cores da paleta oficial, cabeçalho legal já existente mantido
**exatamente igual em conteúdo**, só muda a apresentação) — **a assinatura `gerar_pdf_espelho(conteudo,
*, hash_sha256, versao, tipo, assinaturas=None)` não muda**, e todo campo textual exigido pela Portaria
671/2021 que já está no PDF de F10 continua presente, campo a campo (critério de aceite 4).
**Pronto quando:** teste prova que o dataset `espelho-oficial` reflete corretamente os espelhos já
existentes na fixture sem gerar nenhum novo (grep/análise estática confirma que o módulo nunca importa
`gerar_espelho_do_vinculo`); teste de conteúdo textual extraído do PDF novo (mesmo padrão de F10, via
`pypdf`) prova que todo campo do PDF antigo continua presente byte a byte no PDF novo, só o layout muda.

### T13 — Entrega do espelho por e-mail e dataviz dos dashboards
**Agente:** A4
**Descrição:** `app/relatorios/entrega/espelho_email.py` — agendamento de envio do espelho oficial mais
recente e assinado de um vínculo/período por e-mail (reaproveita a função utilitária de baixo nível de
A3 se a fronteira do §5 permitir; combine antes de escrever). `apps/web/src/componentes/paineis/
dashboard/secao-apuracao.tsx`/`secao-banco-de-horas.tsx`/`secao-ocorrencias.tsx`: adiciona gráfico
(`GraficoDeBarras`/`GraficoDeLinha` de `apps/web/src/componentes/graficos/graficos.tsx`, F9a) alimentado
por `executarRelatorio` com `formato=json` e agrupamento mensal (por exemplo, tendência de horas extras
dos últimos 6 meses, evolução de absenteísmo). `apps/web/src/ganchos/use-dataviz-dashboard.ts` (novo).
**Pronto quando:** teste de componente prova que cada seção renderiza o gráfico com dado mockado da forma
de `RelatorioExecucao`/resultado JSON real do motor (não um formato inventado); teste prova que o envio
de e-mail do espelho grava evidência de tentativa (mesmo padrão "log + marca como enviado" de §2.8/T11).

### T14 — Testes de performance (critério de aceite oficial)
**Agentes:** A1, A2, A3 (conjunto)
**Descrição:** `apps/api/tests/f11/performance/test_performance_relatorio.py` — semeia ~372.000 linhas de
`apuracoes_dia`/`apuracao_componentes` sintéticas (12 meses × 1.000 vínculos) por `INSERT` em lote direto
(nunca via `apurar_dia`), mede o tempo de `executar_dataset` para o relatório `espelho-jornada` (o mais
pesado, 30+ colunas) nesse volume, prova que fica abaixo de 60s **medido na máquina real (sem túnel SSH,
mesmo cuidado que o teste de performance de F4 já documenta)**, e prova que o caminho síncrono recusa
(força assíncrono) para o mesmo volume.
**Pronto quando:** o teste passa com o tempo real colado no relatório da fase; se não passar, este é o
critério de aceite que fica marcado como não atendido (mesmo tratamento honesto que o ADR-010 já deu ao
critério equivalente de F4) — não invente otimização fora do escopo desta tarefa para forçar o número.

### T15 — Testes de propriedade e e2e do catálogo completo
**Agentes:** A1, A2, A3, A4 (conjunto)
**Descrição:** `apps/api/tests/f11/e2e/test_catalogo_completo.py`: para cada um dos 24 relatórios da
fixture, executa (síncrono quando pequeno, assíncrono quando o dataset é `assincrono=true`), exporta nos
formatos declarados em `formatos`, confere que o arquivo resultante não está vazio e que o formato PDF/
XLSX abre sem erro (via `pypdf`/`openpyxl` de leitura, dependência de teste apenas). Prova, num único
teste parametrizado, o critério de aceite "os 24 relatórios do catálogo geram e exportam nos 3 formatos"
— com a ressalva documentada de que o item 1 (espelho oficial) só exporta PDF (não faz sentido CSV/XLSX
para um documento assinado; documente esta exceção explicitamente no teste, não a esconda).
**Pronto quando:** o teste parametrizado passa para os 24 códigos; a exceção do item 1 está documentada
no próprio teste com o motivo.

### T16 — Fechamento da fase
**Agentes:** A1, A2, A3 e A4
**Descrição:** Rodar todos os comandos da §8 e colar a saída real no relatório da fase, item a item
contra a §7.
**Pronto quando:** todos verdes, com saída colada, e `git status --short packages/contracts` mostra
**apenas** o diff da RFC-015 (os dois endpoints de preferências de colunas, aplicados por T1) — nenhuma
outra alteração.

## 7. Critérios de aceite

O relatório final responde item a item, com saída real colada.

1. **Os 24 relatórios do catálogo geram e exportam nos 3 formatos**: prova por T15, com a ressalva
   documentada do item 1 (só PDF).
2. **Relatório de 12 meses × 1.000 colaboradores conclui em < 60s, assíncrono com progresso**: prova por
   T14; `RelatorioExecucao.progresso` avança de 0 a 100 de forma visível durante a execução (não salta
   direto de 0 a 100).
3. **Espelho de ponto confere campo a campo com a apuração**: o dataset `espelho-jornada` (item 2) tem
   teste provando que cada coluna numérica bate com a soma direta das colunas de `apuracoes_dia`/
   `apuracao_componentes` para o mesmo vínculo/período (T7); o refino visual do espelho oficial (item 1)
   preserva byte a byte todo campo textual exigido pela Portaria 671/2021 que já existia no PDF de F10
   (T12).
4. **Colunas configuradas persistem por usuário**: teste de integração prova, via a rota HTTP real da
   RFC-015 (`PUT`/`GET /v1/relatorios/preferencias-colunas`), que salvar uma preferência e reler numa
   sessão nova devolve exatamente a mesma configuração.
5. **Nenhum dataset chama `apurar_dia`/`recalcular_periodo`**: prova por análise estática (grep) em todo
   `app/relatorios/**` mais teste de integração.
6. **Nenhuma escrita em `apuracoes_dia`, `apuracao_componentes`, `bh_lancamentos`, `espelhos`,
   `assinaturas_espelho`, `fechamentos`, `marcacoes`**: você só lê. Prova por análise estática e teste de
   integração (mesmo padrão de prova que F10 já usou para a proibição equivalente).
7. **`banco_horas`, `apuracoes`, `tratamentos`, `workflow`, `notificacao` de F4/F10 continuam verdes**:
   rodar `pytest apps/api/tests/f4 apps/api/tests/f10 -q` depois das mudanças desta fase, sem regressão.
8. **Toda rota declara `Depends(exigir_permissao(...))`** com exatamente o `x-permissao` do contrato —
   verificável pelo mesmo teste que F4/F10 já escreveram (reaproveite o padrão).
9. **Cobertura ≥ 90%** em `app.relatorios` (`--cov=app.relatorios --cov-report=term-missing`), saída real
   colada.
10. **Contrato só com o diff da RFC-015**: `git status --short packages/contracts` mostra exatamente os
    dois endpoints de preferências de colunas já decididos, nenhuma outra alteração.
11. **`apps/web` só tem os arquivos listados no §5**: `git status --short apps/web` mostra apenas os
    diretórios/arquivos novos de A1/A4 já autorizados.
12. **A tela genérica de relatórios roda os 24 sem código condicional por relatório específico**: prova
    por leitura de código (nenhum `if codigo === '...'` na tela de execução) mais teste de componente.
13. **Dataviz reaproveita os componentes de F9a**: prova por leitura de código (nenhum novo componente de
    gráfico é criado fora de `apps/web/src/componentes/graficos/`, que continua intocado).
14. Todos os comandos da §8 verdes, com saída real colada no relatório.

## 8. Comandos de verificação

Rode a partir da **raiz do repositório**, salvo onde indicado. Windows usa `.\tasks.ps1`;
Linux/macOS usa `make`.

Subir o banco:

```bash
docker compose --env-file infra/.env.example -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d postgres redis minio
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
cd apps/api && mypy
cd apps/worker && mypy
```

```powershell
.\tasks.ps1 lint
.\tasks.ps1 typecheck
```

**Saída esperada:** `All checks passed!`, `NN files already formatted`,
`Success: no issues found in NNN source files`.

Testes da fase, com cobertura do domínio:

```bash
cd apps/api && pytest tests/f11 -q --cov=app.relatorios --cov-report=term-missing
```

```powershell
cd apps/api; pytest tests/f11 -q --cov=app.relatorios --cov-report=term-missing
```

**Saída esperada:** todos os testes passam; a linha `TOTAL` da cobertura ≥ 90%; nenhum `skip` nos testes
que exigem banco.

Regressão de F4/F10 (não pode quebrar):

```bash
cd apps/api && pytest tests/f4 tests/f10 -q
```

Performance (o critério de aceite 2, isolado para evidência no relatório):

```bash
cd apps/api && pytest tests/f11/performance -q -s
```

**Saída esperada:** o tempo real medido, abaixo de 60s, colado no relatório da fase.

Catálogo completo (o critério de aceite 1):

```bash
cd apps/api && pytest tests/f11/e2e -q -v
```

Prova de que nenhum dataset recalcula (o critério de aceite 5):

```bash
grep -rn "apurar_dia\|recalcular_periodo" apps/api/app/relatorios/ || echo "OK: nenhuma chamada encontrada"
```

Regressão do andaime da Fase 0 (não pode quebrar):

```bash
cd apps/api && pytest tests/test_andaime.py -q
```

Inventário de rotas idêntico ao contrato:

```bash
cd apps/api && python tools/conferir_rotas.py
```

**Saída esperada:** `Inventario identico ao contrato (metodo, caminho e operationId).`

Contrato só com o diff da RFC-015:

```bash
git status --short packages/contracts
git diff packages/contracts/openapi.yaml
```

`apps/web` só com os arquivos autorizados:

```bash
git status --short apps/web
```

**Saída esperada:** só os caminhos listados no §5 aparecem.

Migration continua reversível contra banco real:

```bash
cd apps/api && alembic upgrade head && alembic downgrade base && alembic upgrade head
```

Testes de frontend:

```bash
cd apps/web && npm test -- --run
```

## 9. Proibições

1. **Não chame `apurar_dia` nem `recalcular_periodo` (nem qualquer código que dispare o resolvedor de
   jornada de F3) a partir de nenhum dataset ou tarefa desta fase.** É a base inteira da estratégia de
   performance do §2.3. Um dia sem apuração materializada aparece como está, nunca é calculado sob
   demanda.
2. **Não escreva em `apuracoes_dia`, `apuracao_componentes`, `bh_lancamentos`, `ocorrencias`,
   `tratamentos`, `afastamentos`, `espelhos`, `assinaturas_espelho`, `fechamentos`, `periodos`,
   `marcacoes`, `auditoria`.** Você só lê. A única escrita desta fase é em `relatorio_execucoes`,
   `relatorio_agendamentos` e `preferencias_colunas`.
3. **Não reabra nem reescreva um período fechado, nem gere um novo espelho de ponto oficial.** Isso é
   F10. O dataset do item 1 só **lista** espelhos já existentes.
4. **Não invente uma correção compensatória para a lacuna do ADR-011** (afastamento retroativo sem efeito
   numérico). Se um dataset mostra uma falta que "deveria" estar abonada por causa de um afastamento
   retroativo aprovado, mostre exatamente o que `apuracoes_dia` diz — a lacuna é de F4, documentá-la
   fielmente é sua responsabilidade, corrigi-la não é.
5. **Não crie código de erro novo.** Os códigos `VAL`/`REC`/`CONF`/`RATE` já listados no §2.8 item 5
   cobrem tudo que esta fase precisa. Se faltar algo mesmo assim, é RFC.
6. **Não edite `packages/contracts/` além dos dois endpoints já decididos pela RFC-015.** Qualquer outra
   divergência de contrato vira RFC nova, não decisão sua.
7. **Não invente endpoint fora do contrato** — em particular, não crie `POST /v1/relatorios` (criar
   definição de relatório custom), `PATCH`/`DELETE` em `/v1/relatorios/agendamentos/{id}`, nem qualquer
   rota de preferências de colunas com forma diferente da que a RFC-015 já fixou.
8. **Não gere, assine nem valide AFD/AEJ.** O dataset do item 23 só lê `afd_arquivos`/`aej_arquivos` já
   existentes (que podem estar vazios nesta fase, F12 roda em paralelo).
9. **Não implemente entrega de webhook com HMAC/retentativa/DLQ.** O canal `webhook` de agendamento é um
   `POST` simples de notificação, não o mecanismo completo da tag `webhooks` (F13).
10. **Não implemente envio real de e-mail sem credencial SMTP configurada.** Mesmo tratamento que F10 já
    deu ao mesmo problema (§2.9/T11): adaptador provisório documentado, nunca uma chamada que pareça real
    sem ser.
11. **Não toque em nenhum arquivo de `app/workflow/fechamento/**` além de `pdf.py`.** `espelho.py`,
    `assinatura.py`, `conferencia.py`, `periodos.py`, `servico.py`, `escopo.py`, `paginacao.py`,
    `eventos.py`, `erros_bd.py` são congelados (F10, você só lê).
12. **Não crie um segundo componente de gráfico.** Dataviz reaproveita `apps/web/src/componentes/
    graficos/graficos.tsx` (F9a). Se algo que você precisa não existir lá, é achado de backlog para F9a
    revisitar, não uma segunda biblioteca de gráfico nesta fase.
13. **Não crie tela de frontend por relatório específico.** A2 e A3 não tocam `apps/web`; a tela genérica
    de A1 (dirigida pela `RelatorioDefinicao`) é a única interface de execução dos 24 relatórios.
14. **Não use os termos proibidos** da seção 6 do glossário: é *apuração* (nunca "cálculo de ponto" fora
    de texto de UI), *tratamento* (nunca "ajuste de marcação"), *colaborador*/*vínculo* (nunca
    "funcionário"), *tenant* (nunca "empresa" para dizer cliente do SaaS), *marcação* (nunca "batida").
15. **Não declare a fase pronta sem rodar os comandos da §8 e colar a saída real.** Em especial o tempo
    real medido de performance (critério de aceite 2) e a prova de que nenhum dataset chama o motor de
    cálculo (critério de aceite 5).
