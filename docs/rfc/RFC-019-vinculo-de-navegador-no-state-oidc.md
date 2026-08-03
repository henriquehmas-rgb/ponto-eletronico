# RFC-019 — `state` do OIDC precisa de vínculo com o navegador que iniciou o fluxo (login-CSRF)

| | |
|---|---|
| **Status** | ✅ Decidida |
| **Autor** | Orquestrador, no fechamento da F13, a partir de achado de revisão adversarial |
| **Data** | 03/08/2026 |
| **Fases impactadas** | F13 (Grupo SSO — OIDC) |
| **Artefatos de contrato afetados** | `packages/contracts/openapi.yaml` — um parâmetro de query novo, opcional na forma mas exigido na prática, em `GET /v1/sso/{provedor}/iniciar` e em `GET /v1/sso/{provedor}/callback` |
| **Bloqueia** | Nada em andamento — corrige uma vulnerabilidade real antes do primeiro commit de F13 |

## 1. O que está errado

`app.identidade.sso.oidc.estado` (RFC-018/A9, não tocado até aqui) assina o `state` (HMAC-SHA256,
`gerar_estado`/`validar_estado`) contra adulteração e replay-após-expiração, e o `nonce` embutido impede
reuso do `id_token` devolvido pelo IdP. O que **nenhuma** dessas duas proteções cobre: `state` nunca é
vinculado ao **navegador** que chamou `iniciarSso` — qualquer navegador que apresente um `state`+`code`
válidos (assinatura correta, não expirado, `nonce` batendo) completa o login, **não importa se foi o mesmo
navegador que iniciou o fluxo**.

Isso é a classe de ataque "login CSRF" (OAuth 2.0 Security Best Current Practice, RFC 9700 §4.1.7; OWASP
CSRF em fluxo de autorização): um atacante completa o próprio login OIDC, intercepta o `code`+`state`
válidos ANTES do próprio navegador consumi-los (a troca só acontece quando `callbackSso` é chamado), e
induz a vítima a visitar `{webBaseUrl}/sso/callback/{provedor}?code=<do atacante>&state=<do atacante>`
(link, `<img>`, redirecionamento). O navegador da vítima completa a troca com sucesso e recebe uma sessão
`httpOnly` real — só que autenticada como a identidade vinculada ao ATACANTE, nunca a da vítima.

**Por que isto só virou explorável agora, nesta sessão de fechamento, não no build original da F13:** antes
do bridge de sessão de navegador (o próprio fechamento desta fase — ver `docs/backlog.md`, achado do
orquestrador sobre SSO não gerar sessão real), `callbackSso` emitia um JSON que nada consumia de verdade;
não havia como o resultado da troca virar uma sessão de navegador utilizável, então o `state` desprotegido
não tinha efeito prático explorável. Completar o bridge tornou o gap pré-existente de `estado.py` real.

## 2. Por que não é suficiente proteger só a rota nova (`api/auth/sso/**` em `apps/web`)

A checagem de mesma origem (`Sec-Fetch-Site`/`Origin`, já aplicada ao proxy Next.js nesta mesma sessão de
fechamento) prova que a REQUISIÇÃO ao proxy partiu da própria página — mas não prova nada sobre QUEM
gerou o `code`/`state` que a página está encaminhando. A página da vítima, hospedada na própria origem
legítima, chamando o próprio proxy legítimo, com dados de um `state` que não é dela: passa em toda checagem
de origem e ainda assim autentica como o atacante. O vínculo precisa estar no PRÓPRIO `state`, não na
chamada que o carrega.

## 3. Decisão

**Vínculo estilo PKCE (RFC 7636), aplicado ao `state` em vez de ao `code`:**

1. `botao-login-oidc.tsx` gera um valor aleatório de alta entropia (`vinculo`, `crypto.randomUUID()`) ANTES
   de navegar para `iniciarSso`, guarda em `sessionStorage` (por aba, mesma origem — nunca em cookie, nunca
   em `localStorage` compartilhado entre abas) e envia só o HASH dele (`SHA-256` via `crypto.subtle`,
   `vinculoHash`) como novo parâmetro de query de `GET /v1/sso/{provedor}/iniciar`.
2. `iniciarSso` embute `vinculoHash` como claim do `state` assinado (`gerar_estado` ganha o parâmetro).
3. A página de conclusão (`sso/callback/[provedor]/pagina-de-conclusao.tsx`) lê o `vinculo` bruto de volta
   de `sessionStorage` e o envia (bruto, nunca a query string do IdP — só no `fetch` servidor-a-servidor,
   nunca exposto a terceiro) ao proxy, que o encaminha a `callbackSso` como novo parâmetro de query
   `vinculo`.
4. `validar_estado` recalcula o hash do `vinculo` recebido e compara (`hmac.compare_digest`) contra a claim
   do `state` — divergência ou ausência é `PONTO-AUTH-004`, mesmo código já usado para `state`
   inválido/expirado (não vaza qual das duas checagens falhou).

**Por que hash em `iniciarSso` e valor bruto só no `callback`:** `iniciarSso` é navegação de página inteira
— o valor na query string aparece em log de servidor/histórico/`Referer` (o IdP pode ecoar parâmetros da
URL de origem). Se o valor bruto fosse embutido ali, um atacante leria o `vinculo` do PRÓPRIO `state`
decodificado (JWT não é cifrado, só assinado) e o anexaria manualmente ao link malicioso, anulando a
proteção. O hash (função de mão única) impede isso: o atacante vê o hash no `state` decodificado mas não
consegue reverter para o valor bruto que só existe no `sessionStorage` da vítima.

**Por que `sessionStorage`, não cookie:** `web_base_url`/`api_base_url` podem ser hosts completamente
diferentes (inclusive em dev, `localhost:3000`/`localhost:8000`, sem domínio-pai comum) — um cookie
funcionaria de forma frágil e dependente de topologia. `sessionStorage` é sempre mesma-origem ao próprio
front, funciona igual em qualquer topologia de host, e por natureza nunca sobrevive à aba/sessão do
navegador (mesma propriedade de curta duração que o `state` já tem, 10 minutos).

**Escopo: só OIDC.** SAML já tem proteção equivalente e correta — `RelayState`/`AuthnRequest.ID`
(`app.identidade.sso.saml.estado`/`protocolo`, A10, não tocado) são validados contra o par de chaves do
IdP do PRÓPRIO tenant durante `POST /v1/sso/saml/acs`, e o binding requestId↔response (`InResponseTo`) já
impede o mesmo tipo de replay entre navegadores distintos — não há gap equivalente a corrigir ali.

## 4. Alternativas consideradas

**Cookie `Domain` compartilhado entre `api_base_url`/`web_base_url`.** Descartada: exige que os dois hosts
compartilhem um domínio-pai real, o que não é garantido (nem em dev). Peça de infraestrutura frágil para
resolver um problema que `sessionStorage` resolve sem nenhuma suposição de topologia.

**Não corrigir agora, registrar em `docs/backlog.md` para uma fase de hardening.** Descartada: SSO ainda
não foi commitado nem está em produção (nenhum cliente Google/Entra real configurado, ADR-013) — corrigir
antes do primeiro commit é estritamente mais barato do que corrigir depois, e "login-CSRF" numa aplicação
de ponto/folha (dados de CPF, jornada, remuneração) é severidade real, não cosmética.

## 5. Consequências

`GET /v1/sso/{provedor}/iniciar` ganha o parâmetro de query opcional `vinculoHash`; `GET /v1/sso/{provedor}/
callback` ganha `vinculo`. Nenhuma mudança em `schema.sql`, nenhuma tabela nova, nenhuma mudança na forma
de resposta de nenhuma operação — puramente aditivo em `openapi.yaml`. Marcados opcionais no schema (para
não quebrar Schemathesis explorando a operação sem eles) mas exigidos em runtime pelo router quando
`provedor` é `google`/`entra_id` (ausência responde `PONTO-VAL-001`) — mesmo padrão de "opcional no
schema, obrigatório por regra de negócio" que outras operações do contrato já usam.
