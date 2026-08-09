# RFC-022 — Extensão de `raio` e `sombra` para o padrão visual "superfícies macias"

**Status:** decidida (dono do produto, 09/08/2026 — importou um layout completo do Claude
Design e determinou adoção imediata como padrão oficial).

## Contexto

`packages/contracts/design-tokens.json` está congelado desde a Fase 0 (RFC-003 fixou
cor/tipografia). O dono do produto trouxe um protótipo completo (Claude Design,
projeto "SEEG Ponto", arquivo `SEEG Ponto.dc.html`) cobrindo os três canais do
produto — celular (10 telas), painel web do RH (8 seções) e totem — e pediu para
adotá-lo **agora** como o padrão oficial de interface, com implementação imediata.

Comparação token a token confirma que **cor e tipografia não mudam**: os valores
CSS do protótipo (`--marca:#4C5FCA`, `--marca-suave:#EDF1FF`, `--marca-borda:#DEE5FF`,
`--marca-forte:#3948A7`, famílias Schibsted Grotesk/IBM Plex Sans/IBM Plex Mono)
são exatamente `primitivo.cor.marca.600/100/200/700` e `tipografia.familia.*` já
congelados. O protótipo não inventou marca nova — aplicou a marca já decidida a
uma linguagem de superfície mais macia (raios grandes, sombras difusas de
"cartão flutuando") que a escala atual de `raio`/`sombra` não cobre.

## O que muda

`raio` (nível 3 atual, `grande`, é 16px — teto da escala) e `sombra` (nível 3
atual, `alta`, é uma sombra "material", apertada) não alcançam os valores que o
protótipo usa sistematicamente em cartão, folha modal e barra de navegação
inferior. Em vez de redefinir os níveis existentes (que continuam servindo grade
densa, tabela do painel de RH, célula, chip pequeno — nada disso muda), esta RFC
**estende** as duas escalas com um nível acima do que já existe:

### `raio` — dois novos passos, acima de `grande` (16px)

| Token | Valor | Uso |
|---|---|---|
| `raio.suave` | 22px | Cartão padrão (celular e painel): resumo do dia, item de lista, KPI. |
| `raio.pronunciado` | 28px | Cartão de destaque (hero do dia, formulário grande), folha modal, sheet inferior no celular. |

`raio.pleno` (9999px, pílula/avatar) não muda.

### `sombra` — nova família `flutuante`, paralela à `baixa/media/alta` existente

A escala existente continua valendo para UI densa (tabela, grade de apuração,
linha em foco). A nova família é para a "superfície flutuante" do celular e dos
cartões do painel — usa alfa mais baixo com blur mais alto (sombra mais difusa,
sem contorno duro), e inclui um realce interno (`inset`) que a escala atual não
tem.

| Token | Composição | Uso |
|---|---|---|
| `sombra.flutuante.chip` | `0 1px 2px rgba(22,26,30,.05), 0 6px 14px -10px rgba(22,26,30,.35)` | Pílula de navegação, botão-chip, badge com sombra. |
| `sombra.flutuante.cartao` | `0 1px 2px rgba(22,26,30,.04), 0 16px 32px -20px rgba(22,26,30,.30), inset 0 1px 0 rgba(255,255,255,.75)` | Cartão padrão — a maioria das superfícies do celular e do painel. |
| `sombra.flutuante.alta` | `0 28px 64px -28px rgba(22,26,30,.40), 0 2px 6px rgba(22,26,30,.05)` | Folha modal, diálogo, cartão de confirmação pós-marcação. |

Tema escuro usa alfa maior sobre preto puro (`rgba(0,0,0,...)`), sem `inset`
claro — ver valores exatos em `apps/web/src/estilos/tokens.gerado.css`.

## O que NÃO muda (confirmado, não decisão desta RFC)

- Cor: nenhum primitivo nem alias novo. `marca`/`sucesso`/`atencao`/`erro`/`info`
  todos batem exatamente com o protótipo.
- Tipografia: família, escala modular e pesos não mudam. Schibsted Grotesk
  continua reservada a título de página e número-destaque (não título de
  seção/cartão) — o protótipo respeita essa regra em todas as telas.
- Espaçamento: grade de 8pt não muda.
- `raio.pequeno`/`medio`/`grande` e `sombra.baixa`/`media`/`alta`: continuam
  existindo e servindo o que já serviam. Nada foi removido.

## Consequência

`docs/design-system-oficial.md` (novo, ver raiz do repo) formaliza o catálogo de
padrões de componente (cartão, chip, badge de status, tile de KPI, navegação
inferior, estado vazio, item de lista com avatar) construídos sobre estes tokens
— é o documento que qualquer tela nova do produto deve seguir a partir de agora.
