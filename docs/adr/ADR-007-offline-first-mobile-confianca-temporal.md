# ADR-007 — Arquitetura offline-first do app mobile e confiança temporal

**Status:** Aceito · 25/07/2026
**Decisores:** SEEG — arquitetura
**Fases afetadas:** F7 (implementa), F5 (recepção e NSR), F14 (score e verificação adversarial)

---

## Contexto

O app precisa funcionar onde não há rede: obra, galpão, área rural, subsolo,
cliente com Wi-Fi fechado, celular sem franquia de dados no fim do mês. Bater
ponto é obrigação do trabalhador, e um app que responde "sem conexão" está
transferindo para ele um problema que é da empresa.

Isso colide de frente com um princípio inegociável do projeto: **o relógio é do
servidor**. O horário do aparelho não é confiável — é trivialmente ajustável nas
configurações, é a fraude mais comum em ponto por celular, e não há como
distinguir, olhando só o valor, um relógio adiantado de propósito de um relógio
adiantado por bug de sincronização.

O terceiro fator é o comprovante: a Portaria MTP 671/2021 dispensa a impressão
no momento da marcação porque garantimos acesso eletrônico permanente e extração
das últimas 48 h. O comprovante contém o NSR — que só o servidor atribui
(ADR-003). Ou seja: **offline não pode gerar comprovante definitivo**.

## Decisão

**Fila local cifrada com três relógios registrados, classificação de confiança
temporal feita no servidor, e sinalização honesta da marcação como coletada
offline.**

1. **Fila local.** Drift/SQLite com cada registro cifrado em **AES-GCM** e
   assinado com **HMAC** de chave derivada no *keystore*/*secure enclave* do
   aparelho, vinculada ao dispositivo. Adulterar a fila com o telefone rooteado
   invalida o HMAC e o servidor recusa.
2. **Três relógios, todos gravados.** No instante da batida o app registra:
   (a) o relógio de parede do aparelho, (b) o **tempo monotônico** desde o boot
   (`elapsedRealtime` / `CLOCK_MONOTONIC`, que não retrocede com ajuste manual) e
   (c) o último instante conhecido do servidor, obtido na última sincronização
   bem-sucedida, com o valor monotônico correspondente. Com isso o servidor
   reconstrói o instante provável por
   `hora_servidor_conhecida + (monotônico_batida − monotônico_sincronização)`.
3. **Contador monotônico anti-replay.** Cada registro carrega um sequencial por
   dispositivo, nunca reaproveitado. Reenvio do mesmo sequencial é idempotente;
   sequencial fora de ordem ou repetido com conteúdo diferente é rejeitado.
4. **Classificação no servidor.** A marcação recebe um nível de confiança
   temporal — *alta* (deriva pequena e coerente entre os três relógios),
   *média* (deriva relevante, mas monotônico consistente) ou *baixa* (relógio
   retrocedeu, boot no meio do caminho, ou divergência inexplicável). O nível
   alimenta o score de confiança (ADR-008) e aparece no espelho.
5. **TTL de 72 h.** Registro que não sincroniza em 72 h continua sendo enviado,
   mas entra sinalizado para tratamento do gestor. Nada é descartado
   silenciosamente pelo app — descarte de registro de ponto pelo cliente é
   inaceitável.
6. **Sinalização honesta.** A marcação sincronizada é gravada como **coletada
   offline**, com a data/hora real e o NSR do momento da chegada. O espelho e o
   AEJ mostram isso. O sistema nunca finge que a batida foi online.
7. **Comprovante provisório e definitivo.** Offline, o app entrega um recibo
   local com identificador próprio, marcado como *pendente de envio*, com aviso
   inequívoco. Quando sincroniza, o recibo é substituído pelo comprovante
   definitivo com NSR e hash, e o histórico local guarda os dois.

## Alternativas consideradas

**Bloquear a batida sem rede.** Descartado por inviabilidade operacional: é a
mesma coisa que dizer que o trabalhador de campo não usa o app.

**Aceitar o relógio do aparelho como verdade.** Descartado: é o vetor de fraude
número um em ponto por celular, e joga fora a única defesa técnica disponível.

**Atribuir NSR no cliente (faixa pré-alocada por dispositivo).** Permitiria
comprovante definitivo offline e foi descartado porque um dispositivo que perde
a fila, é reinstalado ou nunca sincroniza deixa **lacuna permanente** na
sequência do REP-P — a falha exata que o ADR-003 existe para tornar impossível.

**Carimbar a marcação com a hora da chegada ao servidor.** Simples e desonesto:
registraria como 18h uma batida ocorrida às 12h, o que é inserir marcação que
não corresponde ao fato real — vedação expressa da Portaria.

**Servidor NTP embarcado / exigir sincronização de tempo antes da captura.**
Ajuda quando há rede, e não resolve o caso offline, que é o problema.

**Fila em texto claro protegida só pelo sandbox do sistema operacional.**
Descartado: em aparelho rooteado o sandbox não protege nada, e a fila offline é
o alvo natural de quem quer forjar batida.

## Consequências

**Positivas.** O app funciona onde o trabalho acontece. A fraude por
manipulação de relógio deixa de ser invisível: ela passa a ser detectável por
incoerência entre os três relógios e vira sinal, não suposição. O comprovante
continua correto porque o NSR continua sendo do servidor.

**Negativas e mitigações.** (a) A interface fica mais complexa: existe um estado
"pendente de envio" que precisa ser óbvio e não pode ser confundido com sucesso —
tratado como requisito de design, com estado próprio no design system.
(b) Reinicializar o aparelho zera o tempo monotônico e degrada a estimativa;
mitigado registrando o boot e classificando como confiança média, não baixa,
quando o resto é coerente. (c) Fila grande após dias offline exige sincronização
em lote com retomada — a F5 aceita `POST /v1/marcacoes/sincronizar-offline` em
lote idempotente. (d) A chave HMAC no *enclave* morre com o app desinstalado;
a fila pendente é perdida junto, o que precisa estar escrito na tela antes de
qualquer instrução de "reinstalar o aplicativo" do suporte. (e) O nível de
confiança temporal é um dado novo que RH e gestor precisam entender — a F10
inclui isso no material de treinamento.
