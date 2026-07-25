# apps/web — Aplicação web (Next.js 15)

Front-end do **Ponto Eletrônico** (REP-P multiempresa). Entregue na **Fase 0**
como **andaime**: rotas existem, tema funciona, cliente HTTP está tipado pelo
contrato — e **não há uma linha de regra de negócio**. As 215 operações da API
respondem `501 PONTO-INT-005` nesta fase.

|             |                                                             |
| ----------- | ----------------------------------------------------------- |
| Framework   | Next.js 15 (App Router), React 19                           |
| Linguagem   | TypeScript com `strict` **e** `noUncheckedIndexedAccess`    |
| Estilo      | Tailwind v4 (tema no CSS, sem `tailwind.config.js`)         |
| Componentes | shadcn/ui apontado para os tokens do contrato               |
| Dados       | TanStack Query + `openapi-fetch` tipado pelo `openapi.yaml` |
| Testes      | Vitest + Testing Library                                    |
| Gerenciador | **pnpm** (é o que o CI, o Makefile e o compose usam)        |

---

## Comandos

```bash
pnpm install            # instala (o CI usa --frozen-lockfile)
pnpm dev                # desenvolvimento em http://localhost:3000
pnpm build              # build de produção (saída standalone)
pnpm start              # serve o build

pnpm lint               # eslint, --max-warnings=0
pnpm exec tsc --noEmit  # tipos
pnpm test               # vitest
pnpm format             # prettier --write

pnpm tokens             # regera o CSS a partir de design-tokens.json
pnpm tokens:check       # falha se o CSS gerado estiver desatualizado
pnpm tipos:api          # regera os tipos a partir de openapi.yaml
pnpm tipos:api:check    # falha se os tipos estiverem desatualizados
```

---

## O que é gerado e não se edita

Dois arquivos são **derivados de `packages/contracts/`**, que está congelado.
Editar qualquer um deles à mão é trabalho perdido na próxima geração.

| Arquivo gerado                  | Origem               | Gerador                       |
| ------------------------------- | -------------------- | ----------------------------- |
| `src/estilos/tokens.gerado.css` | `design-tokens.json` | `scripts/tokens-para-css.mjs` |
| `src/lib/api/tipos.gerado.ts`   | `openapi.yaml`       | `scripts/tipos-da-api.mjs`    |

Os dois têm modo `--check`, que compara byte a byte com o que sairia da geração
atual. Rode-os quando mexer em qualquer coisa perto de estilo ou de contrato.

### Design tokens → CSS

`design-tokens.json` está no formato W3C Design Tokens (DTCG), com 84
primitivos, 73 tokens semânticos por tema e dois temas de caminhos idênticos.
O gerador produz:

1. `:root` — primitivos, tipografia, espaçamento, raio, movimento, camada,
   ponto de quebra, dimensão, os semânticos do **tema claro** e a ponte de nomes
   do shadcn/ui;
2. `[data-tema="escuro"]` — só os semânticos do **tema escuro**;
3. `@media (prefers-color-scheme: dark) { :root:not([data-tema]) { … } }` — o
   mesmo, para quem está com JavaScript desligado;
4. `.estilo-*` — os 10 estilos tipográficos compostos do contrato;
5. `@theme` — **fecha** as escalas de fábrica do Tailwind (`--color-*: initial`
   e companhia);
6. `@theme inline` — expõe os tokens como utilitários (`bg-fundo-superficie`,
   `text-texto-primario`, `rounded-medio`, `shadow-media`, `ease-padrao`…).

**A regra que isso impõe:** depois de `--color-*: initial`, `bg-red-500` não
existe mais. A única cor disponível é a que saiu do contrato. Idem para raio,
sombra, tamanho de texto, ponto de quebra e curva de movimento.

Três exceções, todas deliberadas e documentadas no cabeçalho do arquivo gerado:

- **`--spacing` (base 4 px) é mantido.** É uma escala calculada, não um punhado
  de valores escolhidos a dedo, e a grade de 8 pt do contrato é subconjunto
  exato dela — todo valor de `espacamento.*` é múltiplo de 4 px. Os valores
  nomeados continuam acessíveis como `var(--espacamento-2x5)`.
- **`--breakpoint-*` e `--container-*` saem com valor literal**, não com
  `var()`. Não é preferência: `@media (width >= var(--x))` é sintaxe inválida e
  derruba o build do Tailwind. Os valores continuam vindo do contrato.
- **`--font-weight-*` e `--container-*` de fábrica não são apagados.** Os pesos
  do contrato (400/500/600/700) coincidem com os do Tailwind, e `--container-*`
  só alimenta `max-w-*`, que não é paleta.

### OpenAPI → tipos

O contrato tem 39.404 linhas, 140 caminhos, 215 operações e 245 schemas. Antes
de decidir por recorte, foi medido: `openapi-typescript` converte o arquivo
**inteiro** em ~0,58 s e produz ~31 mil linhas. Como o custo é irrisório, **não
há recorte** — o contrato é gerado por completo, e nenhum tipo de requisição ou
resposta é escrito à mão nesta aplicação.

---

## Cliente HTTP (`src/lib/api/`)

```ts
import { GET, ehErroDaApi } from "@/lib/api";

const { data } = await GET("/v1/colaboradores", { params: { query: { pagina: 1 } } });
```

Caminho inexistente ou corpo com forma errada é **erro de compilação**.

O cliente já cumpre três regras do contrato, de modo que nenhuma fase futura
precise lembrar delas:

| Regra do contrato                                                          | Onde é cumprida                                              |
| -------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `Idempotency-Key` obrigatória em `POST`/`PUT`/`PATCH`/`DELETE`             | middleware `autenticacao` gera uma por requisição de escrita |
| Erro é RFC 9457 e a mensagem deriva de `codigo`, nunca de `title`/`detail` | `ErroDaApi.codigo`, alimentado pelo schema `Problema`        |
| `X-Tenant` quando o host não identifica o tenant                           | `definirTenant()`                                            |

Origem da API: `NEXT_PUBLIC_API_URL` no navegador, `API_INTERNAL_URL`
(`http://api:8000`) no servidor. Os nomes vêm do `docker-compose.yml`.
`baseUrl` **não** leva `/v1`: os 140 caminhos do contrato já começam com ele.

---

## Tema claro/escuro sem flash

O `<head>` executa um script síncrono (`SCRIPT_ANTI_FLASH`) **antes da primeira
pintura**: ele lê `localStorage["ponto.tema"]`, resolve `sistema` pela
`prefers-color-scheme` e escreve `data-tema` no `<html>`. Sem isso o navegador
pintaria claro, o React hidrataria e trocaria para escuro — o flash branco.

O React não decide o tema inicial; ele só sincroniza seu estado com o que já
está no DOM. Por isso `<html suppressHydrationWarning>`: o atributo é escrito
fora do React, de propósito.

O `dark:` do Tailwind foi religado ao mesmo atributo
(`@custom-variant dark` em `globais.css`), para não existirem duas verdades
sobre "está escuro?".

---

## Rotas

| Rota          | Público               | Quem implementa                                |
| ------------- | --------------------- | ---------------------------------------------- |
| `/`           | todos                 | **F1** — Identidade, Multi-tenant e RBAC       |
| `/painel`     | RH, gestor, diretoria | **F9b** — Painel RH e Gestor                   |
| `/eu`         | colaborador           | **F8** — Web colaborador e registro por webcam |
| `/api/health` | infraestrutura        | já implementada (liveness)                     |

`/api/health` **não** é escolha desta aplicação: `infra/docker-compose.yml` sonda
`http://127.0.0.1:3000/api/health` e o Traefik usa o mesmo caminho. Mudar o
caminho derruba o healthcheck do container. É _liveness_, não _readiness_: não
consulta API, banco nem Redis, para que uma lentidão na API não faça o
orquestrador matar o front.

---

## Docker

O `Dockerfile` é multi-estágio e o **contexto de build é a raiz do monorepo** —
foi assim que `infra/docker-compose.yml` (`context: ..`) e o job `docker` do CI
(`context: .`) já declaram. Por isso todo `COPY` começa com `apps/web/`.

| Estágio   | Quem usa                                                                                  |
| --------- | ----------------------------------------------------------------------------------------- |
| `deps`    | camada de dependências, invalidada só por `package.json`/lockfile                         |
| `dev`     | `infra/docker-compose.dev.yml` (`target: dev`)                                            |
| `builder` | `next build`; as `NEXT_PUBLIC_*` precisam existir aqui, porque o Next as embute no bundle |
| `runner`  | **padrão**; só o `standalone`, usuário `node`, sem código-fonte                           |

---

## Nota sobre `node-linker=hoisted`

`.npmrc` desliga o `node_modules` isolado do pnpm. Não é preferência estética —
são dois defeitos reproduzidos nesta máquina:

1. `output: "standalone"` copia o rastro de dependências **preservando links
   simbólicos**. No Windows sem Modo Desenvolvedor, `fs.symlink` devolve `EPERM`
   e o build morre em _Collecting build traces_ (`fs.symlink` falha, `junction`
   funciona — testado).
2. O ESLint resolve plugins a partir do diretório do projeto, e os que
   `eslint-config-next` traz como dependência própria ficam invisíveis na árvore
   isolada: _"couldn't find the plugin eslint-plugin-react-hooks"_.

O que se perde é a proteção contra dependência fantasma. O que se ganha é o
mesmo comando de build funcionando em Windows, no CI e no Docker.
