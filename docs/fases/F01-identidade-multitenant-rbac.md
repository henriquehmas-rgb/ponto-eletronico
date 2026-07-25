# F01 — Identidade, Multi-tenant e RBAC

| | |
|---|---|
| **Onda** | 1 |
| **Agentes** | 3 · **A1** autenticação (senha, JWT, refresh rotativo, MFA, recuperação, sessões) · **A2** multi-tenancy e Row Level Security · **A3** RBAC, delegação e trilha de auditoria encadeada |
| **Duração estimada** | 5 dias |
| **Depende de** | F0 (contratos congelados e andaime da API) |
| **Criticidade** | Alta — F5, F8, F13 e F14 dependem desta fase; nenhuma fase posterior pode assumir isolamento de tenant sem ela |
| **Branch** | `f01-identidade-multitenant-rbac` |

---

## 1. Objetivo

Ao fim desta fase, **toda requisição à API é atribuída a um sujeito autenticado
e a um tenant, o PostgreSQL recusa por conta própria devolver linha de outro
tenant, cada operação exige a permissão declarada no contrato e toda escrita
deixa rastro numa trilha encadeada por hash cuja adulteração é detectável** —
enquanto as 29 operações das tags `auth`, `tenants`, `admin` e `auditoria`
respondem exatamente o que o `openapi.yaml` promete, no lugar do `501` de hoje.

## 2. Contexto mínimo

**O produto.** Este é um sistema de ponto eletrônico brasileiro do tipo
**REP-P** — *Registrador Eletrônico de Ponto via Programa*, a modalidade de
software prevista na Portaria MTP 671/2021. Ele é vendido como SaaS: uma única
instância atende vários clientes. Cada cliente é um **tenant**. Dentro de um
tenant existem uma ou mais **empresas** (cada uma com seu CNPJ), e dentro delas
**unidades**, **colaboradores** (as pessoas) e **vínculos** (a relação de
trabalho). Esta fase não implementa nada disso: implementa quem entra, sob qual
tenant, com quais poderes, e como isso fica registrado.

**Por que multi-tenancy aqui é questão legal e não de arquitetura.** Vazamento
de dado entre tenants não é bug de usabilidade: expõe dado pessoal de terceiro
sob a LGPD, gera dever de comunicação à ANPD e encerra comercialmente um produto
de RH. A decisão do projeto está no **ADR-001** e **você não pode redecidi-la**:
o isolamento é feito por **Row Level Security (RLS) nativo do PostgreSQL 16**,
em banco e schema únicos, **somado** ao filtro de aplicação — defesa em
profundidade, não substituição. Concretamente: toda tabela de domínio tem
`tenant_id UUID NOT NULL`, com `ENABLE ROW LEVEL SECURITY` **e**
`FORCE ROW LEVEL SECURITY` (o `FORCE` é o que impede até o dono da tabela de
escapar da política), e uma policy `pol_isolamento_tenant` que compara
`tenant_id` com `current_setting('app.tenant_id', true)`. A aplicação publica o
tenant abrindo cada transação com o equivalente a
`SET LOCAL app.tenant_id = '<uuid>'`. **`SET LOCAL`, e não `SET`**, porque a
conexão volta ao pool no fim da transação e não pode carregar o tenant da
requisição anterior. Sem o `SET`, `current_setting` devolve `NULL` e **nenhuma
linha é visível** — a falha é fechada, não aberta.

Duas exceções conscientes à regra "toda tabela tem `tenant_id`", ambas já
documentadas no glossário: **`tenants`** não tem, porque *é* o tenant (a policy
dela compara `id`), e **`permissoes`** não tem, porque é o catálogo global de
recursos e ações do produto, idêntico em todos os tenants e somente leitura para
a aplicação (`REVOKE INSERT, UPDATE, DELETE ON permissoes FROM ponto_app`). O
acesso cross-tenant do suporte da SEEG é feito pela role de banco
`ponto_suporte`, que tem `BYPASSRLS` e **não tem `SELECT` em
`biometria_templates`** — nunca por brecha na policy.

**Como o tenant é descoberto antes de existir sessão.** O cliente chega por
subdomínio (`empresa.ponto.<dominio>`) ou pelo cabeçalho `X-Tenant` (slug ou
UUID), obrigatório quando o host não identifica o tenant. Mas resolver o
subdomínio exige consultar a tabela `tenants`, que está sob RLS, e nesse momento
ainda não há `app.tenant_id`. Para isso existe, já no `schema.sql`, a função
`fn_resolve_tenant(p_slug TEXT)` em `SECURITY DEFINER`, que devolve apenas
quatro colunas (`id, slug, nome_exibicao, status`) — não há como enumerar a base
de clientes por ela. **Use essa função; não desabilite RLS para resolver
tenant.**

**Identidade não é pessoa.** `usuarios` é a identidade de acesso ao sistema;
`colaboradores` (fase F2) é a pessoa que trabalha. Nem todo colaborador tem
usuário — quem só bate ponto no terminal facial não precisa de login — e nem
todo usuário é colaborador (suporte da SEEG, contas de integração). A ligação é
a coluna opcional `usuarios.colaborador_id`. Os segredos de autenticação vivem
em `credenciais`, uma linha ativa por `tipo` (`senha`, `pin`, `certificado`,
`sso`, `recuperacao`), com `algoritmo` restrito por `CHECK` a
`argon2id|bcrypt|scrypt|pbkdf2|nenhum` — **use `argon2id`**, os demais existem
para migração de base legada. A coluna `hash` nunca guarda segredo em claro.
`credenciais.tentativas_falhas` e `credenciais.bloqueado_ate` são a base do
bloqueio progressivo, que responde `PONTO-AUTH-009` (HTTP 423).

**Sessão, refresh rotativo e detecção de reuso — o ponto mais fácil de errar.**
Uma **sessão** (`sessoes`) agrupa uma família de refresh tokens e é o que
permite revogação em massa por usuário ou por dispositivo. Cada
`refresh_tokens` guarda `familia_id` (a cadeia de rotação), `antecessor_id` (o
token que o originou), `token_hash` (SHA-256 — o valor em claro só existe no
cliente) e `usado_em`. A regra: **cada uso do refresh emite um token novo e
marca o anterior como usado**; se um token com `usado_em` preenchido for
apresentado de novo, isso caracteriza **reuso** e a resposta correta é
**invalidar a família inteira** (`motivo_revogacao = 'reuso_detectado'`,
`sessoes.motivo_encerramento = 'reuso_token'`) e responder `PONTO-AUTH-005`.
Invalidar só o token apresentado é o erro clássico: deixa o atacante com o token
válido e derruba a vítima. O access token é um **JWT assinado em RS256** de vida
curta (`bearerAuth` no contrato); a chave privada é montada em runtime a partir
de arquivo (`/run/secrets/jwt/private.pem` no compose) e **nunca é versionada**.

**Reautenticação é diferente de autenticação.** `sessoes.reautenticado_em`
existe porque bater ponto pela web exige reautenticação recente mesmo com sessão
válida (a operação é `POST /v1/auth/reautenticar`, e a falta dela responde
`PONTO-AUTH-011`). Quem consome isso é a F8; sua obrigação aqui é gravar o
carimbo e expô-lo.

**RBAC com escopo hierárquico.** O RBAC tem três níveis. `permissoes` é o
catálogo global, no formato `recurso.acao` (`marcacoes.ler`,
`fechamentos.reabrir`), com `acao` restrita por `CHECK` a
`ler|criar|editar|excluir|aprovar|exportar|executar|assinar|administrar`; a
coluna `sensivel` marca as permissões cujo exercício **obriga** uma linha em
`acessos_dados_sensiveis` (LGPD). `perfis` é o papel, por tenant — os de fábrica
são `super_admin`, `admin_empresa`, `rh`, `gestor`, `colaborador`, `auditor` e
`integracao`, semeados por `migrations/seed_dev.py`. `perfil_permissoes` liga os
dois, e uma linha com `concedida = false` **nega explicitamente** uma permissão
herdada de perfil de fábrica. O que torna isto não trivial é `usuario_perfis`:
a atribuição carrega **escopo** (`escopo_tipo` em
`tenant|empresa|unidade|departamento|equipe|proprio`, com a coluna
correspondente obrigatória por `CHECK`), o *flag* `incluir_subordinados` (que
faz o escopo descer pela árvore de departamentos e pela hierarquia de gestores
de `colaborador_gestores`) e **vigência** (`vigencia_inicio`, `vigencia_fim`). O
mesmo usuário pode ser gestor de uma unidade e colaborador comum no resto da
empresa. Permissão ausente responde `PONTO-PERM-001`; permissão presente mas
alvo fora da árvore do gestor responde `PONTO-PERM-002` — são erros distintos e
não devem ser confundidos.

**Delegação temporária.** `delegacoes` é o caso "o gestor saiu de férias": o
delegado herda o escopo do delegante entre `inicio_em` e `fim_em`, com `motivo`
obrigatório e uma constraint `EXCLUDE` que impede duas delegações vigentes
sobrepostas entre o mesmo par de usuários. **Toda ação exercida por delegação é
marcada como tal na auditoria** (`auditoria.delegacao_id`). Delegação inválida
ou expirada responde `PONTO-PERM-005`.

**Trilha de auditoria encadeada por hash.** `auditoria` é *append-only*: tem
gatilhos que abortam `UPDATE`, `DELETE` e `TRUNCATE` com `ERRCODE 42501`, e a
role `ponto_app` não recebe esses privilégios. Cada linha carrega `sequencia`
(única por tenant), `hash_anterior` e `hash_registro`, formando **uma cadeia por
tenant**: remover uma linha silenciosamente quebra a cadeia e é detectável. A
operação `POST /v1/auditoria/verificar-cadeia` existe para provar isso. Você
precisa fixar e documentar a fórmula do hash (quais campos entram, em que ordem,
com qual normalização) no código, porque o verificador e o gravador têm de
concordar para sempre — mudar a fórmula depois invalida a cadeia histórica.

**O que a Fase 0 já deixou pronto para você.** A API (`apps/api`) sobe, expõe as
215 operações do contrato como *stubs* que respondem `501` com
`PONTO-INT-005`, e o inventário de rotas é idêntico ao contrato. Existem:
`app/core/contexto.py` (propaga `request_id`, `tenant` e `usuario` por
`ContextVar`), `app/core/middleware.py` — cujo `TenantMiddleware` **já resolve**
o identificador do tenant do `X-Tenant` ou do subdomínio e o publica no
contexto, sem consultar o banco e sem validar nada, com o ponto de extensão
explicitamente reservado para você — e `app/db/sessao.py`, cuja função
`aplicar_tenant` já executa `SELECT set_config('app.tenant_id', :tenant, true)`
dentro da transação. `migrations/versions/0001_inicial.py` já cria as 92 tabelas,
182 índices, 21 gatilhos e as policies de RLS; `migrations/seed_dev.py` já semeia
1 tenant, o catálogo de permissões, os 7 perfis de fábrica e 1 usuário
administrador com senha vinda exclusivamente de `PONTO_SEED_ADMIN_SENHA`.

**Fase 0 é congelada.** `packages/contracts/` não se altera. Se o contrato
estiver errado, o caminho é `docs/rfc/` (protocolo em `docs/rfc/README.md`), não
o contorno.

## 3. Leituras obrigatórias (lista fechada)

Leia isto e pare. Não leia `PROJETO.md`, não leia outras fases, não leia o
código das fases vizinhas.

- `packages/contracts/openapi.yaml` — **apenas** as tags `auth`, `tenants`,
  `admin` e `auditoria` (29 operações + `GET /v1/admin/saude`, que já está
  implementada e você não toca). Leia também, em `components`:
  `securitySchemes` (`bearerAuth`, `oauth2`, `apiKeyAuth`), `parameters`
  (`CabecalhoTenant`, `CabecalhoRequestId`, `CabecalhoIdempotencia`),
  `responses` (`Erro400`..`Erro429`) e o schema `Problema`.
- `packages/contracts/schema.sql` — seções **2 (TENANCY)**, **4 (IDENTIDADE,
  ACESSO E RBAC)**, **19 (ROW LEVEL SECURITY)**, **20 (ROLES E PRIVILEGIOS)** e
  **21 (VERIFICACAO DO CONTRATO)**. Tabelas: `tenants`, `tenant_configuracoes`,
  `usuarios`, `credenciais`, `sessoes`, `refresh_tokens`, `mfa_dispositivos`,
  `perfis`, `permissoes`, `perfil_permissoes`, `usuario_perfis`, `delegacoes`,
  `auditoria`, `acessos_dados_sensiveis`, `api_clients`, `api_keys`,
  `oauth_tokens`. Funções: `app_tenant_atual()`, `app_usuario_atual()`,
  `fn_resolve_tenant(TEXT)`, `fn_registro_imutavel()`.
- `packages/contracts/models/tenancy.py`, `models/identidade.py`,
  `models/auditoria.py`, `models/integracao.py` (apenas `api_clients`,
  `api_keys`, `oauth_tokens`), `models/base.py`, `models/mixins.py`,
  `models/tipos.py`.
- `packages/contracts/errors.yaml` — categorias **AUTH** (13 códigos), **PERM**
  (6), **TEN** (5), e os transversais **VAL-001**, **VAL-005**, **VAL-011**,
  **IDEM-001..003**, **CONF-001..003**, **REC-001**, **RATE-001**,
  **INT-001..005**.
- `packages/contracts/glossario.md` — seções **1**, **1.1 (Isolamento por Row
  Level Security)** e **1.2 (Imutabilidade)**; verbetes **Delegação**,
  **Hash chain (trilha encadeada)**, **Perfil e permissão**, **Tenant**,
  **Usuário**, **Soft delete**; seção **3.2** (subseções `permissoes` sem
  `tenant_id`, `tenants` isolada por `id`, `criado_por` e `atualizado_por` sem
  chave estrangeira); seção **6 (Termos proibidos)**.
- `docs/adr/ADR-001-multi-tenancy-row-level-security.md` — **decisão fechada,
  não redecidir.**
- `docs/adr/ADR-005-versionamento-api-publica-depreciacao.md` — apenas para
  entender por que os caminhos são `/v1/...` e por que a forma do erro é
  `application/problem+json`.
- `apps/api/app/core/contexto.py`, `apps/api/app/core/middleware.py`,
  `apps/api/app/core/erros.py`, `apps/api/app/db/sessao.py` — o andaime que você
  vai preencher.
- `apps/api/migrations/seed_dev.py` — o que já é semeado, para não duplicar.
- `docs/rfc/README.md` — o protocolo, para o caso de o contrato estar errado.
- `docs/backlog.md` — onde anotar o que estiver fora do seu escopo.

## 4. Contratos

**Consome** — já existe, esta fase apenas usa:

- Tabelas e policies criadas por `apps/api/migrations/versions/0001_inicial.py`
  (as 92 tabelas, as policies `pol_isolamento_tenant`, as roles `ponto_app`,
  `ponto_leitura`, `ponto_suporte`).
- Funções SQL `app_tenant_atual()`, `app_usuario_atual()`,
  `fn_resolve_tenant(TEXT)`, `fn_registro_imutavel()`.
- Andaime da API: `app/core/contexto.py`, `app/core/erros.py`
  (`ErroDeAplicacao`, `RespostaProblema`, `RESPOSTAS_PADRAO`),
  `app/core/catalogo_erros.py` (os 112 códigos), `app/db/sessao.py`.
- Modelos SQLAlchemy do pacote `ponto_contracts`.
- Semeadura de `migrations/seed_dev.py` (tenant, permissões, 7 perfis, admin).

**Produz** — esta fase implementa:

*Endpoints (29 operações; hoje `501`):*

| Método | Caminho | `operationId` | Permissão exigida |
|---|---|---|---|
| POST | `/v1/auth/login` | `autenticar` | — (público) |
| POST | `/v1/auth/mfa/verificar` | `verificarSegundoFator` | — |
| POST | `/v1/auth/refresh` | `renovarSessao` | — |
| POST | `/v1/auth/logout` | `encerrarSessao` | — |
| POST | `/v1/auth/reautenticar` | `reautenticar` | — |
| POST | `/v1/auth/senha/recuperar` | `solicitarRecuperacaoSenha` | — |
| POST | `/v1/auth/senha/redefinir` | `redefinirSenha` | — |
| POST | `/v1/auth/token` | `emitirTokenOAuth` | — (client credentials) |
| GET | `/v1/auth/sessoes` | `listarSessoes` | `sessoes.ler` |
| DELETE | `/v1/auth/sessoes/{sessaoId}` | `revogarSessao` | `sessoes.excluir` |
| GET | `/v1/auth/sessao` | `obterSessaoAtual` | — |
| GET | `/v1/tenants/atual` | `obterTenantAtual` | — |
| GET | `/v1/tenants` | `listarTenants` | `tenants.ler` |
| POST | `/v1/tenants` | `criarTenant` | `tenants.criar` |
| GET | `/v1/tenants/{tenantId}` | `obterTenant` | `tenants.ler` |
| PATCH | `/v1/tenants/{tenantId}` | `atualizarTenant` | `tenants.editar` |
| GET | `/v1/tenants/{tenantId}/configuracoes` | `listarConfiguracoesTenant` | `tenants.ler` |
| PUT | `/v1/tenants/{tenantId}/configuracoes/{chave}` | `definirConfiguracaoTenant` | `tenants.configurar` |
| GET | `/v1/admin/usuarios` | `listarUsuarios` | `usuarios.ler` |
| POST | `/v1/admin/usuarios` | `criarUsuario` | `usuarios.criar` |
| PATCH | `/v1/admin/usuarios/{usuarioId}` | `atualizarUsuario` | `usuarios.editar` |
| GET | `/v1/admin/perfis` | `listarPerfis` | `perfis.ler` |
| POST | `/v1/admin/perfis` | `criarPerfil` | `perfis.criar` |
| GET | `/v1/admin/permissoes` | `listarPermissoes` | `permissoes.ler` |
| GET | `/v1/admin/api-clients` | `listarApiClients` | `api_clients.ler` |
| POST | `/v1/admin/api-clients` | `criarApiClient` | `api_clients.criar` |
| GET | `/v1/auditoria` | `listarAuditoria` | `auditoria.ler` |
| GET | `/v1/auditoria/{registroId}` | `obterRegistroAuditoria` | `auditoria.ler` |
| POST | `/v1/auditoria/verificar-cadeia` | `verificarCadeiaAuditoria` | `auditoria.executar` |

*Tabelas escritas:* `tenants`, `tenant_configuracoes`, `usuarios`,
`credenciais`, `sessoes`, `refresh_tokens`, `mfa_dispositivos`, `perfis`,
`perfil_permissoes`, `usuario_perfis`, `delegacoes`, `auditoria`,
`acessos_dados_sensiveis`, `api_clients`, `api_keys`, `oauth_tokens`.
`permissoes` é **somente leitura** (catálogo global; a role da aplicação não tem
`INSERT`/`UPDATE`/`DELETE` nela).

*Módulos internos publicados para outras fases:* `app/core/seguranca.py` — a
dependência de autenticação e autorização que **todas** as demais fases da API
importam (§5).

*Eventos publicados:* **nenhum.** Nenhum evento de `events.yaml` tem origem
nesta fase.

**Não toca** — é de outra fase, mesmo que pareça relacionado:

- `POST /v1/aprovacoes/delegacoes` e `GET /v1/aprovacoes/delegacoes`
  (`criarDelegacao`, `listarDelegacoes`) — a **API** de delegação é da **F10**;
  esta fase implementa a tabela `delegacoes`, o efeito da delegação na
  autorização e a marcação na auditoria, **não** os endpoints.
- Tags `empresas`, `unidades`, `organizacao`, `colaboradores`, `contratos`,
  `biometria`, `dispositivos` e as tabelas correspondentes (**F2**, rodando em
  paralelo).
- Tag `terminais` e tabelas `terminais`, `terminal_saude` (**F6**).
- Tag `lgpd`, tabelas `consentimentos`, `politicas_retencao`,
  `solicitacoes_titular` (**F14**). Você **escreve** em
  `acessos_dados_sensiveis` quando uma permissão `sensivel` é exercida, mas não
  implementa os endpoints de LGPD.
- Tags `webhooks` e `integracoes` (**F13**). Você cria `api_clients` e emite
  token OAuth; o portal público, os escopos em produção, o rate limit por
  cliente e os webhooks são da F13.
- Rate limiting, *hardening*, rotação de segredos, mTLS e revisão adversarial de
  RLS (**F14**). Implemente RLS corretamente; a verificação adversarial é lá.
- `packages/contracts/**` — **congelado**.
- `apps/web`, `apps/mobile`, `apps/worker`, `apps/device-gw`, `apps/facial-svc`.

## 5. Ownership de arquivos

Caminhos **exclusivos** desta fase. **F1, F2 e F9a rodam em paralelo**; nenhuma
outra fase escreve aqui, e você não escreve fora daqui.

| Agente | Caminhos |
|---|---|
| **A1** (autenticação) | `apps/api/app/identidade/autenticacao/**`<br>`apps/api/app/identidade/tokens/**`<br>`apps/api/app/identidade/mfa/**`<br>`apps/api/app/routers/auth.py`<br>`apps/api/tests/f1/autenticacao/**` |
| **A2** (multi-tenancy e RLS) | `apps/api/app/identidade/tenancy/**`<br>`apps/api/app/routers/tenants.py`<br>`apps/api/app/core/middleware.py`<br>`apps/api/app/db/sessao.py`<br>`apps/api/migrations/seed_dev.py`<br>`apps/api/tests/f1/tenancy/**` |
| **A3** (RBAC e auditoria) | `apps/api/app/identidade/rbac/**`<br>`apps/api/app/identidade/auditoria/**`<br>`apps/api/app/routers/admin.py`<br>`apps/api/app/routers/auditoria.py`<br>`apps/api/tests/f1/rbac/**` |

**Compartilhado dentro da fase** (exige combinação entre A1, A2 e A3):

| Caminho | Regra |
|---|---|
| `apps/api/app/identidade/__init__.py` | Criado por **A1** na T1, com uma docstring e nada mais. Ninguém acrescenta código aqui. |
| `apps/api/app/core/seguranca.py` | Criado por **A3** na T1 (ver abaixo). Depois disso, **só A3 edita.** |
| `apps/api/app/main.py` | Só **A2** edita, e só para registrar dependências e middleware novos. A1 e A3 pedem a A2. |
| `apps/api/tests/f1/conftest.py` | Só **A2** edita (é onde nasce a fixture de banco com dois tenants). |

**Compartilhado com a F2 — atenção, risco real de colisão:**

| Caminho | Regra de convivência |
|---|---|
| `apps/api/pyproject.toml` | Ambas as fases precisam acrescentar dependências. **Acrescente apenas dentro do seu bloco**, delimitado por `# --- F1 ---` e `# --- fim F1 ---` na lista `dependencies`, criando o bloco no fim da lista se ele não existir. **Nunca reordene, remova ou reformate linha existente.** Dependências previstas para a F1: `argon2-cffi`, `pyjwt[crypto]` (ou `joserfc`), `pyotp`, `cryptography`. |
| `apps/api/app/core/seguranca.py` | **Contrato entre F1 e F2.** A F2 codifica contra este módulo desde o dia 1 ("usa auth stub"). O conteúdo literal inicial está fixado nos dois PCFs e é idêntico; quem chegar primeiro cria o arquivo exatamente assim e **não altera mais**. A implementação real é da **F1/A3**, que substitui os corpos **sem mudar nenhuma assinatura pública**. Mudança de assinatura exige RFC. |

Conteúdo literal inicial de `apps/api/app/core/seguranca.py` (idêntico no PCF da
F2 — ajuste apenas o mínimo necessário para passar `ruff` e `mypy --strict`, sem
alterar nomes nem assinaturas):

```python
"""Autenticacao e autorizacao da API. CONTRATO ENTRE FASES.

As assinaturas publicas deste modulo estao fixadas nos PCFs da F1 e da F2 e
NAO mudam sem RFC. A implementacao real e da F1 (agente A3). Ate ela existir,
os corpos abaixo sao o "auth stub" com que a F2 trabalha em paralelo.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends


@dataclass(frozen=True, slots=True)
class Sujeito:
    """Quem esta chamando. A F1 preenche a partir do JWT validado."""

    usuario_id: UUID | None = None
    tenant_id: UUID | None = None
    email: str = ""
    perfis: tuple[str, ...] = ()
    permissoes: frozenset[str] = frozenset()
    delegacao_id: UUID | None = None
    autenticado: bool = False


async def obter_sujeito() -> Sujeito:
    """Dependencia FastAPI: o sujeito da requisicao corrente."""
    return Sujeito()


def exigir_permissao(codigo: str) -> Callable[..., Awaitable[Sujeito]]:
    """Fabrica de dependencia. `codigo` e o `x-permissao` da operacao."""

    async def _verificar(sujeito: Sujeito = Depends(obter_sujeito)) -> Sujeito:
        # Stub permissivo. A F1 levanta PONTO-PERM-001 quando faltar `codigo`.
        return sujeito

    return _verificar


def exigir_alcance(
    sujeito: Sujeito,
    *,
    empresa_id: UUID | None = None,
    unidade_id: UUID | None = None,
    departamento_id: UUID | None = None,
    equipe_id: UUID | None = None,
) -> None:
    """Alcance hierarquico. Stub: nao restringe.

    A F1 levanta PONTO-PERM-002 quando o alvo estiver fora da arvore do gestor.
    """
    return None
```

**Explicitamente fora do seu ownership** (não edite, nem "só para arrumar"):
`packages/contracts/**`, `apps/api/app/schemas/contrato.py` (gerado),
`apps/api/app/core/catalogo_erros.py`, `apps/api/app/core/erros.py`,
`apps/api/migrations/versions/**`, `apps/api/tests/test_andaime.py`,
`.github/workflows/**`, `infra/**`, `Makefile`, `tasks.ps1`, `apps/web/**`.

> **Nenhuma migration nova nesta fase.** `0001_inicial.py` já cria as 92
> tabelas, os 182 índices, os 21 gatilhos, as 11 domínios e as policies de RLS.
> Se você achar que precisa de uma migration, o contrato está errado: abra RFC.

## 6. Tarefas (T1..Tn)

### T1 — Módulo de segurança e fixture de dois tenants
**Agente:** A3 (módulo) e A2 (fixture) — **primeira tarefa da fase, nada começa antes**
**Descrição:** A3 cria `apps/api/app/core/seguranca.py` com o conteúdo literal
da §5 e comunica à F2 que já existe. A2 cria `apps/api/tests/f1/conftest.py` com
uma fixture que sobe um PostgreSQL 16 (via `docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml`),
aplica `alembic upgrade head`, semeia **dois** tenants distintos (`tenant-a`,
`tenant-b`) com um usuário e um dado de domínio cada, e conecta como a role
`ponto_app` (não como superusuário — superusuário não é afetado por RLS sem
`FORCE`, e conectar como dono mascara o defeito que o teste existe para achar).
**Pronto quando:** `pytest apps/api/tests/f1 -q` coleta e a fixture sobe e
derruba o banco sem erro; `ruff check` e `mypy` verdes sobre o arquivo novo.

### T2 — Resolução de tenant e ligação do RLS
**Agente:** A2
**Descrição:** Preencher o miolo do `TenantMiddleware`: resolver o slug ou UUID
do `X-Tenant`/subdomínio via `fn_resolve_tenant`, recusar tenant inexistente com
`PONTO-TEN-001` (404), tenant `suspenso`/`cancelado` com `PONTO-TEN-003` (403) e
divergência entre o tenant do token e o da requisição com `PONTO-TEN-002` (403).
Endurecer `app/db/sessao.py` para que **toda** transação publique
`app.tenant_id` e para que uma requisição sem tenant resolvido **não** abra
sessão de banco. Implementar `GET /v1/tenants/atual`.
**Pronto quando:** existe teste que, com `X-Tenant` ausente em rota que exige
tenant, recebe `PONTO-VAL-011`; com tenant inexistente, `PONTO-TEN-001`; e um
teste que consulta `current_setting('app.tenant_id')` dentro da transação da
requisição e encontra o UUID correto.

### T3 — Prova de isolamento entre tenants (critério central da fase)
**Agente:** A2
**Descrição:** Escrever o teste adversarial: autenticado no tenant A, tentar ler
dado do tenant B **por três caminhos** — (a) pela API, informando o `id` do
recurso do tenant B; (b) por consulta ORM sem filtro explícito de `tenant_id`;
(c) por **SQL direto** (`text("SELECT * FROM colaboradores")`) na mesma sessão.
Os três devem devolver zero linha ou `PONTO-REC-001`/`PONTO-TEN-004`, nunca dado
do tenant B. Repetir o caminho (c) para uma amostra de pelo menos 10 tabelas de
domínio distintas, e acrescentar um teste de catálogo que percorre
`pg_class`/`pg_policies` e falha se **qualquer** tabela com coluna `tenant_id`
estiver sem `relrowsecurity`, sem `relforcerowsecurity` ou sem a policy
`pol_isolamento_tenant`.
**Pronto quando:** os testes passam contra PostgreSQL 16 real conectado como
`ponto_app`, e passam a falhar se a policy de uma tabela for removida à mão
(prove isso uma vez e cole a saída no relatório).

### T4 — Senha, login e bloqueio progressivo
**Agente:** A1
**Descrição:** Hash **Argon2id** para `credenciais.tipo = 'senha'`, com
parâmetros documentados no código. `POST /v1/auth/login` com resposta
deliberadamente idêntica para "senha errada" e "usuário inexistente"
(`PONTO-AUTH-001`, 401 — o contrato exige isso para impedir enumeração de
contas). Contagem em `tentativas_falhas`, bloqueio progressivo gravado em
`bloqueado_ate` respondendo `PONTO-AUTH-009` (423). Usuário `bloqueado` ou
`inativo` responde `PONTO-AUTH-010`. Honrar
`credenciais.trocar_no_proximo_acesso`.
**Pronto quando:** teste prova que as duas falhas (senha errada e usuário
inexistente) produzem corpo e status byte a byte iguais; teste prova que o
bloqueio entra após N falhas e libera após `bloqueado_ate`.

### T5 — JWT RS256, sessão e refresh rotativo com detecção de reuso
**Agente:** A1
**Descrição:** Emitir access token JWT RS256 de vida curta, com chave privada
lida de arquivo apontado por variável de ambiente (**nunca literal no código,
nunca versionada**). Criar `sessoes` no login. Refresh rotativo: cada
`POST /v1/auth/refresh` emite token novo, preenche `usado_em` do anterior e
encadeia por `antecessor_id` dentro da mesma `familia_id`. Reapresentar token
com `usado_em` preenchido revoga **toda a família** (`reuso_detectado`) e
encerra a sessão (`reuso_token`), respondendo `PONTO-AUTH-005`. Implementar
`logout`, `listarSessoes`, `revogarSessao`, `obterSessaoAtual` e
`reautenticar` (carimba `sessoes.reautenticado_em`).
**Pronto quando:** existe teste que rotaciona três vezes, reapresenta o primeiro
token e verifica que **todos** os tokens da família ficaram revogados e que a
sessão foi encerrada com `motivo_encerramento = 'reuso_token'`.

### T6 — MFA TOTP e recuperação de senha
**Agente:** A1
**Descrição:** `mfa_dispositivos` com `tipo = 'totp'`: segredo cifrado em
AES-256-GCM com chave **externa ao banco** (`chave_id` referencia o cofre;
`segredo_cifrado` e `iv` guardam o resto), `confirmado_em` só após prova de
posse — **fator não confirmado não autentica**. Login com MFA exigido responde
`PONTO-AUTH-007` e continua em `POST /v1/auth/mfa/verificar`; código errado é
`PONTO-AUTH-008`. Códigos de backup de uso único (`tipo = 'codigos_backup'`).
Recuperação de senha por credencial `tipo = 'recuperacao'`, token de uso único
com expiração, resposta da solicitação **sempre igual** exista ou não o e-mail.
**Pronto quando:** teste com relógio controlado aceita o TOTP da janela corrente
e recusa o da janela anterior já usada; teste prova que código de backup não
serve duas vezes.

### T7 — OAuth client credentials e chaves de API
**Agente:** A1
**Descrição:** `POST /v1/auth/token` (grant `client_credentials`) validando
contra `api_clients`/`api_keys`, gravando em `oauth_tokens`, com escopos
granulares conforme `securitySchemes.oauth2.flows.clientCredentials.scopes` do
contrato. Credencial de cliente inválida responde `PONTO-AUTH-012`; chave de API
inválida ou revogada, `PONTO-AUTH-013`; escopo insuficiente, `PONTO-PERM-003`;
origem não permitida para o cliente, `PONTO-PERM-006`.
**Pronto quando:** teste obtém token com um escopo, chama operação que exige
outro e recebe `PONTO-PERM-003`. Segredo do cliente é devolvido **uma única
vez**, na criação, e o que fica no banco é hash.

### T8 — Catálogo de permissões, perfis e escopo hierárquico
**Agente:** A3

> **Leia isto antes de começar a T8.** Duas coisas já foram medidas e você não
> precisa descobrir de novo:
>
> 1. O `openapi.yaml` exige **142** valores distintos de `x-permissao`.
>    `migrations/seed_dev.py` gera 200 códigos a partir de 55 recursos, mas
>    **30 dos 142 não estão entre eles** — inclusive quatro de que **esta fase
>    precisa**: `tenants.ler`, `tenants.criar`, `tenants.editar` e
>    `auditoria.executar`. Completar o catálogo é sua tarefa; a lista dos 30
>    está em `docs/backlog.md`. Complete **os 30**, não só os seus: as fases
>    seguintes vão precisar deles e o catálogo é global.
> 2. **Quatro** dos 142 usavam ações que o `CHECK` de `permissoes.acao` recusava
>    (`configurar`, `reabrir`, `ler_sensivel`): `tenants.configurar` (**seu**,
>    usado por `definirConfiguracaoTenant`), `banco_horas.configurar`,
>    `fechamentos.reabrir` e `marcacoes.ler_sensivel`. Isso já foi decidido em
>    [RFC-002](../rfc/RFC-002-acoes-de-permissao-fora-do-check.md) (opção a): o
>    `CHECK` de `permissoes.acao` em `schema.sql`, na migration
>    `0001_inicial.py` e no model `identidade.py` agora aceita as três ações
>    novas. **`tenants.configurar` está desbloqueado** — implemente
>    `definirConfiguracaoTenant` normalmente, sem exceção nem pendência.

**Descrição:** Implementar `listarPermissoes` (somente leitura),
`listarPerfis`/`criarPerfil` (respeitando `perfis.sistema` — perfil de fábrica
não é excluível — e `somente_leitura`, que responde `PONTO-PERM-004` em
qualquer escrita), `listarUsuarios`/`criarUsuario`/`atualizarUsuario`. Resolver
a permissão efetiva do sujeito: união dos `perfil_permissoes` dos
`usuario_perfis` **vigentes**, com `concedida = false` negando explicitamente, e
o escopo (`escopo_tipo` + coluna correspondente + `incluir_subordinados`)
determinando o alcance. Preencher o corpo real de `exigir_permissao` e
`exigir_alcance` em `app/core/seguranca.py`, **sem alterar as assinaturas**.
**Pronto quando:** existe uma tabela de teste parametrizada perfil × operação
cobrindo os 7 perfis de fábrica contra pelo menos uma operação de cada
permissão exigida nesta fase, com resultado esperado explícito; e um teste em
que o gestor da unidade X recebe `PONTO-PERM-002` ao tentar alcançar um alvo da
unidade Y.

### T9 — Delegação temporária
**Agente:** A3
**Descrição:** Efeito da delegação na autorização: entre `inicio_em` e `fim_em`,
com `status` em (`agendada`,`ativa`), o delegado herda o escopo do delegante,
limitado pelo JSON de `delegacoes.escopo` quando presente. Fora da vigência,
revogada ou cancelada: `PONTO-PERM-005`. Toda ação exercida por delegação grava
`auditoria.delegacao_id`.
**Pronto quando:** teste prova que o delegado aprova dentro da janela, não
aprova fora dela, e que a linha de auditoria correspondente traz o
`delegacao_id`. (Os **endpoints** de delegação são da F10 — aqui a delegação é
criada direto na tabela pelo teste.)

### T10 — Trilha de auditoria encadeada por hash
**Agente:** A3
**Descrição:** Gravar em `auditoria` toda escrita e todo evento de identidade
(`login`, `logout`, `falha_login`, `criar`, `atualizar`, `excluir`, `revogar`,
`configurar`), com `sequencia` monotônica por tenant sob concorrência,
`hash_anterior`/`hash_registro` encadeados e `valor_anterior`/`valor_novo`/
`diferenca` em JSONB. Documentar a fórmula do hash no módulo. Implementar
`listarAuditoria`, `obterRegistroAuditoria` e `verificarCadeiaAuditoria`.
Gravar `acessos_dados_sensiveis` quando a permissão exercida tiver
`permissoes.sensivel = true`.
**Pronto quando:** o verificador acusa quebra depois de uma linha ser removida
por superusuário (a role da aplicação não consegue removê-la — prove isso
também, esperando `ERRCODE 42501`); e um teste de concorrência com 100 escritas
paralelas produz `sequencia` de 1 a 100 sem buraco e sem repetição.

### T11 — Semeadura de tenant e fechamento
**Agente:** A2
**Descrição:** Estender `migrations/seed_dev.py` para semear o **segundo**
tenant usado nos testes de isolamento, sem quebrar a idempotência nem a regra de
que a senha do administrador vem exclusivamente de `PONTO_SEED_ADMIN_SENHA`.
Rodar todos os comandos da §8 e colar a saída real no relatório da fase.
**Pronto quando:** `python migrations/seed_dev.py` roda duas vezes seguidas sem
erro e sem duplicar linha, e todos os comandos da §8 estão verdes com saída
colada.

## 7. Critérios de aceite

O relatório final responde item a item, com saída real colada.

1. **Isolamento provado.** Usuário autenticado no tenant A não lê dado do tenant
   B por nenhum dos três caminhos da T3, incluindo **SQL direto** na sessão da
   requisição, conectado como a role `ponto_app`.
2. **Cobertura de RLS provada por catálogo.** Um teste percorre o catálogo do
   PostgreSQL e falha se qualquer tabela com coluna `tenant_id` estiver sem
   `ENABLE`, sem `FORCE` ou sem a policy `pol_isolamento_tenant`. As exceções
   aceitas são exatamente duas: `tenants` (isolada por `id`) e `permissoes`
   (catálogo global).
3. **Reuso de refresh token invalida a família inteira**, encerra a sessão com
   `motivo_encerramento = 'reuso_token'` e responde `PONTO-AUTH-005`.
4. **Verificador de hash chain detecta remoção de linha** da auditoria; e a role
   da aplicação não consegue removê-la (`ERRCODE 42501`).
5. **`sequencia` da auditoria sem buraco** sob 100 escritas concorrentes.
6. **Matriz perfil × endpoint testada**: os 7 perfis de fábrica × pelo menos uma
   operação de cada permissão exigida nesta fase, com resultado esperado
   explícito por célula.
6.1. **Catálogo de permissões completo**: um teste percorre os 142 valores de
   `x-permissao` do `openapi.yaml` e afirma que cada um existe na tabela
   `permissoes`, sem exceção — a RFC-002 já foi decidida e as quatro ações que
   antes violavam o `CHECK` agora são aceitas.
7. **Escopo hierárquico distingue os dois erros**: permissão ausente responde
   `PONTO-PERM-001`; permissão presente com alvo fora da árvore responde
   `PONTO-PERM-002`.
8. **Login não permite enumeração**: senha errada e usuário inexistente produzem
   status e corpo idênticos.
9. **Argon2id** é o algoritmo gravado em `credenciais.algoritmo` para senha, e
   nenhum hash de senha aparece em log.
10. **As 29 operações** das tags `auth`, `tenants`, `admin` e `auditoria`
    deixaram de responder `501` e respondem conforme o `openapi.yaml`; o
    inventário de rotas continua idêntico ao contrato
    (`python tools/conferir_rotas.py`).
11. **Nenhum segredo versionado**: chave privada RS256, segredo TOTP e segredo
    de cliente OAuth vêm de variável de ambiente ou de arquivo montado; só
    `infra/.env.example` está no repositório.
12. **Contrato intacto**: `git status --short packages/contracts` vazio.
13. Todos os comandos da §8 verdes, com saída real colada no relatório.

## 8. Comandos de verificação

Rode a partir da **raiz do repositório**, salvo onde indicado. Windows usa
`.\tasks.ps1`; Linux/macOS usa `make`.

Subir o banco (necessário para os testes de RLS):

```bash
docker compose --env-file infra/.env.example -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d postgres redis
```

```powershell
.\tasks.ps1 up
```

Migrar e semear:

```bash
cd apps/api && alembic upgrade head && cd ../..
```

```bash
PONTO_SEED_ADMIN_SENHA='<defina no shell, nao versione>' python apps/api/migrations/seed_dev.py
```

```powershell
$env:PONTO_SEED_ADMIN_SENHA = '<defina no shell, nao versione>'; python apps\api\migrations\seed_dev.py
```

Lint, formatação e tipos (as versões são as fixadas no CI: ruff 0.7.4, mypy
1.13.0):

```bash
ruff check apps packages tests
ruff format --check apps packages tests
mypy apps packages
```

```powershell
.\tasks.ps1 lint
.\tasks.ps1 typecheck
```

**Saída esperada:** `All checks passed!`, `NN files already formatted`,
`Success: no issues found in NNN source files`.

Testes da fase, com cobertura:

```bash
cd apps/api && pytest tests/f1 -q --cov=app --cov-report=term-missing
```

**Saída esperada:** todos os testes passam; nenhum `xfail` e nenhum `skip` nos
testes de isolamento — teste de RLS pulado por falta de banco **não conta como
verde**.

Regressão do andaime da Fase 0 (não pode quebrar):

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

1. **Não edite `packages/contracts/`** — `openapi.yaml`, `schema.sql`,
   `models/`, `errors.yaml`, `events.yaml`, `design-tokens.json`,
   `glossario.md`. Divergência vira RFC em `docs/rfc/`, no formato de
   `docs/rfc/README.md`.
2. **Não crie código de erro novo.** Os 112 códigos de `errors.yaml` são o
   conjunto fechado. Se faltar um, é RFC.
3. **Não desabilite RLS, nem por um instante, nem em teste.** Nem
   `SET row_security = off`, nem conectar como superusuário ou como dono da
   tabela para "facilitar" a fixture, nem `BYPASSRLS` fora da role
   `ponto_suporte`. Teste de isolamento que roda como superusuário não prova
   nada.
4. **Não substitua RLS por filtro de aplicação**, nem argumente que o filtro
   basta. ADR-001 é decisão fechada; ambos coexistem.
5. **Não crie migration nova.** `0001_inicial.py` já cria tudo. Precisou de
   migration? O contrato está errado: RFC.
6. **Não versione segredo.** Nenhuma chave RS256, senha, segredo TOTP, segredo
   de cliente OAuth ou `.env` entra no repositório. Só `infra/.env.example`, com
   placeholders.
7. **Não implemente os endpoints de delegação** (`criarDelegacao`,
   `listarDelegacoes`) — são da **F10**. Aqui é a tabela e o efeito na
   autorização.
8. **Não toque em nada da F2**: `app/routers/{empresas,unidades,organizacao,colaboradores,contratos,biometria,dispositivos}.py`,
   `app/organizacao/**`, `app/pessoas/**`, `app/biometria/**` e as tabelas
   correspondentes. Elas estão sendo escritas **agora**, em paralelo.
9. **Não altere as assinaturas públicas de `app/core/seguranca.py`.** A F2 já
   está codificando contra elas. Preencha os corpos; mudança de assinatura é
   RFC.
10. **Não invalide só o token reapresentado** na detecção de reuso. É a família
    inteira. Este é o erro clássico e ele deixa o atacante dentro.
11. **Não faça a resposta de erro vazar regra de segurança**: usuário
    inexistente e senha errada respondem igual, e a solicitação de recuperação
    responde igual exista ou não o e-mail.
12. **Não escreva regra de negócio de outras fases** — jornada, marcação,
    apuração, banco de horas, relatórios. Achou algo fora do escopo? `docs/backlog.md`.
13. **Não declare a fase pronta sem rodar os comandos da §8 e colar a saída
    real.** "Deve funcionar" não é evidência.
