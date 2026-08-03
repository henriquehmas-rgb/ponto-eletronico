# RFC-018 — SSO (Google Workspace, Microsoft Entra ID, SAML 2.0) não tem nenhuma superfície de contrato: nem caminho, nem tag, nem escopo OAuth

| | |
|---|---|
| **Status** | ✅ Decidida |
| **Autor** | F13 (PCF, escalado pelo orquestrador ao revisar antes do build) |
| **Data** | 2026-08-03 |
| **Fases impactadas** | F13 (Grupo SSO, 2 agentes do PCF) |
| **Artefatos de contrato afetados** | `packages/contracts/openapi.yaml` (tag nova, caminhos novos, schemas novos, possivelmente escopo OAuth novo). Nenhuma mudança em `schema.sql` — `credenciais.tipo='sso'`/`credenciais.provedor_sso`/`credenciais.identificador_externo` já modelam a identidade federada do lado do usuário; a configuração de confiança do provedor por tenant cabe em `tenant_configuracoes` sem tabela nova (ver §6) |
| **Bloqueia** | Todo o Grupo SSO do PCF de F13 — os dois agentes (OIDC e SAML) não têm onde pendurar rota nenhuma até esta RFC ser decidida |

## 1. O que está errado

`packages/contracts/schema.sql` já modela metade do problema: `credenciais.tipo` aceita `'sso'`,
`credenciais.provedor_sso` aceita `'google'`, `'entra_id'`, `'saml'`, `'okta'`, e
`credenciais.identificador_externo` guarda o subject/e-mail devolvido pelo provedor (comentário da coluna:
*"Subject ou e-mail retornado pelo provedor de SSO"*). Isso é a modelagem do **vínculo entre um usuário
já existente e uma identidade externa** — mas não existe:

1. **Nenhum caminho HTTP para iniciar ou concluir um login federado.** Busca exaustiva na tag `auth`
   (`packages/contracts/openapi.yaml:121-124`, a única tag cuja descrição sequer menciona "clientes de
   integração e emissão de token OAuth") confirma que ela cobre login por senha, MFA, refresh,
   logout/reautenticação, recuperação de senha, `POST /v1/auth/token` (client credentials) e sessões — nada
   de `redirect`, `callback`, `assertion` ou "SSO". Não existe `GET /v1/auth/sso/{provedor}/iniciar`, não
   existe `POST /v1/auth/sso/saml/acs` (Assertion Consumer Service), não existe nada equivalente.
2. **Nenhum lugar para configurar QUAL provedor um tenant confia.** `credenciais` guarda o vínculo
   *usuário × identidade externa*, não a confiança *tenant × provedor* (client ID OIDC, domínio do Google
   Workspace autorizado, tenant ID do Entra, metadata XML/certificado X.509 do IdP SAML). Não há tabela nem
   endpoint para isso.
3. **Nenhum escopo OAuth relacionado.** A lista completa de escopos em
   `components.securitySchemes.oauth2.flows.clientCredentials.scopes` (32 entradas) não tem nada como
   `sso:ler`/`sso:escrever` — irrelevante, aliás, porque SSO é login **humano** via navegador, não fluxo de
   máquina; mas confirma que ninguém modelou autorização administrativa para configurar SSO (`x-permissao`
   equivalente a `admin.configurar` talvez baste, a decidir).

## 2. Por que isto importa

Sem superfície de contrato, os dois agentes do Grupo SSO não têm `operationId`, schema de requisição/
resposta, nem código de erro para implementar contra — o próprio mecanismo anti-quebra-de-contexto do
projeto (`FASES-E-AGENTES.md` §1) para de funcionar, porque não há contrato para eles lerem. Diferente da
RFC-016/RFC-017 (extensão pequena e óbvia de um padrão já existente no mesmo contrato), **não existe
nenhum precedente de fluxo redirect-based em nenhuma outra tag** — toda a API é JSON síncrono
request/response; login federado é inerentemente um fluxo com redirecionamento de navegador,
estado/nonce anti-CSRF, e (no caso SAML) um POST de formulário HTML com XML assinado, não JSON. Isso não é
uma lacuna pequena: é uma decisão de desenho nova, com superfície de segurança real (redirect URI aberto,
validação de assinatura, replay de assertion).

## 3. Por que não decidi sozinho

Diferente das RFC-016/RFC-017 (mudança aditiva, pequena, seguindo padrão já estabelecido no próprio
contrato), esta é uma superfície **inteiramente nova**, com escolhas de protocolo genuínas (nome da tag,
formato do caminho de callback, se o fluxo é redirect HTML ou JSON-com-URL-de-redirecionamento para o SPA
resolver, onde a configuração por tenant vive) e consequência de segurança direta se a modelagem errar. O
próprio critério do protocolo de RFC (`docs/rfc/README.md` §1) — *"a resposta é óbvia o bastante"* — não se
aplica aqui: existem pelo menos três desenhos razoáveis (ver §4) com trade-offs reais, e nenhum precedente
no próprio contrato para desempatar mecanicamente como aconteceu nas duas RFCs anteriores.

## 4. Opções

**(a) Tag `auth` estendida** com caminhos novos:
`GET /v1/auth/sso/{provedor}/iniciar` (redireciona ao IdP, `provedor` ∈ `google`|`entra_id`|`saml`),
`GET /v1/auth/sso/{provedor}/callback` (OIDC: recebe `code`/`state`; troca por token, resolve/cria
`credenciais`, emite os tokens de sessão do próprio sistema — mesmo par access/refresh que
`autenticar`/`renovarSessao` já emitem), `POST /v1/auth/sso/saml/acs` (SAML: recebe o `SAMLResponse` via
`POST` de formulário, formato distinto de JSON — precisa de `content: application/x-www-form-urlencoded`
ou multipart, exceção ao padrão do resto do contrato). Prós: reaproveita a tag que já é sobre
autenticação. Contras: mistura JSON request/response (todo o resto de `auth`) com redirect HTML/form-POST
(SSO), tornando a tag heterogênea.

**(b) Tag nova `sso`**, com os mesmos caminhos de (a) sob `/v1/sso/...` em vez de `/v1/auth/sso/...`, mais
`GET/POST /v1/admin/sso/provedores` (configuração por tenant: para OIDC, guarda só restrição de domínio/
tenant ID — client ID e client secret do Google/Entra são de **aplicação inteira**, não por tenant, ver §6;
para SAML, guarda `entityId`/`ssoUrl`/certificado X.509 do IdP, que são genuinamente por tenant). Prós:
isola a heterogeneidade de protocolo numa tag própria, deixando `auth` inteiramente JSON; mais fácil de
documentar no portal de desenvolvedor (F13/A2) como "recurso enterprise" separado. Contras: mais uma tag
no contrato (23 → 24).

**(c) Não expor SSO na OpenAPI pública — login federado só pela camada de sessão do `apps/web`**, sem
contrato JSON formal (o browser é redirecionado, a resposta final é um cookie de sessão, não um JSON
consumível por cliente de API). Reduz a superfície de contrato drasticamente, mas contradiz a premissa do
próprio PCF (F13 A3 do plano-base pede SSO como parte da API pública) e deixa o fluxo sem `operationId`/
`x-erros` documentados — perde justamente o benefício de "ninguém inventa contrato" para a parte mais
sensível a segurança do sistema.

## 5. Considerações que não decidem, mas informam a decisão

- **Confirmado por pesquisa (não fonte primária de protocolo, mas prática de mercado):** é padrão comum um
  SaaS B2B registrar **um único app OAuth/OIDC multi-tenant** no Google Workspace e no Microsoft Entra ID
  (client ID/secret de **aplicação**, não por tenant), restringindo por tenant só o domínio de e-mail
  aceito (Google) ou o `tenant_id`/`issuer` aceito (Entra) — o cliente por tenant só entra em planos
  enterprise que exigem app registration própria. Se essa prática for adotada, `credenciais.provedor_sso`
  resolve a identidade do USUÁRIO, e a única configuração POR TENANT necessária para OIDC é uma
  allowlist de domínio/tenant-id, que cabe em `tenant_configuracoes` (chave-valor JSON, já documentada como
  "parâmetros que não merecem coluna própria") — **sem precisar de tabela nova nem de segredo por tenant**.
- **SAML não tem equivalente de app compartilhado** — cada tenant configura o IdP próprio
  (`entityId`/`ssoUrl`/certificado X.509, todos **públicos por natureza**, não segredos: um certificado
  X.509 de assinatura é chave pública). Isso também cabe em `tenant_configuracoes` sem cifra nenhuma (ao
  contrário do segredo HMAC de webhook, que É secreto e usa o padrão `cifra.py` já estabelecido).
- Se a decisão confirmar o parágrafo acima, **nenhuma tabela nova é necessária em `schema.sql`** — a RFC
  fica restrita a `openapi.yaml`, o que simplifica a decisão e a implementação.

## 6. Recomendação (não vinculante — decisão fica com o orquestrador)

Opção **(b)** parece o melhor equilíbrio (tag própria isola a heterogeneidade de protocolo; documentação
do portal fica mais clara), mas esta RFC **não está decidida**: as duas alternativas de caminho (a/b) e a
pergunta de app-compartilhado-vs-por-tenant em §5 têm peso de decisão de produto (o que a SEEG quer
oferecer no dia 1: SSO "básico" com app compartilhado, ou já com app registration própria por cliente
enterprise?) que este documento não deve resolver sozinho.

## 7. O que NÃO é divergência

`credenciais.tipo='sso'`/`provedor_sso`/`identificador_externo` já modelam corretamente o vínculo
usuário×identidade externa e não precisam mudar em nenhuma das opções acima.

---

## Decisão do orquestrador — 03/08/2026

| # | Decisão | Justificativa |
|---|---|---|
| 1 | Opção **(b)**: tag nova `sso`, caminhos sob `/v1/sso/...` (`GET /v1/sso/{provedor}/iniciar`, `GET /v1/sso/{provedor}/callback` para `google`/`entra_id`; `POST /v1/sso/saml/acs`, `content: application/x-www-form-urlencoded`, único caminho do contrato inteiro fora de JSON — documentar essa exceção explicitamente na descrição da operação) mais `GET/PUT /v1/admin/sso/provedores` (configuração por tenant). Login federado emite o mesmo par access/refresh que `autenticar`/`renovarSessao` (F1) já emitem — SSO é uma FORMA alternativa de autenticar, nunca um mecanismo de sessão paralelo. | Isola a heterogeneidade real de protocolo (redirect HTML/form-POST assinado em XML) da tag `auth`, que hoje é inteiramente JSON síncrono; mais fácil de documentar no portal de desenvolvedor (F13/A2) como capacidade separada. |
| 2 | **App OAuth/OIDC compartilhado de aplicação para Google Workspace e Microsoft Entra ID** (um client ID/secret só, gerido como segredo de infraestrutura da SEEG — mesmo padrão de segredo de processo já usado para `client_secret` do OAuth interno, nunca por tenant). A configuração POR TENANT para esses dois provedores é só uma allowlist de domínio de e-mail (Google) ou `tenant_id`/`issuer` aceito (Entra), guardada em `tenant_configuracoes` (chave `sso.google.dominios_permitidos`/`sso.entra_id.tenant_id`, sem tabela nova). **SAML não tem equivalente de app compartilhado**: cada tenant configura o IdP próprio (`entityId`/`ssoUrl`/certificado X.509 — dados públicos por natureza, nunca segredo), também em `tenant_configuracoes` (`sso.saml.entity_id`/`sso.saml.sso_url`/`sso.saml.certificado_x509`), sem cifra (o padrão `cifra.py` de F2/F6 é para segredo de verdade, não para chave pública de assinatura). | Resolve o caso de uso real do dia 1 (a própria SEEG e clientes SaaS típicos autenticando via Google Workspace/Entra ID já existente da empresa) sem construir um fluxo completo de "app registration por tenant" que hoje não tem cliente esperando por ele — mesmo raciocínio de "não construir para hipótese futura sem necessidade concreta" já aplicado a WhatsApp/OpaSuite em F10. Não fecha a porta para SSO enterprise por tenant depois: `credenciais.provedor_sso`/`identificador_externo` (schema já existente) já modelam a identidade de forma genérica o bastante para essa evolução ser aditiva, não uma reescrita. |
| 3 | **Nenhuma tabela nova em `schema.sql`.** `tenant_configuracoes` (chave-valor JSON, já documentada como "parâmetros que não merecem coluna própria") guarda toda a configuração por tenant dos três provedores; `credenciais` (já existente) guarda o vínculo usuário×identidade externa. | Confirmado lendo `tenant_configuracoes` (schema.sql:230-253): é exatamente o mecanismo que a RFC já antecipava em §5 — nenhuma migration nova necessária, menor mudança possível de contrato. |
| 4 | `x-permissao: admin.configurar` para `GET/PUT /v1/admin/sso/provedores` (reaproveita a ação já liberada pela RFC-002, não cria `x-permissao` nova). Callback/ACS (`iniciar`/`callback`/`acs`) não exigem `exigir_permissao` normal — são endpoints de fluxo de autenticação, acessíveis antes de existir sessão, mesma categoria de `POST /v1/auth/login` (proteção é validação de `state`/assinatura de assertion, não RBAC). | Consistente com o padrão de permissão administrativa já usado pelo resto da tag `admin`; documenta explicitamente por que os três caminhos de fluxo não seguem o padrão geral de `Depends(exigir_permissao(...))`. |
| 5 | Este ADR-013 novo (`docs/adr/ADR-013-sso-app-compartilhado-vs-por-tenant.md`) registra a arquitetura resultante — a RFC registra o incidente de contrato, o ADR registra a decisão estrutural de longo prazo (protocolo §5 do `docs/rfc/README.md`). | Mesmo padrão que RFC-013→nada (não gerou ADR, era só padrão técnico) mas RFC-009→ADR implícito de F1 e RFC decisões estruturais anteriores já seguiram quando a decisão muda arquitetura de longo prazo, não só contrato pontual. |

**Nota de processo**: esta RFC foi corretamente deixada `Proposta` pelo agente que escreveu o PCF de F13
(reconheceu, com precisão, que é uma decisão de produto/segurança nova, não uma extensão pequena e óbvia de
padrão já existente — diferente de RFC-016/RFC-017, que o mesmo agente decidiu sozinho por engano; ver nota
equivalente nos dois arquivos). Revisão e decisão de verdade feitas pelo orquestrador nesta data, lendo o
schema real (`tenant_configuracoes`) antes de confirmar que a opção recomendada não precisa de tabela nova.
