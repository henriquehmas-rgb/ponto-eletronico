# RFC-005 — `tests/test_andaime.py` fica obsoleto conforme as fases implementam rotas reais

| | |
|---|---|
| **Status** | ✅ **Decidida** em 26/07/2026 pelo orquestrador — opção (b), implementada |
| **Autor** | F1 / A2 |
| **Data** | 2026-07-25 |
| **Fases impactadas** | Todas as que convertem uma rota `501` em implementação real (F1, F2, ... até F15) |
| **Artefatos de contrato afetados** | Nenhum (`packages/contracts/` intacto). O artefato afetado é `apps/api/tests/test_andaime.py`, que pertence à Fase 0, não a nenhuma fase posterior |
| **Bloqueia** | O critério de aceite "regressão do andaime não pode quebrar", presente em todo PCF de fase (inclusive o meu, seção 8), a partir do momento em que qualquer rota citada literalmente no arquivo deixa de ser stub |

## 1. O que está errado

`apps/api/tests/test_andaime.py` (Fase 0, fora do ownership de qualquer fase
posterior) faz três afirmações que só são verdadeiras enquanto **nenhuma**
fase implementou rota nenhuma:

1. `test_todas_as_operacoes_do_contrato_respondem_501_ou_saude` (linha ~90)
   cravou uma lista fixa de 7 caminhos (`/v1/marcacoes`, `/v1/auditoria`, …)
   e exige `501` de todos.
2. `test_tenant_resolvido_por_cabecalho` (linha ~166) chama
   `GET /v1/colaboradores` com `X-Tenant: seeg` e exige `501`.
3. `test_stub_responde_501_com_codigo_do_catalogo` e
   `test_parametro_invalido_devolve_erros_campo` (linhas ~77 e ~128) chamam
   `/v1/colaboradores` (e uma variação de path) e também exigem `501`.

Com o repositório no estado atual (F1 e F2 rodando em paralelo, ambas já com
trabalho real mesclado), rodando
`pytest tests/test_andaime.py -q` contra um banco migrado e semeado (fluxo
prescrito na seção 8 dos PCFs: subir banco, migrar, semear, só então testar):

```
FAILED tests/test_andaime.py::test_stub_responde_501_com_codigo_do_catalogo
FAILED tests/test_andaime.py::test_todas_as_operacoes_do_contrato_respondem_501_ou_saude
FAILED tests/test_andaime.py::test_parametro_invalido_devolve_erros_campo
FAILED tests/test_andaime.py::test_tenant_resolvido_por_cabecalho
```

As quatro falhas são pela mesma causa: `apps/api/app/routers/colaboradores.py`
(F2) já implementou `listarColaboradores` de verdade (usa `SessaoDb` real) e
`apps/api/app/routers/auditoria.py` (F1/A3) já implementou `listarAuditoria`
de verdade. Nenhuma das duas rotas responde mais `501` — respondem `400`
(tenant ausente), `401` (sem autenticação) ou o que a regra de negócio real
determinar. **Isso é o esperado e o correto**: é exatamente o trabalho que
F1 e F2 existem para fazer.

## 2. Por que isto importa

Toda fase (este PCF incluído, seção 8) lista
`cd apps/api && pytest tests/test_andaime.py -q` como comando de verificação
obrigatório, com a nota "não pode quebrar". Isso é fisicamente impossível de
satisfazer a partir do momento em que a PRIMEIRA fase qualquer implementa a
PRIMEIRA rota citada literalmente no arquivo — o que já aconteceu (F1 e F2, em
paralelo). Ou seja: o critério de aceite, como está escrito hoje em todo PCF,
deixou de ser satisfazível por qualquer fase a partir de F1/F2 em diante, não
por erro de nenhum agente.

## 3. Por que não corrigi sozinho

`apps/api/tests/test_andaime.py` está listado explicitamente como **fora do
meu ownership** ("Explicitamente fora do seu ownership… `apps/api/tests/test_andaime.py`"),
e não pertence a F2 nem a nenhuma outra fase posterior — é um artefato da
Fase 0, que já encerrou. Editá-lo unilateralmente para "consertar" as
asserções seria exatamente o contorno silencioso que o protocolo de RFC
existe para evitar: cada fase decidiria à sua maneira o que fica de pé no
arquivo, e o arquivo pararia de significar a mesma coisa para todo mundo.

## 4. Opções

**(a)** Aposentar `test_todas_as_operacoes_do_contrato_respondem_501_ou_saude`,
`test_stub_responde_501_com_codigo_do_catalogo` (na parte que chama rota de
domínio) e `test_tenant_resolvido_por_cabecalho` assim que a fase dona da rota
citada a implementar de verdade — o que faz sentido tratando o arquivo como
"vivo" e de propriedade rotativa (quem implementa a rota, ajusta a asserção
correspondente). Custo: quebra a regra "ninguém edita o andaime", exige decidir
quem tem permissão de tocar o arquivo a partir de agora.

**(b)** Substituir as asserções fixas por uma verificação dinâmica: o
teste consulta `app.core.erros` ou inspeciona se a exceção é `NaoImplementado`
em vez de comparar status codes contra uma lista de paths hardcoded, e pula
(via `pytest.mark.skip` condicional) caminhos cuja fase já os implementou.
Mais robusto a longo prazo, mas é reescrever o arquivo, mesmo problema de
ownership que (a).

**(c)** Interpretar "regressão do andaime não pode quebrar" como aplicável
apenas às asserções que testam o **andaime em si** (formato do erro, presença
de `request_id`, `/health`/`/ready`, inventário de rotas) — não às asserções
que testam o **conteúdo de uma rota específica ainda-stub no momento em que a
Fase 0 escreveu o arquivo**. Sob essa leitura, os quatro testes que falham
hoje são "esperados ficarem obsoletos", e o orquestrador os desconsidera
fase a fase, documentando no fechamento de cada fase quais assertions do
andaime pararam de valer e por quê (auditável, sem editar o arquivo).
Custo: nenhum código muda; exige o orquestrador aceitar essa leitura
explicitamente, porque hoje o texto do PCF não distingue os dois tipos de
asserção.

## 5. Recomendação

Opção **(c)** para decisão imediata (não bloqueia nenhuma fase, não exige
tocar em código), com a opção **(b)** como evolução de médio prazo quando o
orquestrador tiver banda para reescrever o arquivo com um dono explícito.

## 6. Decisão do orquestrador — 26/07/2026

**Opção (b), aplicada imediatamente** — não só (c). O motivo de não esperar:
o problema é estrutural e vai se repetir a cada fase até a F15; adiar só
adia o retrabalho, e o arquivo já estava com quatro asserções quebradas.
`apps/api/tests/test_andaime.py` foi reescrito para nunca mais fixar "este
caminho específico ainda é stub": as asserções perguntam a `app.openapi()` e
à resposta real, em tempo de execução, e verificam a invariante que continua
válida nos dois casos (stub e implementado) — principalmente **"nenhuma
operação responde 500 sem tratamento"**, que é o que "o andaime não pode
quebrar" realmente significa a partir de agora. Nenhuma fase futura precisa
editar este arquivo só por ter implementado uma rota.

Ownership após esta decisão: `apps/api/tests/test_andaime.py` deixa de ser
"território de ninguém" — o **orquestrador** é quem mantém, exatamente como
esta correção. Fases individuais continuam proibidas de editá-lo (ele
verifica o andaime, não a fase), mas se uma fase achar que a invariante em si
mudou (não só que uma rota específica saiu do stub), isso é RFC nova, não
edição direta.

## 6. O que NÃO é divergência

O restante de `test_andaime.py` — inventário de rotas idêntico ao contrato,
`/health` sem dependência, `/ready` relatando dependências, formato
`application/problem+json`, `request_id` gerado e preservado — continua
correto e passando. A verificação confirmou isso rodando o arquivo inteiro
contra o banco de teste desta fase (ver relatório de F1/A2).
