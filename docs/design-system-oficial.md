# Design system oficial — "superfícies macias"

**Status: padrão oficial, em vigor a partir de 09/08/2026.** Toda tela nova do
produto (celular, painel web do RH, totem) segue este documento. Toda tela
existente é migrada para ele conforme reescrita — não é obrigatório reescrever
tudo de uma vez, mas nada novo nasce fora dele.

Este documento nasce da importação de um protótipo completo do Claude Design
(projeto "SEEG Ponto", arquivo `SEEG Ponto.dc.html`) para o padrão oficial do
produto, decidida pelo dono do produto. Ver [`RFC-022`](rfc/RFC-022-extensao-de-raio-e-sombra-para-superficies-macias.md)
para a extensão de tokens que este padrão exigiu.

## O que muda e o que não muda

**Não muda** — já estava congelado desde a Fase 0 (RFC-003) e o protótipo
confirma, token a token, que continua certo:
- Cor: `marca` = indigo (`#4C5FCA`), toda a paleta semântica de
  `packages/contracts/design-tokens.json`.
- Tipografia: `Schibsted Grotesk` (display — **só** título de página e número
  de indicador, nunca título de seção/cartão), `IBM Plex Sans` (corpo/UI),
  `IBM Plex Mono` (NSR, hash, qualquer identificador de conferir
  caractere a caractere).
- Espaçamento: grade de 8pt.

**Muda** — a linguagem de superfície fica mais macia (raio maior, sombra mais
difusa e realçada) do que o que já existia:
- `raio.suave` (22px) e `raio.pronunciado` (28px) — novos, acima do antigo teto
  `raio.grande` (16px). Ver RFC-022.
- `sombra.flutuanteChip` / `flutuanteCartao` / `flutuanteAlta` — novas, mais
  difusas que `sombra.baixa/media/alta`, com realce interno (`inset`) na
  variante `cartao`. Ver RFC-022.
- `raio.pequeno/medio/grande` e `sombra.baixa/media/alta` **continuam
  existindo** — servem grade densa, tabela do painel de RH, célula, chip
  pequeno. Não é para trocar tudo por `suave`/`pronunciado` às cegas.

## Regra de superfície

| Elemento | Raio | Sombra | Fundo |
|---|---|---|---|
| Cartão padrão (resumo do dia, item de lista, tile de KPI) | `rounded-suave` | `shadow-flutuante-cartao` | `bg-fundo-superficie` |
| Cartão de destaque (hero, formulário grande) / folha modal / sheet inferior | `rounded-pronunciado` | `shadow-flutuante-alta` | `bg-fundo-superficie` |
| Pílula (chip, navegação inferior, filtro) | `rounded-pleno` | `shadow-flutuante-chip` | `bg-fundo-superficie` |
| Botão primário | `rounded-[16px]` (celular) / `rounded-pleno` (painel) | nenhuma | `bg-fundo-inverso` `text-texto-inverso` |
| Tabela / grade densa (painel de RH) | `rounded-medio` no container, `rounded-nulo` na célula | `shadow-baixa` | `bg-fundo-superficie` |
| Badge de status | `rounded-pleno` | nenhuma | `bg-estado-<x>-fundo` `text-estado-<x>-texto` |

## Catálogo de padrões

Todos os exemplos usam os primitivos do projeto (`Cartao` de
`componentes/ui/card.tsx`, `cn()`, tokens via classe Tailwind derivada —
nunca cor/raio/sombra literal, mesma regra que já vale em `globais.css`).

### 1. Cartão flutuante (o padrão mais usado)

```tsx
<Cartao className="rounded-suave shadow-flutuante-cartao gap-[var(--espacamento-3)]">
  ...
</Cartao>
```

### 2. Cartão hero com gradiente de marca (resumo do dia, celular)

Único lugar do produto com gradiente de marca sólido — reservado para o
cartão de maior destaque da tela inicial do colaborador.

```tsx
<div className="relative overflow-hidden rounded-pronunciado p-[var(--espacamento-5)]
                 bg-gradient-to-br from-[var(--primitivo-cor-marca-500)]
                 via-[var(--primitivo-cor-marca-600)] to-[var(--primitivo-cor-marca-800)]
                 shadow-flutuante-alta text-texto-inverso">
  ...
</div>
```

### 3. Pílula / chip flutuante

```tsx
<span className="inline-flex items-center gap-2 rounded-pleno px-3 py-1.5
                  bg-fundo-superficie shadow-flutuante-chip
                  text-[13px] font-semibold text-texto-secundario">
  {rotulo}
</span>
```

### 4. Badge de status semântico (usar o `Selo`/`Badge` já existente, não recriar)

```tsx
<Selo variant="sucesso">Aprovado</Selo>
<Selo variant="atencao">Em análise</Selo>
<Selo variant="erro">Recusado</Selo>
```

Ver `componentes/ui/badge.tsx` — se a variante que você precisa não existir
lá, adicione nele, não crie um badge solto na página.

### 5. Tile de KPI (número-destaque em Schibsted Grotesk)

```tsx
<Cartao className="rounded-suave shadow-flutuante-cartao p-[var(--espacamento-4)]">
  <p className="estilo-legenda text-texto-terciario">{rotulo}</p>
  <p className="font-display font-semibold text-[26px] tracking-[-0.02em]
                tabular-nums text-estado-sucesso-texto">
    {valor}
  </p>
  <p className="estilo-legenda text-texto-desabilitado">{nota}</p>
</Cartao>
```

### 6. Item de lista com avatar circular de iniciais

```tsx
<div className="flex items-center gap-[var(--espacamento-3)] rounded-suave
                 bg-fundo-superficie shadow-flutuante-cartao p-[var(--espacamento-3)]">
  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-pleno
                    bg-acao-sutil-fundo text-acao-sutil-texto text-[11px] font-semibold">
    {iniciais}
  </span>
  <div className="min-w-0 flex-1">
    <p className="truncate text-[14px] font-medium">{nome}</p>
    <p className="truncate text-[11px] text-texto-terciario">{subtitulo}</p>
  </div>
</div>
```

### 7. Navegação inferior (celular) — barra flutuante, não fixa na borda

```tsx
<nav className="fixed inset-x-4 bottom-6 z-40 flex items-center gap-0.5
                 rounded-pronunciado border border-borda-sutil
                 bg-fundo-superficie/90 backdrop-blur-xl shadow-flutuante-alta p-2">
  {abas.map((a) => (
    <button key={a.id} className={cn(
      "flex flex-1 flex-col items-center gap-1 rounded-[18px] py-2",
      a.ativa ? "bg-fundo-inverso text-texto-inverso" : "text-texto-terciario",
    )}>
      {a.icone}
      <span className="text-[10.5px] font-semibold">{a.nome}</span>
    </button>
  ))}
</nav>
```

### 8. Estado vazio

```tsx
<div className="rounded-suave border border-dashed border-borda-padrao p-6 text-center">
  <p className="text-[13px] font-semibold text-estado-sucesso-texto">{titulo}</p>
  <p className="mt-1 text-[12px] text-texto-terciario">{descricao}</p>
</div>
```

## Escopo — o que o protótipo cobre e onde vive na aplicação real

O protótipo (`SEEG Ponto.dc.html`, projeto Claude Design) é uma ferramenta de
prototipagem, não código de produção — usa uma notação própria (`x-dc`,
`sc-if`/`sc-for`, `{{ }}`) interpretada por `support.js` (runtime da
ferramenta) e renderiza dentro de uma moldura de iPhone (`ios-frame.jsx`, só
para a pré-visualização do designer). **Nenhum dos dois arquivos entra na
aplicação** — o que entra é o padrão visual, reimplementado nos componentes
reais do Next.js abaixo.

| Tela do protótipo | Rota real | Situação |
|---|---|---|
| Entrar | `/` | existe, migrar |
| Onboarding (3 passos) | — | não existe rota hoje; fora do escopo desta rodada |
| Início (resumo do dia) | `/eu` | existe, migrar |
| Registrar ponto | `/eu/registrar` | existe, migrar |
| Confirmação da marcação | `/eu/registrar` (estado pós-captura) | existe, migrar |
| Extrato | `/eu/extrato` | existe, migrar |
| Solicitações | `/eu/solicitacoes` | existe, migrar |
| Nova solicitação | `/eu/solicitacoes/nova` | existe, migrar |
| Comprovantes | `/eu/comprovantes` | existe, migrar |
| Perfil | `/eu/perfil` | existe, migrar |
| Painel · Visão geral | `/painel` | existe, migrar |
| Painel · Apuração | `/painel/apuracao` | existe, migrar |
| Painel · Escalas | `/painel/escalas` | existe, migrar |
| Painel · Colaboradores | `/painel/cadastros/colaboradores` | existe, migrar |
| Painel · Aprovações | a confirmar (pode estar dentro de solicitações/apuração) | investigar antes de criar rota nova |
| Painel · Antifraude | `/painel/antifraude` | existe, migrar |
| Painel · Relatórios | `/painel/relatorios` | existe, migrar |
| Painel · Dispositivos | `/painel/cadastros/dispositivos` | existe, migrar |
| Totem | — | sem rota/app hoje; fora do escopo desta rodada |

## Regra de execução

- Nunca literal: toda cor/raio/sombra/espaçamento vem de token
  (`var(--...)` ou classe Tailwind derivada). Se precisar de um valor que não
  existe, é RFC, não gambiarra em CSS solto.
- Reaproveite os primitivos de `componentes/ui/*` (`Cartao`, `Botao`, `Selo`,
  `Entrada`...) em vez de recriar HTML cru — o protótipo é referência visual,
  não referência de implementação.
- Schibsted Grotesk é escassa: só título de página (`h1` da tela) e
  número-destaque. Todo o resto é IBM Plex Sans.
- Teste os dois temas (claro/escuro) — os tokens novos já têm par nos dois,
  ninguém precisa inventar valor de tema escuro à mão.
