# ADR-014 — F14 (antifraude/hardening/LGPD) prossegue sem F7, sinais móveis nativos ficam pendentes

**Status:** Aceito · 03/08/2026
**Decisores:** Orquestrador (autorização do dono do produto: "pode continuar até finalizar", sessão de
fechamento da F13)
**Fases afetadas:** F14, F7 (herda a pendência quando for construída)

---

## Contexto

`FASES-E-AGENTES.md` declara F14 como dependente de F5, F7, F8 e F13. F7 (app mobile Flutter) está
adiada desde o início do projeto por falta do SDK Flutter neste ambiente de desenvolvimento — decisão já
registrada em memória de sessão, nunca revertida, confirmada de novo nesta sessão. F13 acabou de fechar
sem tocar em F7. Isso deixa F14 com uma dependência formalmente não satisfeita.

Lendo o escopo real de F14 (`FASES-E-AGENTES.md` §F14, ADR-008, `PROJETO.md` §7.1) contra o que essa
dependência realmente significa: **nem todo o escopo de F14 depende de F7 de verdade.**

`packages/contracts/schema.sql`/`openapi.yaml` já modelam desde a Fase 0 os campos que F14 consome —
`marcacoes_meta.score_confianca`/`attestation_veredito`/`mock_location`, `dispositivos.attestation_status`,
`exige_attestation`/`politica_mock_location` em `politicas_registro`, o schema `attestationToken` na
entrada de marcação — e o próprio ADR-008 já registra que **F7 e F8 são os PRODUTORES de sinal**, não
quem calcula ou decide (isso é F14, no servidor, por desenho: "o cliente coleta e reporta, nunca calcula
nem decide"). F8 (web colaborador + webcam) **já está construída e commitada** — geolocalização, IP,
BSSID (quando disponível ao navegador), prova de vida e similaridade facial via `analise-facial-edge` já
produzem sinal real hoje. Só os sinais **nativos de plataforma móvel** — veredito de Play Integrity/App
Attest, RASP (root/jailbreak/Magisk/Xposed/Frida/debugger/emulador), leitura de
`DEVELOPMENT_SETTINGS_ENABLED`/`ADB_ENABLED`, `Location.isMock`/`isFromMockProvider`, certificate pinning
— exigem código embarcado num app real (Flutter, F7) e, no caso de attestation, um app de verdade
registrado no Play Console/App Store Connect para gerar token verificável. Não há como simular isso de
forma que prove algo: é a mesma classe de lacuna que o e-CNPJ A1 (F12, "certificado confirmado
indisponível") e o certificado ICP-Brasil real — a máquina que consome o dado pode e deve ser construída e
testada; o dado de origem, não, porque a origem não existe.

## Decisão

**F14 prossegue com os quatro agentes do plano-base, com o escopo nativo-móvel explicitamente destacado
como PENDENTE (não como "concluído com simulação"), a ser fechado quando F7 for construída:**

1. **A1 (score de confiança).** Constrói o motor de composição completo por ADR-008 (pesos, três faixas,
   explicabilidade, mensagem que não vaza regra, sinal decisivo de recusa direta) e aplica sobre os sinais
   que **já existem de verdade hoje**: geolocalização/IP/CIDR, prova de vida e similaridade facial (F8/F6),
   coerência geográfica, velocidade impossível, reputação de dispositivo por histórico. Os campos de
   attestation/RASP/mock-location entram no motor com o mesmo peso e a mesma regra que o ADR já define,
   mas — como nenhum cliente real (F7) existe para popular `attestationToken`/`mockLocation` — esses
   sinais chegam como `nao_aplicavel`/`null` em todo tráfego desta fase, por construção, nunca por bug.
   Teste de unidade cobre a composição com esses sinais sintéticos (payload construído à mão, não gerado
   por SDK real), documentado como tal.
2. **A2 (hardening).** Tudo que é servidor/infra prossegue integralmente: rate limiting, proteção contra
   enumeração, revisão de RLS, gestão/rotação de segredos (exceto a KEK biométrica, já atribuída à F15
   pelo próprio ADR-006), mTLS `device-gw` ↔ `facial-svc`, Semgrep + CodeQL no CI. **Certificate pinning
   fica de fora**: pinning é, por definição, código dentro do binário do cliente — não existe artefato
   para pinar sem F7. Registrado como pendência de F7, não como item cortado.
3. **A3 (LGPD).** Integral, sem dependência de F7 — `apps/api/app/routers/lgpd.py` é stub de Fase 0
   pronto para a regra de negócio real; a criptografia de template biométrico já foi construída pela F2
   (ADR-006, `apps/api/app/biometria/cifra.py`, AES-256-GCM/HKDF confirmado por leitura de código).
4. **A4 (verificação adversarial).** Testa de verdade todo vetor que não exige um app móvel real: réplica
   de assinatura de payload offline, manipulação de relógio, cross-tenant, foto impressa/vídeo contra o
   motor facial (via canal web/terminal, que já existe), bypass de RLS. **Emulador e fake GPS via API
   nativa do dispositivo ficam fora** — testá-los de verdade exige o mesmo app que não existe.

O critério de aceite original ("relatório de pentest... nenhum vetor da lista adversarial passa") é
reinterpretado como: nenhum vetor **testável sem F7** passa. Os vetores nativo-móveis entram no backlog
de F7 com nota explícita apontando de volta para este ADR, não como "aceite cumprido por amostragem".

## Alternativas consideradas

**Esperar F7 para começar F14.** Descartado: bloquearia hardening/LGPD (que não dependem de F7 em nada)
por um prazo indefinido — o Flutter SDK não tem previsão de disponibilidade neste ambiente — e F14 é
⭐ Crítica, o tipo de fase que menos deveria ficar represada.

**Construir um app Flutter mínimo só para gerar sinais de teste.** Descartado: mesmo um app mínimo não
gera um veredito de Play Integrity/App Attest genuíno sem registro real no Play Console/App Store
Connect (contas de desenvolvedor, processo de revisão) — o esforço de contornar a ausência do SDK seria
maior que o de simplesmente aguardar F7, e o resultado ainda não seria uma prova real, só outra simulação
com mais peças.

**Simular os sinais nativos com dados fabricados e marcar como testado.** Descartado por desonestidade —
mesmo padrão já rejeitado pelo ADR-011/ADR-012: dívida técnica documentada é aceitável, alegar cobertura
que não existe não é.

## Consequências

**Positivas.** F14 entrega hoje o motor de score completo, operável e testado sobre sinal real de web/
terminal, mais hardening e LGPD inteiros — nenhum desses depende de F7 para ter valor de produção
imediato (a SEEG já usa F8/F6 hoje). O motor está pronto para receber sinal móvel real no dia em que F7
existir, sem redesenho.

**Negativas e mitigações.** (a) O critério de aceite "nenhum vetor da lista adversarial passa" fica
formalmente incompleto até F7 existir — mitigado por este ADR ser referenciado explicitamente no PCF de
F7 como item de fechamento obrigatório, não uma nota perdida. (b) Um app móvel real pode revelar que o
motor de composição precisa de ajuste de peso ao ver sinal real pela primeira vez (mesmo risco que
qualquer sistema calibrado sem dado de produção) — mitigado por ADR-008 já prever telemetria de
distribuição de score e recalibração como parte normal de operação, não como retrabalho. (c) Certificate
pinning ausente é uma superfície de MITM real contra o app quando ele existir — mitigado por TLS comum já
proteger o transporte hoje (o pinning é defesa em profundidade contra certificado raiz comprometido no
aparelho, não a única defesa).
