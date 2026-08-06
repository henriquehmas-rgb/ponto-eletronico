# F14 — Segurança, antifraude e LGPD

## 1. Objetivo

No fim desta fase, cada marcação passa a carregar um veredito de confiança real (não só os campos
vazios que a Fase 0 já reservou): sinais de geolocalização, prova de vida/similaridade facial,
reputação de dispositivo e (quando F7 existir) attestation de plataforma se compõem num score de 0
a 100 por regra explicável e auditável (ADR-008), com política configurável por empresa e fila de
revisão do gestor. O sistema ganha uma camada de hardening que hoje só existe para as rotas que F13
construiu por conta própria (rate limiting, idempotência) — retrofitada para as ~130 rotas de F1–F13
— mais varredura estática (Semgrep/CodeQL) integrada ao CI. O módulo `lgpd` deixa de responder 501:
consentimento versionado, direitos do titular (acesso/correção/portabilidade/eliminação), expurgo
automático por política de retenção e os dois artefatos documentais que a LGPD exige de um operador
de dado (RIPD, contrato de operador). Por fim, um agente dedicado tenta fraudar o próprio sistema
pelos vetores testáveis sem um app móvel real e corrige tudo que passar.

## 2. Contexto mínimo

**O que é este sistema, em uma frase.** SEEG Ponto é um SaaS multi-tenant de ponto eletrônico
brasileiro, compatível com a Portaria MTP 671/2021 (REP-P), com motor facial próprio; até aqui
(F0–F6, F8–F13, F9a) ele registra marcações imutáveis com NSR sem lacuna, calcula jornada e banco de
horas, roda workflows de aprovação/fechamento, gera relatórios e AFD/AEJ assinados, e agora também
fala com o mundo de fora (API pública, webhooks, SSO). F14 é a fase que pergunta "e se alguém tentar
enganar isso" e "o que a LGPD exige de nós especificamente" — não constrói funcionalidade de negócio
nova, endurece e audita o que já existe.

**Onde F14 se encaixa e a dependência que não está satisfeita.** Onda 5, terceira e penúltima fase.
O plano-base (`FASES-E-AGENTES.md` §F14) declara dependência de F5, F7, F8 e F13. F5, F8 e F13 estão
prontas. **F7 (app mobile Flutter) segue adiada desde o início do projeto** — SDK Flutter
indisponível neste ambiente de desenvolvimento, decisão já registrada e nunca revertida em nenhuma
onda anterior. Isso NÃO bloqueia F14 por completo: leia **ADR-014** (novo, decidido pelo orquestrador
ao escrever este PCF) antes de tocar em qualquer linha desta fase — ele mapeia exatamente qual parte
de cada agente depende de F7 de verdade (pouca) e qual não depende de nada (a maior parte). Resumo
que todo agente precisa internalizar: **F7 e F8 são os PRODUTORES de sinal, F14 é quem calcula e
decide, no servidor, com o que já existe.** F8 já está construída — sinal real de geolocalização,
prova de vida e similaridade facial via `analise-facial-edge` já existe hoje. Só os sinais nativos de
plataforma móvel (attestation, RASP, mock location via API do SO, certificate pinning) exigem F7 e
ficam formalmente pendentes, documentados, não simulados.

**ADR-008 (score de confiança) já decide o desenho de A1 — implemente-o, não o redesenhe.** Composição
no servidor, três faixas configuráveis por empresa/unidade, marcação sinalizada é marcação válida
(nunca alterada/excluída — ADR-002), explicabilidade obrigatória em `marcacoes_meta`, mensagem de
erro que não vaza a regra (`expoe_regra: false`), sinal decisivo (mock location comprovado, HMAC de
fila offline quebrado, assinatura de payload inválida) sempre recusa direto, independente do score.

**ADR-006 (criptografia de template biométrico) já está implementado, não é trabalho desta fase.**
Confirmado por leitura de código: `apps/api/app/biometria/cifra.py` já faz envelope encryption
AES-256-GCM com DEK derivada por HKDF-SHA256 da KEK (`PONTO_BIOMETRIA_CHAVE_MESTRA`), AAD amarrado a
`tenant_id`/`colaborador_id`, exatamente como o ADR especifica. A3 (LGPD) audita isso se quiser, mas
não reconstrói — o trabalho real de A3 é a CAMADA DE DIREITOS (consentimento, acesso, correção,
portabilidade, eliminação, retenção/expurgo automático), que é código de negócio ainda inexistente,
não a cifra em si.

**O módulo `lgpd` é stub puro de Fase 0.** Confirmado por leitura de `apps/api/app/routers/lgpd.py`:
toda operação (`listarConsentimentos`, `criarConsentimento`, `revogarConsentimento`,
`listarSolicitacoesTitular`, `criarSolicitacaoTitular`, `listarAcessosDadosSensiveis`) responde 501
`PONTO-INT-005`, com a própria docstring do arquivo dizendo "regra de negócio entra na fase F14".
Nenhuma tabela nova: `consentimentos`, `solicitacoes_titular`, `acessos_dados_sensiveis`,
`politicas_retencao`, `tipos_tratamento` já existem em `schema.sql` desde a Fase 0, prontas para
receber lógica real.

**Hardening tem retrofit concreto pendente, já documentado por F13 (`docs/backlog.md`, buscar
`2026-08-03`).** Três mecanismos genéricos foram construídos por F13 só para as próprias rotas novas,
com o retrofit para F1–F12 explicitamente adiado para esta fase:
- `apps/api/app/comum/limitador_taxa.py` — rate limiting genérico, hoje só em rotas de F13.
- `apps/api/app/comum/idempotencia_generica.py` — idempotência genérica, mesma situação.
- `apps/api/app/comum/autenticacao_cliente.py::exigir_escopo` — permite um cliente OAuth/API-key
  acessar rotas novas de F13, mas as ~130 rotas de F1–F12 continuam só aceitando sessão humana (JWT)
  mesmo quando o contrato já declara `oauth2`/`apiKeyAuth` como alternativa válida em muitas delas —
  fechar isso exigiria tocar `apps/api/app/core/seguranca.py`, hoje travado à F1/A3; **A2 decide se
  destrava com cuidado (arquivo crítico, mudança precisa preservar 100% do comportamento existente
  de sessão humana) ou registra como não fechado nesta fase, com justificativa.**
- CSRF de login ausente nas três rotas de sessão pré-existentes de F8 (`apps/web/src/app/api/auth/
  {login,refresh,logout}/route.ts`) — o padrão de mitigação (`requisicaoDeMesmaOrigem`/
  `corpoDeclaradoComoJson`, `apps/web/src/lib/sessao/servidor/csrf.ts`) já existe e é diretamente
  reaproveitável, construído para as rotas de SSO da F13.
- Mecanismo de IP confiável ponta a ponta (`X-Forwarded-For` só aceito quando a origem imediata é o
  proxy reverso de produção) — hoje toda rota que passa pelo proxy Next.js captura o IP do servidor,
  não do usuário final.

### 2.1 Nenhuma RFC nova identificada até aqui

O contrato (`packages/contracts/openapi.yaml`) já declara toda a superfície que F14 precisa: tag
`lgpd` completa desde a Fase 0, campos de score/attestation em `marcacoes_meta` e no corpo de
marcação. Se durante o build você encontrar uma lacuna genuína de contrato, **abra RFC como
`Proposta`, nunca `Decidida` por conta própria** (`docs/rfc/README.md` §4) — mesmo padrão que toda
fase anterior já seguiu.

## 3. Ownership de arquivo (mutuamente exclusivo)

| Agente | Território exclusivo |
|---|---|
| A1 | `apps/api/app/antifraude/**` (novo módulo — motor de score, políticas, fila de revisão), `apps/api/app/marcacao/pipeline/**` (só o ponto de integração que popula `marcacoes_meta.score_confianca`/sinais, nunca a lógica de NSR/hash de F5), `apps/api/tests/f14/antifraude/**`, painel de marcações suspeitas em `apps/web/src/app/painel/**` (subpasta nova) |
| A2 | `apps/api/app/comum/limitador_taxa.py`/`idempotencia_generica.py`/`autenticacao_cliente.py` (retrofit, aplicação a routers existentes — edita `apps/api/app/routers/*.py` só para acrescentar `Depends`, nunca a lógica de negócio de dentro), `.github/workflows/ci.yml` (jobs Semgrep/CodeQL novos), `apps/device-gw/**`/`apps/facial-svc/**` (mTLS, se `facial-svc` existir como serviço separado — confirmar antes), revisão de RLS (`packages/contracts/schema.sql`, só policies, nunca schema de tabela), `apps/web/src/lib/sessao/servidor/csrf.ts` (aplicar às 3 rotas de F8, não recriar), `apps/api/tests/f14/hardening/**` |
| A3 | `apps/api/app/routers/lgpd.py`, `apps/api/app/lgpd/**` (novo módulo de serviço), `apps/api/migrations/versions/**` (só se política de retenção precisar de rotina de expurgo agendada — reaproveitar `apps/worker/worker/scheduler.py`, adicionar rotina nova, nunca editar as existentes), documentos `docs/lgpd/ripd.md` e `docs/lgpd/contrato-operador.md` (novos), `apps/api/tests/f14/lgpd/**` |
| A4 | Só arquivos de teste: `apps/api/tests/f14/adversarial/**`, `apps/worker/tests/f14/**` se aplicável. Corrige bug encontrado no módulo do agente dono (não edita código de A1/A2/A3 diretamente — abre achado, o dono corrige, ou o orquestrador decide no fechamento se A4 já tiver terminado). Roda por último, depois de A1–A3 — não é paralelo real, é a segunda onda. |

**Fora do alcance de todos:** `apps/api/app/core/seguranca.py` continua travado a F1/A3 por padrão
salvo decisão explícita de A2 documentada no PCF (§2, já sinalizada acima); `apps/api/app/biometria/
cifra.py` não se reescreve (ADR-006 já implementado); nenhuma tabela de `schema.sql` muda de forma
(só dado, nunca DDL, exceto a rotina de expurgo do scheduler que A3 pode acrescentar).

## 4. Ordem de execução

**Onda 1 (paralela): A1, A2, A3** — territórios mutuamente exclusivos, sem dependência entre si.
**Onda 2 (depois que 1 termina): A4** — precisa que o motor de score, o hardening e a LGPD já
existam para ter o que atacar.

## 5. Escopo por agente

### A1 — Score de confiança

- Módulo `apps/api/app/antifraude/motor.py` (ou equivalente): composição ponderada dos sinais
  disponíveis hoje (geolocalização/CIDR, prova de vida + similaridade facial via `analise-facial-edge`,
  coerência geográfica entre marcações, velocidade impossível, reputação de dispositivo por histórico
  de `dispositivos`) e dos sinais reservados para quando F7 existir (attestation, RASP, modo
  desenvolvedor, mock location) — estes últimos entram como `nao_aplicavel`/`null` sempre que a origem
  do sinal não existir (**nunca inventar valor**, ver ADR-014).
- Política de três faixas configurável por tenant/unidade (`politicas_registro.exige_attestation`/
  `politica_mock_location` já existem — acrescente os campos de limiar que faltarem via migration
  nova, sem mexer nas colunas existentes).
- Fila de revisão do gestor: reaproveita o padrão de aprovação já existente (F10,
  `apps/api/app/workflow/**`) na medida do possível — não reinventa um motor de fila novo se o de F10
  já serve.
- Painel de marcações suspeitas em `apps/web` (novo, sob `painel/`), consumindo a fila.
- **Aceite de A1:** teste de composição cobre as três faixas com sinal sintético documentado (web/
  terminal real onde disponível, `nao_aplicavel` onde depende de F7); mensagem de erro de recusa não
  vaza limiar/peso/raio de geocerca (`expoe_regra: false`); explicabilidade gravada em
  `marcacoes_meta` sobrevive a consulta por API.

### A2 — Hardening

- Retrofit de `limitador_taxa.py`/`idempotencia_generica.py` nas rotas de escrita de F1–F13 (via
  `Depends`, sem tocar lógica de negócio).
- Decisão documentada (não necessariamente implementação completa) sobre destravar
  `core/seguranca.py` para aceitar OAuth/API-key nas rotas antigas — se optar por não fechar, registra
  em `docs/backlog.md` com o mesmo rigor que F13 já usou.
- Proteção contra enumeração (IDs sequenciais expostos, mensagens de erro que confirmam existência de
  recurso a um não-autorizado).
- Revisão de RLS: confirmar policy em toda tabela `tenant_id` (script de auditoria, não reescrita
  manual tabela por tabela — já existe precedente em `tests/f1/tenancy/test_catalogo_rls.py`).
- mTLS `device-gw` ↔ `facial-svc` (confirmar primeiro se `facial-svc` é processo separado neste
  monorepo ou biblioteca embutida — ajustar escopo conforme a resposta).
- `Semgrep` + `CodeQL` como job novo de CI (mesmo padrão do job `contrato-schemathesis` que F13 já
  deixou pronto como referência de "job novo que sobe/analisa e publica achado").
- Aplicar `requisicaoDeMesmaOrigem`/`corpoDeclaradoComoJson` (já existe, `apps/web/src/lib/sessao/
  servidor/csrf.ts`) às três rotas de sessão de F8.
- Mecanismo de IP confiável (allowlist de proxy reverso + `X-Forwarded-For`) para toda rota que hoje
  captura IP via `apps/web` como intermediário.
- **Aceite de A2:** Semgrep/CodeQL sem achado de severidade alta (ou achado triado e justificado);
  rate limiting/idempotência comprovados por teste real (não só existência do `Depends`) numa amostra
  representativa de rotas de F1–F12; RLS audit não encontra tabela `tenant_id` sem policy.

### A3 — LGPD

- Implementa as 6 operações de `lgpd.py` para valer: `criarConsentimento`/`revogarConsentimento`
  (versionado — texto exato aceito, vínculo com `tipos_tratamento`), `listarConsentimentos`,
  `criarSolicitacaoTitular`/`listarSolicitacoesTitular` (acesso, correção, portabilidade, eliminação —
  eliminação de marcação **nunca** apaga o registro, ADR-002/guarda legal de 5 anos; produz relatório
  de dados do titular, não apagamento onde a lei proíbe), `listarAcessosDadosSensiveis` (lê
  `acessos_dados_sensiveis`, já populada por quem acessa biometria hoje — confirmar se F2 já grava
  nela ou se falta instrumentar os pontos de leitura).
- Rotina de expurgo automático: nova tarefa no scheduler do worker, lê `politicas_retencao`, aplica
  `anonimizar`/`eliminar`/`arquivar` por entidade vencida, atualiza `ultima_execucao_em`/
  `proxima_execucao_em`/`registros_ultima_execucao`. Marcação em si nunca é alvo de eliminação
  automática dentro do prazo legal — a política para `entidade='marcacao'` só existe para o que vence
  DEPOIS do prazo de guarda.
- `docs/lgpd/ripd.md` (Relatório de Impacto à Proteção de Dados) e `docs/lgpd/contrato-operador.md`
  (minuta de contrato de operador para cliente SaaS) — documentos, não código; escritos a partir do
  que o sistema de fato faz (não aspiracional), citando os ADRs relevantes (006, 008) como evidência
  técnica das salvaguardas.
- **Aceite de A3:** exportação de dados do titular funciona ponta a ponta (criar solicitação → dado
  correto devolvido); expurgo automático comprovado em teste (política com prazo curto sintético,
  registro vencido, rotina roda, registro tratado conforme `acao`); revogação de consentimento de
  biometria dispara expurgo do template (chama o que A A2/F2 já expõe, não duplica a cifra).

### A4 — Verificação adversarial

Tenta fraudar o próprio sistema pelos vetores testáveis sem F7 (ver ADR-014 para a lista completa do
que fica de fora e por quê):

- Réplica de payload de marcação offline já processado (idempotência de F5 segura?).
- Manipulação de relógio do cliente (confiança temporal, ADR-007 — parte que não depende do app).
- Cross-tenant: tentar ler/gravar marcação, template, relatório de outro tenant por manipulação de
  parâmetro, header, ou reuso de sessão.
- Foto impressa/vídeo contra o motor facial via canal web/terminal (prova de vida de
  `analise-facial-edge`, já em produção via F6/F8).
- Bypass de RLS por consulta direta/função `SECURITY DEFINER` mal escopada.
- Bypass do score de confiança: manipular payload para forçar `score_confianca` alto sem o backend
  recalcular (ADR-008 regra 1: campo não existe na entrada, cliente não pode mandar).

**Aceite de A4:** todo vetor acima testado tem teste automatizado que comprova a defesa (não só
prosa); todo achado real corrigido antes do fechamento da fase, não só registrado.

## 6. Migrations

Só se A1 precisar de campo de limiar novo em `politicas_registro` (aditivo, sem quebrar coluna
existente) e A3 precisar de campo de controle na rotina de expurgo do scheduler (sem tabela nova —
`politicas_retencao` já tem os campos de controle de execução). Nenhum agente cria tabela nova sem
antes confirmar que não existe uma equivalente em `schema.sql`.

## 7. Ambiente

Mesmo padrão de todas as fases anteriores: banco/Redis/MinIO via túnel SSH da VPS
(`PONTO_TEST_DATABASE_URL`/`DATABASE_URL`, `PONTO_TEST_REDIS_URL`, `MINIO_*`), nunca Docker local
(quebrado nesta máquina, ver memória de sessão). Semgrep/CodeQL rodam localmente para o agente A2
confirmar achado antes de subir o job de CI — não depender só do CI para descobrir problema.

## 8. Regressão de fechamento

```
pytest tests/f1 tests/f2 tests/f4 tests/f5 tests/f6 tests/f10 tests/f11 tests/f12 tests/f13 tests/f14 -q
```
(`apps/api`), mais `apps/worker`/`apps/device-gw` próprios, mais `pnpm test`/`build`/`lint`/`typecheck`
em `apps/web`, mais `tools/conferir_rotas.py`, `ruff check`/`ruff format --check`, `mypy app` (agora
como gate real — ver §2, item de A2 sobre fechar a lacuna de F1/F11 se o tempo permitir), Schemathesis
contra o contrato. Todos os padrões de ambiente (env vars corretas, limpeza de `tenants` acumulado
antes de rodar) já documentados em `docs/backlog.md` (2026-08-03) valem aqui sem repetição.
