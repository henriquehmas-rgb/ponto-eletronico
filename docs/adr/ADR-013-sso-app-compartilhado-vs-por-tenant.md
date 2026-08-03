# ADR-013 — SSO: app OAuth/OIDC compartilhado por aplicação (Google/Entra ID), configuração de confiança por tenant sem tabela nova

**Status:** Aceito · 03/08/2026
**Decisores:** Orquestrador, ao decidir a RFC-018 antes do build da F13 — decisão de arquitetura
de longo prazo derivada dessa RFC, registrada aqui separadamente porque muda o modelo de confiança
de identidade federada do produto, não só o contrato de uma fase
**Fases afetadas:** F13 (Grupo SSO, dois agentes — OIDC e SAML)

---

## Contexto

A RFC-018 (`docs/rfc/RFC-018-sso-sem-superficie-de-contrato.md`) identificou que SSO (Google
Workspace, Microsoft Entra ID, SAML 2.0) não tinha nenhuma superfície de contrato — nem tag, nem
caminho, nem schema. Ao decidir a forma do contrato, uma pergunta de arquitetura mais profunda
precisou de resposta: quando um tenant do SaaS quer login federado via Google Workspace ou Entra
ID, o sistema registra **um app OAuth/OIDC por tenant** (cada cliente cria seu próprio "app" no
Google Cloud Console / Azure AD, com client ID e client secret próprios) ou **um único app OAuth/OIDC
de aplicação**, compartilhado por todos os tenants, restringindo por tenant só o domínio de e-mail
ou `tenant_id`/`issuer` aceito?

Essa escolha muda o que existe em produção: quantos segredos o sistema guarda, quem os gerencia,
que fluxo de configuração o RH da SEEG (ou de um cliente futuro) precisa seguir para ativar SSO, e
o quanto de superfície administrativa (`GET/PUT /v1/admin/sso/provedores`) precisa existir no dia 1.

## Decisão

**App OAuth/OIDC de aplicação, único e compartilhado, para Google Workspace e Microsoft Entra ID.
SAML 2.0 não tem equivalente — cada tenant configura seu próprio Identity Provider.**

1. Um único `client_id`/`client_secret` OAuth/OIDC por provedor (Google, Entra ID), gerido como
   segredo de infraestrutura da SEEG (mesma classe de segredo que o `client_secret` do OAuth interno
   já usa — nunca por tenant, nunca na tabela `tenant_configuracoes`, que é para dado não-secreto ou
   dado de confiança pública).
2. A configuração POR TENANT para esses dois provedores é só uma allowlist: domínio de e-mail
   aceito (Google — `sso.google.dominios_permitidos`) ou `tenant_id`/`issuer` do Entra aceito
   (`sso.entra_id.tenant_id`), guardada em `tenant_configuracoes` (chave-valor JSON, já existente,
   sem tabela nova).
3. **SAML é estruturalmente diferente e não usa este modelo.** Não existe "app SAML compartilhado"
   — cada tenant tem seu próprio Identity Provider corporativo, identificado por `entityId`/`ssoUrl`/
   certificado X.509 de assinatura. Esses três dados são **públicos por natureza** (um certificado de
   assinatura é chave pública, não segredo), então também vivem em `tenant_configuracoes`
   (`sso.saml.entity_id`/`sso.saml.sso_url`/`sso.saml.certificado_x509`), sem cifra — o padrão
   `cifra.py` (F2/F6) é reservado para segredo de verdade, não para chave pública.
4. `credenciais.tipo='sso'`/`provedor_sso`/`identificador_externo` (schema já existente desde antes
   desta RFC) continuam guardando o vínculo usuário×identidade externa, sem mudança — essa parte já
   estava certa.
5. **Nenhuma tabela nova em `schema.sql`.** Login federado emite o mesmo par access/refresh que
   `autenticar`/`renovarSessao` (F1) já emitem — SSO é uma forma alternativa de autenticar, nunca um
   mecanismo de sessão paralelo.

## Alternativas consideradas

**App registration próprio por tenant (client ID/secret individuais no Google/Entra).** É o modelo
mais comum entre fornecedores enterprise maduros (permite ao cliente restringir exatamente quais
apps têm acesso ao workspace dele, sem depender de confiar no app compartilhado de um fornecedor
terceiro). Descartada **para o dia 1**: exige um fluxo administrativo completo de "o RH do tenant
cria um app no console do Google/Azure e cola client ID/secret aqui", gestão seguro de N segredos
por tenant (não só 2 de aplicação), e não há hoje nenhum cliente concreto pedindo esse nível de
isolamento — mesmo raciocínio já aplicado a WhatsApp/OpaSuite (RFC/decisão de F10): não construir
para uma necessidade hipotética futura sem cliente esperando por ela agora. **Não fecha a porta**:
o schema (`credenciais`) já é genérico o bastante para essa evolução ser aditiva (uma tabela nova de
"app registrations por tenant" no futuro, sem mudar como `credenciais` funciona), não uma reescrita.

**Não expor SSO na API pública, resolver só na camada de sessão do `apps/web`.** Rejeitada pela
própria RFC-018 (opção c): contradiz a premissa do PCF de F13 (SSO como parte da API pública) e
perde a documentação/`x-erros` formal justamente na parte mais sensível a segurança do sistema.

## Consequências

**Positivas.** F13 entrega SSO funcional para o caso de uso real do dia 1 (SEEG e clientes SaaS
típicos autenticando via Google Workspace/Entra ID já existente da empresa) sem construir
infraestrutura de app-registration-por-tenant que não tem consumidor ainda. Configuração por tenant
cabe inteiramente em `tenant_configuracoes`, sem migration nova.

**Negativas e mitigações.** (a) O app OAuth/OIDC compartilhado da SEEG precisa ser registrado nos
consoles do Google Cloud e do Azure AD antes de qualquer tenant conseguir usar SSO — é uma ação de
infraestrutura real, fora do código, que o dono do produto precisa executar (ou delegar) fora desta
sessão de desenvolvimento; até lá, os testes automatizados usam credenciais de teste/mock do
provedor, nunca um app real. (b) Um cliente enterprise que exija app registration próprio (política
de segurança corporativa que não aceita apps de terceiro com acesso amplo) não é atendido pelo
desenho do dia 1 — se isso virar requisito real, é uma fase/RFC futura que adiciona uma tabela de
app-registrations por tenant, sem quebrar o que existe. (c) SAML, por não ter app compartilhado,
exige que cada tenant configure seu IdP corretamente (UX de configuração fica sob responsabilidade
do agente que constrói `GET/PUT /v1/admin/sso/provedores`, F13) — testar contra um IdP SAML real de
terceiro não é possível sem um parceiro configurado; os testes automatizados usam um IdP de teste
(ex.: um Identity Provider SAML de referência open-source), documentado como tal.
