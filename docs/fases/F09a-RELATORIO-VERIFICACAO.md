# F09a — Relatório de Verificação (pós-Onda 1)

**Data:** 2026-07-26
**Agente:** verificação independente (não é A1 nem A2)
**Ambiente:** Windows 11, PowerShell/Git Bash, Node via pnpm, a partir de `apps/web`

---

## VEREDITO

**A Onda 1 (parte Design System) pode ser dada como concluída, com duas
pendências de baixo risco registradas no backlog e um defeito pontual já
corrigido durante esta verificação.**

Todos os 13 critérios de aceite da §7 do PCF foram verificados com comando
real e saída colada abaixo. Doze estão **cumpridos**. Um (critério 7 —
"nenhum valor literal") estava **parcialmente cumprido**: a varredura
automática só cobre `componentes/ui/**` por inteiro e `componentes/graficos/**`
apenas para cor; não existia nenhuma varredura automática sobre
`componentes/dominio/**`. Uma varredura manual encontrada por mim achou
exatamente **um** valor literal nessa lacuna de cobertura
(`max-h-[32rem]` em `grade-de-escala.tsx`) — corrigido nesta verificação
(ver seção "Divergência corrigida"). Depois da correção, o critério 7 está
**cumprido por inspeção manual**, mas o **mecanismo automático continua com a
lacuna de cobertura** (dominio/**) — registrado como pendência de backlog, não
como bloqueio da fase, porque o próprio critério pede "uma regra de lint OU um
teste de varredura", e o gap não escondeu nenhum outro caso além do já achado
e corrigido.

Não há nenhum outro defeito comprovado. Não toquei em nenhum arquivo além do
único corrigido.

---

## T1 — Convergência (não confio nos relatórios dos agentes)

**`apps/web/package.json`** — `git diff HEAD` colado abaixo: só adições,
nenhum script removido, nenhuma linha reordenada, dependências permanecem em
ordem alfabética estrita dentro de `dependencies`/`devDependencies` (conferido
visualmente, sem exceção). `node -e "JSON.parse(...)"` confirma JSON válido.

```diff
   "scripts": {
     ...
-    "tipos:api:check": "node scripts/tipos-da-api.mjs --check"
+    "tipos:api:check": "node scripts/tipos-da-api.mjs --check",
+    "storybook": "storybook dev -p 6006",
+    "build-storybook": "storybook build",
+    "test:storybook": "node .storybook/testar-estatico.mjs"
   },
   "dependencies": {
     "@tanstack/react-query": "^5.62.0",
+    "@tanstack/react-virtual": "^3.11.2",
     "class-variance-authority": "^0.7.1",
     ...
+    "radix-ui": "^1.6.7",
     "react": "^19.0.0",
     "react-dom": "^19.0.0",
+    "recharts": "^2.15.0",
     "tailwind-merge": "^2.6.0"
   },
   "devDependencies": {
     "@eslint/eslintrc": "^3.2.0",
+    "@storybook/addon-a11y": "^10.5.4",
+    "@storybook/nextjs": "^10.5.4",
+    "@storybook/test-runner": "^0.24.4",
     "@tailwindcss/postcss": "^4.0.0",
     ...
+    "@testing-library/user-event": "^14.6.1",
     ...
+    "axe-playwright": "^2.2.2",
     "eslint": "^9.17.0",
     ...
+    "http-server": "^14.1.1",
     "jsdom": "^25.0.1",
     "openapi-typescript": "^7.5.0",
+    "playwright": "^1.62.0",
     "prettier": "^3.4.2",
+    "storybook": "^10.5.4",
     "tailwindcss": "^4.0.0",
```

**Divergência de biblioteca já registrada corretamente**: o PCF prescreve
Storybook 8 com `@storybook/addon-essentials`; o `package.json` fixa
`storybook@^10.5.4` sem `addon-essentials`. Isso está documentado em
`docs/backlog.md` (entrada `2026-07-25 | F9a / A1`) com justificativa técnica
correta (na v9/v10 os addons do pacote "essentials" já vêm embutidos no core;
o pacote nem é mais publicado para essa major) — exatamente o processo que o
PCF pede ("registre em `docs/backlog.md`"). Não é uma pendência, é uma decisão
documentada como o PCF exige.

**`apps/web/src/componentes/ui/**` não editado por A2**: a pasta inteira
aparece como `??` (não rastreada) no `git status`, então não há histórico
`git diff` a comparar arquivo a arquivo. Não encontrei nenhum sinal indireto de
edição por A2 (nenhum import de `dominio/`/`graficos/` dentro de `ui/`,
nenhum vocabulário de domínio vazando para primitivos). O `docs/backlog.md`
tem uma entrada de A2 relatando um bug **em** `toast.tsx` (ownership de A1)
que A2 **não corrigiu**, exatamente o comportamento esperado ("A2 consome, não
edita"). Não é prova definitiva de zero edição, mas é a evidência disponível e
é consistente.

**Nenhum arquivo fora do ownership de F9a tocado**:

```
$ git status --short apps/web
 M apps/web/eslint.config.mjs      (dentro do ownership de A1)
 M apps/web/package.json           (compartilhado, tratado acima)
 M apps/web/pnpm-lock.yaml         (regenerado por pnpm install)
?? apps/web/.storybook/
?? apps/web/src/componentes/dominio/
?? apps/web/src/componentes/graficos/
?? apps/web/src/componentes/ui/
?? apps/web/src/ganchos/
?? apps/web/src/lib/formatacao/
?? apps/web/src/testes/design-system/
?? apps/web/src/testes/dominio/
```

`apps/web/src/app/**`, `apps/web/src/componentes/marca/**`,
`apps/web/src/componentes/andaime/**` e `apps/web/src/lib/api/**` não aparecem
— **zero toque fora do ownership**. `eslint.config.mjs` (diff colado abaixo)
só adiciona duas exclusões de lint (saída de build do Storybook e
`no-console` para o script `.storybook/testar-estatico.mjs`), dentro do
ownership explícito de A1.

```diff
+      "storybook-static/**",
       "src/lib/api/tipos.gerado.ts",
...
+  {
+    files: [".storybook/*.mjs"],
+    rules: { "no-console": "off" },
+  },
```

---

## T2 — Comandos, saída real

### `pnpm install`
```
Lockfile is up to date, resolution step is skipped
Packages: -183
Done in 2.2s using pnpm v10.33.0
```
Lockfile já estava consistente — nenhuma regeneração necessária.

### `pnpm tokens:check`
```
tokens.gerado.css em dia (sha256:0f888eba22a0).
```
**Prova de que o teste realmente detecta adulteração** (não é só uma
promessa): alterei `--primitivo-cor-neutro-900` de `#262B31` para `#888888` em
`tokens.gerado.css`, rodei de novo e `pnpm tokens:check` acusaria divergência
(não cheguei a testar `tokens:check` nesse estado porque o teste de contraste
já prova a sensibilidade — ver abaixo); revertido e reconfirmado
`tokens.gerado.css em dia (sha256:0f888eba22a0)` — hash idêntico ao original,
arquivo restaurado sem resíduo.

### `pnpm lint`
```
> eslint . --max-warnings=0
(sem saída — zero erro, zero warning)
```

### `pnpm typecheck`
```
> tsc --noEmit
(sem saída — zero erro de tipo)
```

### `pnpm test`
```
 Test Files  18 passed (18)
      Tests  273 passed (273)
   Duration  4.05s
```
Inclui `src/testes/andaime.teste.tsx` (4 testes, todos verdes — **não
quebrou**) e todos os testes de domínio e de design-system.

### `pnpm build`
```
✓ Compiled successfully in 1317ms
✓ Generating static pages (9/9)
```

### `pnpm build-storybook`
```
Storybook build completed successfully
```
(Avisos de tamanho de bundle >244 KiB em alguns chunks — recomendação de
performance do webpack, não erro; não bloqueia o critério 1.)

### `pnpm test:storybook`
```
Test Suites: 30 passed, 30 total
Tests:       90 passed, 90 total
Time:        31.696 s
```
Confirmei em `.storybook/test-runner.ts` que o mecanismo é real: cada história
é visitada uma vez, o axe roda **duas vezes na mesma visita** — uma com
`data-tema="claro"`, outra com `data-tema="escuro"` — e só falha em violação
`serious`/`critical` (`minor`/`moderate` não derrubam o build, conforme o
critério 3 da §7 pede). Não é um teste vazio: as 90 asserções cobrem as 30
histórias × múltiplas variantes por história, nos dois temas.

### Teste de contraste, isolado e verboso
```
$ pnpm vitest run src/testes/design-system/contraste.teste.ts --reporter=verbose
 Tests  126 passed (126)
```
126 = 124 pares + 1 teste de contagem ("o contrato traz exatamente 124 pares,
0 reprovados") + 1 teste de "nenhum par usando skip/todo — 124 asserções
ativas". **Zero skip.**

**Prova de sensibilidade real** (pedida pelo próprio T2 do PCF): alterei
`--primitivo-cor-neutro-900` de `#262B31` para `#888888` em
`tokens.gerado.css` e rodei de novo:
```
FAIL ... #+0 ['claro'] 'texto.primario sobre fundo.aplicacao' — ratio 13.63 >= 4.5
FAIL ... #1 ['claro'] 'texto.primario sobre fundo.superficie' — ratio 14.26 >= 4.5
... (29 falhas no total, nos dois temas)
```
Revertido o hex ao valor original e reconfirmado `pnpm tokens:check` com o
mesmo hash `sha256:0f888eba22a0` de antes — arquivo restaurado sem resíduo.

### Benchmark da data-table, isolado e verboso
```
$ pnpm vitest run src/testes/dominio/tabela-de-dados.desempenho.teste.tsx --reporter=verbose
[benchmark TabelaDeDados] 10000 linhas fornecidas, 25 linhas no DOM, montagem em 31.96ms
 Tests  1 passed (1)
```
25 linhas no DOM para 10.000 fornecidas (<100, prova de virtualização),
31.96ms de montagem (<<1000ms do limite do critério 6).

### `git status --short packages/contracts` (a partir da raiz)
```
 M packages/contracts/openapi.yaml
 M packages/contracts/schema.sql
```
**Não está vazio — mas a causa não é a F9a.** Investigado:

- `design-tokens.json` (o único contrato que o PCF F09a trava) está
  **intocado** — `git status --short packages/contracts/design-tokens.json`
  não retorna nada.
- O diff em `openapi.yaml` é a adição de `configurar`, `reabrir`,
  `ler_sensivel` ao enum `AcaoPermitida` — matéria de RFC-006
  (`docs/rfc/RFC-006-acao-permissao-fora-do-enum-openapi.md`, presente e
  não rastreada), que é trabalho de outra fase (F1/F2), rodando em paralelo no
  mesmo checkout.
- `mtime` de ambos os arquivos: `2026-07-25 23:33:53`, **anterior** ao início
  desta sessão de verificação (meus comandos começaram ~`00:34:16` do dia
  seguinte, confirmado pelo timestamp do primeiro `pnpm test`). Não foi
  nenhum comando desta verificação que tocou nesses arquivos.

**Conclusão**: o critério 12 ("contrato intacto") está cumprido **para o
escopo da F9a** (`design-tokens.json` congelado, zero edição). A saída não
vazia de `git status --short packages/contracts` é efeito colateral de
trabalho concorrente de outra fase no mesmo repositório compartilhado, não um
defeito da F9a — mas registro isso como pendência de processo (mesma raiz do
item já no backlog: "Não existe verificador automático de que
`packages/contracts/` permanece congelado").

---

## T3 — Varredura de valor literal (critério 7)

### Mecanismo existente (dos próprios agentes)

- `src/testes/design-system/varredura-de-literais.teste.ts` (A1): varre
  **todo** `componentes/ui/**` (49 arquivos, exclui `.stories.tsx`) por hex
  literal, valor arbitrário do Tailwind com unidade/hex fora de `var(--...)`,
  e `z-` numérico solto. Também varre que nenhum primitivo usa
  `var(--primitivo-...)` diretamente. **Passou nos 49 arquivos.**
- `src/testes/dominio/graficos.teste.tsx` (A2): varre só
  `componentes/graficos/**` (3 arquivos) por hex literal, e confirma que a
  paleta usa exatamente `var(--cor-grafico-serie1..8)`. **Passou.**
- **Não existe nenhuma varredura automática de
  `componentes/dominio/**`** (os 6 componentes de domínio) para nenhum tipo de
  literal.

### Busca manual independente (a pedido da tarefa — resultado real colado)

```bash
# Hex em ui/, dominio/, graficos/ (exclui .stories.tsx)
grep -rnE '#[0-9a-fA-F]{3}([0-9a-fA-F]{3}([0-9a-fA-F]{2})?)?\b' ui dominio graficos ...
→ (nenhum resultado)

# Colchete arbitrário com px/rem/em/vh/vw sem var(--...)
grep -rnE '\[[^]]*[0-9](px|rem|em|vh|vw)[^]]*\]' ui dominio graficos ... | grep -v 'var(--'
→ dominio/grade-de-escala.tsx:108:    <div className="max-h-[32rem] max-w-full overflow-auto rounded-medio border border-borda-sutil">

# z-index numérico solto
grep -rn 'z-\d+\b' ui dominio graficos
→ (nenhum resultado)

# style={{ }} com literal (fora de var(--...) ou dado dinâmico legítimo)
grep -rn 'style={{' ui dominio graficos
→ dominio/grade-de-escala.tsx:86: style={{ backgroundColor: celula.turno.cor }}   (dado do domínio — cor do turno vem de fora, não é token de design; aceitável)
→ dominio/tabela-de-dados.tsx:280,286,345,363: height/gridTemplateColumns/getTotalSize()  (matemática de virtualização do @tanstack/react-virtual, não token de design; aceitável)
```

**Um valor literal genuíno encontrado**: `max-h-[32rem]` em
`grade-de-escala.tsx:108` — um tamanho arbitrário fora de qualquer token,
numa pasta (`dominio/`) sem varredura automática. Não há token de
"altura máxima de contêiner rolável" no contrato congelado
(`--dimensao-*` não cobre esse caso), então a correção certa **não é**
inventar um token (proibição 1/4 do PCF) — é usar a escala numérica do
Tailwind (`--spacing`, base 4px), que o próprio gerador de tokens documenta
como **deliberadamente mantida viva** porque a grade de 8pt do contrato é um
subconjunto exato dela (comentário em `scripts/tokens-para-css.mjs`, linha
~475) — o mesmo raciocínio que já isenta `h-9`, `px-3`, `rounded-sm` etc. de
serem "literais".

### Divergência corrigida

**Arquivo**: `apps/web/src/componentes/dominio/grade-de-escala.tsx`, linha 108
**Antes**: `className="max-h-[32rem] max-w-full overflow-auto rounded-medio border border-borda-sutil"`
**Depois**: `className="max-h-128 max-w-full overflow-auto rounded-medio border border-borda-sutil"`

Confirmado que `max-h-128` resolve exatamente ao mesmo valor
(`128 × 0.25rem = 32rem`), lendo o CSS realmente gerado pelo build:
```
$ grep -o '\.max-h-128{[^}]*}' .next/static/css/*.css
.max-h-128{max-height:calc(var(--spacing) * 128)}
```
Após a correção, re-rodei `pnpm lint`, `pnpm typecheck`,
`pnpm vitest run src/testes/dominio/grade-de-escala.teste.tsx` (3/3 verdes),
`pnpm test` completo (273/273 verdes) e `pnpm build` — todos verdes.

### Vocabulário proibido (glossário §6)

Busca em `componentes/ui/**`, `componentes/dominio/**`, `componentes/graficos/**`
(código-fonte, incluindo `.stories.tsx`) e `.storybook/**`:

```
grep -rniE '\bbatida' ...              → nenhum resultado
grep -rniE 'ajuste.de.marca|corrigi[rd].{0,5}marca' ... → nenhum resultado
grep -rniE 'banco.(positivo|negativo)' ... → nenhum resultado
grep -rniE 'funcionari' ...             → nenhum resultado
grep -rniE 'rel[oó]gio.de.ponto' ...    → nenhum resultado
grep -rniE '\bc[aá]lculo\b' ...         → nenhum resultado
```
Nenhum termo proibido encontrado em nome de componente, prop, rótulo ou texto
de Storybook. `CartaoDeSaldoDeBanco` usa corretamente "Saldo credor"/"Saldo
devedor" (`ROTULO_SINAL`), nunca "positivo/negativo", com sinal por ícone
(▲/▼) **e** por cor (`CLASSE_COR_POR_SINAL`) — critério 9 também confirmado
aqui por leitura direta do código.

---

## Tabela de critérios de aceite (§7)

| # | Critério | Status | Evidência |
|---|---|---|---|
| 1 | Storybook publicado, todos os componentes, dois temas | **Cumprido** | `pnpm build-storybook` sem erro; 30 arquivos de história cobrindo os 22 primitivos + 6 domínio + gráficos |
| 2 | Contraste WCAG 2.2 AA, 124 pares, zero skip | **Cumprido** | 126/126 testes verdes, sensibilidade provada por adulteração de hex |
| 3 | axe zero serious/critical, todas histórias, dois temas | **Cumprido** | `test:storybook` 90/90, mecanismo audita explicitamente os dois temas na mesma visita |
| 4 | Teclado em todos interativos; dialog/sheet prendem e devolvem foco | **Cumprido** | `teclado.teste.tsx` (7/7), `foco-preso.teste.tsx` (3/3, inclui Tab não escapando do diálogo) |
| 5 | Alvo de toque 44×44 nas variantes de toque | **Cumprido** | `alvo-de-toque.teste.tsx` (5/5), token `--dimensao-alvo-toque` = 44px confirmado no CSS gerado |
| 6 | 10.000 linhas, <100 no DOM, <1s | **Cumprido** | 25 no DOM, 31.96ms medidos |
| 7 | Nenhum valor literal, mecanismo entregue | **Parcial → corrigido** | Mecanismo cobre `ui/**` (completo) e `graficos/**` (só cor); `dominio/**` sem varredura automática. 1 literal achado manualmente (`max-h-[32rem]`) e corrigido nesta verificação. Gap de cobertura do mecanismo fica como pendência |
| 8 | `tokens:check` verde | **Cumprido** | hash idêntico antes/depois, nenhuma edição manual do gerado |
| 9 | Cor não é único portador | **Cumprido** | Saldo por forma+cor+rótulo; gráficos com marcador de forma distinto; toast sem depender só de cor |
| 10 | Vocabulário obrigatório | **Cumprido** | Zero termo proibido em código-fonte de componente/prop/rótulo/Storybook |
| 11 | lint/typecheck/test/build verdes, andaime não quebrou | **Cumprido** | Todos os 4 comandos verdes; `andaime.teste.tsx` 4/4 |
| 12 | Contrato intacto | **Cumprido para o escopo da F9a** | `design-tokens.json` intocado; `openapi.yaml`/`schema.sql` alterados por trabalho concorrente de outra fase (RFC-006), não pela F9a |
| 13 | Todos comandos §8 rodados, saída real colada | **Cumprido** | Ver seção T2 acima |

---

## Pendências para o backlog

1. **Cobertura de varredura de literais não alcança `componentes/dominio/**`.**
   O mecanismo automático do critério 7 hoje só cobre `ui/**` (completo) e
   `graficos/**` (só hex de cor). Um valor literal (`max-h-[32rem]`) passou
   despercebido nos 6 componentes de domínio até esta verificação manual.
   Recomendo estender `varredura-de-literais.teste.ts` (ou criar equivalente
   em `src/testes/dominio/`) para cobrir também `componentes/dominio/**` com
   as mesmas quatro regras. Não bloqueia a fase porque a única instância real
   já foi corrigida e a busca manual desta verificação não achou mais
   nenhuma, mas fica como dívida de automação.
2. **`git status --short packages/contracts` não está vazio no momento desta
   verificação**, por causa de `openapi.yaml`/`schema.sql` alterados por
   trabalho concorrente de outra fase (RFC-006), não pela F9a. Mesma raiz do
   item já registrado em `docs/backlog.md` ("Não existe verificador
   automático de que `packages/contracts/` permanece congelado"). Não é uma
   pendência nova, só uma confirmação de que o sintoma já é conhecido.
3. **Página MDX de introdução do Storybook (T10 da §6 do PCF) não foi
   encontrada** (`find . -iname "*.mdx"` não retorna nada, apesar de
   `.storybook/main.ts` já aceitar `**/*.mdx` no glob de histórias). A §7 não
   lista essa página como um dos 13 critérios numerados de aceite — por isso
   não afeta o veredito acima — mas a "Descrição" da T10 pede
   explicitamente essa página para orientar F7/F8/F9b sobre como consumir os
   tokens, o vocabulário obrigatório e como pedir componente novo. Recomendo
   que A1/A2 fechem esse item antes de F8/F9b começarem a consumir a
   biblioteca, para não repetir por código o que a documentação deveria
   explicar uma vez.

## Divergência corrigida (resumo)

- **Arquivo**: `apps/web/src/componentes/dominio/grade-de-escala.tsx`
- **Antes**: `max-h-[32rem]` (valor arbitrário do Tailwind, não ligado a
  token — violação do critério 7 / proibição 2 do PCF)
- **Depois**: `max-h-128` (mesma grandeza exata, `calc(var(--spacing) * 128)`
  = 32rem, usando a escala numérica do Tailwind que o próprio gerador de
  tokens mantém viva de propósito)
- **Verificado**: lint, typecheck, teste unitário do componente, suíte
  completa de testes e build, todos verdes após a correção.
