# ADR-008 — Score de confiança antifraude em vez de bloqueio binário

**Status:** Aceito · 25/07/2026
**Decisores:** SEEG — arquitetura
**Fases afetadas:** F14 (implementa as regras), F5 (estrutura e campos), F7 e F8 (produzem sinais), F9b (fila de revisão)

---

## Contexto

O app e o portal web coletam uma dúzia de sinais antifraude: veredito do Play
Integrity (Android) e do App Attest/DeviceCheck (iOS), detecção de root,
jailbreak, Magisk, Xposed, Frida, debugger, emulador e binário adulterado,
**modo desenvolvedor e depuração USB ligados** (requisito explícito do cliente),
*mock location* e apps de fake GPS, coerência entre GPS, BSSID de Wi-Fi, célula
e IP, velocidade impossível entre marcações, pertencimento à geocerca, faixa
CIDR de origem, prova de vida, similaridade facial, reputação do dispositivo e
confiança temporal (ADR-007).

O reflexo natural é transformar cada sinal em bloqueio: reprovou attestation,
não bate ponto. Isso quebra na primeira semana de produção, por um motivo que
não é técnico e sim econômico: **o parque de celulares do trabalhador
brasileiro**. Aparelho de entrada com Android antigo, sem Play Services
atualizado, com fabricante que não passa na certificação, ou simplesmente com
`ADB` ligado porque um técnico habilitou uma vez — todos reprovam por motivos
legítimos. E o efeito de bloquear é imediato e grave: o trabalhador não registra
jornada, o que é problema jurídico da empresa, não dele.

O oposto — aceitar tudo e olhar depois — também não serve: transforma o
antifraude em teatro e deixa a empresa sem defesa quando a fraude aparece.

## Decisão

**Cada marcação recebe um score de confiança de 0 a 100, composto por sinais
ponderados, avaliado no servidor, com política de três faixas configurável por
empresa.**

1. **Composição no servidor.** O cliente **coleta e reporta** sinais; ele nunca
   calcula nem decide. Veredito de attestation é verificado contra a API da
   plataforma no backend. Cliente que manda `score: 100` é ignorado por
   construção — o campo não existe na entrada.
2. **Três faixas, configuráveis por empresa e por unidade.**
   *Acima do limiar superior:* grava normalmente.
   *Entre os limiares:* **grava e sinaliza** para a fila de revisão do gestor.
   *Abaixo do limiar inferior:* recusa com `PONTO-SCORE-*` e orienta o canal
   alternativo.
   Padrão recomendado do produto: rigoroso na sede (onde há terminal facial e
   rede corporativa), tolerante em campo.
3. **A marcação sinalizada é uma marcação válida.** Ela entra no AFD como
   qualquer outra. O sinal vive em `marcacoes_meta`, e a revisão do gestor
   produz **tratamento**, nunca alteração ou exclusão da marcação (ADR-002).
4. **Explicabilidade obrigatória.** `marcacoes_meta` guarda quais sinais
   contribuíram e com que peso. Sem isso o gestor não consegue decidir, e o
   trabalhador não consegue contestar — um número solitário é indefensável numa
   audiência.
5. **Mensagem que não vaza a regra.** O erro devolvido ao usuário não revela
   limiar, peso, raio da geocerca nem faixa CIDR (`expoe_regra: false` em
   `errors.yaml`); a causa completa vai para a auditoria. Quem sabe o limiar,
   calibra a fraude.
6. **Bloqueio nunca é beco sem saída.** Toda recusa aponta um caminho: terminal
   facial, totem, navegador em rede corporativa ou registro assistido pelo RH
   com justificativa.
7. **Sinal decisivo continua existindo.** *Mock location* comprovado, assinatura
   de payload inválida e HMAC de fila offline quebrado são recusa direta,
   independentemente do score — são evidência de adulteração, não indício.

## Alternativas consideradas

**Bloqueio binário por sinal (regra rígida).** Descartado pelo Contexto: o falso
positivo tem custo assimétrico e recai sobre quem não pode pagá-lo. Consta no
mapa de riscos de `PROJETO.md` como risco de impacto alto.

**Aceitar tudo e auditar depois.** Descartado: sem limiar inferior, o sistema não
oferece nenhuma barreira real, e a empresa perde o argumento de controle.

**Modelo estatístico ou de aprendizado de máquina para a pontuação.** Atraente e
prematuro: exige base rotulada de fraude que ainda não existe, é difícil de
explicar ao gestor e ao juiz, e um modelo opaco decidindo se alguém registrou
jornada é risco jurídico. Fica no backlog para depois de haver histórico
rotulado; a composição ponderada com pesos explícitos é a base sobre a qual esse
modelo poderá ser treinado.

**Score calculado no cliente.** Descartado sem discussão: o cliente é o
ambiente sob controle do adversário.

**Score único e global, igual para todos os clientes.** Descartado porque a
tolerância legítima varia com o contexto — vendedor externo trabalha fora de
qualquer geocerca por definição, e operador de chão de fábrica não deveria estar
fora dela nunca.

## Consequências

**Positivas.** O sistema fica utilizável no mundo real sem abrir mão da
detecção. A empresa assume conscientemente sua política de risco, em vez de
herdar a nossa. A fila de revisão transforma sinal fraco em decisão humana
rastreável, com tratamento auditado no fim.

**Negativas e mitigações.** (a) A faixa intermediária gera trabalho para o
gestor; se mal calibrada, vira ruído que ninguém lê. Mitigação: a F14 entrega
telemetria da distribuição de scores por empresa e recomendação de calibração,
e a F9b limita a fila a ações em lote. (b) Pesos são decisão de produto e
envelhecem — versionados junto com a política, com o valor vigente registrado na
marcação, para que uma revisão feita hoje seja explicável daqui a três anos.
(c) A explicabilidade armazena sinais que são, eles próprios, dados sensíveis
(localização, características do dispositivo): entram na política de retenção e
no registro de operações de tratamento da LGPD. (d) Configuração por empresa
significa mais superfície de suporte; mitigado com três perfis prontos
(*rigoroso*, *equilibrado*, *tolerante*) e ajuste fino opcional.
