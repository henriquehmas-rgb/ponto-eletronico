# RFC-006 — O schema `Permissao.acao` do `openapi.yaml` nao aceita as tres ações que a RFC-002 liberou no banco

| | |
|---|---|
| **Status** | Proposta |
| **Autor** | F1 / A3 |
| **Data** | 2026-07-25 |
| **Fases impactadas** | F1 (bloqueia parcialmente `listarPermissoes`), F4, F5, F10 |
| **Artefatos de contrato afetados** | `packages/contracts/openapi.yaml` (schema `Permissao`, propriedade `acao`) |
| **Bloqueia** | Serialização de `GET /v1/admin/permissoes` (e de qualquer resposta futura que devolva um `Permissao`) para os quatro códigos que usam `configurar`, `reabrir` ou `ler_sensivel` — não bloqueia o restante do catálogo (138 dos 142 códigos) nem a autorização em si (RBAC não depende deste schema) |

## 1. O que está errado

A RFC-002 (decidida) ampliou o `CHECK` de `permissoes.acao` em três lugares
que precisavam concordar entre si — `packages/contracts/schema.sql:649-652`,
`apps/api/migrations/versions/0001_inicial.py` e
`packages/contracts/models/identidade.py:391-394` — para aceitar
`'configurar'`, `'reabrir'` e `'ler_sensivel'` além das nove ações
originais. Isso está feito e verificado (RFC-002, seção 6).

O que a RFC-002 **não tocou**, e que continua divergente, é o **schema
`Permissao`** do próprio `openapi.yaml`:

```
packages/contracts/openapi.yaml:36795-36807
        acao:
          type: string
          enum:
          - ler
          - criar
          - editar
          - excluir
          - aprovar
          - exportar
          - executar
          - assinar
          - administrar
          description: Acao permitida.
```

Nove valores, sem `configurar`, `reabrir` nem `ler_sensivel`. O código gerado
em `apps/api/app/schemas/contrato.py` reflete isso literalmente:

```python
class Acao2(StrEnum):
    """
    Acao permitida.
    """

    ler = "ler"
    criar = "criar"
    editar = "editar"
    excluir = "excluir"
    aprovar = "aprovar"
    exportar = "exportar"
    executar = "executar"
    assinar = "assinar"
    administrar = "administrar"
```

Comando que reproduz (a partir da raiz do repositório):

```
$ grep -n "administrar" packages/contracts/openapi.yaml
36806:          - administrar
```

Só uma ocorrência no arquivo inteiro: o enum de `acao` do schema `Permissao`
é o único lugar do contrato que enumera as nove ações, e é exatamente o
schema que `GET /v1/admin/permissoes` devolve.

## 2. Por que isto importa

`app/schemas/contrato.py` é **gerado** e está fora do ownership de qualquer
fase (`docs/fases/F01-identidade-multitenant-rbac.md`, seção 5, "explicitamente
fora do seu ownership"); ninguém pode simplesmente acrescentar os três valores
à mão em `Acao2`. Isso significa que, hoje, tentar validar um objeto Python
`Permissao(codigo="tenants.configurar", acao="configurar", ...)` contra o
schema pydantic gerado levanta `ValidationError` — porque `"configurar"` não é
um membro de `Acao2`.

Na prática, isso bloqueia a serialização de resposta de
`GET /v1/admin/permissoes` (`listarPermissoes`, implementado nesta fase) para
os quatro códigos afetados: `tenants.configurar` (F1), `banco_horas.configurar`
(F4), `fechamentos.reabrir` (F10) e `marcacoes.ler_sensivel` (F5). Os outros
138 códigos do catálogo serializam normalmente.

**Nada mais quebra.** A autorização em si (RBAC — `exigir_permissao`,
`perfil_permissoes`, a coluna `permissoes.acao` no banco) não depende deste
schema OpenAPI: ela lê `permissoes.codigo`/`acao` diretamente do banco via
SQLAlchemy, cuja `CheckConstraint` já foi corrigida pela RFC-002. Um usuário
com a permissão `tenants.configurar` concedida consegue exercê-la
normalmente em `PUT /v1/tenants/{tenantId}/configuracoes/{chave}`; só a
**listagem do catálogo** por `GET /v1/admin/permissoes` tropeça nesses
quatro itens específicos.

Verificado nesta fase: o catálogo de 142 permissões foi semeado por completo
no banco (`apps/api/migrations/seed_dev.py`, ver relatório da fase) e um teste
de banco (`apps/api/tests/f1/rbac/test_catalogo_permissoes.py`) confirma que
os 142 códigos existem em `permissoes`. O que este teste **não** cobre — e
não pode cobrir sem a decisão desta RFC — é uma chamada HTTP real a
`GET /v1/admin/permissoes` que devolva os quatro códigos afetados sem erro.

## 3. Por que não corrigi sozinho

O artefato afetado é `packages/contracts/openapi.yaml`, congelado. A escolha
entre as opções abaixo muda a superfície pública do contrato (o enum que todo
cliente gerado a partir do OpenAPI já assume), o que é decisão de
arquitetura, não conserto — exatamente o motivo pelo qual a RFC-002 já tratou
o lado do banco como decisão do orquestrador em vez de correção unilateral.

## 4. Opções

**(a) Ampliar o `enum` de `Permissao.acao` no `openapi.yaml`** para as doze
ações (as nove originais + `configurar`, `reabrir`, `ler_sensivel`), espelhando
o que a RFC-002 já fez em `schema.sql`/models/migration, e regerar
`app/schemas/contrato.py` (`python tools/gerar_do_contrato.py`).
*Muda:* uma lista no `openapi.yaml` + a regeração do arquivo gerado.
*Custa:* mexer no `openapi.yaml` congelado; qualquer cliente já gerado a
partir do enum de nove valores precisa ser regerado (mesmo custo que a
RFC-002 já aceitou do lado do banco).
*Passa a ser verdade:* o schema `Permissao` do contrato público volta a
bater com o que o banco realmente aceita — os 142 códigos, sem exceção,
serializam.

**(b) Deixar como está e excluir os 4 códigos de `listarPermissoes`**
enquanto a RFC não é decidida (ou devolver `acao` como string livre nesses
casos, fora do enum).
*Muda:* nada em `packages/contracts/`; `app/identidade/rbac/servico.py`
filtraria os 4 códigos na listagem HTTP.
*Custa:* o catálogo exposto pela API fica incompleto — quem lista permissões
pela API não vê `tenants.configurar` nem os outros três, mesmo eles existindo
e sendo funcionais no RBAC. É a opção que esconde a divergência em vez de
resolvê-la.

## 5. Recomendação

**(a)**. É a mesma lógica da RFC-002 (que já decidiu ampliar o conjunto de
ações): o schema `Permissao.acao` do OpenAPI é o único artefato que ficou
para trás nessa decisão. Manter (b) deixaria o catálogo estruturalmente
incompleto pela API, mesmo com o banco e o RBAC já corretos.

## 6. O que NÃO é divergência

* As 138 permissões restantes do catálogo (as que usam as nove ações
  originais) serializam normalmente por `GET /v1/admin/permissoes` — só os 4
  códigos citados são afetados.
* `permissoes.acao` no banco, a `CheckConstraint` do model SQLAlchemy e o
  `CHECK` do `schema.sql` já aceitam as doze ações (RFC-002, decidida) — a
  divergência está isolada no `openapi.yaml`/`app/schemas/contrato.py`.
* A autorização (RBAC) não é afetada: `exigir_permissao`/`exigir_alcance` não
  leem o schema OpenAPI, só a tabela `permissoes`.
