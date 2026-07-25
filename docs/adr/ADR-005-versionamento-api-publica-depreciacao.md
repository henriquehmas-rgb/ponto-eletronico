# ADR-005 — Versionamento da API pública e política de depreciação

**Status:** Aceito · 25/07/2026
**Decisores:** SEEG — arquitetura
**Fases afetadas:** F0 (define o contrato), F13 (implementa a API pública), todas (consomem)

---

## Contexto

A API não é detalhe de implementação: ela é produto. Do outro lado dela ficam
ERPs, sistemas de folha (Domínio, Alterdata, TOTVS, Senior, Sankhya, Questor,
Fortes, Contmatic), catracas de terceiros e integrações sob medida do cliente.
Esses consumidores têm ciclos de release próprios, medidos em trimestres, e
alguns são integrações escritas uma vez e nunca mais tocadas.

Ao mesmo tempo, o produto é novo e vai mudar muito: 16 fases, das quais 15
adicionam recurso. Precisamos evoluir rápido sem quebrar quem já integrou — e
sem cair na armadilha oposta, que é congelar tudo e acumular dívida.

Existe ainda um agravante próprio deste domínio: parte da API tem
**consequência fiscal**. Um cliente que perde a capacidade de baixar o AFD por
causa de uma mudança de contrato não tem só um incidente de integração; tem um
problema com a fiscalização do trabalho.

## Decisão

**Versão maior no caminho da URL (`/v1`), evolução apenas aditiva dentro da
versão, e depreciação anunciada por cabeçalho com prazo mínimo de 180 dias.**

1. **`/v1` é o contrato.** `packages/contracts/openapi.yaml` é a fonte da
   verdade; a implementação é conferida contra ele no CI (`spectral` na F0,
   Schemathesis na F13). Divergência entre código e contrato é falha de build,
   não item de backlog.
2. **Dentro de `/v1`, só mudança compatível.** Permitido: novo endpoint, novo
   campo **opcional** na requisição, novo campo na resposta, novo valor em enum
   **de saída** documentado como extensível, novo cabeçalho opcional, novo
   código de erro. Proibido: remover ou renomear campo, tornar campo opcional em
   obrigatório, estreitar tipo ou formato, mudar o significado de um valor, mudar
   o status HTTP de um caso já documentado.
3. **Cliente tolerante é requisito publicado.** A documentação exige que o
   consumidor ignore campos desconhecidos e não trate enum de saída como fechado.
   Sem isso, "campo novo na resposta" seria quebra — e o custo de nunca poder
   adicionar campo é alto demais.
4. **Depreciação com prazo.** Recurso a ser removido responde com
   `Deprecation: <data>` e `Sunset: <data>` (RFC 8594) e `Link` para o guia de
   migração, com **no mínimo 180 dias** entre o anúncio e a remoção, e a marca
   `deprecated: true` no OpenAPI. Nenhum recurso é removido dentro de `/v1`: ele
   deixa de existir em `/v2`.
5. **Eventos versionam separado.** `packages/contracts/events.yaml` versiona por
   inteiro no envelope; mudança incompatível publica o mesmo nome de evento na
   versão seguinte e mantém a anterior por, no mínimo, um ciclo de 180 dias.
6. **Erros são contrato.** O campo `codigo` de `errors.yaml`
   (`PONTO-<CATEGORIA>-<NNN>`) é o identificador estável; `title` e `detail` são
   texto e podem mudar a qualquer momento. Código nunca é renumerado nem
   reaproveitado: erro que sai de uso vira `situacao: descontinuado`.
7. **Ambiente é separado da versão.** Sandbox e produção usam a mesma `/v1`, com
   credenciais distintas — nunca um `/v1-beta`.

## Alternativas consideradas

**Versão por cabeçalho (`Accept: application/vnd.ponto.v1+json`) ou por
media type.** Mais purista em REST e descartado por atrito operacional: a maior
parte dos integradores brasileiros de folha testa com cURL, Postman e navegador,
e um `GET` colável na barra de endereço economiza horas de suporte. Também
complica cache, log e roteamento no Traefik.

**Versão por query string (`?versao=1`).** Fácil de esquecer, fácil de ser
removida por um proxy intermediário, e polui a chave de cache.

**Sem versão, só mudança compatível para sempre.** Descartado por honestidade:
em algum momento a v2 vai precisar mudar algo estruturalmente — provavelmente o
modelo de múltiplos vínculos ou a representação de banco de horas. Fingir que
não vai acontecer produz gambiarra com campo `campoNovo2`.

**Versionamento por recurso (`/marcacoes/v2`).** Dá granularidade fina e cria um
produto impossível de documentar e de testar como conjunto: cada cliente passa a
usar uma combinação diferente de versões.

**Depreciação sem prazo fixo ("avisamos quando der").** Descartado porque
transfere risco para quem integra e, no limite, torna toda mudança impossível
por medo.

## Consequências

**Positivas.** O consumidor consegue planejar. A regra "só aditivo" é
verificável automaticamente por diff de OpenAPI no CI, então a disciplina não
depende de revisão humana. O catálogo de erros estável permite que o web e o
mobile traduzam o `codigo` para mensagem localizada sem depender do texto do
servidor.

**Negativas e mitigações.** (a) Campo mal modelado na F0 vive até a v2 — mitigado
pelo fato de a Fase 0 existir justamente para congelar contrato com revisão
humana antes de qualquer implementação, e pelo protocolo de RFC
(`docs/rfc/README.md`) enquanto o congelamento ainda é recente. (b) O acúmulo de
campos aditivos degrada a legibilidade do contrato ao longo dos anos; mitigado
por marcar `deprecated` cedo, mesmo que a remoção só ocorra na v2. (c) Manter
`/v1` e `/v2` simultaneamente no futuro custa manutenção dupla; a decisão
explícita é que só existirão duas versões maiores vivas ao mesmo tempo, com a
mais antiga em janela de sunset. (d) A regra de cliente tolerante precisa estar
no topo do portal de documentação, não enterrada — integrador que trata enum
como fechado vai quebrar, e a culpa prática recai sobre nós.
