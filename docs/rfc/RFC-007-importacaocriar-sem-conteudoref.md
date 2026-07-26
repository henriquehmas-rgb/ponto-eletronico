# RFC-007 — `ImportacaoCriar` não declara `conteudoRef`

| | |
|---|---|
| **Status** | ✅ Decidida/Implementada |
| **Autor** | F2 / A2 |
| **Data** | 2026-07-25 |
| **Fases impactadas** | F2 (rotas `colaboradores.py` e `importadores/servico.py`), qualquer fase futura que reuse `POST /v1/colaboradores/importar` ou o schema `ImportacaoCriar` (F13 possivelmente, para `POST /v1/importacoes`) |
| **Artefatos de contrato afetados** | `packages/contracts/openapi.yaml` (schema `ImportacaoCriar`) |
| **Bloqueia** | O corpo da rota `POST /v1/colaboradores/importar` (`operationId: importarColaboradores`) não pode repassar a referência do arquivo já enviado para `app.importadores.servico.criar_importacao_colaboradores`, que exige esse dado para o worker saber o que processar |

## 1. O que está errado

`packages/contracts/openapi.yaml`, schema `ImportacaoCriar`
(`components.schemas.ImportacaoCriar`), tem exatamente estas propriedades:

```
empresaId, tipo, origem, nomeArquivo, parametros, status, erros
```

Não existe `conteudoRef`. Mas o **exemplo** do próprio contrato,
`components.examples.ExemploImportacaoCriar`, inclui o campo:

```json
{
  "tipo": "colaboradores",
  "origem": "xlsx",
  "empresaId": "b3f61d47-0a5c-4d92-a7e8-14c6b09f2358",
  "nomeArquivo": "colaboradores-2026-08.xlsx",
  "conteudoRef": "uploads/2026-08/colaboradores-2026-08.xlsx",
  "parametros": { "modo": "criar_ou_atualizar", "delimitador": ";" }
}
```

E o schema de **resposta** `Importacao` tem `conteudoRef` (`conteudo_ref` no
Pydantic gerado, `app/schemas/contrato.py:10243`): "Chave do arquivo no
armazenamento de objetos." O campo existe no schema de saída e no exemplo de
entrada, mas não no schema de entrada.

Confirmado no Pydantic gerado (`app/schemas/contrato.py:10309-10345`,
`class ImportacaoCriar`): não há atributo `conteudo_ref`, e o `model_config`
não declara `extra="allow"` — um cliente que enviar `conteudoRef` no corpo tem
o campo silenciosamente descartado pelo Pydantic (comportamento padrão
`extra="ignore"`), inacessível a partir de `corpo.conteudo_ref` no router.

`app/importadores/servico.py:criar_importacao_colaboradores` (agente A3, T10)
já foi escrito assumindo que esse dado chega — a assinatura exige
`conteudo_ref: str | None` como parâmetro nomeado, e a tarefa do worker
(`apps/worker/worker/tarefas/importacoes.py`) lê o arquivo em
`PONTO_ARMAZENAMENTO_DIR/<conteudo_ref>`.

## 2. Por que isto importa

Sem `conteudoRef` acessível no corpo validado, `POST
/v1/colaboradores/importar` (dono do router: F2/A2) não tem como informar ao
serviço de importação qual arquivo processar. Implementar o endpoint mesmo
assim — por exemplo, chamando `criar_importacao_colaboradores` com
`conteudo_ref=None` sempre — cria uma importação que o worker nunca consegue
localizar: toda carga real falharia silenciosamente na primeira tentativa de
leitura do arquivo, um defeito muito mais caro de depurar do que a rota
continuar respondendo o stub `501` de andaime. Isso bloqueia o critério de
aceite 7 do PCF da F2 ("importador processa 5.000 colaboradores") **via HTTP**
— o teste de carga do critério 7 (T10, agente A3) contorna isso chamando o
serviço/worker diretamente, sem passar pela rota, então não está bloqueado por
esta RFC; só a integração HTTP-completa está.

## 3. Por que não corrigi sozinho

`packages/contracts/openapi.yaml` está congelado (proibição 1 do PCF da F2,
seção 9). Acrescentar `conteudoRef` ao schema `ImportacaoCriar` é edição de
contrato, não de aplicação — e mesmo que fosse só a mim que afetasse, a
correção de contrato precisa ser vista por qualquer fase que reusar
`ImportacaoCriar` (F13 provavelmente, para `POST /v1/importacoes`).

## 4. Opções

**(a)** Acrescentar `conteudoRef` (`string`, opcional) a
`components.schemas.ImportacaoCriar` no `openapi.yaml`, espelhando o campo
homônimo que `Importacao` (resposta) já tem. Regenerar
`app/schemas/contrato.py` com `tools/gerar_do_contrato.py`. Menor mudança
possível: o exemplo do próprio contrato já pressupõe esse campo, então isto é
"completar o que já estava implícito", não uma decisão nova de design.

**(b)** Manter o contrato como está e resolver por fora: o cliente faz upload
do arquivo primeiro (endpoint ou fluxo ainda inexistente no contrato) e o
identificador do objeto vira parte de `parametros` (que aceita
`additionalProperties: true`), por exemplo `parametros.conteudoRef`. Não exige
mudar `openapi.yaml`, mas mistura um dado estrutural (onde está o arquivo) com
um campo pensado para configuração da execução (delimitador, modo de
atualização) — e diverge do próprio exemplo do contrato, que já usa
`conteudoRef` no nível raiz.

**(c)** Trocar o formato da requisição para `multipart/form-data` com upload
direto do arquivo no mesmo `POST /v1/colaboradores/importar`, eliminando a
necessidade de uma referência pré-existente. Resolve o problema de origem
(hoje nenhuma fase integrou um cliente MinIO real — ver nota em
`apps/worker/worker/tarefas/importacoes.py`, docstring do módulo), mas é a
mudança de maior superfície: novo `requestBody` (`content` muda de
`application/json` para `multipart/form-data`), novo limite de tamanho de
corpo, e novo comportamento em todo cliente gerado a partir do contrato.

## 5. Recomendação

Opção **(a)**: é a correção mínima e mais alinhada ao que o próprio contrato já
sinaliza através do exemplo — o campo já é esperado, só falta declarado no
schema de entrada.

## 6. O que NÃO é divergência

`Importacao` (schema de resposta) já expõe `conteudoRef` corretamente, e
`app/importadores/servico.py` (A3) já está escrito certo para o dia em que o
campo existir na entrada — nenhum dos dois precisa mudar quando esta RFC for
decidida, só o `openapi.yaml` e a regeração do Pydantic.

## Estado enquanto a RFC não é decidida

`POST /v1/colaboradores/importar` (`app/routers/colaboradores.py`,
`importar_colaboradores`) continua respondendo o stub de andaime (`501`,
`PONTO-INT-005`). As outras sete operações da tag `colaboradores` e as oito da
tag `contratos` não são afetadas por esta RFC e foram implementadas
normalmente.

## Decisão do orquestrador — 26/07/2026

| # | Decisão | Justificativa |
|---|---|---|
| 1 | Opção **(a)**: `conteudoRef` (`string`, opcional) acrescentado a `ImportacaoCriar` em `packages/contracts/openapi.yaml`, espelhando o campo homônimo de `Importacao` (resposta) e o exemplo já existente no contrato. | Menor mudança possível; o próprio contrato já pressupunha o campo via `ExemploImportacaoCriar`. Nenhuma outra fase que reusa `ImportacaoCriar` (F13) é prejudicada — o campo é aditivo e opcional. |
| 2 | `apps/api/app/schemas/contrato.py` regenerado via `tools/gerar_do_contrato.py`. | Mantém o Pydantic sincronizado com o contrato, sem edição manual do arquivo gerado. |
| 3 | `POST /v1/colaboradores/importar` (`app/routers/colaboradores.py`) ligado a `app.importadores.servico.criar_importacao_colaboradores`, repassando `corpo.conteudo_ref`. | Único ponto que faltava para a operação sair do stub de andaime; a camada de serviço (F2/A3) já estava pronta para receber o campo. |

Verificação real colada (VPS, `ponto_verificacao`, role restrita
`ponto_verificacao_login`, sem `BYPASSRLS`):

```
$ python tools/conferir_rotas.py
contrato : 215 operacoes em 140 caminhos
aplicacao: 215 operacoes em 140 caminhos
Inventario identico ao contrato (metodo, caminho e operationId).

$ pytest tests/f2/importadores -q
.......                                                                  [100%]
```
