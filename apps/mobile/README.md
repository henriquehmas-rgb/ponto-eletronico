# apps/mobile — app Flutter (a ser criado na F7)

**Este diretório contém apenas este README.** O projeto Flutter ainda não
existe, e isso é deliberado.

## Por que o projeto não foi criado na Fase 0

Dois motivos, nesta ordem:

1. **Flutter não está instalado no ambiente de execução da Fase 0.** Verificado:
   `flutter` não está no `PATH` da máquina onde a fase foi construída. Rodar
   `flutter create` fora do SDK não é possível, e versionar um esqueleto
   escrito à mão seria pior que não ter nada — o `flutter create` gera projeto
   Android/iOS com `Gradle`, `CocoaPods`, `Info.plist`, ícones e assinatura, e
   qualquer aproximação manual quebraria na primeira build de verdade.
2. **A decisão do orquestrador na RFC-001 (D-01) foi explícita:** *"`apps/mobile`
   fica só com o `README.md` (Flutter não está instalado)"*.

Ao contrário de `apps/web`, `apps/device-gw` e `apps/facial-svc`, o app mobile
**não é referenciado por `infra/docker-compose.yml`** nem por nenhum job do CI.
Nada quebra por ele não existir hoje: não há `docker compose build mobile`, não
há `dockerfile: apps/mobile/Dockerfile`, e a matriz do job `docker` do CI só
inclui serviço cujo `Dockerfile` já existe.

---

## Comando exato de criação (F7, agente A1)

Pré-requisitos: Flutter 3.29+ (canal `stable`), Android SDK, e — para a build
iOS — macOS com Xcode 16+.

```bash
# A partir da RAIZ do monorepo. O diretorio `apps/mobile` já existe (contém este
# README), e o `flutter create .` aceita diretório não vazio.
cd apps/mobile

flutter create . \
  --project-name ponto \
  --org br.com.seeg \
  --description "SEEG Ponto - registro de ponto, espelho e banco de horas" \
  --platforms=android,ios \
  --template=app
```

Notas sobre cada opção, porque nenhuma é livre:

| Opção | Por quê |
|---|---|
| `--project-name ponto` | mesmo namespace neutro usado no resto do monorepo (`PROJETO.md` §1). Nome de pacote Dart não aceita hífen. |
| `--org br.com.seeg` | gera `br.com.seeg.ponto` como *application id* Android e *bundle id* iOS. **Mudar isso depois de publicar é impossível** — o *application id* é a identidade do app nas lojas. |
| `--platforms=android,ios` | sem `web`, `linux`, `macos` e `windows`: o portal do colaborador em navegador é a `apps/web` (Next.js), e um alvo web no Flutter só criaria duas implementações da mesma tela. |

Depois de criar, o `pubspec.yaml` gerado precisa ser ajustado antes do primeiro
commit: versão mínima de SDK, `flutter_lints`, e a lista de pacotes abaixo.

---

## Estrutura de diretórios prevista

Organização por **funcionalidade**, não por camada técnica: cada pasta de
`funcionalidades/` carrega a sua própria tela, estado e repositório. Em app de
ponto, as funcionalidades são bem separadas entre si e evoluem em ritmos
diferentes — a captura facial muda muito mais que o espelho do mês.

```
apps/mobile/
├── README.md                      ← este arquivo
├── pubspec.yaml
├── analysis_options.yaml          # lints; espelha o rigor do ruff/mypy do backend
├── android/  ios/                 # gerados pelo flutter create
├── assets/
│   ├── icones/
│   └── tokens/                    # design tokens da F9a (packages/contracts/design-tokens.json)
├── lib/
│   ├── main.dart
│   ├── app.dart                   # MaterialApp, rotas, tema
│   ├── nucleo/
│   │   ├── config/                # ambiente, URLs, flags
│   │   ├── rede/                  # cliente HTTP, certificate pinning, interceptadores
│   │   ├── erros/                 # tradução de `codigo` do errors.yaml para mensagem
│   │   ├── log/
│   │   └── tema/                  # tokens da F9a → ThemeData
│   ├── dados/
│   │   ├── local/                 # Drift: esquema, DAOs, migrações
│   │   ├── remoto/                # clientes gerados a partir do openapi.yaml
│   │   └── seguranca/             # keystore/enclave, HMAC, AES-GCM, contador monotônico
│   ├── funcionalidades/
│   │   ├── autenticacao/          # login, sessão, biometria do aparelho (local_auth)
│   │   ├── registro/              # a batida: câmera, prova de vida, GPS, offline
│   │   ├── espelho/               # espelho do mês, marcações do dia
│   │   ├── banco_horas/           # saldo, extrato, simulador
│   │   ├── solicitacoes/          # ajuste, abono, férias, com anexo
│   │   ├── comprovantes/          # últimas 48 h, disponível offline
│   │   ├── notificacoes/          # push
│   │   └── quiosque/              # modo tablet compartilhado (matrícula/PIN + facial)
│   └── compartilhado/             # widgets e utilitários usados por 3+ funcionalidades
└── test/
    ├── unidade/
    ├── widget/
    └── integracao/
```

---

## Pacotes previstos

Nenhum é opcional: cada um cobre um requisito explícito de `PROJETO.md` §3.2 e
§7.1 ou um critério de aceite da F7.

| Pacote | Para quê | Requisito que o exige |
|---|---|---|
| `flutter_riverpod` | estado da aplicação | F7/A1 — "estado (Riverpod)" |
| `drift` | banco local SQLite, com esquema e migrações tipadas | F7/A4 — fila offline |
| `camera` | captura de vídeo/foto para o registro facial | F7/A2 |
| `google_mlkit_face_detection` | detecção de rosto, olhos e pose **no dispositivo**, para o desafio ativo de prova de vida e o enquadramento | F7/A2 — "ML Kit, prova de vida" |
| `geolocator` | posição, precisão e **detecção de localização simulada** | F7/A3 — "mock location e apps de fake GPS" |
| `freerasp` | RASP: root, jailbreak, Magisk, Xposed, Frida, depurador, emulador, binário adulterado | F7/A3 — "RASP" |
| `local_auth` | biometria/PIN **do próprio aparelho**, para reautenticar antes de bater ponto | §7.1 — reautenticação |
| `flutter_secure_storage` | chaves e tokens no Keystore (Android) / Keychain-Secure Enclave (iOS) | F7/A4 — "chave no keystore/enclave" |

### Três distinções que costumam ser confundidas

**`local_auth` não é a prova de vida.** `local_auth` desbloqueia o app com a
biometria *do aparelho* (a mesma que abre o celular) e serve para reautenticar
antes da batida. A identificação do colaborador é outra coisa: acontece no
`facial-svc`, com modelo próprio, e é ela que responde "esta é a pessoa certa".
Confundir as duas seria aceitar que qualquer um com o celular desbloqueado bata
o ponto de outra pessoa.

**`google_mlkit_face_detection` não substitui o `facial-svc`.** O ML Kit roda no
dispositivo e responde "há um rosto, os olhos estão abertos, a pose está boa" —
é qualidade de captura e desafio ativo. O reconhecimento (comparação contra o
template) é sempre servidor: decisão que vale ponto não pode ser tomada em
código que o fraudador controla.

**`freerasp` e `geolocator` cobrem ameaças diferentes.** RASP olha para o
*ambiente* (aparelho comprometido, depurador acoplado); a checagem de
localização simulada olha para o *dado* (GPS falso com aparelho íntegro). Um
emulador com fake GPS aciona os dois — e o critério de aceite da F7 exige que
seja detectado e bloqueado conforme a política da empresa.

### Pacotes que virão do trabalho de outras fases

* **Attestation de plataforma** (Play Integrity no Android, App Attest /
  DeviceCheck no iOS) — F7/A3, com verificação **no servidor**. A escolha do
  pacote depende do desenho do endpoint de verificação e fica para a F7.
* **Notificações push** — F7/A5. O provedor ainda não está decidido, e a decisão
  interage com a infraestrutura da SEEG.
* **Cliente HTTP gerado a partir do `openapi.yaml`** — o contrato está congelado
  desde a F0, então o cliente pode ser gerado em vez de escrito à mão.

---

## O que a F7 recebe pronto da Fase 0

| Artefato | Onde | Para quê no app |
|---|---|---|
| `openapi.yaml` (215 operações, congelado) | `packages/contracts/` | gerar o cliente HTTP; nenhuma rota precisa ser adivinhada |
| `errors.yaml` (112 códigos) | `packages/contracts/` | o app traduz `codigo` → mensagem em português. **Nunca** exibe `title`/`detail` cru, e nunca inventa mensagem própria |
| `design-tokens.json` | `packages/contracts/` | tema e `ThemeData` (com a F9a) |
| `events.yaml` | `packages/contracts/` | nomes dos eventos que viram notificação |
| ADR-006 | `docs/adr/` | ciclo de vida do template biométrico: **imagem crua não é persistida** |
| ADR-007 | `docs/adr/` | offline-first e confiança temporal: HMAC por registro, contador monotônico, TTL de 72 h |
| ADR-008 | `docs/adr/` | score de confiança e antifraude |

Três regras do backend que moldam o app e não são negociáveis:

1. **O relógio do servidor é a verdade.** O horário do aparelho é evidência, e
   segue no registro offline para ser comparado — nunca para ser aceito.
2. **Marcação é imutável.** O app não edita nem apaga marcação; correção é
   `POST /v1/tratamentos`, em fluxo de solicitação.
3. **Toda escrita é idempotente.** `Idempotency-Key` é obrigatória em `POST`,
   `PUT`, `PATCH` e `DELETE` — e é o que faz a fila offline poder reenviar sem
   duplicar batida.

---

## Critérios de aceite da F7 (de `FASES-E-AGENTES.md`)

Registrados aqui porque decidem escolhas de arquitetura desde a primeira linha:

* build Android e iOS gerados em CI;
* bater ponto sem rede e sincronizar depois preserva o horário real e é
  sinalizado como offline;
* emulador com fake GPS é detectado e bloqueado conforme a política;
* celular com modo desenvolvedor ligado respeita a política da empresa
  (bloquear / sinalizar / permitir);
* foto impressa e vídeo em tela reprovam na prova de vida;
* comprovante das últimas 48 h disponível offline.
