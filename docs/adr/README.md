# Architecture Decision Records

Registro das decisões de arquitetura que moldam o Ponto Eletrônico. Um ADR
existe para responder, meses depois, à pergunta *"por que isso é assim?"* sem
depender de quem estava na sala.

## Formato

Todo ADR segue a mesma estrutura, nesta ordem:

| Seção | O que responde |
|---|---|
| **Contexto** | Qual é a força em jogo. Restrição legal, restrição técnica, risco de negócio |
| **Decisão** | O que foi decidido, na voz ativa e no presente do indicativo |
| **Alternativas consideradas** | O que foi descartado e **por quê**. Sem isso o ADR é propaganda, não registro |
| **Consequências** | O que passa a ser verdade, incluindo o que ficou pior |
| **Status** | `Proposto`, `Aceito`, `Substituído por ADR-NNN` ou `Descontinuado` |

## Regras

1. **ADR é imutável depois de aceito.** Mudou de ideia? Escreve um novo ADR que
   substitui o anterior e marca o antigo como `Substituído por ADR-NNN`. Editar
   um ADR aceito apaga a história, que é justamente o que o ADR existe para
   preservar.
2. **Numeração nunca é reaproveitada.**
3. **ADR não é documentação de uso.** Ele registra a decisão e o trade-off; o
   como-fazer vive no Pacote de Contexto de Fase (`docs/fases/`) e no contrato
   (`packages/contracts/`).
4. Mudança em `packages/contracts/` exige RFC (ver `docs/rfc/README.md`).
   A RFC aprovada normalmente **gera** um ADR novo.

## Índice

| ADR | Título | Status | Fases mais afetadas |
|---|---|---|---|
| [001](ADR-001-multi-tenancy-row-level-security.md) | Multi-tenancy com Row Level Security no PostgreSQL | Aceito | F1, F14 |
| [002](ADR-002-imutabilidade-marcacao-camada-tratamento.md) | Imutabilidade da marcação e camada de tratamento separada | Aceito | F5, F4, F10, F12 |
| [003](ADR-003-geracao-nsr-sequencial-sem-lacunas.md) | Geração de NSR sequencial sem lacunas sob concorrência | Aceito | F5, F12 |
| [004](ADR-004-recalculo-determinista-idempotente.md) | Estratégia de recálculo determinista e idempotente da apuração | Aceito | F3, F4, F10 |
| [005](ADR-005-versionamento-api-publica-depreciacao.md) | Versionamento da API pública e política de depreciação | Aceito | F0, F13 |
| [006](ADR-006-criptografia-ciclo-vida-template-biometrico.md) | Criptografia e ciclo de vida do template biométrico (LGPD) | Aceito | F2, F7, F14 |
| [007](ADR-007-offline-first-mobile-confianca-temporal.md) | Arquitetura offline-first do app mobile e confiança temporal | Aceito | F7, F5 |
| [008](ADR-008-score-confianca-antifraude.md) | Score de confiança antifraude em vez de bloqueio binário | Aceito | F14, F7, F8 |
| [009](ADR-009-worker-instala-apps-api-como-biblioteca.md) | Worker instala apps/api como biblioteca | Aceito | F4, F3, F10, F11 |
| [010](ADR-010-debito-tecnico-performance-recalculo-em-lote.md) | Débito técnico aceito: performance do recálculo em lote abaixo do alvo | Aceito | F4, F3, F10, F11 |
| [011](ADR-011-tratamento-afastamento-retroativo-sem-efeito-numerico.md) | Débito técnico aceito: `Tratamento` de categoria `afastamento` (retroativo) não altera a apuração | Aceito | F4, F10, F11, F12 |
| [012](ADR-012-formula-hash-registro-tipo-7-afd-nao-confirmada.md) | Débito técnico aceito: fórmula de concatenação do hash SHA-256 do registro tipo "7" do AFD não confirmada contra fonte primária suficiente | Aceito | F12 |
| [013](ADR-013-sso-app-compartilhado-vs-por-tenant.md) | SSO: app OAuth/OIDC compartilhado por aplicação (Google/Entra ID), configuração de confiança por tenant sem tabela nova | Aceito | F13 |
| [014](ADR-014-f14-antifraude-mobile-sem-f7.md) | F14 (antifraude/hardening/LGPD) prossegue sem F7; sinais nativo-móveis (attestation, RASP, mock location, certificate pinning) ficam pendentes até F7 existir | Aceito | F14, F7 |
