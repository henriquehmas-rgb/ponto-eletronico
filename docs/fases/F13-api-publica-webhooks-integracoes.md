# F13 — API pública, webhooks e integrações

## 1. Objetivo

No fim desta fase, o `/v1` deixa de ser um contrato que só a própria SEEG consome por sessão de
navegador: um cliente de integração externo consegue se autenticar de verdade (OAuth 2.0 client
credentials **ou** API key, por ambiente sandbox/produção, com limite de taxa e idempotência reais),
assinar os 19 eventos públicos do catálogo e recebê-los por webhook com HMAC/retentativa/DLQ, exportar a
apuração fechada para oito sistemas de folha nomeados (mais um layout genérico honesto), importar um AFD
de outro fabricante sem contaminar o NSR do nosso REP-P, e entrar pelo SSO da própria empresa (Google
Workspace, Microsoft Entra ID ou um IdP SAML 2.0 próprio — RFC-018/ADR-013, já decididas antes do build).

## 2. Contexto mínimo

**O que é este sistema, em uma frase.** SEEG Ponto é um SaaS multi-tenant de ponto eletrônico brasileiro,
compatível com a Portaria MTP 671/2021 (REP-P — Registrador Eletrônico de Ponto via Programa), com motor
facial próprio; até aqui (F0–F6, F8–F12, F9a) ele já registra marcações imutáveis com NSR sem lacuna,
calcula jornada e banco de horas, roda workflows de aprovação e fechamento, gera relatórios e produz AFD/
AEJ assinados com certificado ICP-Brasil. F13 é a primeira fase que olha para **fora**: quem, além do
próprio RH da empresa cliente, precisa falar com este sistema por API — o ERP de folha do cliente, o
integrador que migra dados de outro REP-P, o time de TI do cliente que quer SSO corporativo.

**Onde F13 se encaixa.** Onda 5, depende de F0 (contrato), F4 (apuração — a folha exporta apuração
fechada), F11 (relatórios — reaproveita padrões de execução assíncrona) e F12 (conformidade — o AFD é o
formato que o importador de terceiro precisa reconhecer). O plano-base (`FASES-E-AGENTES.md` linha
334-343) desenha esta fase com 3 agentes; **por instrução direta do dono do produto, esta fase é
decomposta em 10**, porque as fronteiras reais (autenticação de cliente vs. portal de docs vs. motor de
entrega vs. painel vs. cada família de parceiro de folha vs. importador de AFD vs. cada protocolo de SSO)
são genuinamente independentes o bastante para ownership de arquivo mutuamente exclusivo — não é uma
divisão artificial, é a divisão que já estava implícita na própria variedade dos oito parceiros de folha
mencionados numa única linha do plano-base.

**A surpresa central desta fase: o contrato já promete muito mais do que o sistema hoje entrega, e parte
disso não é culpa de ninguém — é lacuna genuína de contrato, corrigida por quatro RFCs (§2.1), todas já
decididas pelo orquestrador antes do build começar (as três primeiras já vinham decididas pelo agente que
escreveu este PCF — corrigido: só o orquestrador decide RFC, ver nota em cada arquivo — a quarta, SSO, era
genuinamente nova e foi decidida separadamente, gerando o ADR-013).** `packages/contracts/schema.sql` já tem, desde a
Fase 0, as sete tabelas do grupo "13 · Integração" (`api_clients`, `api_keys`, `oauth_tokens`, `webhooks`,
`webhook_entregas`, `integracoes_folha`, `importacoes`), e F1 já implementou a emissão de token OAuth
2.0 client credentials de ponta a ponta (`apps/api/app/identidade/tokens/oauth.py`). Mas token emitido não
é token aceito: nenhuma rota protegida do sistema hoje reconhece um `Bearer <token OAuth>` nem um
`X-API-Key` (§2.3) — e essa é a primeira coisa que precisa ficar clara antes de escrever qualquer linha de
código desta fase, porque muda o que "OAuth 2.0 client credentials" significa como tarefa: não é
implementar do zero, é **fechar a ponta que falta**.

**Idempotência é outra surpresa do mesmo tipo (§2.4): o contrato exige `Idempotency-Key` em quase toda
escrita do sistema, mas só a F5 (marcações) construiu um mecanismo real — em todo o resto (inclusive nas
próprias rotas novas desta fase, antes de você agir), o cabeçalho chega e é descartado.** Você constrói o
mecanismo genérico e o aplica às suas próprias rotas; retrofitar as ~130 rotas de F1–F12 não é ownership
desta fase (registrado em `docs/backlog.md`, 2026-08-03).

**Barramento de eventos: os 19 eventos públicos de `events.yaml` (de um catálogo de 22, três internos) já
são publicados internamente, mas em listas Python em memória, um por módulo de domínio, que nada consome
(§2.2).** Cada um dos nove arquivos `eventos.py` espalhados por F2/F4/F5/F10/F12 diz, na própria
docstring, alguma variação de "a entrega por webhook é da F13" — isso não é uma leitura sua, é uma decisão
de todo agente que passou por ali antes. Você é quem constrói a ponte real.

**Folha de pagamento: pesquisa de mercado feita para esta revisão (não é opinião, é o que existe
publicamente) mostra que layout de exportação de folha comercial brasileira é overwhelmingly proprietário
— ao contrário do AFD/AEJ (regulação pública federal, já mapeada campo a campo em
`docs/leiaute-afd-aej.md` pela F12).** De oito parceiros nomeados, só a Alterdata tem uma especificação
pública de posição de campo genuinamente verificável (e mesmo essa é um padrão de mercado compartilhado
com IOB/Sage/Athenas, não exclusividade da Alterdata); os outros sete variam entre "documentação pública
só descreve o fluxo, campo por campo fica atrás de login" (Senior, Questor, Contmatic), "layout é
configurado pelo próprio cliente numa ferramenta dentro do sistema, não existe layout fixo para publicar"
(família TOTVS, Sankhya) e "documentação inteira atrás de suporte pago" (Fortes). O design desta fase
assume isso de frente: **o formato genérico bem documentado é o padrão real de entrega**, cada parceiro
recebe os campos e a convenção de nome de arquivo que a pesquisa confirmou (quando confirmou algo), e
onde a fidelidade de leiaute não é verificável com fonte pública, isso é dívida técnica **documentada**,
não uma promessa quebrada silenciosamente — mesmo padrão de honestidade que ADR-011/ADR-012 já
estabeleceram para este projeto.

**SSO tinha uma lacuna de contrato genuína, e diferente das outras, não era óbvia o bastante para o
próprio agente decidir sozinho — corretamente escalada (§2.5).** `credenciais.tipo='sso'`/`provedor_sso`/
`identificador_externo` já modelam o vínculo *usuário × identidade externa*, mas não existia nenhum
caminho HTTP, nenhuma tag, nenhum jeito de um tenant configurar em qual IdP confiar. RFC-018
(`docs/rfc/RFC-018-sso-sem-superficie-de-contrato.md`) foi decidida pelo orquestrador em 03/08/2026 (tag
nova `sso`, app OIDC compartilhado para Google/Entra, IdP próprio por tenant para SAML — detalhe completo
no ADR-013) — o Grupo SSO desta fase **não começa mais bloqueado**.

### 2.1 Quatro RFCs decididas antes do build — leia antes de escrever qualquer rota

O contrato tinha quatro lacunas reais, todas já decididas pelo orquestrador antes de qualquer código desta
fase ser escrito:

- **RFC-016** (`docs/rfc/RFC-016-chaves-de-api-sem-endpoint.md`) — `api_keys` tem tabela e primitivas
  prontas desde F0/F1, mas nenhum endpoint HTTP. Decidido: três operações novas sob
  `/v1/admin/api-clients/{apiClientId}/chaves` (`listarApiKeys`, `criarApiKey`, `revogarApiKey`).
- **RFC-017** (`docs/rfc/RFC-017-tag-integracoes-sem-endpoint-de-item-unico.md`) — a tag `integracoes` não
  tinha endpoint de item único. Decidido: `GET /v1/importacoes/{importacaoId}` (`obterImportacao`) e
  `GET /v1/integracoes/folha/{integracaoId}/exportacoes/{processamentoId}` (`obterExportacaoFolha`).
- **RFC-018** (`docs/rfc/RFC-018-sso-sem-superficie-de-contrato.md`, ver ADR-013) — SSO não tinha nenhuma
  superfície de contrato. Decidido: tag nova `sso`, `GET /v1/sso/{provedor}/iniciar`,
  `GET /v1/sso/{provedor}/callback` (`google`/`entra_id`), `POST /v1/sso/saml/acs`,
  `GET/PUT /v1/admin/sso/provedores`. App OIDC compartilhado de aplicação para Google/Entra (configuração
  por tenant é só allowlist de domínio/tenant-id em `tenant_configuracoes`); SAML sem app compartilhado,
  cada tenant configura seu próprio IdP (`entityId`/`ssoUrl`/certificado X.509, também em
  `tenant_configuracoes`, sem cifra — são dados públicos). Nenhuma tabela nova.
- **RFC-007** (já implementada por F2, nada a fazer aqui) — `ImportacaoCriar.conteudoRef` já existe no
  contrato; confirme que o importador de AFD de terceiro (A8) o usa exatamente como F2 já usa.

**Nota de processo, para você não repetir o mesmo erro em nenhuma RFC nova que encontrar durante o build:**
a primeira versão deste PCF continha RFC-016 e RFC-017 já marcadas "Decidida" pelo próprio agente que
escreveu o PCF — o orquestrador corrigiu isso ao revisar (só ele decide RFC, mesmo quando a resposta
parece óbvia, `docs/rfc/README.md` §4) e ratificou o conteúdo (que estava correto) como decisão própria,
com data real de revisão. Se você encontrar uma lacuna de contrato nova durante o build, **sempre** deixe
a RFC como `Proposta`, com opções e recomendação — nunca `Decidida` por conta própria, mesmo que a solução
pareça pequena e óbvia.

Cada RFC decidida acima nomeia qual agente desta fase aplica a mudança em `packages/contracts/openapi.yaml`
(e regenera `apps/api/app/schemas/contrato.py` via `tools/gerar_do_contrato.py`) no mesmo commit em que
constrói a funcionalidade — é a única exceção ao congelamento do contrato nesta fase, e está listada por
nome no §5.

### 2.2 O barramento interno de eventos — o que existe e o que falta

Nove arquivos, todos com o mesmo desenho (uma lista Python `BARRAMENTO_INTERNO: list[dict] = []` em nível
de módulo, uma função `publicar(envelope)` que só dá `append` e loga, uma função `limpar_barramento()` só
para teste), cada um dono de um subconjunto dos eventos do catálogo:

| Arquivo | Fase dona | Eventos publicados |
|---|---|---|
| `apps/api/app/marcacao/eventos.py` | F5 | `marcacao.criada`, `marcacao.suspeita`, `marcacao.sincronizada_offline` |
| `apps/api/app/pessoas/eventos.py` | F2 | `colaborador.admitido`, `colaborador.demitido` |
| `apps/api/app/apuracao/dominio/eventos.py` | F4 | `ocorrencia.aberta` (**interno**) |
| `apps/api/app/apuracao/tratamento/eventos.py` | F4 | `ajuste.aprovado`, `ajuste.reprovado`, `apuracao.recalculada` |
| `apps/api/app/apuracao/banco_horas/eventos.py` | F4 | `banco_horas.quitado` |
| `apps/api/app/workflow/solicitacoes/eventos.py` | F10 | `ajuste.solicitado` |
| `apps/api/app/workflow/fechamento/eventos.py` | F10 | `periodo.fechado`, `periodo.reaberto`, `espelho.assinado` |
| `apps/api/app/fiscal/afd/eventos.py` | F12 | `afd.gerado` |
| `apps/api/app/fiscal/aej/eventos.py` | F12 | `aej.gerado` |

`comprovante.emitido` (**interno**) não tem barramento próprio: `apps/api/app/marcacao/comprovantes/
eventos_comprovante.py` (F5) importa `montar_envelope`/`publicar` direto de `apps/api/app/marcacao/
eventos.py` e os reaproveita — patchar o `publicar()` de `marcacao/eventos.py` (o único arquivo que você
toca dentro de `apps/api/app/marcacao/**`) já cobre os dois eventos deste módulo. Como o evento é interno
(`webhook_publico: false`), ele não precisa de entrega real por webhook — só `BARRAMENTO_INTERNO`
continua funcionando, inalterado.

Fora deste padrão, três produtores vivem em processos separados (não podem importar `apps/api`, mesma
razão de ADR-009 — imagens Docker distintas):

| Local | Processo | Evento |
|---|---|---|
| `apps/worker/worker/tarefas/importacoes.py` (três ocorrências de `tipo="importacao.concluida"`) | worker | `importacao.concluida` |
| `apps/worker/worker/terminais_saude.py` | worker | `terminal.offline` |
| `apps/worker/worker/banco_horas_vencimento.py` | worker | `banco_horas.vencendo` |
| `apps/device-gw/gateway/dominio/eventos.py` | device-gw | `terminal.online` |

`webhook.desabilitado` (o último dos 22 nomes do catálogo, `webhook_publico: false` — interno) não tem
produtor ainda porque **é seu**: publicado pelo próprio motor de entrega quando um webhook é desabilitado
automaticamente (`docs/backlog.md`, item de 2026-07-25, já registrava isto).

Nenhum desses 13 pontos de publicação escreve nada durável fora do processo. `BARRAMENTO_INTERNO` é uma
lista Python de módulo — em produção, com múltiplos workers Uvicorn/múltiplas requisições concorrentes,
ela cresce sem limite e nunca é lida por ninguém fora do próprio teste que a esvazia manualmente. O motor
de entrega de webhooks (A3) precisa de uma forma **durável e transacionalmente segura** de saber que um
evento aconteceu, e o requisito não negociável é: **a intenção de entrega só pode existir depois que o
fato de domínio está de fato commitado — nunca antes, para não disparar webhook de algo que um rollback
desfez em seguida.** A tabela `webhook_entregas` (já existe, com `status`, `proxima_tentativa_em`) é o
destino natural. Como resolver a costura exata entre "evento publicado" e "linha em `webhook_entregas`"
é uma decisão de A3 — o PCF dá o requisito e o precedente (§6, T da tarefa correspondente), não a
implementação linha a linha.

### 2.3 Autenticação de cliente — o que existe, o que falta, e por que você não toca em `seguranca.py`

Lido com cuidado antes de qualquer linha de código do Grupo API pública:

1. `POST /v1/auth/token` (`emitirTokenOAuth`, tag `auth`, F1) **já funciona** — client credentials, corpo
   ou `Authorization: Basic`, interseção de escopo, emite token opaco (`secrets.token_urlsafe(48)`,
   guardado por hash SHA-256 em `oauth_tokens`). Não reimplemente isto.
2. `apps/api/app/identidade/tokens/oauth.py` também já tem `gerar_client_secret`, `gerar_api_key` e
   `autenticar_api_key` — primitivas prontas, exportadas, com o próprio docstring de
   `autenticar_api_key` avisando: *"esta fase entrega a primitiva de verificação; a fiação... é de uma
   fase futura"*. Reaproveite por import; não duplique.
3. **Nada, em lugar nenhum do sistema, verifica um `Bearer <token OAuth>` nem um `X-API-Key` numa
   requisição real.** `apps/api/app/identidade/tokens/middleware.py::AutenticacaoMiddleware` (o único
   middleware que popula o contexto de usuário da requisição) só decodifica JWT RS256 de sessão humana.
   `apps/api/app/core/seguranca.py::obter_sujeito` (de quem `exigir_permissao`/`x-permissao` dependem em
   toda rota do sistema) só lê esse contexto. Resultado real, hoje: um cliente que obtém um token OAuth ou
   uma API key válida recebe `401 PONTO-AUTH-002` em qualquer rota protegida, porque o sistema não
   reconhece o tipo de credencial.
4. `apps/api/app/core/seguranca.py` tem, na própria primeira linha do docstring do módulo, o aviso mais
   forte deste projeto inteiro sobre ownership: **"a partir daqui, somente A3 [F1] edita este arquivo"**.
   Isto não é uma trava relaxada como a das nove `eventos.py` ("até a F13..."); é um contrato explícito
   entre fases que F13 não tem autorização para reabrir. `apps/api/app/identidade/tokens/middleware.py`
   não tem o mesmo aviso textual, mas populariza um `ContextVar` cuja única leitora é justamente a função
   travada — mudar um sem o outro não resolve nada.

**A solução desta fase para (3) evita tocar em (4) inteiramente**: uma dependência FastAPI nova e
autocontida, dona da própria leitura de cabeçalho, que não depende do `Sujeito`/`obter_sujeito` nem do
`ContextVar` de usuário — ver T2 de A1. Isso resolve a autenticação de cliente para as rotas **novas**
desta fase (as únicas que este PCF tem autoridade de desenhar). Estender a cobertura às ~130 rotas de
F1–F12 (que hoje só aceitam sessão humana apesar de o contrato já declarar `oauth2`/`apiKeyAuth` como
alternativa) é trabalho de uma fase futura com autoridade sobre `seguranca.py` — registrado em
`docs/backlog.md`, 2026-08-03. **Não é proibição arbitrária: é o mesmo princípio de ownership exclusivo
que sustenta todo o mecanismo anti-quebra-de-contexto do projeto.**

### 2.4 Idempotência genérica — o que construir e onde parar

`PONTO-IDEM-001/002/003` (`errors.yaml`) definem o contrato: toda escrita exige `Idempotency-Key`;
reusar a chave com corpo diferente é `409`; duas requisições concorrentes com a mesma chave, a segunda
espera. `apps/api/app/marcacao/pipeline/idempotencia.py` (F5) já prova que o padrão funciona, mas é
amarrado à tabela `marcacoes` (FK `marcacao_id`) — não é reaproveitável fora daquele domínio. Construa a
versão genérica (T3 de A1) e aplique-a **só às rotas que você mesmo implementa nesta fase**
(`admin` api-clients/api-keys, `webhooks`, `integracoes`). Não abra uma tarefa para varrer F1–F12.

### 2.5 SSO — decidida, Grupo SSO liberado

RFC-018 foi decidida (03/08/2026, ver §2.1 e `docs/adr/ADR-013-sso-app-compartilhado-vs-por-tenant.md`).
Os dois agentes do Grupo SSO (A9, A10) já têm `operationId`/schema/tag para implementar contra desde o
primeiro commit — tag `sso`, caminhos `/v1/sso/{provedor}/iniciar`, `/v1/sso/{provedor}/callback`,
`/v1/sso/saml/acs`, `/v1/admin/sso/provedores`. Nenhuma tarefa deste grupo começa bloqueada.

### 2.6 Rate limit — o que já existe, o que falta

`api_clients.rate_limit_por_minuto` (coluna, default 600) e os cabeçalhos `RateLimit-Limit/Remaining/
Reset/Policy` já estão no contrato e já aparecem como `headers:` declarados em toda resposta 200/201 do
OpenAPI, e `apps/api/app/main.py` já expõe os quatro nomes via CORS (`expose_headers`). **Nada aplica o
limite de verdade** — não existe middleware nem dependência que conte requisições e recuse a 429ª. É
trabalho novo de A1 (T4), usando Redis (já provisionado, `config.redis_url`, biblioteca `redis.asyncio`
já em uso por `apps/api/app/routers/saude.py` para o healthcheck — mesma dependência, sem adicionar
nenhuma nova).

## 3. Leituras obrigatórias (lista fechada)

Cada agente lê a lista completa abaixo (não só a parte "da sua tarefa") porque as fronteiras entre os dez
agentes desta fase são finas e o contexto de um informa os outros.

- `packages/contracts/openapi.yaml` — tags `auth` (leitura — `emitirTokenOAuth`/`obterSessaoAtual`/
  `listarSessoes` já implementadas, não mexa), `admin` (operações `listarApiClients`/`criarApiClients`,
  mais as três novas da RFC-016), `webhooks` (as sete operações, completas desde F0), `integracoes` (as
  cinco operações originais, em três caminhos — `listarIntegracoesFolha`/`criarIntegracaoFolha`/
  `exportarFolha`/`listarImportacoes`/`criarImportacao` — mais as duas novas da RFC-017)
- `packages/contracts/schema.sql` — tabelas `api_clients`, `api_keys`, `oauth_tokens`, `webhooks`,
  `webhook_entregas`, `integracoes_folha`, `importacoes` (seção 14, linhas 3337-3569), `tenant_
  configuracoes` (linhas 230-253), `credenciais` (linhas 522-554, colunas `tipo`/`provedor_sso`/
  `identificador_externo`), `nsr_sequencias`/`nsr_emissoes`/`marcacoes` (colunas `canal`, `origem_
  importacao_id`)
- `packages/contracts/events.yaml` — arquivo inteiro (982 linhas, 22 eventos no catálogo: 19 públicos e
  3 internos — `ocorrencia.aberta`, `comprovante.emitido`, `webhook.desabilitado`); envelope, assinatura
  HMAC, política de entrega (retentativa, DLQ) já estão
  especificados por completo — não redecida nenhum desses parâmetros
- `packages/contracts/errors.yaml` — categorias `AUTH`, `PERM`, `RATE`, `IDEM`, `WEBH`, `IMP`, `TEN`,
  `REC`, `INT` por inteiro (não invente código novo; se faltar algum, é achado de RFC, registre e siga)
- `packages/contracts/glossario.md` — inteiro, com atenção a "Canal" (`marcacoes.canal`, valor
  `importacao`) e "Webhook"
- `docs/adr/ADR-003-geracao-nsr-sequencial-sem-lacunas.md` — item 6 da Decisão (namespace de NSR separado
  para AFD de terceiro)
- `docs/adr/ADR-005-versionamento-api-publica-depreciacao.md` — inteiro (versionamento, Schemathesis
  citada explicitamente como ferramenta da F13, política de depreciação com `Deprecation`/`Sunset`/`Link`)
- `docs/adr/ADR-006-criptografia-ciclo-vida-template-biometrico.md` — só a Decisão (padrão de envelope
  encryption a replicar para o segredo do webhook)
- `docs/rfc/RFC-007-importacaocriar-sem-conteudoref.md` (já implementada — confirme o padrão),
  `docs/rfc/RFC-013-enumeracao-cross-tenant-para-rotinas-de-manutencao.md` e `docs/rfc/RFC-014-
  enumeracao-cross-tenant-para-verificar-notificacoes-pendentes.md` (padrão pré-aprovado de função
  `SECURITY DEFINER` para rotina de cron cross-tenant — reaproveite `fn_tenants_ativos()`, já existe, não
  crie uma função nova), `docs/rfc/RFC-016-chaves-de-api-sem-endpoint.md`, `docs/rfc/RFC-017-tag-
  integracoes-sem-endpoint-de-item-unico.md`, `docs/rfc/RFC-018-sso-sem-superficie-de-contrato.md`
- `docs/backlog.md` — as quatro entradas de 2026-08-03 (idempotência genérica, autenticação de cliente,
  tarefas de worker que faltam, e a de 2026-07-25 sobre `webhook.desabilitado`)
- `apps/api/app/comum/armazenamento.py` — cliente MinIO já pronto (reaproveitar para arquivo de folha
  exportado e relatório de erro de importação; nunca criar segundo cliente)
- `apps/api/app/identidade/tokens/oauth.py` — ler por inteiro, reaproveitar as cinco funções já prontas
- `apps/api/app/identidade/tokens/middleware.py` e `apps/api/app/core/seguranca.py` — ler para entender a
  fronteira do §2.3; **não editar**
- `apps/api/app/terminais/cifra.py` — referência exata do padrão de envelope encryption (AES-256-GCM,
  chave mestra por variável de ambiente hex de 32 bytes, `iv || ciphertext` empacotado, `chave_id`
  versionado) a replicar para o segredo HMAC do webhook
- `apps/api/app/core/filas.py` e `apps/worker/worker/filas.py` — padrão de fila `arq`
  (`create_pool(..., default_queue_name=FILA_PADRAO)`); leia o comentário sobre o achado real de F9b/A3
  (job órfão quando `default_queue_name` é esquecido) antes de enfileirar qualquer job novo
- `apps/worker/worker/tarefas/integracoes.py`, `apps/worker/worker/tarefas/__init__.py`,
  `apps/worker/worker/scheduler.py` — estado atual (stubs e tarefas já implementadas de outras fases)
- Os treze pontos de publicação de evento listados em §2.2
- `apps/api/app/routers/webhooks.py`, `apps/api/app/routers/integracoes.py`, `apps/api/app/routers/
  admin.py` — estado atual (stub gerado, `501 PONTO-INT-005`)
- `docs/fases/F10-workflows-aprovacoes-fechamento.md` e `docs/fases/F12-conformidade-rep-p.md` — como
  referência de formato de PCF e do padrão `BARRAMENTO_INTERNO`/`SECURITY DEFINER` já em uso

## 4. Contratos

**Consome:** apuração fechada (`fechamentos`, `apuracoes_dia`, `bh_lancamentos` — só leitura, via F4);
AFD como formato de referência do importador de terceiro (leiaute de `docs/leiaute-afd-aej.md`, F12, só
leitura — o importador NÃO gera AFD, só o lê); armazenamento de objetos (`app.comum.armazenamento`, F10);
`fn_tenants_ativos()` (`SECURITY DEFINER`, já existe, RFC-013/014); catálogo de eventos (`events.yaml`)
como está; emissão de token OAuth e sessão (`apps/api/app/identidade/tokens/oauth.py`, F1); padrão de
cifra (`apps/api/app/terminais/cifra.py`, F6, só como referência de leitura).

**Produz:** autenticação de cliente funcional para as rotas desta fase (OAuth + API key + rate limit +
idempotência genérica); sete operações de `webhooks` implementadas de ponta a ponta; cinco (+ duas da
RFC-017) operações de `integracoes` implementadas; três (RFC-016) operações novas de `admin`; oito
exportadores de folha + layout genérico; um importador de AFD de terceiro; a tarefa `enviar_webhook` real
(já catalogada, hoje stub); uma tarefa nova `exportar_folha` e um dispatcher genérico de importação
(catálogo do worker, pré-autorizado por este PCF, mesmo precedente da nona tarefa de F2); portal de
documentação interativo e sandbox; painel de entregas de webhook; (se RFC-018 decidir a tempo) login SSO
Google Workspace/Entra ID/SAML 2.0.

**Não toca:** `packages/contracts/**` fora das três RFCs nomeadas no §2.1 (aplicadas pelo agente indicado,
nenhuma outra edição); `apps/api/app/core/seguranca.py`, `apps/api/app/identidade/tokens/middleware.py`
(§2.3); qualquer parte de `apps/api/app/marcacao/**`, `apps/api/app/apuracao/**`, `apps/api/app/
workflow/**`, `apps/api/app/pessoas/**`, `apps/api/app/fiscal/**` além do corpo da função `publicar()`
explicitamente listado no §5; nenhuma linha de cálculo de apuração, banco de horas ou geração de AFD/AEJ
(reaproveita, nunca reimplementa); `apps/mobile/**`.

## 5. Ownership de arquivos

### 5.1 Tabela de dependência entre agentes

| Agente | Grupo | Depende de | Motivo |
|---|---|---|---|
| **A1** | API pública — núcleo | — (T1-first da fase inteira) | Ninguém mais autentica cliente de integração sem a interface de A1 |
| **A2** | API pública — portal e sandbox | A1 (leve — precisa de um `ApiClient` real para demonstrar) | O "tente agora" do portal precisa de credencial de sandbox de verdade |
| **A3** | Webhooks — motor de entrega | A1 (leve — interface de `exigir_escopo`) | As rotas de `webhooks` usam a mesma dependência de escopo |
| **A4** | Webhooks — painel | A3 (a integração final; a UI pode ser construída contra o contrato/mock em paralelo) | Painel de entregas mostra dado real de `webhook_entregas` |
| **A5** | Folha — motor genérico + Domínio + Alterdata | A1 (leve) | Rotas de `integracoes` usam a mesma dependência de escopo |
| **A6** | Folha — família TOTVS | A5 (leve — reaproveita o motor genérico e o arquivo compartilhado do worker) | Não duplica o motor de layout; coordena o arquivo de tarefa do worker |
| **A7** | Folha — Senior/Sankhya/Questor/Fortes/Contmatic | A5 (leve, mesmo motivo de A6) | idem |
| **A8** | Importador de AFD de terceiro | A1 (leve) | Rota de `integracoes`/`importacoes` usa a mesma dependência de escopo |
| **A9** | SSO — OIDC (Google Workspace, Entra ID) | A1 (leve, para o padrão de sessão emitida) | RFC-018/ADR-013 já decididas — só falta a dependência leve de A1 (emissão do mesmo par de tokens de sessão) |
| **A10** | SSO — SAML 2.0 | A1 (leve) | idem |

"Leve" significa: precisa só da **assinatura** da função/dependência (que A1 publica cedo, no primeiro
dia, mesmo antes de terminar rate limit/idempotência por completo — mesmo espírito de andaime que a
própria Fase 0 usou), não da implementação inteira concluída.

### 5.2 Ownership exclusivo, por agente

| Agente | Caminhos |
|---|---|
| **A1** — Núcleo de autenticação de cliente | `apps/api/app/comum/autenticacao_cliente.py` (novo)<br>`apps/api/app/comum/limitador_taxa.py` (novo)<br>`apps/api/app/comum/idempotencia_generica.py` (novo)<br>`apps/api/app/integracoes/__init__.py` (novo, único criador)<br>`apps/api/app/integracoes/clientes/**` (novo)<br>`apps/api/tests/f13/conftest.py` (novo, único criador — fixture compartilhada da fase)<br>`apps/api/tests/f13/nucleo/**` |
| **A2** — Portal de documentação e sandbox | `apps/web/src/app/desenvolvedores/**` (novo)<br>`apps/web/src/componentes/desenvolvedores/**` (novo)<br>`apps/api/app/integracoes/sandbox/**` (novo)<br>`apps/web/src/testes/f13/portal/**` |
| **A3** — Motor de entrega de webhooks | `apps/api/app/routers/webhooks.py` (arquivo inteiro, hoje 100% stub)<br>`apps/api/app/integracoes/webhooks/**` (novo — inclui `cifra.py`, `servico.py`, `despacho.py`)<br>`apps/worker/worker/despacho_webhooks.py` (novo, se optar por rotina de cron dedicada)<br>`apps/api/tests/f13/webhooks/**` |
| **A4** — Painel de entregas | `apps/web/src/app/painel/integracoes/**` (novo)<br>`apps/web/src/componentes/paineis/integracoes/**` (novo)<br>`apps/web/src/testes/f13/painel-integracoes/**` |
| **A5** — Motor genérico de folha + Domínio + Alterdata | `apps/api/app/routers/integracoes.py` — só as três funções `listarIntegracoesFolha`/`criarIntegracaoFolha`/`exportarFolha` mais `obterExportacaoFolha` (RFC-017); nunca toque nas funções de `importacoes` (A8)<br>`apps/api/app/integracoes/folha/__init__.py` (novo, único criador)<br>`apps/api/app/integracoes/folha/comum/**` (novo — motor genérico, layout `generico_csv`; A6 e A7 importam, não editam)<br>`apps/api/app/integracoes/folha/dominio/**` (novo)<br>`apps/api/app/integracoes/folha/alterdata/**` (novo)<br>`apps/api/tests/f13/folha/comum/**`, `apps/api/tests/f13/folha/dominio/**`, `apps/api/tests/f13/folha/alterdata/**` |
| **A6** — Família TOTVS | `apps/api/app/integracoes/folha/totvs_rm/**`, `.../totvs_protheus/**`, `.../totvs_datasul/**` (novo)<br>`apps/api/tests/f13/folha/totvs_rm/**`, `.../totvs_protheus/**`, `.../totvs_datasul/**` |
| **A7** — Senior/Sankhya/Questor/Fortes/Contmatic | `apps/api/app/integracoes/folha/senior/**`, `.../sankhya/**`, `.../questor/**`, `.../fortes/**`, `.../contmatic/**` (novo)<br>`apps/api/tests/f13/folha/senior/**`, `.../sankhya/**`, `.../questor/**`, `.../fortes/**`, `.../contmatic/**` |
| **A8** — Importador de AFD de terceiro | `apps/api/app/routers/integracoes.py` — só as funções `listarImportacoes`/`criarImportacao`/`obterImportacao` (RFC-017); nunca toque nas funções de folha (A5)<br>`apps/api/app/integracoes/importadores/afd_terceiro/**` (novo)<br>`apps/api/tests/f13/importadores/afd_terceiro/**` |
| **A9** — SSO OIDC (Google Workspace, Entra ID) | `apps/api/app/routers/sso.py` (novo — RFC-018/ADR-013 já decididas, tag `sso`; se A10 também precisar do mesmo arquivo, dividem por função/rota dentro dele, nunca duas cópias)<br>`apps/api/app/identidade/sso/oidc/**` (novo)<br>`apps/web/src/componentes/sso/oidc/**` (novo — botão/entrada de login federado Google/Entra)<br>`apps/api/tests/f13/sso/oidc/**` |
| **A10** — SSO SAML 2.0 | `apps/api/app/identidade/sso/saml/**` (novo)<br>`apps/web/src/componentes/sso/saml/**` (novo — botão/entrada de login federado SAML)<br>`apps/web/src/app/painel/cadastros/sso/**` (novo — tela de configuração de IdP por tenant)<br>`apps/api/tests/f13/sso/saml/**` |

### 5.3 Compartilhado dentro da fase (exige combinação entre agentes)

| Caminho | Regra |
|---|---|
| `apps/web/src/componentes/paineis/shell/casca-do-painel.tsx` | Arquivo de F9b, com os itens de navegação do `painel` (`Painel`, `Cadastros`, `Apuração`, `Escalas`, ...) escritos em linha. **Só A4** acrescenta UMA linha nova (`<ItemDeNavegacao href="/painel/integracoes" rotulo="Integrações" .../>`), sem reordenar nem remover nenhuma existente. A2 não toca aqui (`/desenvolvedores` é rota própria, fora da casca do `painel` — portal de desenvolvedor externo, não tela interna de RH/gestor). A10 também não precisa tocar aqui: a tela de configuração de SSO vive sob o prefixo já existente `/painel/cadastros` (`prefixoAtivo="/painel/cadastros"` já cobre qualquer sub-rota), sem exigir item de navegação novo. |
| `apps/web/src/app/page.tsx` | Tela de login (raiz `/`, F1/F8), único ponto de entrada de sessão humana do sistema. **A9 e A10**, cada um, acrescenta o próprio botão/link de login federado (usando os componentes isolados de `apps/web/src/componentes/sso/oidc/**` e `.../saml/**`, respectivamente), sem alterar o formulário de senha nem o botão do outro. Combine ordem de commit entre os dois antes de mexer. Confirme a estrutura real do arquivo antes de editar — este PCF não leu o arquivo inteiro, só confirmou que é o único `page.tsx` na raiz de `apps/web/src/app`. |
| `apps/worker/worker/tarefas/integracoes.py` | Um único arquivo, três blocos: **A3** preenche `enviar_webhook` (já é stub nomeado, "F13, ainda stub, não editar" — a proibição era para as OUTRAS fases; agora é sua); **A5** acrescenta `exportar_folha` (nova); **A8** acrescenta uma tarefa de importação genérica, por exemplo `importar_arquivo_generico` (nova, cobre os tipos que `importar_colaboradores`, de F2, não cobre — `afd_terceiro` e os demais). Nunca toque na função `sincronizar_terminal` (F6) nem em `user_id_do_terminal`. Combine ordem de commit entre os três antes de mexer. |
| `apps/worker/worker/tarefas/__init__.py` | Cada um dos três (A3, A5, A8) acrescenta sua própria entrada à tupla `TAREFAS` e à tabela da docstring (doze tarefas → quinze). Mesmo precedente já usado pela F2 para `importar_colaboradores` (nona tarefa) — registrado em `docs/backlog.md`, não é invenção de escopo. |
| `apps/worker/worker/filas.py` | Cada um dos três acrescenta sua entrada a `FILA_POR_TAREFA` (todas em `FILA_INTEGRACOES`) e `FASE_POR_TAREFA` (todas `"F13"`). Não mude nenhuma entrada existente. |
| `apps/worker/worker/scheduler.py` | Se A3 optar por uma rotina de cron para despachar `webhook_entregas` pendentes (em vez de enfileirar direto no ponto de publicação — decisão de A3, ver T11/T12), acrescenta **só** a função nova e a linha de registro em `montar_cron()`, mesmo padrão já usado três vezes (F4 `verificar_banco_horas_vencendo`, F6 `verificar_terminal_offline`, F10 `verificar_notificacoes_pendentes`) — reaproveite `fn_tenants_ativos()` já existente (RFC-013/014, pré-aprovada para qualquer rotina cross-tenant futura), não crie função `SECURITY DEFINER` nova. |
| `apps/api/app/routers/integracoes.py` | Ver linha de A5/A8 acima — mesmo arquivo, funções disjuntas. Nenhum dos dois reordena a função do outro. |
| `apps/api/app/routers/admin.py` | **A1** implementa só `listarApiClients`, `criarApiClients`, `listarApiKeys`, `criarApiKey`, `revogarApiKey` (as duas primeiras já eram stub de F1; as três últimas são novas, RFC-016). Nenhuma outra função deste arquivo (usuários, perfis, permissões, saúde — todas de F1) é tocada. |
| `apps/api/app/routers/auth.py` | Nenhum agente desta fase edita este arquivo. `emitirTokenOAuth` já está implementado (F1). RFC-018/ADR-013 decidiram a opção (b) da RFC (tag nova `sso`) — toda rota de SSO vive em `apps/api/app/routers/sso.py` (novo, A9/A10), nunca em `auth.py`. |
| `packages/contracts/openapi.yaml` | Só as RFCs nomeadas no §2.1, cada trecho aplicado pelo agente que a própria RFC nomeia: **RFC-016** (três operações de `admin`/chaves) → **A1**; **RFC-017** → dividida em dois trechos disjuntos do YAML, cada um aplicado por quem implementa a operação correspondente — `obterExportacaoFolha` → **A5** (T15/T16), `obterImportacao` → **A8** (T19); **RFC-018**, quando decidida → **A9**/**A10**, conforme a decisão do orquestrador definir a tag/caminhos exatos. Nenhuma outra edição, de nenhum agente — e nenhum dos quatro agentes acima edita o trecho do YAML que pertence a outro. |
| `infra/.env.example` | `PONTO_WEBHOOK_CHAVE_MESTRA` (A3, cifra do segredo HMAC), variáveis de credencial do app OIDC compartilhado (A9 — `SSO_GOOGLE_CLIENT_ID`/`SSO_GOOGLE_CLIENT_SECRET`/`SSO_ENTRA_CLIENT_ID`/`SSO_ENTRA_CLIENT_SECRET`, client ID/secret de aplicação, nunca por tenant, confirmado pelo ADR-013) — cada agente acrescenta só o próprio bloco, nunca edita bloco alheio, mesmo padrão já usado por F6/F10/F12. |

### 5.4 Explicitamente fora do seu ownership (não edite, nem "só para arrumar")

`packages/contracts/**` fora das exceções nomeadas acima, `apps/api/app/schemas/contrato.py` (gerado —
regenere via `tools/gerar_do_contrato.py`, nunca edite à mão), `apps/api/app/core/catalogo_erros.py`,
`apps/api/app/core/erros.py`, `apps/api/app/core/seguranca.py`, `apps/api/app/identidade/tokens/
middleware.py`, `apps/api/app/core/middleware.py`, `apps/api/app/db/sessao.py`, `apps/api/app/main.py`,
`apps/api/app/routers/__init__.py`, `apps/api/app/routers/{auth,tenants,empresas,unidades,organizacao,
colaboradores,contratos,biometria,dispositivos,terminais,jornadas,escalas,feriados,afastamentos,
marcacoes,comprovantes,tratamentos,apuracoes,banco_horas,relatorios,solicitacoes,aprovacoes,fechamentos,
espelhos,fiscal,auditoria,lgpd}.py`, `apps/api/app/marcacao/**` (exceto o corpo de `publicar()` no único
arquivo listado no §2.2, `marcacao/eventos.py` — isso também cobre `comprovante.emitido`, ver nota do
§2.2), `apps/api/app/apuracao/**` (idem, três arquivos), `apps/api/app/workflow/**`
(idem, dois arquivos), `apps/api/app/pessoas/**` (idem, um arquivo), `apps/api/app/fiscal/**` (idem, dois
arquivos — nunca toque em `apps/api/app/fiscal/afd/**`/`aej/**` fora de `eventos.py`, e nunca em
`apps/api/app/fiscal/assinatura/**`/`cofre/**`), `apps/api/app/identidade/**` (exceto os dois pacotes
novos `apps/api/app/identidade/sso/oidc/**` e `.../saml/**`, exclusivos de A9/A10), `apps/api/app/
organizacao/**`, `apps/api/app/jornada/**`, `apps/api/app/notificacao/**`, `apps/api/app/comum/
armazenamento.py` (reaproveitamento apenas — se faltar algo, é achado de contrato, não patch seu),
`apps/api/migrations/**` (exceto uma migration nova para a tabela de idempotência genérica, T3 de A1 —
ver nota abaixo), `apps/api/tests/test_andaime.py`, `apps/worker/worker/tarefas/{apuracao,fechamento,
notificacoes,relatorios,lgpd,importacoes}.py` (note: `importacoes.py` aqui é o de `importar_colaboradores`,
F2 — diferente de `integracoes.py`, compartilhado por A3/A5/A8, ver §5.3), `.github/workflows/**` (exceto
o job novo de Schemathesis, T-final de A1, acrescentado sem remover nenhum job existente), `apps/device-
gw/**` (exceto o corpo de `publicar()` no arquivo listado em §2.2, exclusivo de A3), `apps/mobile/**`.

> **Uma migration nova é autorizada nesta fase**, exclusiva de A1: a tabela de idempotência genérica
> (T3). Nenhum outro agente cria migration. Se você achar que precisa de coluna ou tabela nova além dessa
> e da que a RFC-016/017 já cobrem, o contrato está incompleto — abra RFC, não migre por conta própria.

> **NUNCA rode `python tools/gerar_do_contrato.py` depois de começar a implementar.** Sobrescreve **todos**
> os routers já implementados de volta a stub — não só os desta fase, mas os de F1–F12 inteiras. É
> ferramenta de Fase 0/RFC para regenerar o andaime a partir do contrato; usá-la depois destrói trabalho
> alheio sem aviso. Precisa conferir a assinatura de um handler gerado? Leia o arquivo, não regere.

## 6. Tarefas

### Grupo API pública

**T1 — Interface de autenticação de cliente (A1, primeiro commit da fase)**
`apps/api/app/comum/autenticacao_cliente.py`: `exigir_escopo(escopo: str) -> Callable[..., Awaitable[
ClienteAutenticado]]`, uma fábrica de dependência FastAPI autocontida (não depende de `Sujeito`/
`obter_sujeito`/`ContextVar`). Lê `Authorization: Bearer <token>` e `X-API-Key` diretamente da
`Request`; tenta OAuth primeiro (hash SHA-256 contra `oauth_tokens.token_hash`, checa `expira_em`/
`revogado_em`, checa `escopo in token.escopos`), cai para API key (reaproveita `oauth.autenticar_api_key`,
checa `escopo in chave.escopos`); `401 PONTO-AUTH-002` sem nenhuma credencial, `401 PONTO-AUTH-012`/
`013` conforme a credencial fornecida for inválida, `403 PONTO-PERM-003` se o escopo não bate,
`403 PONTO-PERM-006` se `ips_permitidos` do cliente não inclui a origem (reaproveita
`oauth.verificar_origem_permitida`). Devolve um `ClienteAutenticado` (dataclass nova, campos
`tenant_id`/`api_client_id`/`ambiente`/`escopos`) — **não é o `Sujeito` de `seguranca.py`**, é um tipo
próprio desta fase.
**Pronto quando:** teste prova as quatro combinações (OAuth válido, API key válida, sem credencial,
escopo insuficiente) contra as tabelas reais.

**T2 — Gestão de clientes de API e chaves (A1)**
`apps/api/app/integracoes/clientes/servico.py`: CRUD de `api_clients` (reaproveita
`oauth.gerar_client_secret`) e, seguindo RFC-016, de `api_keys` (reaproveita `oauth.gerar_api_key`).
Aplica RFC-016 em `packages/contracts/openapi.yaml` (três operações novas + schemas `ApiKey`/
`ApiKeyCriar`/`ApiKeyCriada`) e regenera `apps/api/app/schemas/contrato.py`. Implementa os corpos de
`listarApiClients`, `criarApiClients` (já eram stub), `listarApiKeys`, `criarApiKey`, `revogarApiKey`
(novas) em `apps/api/app/routers/admin.py`. Validação de aplicação: `ambiente` de uma `ApiKey` nunca
excede o `ambiente` do `ApiClient` pai.
**Pronto quando:** `python tools/conferir_rotas.py` mostra as três operações novas implementadas;
`api_client_secret`/`api_key` aparecem em claro só na resposta de criação, nunca de novo.

**T3 — Idempotência genérica (A1)**
`apps/api/app/comum/idempotencia_generica.py`: dependência `Depends(exigir_idempotencia())` reaproveitável
por qualquer rota de escrita. Nova tabela (migration própria desta fase, ver nota do §5.4) —
`idempotencia_chaves(id, tenant_id, escopo, chave, corpo_hash, status, resposta_status, resposta_corpo
jsonb, criado_em, expira_em)`, unicidade `(tenant_id, escopo, chave)`, TTL de 24h coerente com
`PONTO-IDEM-001`. Aplica a suas próprias rotas novas (`webhooks`, `integracoes`, `admin` api-clients/keys)
— nenhuma rota de F1–F12.
**Pronto quando:** teste prova as três semânticas de `PONTO-IDEM-001/002/003` contra a tabela real;
`alembic upgrade head && alembic downgrade base && alembic upgrade head` reversível.

**T4 — Rate limit por cliente (A1)**
`apps/api/app/comum/limitador_taxa.py`: janela deslizante ou token bucket em Redis (`redis.asyncio`, já
em uso pelo healthcheck — sem dependência nova), chave `ponto:ratelimit:{apiClientId}:{janela}`, limite
lido de `api_clients.rate_limit_por_minuto`. Preenche de verdade os cabeçalhos `RateLimit-Limit/Remaining/
Reset/Policy` (hoje só declarados no contrato) e responde `429 PONTO-RATE-001` com `Retry-After` quando
excedido. Aplica junto de `exigir_escopo` (T1) nas mesmas rotas.
**Pronto quando:** teste de carga simples (N+1 requisições no mesmo minuto) prova o 429 na N+1 com os
cabeçalhos corretos.

**T5 — Versionamento e depreciação (A1)**
Utilitário `apps/api/app/comum/depreciacao.py`: função que, dado um marcador `deprecated: true` numa
operação (ADR-005), acrescenta `Deprecation`/`Sunset`/`Link` à resposta. Nenhuma operação do `/v1` está
marcada como depreciada hoje — este item entrega o **mecanismo**, pronto para o dia em que alguém
depreciar algo, não uma depreciação real.
**Pronto quando:** teste unitário prova os três cabeçalhos com uma operação de teste marcada `deprecated`.

**T6 — Schemathesis no CI (A1, última tarefa do agente)**
Confirmado por leitura (`packages/contracts/README.md:46`, `ADR-005`): Schemathesis é **citada como
ferramenta da F13** em dois lugares do projeto, mas não está instalada nem usada em lugar nenhum
(`.github/workflows/ci.yml`, `Makefile`, `tasks.ps1` — busca confirma zero ocorrências antes desta
fase). Você a introduz agora: `schemathesis run packages/contracts/openapi.yaml --base-url ... --checks
all` contra a API real subida em CI, job novo `contrato-schemathesis` em `.github/workflows/ci.yml`
(paralelo ao job `openapi` existente, que só faz `spectral lint`), alvo novo no `Makefile`/`tasks.ps1`
(`make schemathesis`/`.\tasks.ps1 schemathesis`).
**Pronto quando:** `schemathesis run` roda localmente contra a API subida e não diverge do contrato nas
operações que já respondem de verdade (rotas ainda-stub de fases futuras, se houver, respondem `501`
consistentemente com `errors.yaml` e não contam como divergência).

**T7 — Portal de documentação interativo (A2)**
`apps/web/src/app/desenvolvedores/**`: renderiza `packages/contracts/openapi.yaml` (Redoc ou Swagger UI,
decisão de A2 — avalie licença e peso de bundle antes de escolher) com console "tente agora" que usa uma
credencial de sandbox real (depende de A1/T2). Documenta de forma proeminente a regra de cliente
tolerante do ADR-005 ("ignore campo desconhecido, não trate enum de saída como fechado") — o próprio ADR
exige isso no topo do portal, não enterrado.
**Pronto quando:** navegar até `/desenvolvedores`, criar um cliente de sandbox pela própria tela, e emitir
um token contra ele funciona de ponta a ponta.

**T8 — Sandbox com dados sintéticos (A2)**
`apps/api/app/integracoes/sandbox/**`: script/rota administrativa que semeia um tenant de demonstração
(`ambiente='sandbox'` em `api_clients`) com dados sintéticos plausíveis — reaproveita a estrutura de
`apps/api/migrations/seed_dev.py` como referência de composição (empresa, unidade, colaboradores,
marcações, apuração), sem editar aquele arquivo (fora do seu ownership). Evento de sandbox nunca alcança
webhook de produção (`events.yaml`, campo `ambiente` do envelope) — prove isso por teste.
**Pronto quando:** um cliente de sandbox consegue listar marcações sintéticas e assinar um webhook que
recebe eventos sintéticos, sem nenhum dado real do tenant de produção aparecer.

### Grupo webhooks

**T9 — Cifra do segredo HMAC (A3)**
`apps/api/app/integracoes/webhooks/cifra.py`: cópia deliberada do padrão de `apps/api/app/terminais/
cifra.py` (AES-256-GCM, `PONTO_WEBHOOK_CHAVE_MESTRA` — hex de 32 bytes, nunca versionada —,
`iv || ciphertext` empacotado em `webhooks.segredo_hmac_cifrado`, `chave_id = "webh-v1"`). Acrescenta o
bloco correspondente a `infra/.env.example` (só este bloco, não edite mais nada do arquivo).
**Pronto quando:** teste prova cifrar/decifrar determinístico e que o segredo em claro nunca é logado.

**T10 — CRUD de webhooks (A3)**
`apps/api/app/routers/webhooks.py` completo: as sete operações já especificadas no contrato
(`criarWebhook`, `listarWebhooks`, `obterWebhook`, `atualizarWebhook`, `excluirWebhook`,
`listarEntregasWebhook`, `reenviarEntregaWebhook`). `criarWebhook` valida `PONTO-WEBH-001` (HTTPS, não
privado/loopback) e `PONTO-WEBH-003` (evento não existe ou não é `webhook_publico: true`) antes de gravar.
Usa `exigir_escopo`/`exigir_idempotencia` de A1.
**Pronto quando:** os sete endpoints respondem de acordo com o contrato, testado contra banco real.

**T11 — Fan-out: de evento de domínio a `webhook_entregas` (A3, a tarefa mais delicada da fase)**
Decide e implementa a costura entre os treze pontos de publicação (§2.2) e uma linha durável em
`webhook_entregas`. **Requisito não negociável (§2.2): a linha só pode existir depois que o fato de
domínio está commitado.** Duas rotas aceitáveis, escolha e documente a decisão no PCF/relatório da fase:
(a) threading do `AsyncSession` até `publicar()` (mudança de assinatura, mecânica, tocando os nove
arquivos `apps/api` do §2.2 e os call sites que os chamam) fazendo o `INSERT` em `webhook_entregas` na
MESMA transação; (b) `publicar()` mantém a assinatura atual e, além de `BARRAMENTO_INTERNO.append`
(inalterado — os testes de F2/F4/F5/F10/F12 dependem dessa lista continuar existindo e se comportando
igual), dispara um mecanismo assíncrono que só considera o evento "real" depois de um sinal de commit
confirmado (documentar precisamente qual sinal, e o tamanho da janela de risco aceita). Qualquer que seja
a rota, para os quatro produtores fora de `apps/api` (worker/device-gw), a mesma exigência de "só depois do
commit" vale — nesses processos, o commit da linha de negócio e a gravação em `webhook_entregas` não podem
compartilhar transação (bancos/processos diferentes de conexão), então esses quatro pontos, por
construção, publicam **depois** do commit local (confirme isso é verdade em cada um antes de acrescentar
a chamada).
**Pronto quando:** teste prova que um evento cuja transação de domínio sofre rollback nunca gera linha em
`webhook_entregas`; teste prova que os treze pontos de publicação, exercitados de ponta a ponta, produzem
entregas pendentes para todo webhook ativo que assina o evento.

**T12 — `enviar_webhook` real e retentativa/DLQ (A3)**
Corpo de `enviar_webhook` em `apps/worker/worker/tarefas/integracoes.py` (assinatura já fixada,
`tenant_id`/`entrega_id`/`webhook_id`/`evento`/`tentativa`): assina o corpo (HMAC-SHA256, formato exato de
`events.yaml`, decifra o segredo com T9), `POST` HTTPS com timeout de `webhooks.timeout_segundos`, sucesso
= qualquer 2xx. Falha: agenda a próxima tentativa (backoff `10s, 30s, 2min, 10min, 30min, 2h, 6h`,
`events.yaml` §entrega) até `max_tentativas`; esgotado, `status='dlq'`, incrementa
`webhooks.falhas_consecutivas`, e ao ultrapassar o limite do webhook marca `status='desabilitado_por_
falha'` e publica `webhook.desabilitado` (você mesmo, primeiro produtor real deste evento). Quem
enfileira cada tentativa: se optou pela rota (a) do T11, o próprio commit já sabe o `entrega_id`; se
optou por uma rotina de cron (mesmo padrão RFC-013/014, reaproveitando `fn_tenants_ativos()`), a rotina
varre `webhook_entregas` com `proxima_tentativa_em <= now()`.
**Pronto quando:** teste prova que um endpoint fora do ar acumula em DLQ (critério de aceite oficial) e
que reativar o webhook zera `falhas_consecutivas`.

**T13 — Reenvio manual (A3)**
Corpo de `reenviarEntregaWebhook` (`POST /v1/webhooks/{webhookId}/entregas/{entregaId}/reenviar`): reseta
`tentativa=1`, `status='pendente'`, enfileira imediatamente, mesmo de uma entrega em `dlq`.
**Pronto quando:** teste prova o reenvio de uma entrega em DLQ chegando ao destino.

**T14 — Painel de entregas (A4)**
`apps/web/src/app/painel/integracoes/**`: CRUD de webhook (mesmo padrão visual de outras telas de
`painel`, F9a), histórico de entregas com filtro por status (`pendente`/`enviando`/`sucesso`/`falha`/
`dlq`/`cancelada`), botão de reenvio manual. Pode desenvolver contra o schema do contrato/um mock local
enquanto A3 não termina; integração final depende de A3 responder de verdade.
**Pronto quando:** criar um webhook, ver uma entrega falhar, forçar acúmulo em DLQ e reenviar pela
própria tela — tudo contra API real.

### Grupo integrações de folha

**T15 — Motor genérico de layout e aplicação da RFC-017 do lado de folha (A5, T1-first do subgrupo)**
Aplica a parte de RFC-017 que lhe cabe: `GET /v1/integracoes/folha/{integracaoId}/exportacoes/
{processamentoId}` (`obterExportacaoFolha`, schema `ProcessamentoAssincrono` já existente, sem schema
novo) em `packages/contracts/openapi.yaml`, regenera `apps/api/app/schemas/contrato.py`, implementa o
corpo em `apps/api/app/routers/integracoes.py`. Depois disso, `apps/api/app/integracoes/folha/comum/**`:
contrato interno (protocolo Python, não OpenAPI) que qualquer
exportador de parceiro implementa — recebe apuração fechada de um período + `mapeamento_rubricas`
(`integracoes_folha.mapeamento_rubricas`, de-para já modelado no schema) e devolve bytes do arquivo.
Implementa também o layout `generico_csv` (parceiro `generico_csv`, já no enum do contrato): CSV bem
documentado, cabeçalho com nome de coluna, um registro por combinação vínculo×dia×componente de apuração,
delimitador `;` (convenção de mercado brasileira, confirmada pela pesquisa desta revisão como o
delimitador dominante nos layouts de folha encontrados). Este é o formato que TODO parceiro sem
especificação pública suficiente usa como base (A6, A7).
**Pronto quando:** teste gera um CSV genérico de uma apuração fechada de fixture e confere campo a campo
contra a documentação que você mesmo escreve no módulo.

**T16 — Domínio e Alterdata (A5)**
`apps/api/app/integracoes/folha/dominio/**`: layout de melhor esforço — pesquisa desta revisão encontrou
só documentação parcial pública (fórum/documento de terceiro, não a fonte oficial do fabricante).
Implemente sobre o motor genérico (T15) com os campos que a documentação parcial confirma, documente no
próprio módulo exatamente quais campos são confirmados e quais são extrapolação, e **registre a lacuna
como débito técnico explícito** (mesmo padrão de ADR-012) — nunca declare "validado contra layout do
parceiro" para Domínio sem essa ressalva.
`apps/api/app/integracoes/folha/alterdata/**`: **este é o único parceiro com posição de campo pública e
verificável** (`ajuda.alterdata.com.br`, layout de largura fixa por posição — Sequencial 1-6, Código
Empresa 7-11, datas 12-23, Faltas 24-29, Horas Trabalhadas 30-35, Código Evento 38-40, Valor Evento
41-54, Código Funcionário 55-60, CNPJ/CPF 62-75, PIS 76-86, Departamento 87-90 — confirme os limites
exatos na fonte antes de codificar, a pesquisa desta revisão não é substituto de leitura primária).
Implemente com fidelidade real; este é o exportador que pode legitimamente dizer "validado contra layout
de referência do parceiro" no relatório final.
**Pronto quando:** Alterdata bate posição a posição contra a documentação oficial (teste que confere cada
campo pela posição, não só "arquivo não quebra"); Domínio gera arquivo plausível com o débito documentado.

**T17 — Família TOTVS: RM, Protheus, Datasul (A6)**
`apps/api/app/integracoes/folha/totvs_{rm,protheus,datasul}/**`: pesquisa desta revisão confirma que os
três não publicam layout fixo — "Automação de Ponto" (RM), GPEA200 (Protheus) e PE0540 (Datasul) são
todas ferramentas de mapeamento configurável pelo próprio cliente/consultor dentro do sistema TOTVS, sem
posição de campo fixa para publicar. Implemente sobre o motor genérico (T15) com a convenção de nome de
arquivo e agrupamento de campos que o padrão TOTVS costuma esperar (delimitador, ordem de coluna
plausível), **documente explicitamente que os três são débito técnico de fidelidade** — nenhum dos três
pode ser descrito como "validado contra layout de referência do parceiro" no relatório final. Nota
alternativa real: os três aceitam AFD como entrada direta (confirmado pela pesquisa) — considere expor
"exportar como AFD" como opção adicional de `formato` para este parceiro, se fizer sentido dentro do
tempo da fase (não é obrigatório, é oportunidade).
**Pronto quando:** os três geram arquivo plausível sobre o motor genérico, com o débito documentado no
próprio módulo e no relatório final da fase.

**T18 — Senior, Sankhya, Questor, Fortes, Contmatic (A7)**
`apps/api/app/integracoes/folha/{senior,sankhya,questor,fortes,contmatic}/**`: mesmo tratamento de T17 —
sobre o motor genérico, com a convenção de nome/formato que a documentação pública de cada um permite
confirmar (Senior e Questor e Contmatic têm ao menos o fluxo/tela documentado publicamente, mesmo sem
campo a campo; Sankhya aceita AFD direto, mesma nota de T17; Fortes não tem nada além do nome do formato
de arquivo, `.ps`/`.csv`, atrás de suporte pago). **Nenhum dos cinco é "validado contra layout de
referência do parceiro"** — declare isso com a mesma clareza de T17.
**Pronto quando:** os cinco geram arquivo plausível com o débito documentado.

### Grupo importador de AFD de terceiros

**T19 — Importador de AFD de terceiro, namespace de NSR separado (A8)**
Primeiro, aplica a parte de RFC-017 que lhe cabe: `GET /v1/importacoes/{importacaoId}` (`obterImportacao`,
schema `Importacao` já existente, sem schema novo) em `packages/contracts/openapi.yaml`, regenera
`apps/api/app/schemas/contrato.py`. Depois, `apps/api/app/integracoes/importadores/afd_terceiro/**`: lê
um AFD de outro fabricante (largura fixa,
ISO-8859-1, mesma estrutura posicional que `docs/leiaute-afd-aej.md` já documenta para o NOSSO AFD — a
norma é a mesma para todo REP-P, então a leitura reaproveita conhecimento, nunca o gerador de F12). Cria
marcações com `canal='importacao'` e `origem_importacao_id` apontando para a linha de `importacoes`
(`tipo='afd_terceiro'`) — **nunca aloca NSR da nossa sequência** (`nsr_sequencias`/`nsr_emissoes`, F5/
ADR-003 item 6): `marcacoes.nsr` é `NOT NULL`, então a linha importada guarda o NSR **do arquivo de
origem** (histórico, não alocado por nós), mas nunca ganha linha correspondente em `nsr_emissoes` —
é essa ausência, não o valor numérico em si, que garante que o registro importado não participa da prova
de sequência sem lacunas do nosso REP-P (ver critério de aceite 8 para o detalhe do mecanismo e da decisão
de `rep_p_id` que você precisa tomar e documentar). `crc16`/`hash_registro`/`hash_anterior` (também `NOT
NULL`) são calculados sobre o próprio registro importado, nunca copiados do arquivo de origem nem
inventados sem fórmula documentada. Rejeita (não trunca, não converte) arquivo que não
esteja em ISO-8859-1 original (`PONTO-IMP-003`, já no catálogo). Publica `importacao.concluida` ao final
(reaproveita o padrão de envelope já usado por `importar_colaboradores`, F2 — não invente um segundo).
Corpo de `criarImportacao`/`listarImportacoes`/`obterImportacao` (RFC-017) em
`apps/api/app/routers/integracoes.py` (só estas três funções).
**Pronto quando:** teste adversarial prova que importar um AFD de outro fabricante, mesmo com NSR
colidindo numericamente com o nosso, nunca produz duas marcações com o mesmo `(rep_p_id, nsr)` na
sequência própria — a marcação importada nunca aparece em `nsr_emissoes`. Teste prova relatório de erro
linha a linha, mesmo padrão de `importar_colaboradores`.

### Grupo SSO — RFC-018/ADR-013 já decididas, sem bloqueio

**T20 — Preparação (A9 e A10, em paralelo)**
Sem rota real ainda nesta tarefa (T21/T22 constroem a rota): escolha de biblioteca (OIDC: `authlib` ou
equivalente já compatível com `httpx`, confirme licença; SAML: `python3-saml` ou `pysaml2`, ambos exigem
`xmlsec`/dependência de sistema — documente o custo de imagem Docker antes de escolher), lógica pura de
resolução de tenant por domínio de e-mail (OIDC) ou por `entityId` do IdP (SAML), desenho da tela de
configuração em `apps/web` contra o schema real já fixado pela RFC-018. **Confirmado pelo ADR-013, não
precisa pesquisar de novo:** `client_secret` de Google/Entra é segredo de AMBIENTE (`Configuracao`, um só
para toda a aplicação), nunca por tenant — só SAML tem configuração por tenant, e é dado público
(certificado X.509), sem cifra.
**Pronto quando:** biblioteca escolhida e justificada; protótipo de troca de código→claims validado
contra um provedor de teste (Google tem ambiente de teste gratuito; SAML pode usar um IdP de teste como
`samltest.id`).

**T21 — Login OIDC (Google Workspace, Microsoft Entra ID) (A9)**
`apps/api/app/identidade/sso/oidc/**` + `apps/api/app/routers/sso.py` (tag `sso`, RFC-018/ADR-013). Fluxo:
iniciar → redirecionar ao IdP → callback troca `code` por `id_token`/claims →
resolve `credenciais` existente por `(tenant_id, provedor_sso, identificador_externo)` ou cria uma nova
vinculada a um `usuarios` já existente (nunca cria usuário novo por SSO nesta fase — decisão de escopo,
documentada; provisionamento automático de usuário fica para trabalho futuro se o produto pedir) → emite
o MESMO par de tokens de sessão que `autenticar`/`renovarSessao` já emitem (reaproveita `apps/api/app/
identidade/tokens`, sem inventar um terceiro formato de sessão). Restrição por tenant: domínio de e-mail
(Google) ou `tenant_id`/`issuer` do token (Entra), guardada em `tenant_configuracoes` (chave-valor JSON,
sem tabela nova — confirme que nenhum dos dois provedores exige segredo por tenant antes de assumir isso).
**Pronto quando:** login end-to-end contra um provedor de teste resulta em sessão válida do sistema, com
`credenciais.tipo='sso'` gravada corretamente.

**T22 — Login SAML 2.0 (A10)**
`apps/api/app/identidade/sso/saml/**`: Assertion Consumer Service que recebe `SAMLResponse` (POST de
formulário, `content: application/x-www-form-urlencoded`, exceção documentada ao padrão JSON do resto do
contrato), valida a assinatura da asserção contra o certificado X.509 do IdP configurado
(`tenant_configuracoes`, chave por tenant — SAML não tem app compartilhado, cada tenant configura seu
próprio IdP, ver RFC-018 §5), resolve/cria `credenciais` do mesmo jeito que T21, emite o mesmo par de
tokens de sessão. Tela de configuração de IdP por tenant (`entityId`/`ssoUrl`/certificado) em
`apps/web/src/app/painel/cadastros/sso/**`.
**Pronto quando:** login end-to-end contra um IdP de teste (`samltest.id` ou equivalente) resulta em
sessão válida; assinatura de asserção adulterada é rejeitada (teste adversarial).

## 7. Critérios de aceite

Os quatro critérios oficiais de `FASES-E-AGENTES.md`, adaptados à luz do que esta revisão encontrou —
leia a nota de cada um antes de declarar "atendido".

1. **"Schemathesis roda contra o OpenAPI sem divergência"** — atendido pelas operações que esta fase
   implementa de ponta a ponta (`admin` api-clients/api-keys, `webhooks`, `integracoes`, e SSO se a
   RFC-018 decidir a tempo). Rotas de fases futuras (F14/F15, se alguma ainda estiver stub) respondem
   `501 PONTO-INT-005` de forma consistente com o catálogo e não contam como divergência real — Schemathesis
   compara forma de resposta contra o schema declarado, não "a regra de negócio existe".
2. **"Webhook com endpoint fora do ar acumula em DLQ e reenvia"** — atendido por T12/T13, teste com
   endpoint simulado indisponível.
3. **"Cada exportador de folha valida contra layout de referência do parceiro"** — **parcialmente
   atendido por desenho, não por limitação de esforço, mesmo padrão de honestidade do critério 1 de
   F12**: só **Alterdata** (T16) tem posição de campo pública e verificável, e é o único exportador para
   o qual este critério é literalmente alcançável e alcançado. Os outros sete (Domínio, família TOTVS,
   Senior, Sankhya, Questor, Fortes, Contmatic) geram arquivo plausível sobre o motor genérico
   documentado (T15), com o débito técnico de fidelidade registrado explicitamente em cada módulo e
   neste relatório — **não declare este critério "atendido" para esses sete sem a ressalva**.
4. **"Importador de AFD de outro fabricante ingere sem quebrar NSR próprio (namespace separado)"** —
   atendido por T19, teste adversarial dedicado.

Critérios adicionais, próprios desta decomposição:

5. Autenticação de cliente (OAuth + API key) funciona de ponta a ponta contra as rotas desta fase — não
   contra as ~130 rotas de F1–F12, que continuam só aceitando sessão humana (§2.3, registrado em backlog).
6. Rate limit por cliente responde `429` com os quatro cabeçalhos `RateLimit-*` corretos.
7. Idempotência genérica (T3) cobre as três semânticas do catálogo (`PONTO-IDEM-001/002/003`) nas rotas
   desta fase.
8. Nenhuma linha desta fase escreve em `nsr_sequencias`, `apuracoes_dia`, `bh_lancamentos`,
   `afd_arquivos`, `aej_arquivos` — prova por análise estática (grep) mais teste de integração. **Exceção
   explícita, não contradição:** o importador de AFD de terceiro (A8, T19) escreve em `marcacoes` por
   desenho — é o próprio objetivo da tarefa. A coluna `marcacoes.nsr` é `NOT NULL` (schema.sql:1939) e a
   unicidade é `(tenant_id, rep_p_id, nsr, datahora_marcacao)` — A8 **não pode** chamar a rotina padrão de
   F5 que aloca NSR a partir de `nsr_sequencias` (violaria ADR-003 item 6 diretamente), então o `INSERT`
   de A8 é necessariamente um caminho próprio, que preenche `nsr` com o valor **do arquivo importado**
   (histórico, não alocado), preenche `crc16`/`hash_registro`/`hash_anterior` com valores calculados sobre
   o próprio registro importado (não pode ficar nulo — são `NOT NULL`, mas também não podem ser confundidos
   com os valores que F5 calcularia para uma marcação nossa — documente a fórmula usada, mesmo padrão de
   honestidade do ADR-012 se não houver uma norma clara para isso), e **nunca** insere nem faz `UPDATE` em
   `nsr_sequencias`/`nsr_emissoes`. Decida e documente no próprio módulo se `rep_p_id` de uma linha
   importada aponta para o REP-P real da empresa ou para um marcador dedicado — qualquer uma das duas é
   aceitável desde que `nsr_emissoes` (a tabela que prova a sequência sem lacunas do NOSSO REP-P) nunca
   ganhe uma linha correspondente. O grep deste critério cobre as outras cinco tabelas listadas acima; para
   `marcacoes`, a prova é o teste adversarial do critério 4 (T19).
9. `webhook.desabilitado` é publicado de verdade pela primeira vez (produtor era inexistente antes desta
   fase, confirmado em `docs/backlog.md`).
10. Toda rota nova declara `x-permissao`/`x-escopo` idênticos ao contrato — mesmo teste que F4/F10/F12 já
    escreveram, estendido às operações novas.
11. Grupo SSO: RFC-018/ADR-013 já decididas antes do build — o relatório final da fase prova login
    end-to-end real contra OIDC (Google/Entra, T21) e SAML (T22), não apenas "não bloqueado".
12. Contrato tocado só nos pontos nomeados: `git status --short packages/contracts` mostra só as linhas
    das RFC-016/017/018, nada mais.
13. Cobertura ≥ 85% em `app.integracoes`, `app.comum.autenticacao_cliente`, `app.comum.limitador_taxa`,
    `app.comum.idempotencia_generica` (o alvo é levemente mais baixo que o costume de 90% de fases
    anteriores porque parte do código desta fase — os sete exportadores de melhor esforço — tem valor de
    teste limitado por design: não há como testar fidelidade contra um layout que não existe
    publicamente; teste o que é testável, documente o resto).

## 8. Comandos de verificação

Rode a partir da raiz do repositório. Windows usa `.\tasks.ps1`; Linux/macOS usa `make`.

Subir a stack:
```bash
docker compose --env-file infra/.env.example -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d postgres redis minio
```
```powershell
.\tasks.ps1 up
```

Migrar (só A1 tem migration nova nesta fase):
```bash
cd apps/api && alembic upgrade head
```

Lint, formatação e tipos:
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

Testes da fase:
```bash
cd apps/api && pytest tests/f13 -q --cov=app.integracoes --cov=app.comum.autenticacao_cliente --cov=app.comum.limitador_taxa --cov=app.comum.idempotencia_generica --cov-report=term-missing
cd apps/worker && pytest tests/f13 -q
```

Inventário de rotas idêntico ao contrato (inclui as RFC-016/017 e, se decidida, RFC-018):
```bash
cd apps/api && python tools/conferir_rotas.py
```

Schemathesis (nova nesta fase, T6):
```bash
schemathesis run packages/contracts/openapi.yaml --base-url http://localhost:8000 --checks all
```

Fan-out transacional (T11 — o teste mais importante da fase):
```bash
cd apps/api && pytest tests/f13/webhooks -q -k "rollback or transacional" -s
```

DLQ e retentativa:
```bash
cd apps/api && pytest tests/f13/webhooks -q -k "dlq or retentativa or reenvio" -s
```

Namespace de NSR do importador de AFD de terceiro (o teste adversarial do critério 4):
```bash
cd apps/api && pytest tests/f13/importadores/afd_terceiro -q -k "nsr or namespace" -s
```

Regressão de F1–F12 (não podem quebrar — atenção especial aos nove arquivos `eventos.py` tocados):
```bash
cd apps/api && pytest tests/f1 tests/f2 tests/f4 tests/f5 tests/f6 tests/f9b tests/f10 tests/f11 tests/f12 -q
cd apps/worker && pytest tests -q
```

Regressão do andaime da Fase 0:
```bash
cd apps/api && pytest tests/test_andaime.py -q
```

Contrato tocado só onde autorizado:
```bash
git status --short packages/contracts
```
**Saída esperada:** só as linhas de RFC-016/RFC-017 (e RFC-018 se decidida) — nenhuma outra.

`apps/mobile` intocado:
```bash
git status --short apps/mobile
```
**Saída esperada:** sem saída nenhuma.

Migration reversível:
```bash
cd apps/api && alembic upgrade head && alembic downgrade base && alembic upgrade head
```

Web (portal, painel, telas de SSO):
```bash
cd apps/web && pnpm lint && pnpm exec tsc --noEmit && pnpm build && pnpm test
cd apps/web && pnpm exec playwright test src/testes/f13
```

## 9. Proibições

1. **Não edite `apps/api/app/core/seguranca.py` nem `apps/api/app/identidade/tokens/middleware.py`.**
   São de F1/A3, com trava explícita no próprio arquivo. A solução desta fase (T1, dependência
   autocontida) existe exatamente para não precisar disso (§2.3).
2. **Não redecida a RFC-018/ADR-013.** Já decididas pelo orquestrador (tag `sso`, app OIDC compartilhado,
   SAML por tenant) — implemente exatamente o que está escrito, não "melhore" a decisão no meio do
   trabalho. Se encontrar uma lacuna de contrato NOVA (não coberta por nenhuma RFC existente) durante o
   build, sempre deixe como `Proposta`, nunca `Decidida` por conta própria — mesmo que a resposta pareça
   óbvia (§2.1, nota de processo).
3. **Não mude `BARRAMENTO_INTERNO`, `montar_envelope` nem `limpar_barramento` nos nove arquivos
   `eventos.py`** — nome, assinatura e comportamento continuam exatamente como estão, testes de F2/F4/F5/
   F10/F12 dependem disso. Se a rota escolhida em T11 for threading de `AsyncSession` até `publicar()`
   (opção (a) do T11), a MUDANÇA é aditiva e restrita à assinatura/corpo de `publicar()` em si — nunca às
   três funções acima, e nunca reordenando ou removendo nada que já existe no arquivo.
4. **Não prometa fidelidade de layout que a pesquisa não confirmou.** Domínio, família TOTVS, Senior,
   Sankhya, Questor, Fortes, Contmatic: documente o débito técnico com a mesma clareza que ADR-011/
   ADR-012 já estabeleceram. "Funciona e não quebra" não é o mesmo que "validado contra layout do
   parceiro" — não confunda os dois no relatório final.
5. **Não crie uma segunda função `SECURITY DEFINER` para enumeração cross-tenant.** `fn_tenants_ativos()`
   já existe e está pré-aprovada (RFC-013/014) para qualquer rotina de cron cross-tenant futura — reuse.
6. **Não invente um segundo cliente MinIO.** `app.comum.armazenamento` (F10) é reaproveitável para
   arquivo de folha exportado e relatório de erro de importação.
7. **Não aloque NSR da sequência própria para marcação importada de AFD de terceiro.** ADR-003 item 6 é
   explícito: namespace separado, sempre.
8. **Não implemente cálculo de apuração, banco de horas ou geração de AFD/AEJ.** Esta fase só exporta o
   que F4/F12 já calculam e geram.
9. **Não rode `python tools/gerar_do_contrato.py` depois de começar a implementar.** Sobrescreve todos os
   routers de F1–F12 de volta a stub.
10. **Não toque em `apps/mobile`.** Fora do escopo desta fase.
11. **Não crie usuário novo automaticamente no primeiro login SSO.** Vincula a um `usuarios` já existente;
    provisionamento automático é decisão de produto fora do escopo desta fase (documentado em T21/T22).
12. **Não retrofite idempotência genérica nem autenticação de cliente nas ~130 rotas de F1–F12.**
    Registrado em `docs/backlog.md` para uma fase de hardening futura — não é invenção de escopo desta
    fase tentar "aproveitar que já construiu o mecanismo" para consertar tudo.
