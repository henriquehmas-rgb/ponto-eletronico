# RFC-012 — Fila offline (`ItemFilaOffline.hmac`/AES-256-GCM) não tem contrato de material de chave no servidor

| | |
|---|---|
| **Status** | ✅ Decidida (adiada) |
| **Autor** | F5 / A2 |
| **Data** | 2026-07-26 |
| **Fases impactadas** | F5, F6, F12, F14 |
| **Artefatos de contrato afetados** | `packages/contracts/schema.sql` (tabela `dispositivos`), possivelmente `openapi.yaml` (`ItemFilaOffline`) |
| **Bloqueia** | Só o sub-comportamento "verificação criptográfica real do HMAC/decifragem AES-256-GCM do item da fila offline" da T7 do PCF da F5. O CONTROLE de fluxo inteiro (aceitar, rejeitar por assinatura inválida, rejeitar por replay de contador, expirar por TTL, não abortar o lote, não duplicar em reenvio) está implementado e testado. |

## 1. O que está errado

`packages/contracts/openapi.yaml` descreve `ItemFilaOffline` como "capturado
sem rede, cifrado e assinado no aparelho": o item chega com `payloadCifrado`
(AES-256-GCM), `iv` e `hmac`, "calculado no aparelho" a partir de uma chave
"derivada no keystore ou secure enclave do aparelho" (descrição da operação
`sincronizarMarcacoesOffline`).

Para o servidor **verificar** esse HMAC (ou decifrar o AES-256-GCM), ele
precisa de material de chave correspondente. `packages/contracts/schema.sql`,
tabela `dispositivos` (seção 6), só guarda `chave_publica TEXT` — uma chave
**assimétrica**, comentada como "usada para verificar a **assinatura** do
payload" (isto é, o campo `assinaturaPayload` de `MarcacaoCriar`, verificação
por chave pública/privada). Não existe nenhuma coluna para um segredo
**simétrico** (a chave HMAC/AES-GCM só pode ser simétrica ou derivada de um
segredo compartilhado) nem qualquer tabela de *enrollment* de chave de
dispositivo que a associe. Sem esse contrato, **não há como o servidor
verificar um HMAC real nem decifrar um payload AES-256-GCM real** — o segredo
simplesmente não existe do lado do servidor.

## 2. Por que isto importa

Sem chave, qualquer implementação de "verificação real" seria necessariamente
fictícia (ex.: usar `chave_publica`, que é assimétrica, como se fosse a chave
HMAC simétrica) — o que pareceria funcionar em teste controlado pelo próprio
autor do teste, mas não corresponderia a nenhum protocolo de segurança real
que um app cliente pudesse implementar de verdade. É exatamente o tipo de
"parece que funciona" que a RFC-011 já registrou para outro caso: pior do que
não implementar, porque esconde a lacuna.

## 3. Por que não corrigi sozinho

A correção depende de decisão de protocolo de segurança (que tipo de
segredo, como é provisionado no *enrollment* do dispositivo — que é fluxo da
F6/F2, não desta fase —, se é uma chave por dispositivo ou derivada de um
segredo do tenant, qual algoritmo exato de derivação) — decisão que a F6
(que consome este mesmo formato no catch-up de terminal) e a F14
(reputação/attestation de dispositivo) também precisam enxergar da mesma
forma. Não é ajuste de coluna isolado desta fase.

## 4. O que fiz enquanto a decisão não sai

Implementei `app.marcacao.pipeline.offline.sincronizar_lote` com o CONTROLE
de fluxo completo exigido pela T7 e pelo critério de aceite 5 da §7 do PCF:

* HMAC inválido → item **rejeitado** (`PONTO-MARC-006`), lote continua.
* Contador monotônico já consumido pelo dispositivo → item **duplicado**
  (`PONTO-MARC-007`), lote continua.
* Fora do TTL de sincronização (`politicas_registro.ttl_offline_horas`) →
  item **expirado** (`PONTO-MARC-005`), não gera marcação.
* Dentro do prazo e assinatura válida → converte em marcação via
  `app.marcacao.pipeline.ingestao.registrar_marcacao`, com
  `coletada_offline=true` e o instante real da captura preservado.
* Reenviar o mesmo lote inteiro não duplica nenhuma marcação (idempotência
  pelo escopo `offline_hmac` de `marcacao_idempotencia`, mais o próprio
  contador monotônico).

A função `app.marcacao.pipeline.offline.verificar_hmac_item` (STUB
documentado, mesma filosofia de `app.marcacao.confianca.motor.avaliar_confianca`
e do `crc16` de `app.marcacao.dominio.nsr`, ambos "calculado e congelado de
forma estável", não certificados) computa HMAC-SHA256 sobre os campos do
item usando `dispositivos.chave_publica` como material de verificação — na
ausência de um campo dedicado, não porque isso seja criptograficamente
correto. **Isso significa que nenhum aparelho real, hoje, produziria um HMAC
que esta função aceite**: a função só prova o CONTROLE de fluxo (o teste
constrói o HMAC "válido" com a mesma fórmula do stub, e corrompe
deliberadamente para o caso inválido), exatamente como o motor de confiança
stub prova o controle de fluxo do score sem julgar sinal real. Documentado
com a mesma advertência no docstring do módulo.

Da mesma forma, a decifragem AES-256-GCM de `payloadCifrado` **não é
realizada** nesta fase (não há chave para decifrar de verdade): o item é
tratado como já contendo, em `payloadCifrado` (base64), a representação
canônica JSON dos campos equivalentes a `MarcacaoCriar` que o item
representa — um placeholder documentado, não uma implementação de produção.

## 5. Recomendação

Quando esta RFC for decidida (provável opção: tabela nova
`dispositivo_chaves_offline` ou coluna `dispositivos.chave_offline_id`
referenciando um *keystore* externo, no mesmo espírito de
`biometria_templates` nunca guardar segredo em claro), a F6 e a F5
substituem a verificação stub pela real sem mudar a assinatura pública de
`verificar_hmac_item` nem o formato de `ItemFilaOffline` — mesmo padrão de
substituição sem RFC de forma que a F1 usou para o *auth stub* da F2 e que a
F14 vai usar para o motor de confiança desta fase.

## Decisão do orquestrador — 26/07/2026

| # | Decisão | Justificativa |
|---|---|---|
| 1 | **Adiada, não decidida agora.** Mantido o stub documentado exatamente como F5/A2 entregou, com a assinatura pública de `verificar_hmac_item` fixada por este PCF. A decisão real de protocolo (que segredo, como é provisionado no enrollment) fica para quando uma fase com um CLIENTE REAL de dispositivo precisar dela — provavelmente F7 (app mobile, que implementa a fila offline cifrada do lado do aparelho) ou F6 se o catch-up de terminal precisar antes disso. | Ao contrário de RFC-004/009/010/013, nenhuma fase desta onda ou da próxima tem um cliente real que produza um HMAC/payload cifrado de verdade — decidir o protocolo agora seria adivinhar requisitos de F7 sem contexto de como o app deriva a chave no keystore/enclave. |
| 2 | Quando F7 (ou quem primeiro precisar) chegar a esta decisão, escreve uma NOVA RFC referenciando esta (RFC decidida é imutável) com o protocolo real. | Mantém o histórico de que esta RFC não define o protocolo final — só documenta que a decisão foi conscientemente adiada, não esquecida. |

Registrado em `docs/backlog.md` para que F6/F7/F12/F14 não redescubram esta lacuna do zero.
