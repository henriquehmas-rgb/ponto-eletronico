# F05 — Ingestão de Marcações e NSR

| | |
|---|---|
| **Onda** | 2 |
| **Agentes** | 3 · **A1** domínio da marcação (tabela append-only, NSR transacional, CRC-16, hash encadeado) · **A2** pipeline canal-agnóstico (idempotência, fila offline, resolução de duplicata, carimbo do servidor) · **A3** comprovante, estrutura do score de confiança e consulta |
| **Duração estimada** | 6 dias |
| **Depende de** | F0 (contratos e andaime), F1 (autenticação, RBAC e `app/core/seguranca.py` reais), F2 (cadastros — `colaboradores`, `vinculos`, `dispositivos`, `dispositivo_vinculos`, geocerca e allowlist CIDR reais) |
| **Criticidade** | ⭐ Crítica — F4, F6, F12 e F14 não têm o que consumir sem esta fase; F6 roda **em paralelo** na mesma onda e chama `POST /v1/marcacoes` como cliente HTTP |
| **Branch** | `f05-ingestao-marcacoes-nsr` |

---

## 1. Objetivo

Ao fim desta fase, **qualquer canal (terminal, aplicativo, navegador, totem ou
API) registra uma marcação de ponto por uma única operação canal-agnóstica que
o servidor carimba com o próprio relógio, sequencia com um NSR transacional
sem lacunas por REP-P, protege com CRC-16 e hash encadeado, e que o banco
recusa por conta própria alterar ou apagar depois — com as 9 operações das
tags `marcacoes` e `comprovantes` respondendo exatamente o que o `openapi.yaml`
promete, no lugar do `501` de hoje**, e as duas provas adversariais que a Fase
0 deixou pendentes (imutabilidade sob `UPDATE`/`DELETE` reais e ausência de
lacuna de NSR sob 10.000 gravações concorrentes) finalmente **executadas**
contra um PostgreSQL 16 real, não apenas lidas no código.

## 2. Contexto mínimo

**O produto.** Este é um sistema de ponto eletrônico brasileiro do tipo
**REP-P** — *Registrador Eletrônico de Ponto via Programa*, a modalidade de
software prevista na Portaria MTP 671/2021. Ele é vendido como SaaS
multi-tenant: toda tabela de domínio carrega `tenant_id` sob **Row Level
Security** do PostgreSQL, e a aplicação abre cada transação publicando
`app.tenant_id` (`apps/api/app/db/sessao.py::obter_sessao`, já real, entregue
pela F1). **Você não desabilita RLS e não contorna essa resolução.**

**Marcação não é apuração.** Este é o núcleo mais crítico do produto do ponto
de vista legal, mas a fase é deliberadamente estreita: você **ingere,
sequencia e imortaliza** o registro de ponto. Você **não calcula** jornada,
horas extras, banco de horas nem nada que dependa de regra trabalhista — isso
é da F4, que roda depois e lê `marcacoes` como fato imutável. Se você sentir
vontade de "adiantar" cálculo aqui, pare: não é escopo.

**Por que marcação é imutável — e por que isso não é preferência de
engenharia.** A Portaria 671/2021 veda ao REP **alterar ou apagar** marcação e
veda **inserir** marcação que não corresponda ao fato real. A decisão do
projeto está em **ADR-002** e **você não pode redecidi-la**: a tabela
`marcacoes` é *append-only*, particionada por mês em `datahora_marcacao`, e a
vedação é imposta em três camadas independentes — (1) a tag `marcacoes` do
`openapi.yaml` não declara `PUT`/`PATCH`/`DELETE` e você não os adiciona; (2)
o gatilho `fn_registro_imutavel()` aborta `UPDATE`, `DELETE` e `TRUNCATE` com
`ERRCODE 42501`; (3) a role `ponto_app` não recebe esses privilégios na
tabela. Toda correção de jornada vive em `tratamentos` (tag e tabela de outra
fase — ver §4), que se soma à marcação na apuração sem jamais tocá-la.
Tentativa de alterar responde `PONTO-MARC-001`; de excluir, `PONTO-MARC-002` —
mas como as rotas não existem, isso é inalcançável pela API por construção; o
que você precisa **provar por execução** é a segunda e a terceira camada
contra um Postgres real (§6, §7).

**NSR: por que não é uma `SEQUENCE` do PostgreSQL.** O Número Sequencial de
Registro é o identificador de cada linha do AFD, exigido pela Portaria a
começar em 1, sequencial, **sem lacuna e sem reuso**, por REP-P. A decisão está
em **ADR-003** e também é fechada: `SEQUENCE`/`SERIAL`/`GENERATED AS IDENTITY`
não são transacionais — não voltam atrás em `ROLLBACK` — e uma transação
abortada (falha de validação, deadlock, restart) deixaria um buraco
permanente. Em vez disso, `nsr_sequencias` guarda uma linha por REP-P com o
próximo valor a emitir, e a alocação é um `UPDATE ... RETURNING` que toma o
bloqueio da linha **na mesma transação** que grava a marcação: commit publica
os dois, rollback desfaz os dois. Lacuna vira **impossível por construção**,
não por convenção. **O NSR é ordem de gravação, não ordem cronológica**: uma
marcação offline de terça que chega na quinta recebe o NSR da quinta e carrega
a data/hora real no campo próprio — nunca force os dois a coincidir.

**REP-P não é o terminal.** `rep_ps` identifica cada instância do **nosso
software** em operação — o REP-P é quem atribui NSR, calcula CRC-16 e grava no
AFD. O terminal Control iD (F6, rodando em paralelo) é um **coletor**: ele
identifica a pessoa e produz um evento local (`access_log`); é o `device-gw`
(F6) quem converte isso e chama `POST /v1/marcacoes` como qualquer outro
cliente. Uma empresa normalmente tem um REP-P; o cadastro do REP-P (tag
`fiscal`, `POST /v1/fiscal/rep-ps`) é da **F12** — nesta fase você só **lê**
`rep_ps` (existência e status `ativo` por empresa) para decidir se pode
sequenciar. Sem REP-P ativo, a resposta é `PONTO-MARC-010`.

**A tabela `marcacoes` sozinha não basta para as garantias do contrato — e
isso já está resolvido no `schema.sql`, não é algo para você reabrir.** Uma
`UNIQUE` em tabela particionada por PostgreSQL precisa incluir a coluna de
partição; por isso `uq_marcacoes_nsr` só garante unicidade **dentro do mês**.
Duas tabelas não particionadas complementam: `nsr_emissoes` impõe a
unicidade **global** de `(tenant_id, rep_p_id, nsr)` e torna a detecção de
lacuna uma consulta trivial; `marcacao_idempotencia` impõe, também de forma
global (entre meses), a unicidade das quatro chaves de deduplicação. Ambas são
*append-only* como `marcacoes` (mesmo gatilho, mesma revogação de privilégio).

**Canal-agnóstico de verdade.** `POST /v1/marcacoes` é a **única** porta de
entrada para todo registro de ponto — terminal, app, navegador, totem e API
chamam exatamente a mesma operação, com o mesmo corpo (`MarcacaoCriar`). A F6
(Control iD), rodando em paralelo nesta mesma onda, **não escreve em nenhuma
tabela desta fase**: ela converte `access_log` em `MarcacaoCriar` e chama este
endpoint pela rede, exatamente como o app ou o navegador chamariam. Isso
significa que, até você terminar, a F6 recebe `501` — ela testa a conversão
com um duplo local e reserva um teste de integração ponta a ponta para quando
você estiver pronto. **Não mude o formato de `MarcacaoCriar`/`MarcacaoCriada`
nem os códigos de erro sem RFC** — a F6 já codifica contra eles.

**O relógio é do servidor, sempre.** `datahora_marcacao` (o momento do fato,
que vai para o AFD e para o espelho) é **sempre** atribuído pelo servidor —
nunca aceito do cliente — exceto no caminho de sincronização offline, onde o
horário real da captura é preservado a partir do relógio do aparelho
(evidenciado, nunca cego: ver próximo parágrafo) porque a Portaria não abre
exceção para "quando o servidor recebeu", só para "quando o fato ocorreu".
`datahora_dispositivo` (relógio do aparelho) e `datahora_gravacao` (quando o
servidor persistiu) existem à parte, **apenas como evidência** — nunca são a
fonte de verdade legal.

**Idempotência é requisito de primeira ordem, não um detalhe de API.**
Como marcação nunca pode ser apagada depois, uma duplicata real de ingestão
(o mesmo evento físico chegando duas vezes) tem que ser **evitada antes**, não
corrigida depois. Existem **quatro** chaves de deduplicação, independentes e
simultâneas: `external_id` (canal `api`), o par `dispositivo_id +
log_externo_id` (catch-up de terminal, canal `terminal`), o cabeçalho
`Idempotency-Key` (toda escrita) e o HMAC do item da fila offline (`escopo
offline_hmac`, sobre `marcacao_idempotencia`). Reenviar o mesmo registro por
qualquer uma delas devolve a marcação **original**, nunca cria uma segunda.
Colisão de chave de domínio (`external_id`/`dispositivo+log`) sem a mesma
`Idempotency-Key` responde `PONTO-MARC-003`; reuso da própria
`Idempotency-Key` com corpo diferente responde `PONTO-IDEM-002`; chamada
concorrente com a mesma chave ainda em voo responde `PONTO-IDEM-003`.

**Offline não é um canal — é um estado.** O app, o totem e o terminal podem
capturar sem rede e sincronizar depois. `POST /v1/marcacoes/sincronizar-offline`
recebe um **lote síncrono** (resposta `207`, com o desfecho de cada item já
resolvido na mesma chamada — isto não é um job assíncrono) de itens cifrados
em AES-256-GCM e assinados por HMAC com contador monotônico anti-*replay*;
contador repetido é `PONTO-MARC-007`, HMAC inválido é `PONTO-MARC-006`, item
fora do TTL de sincronização (padrão 72 h, configurável em
`politicas_registro.ttl_offline_horas`) vira ocorrência para tratamento humano
— nunca marcação silenciosa — e responde `PONTO-MARC-005`. A marcação
resultante fica sinalizada `coletada_offline = true` no espelho: **o sistema
nunca finge que foi online**.

**Score de confiança: aqui é só a estrutura, a régua chega na F14.** Toda
marcação carrega, em `marcacoes_meta`, um contexto antifraude (geocerca,
similaridade facial, prova de vida, sinais de attestation/RASP/mock
location/câmera virtual, e um `score_confianca` de 0–100 com
`classificacao_confianca` resultante). A composição do score a partir dos
sinais brutos — quanto cada sinal pesa, como se combinam — é **da F14**
(FASES-E-AGENTES.md, F14/A1). **Você entrega a estrutura**: as colunas, o
armazenamento dos sinais brutos tal como o cliente informou, a API de
leitura (`obterMetaMarcacao`) e um módulo com **assinatura pública fixa**
(`app/marcacao/confianca/motor.py::avaliar_confianca`, conteúdo literal na
§5) cujo corpo hoje é **permissivo por padrão** — sempre devolve
`score=100, classificacao="alta"` — e que a F14 substitui **sem mudar a
assinatura**, exatamente como a F1 substituiu o *auth stub* que a F2 usava em
paralelo. Isso significa que, ao fim desta fase, `PONTO-SCORE-001..004`,
`PONTO-GEO-003` (localização simulada) e `PONTO-DISP-003/004/005` (attestation
reprovado, modo desenvolvedor, ambiente comprometido) estão **conectados no
código mas nunca disparam de fato** — isso é o comportamento correto e
esperado, não uma lacuna sua para preencher. Documente isso explicitamente no
docstring do módulo.

**O que, dentro do score, você implementa de verdade (não é stub).** Três
verificações **não** exigem "julgamento" de sinal antifraude — são
comparações estruturais que a F2 já entregou prontas e testadas, e que fazem
parte do pipeline de ingestão desde já: **geocerca** (`app.organizacao.geocerca.dentro_da_geocerca`,
função pura) e **allowlist CIDR** (`app.organizacao.redes.ip_autorizado`,
função pura) — ambas obrigatórias ou não conforme `politicas_registro.exige_geocerca`
/`exige_rede_permitida` e a política de bloqueio/sinalização
(`politica_fora_geocerca`) — e o **vínculo do dispositivo pessoal** ao
colaborador (`dispositivo_vinculos.status = 'ativo'`, só para `canal = 'mobile'`
— um terminal ou totem não é "vinculado" a uma pessoa). Essas produzem
`PONTO-GEO-001/002`, `PONTO-REDE-001` e `PONTO-DISP-001/002` **de verdade**.
`PONTO-REDE-002` (bloqueio de VPN/proxy/ASN de datacenter) não é seu: é da F8
(canal web) e da F14.

**`politicas_registro` é lida por você em todo registro — não escrita por
você.** Não existe, em nenhuma tag do `openapi.yaml`, operação de CRUD para
esta tabela — verificado: ela não aparece em nenhum `path`. Você **lê** a
linha mais específica que casar com `(tenant_id, empresa_id, unidade_id,
canal)` (a `UNIQUE` da tabela usa `COALESCE` para tratar `unidade_id`/`canal`
nulos como coringa — consulte do mais específico ao mais genérico) e, **na
ausência de qualquer linha**, aplica os mesmos `DEFAULT` que a coluna já tem
no `schema.sql` (`exige_geocerca=true`, `exige_facial=true`,
`exige_rede_permitida=false`, `limiar_bloqueio=40`, `limiar_revisao=70`,
`exige_reautenticacao=true`, `ttl_offline_horas=72`). Não invente endpoint
para esta tabela; se achar que falta uma forma de configurá-la, é achado de
backlog (fase sugerida: quem primeiro precisar editá-la em produção), não
invenção sua.

**Reautenticação para bater ponto pela web.** `politicas_registro.exige_reautenticacao`
(default `true`) exige que `sessoes.reautenticado_em` (coluna que a F1 já
grava via `POST /v1/auth/reautenticar`) seja recente; sem isso, responde
`PONTO-AUTH-011`. Você **lê** esse carimbo — não implementa a rota de
reautenticação, que já existe (F1).

**Comprovante é emitido na mesma transação da marcação, não depois.** A
Portaria dispensa a impressão no momento da batida porque o produto garante
acesso eletrônico permanente, com as **últimas 48 horas** sempre disponíveis
em app e web — por isso existe a operação dedicada
`GET /v1/colaboradores/{colaboradorId}/comprovantes/recentes` (janela padrão
48 h, mínimo legal, mas o produto mantém acesso permanente por padrão). O
comprovante (`comprovantes`, também *append-only*) carrega NSR, CPF, hash e,
quando já houver certificado, a referência da assinatura CAdES — a assinatura
em si é da **F12**; aqui o campo fica vazio até lá.

**Vocabulário proibido.** Nunca "batida" (é **marcação**); nunca "editar
marcação" (não existe — correção é **tratamento**, de outra fase); nunca
"relógio de ponto" (é **coletor**); nunca "empresa" para dizer cliente do
SaaS (é **tenant**).

**Fase 0 é congelada.** `packages/contracts/` não se altera. Divergência vira
RFC (`docs/rfc/README.md`), nunca contorno silencioso.

## 3. Leituras obrigatórias (lista fechada)

Leia isto e pare. Não leia `PROJETO.md`, não leia outras fases, não leia o
código de F1/F2/F6 além dos módulos explicitamente listados abaixo.

- `packages/contracts/openapi.yaml` — **apenas** as tags `marcacoes` (6
  operações) e `comprovantes` (3 operações). Leia também, em `components`:
  `parameters` (`CabecalhoTenant`, `CabecalhoRequestId`, `CabecalhoIdempotencia`,
  `Cursor`, `Limite`, `Ordenar`), `headers` (`IdempotencyReplayed`,
  `RateLimit-*`), `responses` (`Erro400`..`Erro503`), o schema `Problema` e os
  schemas `MarcacaoCriar`, `MarcacaoCriada`, `Marcacao`, `MarcacaoMeta`,
  `ListaMarcacao`, `ItemFilaOffline`, `SincronizacaoOfflineRequisicao`,
  `ResultadoItemOffline`, `SincronizacaoOfflineResposta`, `VerificacaoNsr`,
  `Comprovante`, `ListaComprovante`.
- `packages/contracts/schema.sql` — seção **8 (MARCACAO — NUCLEO LEGAL)**
  inteira: tabelas `rep_ps`, `nsr_sequencias`, `marcacoes` (+ `marcacoes_default`
  e a função `fn_cria_particao_marcacoes`), `nsr_emissoes`,
  `marcacao_idempotencia`, `marcacoes_meta`, `fila_offline`, `comprovantes`,
  `politicas_registro`. Leia também, na seção **1 (DOMINIOS)**: `dom_cpf`,
  `dom_pis`, `dom_sha256`, `dom_fuso`. Função `fn_registro_imutavel()` (seção
  raiz do arquivo, comentário completo). **Não** leia as seções 3–7 nem 9 em
  diante além do necessário para entender FK (`colaboradores`, `vinculos`,
  `empresas`, `unidades`, `dispositivos`, `dispositivo_vinculos`, `terminais` —
  só os nomes de coluna que você referencia por FK).
- `packages/contracts/models/marcacao.py` — classes `RepP`, `NsrSequencia`,
  `Marcacao`, `NsrEmissao`, `MarcacaoIdempotencia`, `MarcacaoMeta`,
  `FilaOffline`, `Comprovante`, `PoliticaRegistro`. Mais `models/base.py`,
  `models/mixins.py`, `models/tipos.py`.
- `packages/contracts/errors.yaml` — categorias **MARC** (10 códigos),
  **SCORE** (4), **GEO** (3), **REDE** (2), **DISP** (6, você usa só 001/002
  de verdade), **IDEM** (3), e os transversais **VAL-001, VAL-005, VAL-007,
  VAL-009, VAL-010, VAL-011**, **TEN-002, TEN-003, TEN-004**, **PERM-001,
  PERM-002**, **AUTH-002, AUTH-003, AUTH-004, AUTH-006, AUTH-011, AUTH-013**,
  **LGPD-002**, **RATE-001, RATE-002**, **REC-001**, **INT-001..005**.
- `packages/contracts/events.yaml` — envelope de entrega e os eventos
  `marcacao.criada`, `marcacao.suspeita`, `marcacao.sincronizada_offline`,
  `comprovante.emitido`.
- `packages/contracts/glossario.md` — seções **1**, **1.1 (RLS)**, **1.2
  (Imutabilidade)**; verbetes **Comprovante**, **Idempotência**, **Marcação**,
  **Mock location**, **NSR**, **Ocorrência**, **REP-P**, **Score de
  confiança**; seção **3.1** (linhas `nsr_emissoes`, `marcacao_idempotencia`,
  `politicas_registro`); seção **3.2** (subseções `marcacoes.tipo_registro` ×
  `sentido_informado`, `marcacoes_meta` não particionada, partição
  `marcacoes_default`, e **`Comprovante.datahoraMarcacao` (API) ×
  `comprovantes.marcacao_datahora` (banco)** — divergência deliberada, RFC-001
  D-07, atenção ao mapear o schema Pydantic); seção **5 (sequência
  canônica)**; seção **6 (termos proibidos)**.
- `docs/adr/ADR-002-imutabilidade-marcacao-camada-tratamento.md` — **decisão
  fechada, não redecidir.**
- `docs/adr/ADR-003-geracao-nsr-sequencial-sem-lacunas.md` — **decisão
  fechada, não redecidir**; contém o algoritmo de alocação de NSR que você vai
  implementar.
- `docs/rfc/RFC-002-acoes-de-permissao-fora-do-check.md` — por que
  `marcacoes.ler_sensivel` existe como ação de permissão (já seedada pela F1;
  você só usa).
- `apps/api/app/core/seguranca.py`, `apps/api/app/db/sessao.py` — reais,
  entregues pela F1. `Sujeito`, `exigir_permissao`, `exigir_alcance`,
  `tenant_id_ou_erro`, `SessaoDb`.
- `apps/api/app/organizacao/geocerca.py` (`dentro_da_geocerca`,
  `GeocercaUnidade`, `ResultadoGeocerca`) e `apps/api/app/organizacao/redes.py`
  (`ip_autorizado`, `FaixaPermitida`, `ip_valido`) — funções puras reais,
  entregues pela F2. **Não as reescreva; importe-as.**
- `apps/api/app/pessoas/eventos.py` — **leia só como referência de padrão**
  (não importe: é módulo próprio da F2). Mostra a forma exigida do barramento
  interno (`montar_envelope`/`publicar`) que você replica no seu próprio
  módulo (§5).
- `apps/api/app/routers/marcacoes.py`, `apps/api/app/routers/comprovantes.py`
  — o andaime que você preenche (stubs `501`/`PONTO-INT-005`).
- `apps/api/app/schemas/contrato.py` (gerado) — só para conhecer os modelos
  Pydantic que as rotas já declaram (`contrato.MarcacaoCriar`,
  `contrato.MarcacaoCriada`, etc.).
- `docs/fases/F06-integracao-control-id.md`, seção 2 apenas (parágrafos "Ponto
  de atenção nº 2" e a explicação de idempotência por
  `dispositivo_id + log_externo_id`) — para entender exatamente como a F6, que
  roda em paralelo, vai **chamar** o seu endpoint. Não leia o resto do arquivo.
- `docs/rfc/README.md` e `docs/backlog.md` — o protocolo, e os dois itens já
  herdados da Fase 0 endereçados a esta fase (teste adversarial de
  imutabilidade nunca executado contra Postgres real; teste de concorrência de
  NSR nunca executado — ver §6 e §7).

## 4. Contratos

**Consome** — já existe, esta fase apenas usa:

- Tabelas, policies e roles de `apps/api/migrations/versions/0001_inicial.py`
  (`rep_ps`, `nsr_sequencias`, `marcacoes` + partições 2026–2027 +
  `marcacoes_default`, `nsr_emissoes`, `marcacao_idempotencia`,
  `marcacoes_meta`, `fila_offline`, `comprovantes`, `politicas_registro`, e as
  tabelas de F1/F2 referenciadas por FK: `empresas`, `unidades`,
  `colaboradores`, `vinculos`, `dispositivos`, `dispositivo_vinculos`,
  `sessoes`).
- `app/core/seguranca.py` (`Sujeito`, `exigir_permissao`, `exigir_alcance`,
  `tenant_id_ou_erro`), `app/db/sessao.py` (`SessaoDb`, `obter_sessao`),
  `app/core/erros.py` (`ErroDeAplicacao`, `RESPOSTAS_PADRAO`),
  `app/core/catalogo_erros.py` — todos reais, entregues por F1/F0.
- `app.organizacao.geocerca.dentro_da_geocerca` e
  `app.organizacao.redes.ip_autorizado` (+ `FaixaPermitida`) — funções puras
  reais, entregues pela F2.
- Permissões já semeadas por `migrations/seed_dev.py` (F1/A3, T8):
  `marcacoes.criar`, `marcacoes.ler`, `marcacoes.exportar`,
  `marcacoes.ler_sensivel`, `comprovantes.ler`, `comprovantes.exportar`.
  **Nenhuma permissão nova é necessária para esta fase.**

**Produz** — esta fase implementa:

*Endpoints (9 operações; hoje `501`):*

| Método | Caminho | `operationId` | Permissão exigida | Agente |
|---|---|---|---|---|
| POST | `/v1/marcacoes` | `criarMarcacao` | `marcacoes.criar` | A2 |
| GET | `/v1/marcacoes` | `listarMarcacoes` | `marcacoes.ler` | A3 |
| GET | `/v1/marcacoes/{marcacaoId}` | `obterMarcacao` | `marcacoes.ler` | A3 |
| GET | `/v1/marcacoes/{marcacaoId}/meta` | `obterMetaMarcacao` | `marcacoes.ler_sensivel` | A3 |
| POST | `/v1/marcacoes/sincronizar-offline` | `sincronizarMarcacoesOffline` | `marcacoes.criar` | A2 |
| GET | `/v1/marcacoes/nsr/verificar` | `verificarSequenciaNsr` | `marcacoes.ler` | A1 |
| GET | `/v1/comprovantes` | `listarComprovantes` | `comprovantes.ler` | A3 |
| GET | `/v1/comprovantes/{comprovanteId}` | `obterComprovante` | `comprovantes.ler` | A3 |
| GET | `/v1/colaboradores/{colaboradorId}/comprovantes/recentes` | `listarComprovantesRecentes` | `comprovantes.ler` | A3 |

*Tabelas escritas:* `marcacoes` (append-only, INSERT apenas), `nsr_emissoes`
(INSERT apenas), `nsr_sequencias` (UPDATE do contador, mesma transação),
`marcacao_idempotencia` (INSERT apenas), `marcacoes_meta` (INSERT; revisão
futura fora de escopo), `fila_offline` (INSERT + UPDATE de status durante o
processamento síncrono do lote), `comprovantes` (INSERT apenas).
`rep_ps` e `politicas_registro` são **somente leitura** para esta fase.

*Módulos internos publicados para outras fases:*
`app/marcacao/confianca/motor.py::avaliar_confianca` — assinatura fixa (§5)
que a **F14** substitui sem mudar a forma. `app/organizacao/geocerca.py` e
`app/organizacao/redes.py` continuam sendo consumidos (não republicados) por
esta fase.

*Eventos publicados:* `marcacao.criada` (toda gravação bem-sucedida, canal
qualquer), `marcacao.suspeita` (só quando `avaliar_confianca` classificar
`media` — na prática, com o stub permissivo desta fase, **nunca** dispara;
fica conectado para a F14 ativar), `marcacao.sincronizada_offline` (por item
convertido com sucesso no lote síncrono), `comprovante.emitido` (na mesma
transação da marcação). Envelope exato de `events.yaml`
(`id, tipo, versao, ocorridoEm, tenantId, dados`).

**Não toca** — é de outra fase, mesmo que pareça relacionado:

- Tag `terminais` e tabelas `terminais`, `terminal_saude` (**F6**, rodando em
  paralelo). A F6 **chama** `POST /v1/marcacoes`; ela não escreve em nenhuma
  tabela desta fase, e você não implementa nada específico de Control iD.
- Tag `fiscal` (`rep_ps` CRUD, geração de AFD/AEJ, assinatura CAdES) —
  **F12**. Você só lê `rep_ps`; não implementa `POST /v1/fiscal/rep-ps`.
- Tag `tratamentos` e a tabela `tratamentos` — correção de jornada, **outra
  fase** (motor de apuração, F4, e workflow, F10). Você nunca sugere "editar"
  marcação.
- Julgamento antifraude real (attestation criptográfico, RASP, mock location,
  câmera virtual, reputação de dispositivo) e a composição do score de
  confiança — **F14**. Você entrega a estrutura e o stub permissivo (§5).
- Bloqueio de VPN/proxy/ASN de datacenter (`PONTO-REDE-002`) — **F8** (canal
  web) e **F14**.
- Cadastro de `empresas`, `unidades`, `colaboradores`, `contratos`,
  `vinculos`, `dispositivos`, `dispositivo_vinculos`, `biometrias` — **F2**,
  já concluída. Você só lê.
- Autenticação, RBAC, resolução de tenant, trilha de auditoria — **F1**, já
  concluída. Você só usa `app/core/seguranca.py` e `app/db/sessao.py`.
- Entrega de webhook (assinatura HMAC, retentativa, *dead letter*) para os
  eventos que você publica — **F13**. Você só publica no barramento interno
  da fase e prova por teste que o *payload* bate campo a campo.
- `packages/contracts/**` — **congelado**.
- `apps/web`, `apps/mobile`, `apps/worker`, `apps/device-gw`, `apps/facial-svc`.

## 5. Ownership de arquivos

Caminhos **exclusivos** desta fase. **F5 e F6 rodam em paralelo** na Onda 2;
a F6 só toca sua fronteira via HTTP (`POST /v1/marcacoes`), nunca em arquivo.

| Agente | Caminhos |
|---|---|
| **A1** (domínio) | `apps/api/app/marcacao/dominio/**`<br>`apps/api/tests/f5/conftest.py`<br>`apps/api/tests/f5/dominio/**` |
| **A2** (pipeline) | `apps/api/app/marcacao/pipeline/**`<br>`apps/api/tests/f5/pipeline/**` |
| **A3** (comprovante, score, consulta) | `apps/api/app/marcacao/comprovantes/**`<br>`apps/api/app/marcacao/confianca/**`<br>`apps/api/app/marcacao/consulta/**`<br>`apps/api/app/routers/comprovantes.py`<br>`apps/api/tests/f5/consulta/**` |

**Compartilhado dentro da fase** (exige combinação entre A1, A2 e A3):

| Caminho | Regra |
|---|---|
| `apps/api/app/marcacao/__init__.py` | Criado por **A1** na T1, com uma docstring e nada mais. Ninguém acrescenta código aqui. |
| `apps/api/app/marcacao/eventos.py` | Criado por **A1** na T1 com o conteúdo literal abaixo. Depois disso, **só A1 edita.** A2 e A3 só importam `montar_envelope` e `publicar`; cada um cria seu **próprio** módulo de publicação específica (`app/marcacao/pipeline/eventos_marcacao.py` para A2; `app/marcacao/comprovantes/eventos_comprovante.py` para A3) — nunca acrescentem função neste arquivo. |
| `apps/api/app/routers/marcacoes.py` | Compartilhado **por operationId**, nunca por linha alheia: **A1** edita só o corpo de `verificar_sequencia_nsr`; **A2** edita só `criar_marcacao` e `sincronizar_marcacoes_offline`; **A3** edita só `listar_marcacoes`, `obter_marcacao` e `obter_meta_marcacao`. O bloco de imports no topo do arquivo é comum: acrescente import necessário **em ordem alfabética**, sem remover nem reordenar linha de outro agente. Nenhum agente toca no corpo da função de outro. |
| `apps/api/tests/f5/conftest.py` | Só **A1** edita. É onde nasce a *fixture* com tenant, empresa, unidade (com geocerca e allowlist), REP-P ativo, colaborador, vínculo ativo e dispositivo vinculado, usada pelos três agentes. |

Conteúdo literal de `apps/api/app/marcacao/eventos.py` (A1 cria na T1; réplica
deliberada do padrão já usado em `app/pessoas/eventos.py` — **não importe
daquele módulo, que é propriedade da F2**; esta fase tem o seu próprio
barramento até a F13 entregar um de verdade):

```python
"""Barramento interno de eventos de dominio da fase de marcacao.

Padrao identico ao de `app.pessoas.eventos` (F2), replicado aqui de proposito:
cada fase tem o seu proprio barramento em memoria ate a F13 entregar fila real
de eventos (webhooks com HMAC, retentativa, DLQ). Ate la, este modulo e o
unico produtor e o unico consumidor: publica, guarda para o teste inspecionar,
e loga a correlacao.

Uso: A2 e A3 importam `montar_envelope` e `publicar` daqui e criam, cada um no
seu proprio arquivo, as funcoes especificas de publicacao dos seus eventos
(`marcacao.criada`, `marcacao.suspeita`, `marcacao.sincronizada_offline` para
A2; `comprovante.emitido` para A3). Ninguem acrescenta funcao neste arquivo
depois da T1.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID, uuid4

from app.core.log import obter_logger

logger = obter_logger("marcacao.eventos")

BARRAMENTO_INTERNO: list[dict[str, Any]] = []


def limpar_barramento() -> None:
    """Esvazia o barramento interno. Uso exclusivo de teste, entre casos."""
    BARRAMENTO_INTERNO.clear()


def montar_envelope(
    *,
    tipo: str,
    versao: int,
    tenant_id: UUID,
    dados: dict[str, Any],
    empresa_id: UUID | None = None,
    ocorrido_em: dt.datetime | None = None,
) -> dict[str, Any]:
    """Monta o envelope exato de `events.yaml`: id, tipo, versao, ocorridoEm,
    tenantId, dados -- os cinco campos `required`, mais os opcionais
    `publicadoEm` e `empresaId`."""
    agora = dt.datetime.now(tz=dt.UTC)
    envelope: dict[str, Any] = {
        "id": str(uuid4()),
        "tipo": tipo,
        "versao": versao,
        "ocorridoEm": (ocorrido_em or agora).isoformat(),
        "publicadoEm": agora.isoformat(),
        "tenantId": str(tenant_id),
        "dados": dados,
    }
    if empresa_id is not None:
        envelope["empresaId"] = str(empresa_id)
    return envelope


def publicar(envelope: dict[str, Any]) -> None:
    """Publica um envelope no barramento interno."""
    BARRAMENTO_INTERNO.append(envelope)
    logger.info(
        "evento de dominio publicado",
        extra={"tipo": envelope["tipo"], "id": envelope["id"], "tenantId": envelope["tenantId"]},
    )
```

Conteúdo literal (assinatura fixa, corpo permissivo) de
`apps/api/app/marcacao/confianca/motor.py` — **A3 cria na T1**. A **F14**
substitui o corpo sem mudar a assinatura; RFC se precisar mudar a forma:

```python
"""Motor de score de confianca do registro de ponto. CONTRATO ENTRE FASES.

A assinatura publica de `avaliar_confianca` esta fixada neste PCF (F5) e NAO
muda sem RFC. A implementacao real -- composicao ponderada de attestation,
RASP, modo desenvolvedor, mock location, coerencia geografica, velocidade
implicita e reputacao do dispositivo -- e da F14. Ate la, o corpo abaixo e
permissivo por design: NUNCA reprova, NUNCA pede revisao. Isso significa que
PONTO-SCORE-001..004, PONTO-GEO-003 e PONTO-DISP-003/004/005 ficam com o
codigo ligado (o chamador sabe levantar o erro) mas nunca sao alcancados na
pratica por esta fase -- comportamento esperado, nao lacuna.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SinaisRegistro:
    """Sinais brutos coletados no momento do registro, tal como informados
    pelo cliente (nenhum e verificado criptograficamente nesta fase)."""

    dentro_geocerca: bool | None = None
    distancia_geocerca_metros: float | None = None
    precisao_insuficiente: bool = False
    score_facial: float | None = None
    liveness_aprovado: bool | None = None
    attestation_veredito: str = "indisponivel"
    root_detectado: bool | None = None
    emulador_detectado: bool | None = None
    modo_desenvolvedor: bool | None = None
    mock_location: bool | None = None
    camera_virtual: bool | None = None
    velocidade_desde_ultima_kmh: float | None = None
    flags_integridade: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResultadoConfianca:
    """Resultado da avaliacao. `avisos` alimenta `MarcacaoCriada.avisos` e
    `marcacao.suspeita.sinais`."""

    score: int = 100
    classificacao: str = "alta"
    avisos: tuple[str, ...] = ()


def avaliar_confianca(
    sinais: SinaisRegistro,
    *,
    limiar_bloqueio: int,
    limiar_revisao: int,
) -> ResultadoConfianca:
    """STUB permissivo. A F14 substitui o corpo sem mudar a assinatura.

    `limiar_bloqueio`/`limiar_revisao` vem de `politicas_registro` e ja sao
    recebidos aqui para que a F14 nao precise mudar quem chama esta funcao --
    so o corpo, que hoje os ignora de proposito.
    """
    return ResultadoConfianca(score=100, classificacao="alta", avisos=())
```

**Explicitamente fora do seu ownership** (não edite, nem "só para arrumar"):
`packages/contracts/**`, `apps/api/app/schemas/contrato.py` (gerado),
`apps/api/app/core/erros.py`, `apps/api/app/core/catalogo_erros.py`,
`apps/api/app/core/seguranca.py`, `apps/api/app/core/middleware.py`,
`apps/api/app/db/sessao.py`, `apps/api/app/main.py`,
`apps/api/app/routers/__init__.py`, `apps/api/app/routers/{terminais,fiscal,tratamentos}.py`,
`apps/api/app/organizacao/**`, `apps/api/app/pessoas/**`, `apps/api/app/biometria/**`,
`apps/api/migrations/**`, `apps/api/tests/test_andaime.py`, `apps/worker/**`,
`apps/device-gw/**`, `.github/workflows/**`, `infra/**`, `Makefile`,
`tasks.ps1`, `apps/web/**`.

> **Nenhuma migration nova nesta fase.** `0001_inicial.py` já cria as 9
> tabelas da seção 8, os índices, os gatilhos e as policies de RLS,
> incluindo as partições mensais de `marcacoes` até 2027-12 e a partição
> `marcacoes_default`. Se você achar que precisa de uma migration, o
> contrato está errado: abra RFC.

> **Nenhuma dependência nova em `pyproject.toml`.** CRC-16 e SHA-256 (hash
> encadeado) são implementáveis com a biblioteca padrão (`hashlib`); AES-GCM
> e HMAC de fila offline também (`cryptography`, já declarada no bloco F1 —
> não duplique; **não acrescente bloco `# --- F5 ---`** a menos que descubra
> uma necessidade real, e nesse caso siga a convenção de bloco delimitado já
> usada por F1/F2).

## 6. Tarefas (T1..Tn)

### T1 — Módulos de fronteira e fixture da fase
**Agentes:** A1 (`__init__.py`, `eventos.py`, fixture) e A3 (`confianca/motor.py`) — **primeira tarefa, nada começa antes**
**Descrição:** A1 cria `apps/api/app/marcacao/__init__.py` (docstring) e
`apps/api/app/marcacao/eventos.py` com o conteúdo literal da §5. A3 cria
`apps/api/app/marcacao/confianca/motor.py` com o conteúdo literal da §5. A1
cria `apps/api/tests/f5/conftest.py`: sobe PostgreSQL 16 (mesmo padrão de
F1/F2: `PONTO_TEST_DATABASE_URL`, role de LOGIN não-superusuário, RLS
ativa), roda `alembic upgrade head`, semeia 1 tenant, 1 empresa, 1 unidade
(com geocerca de ponto+raio e uma faixa em `redes_permitidas`), 1 REP-P
`ativo`, 1 colaborador com vínculo `apura_ponto=true` ativo na data corrente,
e 1 dispositivo `tipo='celular'` com `dispositivo_vinculos.status='ativo'`
para esse colaborador.
**Pronto quando:** `pytest apps/api/tests/f5 -q` coleta, a fixture sobe e
derruba o banco sem erro, e `ruff`/`mypy` verdes sobre os três arquivos
novos.

### T2 — Alocação de NSR, CRC-16 e hash encadeado
**Agente:** A1
**Descrição:** Implementar em `app/marcacao/dominio/nsr.py` a alocação
transacional de ADR-003: `UPDATE nsr_sequencias SET proximo_nsr =
proximo_nsr + 1, ultimo_nsr_emitido = proximo_nsr, ultima_emissao_em = now()
WHERE tenant_id = :t AND rep_p_id = :r RETURNING proximo_nsr - 1 AS nsr,
ultimo_hash AS hash_anterior` (o `RETURNING` calcula sobre a linha **já**
atualizada; subtrair 1 recupera o valor alocado, e `ultimo_hash` ainda não
foi tocado por este `UPDATE`, portanto é o elo anterior correto). Falha de
alocação (linha inexistente para o REP-P, ou erro de banco) responde
`PONTO-MARC-008`. Implementar `crc16(dados: bytes) -> int` (documente o
polinômio/variante escolhida no docstring — a conformidade byte a byte com o
validador oficial da Portaria é conferida pela **F12**; aqui a exigência é
"calculado e congelado de forma estável", não "certificado"). Implementar
`calcular_hash(dados_canonicos: str, hash_anterior: str | None) -> str`
(SHA-256 hex) — **fixe e documente no módulo** exatamente quais campos
entram na canonicalização, em que ordem e com qual normalização (mesma
exigência que a F1 aplicou à auditoria): a fórmula tem que valer para sempre,
porque o verificador (`verificarSequenciaNsr`, T4) e o gravador precisam
concordar.
**Pronto quando:** teste prova que duas chamadas concorrentes (mesma
conexão de teste, duas transações) para o **mesmo** REP-P nunca alocam o
mesmo NSR e nunca pulam um valor (rodar com pelo menos 50 alocações
concorrentes antes do teste de carga completo da T9); teste prova que
`hash_anterior` da alocação N+1 é exatamente `hash_registro` da alocação N.

### T3 — Persistência atômica da marcação
**Agente:** A1
**Descrição:** `app/marcacao/dominio/registro.py::persistir_marcacao(sessao,
*, tenant_id, dados) -> Marcacao` — na mesma transação: aloca NSR (T2),
calcula CRC-16 e hash, monta `linha_afd` (formato canônico simples e
documentado — **não** é o leiaute legal final, que é da F12; a exigência
aqui é determinismo, não conformidade), insere em `marcacoes`, insere em
`nsr_emissoes` (mesma transação, mesmo NSR e hash), e faz o `UPDATE
nsr_sequencias SET ultimo_hash = :hash_registro` de fechamento. `rep_p_ativo(sessao,
tenant_id, empresa_id) -> RepP | None` (REP-P com `status='ativo'` da
empresa) — sem REP-P ativo, quem chama responde `PONTO-MARC-010`.
**Pronto quando:** teste insere 3 marcações sequenciais do mesmo REP-P e
prova a cadeia de hash (`hash_anterior` de cada uma bate com `hash_registro`
da anterior) direto no banco; teste prova que `rep_p_ativo` devolve `None`
para empresa sem REP-P.

### T4 — Prova de imutabilidade e verificação de NSR (critérios centrais)
**Agente:** A1
**Descrição:** Escrever e **executar** contra PostgreSQL 16 real, conectado
como a role de LOGIN não-superusuário (nunca como dono da tabela): `UPDATE`
e `DELETE` diretos em `marcacoes`, em `nsr_emissoes`, em
`marcacao_idempotencia` e em `comprovantes` — os quatro devem falhar com
`ERRCODE 42501`. Isto fecha, com execução real, os dois itens que
`docs/backlog.md` (seção "Aberto — herdado da Fase 0") registra como
providos só por leitura de código. Implementar `verificarSequenciaNsr`
(`app/marcacao/dominio/verificacao_nsr.py`): percorre `nsr_emissoes` na faixa
pedida, detecta lacuna (gap na sequência) e, se `verificarCadeiaHash=true`,
recalcula a cadeia de hash e compara.
**Pronto quando:** os 4 testes de `UPDATE`/`DELETE` bloqueado passam com
`ERRCODE 42501` capturado explicitamente (não um erro genérico); um teste
remove artificialmente uma linha de `nsr_emissoes` **via conexão de
superusuário de teste** (nunca a role da aplicação) e prova que
`verificarSequenciaNsr` acusa a lacuna com a faixa exata; a saída real dos 4
testes de imutabilidade está colada no relatório da fase.

### T5 — Idempotência de quatro chaves
**Agente:** A2
**Descrição:** `app/marcacao/pipeline/idempotencia.py`: antes de gravar,
consultar `marcacao_idempotencia` pelas chaves aplicáveis ao canal
(`external_id` para `api`; `dispositivo_id + log_externo_id` para
`terminal`; sempre `idempotency_key`; `offline_hmac` só no fluxo de T7).
Encontrada colisão de chave de domínio (`external_id`/`dispositivo+log`) sem
o mesmo `Idempotency-Key`: `PONTO-MARC-003`, devolvendo a marcação original.
Mesma `Idempotency-Key` com corpo idêntico: devolve a marcação original com
`duplicada=true` e cabeçalho `Idempotency-Replayed: true` — sucesso, não
erro. Mesma chave com corpo diferente: `PONTO-IDEM-002`. Mesma chave em voo
simultaneamente (dentro da mesma transação de outra requisição): `PONTO-IDEM-003`.
Cabeçalho ausente: `PONTO-IDEM-001` (o `openapi.yaml` já declara o parâmetro
obrigatório; garanta a mensagem correta).
**Pronto quando:** teste envia a mesma requisição duas vezes com a mesma
`Idempotency-Key` e prova UMA linha em `marcacoes` e resposta idêntica
byte a byte na segunda chamada, exceto o cabeçalho `Idempotency-Replayed`;
teste envia `external_id` repetido com `Idempotency-Key` **diferente** e
recebe `PONTO-MARC-003`.

### T6 — Pipeline de `criarMarcacao`: resolução, políticas e gravação
**Agente:** A2
**Descrição:** `app/marcacao/pipeline/ingestao.py::registrar_marcacao(...)`:
resolve colaborador por `colaboradorId`/`cpf`/`matricula`; recusa sem
vínculo ativo (`apura_ponto=true`) na data com `PONTO-MARC-009`; lê
`rep_p_ativo` (A1) e recusa sem REP-P com `PONTO-MARC-010`; carimba
`datahora_marcacao = now()` do servidor (nunca do corpo, exceto no fluxo
offline — T7); busca a linha mais específica de `politicas_registro`
aplicando o fallback de `COALESCE` descrito na §2, com os `DEFAULT` da
coluna quando não houver linha; aplica geocerca
(`app.organizacao.geocerca.dentro_da_geocerca`) quando `exige_geocerca` e
`latitude`/`longitude` informados — `politica_fora_geocerca='bloquear'` vira
`PONTO-GEO-001`, `'sinalizar'` grava e marca aviso, precisão insuficiente
vira `PONTO-GEO-002`; aplica allowlist (`app.organizacao.redes.ip_autorizado`)
quando `exige_rede_permitida` — fora da lista é `PONTO-REDE-001`; para
`canal='mobile'`, confere `dispositivo_vinculos.status='ativo'` do
colaborador e do `dispositivoId` informado — ausente é `PONTO-DISP-001`,
`bloqueado`/`revogado` é `PONTO-DISP-002` (não aplicar esta checagem para os
demais canais); quando `exige_reautenticacao` e `canal='web'`, confere
`sessoes.reautenticado_em` recente — ausente/expirado é `PONTO-AUTH-011`.
Monta `SinaisRegistro` (confiança/motor.py) a partir dos campos do corpo,
chama `avaliar_confianca`, compara o `score` com `limiar_bloqueio`/`limiar_revisao`
da política (`score < limiar_bloqueio` → `PONTO-SCORE-001`; entre os dois →
grava e marca `revisao_status='pendente'`, publica `marcacao.suspeita`;
acima do limiar de revisão → `revisao_status='nao_requer'`). Chama
`persistir_marcacao` (A1), grava `marcacoes_meta`, chama `emitir_comprovante`
(A3), publica `marcacao.criada` e `comprovante.emitido`.
**Pronto quando:** teste de mesa cobre os 7 casos felizes do produto (cada
canal aceito × REP-P ativo) e ao menos um caso de cada código de erro real
listado acima, com resultado esperado explícito por caso; com o stub
permissivo de A3, nenhum teste desta tarefa produz `PONTO-SCORE-*` nem
`marcacao.suspeita` — documente isso no próprio teste como asserção
positiva ("com o motor stub, o score nunca bloqueia").

### T7 — Sincronização offline
**Agente:** A2
**Descrição:** `app/marcacao/pipeline/offline.py::sincronizar_lote(...)`:
para cada item de `SincronizacaoOfflineRequisicao.itens`, valida HMAC contra
a chave do `dispositivoId` (inválido: `PONTO-MARC-006`, item rejeitado, não
aborta o lote); valida `contadorMonotonico` estritamente maior que o último
consumido daquele dispositivo, gravando em `fila_offline` (reuso: constraint
`uq_fila_offline_contador`) — repetido: `PONTO-MARC-007`; calcula o atraso
entre `datahoraDispositivo`/`tempoMonotonicoMs` e o momento do recebimento —
fora do TTL (`politicas_registro.ttl_offline_horas`): `PONTO-MARC-005`, item
vira `expirado` e **não** gera marcação; dentro do prazo: chama
`registrar_marcacao` (T6) com `datahora_marcacao` = o instante real da
captura (preservado, nunca o momento da sincronização) e
`coletada_offline=true`, publica `marcacao.sincronizada_offline`. Resposta
`207` com contagem por desfecho e o array `resultados` item a item, na mesma
chamada (processamento síncrono — não crie tarefa de worker para isto).
**Pronto quando:** lote de 20 itens com 5 propositalmente quebrados
(2 HMAC inválido, 2 contador repetido, 1 fora do TTL) processa os 15
restantes e reporta os 5 com o código correto, sem abortar o lote; reenviar
o mesmo lote inteiro uma segunda vez não duplica nenhuma marcação.

### T8 — Comprovante de registro
**Agente:** A3
**Descrição:** `app/marcacao/comprovantes/emissor.py::emitir_comprovante(sessao,
marcacao) -> Comprovante`: gera `numero` único por tenant e estável — use o
formato `AAAAMMDD` da data da marcação + NSR com 8 dígitos (ex.:
`2026072500001842`, igual ao exemplo de `events.yaml`); se duas empresas do
mesmo tenant tiverem REP-P distintos e puderem colidir no mesmo dia/NSR,
prefixe com o `identificador` do REP-P — **documente a escolha exata no
módulo**, porque `uq_comprovantes_numero` é por tenant, não por empresa.
`conteudo_texto` com os campos legalmente relevantes (NSR, CPF, data/hora,
hash) — o leiaute textual oficial é conferido pela F12; aqui o requisito é
"completo o bastante para a dispensa de impressão", não conformidade
certificada. `hash_sha256` do `conteudo_texto`. `assinatura_ref` fica `NULL`
até a F12. `app/marcacao/comprovantes/eventos_comprovante.py::publicar_comprovante_emitido`
(usa `app.marcacao.eventos.montar_envelope`/`publicar`).
**Pronto quando:** teste prova `numero` único mesmo com duas marcações no
mesmo dia (NSRs diferentes); teste valida o *payload* de `comprovante.emitido`
campo a campo contra `events.yaml`.

### T9 — Prova de concorrência de NSR sob carga (critério central)
**Agente:** A1 (com A2 fornecendo o caminho de ingestão completo da T6)
**Descrição:** Teste de carga: **10.000** chamadas concorrentes de
`registrar_marcacao` para o **mesmo** REP-P (canais variados, sem
colisão de idempotência entre elas — cada uma com `Idempotency-Key` própria),
executado contra PostgreSQL 16 real. Isto fecha, com execução real, o
segundo item que `docs/backlog.md` registra como pendente desde a Fase 0.
**Pronto quando:** os NSRs resultantes formam exatamente `1..10000`, sem
lacuna e sem repetição, verificado por `verificarSequenciaNsr` (T4) sobre a
faixa inteira com `verificarCadeiaHash=true`; o tempo total é registrado no
relatório da fase; a saída real do teste está colada.

### T10 — Consulta de marcações e meta antifraude
**Agente:** A3
**Descrição:** `app/marcacao/consulta/marcacoes.py`: `listarMarcacoes` (todos
os filtros do contrato — colaborador, vínculo, empresa, unidade, REP-P, CPF,
canal, período, faixa de NSR, `coletadaOffline`; `incluirMeta=true` embute
`MarcacaoMeta` de cada linha — a permissão `marcacoes.ler_sensivel` já é
verificada por `exigir_permissao` na própria rota, mas confirme com teste
que `incluirMeta` sem essa permissão responde `PONTO-PERM-001`, nunca
retorna o campo silenciosamente vazio); `obterMarcacao`; `obterMetaMarcacao`.
Use paginação por cursor no mesmo padrão de `app.pessoas.paginacao` (crie a
sua própria cópia em `app/marcacao/consulta/paginacao.py` — não importe o
módulo de outra fase).
**Pronto quando:** teste prova que `ordenar=nsr:desc` e `ordenar=datahoraMarcacao:asc`
produzem páginas estáveis e que o cursor de uma ordenação não é aceito
noutra (`PONTO-VAL-006`, se o parâmetro de teste exigir — confirme o código
exato usado por outras fases para esse caso e reutilize a mesma convenção);
teste prova o bloqueio de `incluirMeta` sem `marcacoes.ler_sensivel`.

### T11 — Consulta de comprovantes e as últimas 48 horas
**Agente:** A3
**Descrição:** `app/marcacao/comprovantes/consulta.py`: `listarComprovantes`,
`obterComprovante` (aceitar `Accept: text/plain` devolvendo
`conteudo_texto` cru, e `application/json` devolvendo o schema completo —
conforme a descrição da operação no contrato), `listarComprovantesRecentes`
(padrão 48 h, parâmetro `horas` até 8760; o próprio colaborador sempre
acessa os seus; gestor/RH dependem de `exigir_alcance`).
**Pronto quando:** teste prova que um comprovante emitido há 50 horas não
aparece na janela padrão de 48 h mas aparece com `horas=72`; teste prova que
`Accept: text/plain` devolve o corpo textual e `application/json` devolve o
schema `Comprovante`.

### T12 — Fechamento
**Agente:** A1, A2 e A3
**Descrição:** Rodar todos os comandos da §8 e colar a saída real no
relatório da fase, item a item contra a §7.
**Pronto quando:** todos verdes, com saída colada, e
`git status --short packages/contracts` vazio.

## 7. Critérios de aceite

O relatório final responde item a item, com saída real colada.

1. **As 9 operações** das tags `marcacoes` e `comprovantes` deixaram de
   responder `501`; `python tools/conferir_rotas.py` continua dizendo
   `Inventario identico ao contrato`.
2. **Imutabilidade provada por execução real**: `UPDATE` e `DELETE` diretos
   em `marcacoes`, `nsr_emissoes`, `marcacao_idempotencia` e `comprovantes`,
   conectado como a role da aplicação (não superusuário), falham com
   `ERRCODE 42501` — evidência colada, não referência a linha de código.
3. **10.000 marcações concorrentes do mesmo REP-P produzem NSR de 1 a
   10.000, sem lacuna e sem repetição**, provado por execução real contra
   PostgreSQL 16 e confirmado por `verificarSequenciaNsr` com verificação de
   cadeia de hash.
4. **Cadeia de hash encadeada é consistente**: `hash_anterior` de cada
   emissão é exatamente `hash_registro` da emissão anterior do mesmo REP-P,
   e a fórmula de canonicalização está documentada no código.
5. **Idempotência nas quatro chaves**: reenvio pela mesma `Idempotency-Key`
   devolve a marcação original sem duplicar; colisão de `external_id` ou de
   `dispositivo_id + log_externo_id` sem a mesma chave responde
   `PONTO-MARC-003`; reenvio do mesmo lote offline inteiro não duplica
   nenhuma marcação.
6. **Canal-agnóstico de verdade**: um teste chama `criarMarcacao` com os
   cinco valores de `canal` aceitos pelo `MarcacaoCriar` e todos produzem
   marcação pelo mesmo caminho de código.
7. **Geocerca e allowlist CIDR aplicadas de verdade** (não stub): ponto fora
   da geocerca com política de bloqueio responde `PONTO-GEO-001`; IP fora da
   allowlist com `exige_rede_permitida` responde `PONTO-REDE-001`; ambas
   usam as funções puras entregues pela F2, sem reimplementação.
8. **Estrutura do score de confiança presente e o motor é comprovadamente um
   stub permissivo**: `marcacoes_meta` grava todos os campos do contrato;
   `avaliar_confianca` sempre devolve `score=100`/`classificacao="alta"`
   nesta fase; nenhum teste desta fase produz `PONTO-SCORE-001..004`,
   `PONTO-GEO-003` ou `PONTO-DISP-003/004/005`.
9. **Comprovante emitido na mesma transação da marcação**, disponível pelas
   últimas 48 h por padrão (e por mais tempo quando pedido), com hash
   verificável.
10. **Eventos `marcacao.criada`, `marcacao.sincronizada_offline` e
    `comprovante.emitido`** publicados com o envelope e o *payload* exatos
    de `events.yaml`, validados campo a campo por teste. `marcacao.suspeita`
    está conectado mas não dispara nesta fase (documentado, não testado como
    "nunca vai dispersar" — apenas "não dispara com o motor stub").
11. **Toda rota declara `Depends(exigir_permissao(...))`** com exatamente o
    `x-permissao` do contrato.
12. **Reautenticação para canal web**: sem `sessoes.reautenticado_em`
    recente e `politicas_registro.exige_reautenticacao=true`, responde
    `PONTO-AUTH-011`.
13. **Nenhum segredo versionado.**
14. **Contrato intacto**: `git status --short packages/contracts` vazio.
15. Todos os comandos da §8 verdes, com saída real colada no relatório.

## 8. Comandos de verificação

Rode a partir da **raiz do repositório**, salvo onde indicado. Windows usa
`.\tasks.ps1`; Linux/macOS usa `make`.

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

Lint, formatação e tipos (versões fixadas no CI: ruff 0.7.4, mypy 1.13.0):

```bash
ruff check apps packages tests
ruff format --check apps packages tests
cd apps/api && mypy
```

```powershell
.\tasks.ps1 lint
.\tasks.ps1 typecheck
```

**Saída esperada:** `All checks passed!`, `NN files already formatted`,
`Success: no issues found in NNN source files`.

Testes da fase, com cobertura:

```bash
cd apps/api && pytest tests/f5 -q --cov=app --cov-report=term-missing
```

**Saída esperada:** todos passam; nenhum `skip` em teste que exige banco —
teste pulado não conta como verde.

Prova de imutabilidade e de concorrência de NSR, isoladas para evidência no
relatório (o critério 2 e o critério 3 da §7 exigem a saída **desses**
comandos especificamente):

```bash
cd apps/api && pytest tests/f5/dominio -q -k "imutavel or update or delete" -s
```

```bash
cd apps/api && pytest tests/f5/dominio -q -k "concorrencia or dez_mil or carga" -s
```

Regressão do andaime da Fase 0:

```bash
cd apps/api && pytest tests/test_andaime.py -q
```

Inventário de rotas idêntico ao contrato:

```bash
cd apps/api && python tools/conferir_rotas.py
```

**Saída esperada:**
`Inventario identico ao contrato (metodo, caminho e operationId).`

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

1. **Não edite `packages/contracts/`.** Divergência vira RFC em
   `docs/rfc/`, no formato de `docs/rfc/README.md`.
2. **Não crie código de erro novo.** Os 112 códigos de `errors.yaml` são o
   conjunto fechado.
3. **Não crie migration nova.** `0001_inicial.py` já cria as 9 tabelas da
   seção 8, incluindo as partições mensais e `marcacoes_default`.
4. **Não desabilite RLS**, nem em *fixture* de teste, nem conectando como
   superusuário "para simplificar" os testes de imutabilidade — um teste de
   imutabilidade que roda como superusuário ou dono da tabela **não prova
   nada** (o `REVOKE` não se aplica a eles).
5. **Não implemente a composição real do score de confiança nem julgue
   sinais antifraude** (attestation, RASP, modo desenvolvedor, mock
   location, câmera virtual). O motor é um stub permissivo com assinatura
   fixa; a régua é da **F14**. Não "adiante" essa lógica achando que ajuda —
   muda o contrato entre fases sem RFC.
6. **Não implemente bloqueio de VPN/proxy/ASN de datacenter**
   (`PONTO-REDE-002`) — é da F8 e da F14.
7. **Não implemente nada de Control iD/terminal físico, nem crie um segundo
   caminho de ingestão para o canal `terminal`.** A F6 chama o seu
   `POST /v1/marcacoes` como qualquer outro cliente; se o formato de
   `MarcacaoCriar` não bastar para o catch-up dela, isso é achado de
   contrato — RFC, não campo extra seu.
8. **Não implemente o cadastro de REP-P** (`POST /v1/fiscal/rep-ps`) nem
   nenhuma operação da tag `fiscal` — **F12**. Você só lê `rep_ps`.
9. **Não implemente `tratamentos`** nem sugira, em mensagem de erro, código
   ou teste, que marcação é "editável". Não existe: é **tratamento**, de
   outra fase.
10. **Não crie tarefa de worker para a sincronização offline.**
    `sincronizarMarcacoesOffline` é processada de forma síncrona, com
    resposta `207` na mesma chamada.
11. **Não invente endpoint de CRUD para `politicas_registro`.** Não existe
    no contrato; leia com os `DEFAULT` de coluna quando faltar linha.
12. **Não altere as assinaturas de `app/core/seguranca.py` nem de
    `app/db/sessao.py`.** São reais, entregues pela F1; você só as consome.
13. **Não reimplemente `dentro_da_geocerca` nem `ip_autorizado`.** São
    funções puras reais da F2; importe-as.
14. **Não escreva regra de negócio de outras fases** — apuração, banco de
    horas, workflow de aprovação, relatórios, AFD/AEJ. Achou algo fora do
    escopo? `docs/backlog.md`.
15. **Não use os termos proibidos** da seção 6 do glossário: é *marcação*
    (nunca "batida"), *tratamento* (nunca "editar marcação"), *coletor*
    (nunca "relógio de ponto"), *tenant* (nunca "empresa" para dizer cliente
    do SaaS).
16. **Não declare a fase pronta sem rodar os comandos da §8 e colar a saída
    real**, em especial os dois testes adversariais herdados da Fase 0
    (imutabilidade e concorrência de NSR) — "deve funcionar" não é
    evidência, e é exatamente o que ficou pendente até agora.
