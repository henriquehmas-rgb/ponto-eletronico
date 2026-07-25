# Fonte original — entrega da identidade visual

Arquivos recebidos de Henrique em 26/07/2026 (`Brand_Identidade visual Seeg
Ponto.zip`), produzidos numa ferramenta de design externa (formato de
Canvas/Artifacts, componentes `<x-dc>` com lógica em `data-dc-script`).

| Arquivo | Conteúdo |
|---|---|
| `SEEG PONTO - Brand Board.dc.html` | Visão de uma página: nome, logotipo, cor, tipografia, ícones, tela de confirmação, documento legal |
| `SEEG Ponto - Manual de Marca.dc.html` | Versão paginada (13 páginas, formato A4) do mesmo conteúdo, com regras de uso e proteção do logotipo |
| `SEEG Ponto - Template de Apresentação.dc.html` | Capa e camadas de slide no padrão da marca, para uso comercial/institucional |
| `Canvas.dc.html` | Shell vazio do runtime (sem conteúdo próprio) |
| `deck-stage.js`, `doc-page.js`, `support.js` | Runtime de componente que renderiza os arquivos `.dc.html` acima |

## Por que não abrem sozinhos no navegador

`support.js` começa com `if (!window.React) throw ...` — estes arquivos
**dependem de `window.React` e do runtime de Canvas/Artifacts do Claude**
para renderizar. Abertos diretamente num navegador comum, o HTML estático
aparece, mas:

- as tabelas de contraste (calculadas em tempo de execução por
  `class Component extends DCLogic`) **não aparecem**;
- a alternância de tema clara/escura não funciona;
- os placeholders `{{ variavel }}` e `<sc-for>` aparecem como texto literal,
  não resolvido.

**Não são o formato de trabalho do projeto** — são o artefato de entrega.
Todo o conteúdo determinístico (nome, paleta, tipografia, SVG dos ícones,
especificação das telas) foi transcrito para
[`../identidade-visual.md`](../identidade-visual.md), que é a referência que
qualquer fase deve consultar. Estes arquivos ficam aqui só como prova de
proveniência — se precisar reabri-los para editar, use uma ferramenta
compatível com Claude Canvas/Artifacts (ou o Claude web, reanexando o zip
original).
