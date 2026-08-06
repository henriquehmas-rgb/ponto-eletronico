# RFC-020 — Fila de revisão do gestor (marcações suspeitas) não tem superfície HTTP no contrato

| | |
|---|---|
| **Status** | Aceita (decisão do orquestrador, 2026-08-06, fechamento da F14) |
| **Autor** | F14 / A1 |
| **Data** | 2026-08-05 |
| **Fases impactadas** | F14 (score de confiança, painel de marcações suspeitas) |
| **Artefatos de contrato afetados** | `packages/contracts/openapi.yaml` |
| **Bloqueia** | Só a escrita da decisão do gestor via HTTP e o botão "decidir" do painel web (`apps/web/src/app/painel/antifraude/`). A listagem de leitura, o motor de composição do score, a explicabilidade gravada e a fila de revisão como conceito de domínio (leitura/decisão via chamada direta de serviço, testada) seguem implementados e testados. |

## 1. O que está errado

ADR-008 (regra 2) e o PCF da F14 (§5, "A1 — Score de confiança") exigem uma
"fila de revisão do gestor": marcações com score entre os dois limiares
gravam normalmente e ficam pendentes de decisão humana
(`marcacoes_meta.revisao_status = 'pendente'`). O PCF também pede
explicitamente "verifique primeiro se o motor de aprovação de F10
(`apps/api/app/workflow/**`) já serve para isso antes de construir um
mecanismo de fila do zero".

Verifiquei. `packages/contracts/schema.sql`, seção 15 (`solicitacoes` /
`aprovacoes`):

```sql
CREATE TABLE solicitacoes (
    ...
    tipo_solicitacao_id   UUID NOT NULL REFERENCES tipos_solicitacao (id) ON DELETE RESTRICT,
    colaborador_id        UUID NOT NULL REFERENCES colaboradores (id) ON DELETE RESTRICT,
    solicitante_usuario_id UUID REFERENCES usuarios (id) ON DELETE SET NULL,
    ...
);
```

```sql
CREATE TABLE tipos_solicitacao (
    ...
    categoria  TEXT NOT NULL
               CHECK (categoria IN ('ajuste_ponto','abono','justificativa','ferias','folga',
                                    'compensacao','afastamento','troca_escala','hora_extra',
                                    'desbloqueio_dispositivo','outro')),
    ...
);
```

Duas incompatibilidades estruturais, não de gosto:

1. `solicitacoes` é **sempre iniciada pelo colaborador** (é um pedido que ele
   abre — `solicitante_usuario_id`). A fila de revisão antifraude é o
   oposto: o **sistema** sinaliza a marcação automaticamente, sem nenhuma
   ação do titular.
2. `tipos_solicitacao.categoria` tem `CHECK` fechado sem nenhum valor para
   "revisão antifraude" — adicionar um exigiria alterar o `CHECK` de uma
   tabela fora do meu ownership (só `politicas_registro` foi
   pré-autorizado para mim, PCF F14 §5/§6).

`marcacoes_meta` (mesma seção do schema, desde a Fase 0) já tem seu próprio
mecanismo de fila, propositalmente construído para isto:

```sql
revisao_status      TEXT NOT NULL DEFAULT 'nao_requer'
                     CHECK (revisao_status IN ('nao_requer','pendente','aprovada','rejeitada')),
revisado_por        UUID,
revisado_em         TIMESTAMPTZ,
revisao_observacao  TEXT,
```

com índice parcial dedicado:

```sql
CREATE INDEX ix_marcacoes_meta_revisao ON marcacoes_meta (tenant_id, revisao_status)
    WHERE revisao_status = 'pendente';
```

O que falta não é mecanismo de domínio — é a superfície HTTP. Confirmado por
leitura de `packages/contracts/openapi.yaml`:

- `GET /v1/marcacoes` (`listarMarcacoes`) não tem parâmetro `revisaoStatus`
  (nem equivalente) para filtrar server-side — só `incluirMeta=true`, que
  embute `ListaMarcacao.metas` (mapa `marcacaoId -> MarcacaoMeta`, RFC-011)
  na página inteira, sem filtro.
- `GET /v1/marcacoes/{marcacaoId}/meta` (`obterMetaMarcacao`) é leitura de
  item único — não serve para listar pendentes.
- Não existe nenhuma operação de escrita para decidir uma revisão
  (`POST`/`PATCH` em `.../meta` ou equivalente). `x-vedacao-legal` da tag
  `marcacoes` proíbe `PUT`/`PATCH`/`DELETE` em `/v1/marcacoes/{marcacaoId}`
  (ADR-002, correto — é o núcleo legal), mas essa vedação é textualmente
  escopada ao caminho da marcação, não ao de `meta` (a própria descrição de
  `obterMetaMarcacao` diz "os campos de revisão mudam ao longo do tempo, mas
  isso nunca altera a marcação em si" — o contrato já reconhece a
  mutabilidade de `meta`, só não expõe uma rota para ela).

## 2. Por que isto importa

O motor de composição do score, a explicabilidade e o cálculo de
`revisao_status='pendente'` já funcionam de ponta a ponta (30 testes reais
contra Postgres, `apps/api/tests/f14/antifraude/`, incluindo um round-trip
HTTP real de `POST /v1/marcacoes` → `GET /v1/marcacoes/{id}/meta`). O que
fica bloqueado é só a ação do GESTOR: hoje não há como, pela API, (a) listar
server-side as marcações pendentes de revisão de forma eficiente (sem trazer
a página inteira e filtrar no cliente) nem (b) registrar a decisão
(aprovar/rejeitar com observação). Sem isso, o "painel de marcações
suspeitas" do PCF fica limitado a uma visualização somente-leitura (via
`incluirMeta=true` + filtro no cliente), sem a ação de decidir.

Nada quebra hoje: o sistema grava e sinaliza corretamente, só a decisão do
gestor não tem caminho HTTP ainda.

## 3. Por que não corrigi sozinho

A correção está inteiramente em `packages/contracts/openapi.yaml`
(adicionar parâmetro(s) de filtro e/ou uma operação nova), congelado fora do
protocolo de RFC. É também uma decisão de FORMA de contrato (nome do
parâmetro/operação, se cabe em `listarMarcacoes` ou merece rota própria) que
outras fases que leem a tag `marcacoes` (F9b, F10, futura F7) precisam
enxergar da mesma forma.

## 4. Opções

**(a) Acrescentar `revisaoStatus` (e opcionalmente `scoreConfiancaMax`) como
parâmetros de query em `GET /v1/marcacoes`, mais `POST
/v1/marcacoes/{marcacaoId}/meta/decisao` para registrar a decisão.**
*Muda:* dois parâmetros novos em `listarMarcacoes` + uma operação nova (não
uma alteração da vedação de `PUT`/`PATCH`/`DELETE` em `/v1/marcacoes/
{marcacaoId}` — a nova rota é sob `.../meta/`, caminho já reconhecido pelo
contrato como mutável).
*Custa:* mais uma operação na tag `marcacoes`; exige `x-idempotente: true` e
`Idempotency-Key` (padrão do contrato para toda escrita) e permissão própria
(`marcacoes.revisar` ou reaproveitar `marcacoes.ler_sensivel`+nova ação de
escrita — a definir).
*Passa a ser verdade:* o painel do gestor funciona de ponta a ponta pela
API pública, com paginação eficiente (usa o índice parcial que já existe).

**(b) Rota dedicada de listagem: `GET /v1/marcacoes/revisao-pendente` (ou
`/v1/antifraude/fila`), mais a mesma operação de decisão de (a).**
*Muda:* duas operações novas (uma tag `antifraude` nova, se for o segundo
caminho) em vez de estender `listarMarcacoes`.
*Custa:* mais um caminho para manter sincronizado com os filtros de
`listarMarcacoes` (paginação, ordenação) — risco de divergência entre os
dois mecanismos de listagem de marcação ao longo do tempo.
*Passa a ser verdade:* semântica mais explícita ("isto é a fila de revisão",
não "marcações com um filtro específico"); mais fácil de dar permissão
própria e granular sem reaproveitar `marcacoes.ler_sensivel`.

**(c) Não mudar o contrato agora — manter o painel somente-leitura
(`incluirMeta=true` + filtro client-side) até uma fase futura decidir.**
*Muda:* nada em `openapi.yaml`.
*Custa:* paginação ineficiente para tenants com muitas marcações por página
(o cliente precisa varrer páginas inteiras para achar as poucas pendentes);
gestor não pode agir pela API, só auditar.
*Passa a ser verdade:* zero risco de contrato, zero superfície nova para
outras fases sincronizarem.

## 5. Recomendação

**(a).** Menor superfície nova (reaproveita `listarMarcacoes`, que já tem
paginação/ordenação/permissão sensível resolvidos), e a operação de decisão
sob `.../meta/decisao` é consistente com o padrão já estabelecido de
"`meta` é mutável, a marcação em si nunca é" que `obterMetaMarcacao` já
documenta.

## 7. Decisão (orquestrador, fechamento da F14)

Síntese de (a) e (b), não (a) pura: a operação de DECISÃO segue (a) sem
alteração (`POST /v1/marcacoes/{marcacaoId}/meta/decisao`, mesmo espírito de
`decidirTratamento`/`decidirAprovacao` já no contrato). A LISTAGEM, porém,
vira uma rota dedicada nova (`GET /v1/marcacoes/revisao-pendente`, opção b),
não um parâmetro `revisaoStatus` em `listarMarcacoes` — motivo concreto
descoberto na implementação: `app.antifraude.fila.listar_pendentes` (já
testado, 5 testes reais) tem seu PRÓPRIO mecanismo de paginação por cursor
(`cursor_datahora`, sobre `MarcacaoMeta.marcacao_datahora`), independente e
não trivialmente compatível com o `Cursor`/`Ordenar` genérico que
`listarMarcacoes` usa (dono: F5, `app.marcacao.consulta.marcacoes`). Encaixar
o filtro dentro de `listarMarcacoes` exigiria ramificar a query genérica de
F5 por dentro para redirecionar a um mecanismo de cursor diferente quando
`revisaoStatus=pendente` — risco de regressão num módulo fora do meu
ownership, para economizar uma rota. A rota dedicada é exatamente o padrão
que `obterMetaMarcacao` (dedicada, não um parâmetro em `obterMarcacao`) já
estabelece: `.../meta` é sensível e muda ao longo do tempo, merece caminho
próprio.

Schema do corpo da decisão: **novo** `DecisaoRevisaoRequisicao`
(`decisao: enum[aprovada, rejeitada]`, `observacao: string`), não reaproveita
`DecisaoRequisicao` (usado por `decidirTratamento`/`decidirAprovacao`) —
os valores do enum daquele (`aprovar`/`reprovar`) não batem com o `CHECK` de
`marcacoes_meta.revisao_status` (`aprovada`/`rejeitada`, Fase 0, imutável) e
`DecisaoRequisicao.delegacaoId` não se aplica aqui (revisão antifraude não
tem conceito de delegação). Resposta: `MarcacaoMeta` (já existe, mesmo
schema de `obterMetaMarcacao`).

Permissão: `marcacoes.ler_sensivel` (já existe) para a listagem — mesma
permissão de `obterMetaMarcacao`, é o mesmo dado sensível. Para a decisão,
`marcacoes.aprovar` — reaproveita a ação `aprovar` já liberada no `CHECK` de
`permissoes.acao` (`packages/contracts/schema.sql`), em vez de uma ação nova
(`revisar`) que exigiria outra migration no molde da RFC-002. Mesma
semântica de `tratamentos.aprovar` (uma permissão gate a decisão inteira,
aprovar OU reprovar) — o nome do RECURSO (`marcacoes`) já cobre a meta
antifraude por convenção (`marcacoes.ler_sensivel` também é sobre a meta,
não o corpo imutável da marcação).

## 6. O que NÃO é divergência

- O MECANISMO de fila (`marcacoes_meta.revisao_status` e colunas
  correlatas) está correto e completo desde a Fase 0 — não precisa de
  nenhuma migration nova.
- A decisão de NÃO reaproveitar `workflow.aprovacoes` (F10) está correta e
  verificada por leitura de schema (ver §1) — não é RFC porque não há
  ambiguidade: as duas tabelas (`solicitacoes`/`tipos_solicitacao`)
  estruturalmente não servem, sem alternativa.
- `apps/api/app/antifraude/fila.py` (`listar_pendentes`/`decidir_revisao`)
  já implementa a lógica de domínio completa e testada
  (`apps/api/tests/f14/antifraude/test_fila_revisao.py`, 5 testes reais
  contra Postgres) — pronta para ganhar uma rota fina em cima assim que esta
  RFC for decidida, sem redesenho.
