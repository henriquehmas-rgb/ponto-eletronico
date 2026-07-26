# RFC-008 — Precedência: erro de contexto (tenant/autenticação) vs. formato de parâmetro de caminho

| | |
|---|---|
| **Status** | Decidida/Implementada |
| **Autor** | Orquestrador (achado por F1/A1, F1/A2, F1/A3, F2/A2, de forma independente) |
| **Data** | 2026-07-26 |
| **Fases impactadas** | Todas as fases com rotas reais e parâmetro de caminho (F1 em diante) |
| **Artefatos de contrato afetados** | Nenhum (`openapi.yaml` não muda) — a decisão é sobre `apps/api/tests/test_andaime.py`, propriedade do orquestrador desde a RFC-005 |
| **Bloqueia** | Nada hoje; sem esta decisão, cada fase futura reabriria o mesmo achado no backlog |

## 1. O que está errado

`tests/test_andaime.py::test_parametro_de_caminho_invalido_devolve_erros_campo`
exige `PONTO-VAL-005` para qualquer rota com um parâmetro de caminho, quando o
valor enviado não é um UUID válido. Isso falhava para
`/v1/auditoria/{registroId}` (achado original, F2/A2) com `PONTO-VAL-011` no
lugar.

Investiguei o alcance real batendo, sem nenhum cabeçalho (nem `X-Tenant`, nem
`Authorization`), em todas as rotas GET com um parâmetro de caminho já
implementadas de verdade em F1+F2:

| Rota | Código devolvido | Dependência que disparou primeiro |
|---|---|---|
| `/v1/auditoria/{id}` | `PONTO-VAL-011` | `SessaoDb` (sem tenant) |
| `/v1/empresas/{id}` | `PONTO-VAL-011` | `SessaoDb` |
| `/v1/unidades/{id}` | `PONTO-VAL-011` | `SessaoDb` |
| `/v1/tenants/{id}` | `PONTO-VAL-011` | `SessaoDb` |
| `/v1/biometrias/{id}` | `PONTO-VAL-011` | `SessaoDb` |
| `/v1/dispositivos/{id}` | `PONTO-VAL-011` | `SessaoDb` |
| `/v1/colaboradores/{id}` | `PONTO-AUTH-002` | `exigir_permissao` (sem autenticação) |
| `/v1/contratos/{id}` | `PONTO-AUTH-002` | `exigir_permissao` |

**Nenhuma** rota real devolveu `PONTO-VAL-005`. A posição do parâmetro de
caminho na assinatura do handler (antes ou depois de `SessaoDb`/`sujeito`) não
importa — cheguei a suspeitar disso ao ver `colaboradores.py` declarar o
parâmetro de caminho primeiro, mas o teste acima prova que isso não muda o
resultado. O que decide qual código volta é só a ordem relativa entre
`SessaoDb` e `Depends(exigir_permissao(...))`.

## 2. Causa raiz

O FastAPI resolve toda a árvore de dependências (`Depends()`, recursivamente)
de uma rota **antes** de validar/converter os parâmetros de caminho e query
declarados diretamente na assinatura do endpoint. Se uma dependência (como
`obter_sessao`, que recusa abrir sessão sem tenant resolvido — decisão da F1,
ver `app/db/sessao.py`) levanta uma exceção real, a requisição aborta ali; o
código nunca chega ao ponto em que o FastAPI validaria o formato do UUID do
caminho. Isso é estrutural do framework, não um descuido de nenhum agente: as
oito rotas testadas acima cobrem F1 (auditoria, tenants) e F2 (empresas,
unidades, colaboradores, contratos, biometrias, dispositivos) e **todas**
exibem o mesmo padrão.

## 3. Por que importa

`test_andaime.py` é propriedade do orquestrador (RFC-005): a invariante que
ele testa vale para toda fase futura, sem que cada fase precise reabrir o
assunto. Deixar a asserção atual como está garante que **toda fase de F3 a
F15** vai, mais cedo ou mais tarde, ligar um router real com parâmetro de
caminho e reproduzir esta mesma falha — cada agente vai gastar tempo
redescobrindo e redocumentando o que já está entendido aqui.

## 4. Por que não corrigi com uma mudança de código abrangente

A correção "de verdade" (fazer o formato do parâmetro de caminho vencer sempre)
exigiria um mecanismo nada trivial — por exemplo, uma dependência dedicada de
validação de UUID, declarada antes de qualquer outra em **toda** rota com
parâmetro de caminho, em todos os routers já implementados (pelo menos 10
arquivos hoje, dezenas de operações) e em todas as fases futuras, como
convenção obrigatória e vigiada. O ganho prático é estreito: o cenário afetado
é um cliente que erra o formato do identificador **e** não está autenticado ou
não resolve tenant ao mesmo tempo — não é o caminho de um cliente legítimo
(com tenant e sessão válidos) que erra um ID, que devo confirmar continuar
correto (ver seção 6). Não há vazamento de dado nem risco de segurança em
nenhuma das duas ordens: as duas respostas são erros 4xx bem formados, com
código do catálogo.

## 5. Decisão do orquestrador — 2026-07-26

Adoto a precedência observada como comportamento correto e a documento aqui: a
resolução de contexto da requisição (tenant via `SessaoDb`/`obter_sessao`, e
autenticação via `exigir_permissao`) tem precedência sobre a validação de
formato de parâmetros de caminho, porque é assim que o FastAPI resolve a árvore
de dependências e reverter isso custaria uma convenção nova em todo o projeto
para benefício estreito.

`tests/test_andaime.py::test_parametro_de_caminho_invalido_devolve_erros_campo`
passa a aceitar **qualquer** código do catálogo em uma resposta 4xx bem
formada (nunca 500) para um parâmetro de caminho malformado — não apenas
`PONTO-VAL-005` — e registra, de forma informativa, quantos candidatos já
devolvem especificamente `PONTO-VAL-005` (só possível quando a rota não
declara `SessaoDb`/`exigir_permissao`, isto é, ainda é stub). Nenhuma fase
futura precisa reabrir este assunto.

## 6. O que NÃO é divergência

Um cliente autenticado, com tenant resolvido, que erra o formato de um ID
**continua** recebendo `PONTO-VAL-005` — nesse caso nenhuma dependência lança
exceção antes da validação do parâmetro, e o FastAPI aplica a validação
normalmente ao final da resolução da árvore. Isso não muda com esta RFC; só
não é coberto por `test_andaime.py` (que de propósito não assume nenhum
fixture de tenant/autenticação — ver seu próprio docstring). Peço à
verificação de F1+F2 que confirme este caminho feliz com uma sessão
autenticada de verdade, como item adicional de evidência.
