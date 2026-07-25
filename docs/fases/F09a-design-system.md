# F09a — Design System

| | |
|---|---|
| **Onda** | 1 |
| **Agentes** | 2 · **A1** primitivos, tipografia, Storybook e o aparato automático de acessibilidade · **A2** componentes de domínio, data-table virtualizada e gráficos base |
| **Duração estimada** | 5 dias |
| **Depende de** | F0 (`packages/contracts/design-tokens.json` congelado e o esqueleto `apps/web` já entregue e executável) |
| **Criticidade** | Alta — **F7 (app mobile), F8 (web colaborador) e F9b (painel RH e gestor) param se esta fase sair tarde.** É por isso que ela está na Onda 1, e não junto do resto da UI |
| **Branch** | `f09a-design-system` |

---

## 1. Objetivo

Ao fim desta fase, **existe uma biblioteca de componentes React em
`apps/web`, publicada em Storybook, em que todo componente funciona nos dois
temas, é operável só pelo teclado, tem contraste WCAG 2.2 AA verificado por
teste automático, e não contém um único valor literal de cor, espaçamento, raio,
sombra ou tipografia** — mais os seis componentes de domínio do ponto eletrônico
(linha do tempo de marcações, cartão de saldo de banco de horas, grade de
escala, seletor de período, data-table configurável e virtualizada, gráficos
base), prontos para as fases de interface consumirem sem reescrever nada.

## 2. Contexto mínimo

**O produto, em três frases.** Este é um sistema de ponto eletrônico brasileiro
do tipo **REP-P** — *Registrador Eletrônico de Ponto via Programa*, a modalidade
de software prevista na Portaria MTP 671/2021. Ele é vendido como SaaS
multiempresa: cada cliente é um **tenant**, com suas empresas, unidades e
pessoas. Você não vai implementar regra de negócio nenhuma; vai construir a
camada visual que três fases posteriores consomem — e vai precisar entender seis
conceitos do domínio para que os componentes tenham a forma certa.

**Os seis conceitos que dão forma aos componentes de domínio.**

- **Marcação** é o registro de um instante em que alguém bateu o ponto. É
  *append-only* e **imutável por exigência legal**: o sistema nunca edita nem
  apaga marcação. Ela tem data/hora, canal de origem (`terminal`, `mobile`,
  `web`, `totem`, `api`), um **NSR** (Número Sequencial de Registro, o contador
  legal sem lacunas do REP-P) e um **score de confiança** antifraude. Importante
  para a interface: **o REP-P não registra "entrada" ou "saída"** — o
  emparelhamento é feito depois, no cálculo. A linha do tempo de marcações
  mostra instantes, não pares; se o sistema informar um sentido, ele é
  *informado pelo coletor*, não deduzido.
- **Tratamento** é a única forma legítima de corrigir a jornada: uma camada
  separada de inclusão, desconsideração ou abono, **aplicada por cima** das
  marcações, que continuam intactas. Na interface **nunca** escreva "editar
  marcação", "corrigir batida" ou "excluir ponto".
- **Apuração** é o resultado do cálculo de um dia para um vínculo: horas
  normais, extras por faixa, adicional noturno, atrasos, faltas.
- **Banco de horas** é a conta-corrente de horas do colaborador: créditos e
  débitos, saldo, vencimento (6 meses em acordo individual escrito, 12 meses em
  acordo coletivo) e quitação. O cartão de saldo mostra **saldo credor** e
  **saldo devedor** — nunca "banco positivo/negativo".
- **Escala** é o ciclo de trabalho: 5x2, 6x1, 4x2, **12x36**, espanhola,
  rotativa de N dias. A grade de escala é uma matriz colaborador × dia, com
  turno por célula, e precisa aguentar jornada que **cruza a meia-noite**.
- **Vínculo** é a relação de trabalho (não a pessoa). Toda apuração pendura em
  vínculo; a interface, porém, quase sempre exibe o **colaborador**. Guarde a
  distinção nos nomes das *props*.

**Vocabulário obrigatório.** A seção 6 do `glossario.md` lista termos proibidos.
Os que mais aparecem em interface: use **marcação** (nunca "batida"),
**tratamento** (nunca "ajuste"/"correção de marcação"), **apuração** (nunca
"cálculo"), **jornada** (nunca "horário de trabalho" como regra), **colaborador**
(nunca "funcionário"), **coletor** (nunca "relógio de ponto"), **saldo credor /
saldo devedor** (nunca "banco positivo/negativo"). Isso vale para nome de
componente, nome de *prop*, rótulo e texto de Storybook.

**O contrato visual está congelado e é excepcionalmente detalhado.**
`packages/contracts/design-tokens.json` é um arquivo no formato **W3C Design
Tokens (DTCG)**, e não uma lista de cores. As rampas foram geradas em **OKLCH**
com luminosidade-alvo fixa por passo, idêntica em todas as famílias: o passo 600
de qualquer família tem aproximadamente a mesma luminosidade percebida, e por
isso **trocar a cor de marca não quebra o contraste dos componentes**. Ele traz:
primitivos de cor (neutro, marca, sucesso, atenção, erro, info, mais 8 séries de
gráfico), tipografia (famílias, 12 tamanhos, 12 alturas de linha, 4 pesos, 12
rastreios e **10 estilos compostos** — `corpo`, `rotulo`, `legenda`,
`tituloCartao`, `tituloSecao`, `tituloPagina`, `numeroDestaque`, `tabular`,
`identificador`, `corpoGrande` — emitidos no CSS em `kebab-case`, como
`.estilo-titulo-pagina`), espaçamento em grade de 8 pt, raios, movimento,
camadas de empilhamento (`z-index`), pontos de quebra, dimensões de componente e
os **tokens semânticos por tema** (`tema.claro` e `tema.escuro`, com **os mesmos
caminhos** nos dois: `fundo` 8, `texto` 8, `borda` 5, `acao` 14, `estado` 24,
`grafico` 11, `sombra` 3).

Três regras que vêm do próprio arquivo e que você **não redecide**:

1. **Consuma o semântico, nunca o primitivo.** `--cor-texto-primario`, não
   `--primitivo-cor-neutro-900`. O tema escuro **não é uma inversão**: cada
   alias foi escolhido e medido separadamente.
2. **Nenhum `z-index` inventado.** A escala `camada` tem dez níveis (`base`,
   `elevado`, `cabecalho`, `navegacao`, `sobreposicao`, `dialogo`, `suspenso`,
   `dica`, `notificacao`, `depuracao`). Faltou um nível? Isso é RFC.
3. **Cor nunca é o único portador de informação** (WCAG 2.2, critério 1.4.1).
   Série de gráfico sempre acompanha rótulo direto, legenda ou marcador de forma
   distinta. Acima de 8 séries, agregue em "outros" — não repita nem clareie
   cor.

**Acessibilidade é requisito medido, não intenção.** O contrato fixa
**WCAG 2.2 nível AA**: 4.5:1 para texto normal, 3:1 para texto grande (≥18.66 px
em peso 700, ou ≥24 px em qualquer peso) e 3:1 para elemento de interface. O
próprio arquivo traz, em
`$extensions["br.com.seeg.ponto"].contraste.pares`, **124 pares já verificados**
com primeiro plano, fundo, ratio medido, ratio exigido, critério e situação —
0 reprovados, menor ratio de texto normal 4.67, menor ratio de elemento de
interface 3.01. Esses 124 pares são o seu *golden dataset* de contraste: o teste
automático da fase recalcula cada um a partir do CSS realmente gerado e compara.
O contrato fixa também **alvo de toque de 44×44 px** (o mínimo do critério 2.5.8
é 24×24; o projeto adota 44 porque ponto é sistema de uso obrigatório, muitas
vezes em celular na mão, em pé, com pressa ou luva), **anel de foco de 2 px com
deslocamento de 2 px** usando `tema.<t>.borda.foco`, e que **toda transição
respeita `prefers-reduced-motion: reduce`**, caindo para 0 ms. Há ainda uma
regra de produto explícita no token de movimento: **nenhuma animação atrasa a
confirmação de uma batida de ponto.**

**O que a Fase 0 já entregou em `apps/web` — leia antes de construir qualquer
coisa, porque metade do caminho já está feito.** A aplicação é **Next.js 15
(App Router)** com **React 19**, **TypeScript 5.7** e **Tailwind CSS v4**
(configuração CSS-first: **não existe `tailwind.config.js`**). O gerenciador é
**pnpm**. Já existem:

- `apps/web/scripts/tokens-para-css.mjs` — o **gerador oficial** que lê
  `packages/contracts/design-tokens.json` e grava
  `apps/web/src/estilos/tokens.gerado.css` (967 linhas: 84 primitivos, 73
  semânticos por tema, 293 variáveis expostas ao Tailwind). Rode com
  `pnpm tokens`; confira com `pnpm tokens:check`. **Esse arquivo CSS é gerado —
  editá-lo à mão é trabalho perdido na próxima geração.** A tarefa "tokens →
  CSS" **já está pronta**; a sua é construir em cima dela.
- Uma **ponte de nomes para o shadcn/ui** dentro do gerador (`background`,
  `foreground`, `card`, `primary`, `popover`, …), cada um apontando para um
  token **semântico**. Consequência prática: `pnpm dlx shadcn@latest add <componente>`
  produz componente **já tematizado nos dois temas**, sem retrabalho.
  `components.json` está configurado (estilo `new-york`, RSC, ícones `lucide`,
  aliases `@/componentes`, `@/componentes/ui`, `@/lib/utils`, `@/ganchos`).
- `apps/web/src/estilos/globais.css` — importa Tailwind e os tokens, declara
  `@custom-variant dark (&:where([data-tema="escuro"], …))` para que o `dark:`
  do Tailwind siga o mesmo atributo do provedor de tema, e já implementa
  `:focus-visible` com a espessura/deslocamento do contrato, `::selection`,
  `font-variant-numeric: tabular-nums` em `table` e o bloco
  `prefers-reduced-motion`.
- `src/componentes/tema/**` — `ProvedorDeTema`, `preferencia-de-tema.ts` (claro
  / escuro / sistema, atributo `data-tema` no `<html>`, script anti-flash) e
  `AlternadorDeTema`.
- `src/lib/api/**` — cliente `openapi-fetch` e `tipos.gerado.ts` gerado do
  `openapi.yaml` por `pnpm tipos:api`. Útil para tipar *props* de domínio.
- **Vitest + Testing Library + jsdom** configurados: `pnpm test`, arquivos em
  `src/**/*.teste.{ts,tsx}`, alias `@` → `src`. Existe
  `src/testes/andaime.teste.tsx`, que **não pode quebrar**.
- ESLint 9 + Prettier, `pnpm lint`, `pnpm typecheck`, `pnpm build`.
- **Não existe Storybook.** Instalá-lo e configurá-lo é entrega desta fase.

**Fase 0 é congelada.** `packages/contracts/` não se altera — inclusive
`design-tokens.json`. Falta um token? O caminho é `docs/rfc/` (protocolo em
`docs/rfc/README.md`), não uma cor escrita à mão "só nesse componente".

## 3. Leituras obrigatórias (lista fechada)

Leia isto e pare. Não leia `PROJETO.md`, não leia outras fases, não leia o
código da F1 nem o da F2.

- `packages/contracts/design-tokens.json` — **o arquivo inteiro**, com atenção
  a `$extensions["br.com.seeg.ponto"]`: `metodo` (como as rampas foram
  geradas), `temas`, `contraste` (norma, limiares e os **124 pares**),
  `paletaCategorica` (critério, matizes por série, separação mínima em ΔE OK
  por tipo de daltonismo, regra de uso) e `acessibilidade` (alvo de toque, foco,
  movimento).
- `packages/contracts/openapi.yaml` — **somente** os schemas de
  `components.schemas` que os componentes de domínio tipam: `Marcacao`,
  `ApuracaoDia`, `SaldoBancoHoras`, `ExtratoBancoHoras`, `Escala`,
  `EscalaCiclo`, `Turno` e os envelopes `Lista*`. **Não leia os `paths`** — esta
  fase não chama a API.
- `packages/contracts/glossario.md` — verbetes **Marcação**, **Tratamento**,
  **Apuração**, **Banco de horas**, **Crédito**, **Débito**, **Escala**,
  **Turno**, **Jornada**, **Vínculo**, **Colaborador**, **Score de confiança**,
  **NSR**, **Canal**; e a seção **6 (Termos proibidos)** por inteiro.
- `apps/web/scripts/tokens-para-css.mjs` — o gerador e a ponte do shadcn/ui.
- `apps/web/src/estilos/tokens.gerado.css` — os nomes reais das variáveis CSS
  que você vai consumir.
- `apps/web/src/estilos/globais.css`, `apps/web/package.json`,
  `apps/web/components.json`, `apps/web/vitest.config.ts`,
  `apps/web/eslint.config.mjs`, `apps/web/tsconfig.json`.
- `apps/web/src/componentes/tema/**` e `apps/web/src/testes/andaime.teste.tsx`.
- `docs/rfc/README.md` e `docs/backlog.md`.

## 4. Contratos

**Consome** — já existe, esta fase apenas usa:

- `packages/contracts/design-tokens.json` (congelado) e o CSS gerado a partir
  dele, via `pnpm tokens`.
- O esqueleto `apps/web`: Next.js 15, React 19, Tailwind v4, shadcn/ui
  configurado, provedor de tema com `data-tema`, `globais.css`, Vitest,
  ESLint, Prettier.
- `apps/web/src/lib/api/tipos.gerado.ts` — tipos TypeScript do `openapi.yaml`,
  **apenas para tipar props**. Esta fase **não chama a API**.

**Produz** — esta fase implementa:

*Primitivos* (em `src/componentes/ui/`, alias `@/componentes/ui`): botão,
input, textarea, select, checkbox, radio, switch, dialog (modal), sheet/drawer,
toast, tooltip, popover, tabs, badge, alerta, card, separador, skeleton,
avatar, breadcrumb, paginação, tabela base. Cada um em ambos os temas, operável
por teclado, com estados `hover`, `active`, `focus-visible`, `disabled` e
`aria-invalid` vindos de tokens.

*Camada tipográfica*: os 10 estilos compostos do contrato **já são emitidos pelo
gerador** como classes utilitárias, em `kebab-case`, a partir da linha 537 de
`tokens.gerado.css`: `.estilo-corpo`, `.estilo-corpo-grande`, `.estilo-rotulo`,
`.estilo-legenda`, `.estilo-titulo-cartao`, `.estilo-titulo-secao`,
`.estilo-titulo-pagina`, `.estilo-numero-destaque`, `.estilo-tabular` e
`.estilo-identificador`. Sua parte é usá-las de forma consistente e documentá-las
— **não** redefinir tipografia em componente.

*Componentes de domínio* (em `src/componentes/dominio/`):

| Componente | O que faz |
|---|---|
| `LinhaDoTempoDeMarcacoes` | Sequência de marcações de um dia ou período, com canal, NSR, score de confiança e estado (normal, suspeita, offline pendente). Não infere entrada/saída. |
| `CartaoDeSaldoDeBanco` | Saldo credor/devedor, vencimento próximo, variação no período, com sinal explícito por forma **e** por cor. |
| `GradeDeEscala` | Matriz colaborador × dia com turno por célula, suporte a jornada que cruza a meia-noite e a ciclos (5x2, 6x1, 12x36, rotativa). |
| `SeletorDePeriodo` | Intervalo de datas com atalhos (mês corrente, mês anterior, período de apuração), teclado completo e validação de intervalo. |
| `TabelaDeDados` | Data-table com colunas configuráveis (mostrar/ocultar, reordenar, largura), ordenação, seleção e **virtualização**. |
| `Graficos` | Barras, linha, área e pizza usando as **8 séries** de `tema.<t>.grafico`, com rótulo direto ou legenda sempre presentes. |

*Storybook*: uma *story* por componente e por estado relevante, nos **dois
temas**, com o *addon* de acessibilidade ativo e o *test-runner* rodando axe em
todas as histórias.

*Aparato de verificação*: o teste dos 124 pares de contraste, os testes de
navegação por teclado e o *benchmark* de 10.000 linhas.

**Não toca** — é de outra fase, mesmo que pareça relacionado:

- `apps/web/src/app/**` — rotas e telas. Portal do colaborador é **F8**; painel
  de RH e gestor é **F9b**. Você entrega componentes, não páginas.
- `apps/web/src/lib/api/**` e qualquer chamada real à API (**F8**, **F9b**).
  Storybook usa dados fixos escritos à mão.
- Autenticação, sessão, tenant (**F1**); cadastros (**F2**); jornada (**F3**);
  cálculo e banco de horas (**F4**); marcação (**F5**).
- Registro por webcam, `getUserMedia`, detecção de câmera virtual (**F8**).
- Tema e componentes do app **Flutter** (**F7**). Esta fase é web; a F7 consome
  os mesmos tokens por conta própria.
- `packages/contracts/**` — **congelado**, `design-tokens.json` inclusive.
- `apps/api`, `apps/worker`, `apps/mobile`, `apps/device-gw`, `apps/facial-svc`,
  `infra/`, `.github/`.

## 5. Ownership de arquivos

Caminhos **exclusivos** desta fase. **F1, F2 e F9a rodam em paralelo** — a F1 e
a F2 escrevem apenas em `apps/api` e `apps/worker`, e você escreve apenas em
`apps/web`. A fronteira é limpa; mantenha-a assim.

| Agente | Caminhos |
|---|---|
| **A1** (primitivos, tipografia, Storybook, acessibilidade) | `apps/web/src/componentes/ui/**`<br>`apps/web/src/componentes/tema/alternador-de-tema.tsx`<br>`apps/web/src/estilos/globais.css`<br>`apps/web/.storybook/**`<br>`apps/web/src/testes/design-system/**`<br>`apps/web/eslint.config.mjs`<br>`apps/web/vitest.config.ts`<br>`apps/web/playwright.config.ts` *(novo, se o test-runner exigir)* |
| **A2** (domínio, tabela, gráficos) | `apps/web/src/componentes/dominio/**`<br>`apps/web/src/componentes/graficos/**`<br>`apps/web/src/ganchos/**`<br>`apps/web/src/lib/formatacao/**`<br>`apps/web/src/testes/dominio/**` |

**Compartilhado dentro da fase** (exige combinação entre A1 e A2):

| Caminho | Regra |
|---|---|
| `apps/web/package.json` | Ambos acrescentam dependências. **Acrescente apenas em ordem alfabética dentro de `dependencies`/`devDependencies`**, sem reordenar nem remover linha existente e sem tocar em `scripts` que você não criou. Scripts novos vão no fim do bloco `scripts`. Bibliotecas prescritas: `@tanstack/react-virtual` (virtualização) e `recharts` (gráficos) para A2; Storybook 8 (`storybook`, `@storybook/nextjs`, `@storybook/addon-a11y`, `@storybook/addon-essentials`, `@storybook/test-runner`, `axe-playwright`) para A1. **Trocar de biblioteca é decisão sua, mas registre em `docs/backlog.md` para que F8 e F9b saibam.** |
| `apps/web/src/componentes/ui/**` | A2 **consome**, não edita. Precisa de um primitivo novo ou de uma variante nova? Pede a A1 — não cria um paralelo em `dominio/`. |
| `apps/web/pnpm-lock.yaml` | Regenerado por `pnpm install`. Conflito aqui se resolve **regenerando**, nunca editando à mão. Combinem quem roda `pnpm install` por último antes de fechar a fase. |

**Explicitamente fora do seu ownership** (não edite, nem "só para arrumar"):

| Caminho | Por quê |
|---|---|
| `packages/contracts/**` | **Congelado.** `design-tokens.json` inclusive. |
| `apps/web/src/estilos/tokens.gerado.css` | **Gerado.** Regerar com `pnpm tokens`; editar à mão é perdido. |
| `apps/web/scripts/tokens-para-css.mjs` | Gerador oficial da F0. Mudar o formato de saída quebra a rastreabilidade token → CSS. |
| `apps/web/src/lib/api/tipos.gerado.ts` e `apps/web/scripts/tipos-da-api.mjs` | Gerados do `openapi.yaml`. |
| `apps/web/src/componentes/tema/provedor-de-tema.tsx`, `preferencia-de-tema.ts` | Mecanismo de tema da F0. O `data-tema` é a única verdade sobre "está escuro?"; não crie uma segunda. |
| `apps/web/src/app/**`, `apps/web/src/componentes/andaime/**` | Rotas e placeholders — **F8** e **F9b**. |
| `apps/web/src/testes/andaime.teste.tsx` | Teste da F0. Não pode quebrar e não se edita. |
| `apps/web/next.config.ts`, `Dockerfile`, `postcss.config.mjs`, `tsconfig.json` | Andaime da F0. Storybook não deve exigir mudança neles; se exigir, registre no relatório. |
| `apps/api/**`, `apps/worker/**`, `infra/**`, `.github/**` | Outras fases. |

## 6. Tarefas (T1..Tn)

### T1 — Storybook e o gate de acessibilidade
**Agente:** A1 — **primeira tarefa; A2 não abre nenhuma *story* antes**
**Descrição:** Instalar e configurar **Storybook 8** com `@storybook/nextjs`,
importando `src/estilos/globais.css` no preview. Criar um **decorator global de
tema** que renderiza cada história nos dois temas (alternando `data-tema` no
elemento raiz do preview) e um `globalType` para trocar manualmente. Ativar
`@storybook/addon-a11y`. Configurar `@storybook/test-runner` com
`axe-playwright` para rodar axe em **todas** as histórias, em ambos os temas,
falhando em qualquer violação de severidade `serious` ou `critical`.
Acrescentar os scripts `storybook`, `build-storybook` e `test:storybook` ao
`package.json`.
**Pronto quando:** `pnpm build-storybook` conclui sem erro e
`pnpm test:storybook` roda contra o Storybook servido e passa com pelo menos uma
história de exemplo nos dois temas.

### T2 — Teste automático dos 124 pares de contraste
**Agente:** A1
**Descrição:** Escrever um teste Vitest que (a) lê
`packages/contracts/design-tokens.json` e `apps/web/src/estilos/tokens.gerado.css`
com `readFileSync` (o Vitest está com `css: false`; não tente importar o CSS);
(b) resolve, por tema, o valor hexadecimal final de cada variável semântica,
seguindo as indireções `var(--…)`; (c) para cada um dos **124 pares** de
`$extensions["br.com.seeg.ponto"].contraste.pares`, recalcula o ratio pela
fórmula declarada no próprio arquivo — WCAG 2.2, `(L1 + 0.05) / (L2 + 0.05)`
com `L = 0.2126R + 0.7152G + 0.0722B` sobre canais sRGB linearizados, truncado
para baixo em 2 casas — e afirma que o valor recalculado **é igual ao `ratio`
declarado** e **≥ `exigido`**.
**Pronto quando:** o teste passa para os 124 pares, e passa a falhar se você
alterar um hexadecimal do CSS à mão (prove isso uma vez e cole a saída no
relatório). Nenhum par pode ser marcado como `skip`.

### T3 — Primitivos, parte 1: controles de formulário
**Agente:** A1
**Descrição:** Botão (variantes primária, secundária, sutil, destrutiva;
tamanhos vindos de `--dimensao-altura-controle` (36 px),
`--dimensao-altura-controle-compacta` (28 px) e
`--dimensao-altura-controle-toque` (44 px)), input, textarea, select, checkbox,
radio, switch, label,
mensagem de erro de campo. Todos com estados `hover`, `active`,
`focus-visible`, `disabled`, `aria-invalid`, `readonly` e `required`, e **alvo
de toque de 44×44 px** nas variantes de toque.
**Pronto quando:** cada componente tem *story* nos dois temas; `pnpm test:storybook`
verde; teste de teclado (`@testing-library/user-event`) prova que cada controle
recebe foco por `Tab`, ativa por `Enter`/`Espaço` quando aplicável, e que o
grupo de radio navega por setas.

### T4 — Primitivos, parte 2: sobreposição, navegação e sinalização
**Agente:** A1
**Descrição:** Dialog (modal), sheet/drawer, popover, tooltip, toast, tabs,
badge, alerta, card, separador, skeleton, avatar, breadcrumb, paginação e
tabela base. **Empilhamento vindo exclusivamente da escala `camada`.** Dialog e
sheet com *focus trap*, retorno de foco ao gatilho ao fechar, `Escape` fecha e
`aria-modal`/`role="dialog"` corretos. Toast com região `aria-live` adequada e
sem depender de cor para distinguir sucesso de erro.
**Pronto quando:** teste prova, para dialog e sheet, que o foco entra, fica
preso, retorna ao gatilho e que `Escape` fecha; nenhum `z-index` literal aparece
no código-fonte (verificável por busca); `pnpm test:storybook` verde.

### T5 — Formatação de domínio
**Agente:** A2
**Descrição:** `src/lib/formatacao/**` com as funções que todos os componentes
de domínio usam: minutos → `HH:MM` e → decimal (o contrato guarda **duração
sempre em minutos inteiros**, nunca em `float` — a conversão é de apresentação),
data e hora em `pt-BR`, fuso da unidade, CPF/CNPJ/PIS mascarados para exibição,
sinal explícito de crédito/débito. Puras, sem estado, testadas.
**Pronto quando:** teste cobre virada de meia-noite, duração negativa, duração
acima de 24 h e arredondamento decimal (`90 min` → `1:30` → `1,50`).

### T6 — `LinhaDoTempoDeMarcacoes` e `CartaoDeSaldoDeBanco`
**Agente:** A2
**Descrição:** A linha do tempo exibe marcações de um dia ou período com
data/hora, canal, NSR, score de confiança e estado (normal, suspeita, pendente
de envio offline), em ordem cronológica, **sem inferir entrada/saída**, com
densidade compacta e confortável. O cartão de saldo exibe saldo credor/devedor
com **sinal por forma e por cor**, vencimento próximo destacado e variação no
período.
**Pronto quando:** *stories* cobrem dia vazio, dia com marcação ímpar, marcação
suspeita, marcação offline pendente, saldo credor, saldo devedor, saldo zero e
vencimento em menos de 30 dias — tudo nos dois temas, com axe verde.

### T7 — `GradeDeEscala` e `SeletorDePeriodo`
**Agente:** A2
**Descrição:** Grade colaborador × dia, com turno por célula, cabeçalho fixo nas
duas direções, marcação visual de fim de semana, feriado e folga, e tratamento
correto de **jornada que cruza a meia-noite** (a célula pertence ao dia de
início). Seletor de período com atalhos, entrada por teclado, validação de
intervalo invertido e navegação por setas no calendário.
**Pronto quando:** *story* da grade com 12x36 atravessando virada de mês
renderiza corretamente; o seletor é operável **inteiramente pelo teclado**, com
`aria-label` de cada dia e anúncio do intervalo selecionado; axe verde.

### T8 — `TabelaDeDados`: colunas configuráveis e virtualização
**Agente:** A2
**Descrição:** Colunas mostrar/ocultar, reordenar e redimensionar; ordenação por
coluna; seleção de linha; estado vazio; estado de carregamento; e
**virtualização** com `@tanstack/react-virtual`. A preferência de colunas é
**estado do componente e *prop* controlada** — a persistência por usuário é da
F11 (`preferencias_colunas`), não sua. Cabeçalho fixo, `role`/`aria-sort`
corretos e navegação por teclado entre células.
**Pronto quando:** *benchmark* renderiza **10.000 linhas** e afirma (a) que o
DOM contém **menos de 100 linhas** simultaneamente — prova de que virtualiza —
e (b) que o tempo de montagem inicial fica abaixo do limite do critério 6 da
§7, com o tempo real impresso.

### T9 — Gráficos base com paleta acessível
**Agente:** A2
**Descrição:** Barras, linha, área e pizza sobre `recharts`, consumindo
exclusivamente `tema.<t>.grafico.serie1..serie8`, `grade`, `eixo` e `rotulo`.
**Cor nunca é o único portador**: cada série leva rótulo direto ou legenda, e
séries em gráfico de linha recebem marcador de forma distinta. Acima de 8
séries, agregue em "outros". Eixos, grade e rótulos legíveis nos dois temas.
**Pronto quando:** *story* com as 8 séries simultâneas passa no axe nos dois
temas; existe teste afirmando que nenhuma cor de série é escrita literalmente
no código (só `var(--cor-grafico-serieN)`); e o comportamento de agregação acima
de 8 séries tem *story* própria.

### T10 — Documentação viva e fechamento
**Agentes:** A1 e A2
**Descrição:** Uma página MDX de introdução no Storybook explicando, para quem
chega na F8, na F9b e na F7: como consumir tokens semânticos, o que **não**
fazer (valor literal, `z-index` próprio, cor como único portador), o vocabulário
obrigatório e como pedir um componente novo. Rodar todos os comandos da §8 e
colar a saída real no relatório, item a item contra a §7.
**Pronto quando:** todos os comandos da §8 verdes com saída colada, e
`git status --short packages/contracts` vazio.

## 7. Critérios de aceite

O relatório final responde item a item, com saída real colada.

1. **Storybook publicado** com **todos** os componentes — primitivos e de
   domínio — e cada um em **ambos os temas**. `pnpm build-storybook` conclui sem
   erro.
2. **Contraste WCAG 2.2 AA verificado automaticamente**: os 124 pares de
   `design-tokens.json` recalculados a partir do CSS gerado, todos ≥ o exigido e
   iguais ao ratio declarado. Zero `skip`.
3. **axe sem violação** de severidade `serious` ou `critical` em **todas** as
   histórias, nos dois temas (`pnpm test:storybook`).
4. **Navegação por teclado em todos os interativos**: cada primitivo interativo
   tem teste de teclado; dialog e sheet prendem e devolvem o foco e fecham com
   `Escape`.
5. **Alvo de toque de 44×44 px** nas variantes de toque, verificável por teste.
6. **Data-table renderiza 10.000 linhas sem travar**: menos de 100 linhas no DOM
   e montagem inicial **abaixo de 1 s** no ambiente de teste; registre o tempo
   real medido.
7. **Nenhum valor literal** de cor, espaçamento, raio, sombra, duração,
   `z-index` ou tamanho de fonte no código de componente — só `var(--…)` e
   utilitários do Tailwind ligados aos tokens. Verificável por uma regra de
   lint ou por um teste de varredura do código-fonte; entregue o mecanismo, não
   só a promessa.
8. **`pnpm tokens:check` verde**: `tokens.gerado.css` está sincronizado com o
   contrato, ou seja, ninguém editou o gerado à mão.
9. **Cor não é o único portador de informação** em nenhum componente de estado
   (badge, alerta, toast, saldo, série de gráfico).
10. **Vocabulário obrigatório respeitado** em nome de componente, nome de
    *prop*, rótulo e texto de Storybook. Nenhum termo proibido da seção 6 do
    glossário aparece.
11. **`pnpm lint`, `pnpm typecheck`, `pnpm test` e `pnpm build` verdes**, e
    `src/testes/andaime.teste.tsx` continua passando.
12. **Contrato intacto**: `git status --short packages/contracts` vazio.
13. Todos os comandos da §8 verdes, com saída real colada no relatório.

## 8. Comandos de verificação

Rode a partir de `apps/web`, salvo onde indicado. Os comandos são idênticos no
Windows e no Linux/macOS porque tudo passa por `pnpm`; os alvos equivalentes na
raiz são `make lint-web` / `make test-web` / `make typecheck` e
`.\tasks.ps1 lint-web` / `.\tasks.ps1 test-web` / `.\tasks.ps1 typecheck`.

```bash
cd apps/web && pnpm install
```

Tokens sincronizados com o contrato (ninguém editou o gerado à mão):

```bash
pnpm tokens:check
```

**Saída esperada:** sucesso, sem diferença apontada.

Lint, tipos, testes e build:

```bash
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

**Saída esperada:** ESLint sem erro; `tsc --noEmit` sem erro; Vitest com todos
os testes passando, **incluindo** `src/testes/andaime.teste.tsx`; `next build`
concluindo.

Storybook — build estático e axe em todas as histórias:

```bash
pnpm build-storybook
pnpm test:storybook
```

**Saída esperada:** build sem erro; test-runner sem violação `serious` nem
`critical`, em ambos os temas.

Teste de contraste dos 124 pares, isolado e verboso:

```bash
pnpm vitest run src/testes/design-system/contraste.teste.ts --reporter=verbose
```

**Saída esperada:** 124 asserções aprovadas, nenhuma pulada.

*Benchmark* da data-table, com o tempo impresso:

```bash
pnpm vitest run src/testes/dominio/tabela-de-dados.desempenho.teste.tsx --reporter=verbose
```

**Saída esperada:** menos de 100 linhas no DOM para 10.000 itens e tempo de
montagem abaixo de 1 s, com o valor real impresso.

Contrato não foi tocado (a partir da raiz do repositório):

```bash
git status --short packages/contracts
```

**Saída esperada:** nada.

## 9. Proibições

1. **Não edite `packages/contracts/`**, `design-tokens.json` inclusive. Falta
   uma cor, um nível de `camada`, um tamanho? Isso é RFC em `docs/rfc/`, no
   formato de `docs/rfc/README.md` — nunca um valor escrito à mão.
2. **Não escreva valor literal** de cor, espaçamento, raio, sombra, duração,
   `z-index` ou tamanho de fonte em componente nenhum. Nem "só nesse caso", nem
   "só no Storybook".
3. **Não consuma token primitivo** (`--primitivo-cor-*`) na interface. Consuma o
   semântico do tema. O tema escuro não é inversão do claro.
4. **Não invente `z-index`.** A escala `camada` tem dez níveis.
5. **Não edite `src/estilos/tokens.gerado.css`** nem
   `scripts/tokens-para-css.mjs`. O CSS é gerado; regere com `pnpm tokens`.
6. **Não crie uma segunda verdade sobre o tema.** O atributo `data-tema` no
   `<html>`, escrito pelo `ProvedorDeTema`, é a única. Não introduza classe
   `.dark`, `localStorage` paralelo ou contexto próprio.
7. **Não escreva páginas nem rotas** em `src/app/**` — F8 e F9b. Você entrega
   componentes e histórias.
8. **Não chame a API.** Storybook usa dados fixos escritos à mão. Nenhum `fetch`
   real, nenhum uso de `src/lib/api/cliente.ts`.
9. **Não persista preferência de colunas** da data-table em backend nem em
   `localStorage`: é *prop* controlada. A persistência por usuário é da **F11**
   (`preferencias_colunas`).
10. **Não use cor como único portador de informação** (WCAG 2.2, 1.4.1), e não
    ultrapasse 8 séries de gráfico repetindo ou clareando cor — agregue em
    "outros".
11. **Não remova `outline` sem substituir** por indicador de foco equivalente
    (critérios 2.4.7 e 2.4.11). O anel do contrato é 2 px com deslocamento de
    2 px.
12. **Não ignore `prefers-reduced-motion`**, e não crie animação que atrase
    confirmação de ação — regra de produto declarada no próprio token de
    movimento.
13. **Não use os termos proibidos** do glossário: é *marcação* (nunca "batida"),
    *tratamento* (nunca "ajuste de marcação"), *apuração* (nunca "cálculo"),
    *colaborador* (nunca "funcionário"), *saldo credor/devedor* (nunca "banco
    positivo/negativo").
14. **Não quebre `src/testes/andaime.teste.tsx`** nem edite o arquivo.
15. **Não declare a fase pronta sem rodar os comandos da §8 e colar a saída
    real.** "Storybook está bonito" não é critério; "axe sem violação
    `serious` em 87 histórias nos dois temas" é.
