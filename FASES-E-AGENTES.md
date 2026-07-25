# Fases e Mapa de Agentes — Ponto Eletrônico

> Complemento operacional de [PROJETO.md](PROJETO.md).
> Define **como** o sistema é construído por agentes trabalhando em paralelo sem quebrar contexto.

---

## 1. O mecanismo anti-quebra-de-contexto

O problema de rodar muitos agentes num sistema grande é que cada um precisa "entender o projeto inteiro" — e não cabe. A solução é inverter: **nenhum agente precisa entender o projeto inteiro.**

Cada agente lê exatamente duas coisas:

1. **`packages/contracts/`** — congelado na Fase 0, imutável depois. É o vocabulário comum: OpenAPI, modelo de dados, catálogo de erros, catálogo de eventos, design tokens, glossário do domínio.
2. **O Pacote de Contexto da sua Fase (PCF)** — um único arquivo `docs/fases/FXX-nome.md` que é auto-suficiente.

Nada mais. Sem "leia o código do módulo vizinho", sem "pergunte ao agente da fase anterior". Se um agente precisa de algo que não está nesses dois lugares, isso é um **defeito do PCF**, não do agente — e se corrige atualizando o PCF.

### 1.1 Template obrigatório do PCF

```markdown
# FXX — <Nome da Fase>

## 1. Objetivo
Uma frase. O que existe no fim que não existia no começo.

## 2. Contexto mínimo
3 a 8 parágrafos. Tudo que o agente precisa saber do domínio para esta fase.
Escrito assumindo que o agente NÃO leu nenhuma outra fase.

## 3. Leituras obrigatórias (lista fechada)
- packages/contracts/openapi.yaml  (seções: <tags exatas>)
- packages/contracts/schema.sql    (tabelas: <lista exata>)
- packages/contracts/errors.yaml
- packages/contracts/glossario.md
- <arquivos específicos desta fase>

## 4. Contratos
**Consome:** endpoints/tabelas/eventos que já existem.
**Produz:** endpoints/tabelas/eventos que esta fase implementa.
**Não toca:** o que é de outra fase.

## 5. Ownership de arquivos
Caminhos EXCLUSIVOS desta fase. Nenhuma outra fase escreve aqui.

## 6. Tarefas (T1..Tn)
Atômicas, ordenadas, cada uma com definição de pronto.

## 7. Critérios de aceite
Verificáveis, não subjetivos.

## 8. Comandos de verificação
Comandos exatos. A fase só está pronta quando todos rodam verde
E a saída real foi conferida.

## 9. Proibições
O que o agente NÃO deve fazer, para não invadir escopo alheio.
```

### 1.2 Regras de convivência

| Regra | Detalhe |
|---|---|
| **Ownership exclusivo** | Duas fases nunca escrevem no mesmo caminho. Conflito de merge é sinal de erro de planejamento |
| **Contratos são congelados** | Só a Fase 0 escreve em `packages/contracts/`. Depois disso, mudança exige RFC |
| **Worktree isolado** | Cada agente em `git worktree` próprio, branch `fXX-<slug>` |
| **Commits atômicos** | Prefixo da fase: `f07: adiciona detecção de mock location` |
| **Verificação antes de reportar** | Nenhum agente declara "pronto" sem rodar os comandos do §8 do seu PCF e colar a saída real |
| **Sem invenção de escopo** | Se está fora do PCF, não faz. Anota em `docs/backlog.md` |

### 1.3 Protocolo de RFC (quando o contrato está errado)

Vai acontecer — nenhum contrato nasce perfeito. Quando um agente descobre que o contrato está errado ou incompleto:

1. **Para** a tarefa afetada (continua as demais).
2. Escreve `docs/rfc/RFC-NNN-<slug>.md`: o que está errado, por quê, mudança proposta, fases impactadas.
3. O orquestrador decide, atualiza `packages/contracts/` e notifica **todas** as fases impactadas.
4. Nunca contorna o contrato silenciosamente. Contorno silencioso é como o sistema se desintegra.

---

## 2. Ondas de execução

Fases da mesma onda rodam **em paralelo**. Ondas rodam em sequência.

```
Onda 0 ──► Onda 1 ──► Onda 2 ──► Onda 3 ──► Onda 4 ──► Onda 5
  F0        F1           F3        F4         F10       F13
            F2           F5        F7         F11       F14
            F9a          F6        F8         F12       F15
                                   F9b
 2 ag.     8 ag.        9 ag.     16 ag.     11 ag.    10 ag.
  3 d       5 d          8 d       12 d       9 d       8 d
```

**Total: 16 fases · 56 slots de agente · ~45 dias úteis (~9 semanas) em caminho crítico.**

> **Nota de capacidade real:** a execução paralela é limitada a `min(16, núcleos − 2)` agentes simultâneos. A Onda 3, com 16 slots, vai enfileirar em máquina menor — recomendo quebrá-la em 3a (F4 + F7 = 9 agentes) e 3b (F8 + F9b = 7 agentes), o que adiciona ~2 dias ao caminho crítico mas evita contenção. Isso é decisão do momento do start, não do plano.

---

## 3. Fases

### ONDA 0

---

#### F0 — Fundação e Contratos 🔒 BLOQUEANTE
**Agentes: 2 · Duração: 3 dias · Depende de: nada**

| Agente | Papel |
|---|---|
| A1 | Arquiteto de Contratos — OpenAPI, modelo de dados, erros, eventos, glossário |
| A2 | Engenheiro de Plataforma — monorepo, Docker, Traefik, CI, migrations, esqueletos |

**Entrega**
- Monorepo `ponto-eletronico` criado e publicado (privado).
- `packages/contracts/` completo: `openapi.yaml` (todos os recursos da v1, ~120 operações), `schema.sql` + models SQLAlchemy, `errors.yaml`, `events.yaml`, `design-tokens.json`, `glossario.md`.
- `infra/`: `docker-compose.yml` (api, worker, scheduler, postgres, redis, minio, facial-svc, device-gw, web), labels do Traefik existente, `.env.example`.
- Esqueletos executáveis de todas as apps (sobem e respondem healthcheck com stubs).
- Migration inicial Alembic (aplica e reverte).
- CI GitHub Actions: lint + tipos + testes + build + validação de OpenAPI.
- ADRs 001–008: multi-tenancy/RLS, imutabilidade de marcação, geração de NSR, estratégia de recálculo, versionamento de API, criptografia de biometria, offline-first mobile, política de score de confiança.

**Aceite**
`docker compose --env-file infra/.env.example -f infra/docker-compose.yml config` válido *(o `--env-file` é obrigatório: os segredos usam `${VAR:?}` e recusam resolver sem valor — fail-fast deliberado, ver RFC-001 D-03)* · `docker compose build` sem erro · todos os serviços `healthy` em `docker ps` · `spectral lint openapi.yaml` sem erro · `alembic upgrade head && alembic downgrade base` contra PostgreSQL 16 real · CI verde no primeiro push.

**Proibições:** não implementar regra de negócio nenhuma. Fase 0 é contrato e andaime.

---

### ONDA 1

---

#### F1 — Identidade, Multi-tenant e RBAC
**Agentes: 3 · Duração: 5 dias · Depende de: F0**

| Agente | Escopo |
|---|---|
| A1 | Autenticação: login, senha (Argon2id), JWT RS256, refresh rotativo com detecção de reuso, MFA opcional (TOTP), recuperação de senha, sessões e revogação |
| A2 | Multi-tenancy: `tenant_id` em todo modelo, **Row Level Security** no PostgreSQL, resolução de tenant por subdomínio/header, seed de tenant |
| A3 | RBAC + auditoria: perfis, permissões granulares, escopo hierárquico (gestor vê sua árvore), delegação temporária, trilha de auditoria com hash encadeado |

**Aceite:** teste automatizado prova que usuário do tenant A **não** lê dado do tenant B nem com SQL direto (RLS ativa) · reuso de refresh token invalida a família · verificador de hash chain detecta remoção de linha da auditoria · matriz perfil × endpoint testada.

---

#### F2 — Cadastros organizacionais e pessoas
**Agentes: 3 · Duração: 5 dias · Depende de: F0 (paralela a F1, usa auth stub)**

| Agente | Escopo |
|---|---|
| A1 | Estrutura: empresas (CNPJ matriz/filial), unidades (endereço, **geocerca** ponto+raio e polígono, **allowlist CIDR**, fuso), departamentos, centros de custo, cargos, equipes |
| A2 | Pessoas: colaboradores (CPF, PIS/NIT, matrícula eSocial), contratos e vínculos múltiplos, admissão/demissão, hierarquia de gestores, histórico de mudanças |
| A3 | Biometria e dispositivos: enrollment multicanal com versionamento de modelo, template cifrado, cadastro de dispositivos (terminal, celular vinculado, navegador), importadores CSV/XLSX de colaboradores e estrutura |

**Aceite:** CRUD completo conforme OpenAPI · validação de CPF/CNPJ/PIS · importador processa 5.000 colaboradores com relatório de erros linha a linha · template biométrico ilegível sem a chave · geocerca aceita polígono e calcula pertencimento corretamente.

---

#### F9a — Design System
**Agentes: 2 · Duração: 5 dias · Depende de: F0 (`design-tokens.json`)**

| Agente | Escopo |
|---|---|
| A1 | Tokens → CSS/Tailwind, tema claro/escuro, tipografia, espaçamento, primitivos (botão, input, select, dialog, toast, tabela, tabs, badge) |
| A2 | Componentes de domínio: timeline de marcações, cartão de saldo de banco, grade de escala, seletor de período, data-table com colunas configuráveis e virtualização, gráficos base com paleta acessível |

**Aceite:** Storybook publicado com todos os componentes nos dois temas · contraste WCAG 2.2 AA verificado automaticamente · navegação por teclado em todos os interativos · data-table renderiza 10.000 linhas sem travar.

**Por que na Onda 1:** todo o trabalho de UI das ondas 3 e 4 depende disso. Se sair tarde, três fases param.

---

### ONDA 2

---

#### F3 — Motor de Jornada ⭐ CRÍTICA
**Agentes: 4 · Duração: 8 dias · Depende de: F0, F2**

| Agente | Escopo |
|---|---|
| A1 | Modelagem: jornadas fixas/flexíveis/livres, escalas (5x2, 6x1, 4x2, 12x36, espanhola, rotativa N dias), turnos com revezamento, jornada que cruza meia-noite, vigência e histórico |
| A2 | Calendário: feriados nacional/estadual/municipal por unidade, feriados móveis calculados, ponto facultativo, afastamentos (férias, atestado, licenças, INSS, suspensão) |
| A3 | Resolvedor: dado colaborador + data, retorna a jornada vigente, o horário previsto, os intervalos esperados e o tipo do dia (útil/DSR/feriado/afastado) |
| A4 | **Golden dataset** + testes: escreve os cenários trabalhistas com resultado esperado **antes** do código de cálculo existir |

**Aceite:** resolvedor cobre os 40+ cenários do golden dataset · virada de mês em 12x36 correta · troca de jornada no meio do mês respeita vigência · feriado municipal aplica só na unidade certa · cobertura ≥ 90 %.

**Nota:** esta é a fase onde projetos de ponto morrem. Por isso 4 agentes e o golden dataset primeiro.

---

#### F5 — Ingestão de Marcações e NSR
**Agentes: 3 · Duração: 6 dias · Depende de: F0, F1, F2**

| Agente | Escopo |
|---|---|
| A1 | Domínio da marcação: tabela append-only particionada por mês, **trigger que barra UPDATE/DELETE**, sequência de NSR transacional sem lacunas por REP-P, CRC-16 por registro, hash encadeado |
| A2 | Pipeline canal-agnóstico: recepção de qualquer canal, idempotência (`external_id`, `device_id + log_id`, `Idempotency-Key`), fila de sincronização offline, resolução de duplicata, carimbo de tempo do servidor |
| A3 | Comprovante de registro (últimas 48 h em app e web), estrutura do score de confiança (campos e API — as regras chegam na F14), consulta de marcações |

**Aceite:** teste tenta UPDATE e DELETE direto no banco e ambos falham · 10.000 marcações concorrentes produzem NSR de 1 a 10.000 sem buraco e sem repetição · reenvio do mesmo registro offline não duplica · comprovante recuperável por 48 h em todos os canais.

---

#### F6 — Integração Control iD (iDFace)
**Agentes: 2 · Duração: 6 dias · Depende de: F0, F2, F5**

| Agente | Escopo |
|---|---|
| A1 | `device-gw`: sessão via `login.fcgi`, **modo Push** (terminal busca comandos no servidor), serviço **Monitor** (eventos assíncronos), *catch-up* de `access_logs` por marca d'água, conversão para marcação canônica, saúde e reconexão de terminal |
| A2 | Provisionamento: sincronização de `users`, `templates`, `groups`, `access_rules`, `portals`, `time_zones`; envio de face por `user_set_image`; `execute_actions.fcgi`; **simulador de terminal** para desenvolver e testar sem hardware |

**Aceite:** com o simulador, 1.000 eventos entram sem duplicar e sem perder · derrubar a rede por 10 min e religar recupera tudo via catch-up · alteração de colaborador propaga ao terminal em < 60 s · terminal offline gera alerta.

**Nota:** o simulador não é luxo — sem ele a fase fica bloqueada esperando hardware, e as fases 3, 4 e 5 do teste e2e também.

---

### ONDA 3

---

#### F4 — Cálculo e Banco de Horas ⭐ CRÍTICA
**Agentes: 4 · Duração: 10 dias · Depende de: F3, F5**

| Agente | Escopo |
|---|---|
| A1 | Apuração do dia: pareamento de marcações, tolerância (5 min/marcação, 10 min/dia), horas normais, extras por faixa e fator, adicional noturno com hora ficta 52'30" e prorrogação, intrajornada, interjornada, DSR, faltas/atrasos/saídas antecipadas |
| A2 | **Banco de horas**: múltiplas contas por colaborador, fatores de crédito/débito, extrato conta-corrente imutável, vencimento (6 meses individual / 12 meses coletivo) com FIFO ou LIFO, quitação em folha, expiração, tetos positivo e negativo, compensação programada, simulador de saldo |
| A3 | Camada de tratamento: ajustes aprovados, abonos, afastamentos aplicados sobre a apuração sem tocar na marcação; recálculo determinístico e idempotente com *diff* auditado; trava de período fechado |
| A4 | Verificação: execução do golden dataset da F3 contra o cálculo real, testes de propriedade, performance |

**Aceite:** 100 % do golden dataset passa · recalcular duas vezes o mesmo período dá exatamente o mesmo resultado · apuração de 10.000 colaboradores × 31 dias em < 5 min · extrato de banco fecha com a soma dos lançamentos em todos os cenários · alterar regra retroativamente reprocessa só o intervalo afetado e registra o diff.

---

#### F7 — App Mobile (Flutter)
**Agentes: 5 · Duração: 12 dias · Depende de: F1, F2, F5, F9a**

| Agente | Escopo |
|---|---|
| A1 | Shell: navegação, tema (tokens da F9a), estado (Riverpod), cliente HTTP com pinning, login, sessão, i18n |
| A2 | Captura facial: câmera, ML Kit, **prova de vida** (desafio ativo + análise passiva), qualidade de imagem, envio ao `facial-svc`, fallback por PIN |
| A3 | **Antifraude**: Play Integrity (Android) + App Attest/DeviceCheck (iOS) com verificação no servidor; RASP (root, jailbreak, Magisk, Xposed, Frida, debugger, emulador, binário adulterado); **detecção de modo desenvolvedor / depuração USB**; detecção de **mock location** e apps de fake GPS; coerência GPS × Wi-Fi BSSID × célula × IP; vínculo de dispositivo; bloqueio de screenshot e overlay |
| A4 | **Offline**: Drift/SQLite, fila cifrada AES-GCM, HMAC por registro com chave no keystore/enclave, contador monotônico anti-replay, TTL de 72 h, sincronização com resolução de conflito, indicador claro de "pendente de envio" |
| A5 | Autoatendimento: espelho do mês, saldo e extrato de banco, solicitação de ajuste com anexo, férias/folga, notificações push, comprovantes das últimas 48 h, **modo quiosque compartilhado**, leitura de QR/NFC do local |

**Aceite:** build Android e iOS gerados em CI · bater ponto sem rede e sincronizar depois preserva o horário real e é sinalizado como offline · emulador com fake GPS é detectado e bloqueado conforme política · celular com modo desenvolvedor ligado respeita a política da empresa (bloquear/sinalizar/permitir) · foto impressa e vídeo em tela reprovam na prova de vida · comprovante das últimas 48 h disponível offline.

---

#### F8 — Web colaborador e registro por webcam
**Agentes: 3 · Duração: 8 dias · Depende de: F1, F5, F9a**

| Agente | Escopo |
|---|---|
| A1 | Portal do colaborador: espelho, saldo e extrato de banco, solicitações, comprovantes, perfil, PWA instalável |
| A2 | Registro por webcam: captura ao vivo via `getUserMedia` (nunca upload), prova de vida com desafio aleatório, **detecção de câmera virtual**, feedback de confirmação inequívoco |
| A3 | Controles de acesso ao registro: **allowlist CIDR por empresa/unidade** (IPv4 e IPv6), fingerprint de dispositivo, bloqueio opcional de VPN/proxy/ASN de datacenter, reautenticação para bater ponto, mensagens de erro que explicam sem vazar a regra |

**Aceite:** IP fora da allowlist não consegue registrar e recebe mensagem clara · OBS Virtual Camera é detectada e bloqueada · upload de arquivo de imagem é rejeitado · Lighthouse ≥ 90 em performance e acessibilidade.

---

#### F9b — Painel RH e Gestor
**Agentes: 4 · Duração: 10 dias · Depende de: F2, F3, F4, F9a**

| Agente | Escopo |
|---|---|
| A1 | Dashboards: RH (empresa), gestor (equipe), diretoria (custo e conformidade); KPIs, gráficos, tempo real de quem está trabalhando |
| A2 | Telas de cadastro: empresas, unidades com mapa e geocerca, departamentos, centros de custo, cargos, colaboradores, contratos, dispositivos, biometria |
| A3 | Grade de apuração: visão mês × colaborador, edição via tratamento (nunca marcação), destaque de inconsistências, ações em lote, recálculo sob demanda |
| A4 | Escalas e planejamento: montagem de escala, cópia de período, previsão × realizado, cobertura por turno |

**Aceite:** grade de apuração com 500 colaboradores × 31 dias navega fluida · toda edição gera tratamento auditado e nunca altera marcação · geocerca editável em mapa e refletida no app · dois temas e responsivo até 1280 px.

---

### ONDA 4

---

#### F10 — Workflows, aprovações e fechamento
**Agentes: 4 · Duração: 8 dias · Depende de: F4, F9b**

| Agente | Escopo |
|---|---|
| A1 | Motor de solicitações: tipos configuráveis, cadeia de aprovação (gestor → RH), prazos, escalonamento, delegação, histórico |
| A2 | Fechamento: conferência, correções, trava, geração do espelho, **assinatura eletrônica do colaborador** com carimbo de tempo e hash, reabertura auditada e nominal |
| A3 | Notificações multicanal: push (app), e-mail, in-app e **WhatsApp via OpaSuite** (já disponível na infra); regras (esqueceu de bater, jornada excedida, banco vencendo, pendência há N dias); preferências por usuário |
| A4 | Férias, afastamentos e abonos: solicitação, programação, aprovação, efeito no cálculo, anexos (atestado), tipos configuráveis |

**Aceite:** solicitação percorre a cadeia completa e reflete na apuração · fechar período trava edição e reabrir exige justificativa registrada com autor · assinatura do colaborador é verificável e não repudiável · notificação chega nos 4 canais em teste e2e.

---

#### F11 — Relatórios, espelho e exportações
**Agentes: 4 · Duração: 9 dias · Depende de: F4, F9a, F10**

| Agente | Escopo |
|---|---|
| A1 | Engine: colunas configuráveis e salvas por usuário, filtros compostos, agrupamentos, totalizadores, paginação/virtualização, execução assíncrona para volumes grandes |
| A2 | Relatórios 1–12 (operacionais): jornada/espelho prévio com 30+ colunas, banco de horas, horas extras, adicional noturno, absenteísmo, atrasos, faltas, tempo real, ocorrências, abonos, férias/afastamentos |
| A3 | Relatórios 13–24 (gerenciais e fiscais) + exportadores CSV/XLSX/PDF + conversão decimal |
| A4 | **Espelho de ponto oficial** em PDF (cabeçalho legal, layout de designer), agendamento por e-mail, dataviz dos dashboards |

**Aceite:** os 24 relatórios do catálogo geram e exportam nos 3 formatos · relatório de 12 meses × 1.000 colaboradores conclui em < 60 s (assíncrono com progresso) · espelho de ponto confere campo a campo com a apuração · colunas configuradas persistem por usuário.

---

#### F12 — Conformidade REP-P (AFD, AEJ, assinatura) ⭐ CRÍTICA
**Agentes: 3 · Duração: 8 dias · Depende de: F5, F4, F10**

| Agente | Escopo |
|---|---|
| A1 | **T0 bloqueante:** conferir o leiaute campo a campo contra os anexos da Portaria 671/2021 e documentar em `docs/leiaute-afd-aej.md`. Depois: gerador de **AFD** (ASCII ISO 8859-1, separador `\|`, CR+LF, NSR sequencial, registro **tipo 7** para REP-P com NSR + tipo + data/hora + CPF + CRC-16, demais tipos, **CRC-16** por registro, **SHA-256** do arquivo, fracionamento por período) |
| A2 | Gerador de **AEJ**: cabeçalho, REPs utilizados, vínculos, horário contratual, marcações, matrícula eSocial, ausências, **banco de horas**, identificação do PTRP, trailer |
| A3 | **Assinatura CAdES** em `.p7s` destacado com certificado ICP-Brasil (e-CNPJ A1), assinatura do comprovante de registro, cofre de arquivos gerados com histórico e download, validação cruzada |

**Aceite:** AFD gerado passa em validador oficial/de mercado · comparação byte a byte contra AFD de sistema já aceito para o mesmo conjunto de marcações · `.p7s` valida em verificador ICP-Brasil independente · AEJ contém banco de horas coerente com o extrato · lacuna de NSR é impossível de produzir (teste adversarial).

**Dependência externa:** o certificado e-CNPJ A1 precisa estar disponível. Sem ele, a fase entrega arquivos válidos porém **não assinados**, e a assinatura vira tarefa de 1 dia quando o certificado chegar.

---

### ONDA 5

---

#### F13 — API pública, webhooks e integrações
**Agentes: 3 · Duração: 7 dias · Depende de: F0, F4, F11, F12**

| Agente | Escopo |
|---|---|
| A1 | API pública `/v1`: OAuth 2.0 client credentials, escopos granulares, API keys por ambiente, rate limit por cliente, idempotência, versionamento e política de depreciação, portal de documentação interativo, **sandbox com dados sintéticos** |
| A2 | Webhooks: assinatura HMAC, retentativa exponencial, dead letter, reenvio manual, painel de entregas, os eventos do `events.yaml` |
| A3 | Integrações: exportadores de folha (Domínio, Alterdata, TOTVS RM/Protheus/Datasul, Senior, Sankhya, Questor, Fortes, Contmatic + layout genérico), **importador de AFD de terceiros**, SSO (Google Workspace, Entra ID, SAML 2.0) |

**Aceite:** Schemathesis roda contra o OpenAPI sem divergência · webhook com endpoint fora do ar acumula em DLQ e reenvia · cada exportador de folha valida contra layout de referência do parceiro · importador de AFD de outro fabricante ingere sem quebrar NSR próprio (namespace separado).

---

#### F14 — Segurança, antifraude e LGPD
**Agentes: 4 · Duração: 8 dias · Depende de: F5, F7, F8, F13**

| Agente | Escopo |
|---|---|
| A1 | **Score de confiança** no servidor: composição dos sinais (attestation, RASP, modo dev, mock location, coerência geográfica, velocidade impossível, reputação de dispositivo), políticas configuráveis por empresa (bloquear / sinalizar / permitir), fila de revisão do gestor, painel de marcações suspeitas |
| A2 | Hardening: rate limiting, proteção contra enumeração, revisão de RLS, certificate pinning, gestão e rotação de segredos, mTLS `device-gw` ↔ `facial-svc`, **Semgrep + CodeQL** no CI, correção dos achados |
| A3 | LGPD: registro de consentimento versionado, criptografia de template com chave separada, política de retenção e expurgo automático, atendimento a titular (acesso, correção, portabilidade, eliminação), **RIPD**, registro de operações de tratamento, contrato de operador para clientes SaaS |
| A4 | Verificação adversarial: tentar fraudar o próprio sistema (foto impressa, vídeo, emulador, fake GPS, replay de payload offline, manipulação de relógio, cross-tenant) e corrigir tudo que passar |

**Aceite:** relatório de pentest interno com todos os achados críticos e altos fechados · nenhum vetor da lista adversarial passa · Semgrep/CodeQL sem findings de severidade alta · expurgo automático comprovado em teste · exportação de dados do titular funciona ponta a ponta.

---

#### F15 — Observabilidade, deploy e homologação
**Agentes: 3 · Duração: 7 dias · Depende de: todas**

| Agente | Escopo |
|---|---|
| A1 | Observabilidade: OpenTelemetry ponta a ponta, Prometheus + Grafana (dashboards de API, workers, terminais, apuração), Loki, Sentry, alertas (terminal offline, fila travada, apuração falhando, erro 5xx), **runbooks** |
| A2 | Deploy: `/docker/ponto/` na VPS atrás do Traefik existente, ambientes hml e prd, backup criptografado com **restauração testada**, migrations com rollback, deploy sem downtime, plano de contingência |
| A3 | Homologação: teste de carga (k6), UAT com a SEEG como cliente #1, checklist de conformidade REP-P, documentação de usuário (RH, gestor, colaborador), material de treinamento, roteiro de migração de dados |

**Aceite:** `docker ps` com todos os serviços healthy em produção · restauração de backup validada em ambiente limpo · k6 com 500 marcações simultâneas sem erro · UAT assinado pela SEEG · checklist REP-P completo com evidências.

---

## 4. Painel de fases

| Fase | Nome | Onda | Agentes | Dias | Depende de | Criticidade |
|---|---|---|---|---|---|---|
| F0 | Fundação e Contratos | 0 | 2 | 3 | — | 🔒 Bloqueante |
| F1 | Identidade, Multi-tenant, RBAC | 1 | 3 | 5 | F0 | Alta |
| F2 | Cadastros organizacionais e pessoas | 1 | 3 | 5 | F0 | Alta |
| F9a | Design System | 1 | 2 | 5 | F0 | Alta |
| F3 | Motor de Jornada | 2 | 4 | 8 | F0, F2 | ⭐ Crítica |
| F5 | Ingestão de Marcações e NSR | 2 | 3 | 6 | F0, F1, F2 | ⭐ Crítica |
| F6 | Integração Control iD | 2 | 2 | 6 | F0, F2, F5 | Média |
| F4 | Cálculo e Banco de Horas | 3 | 4 | 10 | F3, F5 | ⭐ Crítica |
| F7 | App Mobile Flutter | 3 | 5 | 12 | F1, F2, F5, F9a | Alta |
| F8 | Web colaborador + webcam | 3 | 3 | 8 | F1, F5, F9a | Alta |
| F9b | Painel RH e Gestor | 3 | 4 | 10 | F2, F3, F4, F9a | Alta |
| F10 | Workflows e fechamento | 4 | 4 | 8 | F4, F9b | Alta |
| F11 | Relatórios e exportações | 4 | 4 | 9 | F4, F9a, F10 | Alta |
| F12 | Conformidade REP-P | 4 | 3 | 8 | F5, F4, F10 | ⭐ Crítica |
| F13 | API pública e integrações | 5 | 3 | 7 | F0, F4, F11, F12 | Média |
| F14 | Segurança, antifraude, LGPD | 5 | 4 | 8 | F5, F7, F8, F13 | ⭐ Crítica |
| F15 | Observabilidade e homologação | 5 | 3 | 7 | todas | Alta |
| | **Total** | | **56** | **~45 d úteis** | | |

---

## 5. O que acontece quando você aprovar

1. **Fase 0 sozinha primeiro.** 2 agentes, 3 dias. Nada mais roda até os contratos estarem congelados — é o investimento que paga todo o paralelismo depois.
2. **Revisão sua dos contratos.** Você olha `openapi.yaml` e `schema.sql`. É o último momento barato para mudar de ideia sobre o modelo.
3. **A partir da Onda 1, execução contínua.** Cada onda dispara suas fases em paralelo, cada agente em worktree próprio, e só avança quando os critérios de aceite da onda anterior estiverem verdes com saída conferida.
4. **Checkpoint no fim de cada onda:** demonstração do que funciona, revisão de RFCs abertos, ajuste de escopo se necessário.

**Em paralelo, do dia 1 (não bloqueiam código, bloqueiam a homologação):**
- Solicitar o certificado **e-CNPJ A1 ICP-Brasil** da SEEG.
- Iniciar o **registro do programa no INPI**.
- Providenciar um **iDFace** físico para os testes da F6.
- Formalizar juridicamente o **acordo de banco de horas** da SEEG (individual escrito ou via CCT).
