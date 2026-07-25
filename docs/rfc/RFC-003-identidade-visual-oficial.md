# RFC-003 — Identidade visual oficial: nome, tipografia e paleta

| | |
|---|---|
| **Status** | ✅ **Decidida** em 26/07/2026 pelo orquestrador — implementada nesta mesma RFC |
| **Autor** | Henrique (entidade externa: Manual de Marca produzido em ferramenta de design) |
| **Fases impactadas** | F9a (Design System), F7 (app mobile), F8 (web colaborador), F11 (relatórios/espelho), F12 (REP-P) |
| **Artefatos de contrato afetados** | `packages/contracts/design-tokens.json`, `packages/contracts/openapi.yaml` (cosmético) |

## 1. O que motiva esta RFC

O Henrique entregou a identidade visual oficial do produto — nome, logotipo,
paleta, tipografia, ícones de domínio e especificação da tela de confirmação
de registro — produzida externamente (`SEEG Ponto - Manual de Marca` e
`SEEG PONTO - Brand Board`, arquivos anexados em 26/07/2026). Isso substitui
decisões de placeholder que a Fase 0 tomou sem essa informação, porque na
Fase 0 a identidade ainda não existia.

## 2. Nome do produto — confirmado, sem mudança de contrato

**Nome oficial: SEEG Ponto.** O Manual de Marca resolve isso sem ambiguidade
na página 03 ("NOME DEFINIDO"): SEEG é a marca já estabelecida da empresa,
Ponto nomeia a categoria. As alternativas exploradas (aponta, kairo, cadência,
lastro, prumo) foram descartadas.

> **Nota de qualidade dos artefatos recebidos:** o `SEEG PONTO - Brand Board`
> tem uma inconsistência interna — o card marcado "★ RECOMENDADO" na seção de
> nomes exibe "aponta" como título grande, mas o texto do próprio card descreve
> "SEEG Ponto" (nome definido pela empresa, herdando o reconhecimento da
> marca). O Manual de Marca, documento irmão, não tem essa falha: apresenta os
> 5 nomes numa tabela neutra e resolve com um quadro "NOME DEFINIDO" que só diz
> SEEG Ponto. Interpretação adotada: o rótulo "★ RECOMENDADO" no Brand Board
> foi aplicado ao card errado (resíduo de um rascunho anterior), e a decisão
> real — repetida de forma consistente no logotipo, no ícone de app, no
> documento legal e no rodapé dos dois arquivos — é SEEG Ponto.

Não há campo de "nome do produto" em `packages/contracts/`; o nome vive em
metadados de aplicação (título de página, `info.title` do OpenAPI, nome do
pacote mobile). Ver §5.

## 3. Paleta de cor — sem mudança

O índigo `#4C5FCA` e toda a escala de 11 tons, as 4 escalas semânticas e as 8
cores categóricas do Manual de Marca **já são exatamente** as de
`design-tokens.json` (conferido tom a tom). Isso não é coincidência: o Manual
foi construído a partir da paleta já implementada — ele mesmo declara "Índigo
#4C5FCA mantido da paleta existente". **Nenhuma mudança de contrato aqui.**

## 4. Tipografia — MUDA o contrato

`design-tokens.json` (`tipografia.familia.sans` / `.mono`) foi escrito na
Fase 0 com **Inter** e **JetBrains Mono** — escolha de placeholder, com
justificativa técnica válida (numerais tabulares, distinção 1/l/I), mas tomada
sem conhecimento da marca. O Manual de Marca especifica um sistema de
**três vozes**:

| Voz | Fonte | Uso |
|---|---|---|
| Display | Schibsted Grotesk | Logotipo, títulos, números-destaque |
| Texto/UI | IBM Plex Sans | Corpo, rótulo, tabela densa de RH |
| Tabular | IBM Plex Mono | Horas, NSR, hash, documento legal |

Ambas licenciadas SIL OFL 1.1 (uso comercial e embed em SaaS liberados,
conferido pelo próprio Manual).

### Mudança aplicada

1. `tipografia.familia.sans`: Inter → **IBM Plex Sans** (pilha completa com
   fallback de sistema preservada).
2. `tipografia.familia.mono`: JetBrains Mono → **IBM Plex Mono** (idem).
3. **Nova família** `tipografia.familia.display`: **Schibsted Grotesk**. Não
   existia voz de display no sistema de 2 vozes da Fase 0; o Manual introduz
   uma terceira, deliberadamente reservada para o momento de maior destaque —
   não para todo título.
4. Dos 10 estilos compostos (`tipografia.estilo.*`), **dois** passam a
   referenciar `{tipografia.familia.display}`:
   - `tituloPagina` ("Um por tela" — peso `forte`/700) — é literalmente
     "título" da lista do Manual.
   - `numeroDestaque` ("saldo de banco de horas, total de horas extras,
     headcount" — peso `semiforte`/600) — é literalmente "números-destaque"
     da lista do Manual.

   **Os demais oito permanecem em `sans`** (`corpo`, `corpoGrande`, `rotulo`,
   `legenda`, `tituloCartao`, `tituloSecao`, `tabular`) ou `mono`
   (`identificador`). Decisão deliberada, não decorrente automática do
   Manual: o texto do Manual lista "títulos" no plural sem detalhar por nível
   de hierarquia (página/seção/cartão), e o próprio Manual argumenta a favor
   de UI densa em IBM Plex Sans ("tabelas densas de RH"). Alternar a fonte de
   `tituloSecao`/`tituloCartao` para display também produziria uma interface
   com títulos trocando de fonte a cada nível de aninhamento — ruído visual
   num produto que é usado 8h/dia. Reservar o display para o único título "um
   por tela" e para os números mais destacados é a leitura mais conservadora
   e mais alinhada ao restante do Manual. **Registrado aqui para que a F9a
   possa reabrir esta escolha específica com conhecimento de causa, se
   achar que títulos de seção também merecem a voz de display.**

### Por que isto é mudança de contrato, não conserto

Fonte é `packages/contracts/design-tokens.json`, congelado. `apps/web/scripts/tokens-para-css.mjs`
não é congelado (é código de aplicação da F0), mas depende inteiramente da
forma do contrato — adicionar `tipografia.familia.display` exige adicionar uma
linha `--font-display: var(--tipografia-familia-display);` no bloco
"famílias tipográficas" do gerador (ele já emite `--font-sans`/`--font-mono`
manualmente, não há automação para novas famílias).

## 5. Nome nos artefatos de contrato — cosmético

`packages/contracts/openapi.yaml`: `info.title` era `"Ponto Eletronico - API v1"`.
Passa a `"SEEG Ponto - API v1"`; `info.description` ganha a frase da marca.
**Nenhum `operationId`, `path`, `schema` ou código de erro muda** — é troca de
string de exibição, sem efeito em cliente gerado ou em teste de contrato.

## 6. Logotipo, ícones e especificação de tela — não são tokens, são ativos

O símbolo (traço de confirmação sobre a linha do dia — dois `<path>` simples,
`stroke` `currentColor`, sem preenchimento) e os 11 ícones de domínio não têm
lugar natural em `design-tokens.json` (que descreve valores, não geometria).
Foram extraídos como:

- Componentes React em `apps/web/src/componentes/marca/` (símbolo, logotipo
  completo, favicon/ícones de app).
- Referência durável em `docs/marca/identidade-visual.md`, com todo o SVG,
  a tabela de cor, a régua tipográfica, a especificação da tela de
  confirmação de registro (F7) e do cabeçalho do espelho de ponto (F11/F12).
- Os 4 arquivos originais (`.dc.html` + scripts de suporte) preservados em
  `docs/marca/fonte-original/`, com nota de que dependem do runtime de
  Canvas/Artifacts do Claude para renderizar interativamente — o conteúdo
  determinístico já foi transcrito para `identidade-visual.md`.

## 7. O que NÃO está nesta RFC

- Registro de domínio (`seegponto.com.br`, `seegponto.app` aparecem como
  placeholder no Manual — **não há confirmação de que estejam registrados**).
  Ação de negócio, fora do escopo de código.
- Ícone do app mobile de verdade (`.appiconset`, adaptive icon Android) —
  isso só existe quando o projeto Flutter existir, na F7. O que existe hoje é
  a especificação (tamanhos, zona de segurança) em `identidade-visual.md`.
- Registro de marca/INPI do nome — já era pendência externa registrada em
  `PROJETO.md` §1, independente desta RFC.

## 8. Verificação

- `pnpm tokens && pnpm tokens:check` — gerador aceita a família nova sem
  mudança estrutural, `tokens.gerado.css` bate com o contrato.
- `npx tsc --noEmit`, `pnpm lint`, `pnpm test`, `pnpm build` em `apps/web` —
  verdes com as fontes carregadas via `next/font/google` (self-hospedadas,
  sem chamada a CDN do Google em produção).
- Inspeção visual no navegador (Fase 0 tinha só placeholder de andaime; esta
  RFC é a primeira vez que a aplicação renderiza com a fonte e o símbolo
  reais) — conferido antes de reportar concluído.
