# Ponto Eletrônico — Projeto Técnico

> **Codinome de trabalho:** `Kairo Ponto` (marca definitiva a definir — o código usa `ponto` como namespace neutro)
> **Empresa:** SEEG Serviços de Tecnologia da Informação (CNPJ 60.258.502/0001-49)
> **Documento:** especificação de produto e arquitetura · v1.0 · 25/07/2026
> **Execução:** ver [FASES-E-AGENTES.md](FASES-E-AGENTES.md)

---

## 1. Decisões fundadoras (aprovadas)

| # | Decisão | Escolha | Consequência |
|---|---|---|---|
| D1 | Escopo comercial | **Multi-empresa (SaaS)** | Todo dado nasce com `tenant_id`; RLS no PostgreSQL; SEEG é o cliente #1 e cliente de homologação |
| D2 | App de celular | **Flutter (Android + iOS)** | Um código-fonte; plugins nativos para integridade/attestation e câmera |
| D3 | Conformidade legal | **REP-P completo (Portaria MTP 671/2021)** | AFD com NSR + CRC-16 + SHA-256 + assinatura CAdES; AEJ; comprovante; exige e-CNPJ A1 e registro INPI |
| D4 | Motor facial (app/web) | **Reaproveitar `analise-facial-edge`** | Self-hosted, sem custo por chamada, biometria não sai da infra SEEG (LGPD) |

**Dependências externas que precisam ser iniciadas já (não bloqueiam o código, bloqueiam a homologação):**
1. Certificado digital **e-CNPJ A1 ICP-Brasil** da SEEG (para assinar AFD e comprovantes em CAdES/`.p7s`).
2. **Registro do programa no INPI** (o REP-P não exige homologação ministerial, mas exige o certificado de registro de programa de computador).
3. Aquisição/empréstimo de um **Control iD iDFace** físico para integração e teste.
4. Definição jurídica do **acordo de banco de horas** da SEEG (individual escrito = 6 meses; ACT/CCT = 12 meses).

---

## 2. Visão do produto

Sistema de ponto eletrônico **REP-P** multiempresa, com registro por **cinco canais** (terminal facial, app mobile, navegador, totem/quiosque e API), motor de jornada e **banco de horas** completo, workflow de aprovações, mais de 20 relatórios gerenciais, geração dos arquivos fiscais **AFD/AEJ** assinados digitalmente e **API pública** para integração com folha de pagamento e ERPs.

### 2.1 Princípios inegociáveis de arquitetura

1. **Marcação é imutável.** Nenhum endpoint, tela ou rotina altera ou apaga um registro de marcação. Correções vivem numa camada separada de *tratamento*, sempre auditada. Isso não é preferência de engenharia — é exigência da Portaria 671 (é vedado ao REP alterar ou apagar marcações, e é vedado inserir marcação que não corresponda ao fato real).
2. **NSR sem lacunas.** O Número Sequencial de Registro é gerado por sequência transacional do banco, por REP-P, começando em 1, sem buracos e sem reuso — inclusive para marcações que chegam offline dias depois.
3. **O relógio é do servidor.** O horário do dispositivo nunca é a fonte de verdade. Em registros offline, guardamos os dois (relógio do device + tempo monotônico) e o servidor classifica a confiança temporal, sinalizando a marcação como *coletada offline* no espelho.
4. **Biometria é dado pessoal sensível (LGPD art. 5º, II).** Template criptografado em repouso, chave separada da base, nunca trafega imagem crua para a nuvem quando houver edge, consentimento registrado e rotina de expurgo.
5. **Contratos antes de código.** OpenAPI, schema do banco, catálogo de erros, catálogo de eventos e design tokens são congelados na Fase 0. Toda fase seguinte consome contrato, não conhecimento tribal — é isso que permite N agentes trabalharem em paralelo sem quebrar contexto.
6. **Trilha de auditoria encadeada.** Cada evento de auditoria carrega o hash do anterior (hash chain), tornando remoção silenciosa detectável.

---

## 3. Canais de registro de ponto

O usuário pediu "vários tipos de bater o ponto". Mapeamento completo:

### 3.1 Terminal facial Control iD iDFace *(canal primário na sede)*

| Item | Especificação |
|---|---|
| Modelos | iDFace Lite (3.000 faces) / iDFace Pro (30.000 faces) · +200.000 usuários cadastrados |
| Identificação | Face (câmeras duplas HD 1080p, luz visível + infravermelho, detecção de face viva), cartão de proximidade (MIFARE, 125 kHz ASK, HID), senha numérica, QR Code |
| Conectividade | Ethernet 10/100, Wi-Fi (opcional), USB 2.0 host, RS-485, GPRS (opcional), SIP (Pro) |
| Ambiente | IP65, −20 °C a 40 °C, fonte 12 V 2 A |
| Integração | API REST sobre HTTP (`*.fcgi`), sessão via `login.fcgi`, CRUD via `create_objects` / `load_objects` / `modify_objects` / `destroy_objects`, ações via `execute_actions.fcgi`, foto/face via `user_set_image`, **modo Push** (equipamento consulta o servidor periodicamente buscando comandos) e **serviço Monitor** (eventos assíncronos: novo `access_log`, alarme, cadastro de credencial, giro de catraca, abertura de porta) |
| Tabelas relevantes | `users`, `templates`, `groups`, `access_rules`, `portals`, `time_zones`, `access_logs`, `alarm_logs` |

**Como usamos:** o iDFace é um **coletor**. Ele não é o REP-P — o REP-P é o nosso software. O terminal identifica e produz um `access_log`; nosso *device gateway* recebe (via Monitor/Push), converte em marcação canônica e é **o servidor** quem atribui NSR e grava no AFD.

**Modo push é obrigatório na nossa topologia** porque o terminal costuma ficar em LAN sem IP público — quem inicia a conexão é o equipamento.

**Contingência:** se a rede cair, o iDFace armazena localmente; nosso gateway faz *catch-up* por `load_objects` sobre `access_logs` com marca d'água do último ID coletado, garantindo que nada se perca (e nada duplique — chave de idempotência `device_id + access_log_id`).

**Extensível a:** iDBlock/catracas Control iD, e por importação de AFD a Henry, Topdata, Madis, Dimep e Inner.

### 3.2 App mobile (Flutter) — facial + GPS + anti-fraude + offline

Fluxo de uma batida:
1. App verifica **integridade do ambiente** *antes* de abrir a câmera (ver §7.1). Se reprovar por política da empresa, bloqueia e explica o motivo.
2. Captura facial com **prova de vida** (desafio ativo: piscar / virar a cabeça + análise passiva de textura).
3. Coleta **posição** (GPS + rede), precisão, e sinais de corroboração: BSSID do Wi-Fi, célula, altímetro.
4. Valida **geocerca** da unidade/cliente (raio ou polígono) — ou marca como "fora da cerca" quando a política permitir (ex.: vendedor externo) para o gestor tratar.
5. Envia. Se **sem internet**, grava na fila local criptografada, assinada com HMAC de chave derivada no *secure enclave/keystore*, e sincroniza depois.
6. Recebe o **comprovante** (com NSR, CPF, data/hora, hash) e guarda no histórico local. As últimas 48 h ficam sempre acessíveis — é o que a Portaria exige para dispensar comprovante impresso.

Extras do app:
- Espelho de ponto do mês, saldo de banco de horas em tempo real, próximos feriados.
- Solicitação de ajuste, justificativa com foto do atestado, pedido de férias/folga.
- Notificações push (esqueceu de bater, ajuste aprovado/reprovado, fechamento aberto).
- Modo **quiosque compartilhado** (tablet fixo no chão de fábrica: matrícula/PIN + facial, sem login individual).
- Widget/atalho de batida rápida e leitura de **QR Code fixo / tag NFC** no local de trabalho como segundo fator de presença.

### 3.3 Navegador (web) — webcam + IP corporativo

- Registro só habilita se o IP de origem estiver na **allowlist CIDR** da empresa/unidade (IPv4 e IPv6, suporte a múltiplos links).
- **Webcam obrigatória** — captura ao vivo via `getUserMedia`, nunca upload de arquivo.
- Detecção de **câmera virtual** (OBS Virtual Camera e similares) por inspeção de `enumerateDevices` + heurística de estabilidade de frames.
- Prova de vida com desafio aleatório.
- *Fingerprint* de dispositivo + navegador, sessão curta e reautenticação para bater ponto mesmo já logado.
- Bloqueio configurável de acesso via VPN/proxy/datacenter (base de ASN).

### 3.4 Totem / Quiosque

Tablet ou PC com webcam em modo dedicado, sem sessão pessoal: matrícula + facial, fila de N pessoas, feedback grande e sonoro, funciona offline com sincronização.

### 3.5 API / Integração

Endpoint autenticado (`POST /v1/marcacoes`) para relógios de terceiros, catracas, sistemas de acesso e integrações sob medida, com idempotência por `external_id` e a mesma trilha de auditoria dos demais canais.

### 3.6 Lançamento manual (RH/gestor) — *não é canal de marcação*

Deliberadamente **não gera registro no AFD**. Vive na camada de tratamento, aparece no espelho identificado como lançamento manual com autor, data/hora, motivo e anexo, e vai para o **AEJ**. Essa separação é o que mantém o AFD fidedigno e o sistema defensável numa fiscalização.

---

## 4. Motor de jornada e cálculo

### 4.1 Modalidades de jornada suportadas

- Jornada fixa (entrada/saída/intervalo definidos por dia da semana).
- Jornada flexível (carga diária/semanal com janela de tolerância).
- Jornada móvel / livre (sem horário previsto, só carga total).
- Escalas: 5x2, 6x1, 4x2, **12x36**, escala espanhola, escalas rotativas com ciclo N dias.
- Turnos com **revezamento** e virada de dia (jornada que cruza meia-noite).
- Tempo parcial, jovem aprendiz, estagiário.
- Teletrabalho (art. 62, III da CLT — controle facultativo, configurável por contrato).
- Sobreaviso e prontidão (fatores próprios).
- Motoristas profissionais (Lei 13.103 — tempo de espera e direção).

### 4.2 Regras de cálculo

| Regra | Comportamento |
|---|---|
| Tolerância | Até 5 min por marcação e 10 min no total do dia (art. 58, §1º CLT); configurável por empresa, com opção "desconta tudo se estourar" |
| Horas extras | Fatores configuráveis por faixa (ex.: 1ª e 2ª hora 50 %, além disso 100 %, domingo/feriado 100 %); limite de 2 h/dia e 10 h de jornada; alerta e bloqueio opcionais |
| Adicional noturno | 22h–05h, hora ficta de 52'30" (urbano), prorrogação do noturno; regra rural configurável |
| Intrajornada | Mínimo legal por faixa de jornada; violação gera indenização de 50 % do período suprimido (art. 71, §4º) e ocorrência no relatório |
| Interjornada | Mínimo de 11 h entre jornadas; violação vira ocorrência |
| DSR | Repouso semanal remunerado, crédito/débito de DSR sobre horas extras, perda por falta injustificada |
| Pausas NR-17 | Pausas obrigatórias para digitação/teleatendimento, com contagem automática |
| Faltas e atrasos | Falta integral, meia falta, atraso, saída antecipada, com abono por tipo |
| Feriados | Base nacional + estadual + municipal + ponto facultativo, por unidade/CEP; feriado móvel calculado (Páscoa etc.) |
| Afastamentos | Férias, atestado, licença-maternidade/paternidade, INSS, suspensão, com integração ao cálculo |
| Compensação | Semanal, mensal e via banco de horas |

### 4.3 Banco de horas — o núcleo pedido

Requisito explícito: *"Empresa trabalha com banco de horas"*. O módulo é tratado como produto dentro do produto.

- **Múltiplos regimes por empresa/contrato:** acordo individual escrito (compensação em até **6 meses**) e acordo/convenção coletiva (até **12 meses**), com o teto legal de 10 h diárias respeitado.
- **Múltiplas contas por colaborador** (ex.: banco normal, banco de sobreaviso, banco de feriado) com fatores de crédito/débito distintos.
- **Extrato tipo conta-corrente:** cada lançamento com origem rastreável (apuração do dia X, ajuste aprovado, quitação em folha, expiração), saldo corrido, e nunca sobrescrito.
- **Vencimento e prescrição:** política FIFO ou LIFO; horas que atingem o fim do período são automaticamente **quitadas em folha** ou **expiradas**, conforme regra — com pré-aviso de 30/15/7 dias ao gestor e ao colaborador.
- **Limites de saldo** (teto positivo e negativo) com alerta e bloqueio de novas extras.
- **Compensação programada:** agendamento de folga que consome saldo previamente.
- **Simulador:** o colaborador vê "se eu sair às 16h na sexta, meu saldo fica em X".
- **Fechamento de banco** independente do fechamento do ponto, com relatório de quitação exportável para folha.

### 4.4 Camada de tratamento

Sequência canônica: `marcações imutáveis` → `regras da jornada do dia` → `tratamentos aplicáveis` (ajustes aprovados, abonos, afastamentos) → `apuração do dia` → `lançamentos de banco de horas` → `fechamento`.

A apuração é **recalculável e determinística**: mudou uma regra ou entrou um atestado retroativo, o motor reprocessa o intervalo afetado e registra o *diff* na auditoria. Períodos fechados só reprocessam com reabertura autorizada e justificada.

---

## 5. Gestão de pessoas e acessos

**Estrutura organizacional:** Tenant → Empresas (CNPJ matriz/filiais) → Unidades (com endereço, geocerca, CIDRs, feriados municipais) → Departamentos → Centros de custo → Cargos → Equipes.

**Colaborador:** dados pessoais, CPF, PIS/NIT, **matrícula eSocial**, foto, contratos (múltiplos vínculos ativos possíveis), admissão/demissão, jornada vigente com histórico, gestores diretos e substitutos, dependentes, documentos.

**Cadastro biométrico (enrollment):** presencial no iDFace, remoto pelo app com validação por RH, ou importação de foto — sempre com versionamento do modelo facial, para permitir troca de motor sem perder rastreabilidade.

**Perfis (RBAC + escopo):**

| Perfil | Alcance |
|---|---|
| Super admin (SEEG) | Cross-tenant, suporte, sem acesso a biometria bruta |
| Admin da empresa | Tudo dentro do tenant |
| RH | Cadastros, apuração, fechamento, relatórios, arquivos fiscais |
| Gestor | Sua árvore de subordinados: aprovações, escalas, relatórios da equipe |
| Colaborador | Só o próprio: bater ponto, espelho, saldo, solicitações |
| Auditor / Fiscal | Somente leitura, incluindo AFD/AEJ e trilha de auditoria |
| Integração (máquina) | Escopos OAuth granulares |

Permissões granulares por recurso e ação, delegação temporária (férias do gestor), e **toda leitura de dado sensível é logada**.

---

## 6. Fluxos e workflow

- **Solicitação de ajuste de ponto:** colaborador aponta o dia → anexa justificativa → gestor aprova/reprova → RH homologa (etapa opcional). Prazo configurável, escalonamento automático, notificação em todos os canais.
- **Justificativas e abonos** com anexo (atestado, declaração), tipos configuráveis, e efeito no cálculo por tipo.
- **Férias:** solicitação, aprovação, programação, integração com o cálculo e com o eSocial (evento S-2230).
- **Folgas e compensações** consumindo banco de horas.
- **Fechamento de período:** conferência → correções → trava → geração do espelho → **assinatura eletrônica do colaborador** (aceite com carimbo de tempo e hash) → exportação para folha. Reabertura sempre auditada e nominal.
- **Notificações:** push (app), e-mail, WhatsApp (via OpaSuite, já disponível na infra) e in-app. Regras: esqueceu de bater, jornada excedida, banco perto do vencimento, solicitação pendente há N dias.

---

## 7. Segurança e antifraude

### 7.1 App mobile — camadas

| Camada | Implementação |
|---|---|
| Attestation de plataforma | **Play Integrity API** (Android) exigindo veredito de dispositivo/app; **App Attest + DeviceCheck** (iOS). Veredito verificado **no servidor**, nunca no cliente |
| RASP | Detecção de root/jailbreak, Magisk, Xposed, Frida, hooking, debugger anexado, emulador e binário adulterado |
| **Modo desenvolvedor** *(requisito explícito)* | Leitura de `DEVELOPMENT_SETTINGS_ENABLED` e `ADB_ENABLED`; política por empresa: **bloquear**, **permitir sinalizando risco** ou **permitir**. Padrão recomendado: bloquear na sede, sinalizar em campo |
| GPS falso | `Location.isMock` / `isFromMockProvider`, varredura de apps de fake GPS, checagem de coerência entre GPS, BSSID de Wi-Fi, célula e IP; detecção de saltos impossíveis (velocidade > limiar entre marcações) |
| Prova de vida | Desafio ativo aleatório + análise passiva anti-*spoof* (foto de foto, vídeo em tela, máscara) |
| Vínculo de dispositivo | 1 dispositivo ativo por colaborador; troca exige aprovação do RH; chave por dispositivo no keystore/enclave |
| Transporte | TLS 1.3 + *certificate pinning*; payload assinado |
| Offline | Fila cifrada (AES-GCM) com HMAC por registro, contador monotônico anti-*replay*, TTL de sincronização (padrão 72 h), e o servidor **marca a marcação como coletada offline** — nunca finge que foi online |
| Anticaptura | Bloqueio de screenshot/gravação e detecção de overlay durante a captura facial |
| Binário | Ofuscação (R8/ProGuard), sem segredos embarcados, chaves derivadas em runtime |

**Modelo de risco:** cada marcação recebe um **score de confiança** (0–100) composto pelos sinais acima. A empresa configura o limiar: acima dele grava direto; entre limiares grava e sinaliza para revisão do gestor; abaixo bloqueia. Isso evita o falso-dilema "bloqueia tudo ou aceita tudo" — e é o que torna o sistema utilizável no mundo real, onde celular corporativo antigo às vezes reprova attestation legitimamente.

### 7.2 Web

Allowlist de CIDR por unidade · webcam ao vivo obrigatória · detecção de câmera virtual · prova de vida · fingerprint de dispositivo · bloqueio opcional de VPN/proxy/ASN de datacenter · reautenticação para bater ponto.

### 7.3 Backend

- Marcações **append-only** com hash encadeado; qualquer tentativa de UPDATE/DELETE é barrada por *trigger* e por permissão de banco.
- Trilha de auditoria imutável (quem, quando, de onde, o quê, valor antes/depois).
- Isolamento multi-tenant por **Row Level Security** do PostgreSQL, além do filtro de aplicação (defesa em profundidade).
- Segredos fora do git (`.env` sempre gitignored, conforme regra da casa), rotação de chaves, `.env.example` versionado.
- Rate limiting por IP/cliente/rota, proteção contra enumeração, bloqueio progressivo.
- mTLS entre gateway de dispositivos e serviço edge facial.
- Backups criptografados com teste de restauração agendado.

### 7.4 LGPD

Base legal (obrigação legal para o ponto; consentimento específico para biometria) · registro de consentimento versionado · minimização (edge processa, nuvem recebe vetor/evento) · criptografia de template com chave gerenciada separadamente · política de retenção (marcações 5 anos; imagens de captura por prazo curto configurável) · atendimento a titular (acesso, correção, portabilidade, eliminação) · **RIPD** documentado · registro de operações de tratamento · contrato de operador para clientes SaaS.

---

## 8. Conformidade REP-P (Portaria MTP 671/2021)

### 8.1 O que o sistema precisa entregar

| Exigência | Como atendemos |
|---|---|
| Registro do programa no **INPI** | Processo externo, iniciado em paralelo; número gravado na configuração e impresso no cabeçalho do AFD (só dígitos) |
| **AFD** (Arquivo Fonte de Dados) | Gerado exclusivamente pelo REP-P. Texto ASCII ISO 8859-1, campos separados por `\|`, linhas terminadas em CR+LF, um NSR por registro começando em 1 sem lacunas, **CRC-16 por registro** e **SHA-256 do arquivo**. Registro tipo **7** = marcação do REP-P (NSR, tipo, data/hora, CPF do trabalhador, CRC-16). Fracionamento por período permitido no REP-P |
| **Assinatura digital** | Padrão **CAdES**, arquivo `.p7s` destacado, com certificado **ICP-Brasil** válido do desenvolvedor/fabricante |
| **Comprovante de registro** | Emitido e assinado; dispensada a impressão no momento da marcação porque garantimos acesso eletrônico permanente com extração das **últimas 48 h** — em app e web |
| **AEJ** (Arquivo Eletrônico de Jornada) | Gerado pelo Programa de Tratamento. Substitui AFDT e ACJEF. Registros: cabeçalho, REPs utilizados, vínculos, horário contratual, marcações, matrícula eSocial do vínculo, ausências, **banco de horas**, identificação do PTRP e *trailer* |
| **Espelho de ponto** | Emissão oficial no fechamento, com todos os elementos exigidos |
| Vedações | Sem inserção de marcação falsa; jornada exige pares entrada/saída (sequência ímpar é inconsistência sinalizada, não corrigida silenciosamente); horas extras não geram marcação artificial |

> **Nota de implementação honesta:** o leiaute campo-a-campo do AFD e do AEJ deve ser conferido diretamente contra os anexos da Portaria 671/2021 no momento de codificar. A Fase 12 tem uma tarefa dedicada e bloqueante para essa conferência, com validação contra o validador oficial e contra AFDs reais de mercado — não vamos codificar de memória.

### 8.2 Estratégia de homologação

1. Fase 12 entrega os geradores.
2. Validação cruzada: comparar nosso AFD com o de um sistema já aceito no mercado, para o mesmo conjunto de marcações.
3. Assinatura com e-CNPJ A1 em ambiente de homologação.
4. Parecer de contador/advogado trabalhista da SEEG.
5. Registro INPI concluído → produção.

---

## 9. Relatórios

Referência: a plataforma VR/Pontomais oferece **mais de 20 relatórios gerenciais**, com o espelho de jornada tendo **30+ colunas configuráveis** e exportação em CSV, PDF e XLS. Nosso alvo é paridade e superação.

**Catálogo (24 relatórios):**

1. **Espelho de ponto oficial** (fechamento, com cabeçalho legal e assinatura)
2. **Jornada / espelho prévio** — 30+ colunas configuráveis (nome, matrícula, cargo, equipe, turno, gestor, horário previsto, H.P., H.T., normais, extras diurnas/noturnas por fator, intrajornada, sobreaviso, faltas, intervalos, horas faltantes, adicional noturno, crédito/débito DSR, banco de horas, pausas NR-17, feriados, motivos/observações, marcações)
3. **Banco de horas** — saldo, extrato, projeção de vencimento
4. **Horas extras** — por fator, por período, por centro de custo
5. **Adicional noturno**
6. **Absenteísmo** — índice, ranking, evolução
7. **Atrasos e saídas antecipadas**
8. **Faltas** (justificadas e injustificadas)
9. **Tempo real** — quem está trabalhando agora, por unidade
10. **Ocorrências e inconsistências** — marcação ímpar, sem par, fora de cerca, score de risco baixo
11. **Abonos e justificativas**
12. **Férias e afastamentos**
13. **Escalas** — previsto x realizado
14. **Violações de intrajornada**
15. **Violações de interjornada**
16. **Horas por centro de custo / projeto / cliente**
17. **Extrato para folha** (layout por parceiro de folha)
18. **Movimentação** — admissões, demissões, aniversariantes
19. **Auditoria** — quem alterou o quê, quando, de onde
20. **Dispositivos e canais** — uso por canal, terminais offline, apps desatualizados
21. **Custo de horas extras** (financeiro, com valor-hora)
22. **Produtividade / headcount por área**
23. **Arquivos fiscais** — AFD, AEJ, comprovantes, com histórico de geração e download
24. **LGPD** — acessos a dados sensíveis e solicitações de titular

Todos com: período, agrupamento, filtros compostos, colunas configuráveis e salvas por usuário, inclusão/exclusão de inativos, conversão para decimal, exportação **CSV / XLSX / PDF**, agendamento por e-mail e disponibilização via API.

**Dashboards:** RH (visão da empresa), gestor (visão da equipe), colaborador (visão própria), diretoria (custo e conformidade).

---

## 10. API pública e integrações

- **REST versionada** (`/v1`), especificada em **OpenAPI 3.1**, com portal de documentação interativo.
- **Autenticação:** OAuth 2.0 *client credentials* com escopos granulares + API keys para casos simples. Chaves por ambiente (sandbox/produção).
- **Recursos expostos:** colaboradores, contratos, jornadas, escalas, marcações (leitura e criação), apurações, banco de horas, solicitações, fechamentos, relatórios, arquivos fiscais.
- **Webhooks** com assinatura HMAC, retentativa exponencial e *dead letter*: `marcacao.criada`, `marcacao.suspeita`, `ajuste.solicitado`, `ajuste.aprovado`, `periodo.fechado`, `banco_horas.vencendo`, `colaborador.admitido/demitido`.
- **Idempotência** por `Idempotency-Key` em toda escrita.
- **Exportadores de folha:** Domínio (Thomson Reuters), Alterdata, TOTVS (RM / Protheus / Datasul), Senior, Sankhya, Questor, Fortes, Contmatic + layout genérico CSV configurável.
- **Importadores:** AFD de terceiros (para migração e para empresas com relógio legado), colaboradores via planilha, escalas via planilha.
- **SSO:** Google Workspace, Microsoft Entra ID, SAML 2.0.
- **eSocial:** matrícula de vínculo no AEJ; eventos S-2200/S-2230/S-2299 tratados como integração de leitura (o ponto não é o emissor).
- **Sandbox** com dados sintéticos para o parceiro testar sem tocar produção.

---

## 11. Arquitetura técnica

### 11.1 Stack

| Camada | Tecnologia | Por quê |
|---|---|---|
| API | **Python 3.12 + FastAPI + SQLAlchemy 2 + Alembic + Pydantic v2** | Mesmo padrão do Lave e Seeg; OpenAPI nativo; ecossistema pronto para o motor facial |
| Banco | **PostgreSQL 16** com RLS, particionamento mensal de `marcacoes` | Isolamento multi-tenant real; volume de marcações cresce linearmente |
| Fila / cache | **Redis 7 + ARQ** | Workers assíncronos para apuração, geração de AFD/AEJ, relatórios, webhooks |
| Objetos | **MinIO** (S3-compatível) | Fotos de captura, anexos, PDFs, AFD/AEJ e `.p7s` |
| Web | **Next.js 15 (App Router) + TypeScript + Tailwind v4 + shadcn/ui + TanStack Query** | Mesmo padrão dos projetos existentes |
| Mobile | **Flutter 3.2x + Riverpod + Drift (SQLite) + camera + ML Kit** | Decisão D2 |
| Facial | **`analise-facial-edge`** (InsightFace/ArcFace ONNX) como serviço interno `facial-svc` | Decisão D4 |
| Gateway de dispositivos | Serviço dedicado `device-gw` (FastAPI) | Fala Push/Monitor da Control iD; isolado para não derrubar a API principal |
| Proxy | **Traefik global existente** na VPS | Regra da casa: não subir outro proxy nas portas 80/443 |
| Observabilidade | OpenTelemetry + Prometheus + Grafana + Loki + Sentry | Rastreabilidade ponta a ponta |
| CI/CD | GitHub Actions → build → registry → deploy na VPS | `gh` já autenticado na VPS |

### 11.2 Topologia de deploy

```
Internet ──► Traefik (VPS, já existente)
              ├─ ponto.<dominio>            → web (Next.js)
              ├─ api.ponto.<dominio>        → api (FastAPI)
              ├─ dev.ponto.<dominio>        → device-gw (Push/Monitor Control iD)
              └─ docs.ponto.<dominio>       → portal OpenAPI

Rede interna Docker (/docker/ponto/):
   api ─ worker(ARQ) ─ scheduler ─ postgres ─ redis ─ minio ─ facial-svc ─ device-gw

LAN do cliente:
   iDFace ──(push HTTPS)──► dev.ponto.<dominio>
   [opcional] agente edge on-premise ──(mTLS)──► api
```

Ambientes: `dev` (local), `hml` (VPS, dados sintéticos), `prd` (VPS). Cliente SaaS acessa por subdomínio (`empresa.ponto.<dominio>`) ou domínio próprio (white label, fase futura).

### 11.3 Repositório

Monorepo privado **`ponto-eletronico`** em `henriquehmas-rgb` — monorepo é o que viabiliza contrato compartilhado entre N agentes paralelos.

```
ponto-eletronico/
├── packages/contracts/     # ⚠️ FONTE DA VERDADE — congelado na Fase 0
│   ├── openapi.yaml            # OpenAPI 3.1 completo
│   ├── schema.sql / models/    # modelo de dados canônico
│   ├── errors.yaml             # catálogo de erros
│   ├── events.yaml             # catálogo de eventos/webhooks
│   ├── design-tokens.json      # tokens de design
│   └── glossario.md            # domínio: marcação, tratamento, apuração...
├── apps/
│   ├── api/                # FastAPI
│   ├── worker/             # ARQ (apuração, arquivos, relatórios, webhooks)
│   ├── device-gw/          # Control iD push/monitor
│   ├── facial-svc/         # wrapper do analise-facial-edge
│   ├── web/                # Next.js
│   └── mobile/             # Flutter
├── infra/                  # docker-compose, Traefik labels, .env.example
├── docs/                   # ADRs, runbooks, pacotes de contexto de fase
└── tests/                  # e2e, carga, fixtures legais (AFD/AEJ de referência)
```

---

## 12. Design e experiência

O pedido foi explícito: *"sistema moderno, com layout e design de designer profissional"*. Isso é fase própria (F9a), com entregável de **design system**, não CSS improvisado.

**Direção visual:** interface densa mas respirável, apropriada para software de RH usado 8 h por dia — inspiração em Linear/Vercel/Height, não em ERP dos anos 2000.

- **Tokens:** escala tipográfica modular, grid de 8 pt, paleta neutra fria + um accent de marca, semânticos para estado (sucesso/atenção/erro/info), raios e sombras em 3 níveis.
- **Tema claro e escuro** desde o primeiro componente, não como remendo.
- **Componentes:** shadcn/ui como base, estendido com componentes de domínio — *timeline* de marcações do dia, cartão de saldo de banco, grade de escala, seletor de período, tabela de dados com colunas configuráveis e virtualização.
- **Dados visuais:** gráficos com paleta acessível validada (contraste AA em ambos os temas), sem *chartjunk*, tooltips consistentes, sparklines nos KPIs.
- **Mobile-first no portal do colaborador**, PWA instalável.
- **Acessibilidade WCAG 2.2 AA:** navegação por teclado, foco visível, leitores de tela, alvos de toque ≥ 44 px — relevante porque ponto é sistema de uso obrigatório por *todo* funcionário.
- **Microinterações com propósito:** confirmação de batida com feedback tátil/sonoro/visual inequívoco (o funcionário precisa ter certeza absoluta de que registrou).
- **Estados vazios, de carregamento e de erro** desenhados, não genéricos.

---

## 13. Qualidade e verificação

- **Testes:** unitários no motor de cálculo (o mais crítico), integração por módulo, e2e (Playwright no web, integration_test no Flutter), contrato (Schemathesis contra o OpenAPI), carga (k6).
- **Suíte legal de referência:** conjunto de cenários trabalhistas com resultado esperado calculado à mão e conferido por contador — 12x36 virando o mês, noturno com prorrogação, intrajornada suprimida, banco vencendo em feriado, admissão/demissão no meio do período. É o *golden dataset* do motor.
- **Cobertura mínima:** 90 % no motor de jornada/cálculo e nos geradores AFD/AEJ; 70 % no restante.
- **Gate de CI:** lint, tipos, testes, build de imagem, verificação de contrato, scan de segurança (Semgrep) e de dependências.
- **Nenhuma fase é dada como concluída sem os comandos de verificação rodando verde** — cada pacote de fase traz os comandos exatos.

---

## 14. Riscos e mitigações

| Risco | Impacto | Mitigação |
|---|---|---|
| Leiaute AFD/AEJ implementado errado | Alto — invalida o sistema na fiscalização | Fase 12 dedicada, conferência contra os anexos da Portaria, validação cruzada com AFD de sistema aceito, revisão de contador |
| Certificado ICP-Brasil / INPI atrasarem | Médio — trava só a homologação | Iniciar os dois processos na semana 1; código gera arquivo não assinado até chegar |
| Attestation reprovando celular legítimo | Alto — funcionário não consegue bater ponto | Score de confiança com política configurável + canal alternativo sempre disponível |
| Motor facial com falso negativo | Alto — mesma consequência | Fallback obrigatório (PIN + matrícula, cartão no terminal), limiar ajustável, reenrollment fácil |
| iDFace indisponível para teste | Médio | Simulador do protocolo Control iD (`device-gw` com modo fake) desenvolvido na Fase 6 |
| Complexidade do motor de cálculo subestimada | Alto — é onde projetos de ponto morrem | Fase 3 e 4 recebem o maior número de agentes e o golden dataset é escrito **antes** do código |
| Vazamento de biometria | Crítico — dado sensível LGPD | Edge processa, nuvem guarda vetor cifrado com chave separada, sem imagem crua, auditoria de todo acesso |
| Deriva de contexto entre agentes paralelos | Médio — retrabalho | Contratos congelados na Fase 0 + *ownership* exclusivo de arquivos por fase + worktree isolado |

---

## 15. O que fica fora da v1 (backlog explícito)

Registrado para não virar escopo silencioso: reconhecimento por impressão digital no app, controle de refeitório/vale-refeição, gestão de EPI, integração com catracas de terceiros além da Control iD, módulo de férias coletivas complexo, app para smartwatch, URA telefônica, marcação por Bluetooth beacon, white label com domínio próprio, billing/assinatura automática do SaaS, BI embarcado.

---

## 16. Resumo da execução

| Onda | Fases | Agentes na onda | O que sai |
|---|---|---|---|
| 0 | F0 | 2 | Contratos congelados, monorepo, infra |
| 1 | F1, F2, F9a | 8 | Auth/multi-tenant, cadastros, design system |
| 2 | F3, F5, F6 | 9 | Motor de jornada, ingestão + NSR, Control iD |
| 3 | F4, F7, F8, F9b | 16 | Banco de horas, app Flutter, web colaborador, painel |
| 4 | F10, F11, F12 | 11 | Workflows, relatórios, REP-P/AFD/AEJ |
| 5 | F13, F14, F15 | 10 | API pública, antifraude/LGPD, deploy e homologação |
| | **16 fases** | **56 slots de agente** | Sistema completo |

Detalhamento fase a fase, com pacote de contexto, *ownership* de arquivos, critérios de aceite e comandos de verificação: **[FASES-E-AGENTES.md](FASES-E-AGENTES.md)**.

---

## Fontes consultadas

- [Control iD — iDFace](https://www.controlid.com.br/controle-de-acesso/idface/)
- [Control iD — API Linha de Acesso (introdução)](https://www.controlid.com.br/docs/access-api-pt/)
- [Control iD — Exemplos de requisição](https://www.controlid.com.br/docs/access-api-pt/primeiros-passos/exemplos/)
- [VR / Pontomais — Controle de ponto](https://www.vr.com.br/lp/controle-de-ponto/)
- [VR / Pontomais — Relatório de Jornada (espelho de ponto)](https://materiais.vr.com.br/central-de-ajuda/relatorios-jornada-espelho-ponto/)
- [VR / Pontomais — Espelho de ponto (fechamento)](https://materiais.vr.com.br/central-de-ajuda/relatorios-fechamentos/)
- [VR / Pontomais — Extração de arquivos fiscais (AFD, AEJ, AFDT, ACJEF)](https://materiais.vr.com.br/central-de-ajuda/cancelou-o-sistema-veja-aqui-como-extrair-seus-arquivos-fiscais-afd-aej-afdt-acjef-e-relatorios/)
- [Gov.br — Perguntas e Respostas Portaria 671/2021 (REP)](https://www.gov.br/trabalho-e-emprego/pt-br/assuntos/inspecao-do-trabalho/fiscalizacao-do-trabalho/Perguntas%20e%20Respostas%20REP)
- [TOTVS — Portaria 671/2021](https://espacolegislacao.totvs.com/portaria-671/)
- [UsePonto — AFD e AEJ no ponto eletrônico](https://useponto.com.br/blog/afd-aej-ponto-eletronico)
- [Android Developers — Play Integrity API](https://developer.android.com/google/play/integrity/overview)
- [OWASP MASTG — Google Play Integrity API](https://mas.owasp.org/MASTG-KNOW-0035/)
- [Guia Trabalhista — Banco de horas: validade e requisitos](https://www.guiatrabalhista.com.br/tematicas/banco-horas.htm)
- [ConJur — Jornada de trabalho: prorrogação, compensação e banco de horas](https://www.conjur.com.br/2024-fev-08/jornada-de-trabalho-prorrogacao-compensacao-e-banco-de-horas/)
