# F06 — Integração Control iD (iDFace)

| | |
|---|---|
| **Onda** | 2 |
| **Agentes** | 2 · **A1** `device-gw` — sessão via `login.fcgi`, modo Push, serviço Monitor, catch-up por marca d'água, conversão para marcação canônica, cadastro/saúde/reconexão do terminal · **A2** Provisionamento — sincronização de `users`/`templates`/`groups`/`access_rules`/`portals`/`time_zones`, envio de face por `user_set_image`, `execute_actions.fcgi`, simulador de terminal |
| **Duração estimada** | 6 dias |
| **Depende de** | F0 (contratos e andaime), F2 (tabela `dispositivos`, já implementada), F5 (endpoint `POST /v1/marcacoes` e pipeline de ingestão — roda **em paralelo**, ver §2) |
| **Criticidade** | Média |
| **Branch** | `f06-integracao-control-id` |

---

## 1. Objetivo

Ao fim desta fase, **um terminal Control iD iDFace (real ou simulado) tem seu
cadastro, sincronização de usuários/faces e saúde geridos pelas 7 operações da
tag `terminais`, e todo `access_log` que ele produzir — em tempo real via
Monitor, por Push, ou recuperado por catch-up depois de uma queda de rede —
vira uma marcação canônica gravada pela API através do mesmo pipeline de
ingestão da F5, sem duplicar e sem perder nenhum registro**.

## 2. Contexto mínimo

**O terminal não é o REP-P.** REP-P — *Registrador Eletrônico de Ponto via
Programa* — é o nosso software: quem atribui o Número Sequencial de Registro
(NSR), calcula o CRC-16 e grava no AFD. O iDFace é um **coletor**: identifica a
pessoa (face, cartão, senha, QR) e produz um `access_log` — um evento local, na
tabela interna do próprio equipamento. Esta fase constrói a ponte entre os
dois: um serviço HTTP separado, `apps/device-gw`, que fala o protocolo do
fabricante de um lado e a API interna do outro. Ele fica isolado da API
principal de propósito — quarenta terminais religando depois de uma queda de
rede e despejando o backlog de `access_logs` ao mesmo tempo não podem derrubar
a API que o RH está usando.

**Dois canais de entrega, nenhum garantido sozinho.** O **modo Push** é
obrigatório na nossa topologia porque o iDFace normalmente vive em LAN sem IP
público: quem inicia a conexão é sempre o terminal, que pergunta
periodicamente "tem comando para mim?" (`POST /new_connection.fcgi`), executa
localmente o que vier e devolve o resultado (`POST /send_response.fcgi`). O
**serviço Monitor** é o complemento: o terminal, por conta própria, notifica o
servidor assim que algo acontece (`POST /api/notifications/dao` para
`access_logs` novos, `.../door`, `.../catra`, `.../template`, `.../secbox`,
`.../operation_mode` para os demais eventos) — menor latência, mas sem
garantia de entrega. Nenhum dos dois é suficiente sozinho: por isso o
**catch-up** existe e é obrigatório. Ele funciona por **marca d'água** — o
maior `access_logs.id` já coletado daquele terminal, guardado em
`terminais.ultimo_log_externo_id` — e pede ao equipamento, via
`load_objects.fcgi` sobre o objeto `access_logs` com `id > marca`, tudo que
ficou para trás enquanto a rede esteve fora. A marca só avança **depois** da
gravação confirmada: entre duplicar (inofensivo, a idempotência trata) e
perder (irreversível), a escolha é sempre não perder.

**A idempotência real é um par de UUID, não a string do fabricante.** O
`access_log` do terminal tem um `id` inteiro, local àquele equipamento; a
chave de deduplicação da marcação, no nosso schema, é
`marcacoes.dispositivo_id` (o UUID da linha em `dispositivos` correspondente a
este terminal) **mais** `marcacoes.log_externo_id` (esse mesmo `id` do
`access_log`) — ver os índices `ix_marcacoes_idem_dispositivo` e a coluna
`terminais.ultimo_log_externo_id` em `packages/contracts/schema.sql`. Todo
`access_log` recebido — por Push, por Monitor ou por catch-up — deve ser
convertido para esse par antes de chegar em `POST /v1/marcacoes`; o relógio do
equipamento (`access_logs.time`) viaja como evidência
(`MarcacaoCriar.datahoraDispositivo`), nunca como o horário oficial do fato —
quem carimba a hora real é o servidor da F5.

**`terminais` referencia `dispositivos` (F2, já concluída) e nunca escreve
biometria.** Toda linha de `terminais` tem `dispositivo_id UUID NOT NULL`
apontando para a tabela `dispositivos` (tipo `terminal`), que já existe e cujo
serviço (`app.biometria.dispositivos`) já está implementado pela F2. A operação
`POST /v1/terminais` (`TerminalCriar`) **não exige** `dispositivoId` no corpo —
quando ausente, esta fase cria o `dispositivos` correspondente antes de
inserir a linha de `terminais`, reaproveitando aquele serviço em vez de
duplicar a lógica. Nunca crie uma segunda forma de cadastrar dispositivo. Do
lado do enrollment facial, o único fato que atravessa este serviço é "fulano
cadastrou face no terminal X, na versão de modelo Y" — o vetor biométrico em
si nunca passa em claro por `device-gw` (ADR-006, decisão fechada da F2, que
você não redecide): a notificação `POST /api/notifications/template` registra
o evento, nunca o conteúdo.

**Ponto de atenção nº 1 — resolução de terminal antes de existir tenant: JÁ
RESOLVIDO (RFC-010), use diretamente.** O terminal se identifica ao gateway
pelo número de série mais o segredo `CONTROLID_PUSH_TOKEN` — não há cabeçalho
`X-Tenant`, porque o firmware não sabe o que é um tenant. `terminais` está sob
`FORCE ROW LEVEL SECURITY` e `uq_terminais_serie` é único **por tenant**, não
globalmente — exatamente o mesmo problema que a F1 resolveu para `tenants` com
`fn_resolve_tenant(p_slug TEXT) SECURITY DEFINER` (RFC-004/RFC-009). Um agente
que redigiu uma versão anterior deste PCF encontrou essa lacuna e o
orquestrador já a decidiu como **RFC-010**
(`docs/rfc/RFC-010-resolucao-de-terminal-e-tipo-sincronizacao.md`, já
implementada em `packages/contracts/schema.sql` e em
`apps/api/migrations/versions/0001_inicial.py`): existe
`fn_resolve_terminal(p_numero_serie TEXT) RETURNS TABLE (id UUID, tenant_id
UUID, status TEXT) SECURITY DEFINER`, que devolve **até 2 linhas** de
propósito — se vierem 2, trate como ambiguidade (erro interno, nunca escolha a
primeira em silêncio; isso não deveria acontecer na prática, mas o código
precisa se defender do caso). **Use esta função diretamente na T2; não abra
uma RFC nova para isto.**

**Ponto de atenção nº 2 — F5 constrói o pipeline que esta fase consome, na
mesma onda.** `POST /v1/marcacoes` (`criarMarcacao`, tag `marcacoes`) é
implementado pela F5, que roda **em paralelo** com esta fase, na mesma Onda 2.
O contrato (`MarcacaoCriar`, `MarcacaoCriada`, os códigos de erro, os quatro
mecanismos de idempotência) já está congelado e não deveria mudar — mas até a
F5 terminar sua implementação, o endpoint responde `501`. Construa e teste a
conversão `access_log → MarcacaoCriar` contra o contrato documentado desde já
(com um duplo de teste local, não contra a API real), e reserve um teste de
integração ponta a ponta (device-gw → API real) para quando a F5 estiver
pronta. Se, ao integrar de verdade, você achar que o formato de
`MarcacaoCriar` não basta para o que o catch-up precisa informar, isso é
achado de contrato — RFC, não um campo extra inventado no seu lado.

**Ponto de atenção nº 3 — enum de `ProcessamentoAssincrono.tipo`: JÁ RESOLVIDO
(RFC-010), use diretamente.** `sincronizarTerminal` devolve `202` com um corpo
`ProcessamentoAssincrono`, cujo campo `tipo` é um enum. Um agente que redigiu
uma versão anterior deste PCF encontrou que nenhum valor descrevia
"sincronização de terminal", e o orquestrador já decidiu isso na mesma
**RFC-010** citada no Ponto de Atenção nº 1: o enum ganhou o valor
`sincronizacao_terminal` (já em `packages/contracts/openapi.yaml` e já
regenerado em `apps/api/app/schemas/contrato.py`). **Use
`tipo="sincronizacao_terminal"` diretamente na T7; não abra uma RFC nova para
isto.**

**Vocabulário do próprio equipamento, para não confundir com o nosso
schema.** Control iD chama de `users`, `templates`, `groups`, `access_rules`,
`portals`, `time_zones`, `access_logs` e `alarm_logs` às tabelas **dentro do
terminal**, manipuladas por `create_objects.fcgi` / `load_objects.fcgi` /
`modify_objects.fcgi` / `destroy_objects.fcgi`. Nenhuma delas é uma tabela do
nosso `schema.sql` — são objetos do protocolo do fabricante, documentados em
`PROJETO.md` §3.1. A tradução entre o `user_id` interno do equipamento e o
nosso `colaborador_id` é feita pelo campo `registration` que a própria Control
iD associa a cada `user`: o provisionamento (A2) grava ali a matrícula do
colaborador ao criar o usuário no terminal; a ingestão (A1) resolve
`access_logs.user_id → users.registration` (via cache local populado no
provisionamento, ou por `load_objects.fcgi` sob demanda) e envia esse valor
como `MarcacaoCriar.matricula` — nunca como `colaboradorId`, que exigiria uma
consulta a `colaboradores` que este serviço não tem motivo para fazer.

**Simulador: pré-requisito, não luxo.** Sem hardware disponível
(`PROJETO.md` §2 registra a aquisição do iDFace físico como pendência externa
em aberto), o simulador é o que permite escrever e provar esta fase — e as
fases 3, 4 e 5 do teste e2e do produto inteiro dependem dele também. O
esqueleto em `apps/device-gw/gateway/simulador.py` (Fase 0) já documenta o
formato de três respostas (`login.fcgi`, `load_objects.fcgi`,
`execute_actions.fcgi|`) e a lista de tabelas do equipamento; falta o
servidor/estado real, os demais `*.fcgi` (`create_objects`, `modify_objects`,
`destroy_objects`, `user_set_image`) e os modos de falha (queda de rede,
sessão expirada, resposta corrompida). **A primeira tarefa de A2, antes de
qualquer outra coisa, é revisar esses formatos contra a especificação pública
da Control iD citada em `PROJETO.md`** — o próprio docstring do esqueleto
avisa que nada ali foi conferido contra hardware real.

**Fase 0 já entrega o andaime que você vai preencher, não recriar.** Em
`apps/device-gw`: `gateway/config.py` (variáveis de ambiente, incluindo
`CONTROLID_SIMULADOR`), `gateway/erros.py` (recorte de `errors.yaml` com os
códigos `PONTO-TERM-001..005`, conferido contra o contrato por teste), os três
roteadores de `gateway/rotas/{push,monitor,catchup}.py` (rotas montadas,
respondendo `501`, com a docstring de cada operação descrevendo exatamente o
que fazer). Em `apps/worker`: a tarefa `sincronizar_terminal`
(`worker/tarefas/integracoes.py`) e a rotina de cron
`verificar_terminal_offline` (`worker/scheduler.py`), ambas já registradas com
nome, fila e assinatura — vazias, devolvendo resultado marcado como não
implementado. Em `apps/api`: o roteador `app/routers/terminais.py` já existe
com as 7 operações declaradas e tipadas contra `app.schemas.contrato`,
respondendo `501`. **Nenhum destes arquivos-andaime muda de nome, de
assinatura pública ou de fila.** Você preenche o corpo.

**Fase 0 é congelada.** `packages/contracts/` não se altera fora do protocolo
de RFC.

## 3. Leituras obrigatórias (lista fechada)

Leia isto e pare. Não leia `PROJETO.md` além da seção 3.1 (protocolo Control
iD) e da nota de risco "iDFace indisponível para teste" na seção 14; não leia
outras fases; não leia o código de F1/F2/F3/F5 além dos módulos explicitamente
citados abaixo como "consumidos".

- `packages/contracts/openapi.yaml` — **apenas** a tag `terminais` (7
  operações: `listarTerminais`, `criarTerminal`, `obterTerminal`,
  `atualizarTerminal`, `excluirTerminal`, `listarSaudeTerminal`,
  `sincronizarTerminal`). Leia também os schemas `Terminal`, `TerminalCriar`,
  `TerminalAtualizar`, `TerminalSaude`, `ListaTerminal`, `ListaTerminalSaude`,
  `SincronizacaoTerminalRequisicao`, `ProcessamentoAssincrono` e, na tag
  `marcacoes`, **apenas** a operação `criarMarcacao` (`POST /v1/marcacoes`) com
  os schemas `MarcacaoCriar` e `MarcacaoCriada` — você consome este endpoint,
  não o implementa. Em `components`: `parameters` (`CabecalhoTenant`,
  `CabecalhoRequestId`, `CabecalhoIdempotencia`, `Cursor`, `Limite`,
  `Ordenar`), `responses` (`Erro400`..`Erro504`), o schema `Problema`.
- `packages/contracts/schema.sql` — seção **6 (BIOMETRIA E DISPOSITIVOS)**,
  tabelas `terminais` e `terminal_saude` (as únicas duas que você escreve), e a
  tabela `dispositivos` (você lê e insere, não altera a definição). Seção **8
  (MARCACAO — NÚCLEO LEGAL)**, **apenas** as colunas de `marcacoes` citadas no
  §2 (`dispositivo_id`, `terminal_id`, `log_externo_id`, `datahora_dispositivo`,
  `coletada_offline`, `canal`) — não leia a seção inteira, o resto é da F5.
  Seção **19 (ROW LEVEL SECURITY)** e a função `fn_resolve_terminal` (RFC-010,
  mesma seção 2), que você usa diretamente no Ponto de Atenção nº 1.
  Seção **20 (ROLES E PRIVILÉGIOS)**: confirme que `terminal_saude` está na
  lista `v_append_only` (a role `ponto_app` não tem `UPDATE`/`DELETE` nela —
  você só insere).
- `packages/contracts/models/biometria.py` — classes `Terminal` e
  `TerminalSaude` (modelos SQLAlchemy já gerados; **não** as classes de
  `biometrias`/`biometria_templates`, que são da F2).
- `packages/contracts/errors.yaml` — categoria **TERM** (5 códigos,
  `PONTO-TERM-001..005`), e os transversais `PONTO-AUTH-002`, `PONTO-AUTH-013`,
  `PONTO-CONF-001`, `PONTO-CONF-002`, `PONTO-CONF-004`, `PONTO-PERM-001`,
  `PONTO-PERM-002`, `PONTO-PERM-004`, `PONTO-REC-001`, `PONTO-TEN-002..004`,
  `PONTO-VAL-001`, `PONTO-VAL-005`, `PONTO-VAL-006`, `PONTO-VAL-011`,
  `PONTO-IDEM-001..003`, `PONTO-RATE-001`, `PONTO-INT-001..005`.
- `packages/contracts/events.yaml` — envelope de entrega (seção inicial) e os
  eventos `terminal.offline` (`origem: scheduler`) e `terminal.online`
  (`origem: worker`).
- `packages/contracts/glossario.md` — verbetes **Canal**, **Catch-up**,
  **Coletor**, **CRC-16** (só para não confundir com o que você não calcula),
  **REP-P**, **PTRP**; seção **6 (Termos proibidos)**.
- `docs/adr/ADR-001-multi-tenancy-row-level-security.md` — por que você não
  desabilita RLS nem contorna com `BYPASSRLS` fora do padrão já estabelecido.
- `docs/adr/ADR-006-criptografia-ciclo-vida-template-biometrico.md` — por que
  template biométrico não passa em claro por este serviço.
- `docs/rfc/RFC-010-resolucao-de-terminal-e-tipo-sincronizacao.md` — já
  decidida e implementada: resolve o Ponto de Atenção nº 1 (`fn_resolve_terminal`)
  e o nº 3 (`sincronizacao_terminal`). Use diretamente, não reabra.
- `apps/device-gw/README.md`, `apps/device-gw/gateway/{config,log,erros,
  simulador}.py`, `apps/device-gw/gateway/rotas/{push,monitor,catchup}.py`,
  `apps/device-gw/tests/test_andaime_device_gw.py` — o andaime que você
  preenche. **Não edite `test_andaime_device_gw.py`**: é propriedade do
  orquestrador (mesmo tratamento de `apps/api/tests/test_andaime.py` sob
  RFC-005); adicione testes novos em `apps/device-gw/tests/f6/`.
- `apps/api/app/routers/terminais.py` — o roteador-andaime que você implementa.
- `apps/api/app/routers/colaboradores.py` e `apps/api/app/biometria/
  dispositivos.py` — exemplo vivo de como um router e um serviço de domínio
  desta base de código são escritos (import, paginação por cursor, tradução de
  `IntegrityError`, forma de devolver erro do catálogo) **e** o serviço que
  você reaproveita para criar a linha de `dispositivos` subjacente a um
  terminal novo. Não copie o padrão de biometria (cifra de template); copie o
  padrão de estrutura (CRUD + paginação + `traduzir_integridade`).
- `apps/api/app/core/seguranca.py` (`Sujeito`, `exigir_permissao`,
  `tenant_id_ou_erro`) e `apps/api/app/db/sessao.py` (`SessaoDb`,
  `aplicar_tenant`) — já implementados pela F1; você só consome.
- `apps/worker/worker/filas.py`, `apps/worker/worker/tarefas/__init__.py`,
  `apps/worker/worker/tarefas/integracoes.py` (função `sincronizar_terminal`,
  a única que você edita neste arquivo) e `apps/worker/worker/scheduler.py`
  (função `verificar_terminal_offline`, a única que você edita neste arquivo)
  — o andaime que você preenche.
- `docs/backlog.md` — para não redescobrir o que já está registrado (em
  particular, confirme que `terminais.*` e `dispositivos:{ler,escrever}` já
  estão no catálogo de permissões semeado — não há pendência de catálogo para
  esta fase).

## 4. Contratos

**Consome** — já existe, esta fase apenas usa:

- Tabela `dispositivos` e o serviço `app.biometria.dispositivos` (função
  `criar_dispositivo`, F2) para criar o dispositivo subjacente quando
  `TerminalCriar` não informar `dispositivoId`.
- `POST /v1/marcacoes` (`criarMarcacao`, tag `marcacoes`, F5, rodando em
  paralelo — Ponto de Atenção nº 2 do §2).
- Andaime da API: `app/core/erros.py`, `app/core/catalogo_erros.py`,
  `app/core/seguranca.py` (`Sujeito`, `exigir_permissao`, `tenant_id_ou_erro`
  — F1), `app/db/sessao.py` (`SessaoDb`, `aplicar_tenant` — F1), modelos
  SQLAlchemy do pacote `ponto_contracts`.
- Andaime do `device-gw`: `gateway/config.py`, `gateway/log.py`,
  `gateway/erros.py`, `gateway/main.py`, os três roteadores de
  `gateway/rotas/`.
- Andaime do `worker`: `worker/filas.py` (fila `FILA_INTEGRACOES`, já mapeada
  para `sincronizar_terminal`), `worker/tarefas/__init__.py` (a tarefa já
  registrada em `TAREFAS`/`NOMES_DAS_TAREFAS`), `worker/main.py`,
  `worker/scheduler.py` (a rotina já registrada em `montar_cron()`).
- Catálogo de permissões semeado (`terminais.{ler,criar,editar,excluir,
  executar}`, escopos OAuth `dispositivos:{ler,escrever}`) — já completo,
  nenhuma pendência de catálogo nesta fase.

**Produz** — esta fase implementa:

*Endpoints da API (7 operações; hoje `501`):*

| Método | Caminho | `operationId` | Permissão exigida |
|---|---|---|---|
| GET | `/v1/terminais` | `listarTerminais` | `terminais.ler` |
| POST | `/v1/terminais` | `criarTerminal` | `terminais.criar` |
| GET | `/v1/terminais/{terminalId}` | `obterTerminal` | `terminais.ler` |
| PATCH | `/v1/terminais/{terminalId}` | `atualizarTerminal` | `terminais.editar` |
| DELETE | `/v1/terminais/{terminalId}` | `excluirTerminal` | `terminais.excluir` |
| GET | `/v1/terminais/{terminalId}/saude` | `listarSaudeTerminal` | `terminais.ler` |
| POST | `/v1/terminais/{terminalId}/sincronizar` | `sincronizarTerminal` | `terminais.executar` |

*Endpoints internos do `device-gw` (protocolo do fabricante, fora do
`openapi.yaml` — implementação real, hoje `501`):* `POST /new_connection.fcgi`,
`POST /send_response.fcgi`, `POST /interno/terminais/{numeroSerie}/comandos`,
`POST /api/notifications/{dao,door,catra,template,secbox,operation_mode}`,
`GET /interno/terminais/{numeroSerie}/marca-dagua`,
`POST /interno/terminais/{numeroSerie}/catch-up`.

*Tabelas escritas:* `terminais` (CRUD completo), `terminal_saude`
(append-only — só `INSERT`, nunca `UPDATE`/`DELETE`). Escrita de referência em
`dispositivos` **apenas** via `app.biometria.dispositivos.criar_dispositivo`
(nunca duplique a lógica de criação de dispositivo).

*Tarefas assíncronas preenchidas:* `sincronizar_terminal`
(`apps/worker/worker/tarefas/integracoes.py`, fila `FILA_INTEGRACOES`) e a
rotina de cron `verificar_terminal_offline`
(`apps/worker/worker/scheduler.py`).

*Módulos novos publicados para dentro da própria fase (não para outras
fases — F6 não tem consumidor externo):* `gateway/cliente_controlid.py` (ver
§5, contrato interno entre A1 e A2).

*Eventos publicados:* `terminal.offline` (origem: `scheduler`, pela rotina
`verificar_terminal_offline`), `terminal.online` (origem: `worker`, ao fim de
um catch-up bem-sucedido que encerra um período classificado como offline).
Publique no barramento interno com o envelope exato de `events.yaml` (`id`,
`tipo`, `versao`, `ocorridoEm`, `tenantId`, `dados`); a entrega por webhook é
da F13, aqui basta publicar e provar por teste que o payload bate campo a
campo com o declarado.

**Não toca** — é de outra fase, mesmo que pareça relacionado:

- Tag `marcacoes`, tabelas `marcacoes`, `rep_ps`, `nsr_sequencias`,
  `nsr_emissoes`, `comprovantes` e todo o motor de NSR/CRC-16/hash chain de
  marcação (**F5**, rodando em paralelo). Você **chama** `POST /v1/marcacoes`;
  não grava marcação, não atribui NSR, não calcula CRC-16.
- Tag `dispositivos`, tabelas `dispositivos`, `dispositivo_vinculos`, e o
  julgamento dos sinais antifraude do dispositivo (`attestation_status`,
  `root_detectado`, ...) — **F2** (já concluída) e **F14** (avaliação). Você
  só cria a linha de `dispositivos` subjacente ao terminal, via o serviço já
  pronto.
- Tag `biometria`, tabelas `biometrias`, `biometria_templates` e toda cifra de
  template — **F2** (já concluída). O enrollment presencial no terminal é só
  um **fato** registrado (quem, quando, em qual terminal); o vetor nunca passa
  por aqui.
- Tags `jornadas`, `escalas`, `feriados`, `afastamentos` — **F3**.
- `enviar_webhook` (`apps/worker/worker/tarefas/integracoes.py`) e tudo de
  entrega de webhook, assinatura HMAC, DLQ — **F13**. Você edita **só**
  `sincronizar_terminal` neste arquivo.
- `verificar_banco_horas_vencendo` (`apps/worker/worker/scheduler.py`) — **F4**.
  Você edita **só** `verificar_terminal_offline` neste arquivo.
- Tags `lgpd`, `webhooks`, `integracoes` e as tabelas correspondentes —
  **F13**/**F14**.
- `packages/contracts/**` — **congelado**.
- `apps/web`, `apps/mobile`, `apps/facial-svc`.

## 5. Ownership de arquivos

Caminhos **exclusivos** desta fase. Nenhuma outra fase escreve aqui.

| Agente | Caminhos |
|---|---|
| **A1** (`device-gw`, ingestão e cadastro) | `apps/device-gw/gateway/rotas/push.py`<br>`apps/device-gw/gateway/rotas/monitor.py`<br>`apps/device-gw/gateway/rotas/catchup.py`<br>`apps/device-gw/gateway/dominio/**` (novo — conversão `access_log`→`MarcacaoCriar`, resolução de terminal, saúde/reconexão)<br>`apps/api/app/terminais/**` (novo)<br>`apps/api/app/routers/terminais.py`<br>`apps/worker/worker/scheduler.py` (**só** a função `verificar_terminal_offline` e sua entrada em `montar_cron()`)<br>`apps/api/tests/f6/**`<br>`apps/device-gw/tests/f6/push/**`, `apps/device-gw/tests/f6/monitor/**`, `apps/device-gw/tests/f6/catchup/**` |
| **A2** (provisionamento e simulador) | `apps/device-gw/gateway/provisionamento/**` (novo — `create_objects`, `modify_objects`, `destroy_objects`, `user_set_image`, `execute_actions`)<br>`apps/device-gw/gateway/simulador.py`<br>`apps/worker/worker/tarefas/integracoes.py` (**só** a função `sincronizar_terminal`)<br>`apps/device-gw/tests/f6/provisionamento/**`, `apps/device-gw/tests/f6/simulador/**` |

**Compartilhado dentro da fase** (exige combinação entre A1 e A2):

| Caminho | Regra |
|---|---|
| `apps/device-gw/gateway/cliente_controlid.py` | **Criado por A2 na T1**, antes de qualquer outra tarefa da fase — mesmo padrão de `app/core/seguranca.py` em F1/F2. Define a interface única de fala com o equipamento (`login`, `load_objects`, `create_objects`, `modify_objects`, `destroy_objects`, `execute_actions`, `user_set_image`), com duas implementações: uma real (HTTP contra `endereco_ip`/`porta` do terminal, usada quando `modo_comunicacao` é `polling` ou `direto`) e uma simulada (usada quando `CONTROLID_SIMULADOR=true`, delegando a `gateway/simulador.py`). A1 (catch-up, T5) só **importa e chama** esta interface; não altera as assinaturas. Mudança de assinatura depois da T1 é combinada entre os dois agentes, não decidida unilateralmente. |
| `apps/device-gw/gateway/config.py` | Ambos podem **acrescentar** campos novos (nunca remover, renomear ou mudar o valor padrão de um campo existente) — por exemplo, a credencial que o `device-gw` usa para autenticar suas próprias chamadas a `POST /v1/marcacoes` (ver T3). Coordene em texto no PR quem acrescenta o quê para não haver dois campos equivalentes com nomes diferentes. |
| `apps/device-gw/gateway/main.py` | Só quem precisar registrar uma dependência de processo nova (ex.: cliente HTTP da API interna) edita, e só para isso — nenhum roteador novo é necessário aqui, os três já estão montados desde a Fase 0. |

**Compartilhado com outras fases — atenção, risco real de colisão:**

| Caminho | Regra de convivência |
|---|---|
| `apps/worker/worker/tarefas/integracoes.py` | Arquivo também "dono" da função `enviar_webhook` (**F13**, ainda stub, roda na Onda 5). Edite **apenas** o corpo de `sincronizar_terminal`; não toque em `enviar_webhook` nem na docstring do módulo além do necessário para refletir o que você implementou. |
| `apps/worker/worker/scheduler.py` | Arquivo também "dono" da função `verificar_banco_horas_vencendo` (**F4**, ainda stub, roda na Onda 3). Edite **apenas** o corpo de `verificar_terminal_offline` e, em `montar_cron()`, apenas o `CronJob` correspondente — não altere o de `verificar_banco_horas_vencendo`. |
| `apps/device-gw/pyproject.toml`, `apps/worker/pyproject.toml`, `apps/api/pyproject.toml` | Acrescente dependências **apenas** dentro de um bloco `# --- F6 ---` / `# --- fim F6 ---` na lista `dependencies`, criando o bloco no fim da lista se não existir (mesma convenção de F1/F2). Nunca reordene, remova ou reformate linha existente, nem toque nos blocos de outras fases. Antes de acrescentar, confira se a dependência já está declarada (ex.: `httpx` e `cryptography` provavelmente já bastam). |

**Explicitamente fora do seu ownership** (não edite, nem "só para arrumar"):
`packages/contracts/**`, `apps/api/app/schemas/contrato.py` (gerado),
`apps/api/app/core/{erros.py,catalogo_erros.py,seguranca.py,middleware.py}`,
`apps/api/app/db/sessao.py`, `apps/api/app/main.py`,
`apps/api/migrations/**`, `apps/api/tests/test_andaime.py`,
`apps/device-gw/tests/test_andaime_device_gw.py`,
`apps/worker/tests/test_andaime_worker.py`,
`apps/api/app/{organizacao,pessoas,biometria,importadores}/**`,
`apps/api/app/routers/{colaboradores,contratos,biometria,dispositivos,
empresas,unidades,organizacao,marcacoes}.py`, `.github/workflows/**`,
`infra/**`, `Makefile`, `tasks.ps1`, `apps/web/**`.

> **Nenhuma migration nova nesta fase.** `0001_inicial.py` já cria `terminais`,
> `terminal_saude` e (RFC-010) `fn_resolve_terminal`, com seus índices,
> constraints e a política de RLS. Se você
> achar que precisa de mais alguma coisa no schema além do que uma RFC
> aprovar, o contrato está errado: abra RFC.

## 6. Tarefas (T1..Tn)

### T1 — Interface do cliente Control iD e revisão do simulador contra a especificação
**Agente:** A2 — **primeira tarefa da fase, nada de A1 no catch-up começa antes**
**Descrição:** Criar `apps/device-gw/gateway/cliente_controlid.py` com a
interface descrita em §5 (Protocol ou ABC — a escolha é sua, a assinatura dos
métodos é o que fica fixado) e as duas implementações. Antes de escrever
qualquer corpo, revisar o formato das respostas em `gateway/simulador.py`
(hoje: `login.fcgi`, `load_objects.fcgi`, `execute_actions.fcgi`) contra a
documentação pública da Control iD citada em `PROJETO.md` §3.1, corrigindo o
que estiver diferente, e estender o simulador para responder também
`create_objects.fcgi`, `modify_objects.fcgi`, `destroy_objects.fcgi` e
`user_set_image.fcgi`, com estado em memória (lista de usuários, faces,
access_logs) que a T2/T5/T8 vão exercitar.
**Pronto quando:** `cliente_controlid.py` existe, é importável, e
`ruff check`/`mypy --strict` passam sobre ele; `descrever_simulador()` reporta
os sete `*.fcgi` cobertos (os três originais mais os quatro novos); existe
teste que cria um usuário simulado, gera dois `access_logs` para ele e lista
ambos por `id` crescente via a implementação simulada de `load_objects`.

### T2 — Resolução de terminal antes do tenant (Ponto de Atenção nº 1)
**Agente:** A1
**Descrição:** Implementar a identificação do terminal no modo Push e no
Monitor: o equipamento apresenta `numero_serie` (no corpo, conforme a
descrição de `push_obter_comando`) e o segredo `CONTROLID_PUSH_TOKEN` (em
tempo constante — não early-return na primeira diferença de byte). Chame
`fn_resolve_terminal(p_numero_serie)` (RFC-010, já implementada — ver §2,
Ponto de Atenção nº 1) para obter `tenant_id`/`id`/`status` do terminal antes
de publicar `app.tenant_id` e abrir sessão de banco; trate 2 linhas devolvidas
como ambiguidade (erro interno, nunca escolha a primeira). Depois de resolvido
o tenant e confirmado o token, publique `app.tenant_id` e prossiga.
**Pronto quando:** teste prova que um `numero_serie` inexistente responde
`PONTO-TERM-003`; teste prova que a credencial correta com `numero_serie` de
um terminal `inativo` também responde `PONTO-TERM-003` (mensagem não revela
qual parte falhou); teste prova que a comparação do token é em tempo
constante (ex.: usando `hmac.compare_digest`, nunca `==` de string).

### T3 — Cadastro de terminal e saúde na API
**Agente:** A1
**Descrição:** Implementar as 7 operações de `apps/api/app/routers/
terminais.py` sobre um novo módulo `apps/api/app/terminais/servico.py` (padrão
de `app/pessoas/colaboradores.py`: paginação por cursor, `traduzir_integridade`
equivalente para `PONTO-CONF-001` em número de série duplicado por tenant,
soft delete em `excluirTerminal`, `PONTO-CONF-004` se houver dependente).
`criarTerminal` sem `dispositivoId`: chamar
`app.biometria.dispositivos.criar_dispositivo` com `tipo="terminal"` antes de
inserir a linha de `terminais`. Cifrar `senhaApi` recebida em `TerminalCriar`/
`TerminalAtualizar` com o mesmo padrão de envelope (AES-256-GCM, chave externa
ao banco) já usado por `app.identidade.mfa.cifra`/`app.biometria.cifra` —
nunca devolver a senha em nenhuma leitura. `listarSaudeTerminal` lê
`terminal_saude` ordenada por `verificadoEm`. Definir, neste módulo, a
configuração usada por T3 para a credencial de serviço que o `device-gw`
apresenta ao chamar `POST /v1/marcacoes` (um `api_client`/`api_key` de
integração, criado por semeadura de desenvolvimento — **não** um usuário
humano).
**Pronto quando:** as 7 operações respondem conforme o contrato; teste prova
que criar dois terminais com o mesmo número de série no mesmo tenant é
`PONTO-CONF-001`; teste lê `senha_api_cifrada` direto do banco e confirma que
o conteúdo não é a senha em claro; `GET /v1/terminais/{id}` nunca devolve
`senhaApi`.

### T4 — Modo Push: obtenção e entrega de comando
**Agente:** A1
**Descrição:** Preencher `push_obter_comando` (entrega o próximo comando
enfileirado no Redis para aquele terminal, ou corpo vazio) e
`push_enviar_resultado` (fecha o ciclo: se o resultado for uma lista de
`access_logs`, converte cada um em `MarcacaoCriar` — ver T6 — e chama
`POST /v1/marcacoes`; qualquer outro tipo de resultado só marca o comando como
concluído). Atualizar `terminais.ultimo_contato_em` a cada contato válido — é
a base do alerta de terminal offline (T9). `enfileirar_comando` grava o
envelope `{verb, endpoint, body}` na fila do Redis, associada ao
`numero_serie`, e responde `PONTO-TERM-004` quando o terminal está mudo há
mais que `intervalo_push_segundos`.
**Pronto quando:** teste enfileira um comando, o terminal simulado (via T1)
pergunta e recebe exatamente aquele envelope, devolve um resultado, e o
comando some da fila; teste prova que dois `access_logs` idênticos entregues
duas vezes (reapresentação de resultado) não geram duas marcações.

### T5 — Serviço Monitor e catch-up por marca d'água
**Agente:** A1
**Descrição:** Preencher os seis endpoints de `monitor.py` — `monitorDao` é o
crítico: recebe `{object, type, values}`, e quando `object == "access_logs"`
converte cada valor em `MarcacaoCriar` (T6) e entrega à API; os demais só
registram o fato (porta, catraca, alarme, modo de operação) e, para
`monitorCredencial`, **nunca** repassam o vetor quando `object == "templates"`.
Preencher `obter_marca_dagua` (leitura pura de `terminais.ultimo_log_externo_id`)
e `executar_catch_up`: abrir sessão via `cliente_controlid` (T1),
`load_objects` sobre `access_logs` com `id > marca`, paginado por
`catchup_tamanho_pagina`, convertendo e entregando cada página, avançando a
marca **só depois** da confirmação de gravação de cada página, respeitando
`paginas_maximas`. Ao final de um catch-up que encerra um período classificado
como offline, publicar `terminal.online`.
**Pronto quando:** com o simulador gerando 1.000 `access_logs` e a rede
"derrubada" (o teste chama `executar_catch_up` sem que os 1.000 tenham
passado por Push/Monitor), o catch-up recupera os 1.000 sem duplicar e sem
perder nenhum (contagem exata de marcações criadas), e a marca d'água final
é o maior `id` visto; teste de reprocessamento (rodar o catch-up de novo sobre
o mesmo intervalo) produz zero marcação nova.

### T6 — Conversão `access_log` → marcação canônica
**Agente:** A1
**Descrição:** Módulo dedicado (`apps/device-gw/gateway/dominio/conversao.py`)
que recebe um `access_log` do formato do fabricante e o terminal resolvido
(T2) e devolve o corpo de `MarcacaoCriar`: `canal="terminal"`,
`matricula=<resolvida de users.registration>`, `empresaId`/`unidadeId` do
terminal, `terminalId`, `dispositivoId=terminais.dispositivo_id`,
`datahoraDispositivo` a partir de `access_logs.time` (epoch do equipamento),
`logExternoId=access_logs.id`, `sentidoInformado` mapeado de `event` quando
aplicável, `coletadaOffline=true` quando vier do catch-up. Gerar
`Idempotency-Key` determinística a partir de `numero_serie:access_log_id`, para
que reapresentação produza a mesma chave nos dois mecanismos de idempotência
ao mesmo tempo (cabeçalho e par `dispositivoId`+`logExternoId`).
**Pronto quando:** teste unitário (sem rede, sem banco) cobre um `access_log`
de cada `event` documentado em `EVENTOS_ACCESS_LOG` e confere campo a campo o
`MarcacaoCriar` produzido contra o schema do contrato; teste prova que o
mesmo `access_log` convertido duas vezes produz a mesma `Idempotency-Key`.

### T7 — Provisionamento e enfileiramento de sincronização
**Agente:** A2
**Descrição:** Preencher `sincronizar_terminal`
(`apps/worker/worker/tarefas/integracoes.py`): a partir de `escopo`
(`completo`, `usuarios`, `templates`, `grupos`, `regras`, `horarios`), montar
os comandos `create_objects.fcgi`/`modify_objects.fcgi`/
`destroy_objects.fcgi`/`user_set_image.fcgi` corretos e entregá-los via
`POST /interno/terminais/{numeroSerie}/comandos` (T4, A1) — a tarefa do worker
não fala HTTP com o terminal diretamente, delega ao `device-gw`. Ao criar um
usuário no terminal, gravar a matrícula do colaborador em `registration` (a
tradução que a T6 depende). Ligar `POST /v1/terminais/{id}/sincronizar` (em
`apps/api/app/routers/terminais.py`, T3 de A1) ao enfileiramento desta tarefa
via ARQ, no mesmo padrão de `importar_colaboradores`. Preencher o campo
`ProcessamentoAssincrono.tipo` da resposta com `"sincronizacao_terminal"`
(Ponto de Atenção nº 3, já decidido pela RFC-010 — não é uma decisão sua).
**Pronto quando:** teste enfileira `sincronizar_terminal` com escopo
`usuarios`, e o comando resultante chega ao terminal simulado (T1) como
`create_objects.fcgi` sobre `users` com o `registration` correto; teste prova
que a resposta de `POST /v1/terminais/{id}/sincronizar` devolve
`tipo="sincronizacao_terminal"`.

### T8 — Envio de face (`user_set_image`) e ações (`execute_actions`)
**Agente:** A2
**Descrição:** Implementar, em `apps/device-gw/gateway/provisionamento/`, a
construção do comando `user_set_image.fcgi` (foto em base64 do colaborador,
nunca persistida em disco pelo `device-gw` — ela só atravessa em memória até
virar o corpo do comando enfileirado) e de `execute_actions.fcgi` (abrir
porta, liberar giro de catraca, reiniciar) com os `parameters` no formato
`chave=valor;chave=valor` exigido pelo fabricante (não JSON).
**Pronto quando:** teste monta um comando `user_set_image` a partir de uma
imagem de teste e confirma que nenhum arquivo temporário sobrevive à chamada;
teste monta `execute_actions` para `open_door` e confirma o formato exato da
string de `parameters`.

### T9 — Saúde do terminal e detecção de offline
**Agente:** A1
**Descrição:** Preencher `verificar_terminal_offline`
(`apps/worker/worker/scheduler.py`): para cada terminal `ativo`, comparar
`ultimo_contato_em` ao limite configurado para o `modo_comunicacao` (Push e
Monitor podem ter limites diferentes — documente a escolha), gravar uma linha
em `terminal_saude` a cada verificação (append-only) e publicar
`terminal.offline` **uma vez por queda**, não a cada varredura (precisa de
marca de "já avisado" — por exemplo, o próprio estado `online=false` mais
recente em `terminal_saude`).
**Pronto quando:** teste com relógio controlado prova que um terminal sem
contato há mais que o limite gera exatamente uma publicação de
`terminal.offline` mesmo com várias varreduras consecutivas sem contato; teste
prova que o evento publicado bate campo a campo com o `payload` de
`events.yaml`.

### T10 — Fechamento
**Agentes:** A1 e A2
**Descrição:** Rodar todos os comandos da §8 e colar a saída real no relatório
da fase, item a item contra a §7.
**Pronto quando:** todos verdes, com saída colada, e
`git status --short packages/contracts` vazio.

## 7. Critérios de aceite

O relatório final responde item a item, com saída real colada.

1. **As 7 operações da tag `terminais`** deixaram de responder `501` e
   respondem conforme `openapi.yaml`; `python tools/conferir_rotas.py`
   continua dizendo `Inventario identico ao contrato`.
2. **Com o simulador, 1.000 eventos entram sem duplicar e sem perder** —
   contagem exata de marcações criadas igual a 1.000, verificada após uma
   combinação de Push, Monitor e catch-up sobre o mesmo lote.
3. **Derrubar a comunicação por um intervalo simulado e religar recupera tudo
   via catch-up**, sem intervenção manual, avançando a marca d'água só depois
   da confirmação de gravação.
4. **Idempotência real por `dispositivo_id + log_externo_id`**: reenviar o
   mesmo `access_log` (por Push, por Monitor, ou pelo catch-up reprocessando
   o mesmo intervalo) nunca produz uma segunda marcação.
5. **`terminal_saude` é append-only**: teste prova que a role `ponto_app` não
   consegue `UPDATE`/`DELETE` nela.
6. **Alteração de cadastro (usuário/face/regra) propaga ao terminal em menos
   de 60 segundos** no cenário simulado, via `sincronizar_terminal` →
   `enfileirar_comando` → próximo ciclo de Push.
7. **Terminal sem contato gera alerta**: `terminal.offline` publicado uma
   única vez por queda, com o payload conferido campo a campo contra
   `events.yaml`; `terminal.online` publicado ao final do catch-up de
   recuperação.
8. **Template biométrico nunca passa em claro por este serviço**: teste prova
   que `monitorCredencial` para `object == "templates"` não grava nem repassa
   o conteúdo do vetor, só o fato do cadastro.
9. **`senhaApi` nunca é devolvida em nenhuma leitura** de `Terminal`, e
   `senha_api_cifrada` lida direto do banco é ilegível sem a chave.
10. **Resolução de terminal antes do tenant usa `fn_resolve_terminal`
    (RFC-010), nunca `BYPASSRLS` fora do padrão aprovado.**
11. **Nenhum segredo versionado**: `CONTROLID_SENHA`, `CONTROLID_PUSH_TOKEN`
    e a chave de cifra de `senha_api_cifrada` vêm de variável de ambiente; só
    `infra/.env.example` está no repositório.
12. **Contrato intacto**: `git status --short packages/contracts` vazio.
13. Todos os comandos da §8 verdes, com saída real colada no relatório.

## 8. Comandos de verificação

Rode a partir da **raiz do repositório**, salvo onde indicado. Windows usa
`.\tasks.ps1`; Linux/macOS usa `make`.

Subir o banco e o Redis:

```bash
docker compose --env-file infra/.env.example -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d postgres redis
```

```powershell
.\tasks.ps1 up
```

Migrar (nenhuma migration nova é esperada, salvo RFC decidida):

```bash
cd apps/api && alembic upgrade head
```

Lint, formatação e tipos (versões fixadas no CI: ruff 0.7.4, mypy 1.13.0), nos
três apps que esta fase toca:

```bash
ruff check apps/api apps/device-gw apps/worker packages
ruff format --check apps/api apps/device-gw apps/worker packages
cd apps/api && mypy && cd ../device-gw && mypy && cd ../worker && mypy && cd ../..
```

```powershell
.\tasks.ps1 lint
.\tasks.ps1 typecheck
```

**Saída esperada:** `All checks passed!`, `NN files already formatted`,
`Success: no issues found in NNN source files` (uma vez por app).

Testes da fase, com cobertura:

```bash
cd apps/api && pytest tests/f6 -q --cov=app --cov-report=term-missing
cd apps/device-gw && pytest tests/f6 -q --cov=gateway --cov-report=term-missing
cd apps/worker && pytest tests/f6 -q --cov=worker --cov-report=term-missing
```

**Saída esperada:** todos os testes passam; nenhum `skip` no teste de 1.000
eventos nem no de catch-up — teste pulado não conta como verde.

Regressão do andaime (não pode quebrar):

```bash
cd apps/api && pytest tests/test_andaime.py -q
cd apps/device-gw && pytest tests/test_andaime_device_gw.py -q
cd apps/worker && pytest tests/test_andaime_worker.py -q
```

Inventário de rotas da API idêntico ao contrato:

```bash
cd apps/api && python tools/conferir_rotas.py
```

**Saída esperada:**
`Inventario identico ao contrato (metodo, caminho e operationId).`

Contrato não foi tocado:

```bash
git status --short packages/contracts
```

**Saída esperada:** nada — as mudanças da RFC-010 (`fn_resolve_terminal`, enum
`sincronizacao_terminal`) já estão aplicadas antes do início desta fase, então
o contrato deve estar intacto do seu ponto de vista.

Catálogo de tarefas do worker continua íntegro:

```bash
cd apps/worker && python -c "from worker.tarefas import NOMES_DAS_TAREFAS as n; print(len(n)); print(n)"
```

**Saída esperada:** as mesmas nove tarefas de antes desta fase — nenhuma
tarefa nova foi criada, `sincronizar_terminal` só teve o corpo preenchido.

## 9. Proibições

1. **Não edite `packages/contracts/`** fora de uma RFC decidida. Divergência
   vira RFC em `docs/rfc/`, no formato de `docs/rfc/README.md`.
2. **Não crie código de erro novo.** Os 5 códigos `PONTO-TERM-*` e os
   transversais listados na §3 são o conjunto disponível. Faltou um? RFC.
3. **Não desabilite RLS, nem com `BYPASSRLS`, nem conectando como dono da
   tabela, "só para o gateway resolver o terminal".** Use
   `fn_resolve_terminal` (RFC-010, já implementada — Ponto de Atenção nº 1).
4. **Não invente um valor diferente de `sincronizacao_terminal` para
   `ProcessamentoAssincrono.tipo`** — o valor já existe no enum (RFC-010,
   Ponto de Atenção nº 3).
5. **Não grave nem repasse vetor biométrico em claro** em nenhum ponto do
   `device-gw`. `monitorCredencial` registra o fato, nunca o conteúdo.
   ADR-006 é decisão fechada.
6. **Não persista imagem facial crua** em arquivo, log ou objeto — nem
   temporariamente. `user_set_image` mantém a imagem só em memória até virar
   corpo do comando enfileirado.
7. **Não implemente nem toque na tag `marcacoes`, nem nas tabelas `marcacoes`,
   `rep_ps`, `nsr_sequencias`** — são da F5, rodando em paralelo. Você chama
   `POST /v1/marcacoes`; não grava marcação você mesmo, nem cria uma tabela
   paralela para "adiantar" enquanto a F5 não termina.
8. **Não duplique a lógica de criação de `dispositivos`.** Use
   `app.biometria.dispositivos.criar_dispositivo`. Criar uma segunda forma de
   inserir dispositivo é como o cadastro diverge silenciosamente entre fases.
9. **Não invalide a idempotência do catch-up avançando a marca d'água antes
   da confirmação de gravação.** Entre duplicar e perder, o sistema escolhe
   sempre não perder — inverter isso é o erro clássico desta fase.
10. **Não toque em `enviar_webhook`** (mesmo arquivo de `sincronizar_terminal`)
    nem em `verificar_banco_horas_vencendo` (mesmo arquivo de
    `verificar_terminal_offline`). São de F13 e F4, ainda stub.
11. **Não verse o segredo do terminal nem a credencial do `device-gw` para a
    API.** `CONTROLID_SENHA`, `CONTROLID_PUSH_TOKEN` e a credencial de serviço
    usada para chamar `POST /v1/marcacoes` vêm de variável de ambiente; só
    `infra/.env.example`, com placeholders.
12. **Não escreva regra de negócio de outras fases** — jornada, apuração,
    banco de horas, relatórios, LGPD. Achou algo fora do escopo?
    `docs/backlog.md`.
13. **Não declare a fase pronta sem rodar os comandos da §8 e colar a saída
    real.** "Deve funcionar com hardware real" não é evidência — o simulador
    existe exatamente para produzir essa evidência sem hardware.
