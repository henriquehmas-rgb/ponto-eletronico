# RFC-021 — `BiometriaCriar` não declara nenhum dos seis campos que `criarBiometria` realmente lê (`fotoBase64`, `mimeType`, `vetor`, `versaoModelo`, `dimensao`, `provedor`)

| | |
|---|---|
| **Status** | ✅ Decidida/Implementada |
| **Autor** | Orquestrador (fechamento do gap #1 registrado em `docs/backlog.md`, entrada de 09/08/2026) |
| **Data** | 2026-08-09 |
| **Fases impactadas** | F2 (dona de `app/routers/biometria.py` e `app/biometria/servico.py`), F14 (motor facial ligado às rotas), F7/F8 (clientes que cadastram biometria pelo app e pelo portal) |
| **Artefatos de contrato afetados** | `packages/contracts/openapi.yaml` (schema `components.schemas.BiometriaCriar`) |
| **Bloqueia** | Nada em execução. O endpoint funciona hoje. O que estava bloqueado era a possibilidade de um cliente descobrir, **lendo o contrato**, como se cadastra uma biometria — o único caminho documentado era ler o código do servidor. |

## 1. O que está errado

`packages/contracts/openapi.yaml`, `components.schemas.BiometriaCriar`
(linha 30306 antes desta RFC), declarava exatamente sete propriedades:

```
colaboradorId, modalidade, status, origemCadastro, qualidade,
consentimentoId, identificadorCartao
```

Nenhuma delas carrega template biométrico nem imagem. Mas
`apps/api/app/routers/biometria.py::criar_biometria` lê **seis** campos que
não estavam ali, direto do corpo bruto:

```python
bruto: dict[str, Any] = await request.json()
extraido = await _extrair_template(bruto, colaborador_id=corpo.colaborador_id)
...
    vetor = _decodificar_vetor(bruto)
    versao_modelo = bruto.get("versaoModelo") or None
    dimensao = bruto.get("dimensao")
provedor = bruto.get("provedor") or "facial-svc"
```

e, dentro de `_extrair_template`:

```python
foto = bruto.get("fotoBase64")
...
    mime_type=str(bruto.get("mimeType") or "image/jpeg"),
```

Três fatos confirmados por leitura, não presumidos:

1. **O schema não tinha `additionalProperties: false`** — nem ele, nem
   nenhum outro schema do contrato (`grep -c 'additionalProperties: false'
   packages/contracts/openapi.yaml` → 0). Ou seja: enviar os seis campos
   nunca foi uma violação de validação. Era uma lacuna de **documentação**,
   não um bypass.
2. **O próprio contrato já pressupunha um deles.**
   `components.examples.ExemploBiometriaCriar` usa `versaoModelo`, campo que
   o schema de entrada não declarava — exatamente o mesmo padrão que a
   [RFC-007](RFC-007-importacaocriar-sem-conteudoref.md) corrigiu em
   `ImportacaoCriar`/`conteudoRef`.
3. **O Pydantic gerado descarta silenciosamente.**
   `apps/api/app/schemas/contrato.py`, `class BiometriaCriar`, tem
   `model_config = ConfigDict(populate_by_name=True)` e nada de `extra` —
   o padrão do Pydantic v2 é `extra="ignore"`. É precisamente por isso que a
   rota lê `Request.json()`: pelo modelo tipado, os seis campos não chegam.

O gap foi registrado ontem em `docs/backlog.md` (entrada de 09/08/2026, gap
(1) dos quatro deixados em aberto pela entrega do motor facial): «`fotoBase64`
não está declarado no contrato (`BiometriaCriar`) — lido do corpo bruto, mesma
técnica que o campo `vetor` já usava». A leitura desta RFC corrige um detalhe
dessa nota: `vetor` **também** não estava declarado. Os dois estavam fora.

## 2. Por que isto importa

Nada quebra hoje, e nada quebrava ontem — o endpoint cadastra biometria de
verdade, com template real extraído no `facial-svc`, e os testes de
`apps/api/tests/f14/facial/` provam isso ponta a ponta.

O que estava quebrado é o contrato como **fonte da verdade**. Consequências
concretas, todas verificáveis:

* Um cliente gerado a partir do `openapi.yaml` (o app Flutter da F7, o portal
  da F8, um integrador externo) não tem como cadastrar biometria nenhuma: o
  tipo de requisição gerado não tem campo para a foto nem para o vetor. A
  única saída é o desenvolvedor abrir `app/routers/biometria.py` e copiar os
  nomes na mão — que é a definição de "vocabulário comum partido em dois" do
  [protocolo de RFC](README.md).
* A regra de exclusividade mútua entre `fotoBase64` e `vetor` existia **só**
  numa docstring Python. Quem lê o contrato descobre a regra recebendo
  `PONTO-VAL-001` em produção.
* No dia em que alguém acrescentasse `additionalProperties: false` a este
  schema — coisa perfeitamente razoável de se querer — todo cadastro de
  biometria do produto passaria a ser rejeitado, sem que nada no contrato
  explicasse por quê.

## 3. Por que não corrigi sozinho

`packages/contracts/openapi.yaml` está congelado desde a Fase 0; edição nele é
o único caso em que uma RFC é obrigatória mesmo quando a correção é óbvia
(README §1, linha "A mudança pedida atinge `packages/contracts/`"). E a forma
escolhida para expressar "um ou outro, nunca os dois" precisa ser a **mesma**
em todo o contrato — senão a próxima fase inventa uma terceira.

## 4. Opções

**(a) Declarar os seis campos como propriedades opcionais independentes, com a
exclusividade mútua descrita em prosa (na `description` do schema e na do
campo) e verificada pelo servidor.**
*Muda:* seis propriedades novas em `BiometriaCriar` e o texto da `description`
do schema. Nenhum comportamento de runtime.
*Custa:* a exclusividade não é verificável por um validador de JSON Schema
genérico — quem só valida o corpo contra o schema aceita `fotoBase64` e
`vetor` juntos, e é o servidor que recusa.
*Passa a ser verdade:* o contrato descreve o que a rota realmente aceita, e
usa **a convenção que o contrato já usa** para alternativas mutuamente
exclusivas — `MarcacaoCriar` faz exatamente isto com `colaboradorId` x `cpf` x
`matricula` ("Alternativa a informar cpf ou matricula"), três propriedades
opcionais independentes, exclusividade em prosa e no servidor.

**(b) Declarar os campos e expressar a exclusividade com `oneOf`/`not`/
`dependentRequired` do JSON Schema.**
*Muda:* as mesmas seis propriedades, mais uma construção combinatória no
schema.
*Custa:* **o contrato inteiro não tem uma única ocorrência de `oneOf` ou
`anyOf`** (`grep -cE 'oneOf|anyOf' packages/contracts/openapi.yaml` → 0, em
~1,4 MB de contrato). Inventar aqui o primeiro padrão
combinatório do contrato, num schema de canto, é decidir por todas as fases
sem que nenhuma tenha pedido. Além disso muda a forma do modelo Pydantic
gerado (`oneOf` vira `Union`, não campos opcionais irmãos), o que **mudaria**
o código do router — exatamente o que esta mudança não deve fazer.
*Passa a ser verdade:* a exclusividade passa a ser verificável por qualquer
validador — ganho real, mas pago com uma decisão estrutural fora de escopo.

**(c) Declarar só `fotoBase64` e deixar `vetor`, `versaoModelo`, `dimensao`,
`provedor` e `mimeType` fora, como estavam.**
*Muda:* uma propriedade.
*Custa:* deixa cinco sextos do problema no lugar, e torna a frase "mutuamente
exclusivo com `vetor`" impossível de escrever no contrato — `vetor` não
existiria lá para ser referenciado. Fecharia o item do backlog sem fechar o
defeito.
*Passa a ser verdade:* nada de útil.

## 5. Recomendação

**(a).** É a correção mínima que torna o contrato verdadeiro, não inventa
padrão novo (reusa o de `MarcacaoCriar`), não muda uma linha de comportamento
e não fecha a porta para (b) no futuro — acrescentar `dependentRequired` ou
`not` depois é aditivo sobre propriedades que já existirão.

## 6. O que NÃO é divergência

* **O nome `fotoBase64` não foi inventado pela entrega de ontem.** É o mesmo
  campo, com a mesma semântica e a mesma proibição, que `MarcacaoCriar` já
  declarava desde a Fase 0: "Captura ao vivo em base64, quando a politica
  exige facial. NUNCA aceita upload de arquivo previamente salvo."
* **A ausência de `additionalProperties: false` é do contrato inteiro**, não
  deste schema. Nenhum schema tem. Ler campo não declarado do corpo bruto
  nunca foi violação de validação — só de documentação.
* **`vetor` continua sem aparecer em nenhuma resposta.** Ele é declarado
  apenas no schema de **entrada**. `Biometria` (resposta) não ganha campo
  nenhum: o template é dado pessoal sensível, entra cifrado e não sai (ADR-006
  regra 5, `PONTO-LGPD-002`).
* **O comportamento do handler não muda.** `criarBiometria` continua lendo os
  seis campos do corpo bruto — ver §7.

## 7. `apps/api/app/schemas/contrato.py` NÃO foi regerado nesta RFC

A RFC-007 regerou o Pydantic no mesmo passo. Aqui **não**, por um motivo
verificado e não presumido: a versão de `datamodel-code-generator` disponível
no ambiente onde esta RFC foi aplicada não é a que produziu o arquivo
versionado. Regerando com ela, o diff vai muito além de `BiometriaCriar` —
entre outras coisas renomeia classes de enum de outros schemas
(`DecisaoRevisao` → `Decisao2`, `Canal2` → `Canal9`), o que quebra importações
em módulos que não têm nada a ver com biometria. Aplicar isso "de brinde"
numa mudança que não deve alterar comportamento nenhum seria o oposto do que
esta RFC se propõe.

Consequências, explicitamente:

* `class BiometriaCriar` do Pydantic gerado continua com sete campos, e
  `app/routers/biometria.py` continua lendo os seis do corpo bruto via
  `Request.json()`. **Nenhuma mudança de runtime**, que é o ponto.
* Quando o arquivo for regerado no ambiente com o extra `codegen` na versão
  fixada, `BiometriaCriar` ganha `foto_base64`, `mime_type`, `vetor`,
  `versao_modelo`, `dimensao` e `provedor` automaticamente, e a leitura do
  router **pode** ser simplificada para ler do modelo tipado. Isso é trabalho
  opcional de limpeza, não parte desta decisão.
* Um efeito que essa regeração futura terá e que vale registrar agora:
  `dimensao` passa a ser validado como `int` com `ge=1`. Hoje um
  `"dimensao": "abc"` é repassado adiante sem validação de tipo na borda; depois
  ele vira `422`. Isso é aperto desejado, mas é mudança observável — quem
  regerar deve rodar `tests/f2/biometria` e `tests/f14/facial` no mesmo passo.

## Decisão do orquestrador — 09/08/2026

| # | Decisão | Justificativa |
|---|---|---|
| 1 | Opção **(a)**: `fotoBase64`, `mimeType`, `vetor`, `versaoModelo`, `dimensao` e `provedor` acrescentados como propriedades **opcionais** a `components.schemas.BiometriaCriar` em `packages/contracts/openapi.yaml`. `required` não muda (`colaboradorId`, `modalidade`, `origemCadastro`). | Correção mínima que torna o contrato verdadeiro. Todos os seis já eram lidos pelo servidor; nenhum passa a ser obrigatório, então nenhum cliente existente quebra. |
| 2 | A exclusividade mútua entre `fotoBase64` e `vetor` fica **em prosa** na `description` do schema e na do campo `fotoBase64`, e continua verificada pelo servidor (`PONTO-VAL-001`). Sem `oneOf`/`anyOf`. | É a convenção que o contrato já usa (`MarcacaoCriar`: `colaboradorId` x `cpf` x `matricula`). O contrato não tem nenhuma ocorrência de `oneOf`/`anyOf`; criar a primeira aqui seria decidir por todas as fases sem necessidade, e mudaria a forma do modelo gerado. |
| 3 | `mimeType` ganha `default: image/jpeg` e `provedor` ganha `default: facial-svc`. | Não é invenção: é literalmente o que o servidor faz hoje (`bruto.get("mimeType") or "image/jpeg"`, `bruto.get("provedor") or "facial-svc"`). Declarar o default documenta o comportamento real. |
| 4 | `components.examples.ExemploBiometriaCriar` **não** muda. | Continua válido contra o schema novo. `versaoModelo`, que ele já usava sem estar declarado, agora está — o exemplo passou de "usa campo inexistente" a "usa campo declarado" sem tocar em nada. |
| 5 | `apps/api/app/schemas/contrato.py` **não** regerado; `app/routers/biometria.py` mantém a leitura do corpo bruto (só as docstrings foram atualizadas para refletir que os campos agora existem no contrato). | Ver §7. Regerar com a versão de codegen disponível arrastaria renomeações de enums não relacionados. Zero mudança de comportamento era requisito desta entrega. |

Verificação colada:

```
$ npx @stoplight/spectral-cli@6.14.2 lint packages/contracts/openapi.yaml \
    --ruleset /tmp/spectral-padrao.yaml --fail-severity=warn --format=pretty
0 Unique Issue(s)
No results with a severity of 'warn' or higher found!
```
