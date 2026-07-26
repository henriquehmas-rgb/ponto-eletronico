# F01-F02 — Relatório Consolidado de Verificação (3ª camada, pós-Onda 1)

> ## ADENDO DO ORQUESTRADOR — 26/07/2026 (pós-verificação)
>
> O achado crítico nº1 abaixo (`fn_resolve_tenant` quebrado para slug) foi
> **corrigido** logo após este relatório ser escrito, e a correção foi
> verificada de forma independente do que este relatório descreve. Registro
> aqui para quem ler este documento depois não confunda o veredito original
> (bloqueada) com o estado atual do repositório.
>
> **O que foi feito** (RFC-009,
> [`docs/rfc/RFC-009-fn-resolve-tenant-quebra-com-slug.md`](../rfc/RFC-009-fn-resolve-tenant-quebra-com-slug.md)):
> `fn_resolve_tenant` reescrita com `CASE WHEN` (a construção que o próprio
> manual do PostgreSQL documenta como segura para forçar ordem de avaliação,
> ao contrário do guard de `AND`/`OR` original) em `packages/contracts/schema.sql`
> e `apps/api/migrations/versions/0001_inicial.py`.
>
> **Como foi verificado, de forma independente do achado original:**
> - Reproduzi eu mesmo o bug primeiro (antes de corrigir), com SQL cru contra
>   o mesmo banco (`ponto_verificacao`) — confirmando que não era erro de
>   ambiente dos verificadores: a MESMA suíte que tinha rodado 100% verde para
>   mim horas antes voltou a falhar com os mesmos 19 failed/25 errors ao
>   rodar de novo, contra o mesmo banco, sem nenhuma mudança — prova de que o
>   bug é real e intermitente (dependente do plano de execução do Postgres),
>   não uma peculiaridade do agente verificador.
> - Apliquei a correção e testei 5 slugs + 1 UUID + 10 repetições do mesmo
>   slug (forçando a troca de plano *custom* para *genérico* que o Postgres
>   faz após a 5ª execução) — sem erro em nenhum caso.
> - Rodei `pytest tests/f1 tests/f2 tests/test_andaime.py -q` **três vezes
>   seguidas**, do zero, contra o mesmo banco (`ponto_verificacao`, role
>   restrita `ponto_verificacao_login`, sem `BYPASSRLS`) — **100% verde nas
>   três rodadas**, sem nenhum FAILED/ERROR.
> - Reexecutei o script `scratchpad/rfc008_check.py` (login real por slug +
>   sessão autenticada + `GET /v1/empresas/nao-e-um-uuid`): login `200`,
>   `PONTO-VAL-005` confirmado — a seção 6 da RFC-008, que a verificação
>   original não conseguiu confirmar por causa deste mesmo bug, agora se
>   sustenta com evidência real.
> - O achado nº2 (`mypy apps packages` não encontra config de nenhum app) foi
>   corrigido nos três invocadores (`ci.yml`, `Makefile`, `tasks.ps1` — cada um
>   passa a rodar `mypy` uma vez por diretório de app). Isso também explica
>   por completo os "301 erros" do achado nº2: rodando `cd apps/api && mypy`
>   (config correta descoberta), o resultado bate exatamente com o esperado —
>   1 erro pré-existente em `saude.py` — confirmando que os ~300 erros em
>   `tests/f2/pessoas/*.py` eram inteiramente artefato da config não
>   descoberta, não um problema adicional de tipagem a corrigir separadamente.
> - Achados nº3 (`ruff format` de `contrato.py`) e nº5 (E501 em
>   `test_andaime.py:199`) corrigidos (triviais).
> - Achados nº4 (código morto `PONTO-TEN-002`) e nº6 (ciclo de gestores sem
>   constraint de banco) permanecem em aberto, registrados em
>   `docs/backlog.md` para decisão futura — nenhum dos dois é bloqueante nem
>   tem exploração de segurança confirmada.
>
> **Veredito atualizado: F1 e F2 — concluídas.** O restante deste documento
> é mantido **sem alteração**, como registro histórico do que a verificação
> adversarial encontrou e de como chegou a esse veredito — não invalido o
> trabalho dos dois verificadores editando o corpo abaixo; a correção e sua
> prova ficam só neste adendo.



**Data:** 2026-07-26
**Agentes:** dois agentes de verificação independentes (F1 e F2), consolidados
por um terceiro agente que não escreveu nem verificou código diretamente —
apenas leu, cruzou e redigiu este relatório a partir dos JSONs estruturados
devolvidos por F1 e F2.
**Ambiente:** Windows 11, PowerShell/Git Bash, Postgres/Redis reais da VPS via
túnel SSH (`127.0.0.1:15432`/`127.0.0.1:16379`), role restrita
`ponto_verificacao_login` (sem `BYPASSRLS`) para os testes de tenancy/RLS e
role administrativa `ponto` para fixtures que criam schema/roles de teste.

---

## VEREDITO

**F1 — bloqueada.** **F2 — concluída com ressalvas.** **Onda 1 (F1+F2) —
bloqueada para produção, não bloqueada para prosseguir o desenvolvimento das
fases seguintes.**

O achado central desta rodada, confirmado **de forma independente por F1 e
F2** (dois agentes diferentes, dois métodos diferentes — SQL cru e HTTP
completo via `TestClient`), contradiz diretamente a alegação registrada no
contexto desta tarefa de que a suíte completa (`pytest tests/f1 tests/f2
tests/test_andaime.py -q`) rodou **100% verde** contra o Postgres real com a
role restrita: **não rodou.** `pytest tests/f1 -q` deu **26 passed, 19 failed,
25 errors** de 70 testes coletados. A causa raiz única é que
`fn_resolve_tenant` (RFC-004) lança `InvalidTextRepresentationError` para
**qualquer slug que não seja UUID** assim que a tabela `tenants` tem linhas
reais — ou seja, o caminho de resolução de tenant por slug, o mecanismo
**primário** documentado em `openapi.yaml` (cabeçalho `X-Tenant` ou
subdomínio), está quebrado em qualquer banco populado. Isso também refuta a
seção 6 da própria RFC-004, que afirma ter "verificado manualmente" que
`fn_resolve_tenant('tenant-a')` devolve a linha esperada — essa verificação,
se ocorreu, não reproduz mais hoje.

Isolado esse bug (44 dos 70 testes de `tests/f1/{autenticacao,tenancy}` falham
só por causa dele), o restante do trabalho de F1 e F2 se sustenta bem sob
verificação adversarial independente: RBAC (23/23), hash chain de auditoria,
matriz de perfis, escopo hierárquico, RFC-007 (importador ligado, 5.000 linhas
em 7.13s), RFC-008 (precedência de erro confirmada com sessão real), unicidade
de biometria/dispositivo (provada até por INSERT SQL cru contornando o
serviço), RLS cross-tenant em `colaboradores` e detecção de ciclo de gestores
em profundidade 3 resistiram a ataques de próprio punho dos dois verificadores.
`tests/f2` deu 168/168 e `tests/test_andaime.py` deu 14/14 nas duas rodadas —
essas suítes não dependem de `fn_resolve_tenant` com slug do mesmo jeito que
`tests/f1/{autenticacao,tenancy}` dependem.

Os gates de qualidade "oficiais" (`mypy apps packages` e
`ruff format --check apps packages tests`, rodados **da raiz do repo, exatamente
como o CI faz**) também não estão verdes hoje, por motivos distintos e menos
graves, detalhados abaixo.

---

## Achado crítico nº1 — `fn_resolve_tenant` quebrado para slug (bloqueia F1 e mancha F2)

**Severidade: crítica.**

**Arquivos:** `packages/contracts/schema.sql` (função `fn_resolve_tenant`,
implementação da RFC-004) e `apps/api/migrations/versions/0001_inicial.py`
(mesmo corpo replicado).

**O que acontece:** o guard da RFC-004 —
```sql
(p_slug ~ formato_uuid AND t.id = p_slug::uuid) OR (p_slug !~ formato_uuid AND t.slug = p_slug)
```
depende de curto-circuito de avaliação de `AND`/`OR` para nunca tentar
`p_slug::uuid` quando `p_slug` não bate com o formato de UUID. O PostgreSQL
**não garante** essa ordem de avaliação para expressões que não dependem de
coluna de tabela — é comportamento documentado do próprio planner, não
peculiaridade da instância desta VPS.

**Reproduzido de forma determinística e independente por ambos os
verificadores:**
- F1: 7 slugs distintos (`tenant-a`, `abc`, `xxx`, `tenant-b`, `foo-bar-baz`,
  `seeg`, e SQL literal sem bind, para descartar cache de plano do asyncpg) —
  100% falham com `InvalidTextRepresentationError: invalid input syntax for
  type uuid`; UUIDs reais funcionam 100% das vezes.
- F2: reproduzido via SQL cru (`psycopg` direto) e via **HTTP completo**
  (`TestClient(app)` batendo em `POST /v1/auth/login` de verdade, com
  usuário/perfil/permissão semeados) — resultado `503 PONTO-INT-003`, com
  traceback originando em `app/identidade/tenancy/resolucao.py:55`, dentro do
  `TenantMiddleware` real (`app/core/middleware.py:142`). Prova que o bug
  atinge o caminho de produção via asyncpg/SQLAlchemy, não só um driver
  síncrono de reprodução.

**Efeito prático:** qualquer cliente real (web, mobile, integração) que envie
`X-Tenant` como slug — o caso de uso mais comum e o documentado como primário
— recebe `503` em vez da resposta do contrato, em qualquer banco com tenants
populados. As fixtures de `tests/f1/conftest.py:288` e
`tests/f1/autenticacao/conftest.py` usam exatamente esse padrão (slug tipo
`tenant-a`/`f1a1-xxxx`), por isso 44/70 testes de `tests/f1/{autenticacao,tenancy}`
terminam em `FAILED`/`ERROR` — não por defeito de lógica de teste, mas porque a
própria montagem da fixture já quebra.

**Consequência sobre os critérios de aceite de F1** (ver tabela §Critérios de
F1 abaixo): critérios 1 (isolamento), 2 (catálogo RLS), 8 (anti-enumeração de
login) e a parte funcional do critério 10 (rotas responderem de fato, não só
existirem) não puderam ser confirmados pela suíte automatizada. F1 confirmou
manualmente, contornando o bug (usando UUID em vez de slug no `X-Tenant`), que
a **lógica** de reuso de refresh token (critério 3) está correta — o defeito é
só no caminho HTTP/fixture que depende de slug.

**Isto não é uma reabertura da RFC-004** — é a constatação de que a
implementação decidida e já aplicada não corresponde ao comportamento
verificado na seção 6 do próprio documento. Cabe ao orquestrador decidir a
correção (não é ownership de F1 nem de F2, e nenhum dos dois verificadores
tocou em `packages/contracts/schema.sql`). Opções de correção sugeridas por
ambos os verificadores: `CASE WHEN` explícito, validação do formato numa
sub-select/CTE materializada antes do cast, ou reescrever como função
PL/pgSQL com `IF`/`ELSE` real em vez de uma única `SQL STABLE` inline (que o
planner pode constant-fold).

---

## Veredito por fase

### F1 — Identidade, Multi-tenant (RLS) e RBAC/auditoria

**Veredito do verificador F1: bloqueada.**

| # | Critério | Atendido | Evidência (resumida) |
|---|---|---|---|
| 1 | Isolamento provado (API, ORM sem filtro, SQL direto) tenant A vs. B | Não | `pytest tests/f1/tenancy/test_isolamento.py -q` → 10 ERROR; fixture `contexto_f1` crasha em `fn_resolve_tenant` antes de exercitar qualquer asserção (achado crítico nº1) |
| 2 | Cobertura de RLS por catálogo (ENABLE+FORCE+policy) | Não | `pytest tests/f1/tenancy/test_catalogo_rls.py -q` → 2 ERROR, mesma causa raiz. O comportamento correto (RLS falha fechado) já foi provado uma vez em `docs/fases/F01-A2-prova-quebra-policy.md`, não reproduzido nesta rodada para não duplicar |
| 3 | Reuso de refresh token invalida a família inteira (PONTO-AUTH-005) | Sim | Suíte automática falha (mesma causa raiz), mas reproduzido manualmente com X-Tenant=UUID (script próprio): 3 rotações OK → reapresentar o 1º token → 401 PONTO-AUTH-005 → usar o último (legítimo) → 401 PONTO-AUTH-006 (sessão encerrada) — família inteira revogada, confirmado |
| 4 | Hash chain detecta remoção; app não remove (ERRCODE 42501) | Sim | `pytest tests/f1/rbac -q` → 23 passed (fixture de RBAC não depende de `fn_resolve_tenant` com slug); não reatacado adversarialmente por falta de janela |
| 5 | Sequência de auditoria sem buraco sob 100 escritas concorrentes | Sim | Coberto pelos mesmos 23 passed; não isolado/reexecutado à parte |
| 6 | Matriz perfil × endpoint (7 perfis, ≥1 operação por permissão) | Sim | Parte dos 23 passed (`test_matriz_perfis.py`) |
| 6.1 | Catálogo de 142 valores de `x-permissao` existem em `permissoes` | Sim | Parte dos 23 passed (`test_catalogo_permissoes.py`) |
| 7 | Escopo hierárquico distingue PONTO-PERM-001/002 | Sim | Parte dos 23 passed (`test_escopo_hierarquico.py`) |
| 8 | Login sem enumeração (senha errada vs. usuário inexistente) | Não | `test_senha_errada_e_usuario_inexistente_respondem_identico` FAILED, mesma causa raiz — não confirmável nem refutável nesta janela |
| 9 | Argon2id gravado; nenhum hash em log | Sim | Confirmado indiretamente (3 scripts próprios usaram `gerar_hash`/`argon2id` e logaram sucesso); sem auditoria exaustiva de todos os pontos de log |
| 10 | 29 operações fora do 501; inventário idêntico ao contrato | Não (funcionalmente) | `conferir_rotas.py` → 215/215 idêntico ao contrato (passa); mas rotas que dependem de resolução por slug (a maioria do fluxo real) devolvem 503 em vez do contrato — achado crítico nº1 |
| 11 | Nenhum segredo versionado | Sim | `git ls-files \| grep -iE "private.*\.pem$\|\.env$"` sem saída; verificação superficial |
| 12 | Contrato intacto | Não (literal) | `git status --short packages/contracts` mostra `openapi.yaml`/`schema.sql` modificados — esperado por RFC-004/RFC-007, não commitado ainda; não é achado novo |
| 13 | Todos os comandos da §8 verdes | Não | `conferir_rotas.py` OK; `ruff check` → 1 erro (E501 em `tests/test_andaime.py:199`); `ruff format --check` → `app/schemas/contrato.py` não formatado; `mypy apps packages` (raiz) → 301 erros (config não é encontrado a partir da raiz — ver achado nº4); `pytest tests/f1 -q` → 26 passed/19 failed/25 errors |

### F2 — Cadastros organizacionais e pessoas

**Veredito do verificador F2: concluída com ressalvas.**

| # | Critério | Atendido | Evidência (resumida) |
|---|---|---|---|
| 1 | CRUD completo conforme OpenAPI (58 operações, sem 501) | Sim | `conferir_rotas.py` → 215/215 idêntico ao contrato |
| 2 | CPF/CNPJ/PIS com dígito verificador, sequências repetidas | Sim | `pytest tests/f2 -q` (168/168) exercita `app/comum/documentos.py` |
| 3 | Geocerca (ponto+raio, polígono côncavo/tolerância/borda) | Sim | `test_geocerca.py` incluído nos 168 passed; 14 casos lidos, sem lacuna |
| 4 | Allowlist CIDR IPv4/IPv6 com escopo | Sim | `test_redes.py` (12 casos) incluído nos 168 passed |
| 5 | Template biométrico ilegível sem chave; AAD de outro colaborador falha | Sim | `test_cifra.py` (11 casos) — AES-256-GCM, AAD cruzado, adulteração de byte/tag |
| 6 | 1 credencial biométrica ativa/colaborador+modalidade; 1 dispositivo ativo/colaborador | Sim | Confirmado em dobro: suíte via serviço + INSERT SQL cru contornando o serviço bloqueado por `uq_biometrias_ativa`/`uq_dispositivo_vinculos_ativo` — prova que a invariante é do banco |
| 7 | Importador 5.000 colaboradores, relatório linha a linha, idempotente, <5min | Sim | `[cinco_mil] 5000 linhas, 50 erros, 7.13s (limite: 300s)` |
| 8 | Vínculos simultâneos em empresas diferentes aceitos; sobrepostos na mesma recusados | Sim | `test_contratos_vinculos.py` incluído nos 168 passed |
| 9 | Único gestor vigente por colaborador; ciclo recusado (PONTO-CONF-003) | Sim | Suíte cobre ciclo de 2 nós; verificação adversarial própria confirmou ciclo de profundidade 3 (A→B→C→A) recusado. Nota: o banco sozinho **não** impede ciclo (só a EXCLUDE de gestor imediato único) — detecção é 100% da aplicação, informativo |
| 10 | Eventos `colaborador.admitido/demitido`, `importacao.concluida` com envelope exato | Sim | `test_eventos.py`/`test_worker_tarefa.py` incluídos nos 168 passed |
| 11 | Toda rota com `Depends(exigir_permissao(...))` == `x-permissao` do contrato | Sim | Cruzamento estático (script próprio): 58 esperadas, 58 encontradas, 0 divergências |
| 12 | Nenhum segredo versionado (chave mestra de biometria só por env) | Sim | `grep PONTO_BIOMETRIA_CHAVE_MESTRA` só encontra o nome da variável |
| 13 | Contrato intacto | Não (literal) | `openapi.yaml`/`schema.sql` modificados por RFC-007/RFC-004, já decididas — não é regressão |
| 14 | Todos os comandos da §8 verdes | Não | `ruff check` 1 erro (mesma linha de F1); `ruff format --check` reprova `contrato.py`; `mypy apps packages` (raiz) 301 erros; escopo restrito a `app/` bate com o esperado (só `saude.py`) |

---

## Achados novos (consolidado, deduplicado entre F1 e F2)

### 1. CRÍTICO — `fn_resolve_tenant` quebrado para slug em banco populado
Ver seção dedicada acima. Confirmado independentemente por F1 e F2, com dois
métodos de reprodução diferentes cada. Contradiz a seção 6 da RFC-004 e a
premissa de "100% verde" registrada no contexto desta verificação.

### 2. ALTA — `mypy apps packages` (comando oficial do CI/§8) não reflete a configuração `strict` pretendida
**Arquivos:** ausência de `pyproject.toml`/`mypy.ini` na raiz do monorepo;
`apps/api/pyproject.toml` (`[tool.mypy]`, `strict=true`, excludes e
`ignore_missing_imports` para asyncpg/redis).

`mypy apps packages`, rodado **exatamente como CI/Makefile/tasks.ps1 fazem** (a
partir da raiz), imprime (`--verbose`) `Config File: Default` — nenhum
`pyproject.toml` é descoberto a partir da raiz, então a config de
`apps/api/pyproject.toml` nunca é carregada nessa invocação. Resultado: 301
erros em 5 arquivos (maioria falso-positivo de mypy 1.13.0 com campos Pydantic
opcionais com alias em testes de F2, confirmado por runtime que a construção
funciona; mais 2 erros de import-untyped de asyncpg que seriam suprimidos pelo
override). Quando o comando roda de dentro de `apps/api` com escopo `app`
apenas (onde o `pyproject.toml` correto é encontrado), o resultado bate
exatamente com o esperado (1 erro pré-existente em `app/routers/saude.py`).
Ambos os verificadores concluem, de forma independente, que **o comando
oficial do CI e o comando usado para validar informalmente durante o
desenvolvimento divergem hoje**, e que qualquer claim anterior de "mypy limpo"
provavelmente rodou o segundo, não o primeiro.

### 3. MÉDIA — `ruff format --check` reprova `app/schemas/contrato.py`
Arquivo gerado por `tools/gerar_do_contrato.py`, provavelmente regenerado pela
RFC-007 sem passar pelo passo de auto-formatação do gerador
(`formatar_com_ruff`, que o próprio gerador documenta pular silenciosamente se
o ruff não estiver disponível naquele ambiente de execução).

### 4. MÉDIA — Código morto: `verificar_tenant_do_cabecalho`/PONTO-TEN-002 nunca é chamado
**Arquivo:** `apps/api/app/identidade/autenticacao/tenant.py:92-109`. A função
que implementaria a divergência "tenant do token vs. tenant do cabeçalho"
existe, mas nenhum router a invoca (`grep` vazio em `app/routers/*.py`).
Testado o cenário real (token válido do tenant SEEG + cabeçalho `X-Tenant` de
outro tenant, em rota protegida): **não há vazamento** — o sistema responde
`401 PONTO-AUTH-002` porque a linha do usuário fica invisível sob RLS do
tenant errado, então a proteção existe, só que por efeito colateral de RLS, não
pelo mecanismo documentado (PONTO-TEN-002/403). Achado de consistência/dívida
técnica, não de segurança.

### 5. BAIXA — `ruff check` reprova `tests/test_andaime.py:199` (E501, 103 caracteres)
Ownership do orquestrador (edição da RFC-008), não de F1 nem F2, mas quebra o
gate hoje.

### 6. INFORMATIVO (não é defeito) — `colaborador_gestores` não tem defesa de ciclo no banco
Confirmado via INSERT SQL cru que o banco sozinho aceita um ciclo de
profundidade 3; a única `EXCLUDE` existente impede dois gestores imediatos
vigentes simultâneos, não ciclo. A detecção é 100% da aplicação
(`definir_gestor_colaborador`), que foi comprovada correta por ataque direto.
Registrado como ausência de defesa em profundidade, sem exploração encontrada.

### 7. Endpoint público de tenant (não é achado, registrado por transparência)
F1 testou `GET /v1/tenants/atual` com token de um tenant e `X-Tenant` de outro:
devolveu 200 com dados do tenant do cabeçalho. Investigado a fundo: a rota é
pública por contrato (sem `x-permissao`) e funciona até sem `Authorization`
nenhum — comportamento intencional, não vazamento de dado sensível (só
metadado de tenant: razão social, CNPJ, plano).

---

## Pendências conhecidas (cross-referenciadas com `docs/backlog.md` e RFCs)

As pendências abaixo **não são novas** — já estavam registradas antes desta
verificação e são citadas aqui só para não serem confundidas com achados
inéditos:

- `docs/backlog.md`, entrada `2026-07-25 | F1 / A2`: `GET/POST /v1/tenants`
  seguem `501` por decisão arquitetural (RBAC de suporte cross-tenant exige
  role de banco diferente) — não relacionado ao achado crítico nº1 desta
  rodada, embora ambos envolvam `fn_resolve_tenant`/tenancy.
- `docs/backlog.md`, entrada `2026-07-26 | F1 / A1`: `SessaoAtual.escopos`/
  `empresasVisiveis` não preenchidos — fora do ownership de A1, endereçado a
  F2/F13.
- `docs/backlog.md`, entrada `2026-07-26 | F1 / A1`: `dispositivoIdentificador`
  não resolvido a `dispositivos.id` real — aguardando F6.
- `docs/backlog.md`, entrada `2026-07-25 | F1 / A3`: N+1 em
  `listar_usuarios`/`listar_perfis` de `admin.py` — dívida de performance
  registrada, sem urgência.
- RFC-004 (decidida): resolução de tenant por UUID — implementada, mas ver
  **achado crítico nº1** acima: a implementação não corresponde ao
  comportamento que a própria RFC alega ter verificado para o caso de slug.
  **Este relatório não reabre a RFC-004**; registra que a verificação da
  seção 6 dela não reproduz mais e recomenda ao orquestrador tratar como
  correção urgente (nova RFC ou patch direto, a critério de quem decide).
- RFC-007 (decidida/implementada): `conteudoRef` em `ImportacaoCriar` —
  confirmado funcional por ambos os verificadores (F1 indiretamente via
  RBAC/rotas, F2 diretamente via `pytest tests/f2/importadores -k cinco_mil`).
- RFC-008 (decidida/implementada): precedência de erro de contexto sobre
  formato de path param — confirmado por F1 com sessão autenticada real
  (script próprio, `GET /v1/auditoria/{id inválido}` e
  `/v1/tenants/{id inválido}` → `400 PONTO-VAL-005`, não
  `PONTO-VAL-011`/`PONTO-AUTH-002`, confirmando a seção 6 da RFC).

### Pendências novas geradas por esta rodada de verificação

1. **Urgente (bloqueia produção/qualquer banco populado):** corrigir
   `fn_resolve_tenant` (`packages/contracts/schema.sql` e
   `apps/api/migrations/versions/0001_inicial.py`) para não depender de
   curto-circuito de `AND`/`OR` — por exemplo `CASE WHEN` explícito, validação
   de formato antes do cast via CTE materializada, ou reescrita como PL/pgSQL
   com `IF`/`ELSE` real. Depois da correção, **toda** a suíte
   `tests/f1/{autenticacao,tenancy}` precisa ser re-executada do zero contra
   Postgres real antes de qualquer novo claim de "100% verde".
2. Depois de corrigir o item 1, refazer a leitura dos critérios F1 1, 2, 8 e a
   parte funcional do 10 com a suíte automatizada real, não com scripts
   avulsos de contorno.
3. Decidir se `verificar_tenant_do_cabecalho`/PONTO-TEN-002 (código morto)
   deve ser removido ou efetivamente ligado a alguma rota, e se a divergência
   de código de erro observada (AUTH-002/401 em vez de TEN-002/403) é
   aceitável ou merece ajuste de contrato/RFC.
4. Investigar por que `mypy apps packages` (comando real do CI) e `mypy app`
   (de dentro de `apps/api`) divergem — criar um `mypy.ini`/`pyproject.toml`
   na raiz do monorepo, ou ajustar o invocador do CI para usar
   `--config-file` explícito, para que o gate reflita de fato a config
   `strict` pretendida.
5. Rodar `ruff format` sobre `apps/api/app/schemas/contrato.py` e encurtar a
   linha 199 de `apps/api/tests/test_andaime.py` (ownership do orquestrador).
6. Não houve tempo, em nenhuma das duas verificações, de reatacar
   isoladamente os critérios de hash chain/concorrência (F1, critérios 4/5)
   nem de auditar exaustivamente logs em busca de vazamento de hash (F1,
   critério 9) além do que já foi confirmado indiretamente.

---

## Nota de rastreabilidade

Este relatório não editou nenhum arquivo de código, `docs/backlog.md` nem
nenhuma RFC — é consolidação, em modo leitura, dos dois JSONs estruturados
devolvidos pelos verificadores independentes de F1 e F2. Toda evidência citada
acima é textual desses JSONs; nenhum comando foi re-executado por este agente
consolidador.
