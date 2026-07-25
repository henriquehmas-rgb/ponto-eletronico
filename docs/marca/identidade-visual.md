# Identidade visual — SEEG Ponto

> Referência durável, em texto puro. Transcrita de `SEEG PONTO - Brand Board`
> e `SEEG Ponto - Manual de Marca` (entregues por Henrique em 26/07/2026,
> produzidos em ferramenta de design externa). Os arquivos originais estão em
> [`fonte-original/`](fonte-original/) — dependem do runtime de Canvas/Artifacts
> do Claude para renderizar interativamente; **este arquivo é a fonte
> consultável por qualquer fase sem essa dependência.**
>
> Decisão que trouxe isto para o contrato: [RFC-003](../rfc/RFC-003-identidade-visual-oficial.md).
> Já implementado em código: `apps/web/src/componentes/marca/`,
> `packages/contracts/design-tokens.json` (tipografia). O que falta está
> marcado explicitamente em cada seção.

---

## 1. Nome

**SEEG Ponto.** SEEG é a marca já estabelecida da empresa; Ponto nomeia a
categoria sem margem para dúvida — para o RH, para o auditor, para quem bate
o registro todo dia. Como o nome em si é literal, o resto do sistema —
símbolo, tom de voz, cor — carrega sozinho o argumento de prova justa, não
vigilância.

Alternativas exploradas e descartadas:

| Nome | Conceito | Por que não |
|---|---|---|
| aponta | De apontamento de horas — o verbo do próprio ofício | Nasce do jargão de horas, literalidade parcial |
| kairo | Do grego kairós — o tempo oportuno | Pede soletração, conceito erudito, não se explica no chão de fábrica |
| cadência | Ritmo de trabalho sustentável | Acento/cedilha, colide com Cadence (software), diz "ritmo" não "prova" |
| lastro | O que dá valor de prova a um registro | Frio, bancário — erra o lado humano |
| prumo | Instrumento que encontra a vertical exata | Homônimo em logística, metáfora menos óbvia |

**Todo nome exige busca de anterioridade no INPI (classes 9, 35 e 42) antes do
registro** — pendência externa, já registrada em `PROJETO.md` §1.

---

## 2. Posicionamento

Um sistema de ponto carrega, por padrão, a leitura de "o patrão te vigiando".
A SEEG Ponto existe para o oposto: **o mesmo registro que comprova a jornada
cumprida para a empresa comprova a hora extra devida ao trabalhador.** Prova
justa, não vigilância.

| Somos | Não somos |
|---|---|
| **Preciso** — instrumento de medida com fé pública, números tabulares, terminologia exata | Vigilante |
| **Claro** — uma pergunta, uma resposta: registrou ou não registrou; todo estado tem forma e palavra, nunca só cor | Burocrático |
| **Justo** — a mesma prova serve aos dois lados | Frio |

---

## 3. Logotipo

O símbolo é um traço de confirmação pousado sobre a linha do dia — **não é
relógio, não é olho**: é o gesto de quem confere um registro, no ponto certo.

- **Traço diagonal** — a conferência, o "sim, está certo".
- **Linha horizontal** — a jornada, o dia que se mede.

### Símbolo isolado (SVG fonte)

Implementado em `apps/web/src/componentes/marca/simbolo.tsx`.

```svg
<svg viewBox="0 0 32 32" fill="none">
  <path d="M8.6 18.6 13.6 24.1 24.2 7.6" stroke="currentColor" stroke-width="2.6"
        stroke-linecap="round" stroke-linejoin="round" />
  <path d="M6.4 26 H25.6" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" />
</svg>
```

Cor sempre por `currentColor` — funciona em qualquer cor de texto, tema
claro/escuro, monocromático (preto ou branco puro) e negativo, sem redesenho.

### Área de proteção e tamanho mínimo

- **Área de proteção:** nunca menor que a altura do próprio traço, em todos os
  lados. Nenhum outro elemento — texto, borda, outro logotipo — entra nesse
  espaço.
- **Tamanho mínimo:** legível a partir de **16 px** (o tamanho do favicon).
  Testado e confirmado nesse tamanho.

### Uso incorreto

Não fazer, em nenhuma hipótese:

1. **Recolorir fora da paleta** (gradiente, cor fora da escala de marca).
2. **Distorcer proporções** (esticar/comprimir).
3. **Adicionar efeitos ou relevo** (sombra projetada, brilho, 3D).
4. **Usar sobre fundo poluído** (textura, padrão, imagem com muito contraste).

### Logotipo completo (símbolo + nome)

Implementado em `apps/web/src/componentes/marca/logotipo.tsx` — **texto real
em DOM** (não SVG `<text>`), para manter seletividade, acessibilidade e
reflow. O nome usa a voz de display (Schibsted Grotesk, peso 700).

Regra do Manual: **em ícone de app, nunca a palavra "SEEG PONTO" inteira** —
apenas o símbolo isolado, sobre fundo sólido de marca.

---

## 4. Cor

Índigo `#4C5FCA` — distinto do azul corporativo genérico, sóbrio sem ser
frio. **Cor nunca é o único canal de informação: estado sempre tem forma e
rótulo.**

A paleta abaixo é idêntica, tom a tom, à já implementada em
`packages/contracts/design-tokens.json` (conferido nesta integração — o
Manual foi construído a partir dela, não o contrário). **Nenhuma mudança de
contrato de cor foi necessária.**

### Marca · índigo — 11 tons

| Tom | Hex | Tom | Hex | Tom | Hex |
|---|---|---|---|---|---|
| 50 | `#F1F3FC` | 400 | `#7D8CDB` | 800 | `#33408D` |
| 100 | `#E3E7F9` | 500 | `#5F71D3` | 900 | `#2B3670` |
| 200 | `#C9D0F2` | **600** | **`#4C5FCA`** (base) | 950 | `#191F45` |
| 300 | `#A7B2E9` | 700 | `#3D4DAF` | | |

### Semânticas (7 tons cada: fundo, fundo-forte, sólido-claro, sólido, sólido-escuro, texto, texto-escuro)

| Estado | Fundo suave | Sólido | Texto (tema claro) |
|---|---|---|---|
| Sucesso | `#EBF7F0` | `#27935B` | `#14603A` |
| Atenção | `#FDF6E7` | `#D99A0B` | `#8A5B00` |
| Erro | `#FCEEF0` | `#C9354B` | `#A32239` |
| Informação | `#E9F6FA` | `#0F7E9E` | `#0A5A70` |

Tabela completa (todos os 7 tons por escala, tema claro e escuro) vive em
`design-tokens.json` — os valores acima são os de maior exposição.

### Categóricas — 8 séries para gráficos

`C1 #5F71D3` `C2 #2BA3C4` `C3 #14A38B` `C4 #D99A0B` `C5 #E0703A` `C6 #DD5468`
`C7 #C75FA1` `C8 #9A6BD4` — uso em ordem fixa, sempre com rótulo direto na
série, nunca só cor. Para "outros": cinza neutro `#9A9EB5`.

### Neutros

Derivados do índigo (tinta fria, nunca cinza puro):
- Claro: texto primário `#171A29` · texto secundário `#565B76` · fundo `#F7F8FB` · superfície `#FFFFFF`
- Escuro: texto primário `#EDEFF7` · texto secundário `#A6ABC4` · fundo `#0C0E1A` · superfície `#14172A`

Todos os pares texto-sobre-fundo estão **medidos** (WCAG 2.2, não estimados)
em `design-tokens.json` — 124 pares, todos ≥ AA. Não remedir a partir deste
documento; ele é resumo, o contrato é a fonte.

---

## 5. Tipografia

Três vozes, uma régua. Licenças **SIL OFL 1.1** — uso comercial e embed em
SaaS liberados. Implementado via `next/font/google` (self-hospedado, sem
chamada a CDN em produção) em `apps/web/src/app/layout.tsx`.

| Voz | Fonte | Pesos carregados | Uso |
|---|---|---|---|
| Display | **Schibsted Grotesk** | 500, 600, 700, 800 | Logotipo, título de página (1 por tela), número-destaque |
| Texto/UI | **IBM Plex Sans** | 400, 500, 600, 700 | Corpo, rótulo, tabela densa de RH — numerais tabulares (`tnum`) |
| Tabular | **IBM Plex Mono** | 400, 500, 600, 700 | Horas, NSR, hash, CRC-16, documento legal — tabular por construção |

**Escopo da voz de display, decisão explícita (RFC-003):** só
`tipografia.estilo.tituloPagina` (peso 700) e `tipografia.estilo.numeroDestaque`
(peso 600) usam Schibsted Grotesk. Os outros 8 estilos compostos —
`tituloSecao`, `tituloCartao` incluídos — permanecem em IBM Plex Sans, para
não ter fonte trocando a cada nível de título numa interface de uso diário de
8h. Se a F9a decidir que título de seção também merece a voz de display, é
mudança de contrato (nova RFC), não ajuste de CSS.

Amostra do Manual: números em `08:02:47` (mono, tabular) alinham
perfeitamente coluna a coluna — "cada dígito tem a mesma largura, colunas não
dançam entre linhas". Isso é **obrigatório**, não estético: coluna de horário
com numeral proporcional induz erro de leitura.

---

## 6. Ícones do domínio

Grade 24×24, traço 2, cantos redondos. **Sem olho, sem mira, sem relógio de
ponteiro** — instrumentos, não vigilância. Ainda não extraídos como
componentes React (fica para F9a/F7 conforme a tela que precisar de cada um);
o SVG fonte de cada um está aqui, pronto para copiar.

<details>
<summary>Reconhecimento facial</summary>

```svg
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M8 4H6.5A2.5 2.5 0 0 0 4 6.5V8"/><path d="M16 4h1.5A2.5 2.5 0 0 1 20 6.5V8"/>
  <path d="M20 16v1.5a2.5 2.5 0 0 1-2.5 2.5H16"/><path d="M4 16v1.5A2.5 2.5 0 0 0 6.5 20H8"/>
  <circle cx="9.4" cy="10.2" r="1" fill="currentColor" stroke="none"/>
  <circle cx="14.6" cy="10.2" r="1" fill="currentColor" stroke="none"/>
  <path d="M9.3 14.2c.7.8 1.6 1.2 2.7 1.2s2-.4 2.7-1.2"/>
</svg>
```
</details>

<details>
<summary>Prova de vida</summary>

```svg
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="3.3"/><path d="M19.8 10.4A8 8 0 0 0 6.9 6.2"/>
  <path d="M6.6 3.4l.2 3 3-.3"/><path d="M4.2 13.6a8 8 0 0 0 12.9 4.2"/><path d="M17.4 20.6l-.2-3-3 .3"/>
</svg>
```
</details>

<details>
<summary>Cerca virtual + GPS</summary>

```svg
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="4" y="4" width="16" height="16" rx="4.5" stroke-dasharray="3.1 3.1"/>
  <circle cx="12" cy="12" r="2.2" fill="currentColor" stroke="none"/>
</svg>
```
</details>

<details>
<summary>Offline — pendente de envio</summary>

```svg
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="8.2" stroke-dasharray="3.35 3.1"/><path d="M12 15.6V8.8"/><path d="M9 11.4 12 8.5l3 2.9"/>
</svg>
```
</details>

<details>
<summary>Banco de horas — crédito</summary>

```svg
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3.5" y="5" width="17" height="14" rx="2.5"/><path d="M7 10h4"/><path d="M7 14h3"/>
  <path d="M14.5 12h4.5"/><path d="M16.75 9.75v4.5"/>
</svg>
```
</details>

<details>
<summary>Banco de horas — débito</summary>

```svg
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3.5" y="5" width="17" height="14" rx="2.5"/><path d="M7 10h4"/><path d="M7 14h3"/><path d="M14.5 12h4.5"/>
</svg>
```
</details>

<details>
<summary>Escala e turno (12×36)</summary>

```svg
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="4" y="4" width="7" height="7" rx="1.8"/>
  <rect x="13" y="4" width="7" height="7" rx="1.8" fill="currentColor" stroke="none"/>
  <rect x="4" y="13" width="7" height="7" rx="1.8" fill="currentColor" stroke="none"/>
  <rect x="13" y="13" width="7" height="7" rx="1.8"/>
</svg>
```
</details>

<details>
<summary>Adicional noturno</summary>

```svg
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/><path d="M17 5h4"/><path d="M19 3v4"/>
</svg>
```
</details>

<details>
<summary>Marcação inconsistente (cor: <code>--cor-estado-atencao-texto</code>)</summary>

```svg
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M3.5 12h5.5"/><path d="M15 12h5.5"/><path d="M9.8 15.2 14.2 8.8"/>
</svg>
```
</details>

<details>
<summary>Período travado</summary>

```svg
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="5" y="10.5" width="14" height="9" rx="2.5"/><path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5"/>
  <circle cx="12" cy="15" r="1.4" fill="currentColor" stroke="none"/>
</svg>
```
</details>

<details>
<summary>Assinatura eletrônica</summary>

```svg
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M4 19.5h16"/><path d="M5.5 15.5c1.8-4.6 3.6-6.9 4.7-6.1 1.2.8-1.9 4.6-.7 5.4 1 .7 2.6-1 3.7-2.1"/>
  <path d="M14.8 14.6l1.6 1.6 3-3.3"/>
</svg>
```
</details>

---

## 7. Ícones de app e favicon

**Regra:** o símbolo isolado, sempre em fundo sólido de marca (`#4C5FCA`) —
nunca a palavra "SEEG PONTO" inteira num ícone de app.

| Uso | Tamanho | Status |
|---|---|---|
| Favicon web | 16 · 32 px | ✅ `apps/web/src/app/icon.svg` (SVG estático, escala perfeita) |
| Web app / PWA | 192 · 512 px | ✅ `apps/web/src/app/icon-192.png/route.tsx` e `icon-512.png/route.tsx` (gerados via `next/og`), referenciados em `apps/web/src/app/manifest.ts` |
| iOS tela inicial | 120 · 180 px | ✅ `apps/web/src/app/apple-icon.tsx` (180 px, gerado via `next/og`) |
| iOS App Store | 1024 px | ⏳ F7 (projeto Flutter ainda não existe) |
| Android adaptável | 108×108 dp, símbolo na zona segura 66/108 | ⏳ F7 |
| Google Play | 512 px | ⏳ F7 |

---

## 8. Especificação — tela de confirmação de registro (F7)

O momento mais importante do produto: 10 segundos, 2 a 4 vezes por dia, com
pressa, no sol, de luva. A resposta a "registrou?" precisa atravessar um
metro de distância.

- **Legível a um metro:** hora tabular grande (68 px no mockup), símbolo de
  estado com 128 px, título em display. **Tela sempre clara** neste momento —
  texto escuro sobre fundo claro vence o sol, independente do tema escolhido
  no resto do app.
- **Sem depender de som:** o estado chega por **quatro canais** — forma
  (✓ ou seta pendente), cor, palavra e vibração dupla no registro. Quem não
  ouve, vê; quem não vê cor, lê a forma.
- **Offline é honesto, não é erro:** tela âmbar (não vermelha) com NSR local
  visível — "seu horário já está guardado e assinado, será enviado quando a
  conexão voltar". Promete pouco, prova muito.
- **Toques:** botões com 48 px de altura; nada acionável abaixo de 44 px.

Dois estados de referência (copy exata do Manual):

| | Online | Offline |
|---|---|---|
| Círculo | 128 px, verde (`#EBF7F0` → `#14603A`) | 128 px, âmbar (`#FDF6E7` → `#8A5B00`) |
| Título | "Entrada registrada" | "Registrado no aparelho" |
| Rodapé | `NSR 004.519 · comprovante no aparelho` | `NSR local 000.087 · pendente de envio` |
| Ação | "Ver comprovante" (primário) + "Fechar" (secundário) | "Entendi" (primário, único) |

---

## 9. Especificação — documento legal (espelho de ponto, F11/F12)

**Preto sobre branco, 1 bit.** É assim que a marca chega ao auditor e ao
juiz — se funciona aqui, funciona em qualquer lugar. Sem cor, sem tema
escuro, sem glassmorphism: só hierarquia tipográfica e regra.

Cabeçalho: símbolo (26 px, preto) + "SEEG PONTO" (Schibsted Grotesk 700) à
esquerda; `REP-P · PORTARIA MTP Nº 671/2021` em mono, maiúsculo, à direita.
Título "ESPELHO DE PONTO ELETRÔNICO" com borda inferior de 2px. Grade de
identificação (empregador, colaborador, jornada, admissão) em mono. Tabela de
marcações com colunas `DATA · DIA · 1ª ENT · 1ª SAÍ · 2ª ENT · 2ª SAÍ ·
PREVISTO · REALIZADO · SALDO · NSR`, números em mono tabular. Rodapé:
`Assinado digitalmente — certificado ICP-Brasil A1 · SHA-256 [hash]` e URL de
autenticidade.

Isto é especificação de **layout visual**; o leiaute de **campos legais**
obrigatórios do espelho é o da Portaria 671/2021 em si (conferência
obrigatória na F12, `PROJETO.md` §8.1) — os dois precisam concordar, mas são
decisões diferentes.

---

## 10. Contato e domínios (placeholder, não confirmado)

O Manual cita `seegponto.com.br` (site), `marca@seegponto.com.br` (contato de
marca) e `seegponto.app/verificar` (URL de autenticação no documento legal).
**Nenhum destes foi verificado como registrado** — são convenção de nome
usada no material de marca, não confirmação de disponibilidade ou posse.
Registrar (ou confirmar posse) é ação de negócio, fora do escopo de código.

---

## 11. Fontes

- `fonte-original/` — os 4 arquivos entregues (`Brand Board`, `Manual de
  Marca`, `Template de Apresentação`, `Canvas`) + scripts de suporte do
  runtime de Canvas/Artifacts do Claude. Exigem esse runtime (`window.React`
  + `support.js`) para renderizar interativamente — abrir direto no navegador
  mostra HTML incompleto (as tabelas de contraste e a alternância de tema são
  geradas por esse runtime). O conteúdo determinístico deles está transcrito
  aqui.
- [RFC-003](../rfc/RFC-003-identidade-visual-oficial.md) — decisão que trouxe
  esta identidade para o contrato (tipografia) e a nota sobre a inconsistência
  de rótulo "recomendado" encontrada no Brand Board.
