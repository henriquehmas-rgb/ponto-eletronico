# `packages/contracts` — Fonte da Verdade

> **Este diretório é congelado.** Somente a **Fase 0** escreve aqui.
> Qualquer mudança depois disso passa pelo protocolo de RFC descrito na seção 3.

---

## 1. O que é este diretório

Este é o **vocabulário comum** de todo o monorepo. O sistema é construído por
dezenas de agentes trabalhando em paralelo, e nenhum deles lê o projeto inteiro
— cada um lê exatamente duas coisas: **este diretório** e o Pacote de Contexto
da sua Fase (`docs/fases/FXX-nome.md`).

Isso só funciona enquanto o contrato for estável. Se o contrato muda sem
aviso, todo trabalho paralelo feito contra a versão anterior vira retrabalho
silencioso. Daí o congelamento.

### Arquivos

| Arquivo | O que define | Quem consome |
|---|---|---|
| `openapi.yaml` | OpenAPI 3.1 completo da API `/v1`: caminhos, schemas, parâmetros, respostas, escopos de segurança | api, web, mobile, device-gw, testes de contrato, portal de docs |
| `schema.sql` | Modelo de dados canônico: tabelas, colunas, tipos, chaves, índices, políticas de RLS, triggers | api, worker, migrations Alembic |
| `models/` | Modelos SQLAlchemy 2 correspondentes ao `schema.sql` | api, worker, scheduler, device-gw |
| `errors.yaml` | Catálogo de erros: código, categoria HTTP, mensagem canônica em pt-BR, se é retryable | api, web, mobile — mensagens de erro nunca são inventadas na ponta |
| `events.yaml` | Catálogo de eventos e webhooks: nome, payload, quando dispara | worker, integrações, F13 |
| `design-tokens.json` | Tokens de design: cor, tipografia, espaçamento, raio, sombra, semânticos de estado | web (F9a), mobile (F7) |
| `glossario.md` | Domínio em português: marcação, tratamento, apuração, NSR, AFD, AEJ, banco de horas, jornada, escala | todo mundo |

---

## 2. Regras

1. **Só a Fase 0 escreve aqui.** Concluída a Fase 0, o diretório está congelado.
2. **Ninguém contorna o contrato.** Se a API precisa de um campo que não está no
   `openapi.yaml`, o campo **não existe** — abre-se uma RFC. Adicionar o campo
   direto no código é como o sistema se desintegra: cada fase passa a ter a sua
   versão da verdade e a integração final não fecha.
3. **Erro vem do catálogo.** Nenhum serviço inventa string de erro. Se falta um
   erro, é RFC.
4. **Evento vem do catálogo.** O mesmo vale para webhooks.
5. **O contrato é a especificação, não a documentação.** Divergência entre
   `openapi.yaml` e implementação é **defeito da implementação** até que uma RFC
   diga o contrário. O CI roda `spectral lint` sobre o `openapi.yaml` e a Fase 13
   roda Schemathesis contra a API real.
6. **Português do Brasil** em nomes de domínio, descrições e no glossário.

---

## 3. Protocolo de RFC — quando o contrato está errado

Nenhum contrato nasce perfeito; descobrir defeito no contrato é resultado
esperado, não fracasso. O que não pode acontecer é o contorno silencioso.

Procedimento (conforme §1.3 de [FASES-E-AGENTES.md](../../FASES-E-AGENTES.md)):

1. **Pare a tarefa afetada.** As demais tarefas da fase continuam — só o que
   depende do trecho defeituoso trava.
2. **Escreva a RFC** em `docs/rfc/RFC-NNN-<slug>.md`, com quatro seções:
   - **O que está errado** — trecho exato do contrato (arquivo, caminho, linha).
   - **Por quê** — o que quebra ou o que fica impossível de implementar.
   - **Mudança proposta** — o diff pretendido, redigido como contrato, não como
     código.
   - **Fases impactadas** — quem já consome esse trecho e precisa ser notificado.
3. **O orquestrador decide.** Se aprovada, o orquestrador — e ninguém mais —
   atualiza `packages/contracts/` e **notifica todas as fases impactadas**.
4. **Nunca contorne em silêncio.**

`NNN` é sequencial e nunca reutilizado. RFC rejeitada continua no repositório
com o desfecho registrado: o histórico do porquê de uma decisão vale tanto
quanto a decisão.

### Quando abrir RFC e quando não abrir

| Situação | Ação |
|---|---|
| Campo obrigatório para a regra de negócio não existe no schema | **RFC** |
| Endpoint devolve um erro que não está no `errors.yaml` | **RFC** |
| Webhook precisa de um campo novo no payload | **RFC** |
| Typo em `description` que não muda semântica | **RFC** (trivial, aprovação rápida) |
| Você quer um endpoint auxiliar interno, não exposto na API pública | Sem RFC — é detalhe de implementação da sua fase, desde que não apareça em `/v1` |
| Você quer nomear uma variável interna diferente do contrato | Sem RFC — nomes internos são seus |

Critério prático: **atravessa a fronteira entre duas fases? Então é contrato.**

---

## 4. Verificação

```bash
# Lint do OpenAPI (bloqueante no CI)
npx @stoplight/spectral-cli lint packages/contracts/openapi.yaml --fail-severity=warn

# Sintaxe dos demais catálogos
python -c "import yaml,pathlib; [yaml.safe_load(p.read_text(encoding='utf-8')) for p in pathlib.Path('packages/contracts').glob('*.yaml')]; print('ok')"
```

O CI (`.github/workflows/ci.yml`, job `Contrato · spectral`) roda a mesma
verificação a cada push e PR.

---

## 5. Leituras

- [PROJETO.md](../../PROJETO.md) — especificação de produto e arquitetura
- [FASES-E-AGENTES.md](../../FASES-E-AGENTES.md) — §1 (mecanismo anti-quebra-de-contexto), §1.3 (RFC)
