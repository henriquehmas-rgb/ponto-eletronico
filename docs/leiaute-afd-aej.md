# Leiaute AFD e AEJ — REP-P (Portaria MTP nº 671/2021)

**T0 bloqueante da Fase 12.** Este documento confere, campo a campo, o leiaute oficial do AFD (Arquivo Fonte de Dados) e do AEJ (Arquivo Eletrônico de Jornada) definidos pela Portaria MTP nº 671, de 8 de novembro de 2021, para o REP-P (Registrador Eletrônico de Ponto via Programa) — o modelo usado pelo SEEG Ponto. Toda seção técnica cita a fonte usada. Nada aqui foi inventado: onde a fonte primária não respondeu com precisão suficiente para gerar bytes idênticos aos de um AFD/AEJ já aceito, o campo está marcado **NÃO CONFIRMADO**.

Data da pesquisa: 2026-07-30.

---

## 1. Lacunas conhecidas e riscos (leia isto primeiro)

Estas são as pendências que **bloqueiam** a promessa de "comparação byte a byte contra AFD de sistema já aceito" (critério de aceite da F12) enquanto não forem resolvidas contra uma fonte adicional (ex.: AFD de referência de outro fabricante homologado, ou esclarecimento formal da SIT/MTE).

1. **Fórmula exata de concatenação do hash SHA-256 do registro tipo "7" (NÃO CONFIRMADO).** O Anexo V lista os 8 insumos do hash (NSR, tipo do registro, data/hora da marcação, CPF, data/hora de gravação, identificador do coletor, indicador on-line/off-line, hash do registro anterior) mas **não especifica** o formato de concatenação: se é a representação de largura fixa de cada campo (com os *paddings* do próprio registro), os valores "crus" sem padding, com ou sem separador entre eles, e em que codificação de bytes exata (ISO 8859-1 presumivelmente, mas não afirmado nesta frase). Duas implementações que sigam apenas o texto do anexo podem produzir hashes diferentes para o mesmo evento. **Isto precisa ser resolvido antes de codificar o Agente A1 da F12** — via AFD de referência de um fabricante já homologado, ou pedido formal de esclarecimento ao MTE.
2. **Regra de preenchimento de campos numéricos no AFD é ambígua no texto oficial (NÃO CONFIRMADO com certeza total).** A regra geral 7 do Anexo V diz literalmente: *"O preenchimento dos campos deve se iniciar pela esquerda e posições não utilizadas devem ser preenchidas com espaço."* Lida ao pé da letra, isso significa que até campos numéricos (tipo N) seriam alinhados à esquerda e completados com espaços à direita — o que quebraria a ordenação lexicográfica correta do NSR exigida pela regra 4 (*"Ordenar os registros pelo NSR"*: "2" + espaços ordena depois de "10" + espaços em comparação de string, o que é numericamente errado) e contradiz a prática universal do mercado (herdada da tradição REP-C da Portaria 1.510/2009) de preencher campos numéricos com zeros à esquerda, alinhados à direita. A seção 6 abaixo detalha o raciocínio. **Antes de implementar o gerador, validar contra um AFD de referência real** para confirmar se campos N (especialmente NSR e CNPJ/CPF-em-campo-de-14) são zero-padded à esquerda (como a prática de mercado sugere) ou espaço-padded à direita (como o texto genérico da regra 7 sugere).
3. **Prazo de guarda (retenção) do AFD/AEJ não localizado com número de artigo confirmável.** Vários sites secundários (blogs de fornecedores de RH) repetem "5 anos" sem citar artigo específico da Portaria 671/2021 ou do Decreto 10.854/2021. Não encontrei essa regra no texto que consegui extrair diretamente dos artigos 76–92 (a faixa que trata de REP/AFD/AEJ). Pode estar em artigo fora dessa faixa, ou derivar da regra geral trabalhista (prescrição de 5 anos, CLT). **Marcado NÃO CONFIRMADO** — não usar "5 anos" no código ou em documentação de conformidade sem confirmação em fonte primária.
4. **Regra de fracionamento do AFD por período**: confirmei (Perguntas e Respostas oficiais do MTE, pergunta 39) que o AFD do REP-C **não pode** ser fracionado e que o AFD do REP-A **ou REP-P pode** ser fracionado — mas a fonte não especifica a **periodicidade** (por mês? por ano-calendário? por competência de folha?) nem um limite de tamanho/tempo. Ou seja: sabemos que fracionar é permitido para REP-P, mas não sabemos a regra de corte. **NÃO CONFIRMADO** o critério de corte.
5. **Fracionamento do AEJ**: não encontrei, em nenhuma fonte consultada, uma afirmação equivalente à do AFD sobre se/como o AEJ pode ser fracionado por período. **NÃO CONFIRMADO.**
6. **Lista de Anexos (I a IX) da Portaria** foi corroborada por duas extrações independentes de fontes secundárias (normaslegais.com.br e legisweb.com.br), mas eu não consegui abrir o PDF oficial consolidado da Portaria (todas as URLs testadas em `gov.br` para a versão compilada retornaram HTTP 404 nesta sessão — provável proteção anti-bot/CDN, não ausência do documento). A lista da seção 10 deste documento deve ser tratada como **alta confiança, mas não verificada num PDF primário aberto por mim nesta sessão** — apenas os Anexos V e VI (AFD e AEJ) foram lidos diretamente do PDF oficial.

**Avaliação honesta de prontidão:** os leiautes de AFD e AEJ (campos, tamanhos, tipos, ordem, separador, terminador, CRC-16) vêm de leitura direta do PDF técnico oficial do MTE e têm alta confiança — o suficiente para começar a implementação dos tipos de registro 1–6, 9 do AFD e todos os tipos do AEJ. **O registro tipo "7" do AFD (o coração do REP-P) não está pronto para gerar bytes que baterão com um AFD de referência**, porque a fórmula do hash SHA-256 encadeado não está especificada com precisão suficiente na fonte oficial disponível. Isso deve ser resolvido antes de declarar a Fase 12 "pronta para o critério de aceite".

---

## 2. Correções às premissas do projeto (FASES-E-AGENTES.md)

O `FASES-E-AGENTES.md` (linha 320) presumia, antes desta pesquisa: *"gerador de AFD (ASCII ISO 8859-1, separador `\|`, CR+LF, NSR sequencial, registro tipo 7 para REP-P com NSR + tipo + data/hora + CPF + CRC-16, ... SHA-256 do arquivo, fracionamento por período)"*. A pesquisa desta tarefa (T0) encontrou **três divergências factuais** entre essa premissa e o texto oficial:

| Premissa do projeto | O que a fonte oficial diz | Impacto |
|---|---|---|
| AFD usa separador `\|` (pipe) | O AFD **não usa delimitador algum**. É um arquivo de **largura fixa por posição** ("Posição" 001-009, 010-010, etc.). O separador `\|` é exclusivo do **AEJ**. | Alto — o gerador de AFD não deve inserir pipes; deve escrever campos em posições fixas com preenchimento por espaço/zero conforme o tipo. |
| Registro tipo "7" tem CRC-16 | A regra 8 do Anexo V limita o CRC-16 explicitamente aos **tipos "1" a "5"**. O tipo "6" não tem CRC-16 nem hash. O tipo "7" **não tem campo de CRC-16** — no lugar, tem um campo de **hash SHA-256 encadeado** (campo nº 8, "código hash"). | Alto — um gerador que calcule CRC-16 para o tipo 7 produzirá um arquivo inválido. |
| "SHA-256 do arquivo" (implica hash do arquivo inteiro) | O SHA-256 é usado **apenas no registro tipo "7"**, como hash **por registro, encadeado ao hash do registro tipo 7 anterior** (regra 9 + explicação do campo nº 8) — não é um hash do arquivo inteiro. Não há, nas fontes consultadas, nenhuma exigência de hash de arquivo inteiro separada disso. | Médio-alto — não implementar um hash de arquivo; implementar a cadeia de hash por registro tipo 7, respeitando a Lacuna nº 1 acima sobre o formato exato de concatenação. |

Essas correções devem ser propagadas para o `FASES-E-AGENTES.md` / PCF da F12 quando a fase for planejada em detalhe.

---

## 3. Fontes primárias utilizadas

Nesta ordem de confiança (todas em `.gov.br`, exceto onde indicado como secundária):

1. **Leiaute oficial do AFD** — Ministério do Trabalho e Emprego, PDF técnico dedicado (metadado: criado em 09/06/2022 por Luiz Henrique Lopes):
   `https://www.gov.br/trabalho-e-emprego/pt-br/assuntos/inspecao-do-trabalho/fiscalizacao-do-trabalho/leiaute-do-arquivo-fonte-de-dados-afd.pdf`
   Lido integralmente (texto completo extraído do PDF, 6 páginas). Esta é a fonte de **todo** o conteúdo das seções 6, 7 e 8 abaixo, salvo indicação contrária.
2. **Leiaute oficial do AEJ** — mesma origem MTE, PDF técnico dedicado:
   `https://www.gov.br/trabalho-e-emprego/pt-br/assuntos/inspecao-do-trabalho/fiscalizacao-do-trabalho/leiaute-do-arquivo-eletronico-de-jornada-aej.pdf`
   Lido integralmente (5 páginas). Fonte de **todo** o conteúdo das seções 9 e 10 abaixo, salvo indicação contrária.
3. **Portaria MTP nº 4.198, de 19 de dezembro de 2022** — Diário Oficial da União, publicada em 21/12/2022, Edição 239, Seção 1, Página 359, que altera o art. 86 da Portaria 671/2021 (assinatura eletrônica do AFD/AEJ):
   `https://www.in.gov.br/en/web/dou/-/portaria-mtp-n-4.198-de-19-de-dezembro-de-2022-452386805`
   Lida integralmente (23 páginas do DOU); confirma que esta alteração **não toca o leiaute técnico** do AFD/AEJ, apenas quem deve assinar cada saída.
4. **Perguntas e Respostas oficiais — REP** (Ministério do Trabalho e Emprego), página institucional:
   `https://www.gov.br/trabalho-e-emprego/pt-br/assuntos/inspecao-do-trabalho/fiscalizacao-do-trabalho/Perguntas%20e%20Respostas%20REP`
   Consultada para: regra de atribuição do NSR (pergunta 41), regra de fracionamento do AFD (pergunta 39), padrões de assinatura CAdES/PAdES e quem assina (perguntas 28–30, 33–35). Republicada também em `guiatrabalhista.com.br/tematicas/portaria-671-2021-perguntas-e-respostas.htm`, usada para checagem cruzada do mesmo conteúdo.
5. **Texto consolidado dos artigos da Portaria 671/2021** — não consegui abrir o PDF oficial compilado do `gov.br` diretamente nesta sessão (múltiplas URLs testadas retornaram HTTP 404, provavelmente por proteção anti-bot da CDN, incluindo as versões "compilada-20-10-2023" e "compilada-26-09-2024"). Usei como fonte secundária o texto reproduzido por `normaslegais.com.br/legislacao/portaria-mtp-671-2021.htm` e por síntese de `legisweb.com.br`, cruzando os dois. Onde citados abaixo como "Art. XX", a fonte é esta reprodução secundária, não o PDF oficial lido diretamente — **tratar como confiança média**, suficiente para identificar o artigo e o teor geral, insuficiente para transcrição legal literal palavra por palavra (a extração apresentou problemas de codificação de acentuação).

Fontes descartadas ou usadas apenas como triagem inicial: `espacolegislacao.totvs.com/portaria-671/` (retornou HTTP 402 ao tentar acessar — paywall), `acesso.trabalho.gov.br` (erro de certificado SSL).

---

## 4. REP-C, REP-A, REP-P — não confundir

A Portaria 671/2021 (Capítulo VII, arts. 76–92, conforme reprodução secundária cruzada de `normaslegais.com.br` e `legisweb.com.br`) define três registradores distintos, com leiautes de AFD que **compartilham a mesma estrutura de arquivo e a maioria dos tipos de registro**, mas que têm campos e regras específicas por tipo (ex.: o registro tipo "3" é exclusivo de REP-C/REP-A, o tipo "7" é exclusivo de REP-P):

- **REP-C** (Registrador Eletrônico de Ponto Convencional, Art. 76): equipamento de automação monolítico dedicado, identificado por número de fabricação.
- **REP-A** (Registrador Eletrônico de Ponto Alternativo, Art. 77): conjunto de equipamentos e programas autorizado por convenção/acordo coletivo.
- **REP-P** (Registrador Eletrônico de Ponto via Programa, Art. 78): "programa (software) executado em servidor dedicado ou em ambiente de nuvem" — **este é o modelo do SEEG Ponto**.

Todo o conteúdo técnico deste documento (seções 6–10) foi lido diretamente dos PDFs oficiais de leiaute do AFD e do AEJ, que cobrem os três tipos de REP no mesmo texto normativo — mas cada tabela de campo indica explicitamente, quando aplicável, se um tipo de registro ou campo é exclusivo de REP-C, REP-A ou REP-P. Onde a tabela não faz distinção, o campo/registro se aplica aos três.

---

## 5. PTRP

Confirmado diretamente no leiaute oficial do AEJ (registro tipo "08"): **PTRP = Programa de Tratamento de Registro de Ponto**. Fonte: leiaute AEJ oficial (fonte 2 acima), título da tabela do registro tipo "08": *"Registro do tipo "08" - Identificação do PTRP (Programa de Tratamento de Registro de Ponto)"*.

---

## 6. Regras gerais do AFD

Fonte: leiaute oficial do AFD (fonte 1, seção 3 acima). Todas as regras abaixo são citação/paráfrase direta do texto lido.

1. Formato texto, **codificado em ASCII/ISO 8859-1** (Latin-1). Confirma a premissa do projeto.
2. Cada linha = um registro, terminando com os **caracteres 13 e 10** (CR LF) da tabela ASCII ISO 8859-1, nessa ordem. Confirma a premissa do projeto.
3. Registros **ordenados pelo NSR**.
4. Sem linhas em branco.
5. **Não há caractere delimitador entre campos no AFD.** Os campos são de **largura fixa**, definidos por posição inicial e final dentro da linha (colunas "Posição" nas tabelas da seção 7). **Isto corrige a premissa do projeto de que o AFD usa `\|` como separador** — o `\|` é exclusivo do AEJ (seção 9).
6. Tipos de dado por campo:
   - `N`: numérico.
   - `A`: alfanumérico.
   - `D`: data, formato `AAAA-MM-dd`.
   - `DH`: data e hora, formato `AAAA-MM-ddThh:mm:00ZZZZZ`, onde `T` é literal, `hh`=00–23, `mm`=00–59, os segundos são sempre fixados em `"00"`, e `ZZZZZ` é o fuso horário (1 dígito de sinal + 4 dígitos de hora/minuto). Exemplo dado pela própria fonte: `2021-04-27T16:44:00-0300`.
7. **Regra geral de preenchimento** (citação literal): *"O preenchimento dos campos deve se iniciar pela esquerda e posições não utilizadas devem ser preenchidas com espaço."* — Ver Lacuna nº 2 na seção 1: esta regra, lida literalmente, é ambígua para campos numéricos (N) e entra em tensão com a exigência de ordenação correta por NSR (regra 3) e com a prática de mercado herdada da Portaria 1.510/2009 (zero à esquerda para campos N). **Recomendação:** tratar campos `A` (alfanumérico) como alinhados à esquerda com espaço à direita (sem ambiguidade — é o comportamento natural para texto) e tratar campos `N` como candidatos a zero-padding à esquerda (alinhados à direita), **mas validar contra um AFD de referência real antes de confiar nisso em produção**.
8. **CRC-16**: obrigatório apenas para os registros dos **tipos "1" a "5"**. Não existe para os tipos "6", "7" ou "9" (trailer), nem para a linha de assinatura digital. Ver seção 8 para o algoritmo exato.
9. **SHA-256**: usado exclusivamente no **registro tipo "7"**, campo nº 8. Ver seção 8.2.
10. **Nome do arquivo**: junção da palavra `"AFD"` com:
    - REP-C: número de fabricação do REP + CNPJ/CPF do empregador + `"REP_C"`.
    - REP-A: CNPJ/CPF do empregador + `"REP_A"`.
    - REP-P: **número de registro no INPI** + CNPJ/CPF do empregador + `"REP_P"`.
    (A fonte não especifica o separador exato entre esses três componentes do nome do arquivo nem a extensão — **NÃO CONFIRMADO** o formato exato do nome de arquivo além da ordem e do conteúdo dos componentes.)

---

## 7. AFD — tipos de registro (leiaute completo)

Fonte: leiaute oficial do AFD (fonte 1). Todas as tabelas abaixo são transcrição literal das tabelas do PDF oficial (nomes de campo, posições, tamanhos, tipos e conteúdo). A coluna **Tam. calc.** ao final de cada tabela é derivada por mim (soma dos tamanhos = posição final do último campo) como checagem de consistência — todas bateram exatamente com a posição final informada pela fonte, o que dá alta confiança de que a extração do PDF não perdeu nem duplicou linhas.

### Tipo "1" — Cabeçalho (302 caracteres)

| # | Posição | Tam. | Tipo | Conteúdo |
|---|---|---|---|---|
| 1 | 001-009 | 9 | N | `"000000000"` (constante). |
| 2 | 010-010 | 1 | N | Tipo do registro. `"1"`. |
| 3 | 011-011 | 1 | N | Tipo de identificador do empregador: `"1"`=CNPJ, `"2"`=CPF. |
| 4 | 012-025 | 14 | N | CNPJ ou CPF do empregador. |
| 5 | 026-039 | 14 | N | CNO ou CAEPF, quando existir. |
| 6 | 040-189 | 150 | A | Razão social ou nome do empregador. |
| 7 | 190-206 | 17 | N | REP-C: número de fabricação · REP-A: número do processo do último acordo/convenção coletiva depositado (se não houver: `"99999999999999999"`) · **REP-P: número de registro no INPI**. |
| 8 | 207-216 | 10 | D | Data inicial dos registros no arquivo. |
| 9 | 217-226 | 10 | D | Data final dos registros no arquivo. |
| 10 | 227-250 | 24 | DH | Data e hora da geração do arquivo. |
| 11 | 251-253 | 3 | N | Versão do leiaute do AFD. Preencher com `"003"`. |
| 12 | 254-254 | 1 | N | Tipo de identificador do fabricante/desenvolvedor do REP: `"1"`=CNPJ, `"2"`=CPF. |
| 13 | 255-268 | 14 | N | CNPJ ou CPF do fabricante/desenvolvedor do REP. |
| 14 | 269-298 | 30 | A | Modelo (apenas para REP-C). |
| 15 | 299-302 | 4 | A | CRC-16 do registro (hex, sem `"0x"`). |

### Tipo "2" — Inclusão ou alteração da identificação da empresa no REP (331 caracteres)

| # | Posição | Tam. | Tipo | Conteúdo |
|---|---|---|---|---|
| 1 | 001-009 | 9 | N | NSR. |
| 2 | 010-010 | 1 | N | Tipo do registro. `"2"`. |
| 3 | 011-034 | 24 | DH | Data e hora da gravação do registro. |
| 4 | 035-048 | 14 | N | CPF do responsável pela inclusão/alteração. |
| 5 | 049-049 | 1 | N | Tipo de identificador do empregador: `"1"`=CNPJ, `"2"`=CPF. |
| 6 | 050-063 | 14 | N | CNPJ ou CPF do empregador. |
| 7 | 064-077 | 14 | N | CNO ou CAEPF, quando existir. |
| 8 | 078-227 | 150 | A | Razão social ou nome do empregador. |
| 9 | 228-327 | 100 | A | Local de prestação de serviços. |
| 10 | 328-331 | 4 | A | CRC-16 do registro (hex, sem `"0x"`). |

*Nota: campo 4 ("CPF do responsável") tem 14 posições aqui, mas 11 no tipo "4" e 11 no tipo "5" — divergência presente no texto oficial em si, não erro de transcrição (verificado por soma de posições).*

### Tipo "3" — Marcação de ponto para REP-C e REP-A (50 caracteres) — **não se aplica ao REP-P**

| # | Posição | Tam. | Tipo | Conteúdo |
|---|---|---|---|---|
| 1 | 001-009 | 9 | N | NSR. |
| 2 | 010-010 | 1 | **A** | Tipo do registro. `"3"`. *(tipo de campo A, não N — assim consta na fonte, mesmo sendo um dígito.)* |
| 3 | 011-034 | 24 | DH | Data e hora da marcação de ponto. |
| 4 | 035-046 | 12 | N | CPF do empregado. |
| 5 | 047-050 | 4 | A | CRC-16 do registro (hex, sem `"0x"`). |

### Tipo "4" — Ajuste do relógio (73 caracteres)

| # | Posição | Tam. | Tipo | Conteúdo |
|---|---|---|---|---|
| 1 | 001-009 | 9 | N | NSR. |
| 2 | 010-010 | 1 | N | Tipo do registro. `"4"`. |
| 3 | 011-034 | 24 | DH | Data e hora antes do ajuste. |
| 4 | 035-058 | 24 | DH | Data e hora ajustada. |
| 5 | 059-069 | 11 | N | CPF do responsável pela alteração. |
| 6 | 070-073 | 4 | A | CRC-16 do registro (hex, sem `"0x"`). |

### Tipo "5" — Inclusão, alteração ou exclusão de empregado no REP (118 caracteres)

| # | Posição | Tam. | Tipo | Conteúdo |
|---|---|---|---|---|
| 1 | 001-009 | 9 | N | NSR. |
| 2 | 010-010 | 1 | N | Tipo do registro. `"5"`. |
| 3 | 011-034 | 24 | DH | Data e hora da gravação do registro. |
| 4 | 035-035 | 1 | A | Tipo de operação: `"I"`=inclusão, `"A"`=alteração, `"E"`=exclusão. |
| 5 | 036-047 | 12 | N | CPF do empregado. |
| 6 | 048-099 | 52 | A | Nome do empregado. |
| 7 | 100-103 | 4 | A | Demais dados de identificação do empregado (a fonte não detalha o conteúdo exato deste campo — **NÃO CONFIRMADO** o que exatamente vai aqui). |
| 8 | 104-114 | 11 | N | CPF do responsável pela alteração. |
| 9 | 115-118 | 4 | A | CRC-16 do registro (hex, sem `"0x"`). |

### Tipo "6" — Eventos sensíveis do REP (36 caracteres, sem CRC-16)

| # | Posição | Tam. | Tipo | Conteúdo |
|---|---|---|---|---|
| 1 | 001-009 | 9 | N | NSR. |
| 2 | 010-010 | 1 | N | Tipo do registro. `"6"`. |
| 3 | 011-034 | 24 | DH | Data e hora da gravação do registro. |
| 4 | 035-036 | 2 | N | Tipo de evento (ver tabela abaixo). |

Valores do campo 4 (tipo de evento):

| Código | Significado | Exclusivo de |
|---|---|---|
| `01` | Abertura do REP por manutenção ou violação | REP-C |
| `02` | Retorno de energia | REP-C ou REP-P |
| `03` | Introdução de dispositivo externo de memória na Porta Fiscal | REP-C |
| `04` | Retirada de dispositivo externo de memória na Porta Fiscal | REP-C |
| `05` | Emissão da Relação Instantânea de Marcações | REP-C |
| `06` | Erro de impressão | REP-C |
| `07` | Disponibilidade de serviço | REP-P |
| `08` | Indisponibilidade de serviço | REP-P |

Confirmado: o registro tipo "6" **não tem CRC-16**, consistente com a regra 8 da seção 6 (CRC-16 limitado aos tipos 1–5).

### Tipo "7" — Marcação de ponto para REP-P (137 caracteres, sem CRC-16, com hash SHA-256) ⭐

**Este é o registro central do REP-P** citado no `FASES-E-AGENTES.md`. Confirmado: NSR + tipo + data/hora + CPF **fazem parte do registro, mas o campo de verificação é hash SHA-256, não CRC-16**, ao contrário do que a premissa do projeto assumia.

| # | Posição | Tam. | Tipo | Conteúdo |
|---|---|---|---|---|
| 1 | 001-009 | 9 | N | NSR. |
| 2 | 010-010 | 1 | **A** | Tipo do registro. `"7"`. *(tipo A na fonte, não N.)* |
| 3 | 011-034 | 24 | DH | Data e hora da marcação de ponto. |
| 4 | 035-046 | 12 | N | CPF do empregado. |
| 5 | 047-070 | 24 | DH | Data e hora de **gravação** do registro (distinta do campo 3 — permite marcação offline gravada depois). |
| 6 | 071-072 | 2 | N | Identificador do coletor da marcação: `01`=app mobile, `02`=browser, `03`=app desktop, `04`=dispositivo eletrônico, `05`=outro não especificado. |
| 7 | 073-073 | 1 | N | `"0"` = marcação on-line, `"1"` = marcação off-line. |
| 8 | 074-137 | 64 | A | **Código hash** (SHA-256, representação hexadecimal = 64 caracteres). |

**Especificação do hash (seção 8.2 abaixo tem a lacuna detalhada).**

### Tipo "9" — Trailer (64 caracteres, sem CRC-16)

| # | Posição | Tam. | Tipo | Conteúdo |
|---|---|---|---|---|
| 1 | 001-009 | 9 | N | `"999999999"` (constante). |
| 2 | 010-018 | 9 | N | Quantidade de registros do tipo "2". |
| 3 | 019-027 | 9 | N | Quantidade de registros do tipo "3". |
| 4 | 028-036 | 9 | N | Quantidade de registros do tipo "4". |
| 5 | 037-045 | 9 | N | Quantidade de registros do tipo "5". |
| 6 | 046-054 | 9 | N | Quantidade de registros do tipo "6". |
| 7 | 055-063 | 9 | N | Quantidade de registros do tipo "7". |
| 8 | 064-064 | 1 | N | Tipo do registro. `"9"`. |

Nota: o trailer **não conta** os registros do tipo "1" (cabeçalho — sempre exatamente 1) nem de si mesmo (tipo "9" — sempre exatamente 1).

### Linha final — Assinatura digital (100 caracteres, sem número de tipo)

| # | Posição | Tam. | Tipo | Conteúdo |
|---|---|---|---|---|
| 1 | 001-100 | 100 | A | Assinatura digital. **Para REP-A e REP-P**: preencher com o texto literal `"ASSINATURA_DIGITAL_EM_ARQUIVO_P7S"` e espaços à direita até completar 100 caracteres (a assinatura real fica no arquivo `.p7s` destacado, não embutida no AFD). |

Esta linha **não é um "tipo de registro" numerado** — é a última linha do arquivo, fora da contagem do trailer.

---

## 8. Algoritmos de verificação

### 8.1 CRC-16

Fonte: leiaute oficial do AFD, regra 8 e observação (OBS) subsequente. Citação literal:

> *"Para o AFD gerado pelo REP-A ou pelo REP-P, deve ser utilizado o padrão CRC-16 CCITT-TRUE (CRC-16/KERMIT). Por exemplo, os 9 caracteres "123456789" geram o CRC-16 de valor 0x2189 em hexadecimal com esse algoritmo. Os 4 caracteres hexadecimais do CRC-16 devem ser gravados no campo de CRC do arquivo AFD nesta ordem ("2189" no exemplo, que é a representação hexadecimal sem o "0x")."*

Isto é **inequívoco e verificável**: `0x2189` é exatamente o *check value* catalogado publicamente para a variante **CRC-16/KERMIT** (também conhecida como CRC-16/CCITT-TRUE) sobre a string de teste padrão `"123456789"`. Os parâmetros dessa variante, de conhecimento técnico público (catálogo de CRCs, não específico da Portaria — a norma não os declara explicitamente, apenas nomeia o padrão e dá o vetor de teste, que bate exatamente com estes parâmetros):

- **Largura**: 16 bits.
- **Polinômio**: `0x1021`.
- **Valor inicial**: `0x0000`.
- **RefIn**: sim (bytes de entrada refletidos).
- **RefOut**: sim (registro final refletido).
- **XorOut**: `0x0000`.
- **Check ("123456789")**: `0x2189` — bate com o exemplo da fonte oficial.

**Escopo do cálculo**: aplica-se apenas aos registros dos tipos "1" a "5" (regra 8 da seção 6). O texto diz "CRC-16 ... do registro" — interpretação razoável (não 100% explícita na fonte) é que o CRC cobre os bytes do registro na sua representação de largura fixa, da posição 1 até a posição imediatamente anterior ao campo de CRC, excluindo o próprio campo de CRC e excluindo o terminador CR LF. **Isto é inferência razoável, não citação literal** — recomendo confirmar contra um AFD de referência antes de assumir como definitivo.

### 8.2 SHA-256 (registro tipo "7")

Fonte: leiaute oficial do AFD, regras 9 + texto que segue a tabela do tipo "7". Citação literal:

> *"Será utilizado o padrão SHA-256 na geração do código hash especificado no campo nº 8, e seu cálculo será feito com base nos dados abaixo: 1. NSR (campo nº 1); 2. tipo do registro (campo nº 2); 3. data e hora da marcação de ponto (campo nº 3); 4. CPF do empregado (campo nº 4); 5. data e hora da gravação do registro (campo nº 5); 6. identificador do coletor da marcação (campo nº 6); 7. informação se a marcação foi on-line ou off-line (campo nº 7); e 8. código hash (SHA-256) do registro anterior, caso exista."*

Confirmações:
- É um **hash por registro**, não um hash do arquivo inteiro. A premissa "SHA-256 do arquivo" do projeto está incorreta (ver seção 2).
- É uma **cadeia de hashes** (blockchain-like): o hash de cada registro tipo "7" inclui o hash SHA-256 do registro tipo "7" **imediatamente anterior**, "caso exista" (ou seja, o primeiro registro tipo "7" do arquivo/da sequência do REP não tem um hash anterior para encadear — **NÃO CONFIRMADO** o que substitui esse insumo ausente: campo vazio, string vazia, ausência total do 8º insumo na concatenação, ou outro valor sentinela).
- **NÃO CONFIRMADO** (Lacuna nº 1, seção 1): o formato exato de concatenação dos 7 valores de campo + o hash anterior antes de aplicar SHA-256. A fonte lista os insumos mas não diz se são concatenados em sua representação de campo do próprio registro AFD (com padding de largura fixa), em formato "cru" sem padding, com algum separador entre eles, nem a codificação de bytes usada para a concatenação (embora ISO 8859-1 seja a codificação do arquivo como um todo, isso não foi dito explicitamente para o cálculo do hash).

**Este é o item de maior risco técnico de todo o documento** porque bloqueia diretamente o critério de aceite de comparação byte a byte para o tipo de registro mais importante do REP-P.

### 8.3 SHA-256 no AEJ

Não encontrei, nas fontes lidas (leiaute oficial do AEJ, Perguntas e Respostas oficiais), nenhuma menção a um requisito de hash SHA-256 dentro do próprio AEJ. A integridade do AEJ é garantida por assinatura eletrônica CAdES em arquivo `.p7s` destacado (seção 11), não por um campo de hash embutido como no AFD tipo "7". Se o projeto presumia um hash SHA-256 também no AEJ, isso não foi confirmado — trate como **não existente** até prova em contrário.

---

## 9. Regras gerais do AEJ

Fonte: leiaute oficial do AEJ (fonte 2 acima).

1. Formato texto, codificado em **ASCII/ISO 8859-1**. Igual ao AFD.
2. Cada linha = um registro, terminando com **caracteres 13 e 10** (CR LF) ISO 8859-1. Igual ao AFD.
3. **Diferente do AFD**: cada campo é terminado pelo caractere delimitador **`"|"` (pipe/barra vertical)**, exceto o último campo do registro (que vai direto seguido do CR LF). **A premissa do projeto sobre separador `\|` está correta para o AEJ**, mas — conforme a correção da seção 2 — **não** para o AFD.
4. Sem linhas em branco.
5. Tipos de dado por campo:
   - `N`: numérico.
   - `A`: alfanumérico.
   - `H`: hora, formato `hhmm` (4 dígitos, sem separador).
   - `D`: data, formato `AAAA-MM-dd`.
   - `DH`: data e hora, mesmo formato do AFD (`AAAA-MM-ddThh:mm:00ZZZZZ`).
6. Como os campos são delimitados por `|` (e não de largura fixa), os tamanhos nas tabelas da seção 10 aparecem como **faixas** (ex.: `1 a 150`, `1 a 9`) — é o tamanho do conteúdo real, não uma posição fixa no arquivo.

---

## 10. AEJ — tipos de registro (leiaute completo)

Fonte: leiaute oficial do AEJ. Nomes de campo (coluna "Campo") são os identificadores técnicos usados pela própria norma (ex.: `tipoReg`, `idtVinculoAej`) — úteis para nomear variáveis/colunas no gerador de forma rastreável até a norma.

### Tipo "01" — Cabeçalho

| # | Campo | Tam. | Tipo | Conteúdo |
|---|---|---|---|---|
| 1 | `tipoReg` | 2 | N | `"01"`. |
| 2 | `tpIdtEmpregador` | 1 | N | `"1"`=CNPJ, `"2"`=CPF. |
| 3 | `idtEmpregador` | 11 ou 14 | N | CNPJ ou CPF do empregador. |
| 4 | `caepf` | 14 | N | CAEPF, se existir. |
| 5 | `cno` | 12 | N | CNO, se existir. |
| 6 | `razaoOuNome` | 1 a 150 | A | Razão social ou nome do empregador. |
| 7 | `dataInicialAej` | 10 | D | Data inicial dos registros no AEJ. |
| 8 | `dataFinalAej` | 10 | D | Data final dos registros no AEJ. |
| 9 | `dataHoraGerAej` | 24 | DH | Data e hora da geração do AEJ. |
| 10 | `versaoAej` | 3 | A | Versão do leiaute do AEJ. Preencher com `"001"`. |

### Tipo "02" — REPs utilizados

| # | Campo | Tam. | Tipo | Conteúdo |
|---|---|---|---|---|
| 1 | `tipoReg` | 2 | N | `"02"`. |
| 2 | `idRepAej` | 1 a 9 | N | Identificador do REP dentro do AEJ (chave local, referenciada por outros registros). |
| 3 | `tpRep` | 1 | N | `"1"`=REP-C, `"2"`=REP-A, `"3"`=REP-P. |
| 4 | `nrRep` | 17 | N | Número de fabricação (REP-C) / processo do acordo/convenção (REP-A, ou `"99999999999999999"` se não houver) / **número de registro no INPI (REP-P)**. Obrigatório quando `fonteMarc` (registro tipo "05") = `"O"`. |

### Tipo "03" — Vínculos

| # | Campo | Tam. | Tipo | Conteúdo |
|---|---|---|---|---|
| 1 | `tipoReg` | 2 | N | `"03"`. |
| 2 | `idtVinculoAej` | 1 a 9 | N | Identificador do vínculo empregatício dentro do AEJ (chave local). |
| 3 | `cpf` | 11 | N | CPF do empregado. |
| 4 | `nomeEmp` | 1 a 150 | A | Nome do empregado. |

### Tipo "04" — Horário contratual

| # | Campo | Tam. | Tipo | Conteúdo |
|---|---|---|---|---|
| 1 | `tipoReg` | 2 | N | `"04"`. |
| 2 | `codHorContratual` | 1 a 30 | A | Código do horário contratual (chave local). |
| 3 | `durJornada` | 1 a 12 | N | Duração da jornada, em minutos. |
| 4 | `hrEntrada01` | 4 | H | Hora da 1ª entrada. |
| 5 | `hrSaida01` | 4 | H | Hora da 1ª saída. |
| 6 | `hrEntrada02` | 0 ou 4 | H | Hora da 2ª entrada (condicional). |
| 7 | `hrSaida02` | 0 ou 4 | H | Hora da 2ª saída (condicional). |

Observações da própria norma: se houver mais de 2 pares entrada/saída, seguem-se campos `hrEntradaNN`/`hrSaidaNN` na sequência (NN = ordem do par). Se o horário for noturno, `durJornada` já deve refletir a redução da hora noturna.

### Tipo "05" — Marcações

| # | Campo | Tam. | Tipo | Conteúdo |
|---|---|---|---|---|
| 1 | `tipoReg` | 2 | N | `"05"`. |
| 2 | `idtVinculoAej` | 1 a 9 | N | Referência ao registro tipo "03". |
| 3 | `dataHoraMarc` | 24 | DH | Data e hora da marcação. |
| 4 | `idRepAej` | 0 a 9 | N | Referência ao registro tipo "02" (0 = sem REP associado). |
| 5 | `tpMarc` | 1 | A | `"E"`=entrada, `"S"`=saída, `"D"`=desconsiderada. |
| 6 | `seqEntSaida` | 3 | N | Número sequencial do par entrada/saída. |
| 7 | `fonteMarc` | 1 | A | `"O"`=original do REP, `"I"`=incluída manualmente, `"P"`=pré-assinalada, `"X"`=incluída (ponto por exceção), `"T"`=outras fontes. |
| 8 | `codHorContratual` | 0 a 30 | A | Referência ao registro tipo "04". Obrigatório quando `tpMarc="E"` e `seqEntSaida="1"`. |
| 9 | `motivo` | 0 a 150 | A | Motivo da desconsideração/inclusão. Obrigatório quando `tpMarc="D"` ou `fonteMarc="I"`. |

**Este é o registro-chave para o banco de horas e a apuração** (F4), já que carrega o vínculo entre marcação real e horário contratual.

### Tipo "06" — Identificação da matrícula do vínculo no eSocial (múltiplos vínculos)

| # | Campo | Tam. | Tipo | Conteúdo |
|---|---|---|---|---|
| 1 | `tipoReg` | 2 | N | `"06"`. |
| 2 | `idtVinculoAej` | 1 a 9 | N | Referência ao registro tipo "03". |
| 3 | `matEsocial` | 1 a 30 | A | Matrícula do vínculo no eSocial. |

Só existe "para empregados com mais de um vínculo no AEJ" (título literal da tabela na fonte).

### Tipo "07" — Ausências e Banco de Horas

| # | Campo | Tam. | Tipo | Conteúdo |
|---|---|---|---|---|
| 1 | `tipoReg` | 2 | N | `"07"`. |
| 2 | `idtVinculoAej` | 1 a 9 | N | Referência ao registro tipo "03". |
| 3 | `tipoAusenOuComp` | 1 | N | `"1"`=DSR, `"2"`=falta não justificada, `"3"`=movimento no banco de horas, `"4"`=folga compensatória de feriado. |
| 4 | `data` | 10 | D | Data da ausência/compensação. |
| 5 | `qtMinutos` | 0 a 12 | N | Quantidade de minutos. Obrigatório se `tipoAusenOuComp="3"`. |
| 6 | `tipoMovBH` | 0 ou 1 | N | `"1"`=inclusão no banco de horas, `"2"`=compensação. Obrigatório se `tipoAusenOuComp="3"`. |

### Tipo "08" — Identificação do PTRP

| # | Campo | Tam. | Tipo | Conteúdo |
|---|---|---|---|---|
| 1 | `tipoReg` | 2 | N | `"08"`. |
| 2 | `nomeProg` | 1 a 150 | A | Nome do PTRP. |
| 3 | `versaoProg` | 1 a 8 | A | Versão do PTRP. |
| 4 | `tpIdtDesenv` | 1 | N | `"1"`=CNPJ, `"2"`=CPF do desenvolvedor. |
| 5 | `idtDesenv` | 11 ou 14 | N | CNPJ ou CPF do desenvolvedor do PTRP. |
| 6 | `razaoNomeDesenv` | 1 a 150 | A | Razão social ou nome do desenvolvedor. |
| 7 | `emailDesenv` | 1 a 50 | N | E-mail do desenvolvedor. *(A fonte declara tipo `N` para um campo de e-mail — provável erro de digitação no documento oficial, já que um e-mail não é numérico. Registrar como observado; **não corrigir silenciosamente** — o gerador deve tratar como texto livre mas isto é uma discrepância literal da norma que vale a pena reportar ao MTE/verificar contra referência de mercado.)* |

### Tipo "99" — Trailer

| # | Campo | Tam. | Tipo | Conteúdo |
|---|---|---|---|---|
| 1 | `tipoReg` | 2 | N | `"99"`. |
| 2 | `qtRegistrosTipo01` | 1 a 9 | N | Quantidade de registros tipo "01". |
| 3 | `qtRegistrosTipo02` | 1 a 9 | N | Quantidade de registros tipo "02". |
| 4 | `qtRegistrosTipo03` | 1 a 9 | N | Quantidade de registros tipo "03". |
| 5 | `qtRegistrosTipo04` | 1 a 9 | N | Quantidade de registros tipo "04". |
| 6 | `qtRegistrosTipo05` | 1 a 9 | N | Quantidade de registros tipo "05". |
| 7 | `qtRegistrosTipo06` | 1 a 9 | N | Quantidade de registros tipo "06". |
| 8 | `qtRegistrosTipo07` | 1 a 9 | N | Quantidade de registros tipo "07". |
| 9 | `qtRegistrosTipo08` | 1 a 9 | N | Quantidade de registros tipo "08". |

Nota: diferente do trailer do AFD, este **não conta a si mesmo nem precisa contar o tipo "01"** implicitamente (mesma lógica: cabeçalho é sempre exatamente 1 e o próprio trailer é sempre exatamente 1, portanto omitidos).

### Linha final — Assinatura digital

| # | Campo | Tam. | Tipo | Conteúdo |
|---|---|---|---|---|
| 1 | `assinDigital` | 100 | A | Preencher com o texto literal `"ASSINATURA_DIGITAL_EM_ARQUIVO_P7S"` e espaços à direita até 100 caracteres. |

Igual ao padrão do AFD: a assinatura real fica em arquivo `.p7s` destacado.

---

## 11. Assinatura eletrônica — quem assina o quê

Fonte primária: **Art. 86, §§1º e 2º**, na redação dada pela **Portaria MTP nº 4.198/2022** (fonte 3 da seção 3, DOU 21/12/2022, Edição 239, Seção 1, Página 359) — citação literal:

> *"§ 1º A assinatura eletrônica, do fabricante ou do desenvolvedor, deve ser atribuída às saídas geradas pelo REP: Arquivo Fonte de Dados, Comprovante de Registro de Ponto do Trabalhador e, no caso do REP-C, Relação Instantânea de Marcações.*
> *§ 2º A assinatura eletrônica, do desenvolvedor ou do empregador, deve ser atribuída à saída gerada pelo Programa de Tratamento de Registro de Ponto: Arquivo Eletrônico de Jornada."*

Ou seja:
- **AFD**: assinado pelo **fabricante ou desenvolvedor do REP** (para o SEEG Ponto como REP-P, isso é a própria SEEG como desenvolvedora do software, ou quem ela designar).
- **AEJ**: assinado pelo **desenvolvedor do PTRP OU pelo empregador** (o texto oferece as duas opções, não restringe a uma única parte).

Padrões de formato (fonte: Perguntas e Respostas oficiais do MTE, perguntas 28–30, 33–34 — confiança alta por ser FAQ institucional, mas não é o texto legal em si):
- AFD: assinatura eletrônica em padrão **CAdES**, armazenada em arquivo **`.p7s` destacado**, com certificado válido emitido no âmbito da **ICP-Brasil**.
- AEJ: mesmo padrão **CAdES / `.p7s` destacado**.
- Comprovante de Registro de Ponto do Trabalhador em PDF (quando emitido pelo REP-P): padrão **PAdES**.

Esta portaria de alteração (4.198/2022) **não mexeu no leiaute técnico do AFD/AEJ** (Anexos V/VI) — apenas em quem deve assinar. Confirmado por leitura direta e completa das 23 páginas do DOU: nenhuma outra menção a AFD/AEJ/REP no restante do texto publicado nesse mesmo diploma.

---

## 12. NSR (Número Sequencial de Registro)

Fonte: Perguntas e Respostas oficiais do MTE (pergunta 41), confirmado também por reprodução em `guiatrabalhista.com.br` citando a mesma fonte. Conteúdo (paráfrase próxima do original, já que a fonte é um FAQ e não um artigo legal citável literalmente com o mesmo rigor):

- **Cada estabelecimento** (identificado por CNPJ de 14 posições ou CPF de 11 posições) tem **sua própria sequência de NSR**.
- A numeração é **sequencial, em incrementos unitários, começando em 1** na primeira operação do REP em relação àquele estabelecimento.
- O mesmo procedimento pode ser adotado pelo REP-A (a fonte não menciona explicitamente o REP-P nesta frase específica, mas o restante do documento trata REP-A e REP-P de forma equivalente na maioria das regras de arquivo — **NÃO CONFIRMADO com 100% de certeza que a mesma regra de "por estabelecimento" se aplica textualmente ao REP-P nesta pergunta específica do FAQ**, embora seja a leitura mais razoável dado o resto do documento).
- Onde aparece no arquivo: campo 1 de todos os tipos de registro do AFD exceto o tipo "1" (cabeçalho, que usa a constante `"000000000"`) e o tipo "9" (trailer, que usa a constante `"999999999"`).
- A regra "sem lacunas" não está redigida literalmente com essas palavras na fonte que consultei — é inferida da combinação "sequencial, em incrementos unitários" + a exigência de ordenação dos registros pelo NSR (regra 4, seção 6). Tratar como requisito forte, mas **a redação literal exata ("sem lacunas") não foi confirmada em nenhuma fonte primária consultada nesta sessão**.

---

## 13. Fracionamento do arquivo

Fonte: Perguntas e Respostas oficiais do MTE (pergunta 39).

- **AFD gerado por REP-C**: **não pode** ser fracionado — deve conter todos os dados armazenados na Memória de Registro de Ponto (MRP) do equipamento.
- **AFD gerado por REP-A ou REP-P**: **pode** ser fracionado.
- **NÃO CONFIRMADO**: a fonte não especifica periodicidade, critério de corte (por competência mensal? por ano-calendário? por tamanho de arquivo?), nem se há um limite mínimo/máximo. Nenhuma fonte consultada tratou do fracionamento do **AEJ** especificamente.

---

## 14. Glossário rápido (para o gerador)

| Sigla | Nome completo | Confirmado em |
|---|---|---|
| AFD | Arquivo Fonte de Dados | Leiaute oficial AFD |
| AEJ | Arquivo Eletrônico de Jornada | Leiaute oficial AEJ |
| PTRP | Programa de Tratamento de Registro de Ponto | Leiaute oficial AEJ, registro tipo "08" |
| REP-C | Registrador Eletrônico de Ponto Convencional | Art. 76 (fonte secundária cruzada) |
| REP-A | Registrador Eletrônico de Ponto Alternativo | Art. 77 (fonte secundária cruzada) |
| REP-P | Registrador Eletrônico de Ponto via Programa | Art. 78 (fonte secundária cruzada) |
| NSR | Número Sequencial de Registro | Leiaute oficial AFD, regra 4 + FAQ pergunta 41 |
| CAEPF | Cadastro de Atividade Econômica da Pessoa Física | Leiaute oficial AFD/AEJ |
| CNO | Cadastro Nacional de Obras | Leiaute oficial AFD/AEJ |

---

## 15. Recomendações concretas para a Fase 12 (A1/A2/A3)

1. **Antes de codificar o registro tipo "7"**: obter um AFD de referência de um fabricante REP-P já homologado (ou abrir chamado formal com a Secretaria de Inspeção do Trabalho/MTE pedindo esclarecimento do formato exato de concatenação do hash SHA-256) para fechar a Lacuna nº 1. Sem isso, qualquer implementação é uma hipótese razoável, não uma garantia de bater byte a byte.
2. **Implementar dois modos de preenchimento de campo N no AFD** (zero-padded-à-direita vs espaço-padded-à-direita conforme a leitura literal da regra 7) atrás de uma constante/flag isolada, para permitir alternar rapidamente qual interpretação está correta assim que houver um AFD de referência para comparar (Lacuna nº 2).
3. **Não implementar hash de arquivo inteiro** para o AFD — apenas a cadeia de hash por registro tipo "7" (seção 8.2). Não implementar hash algum para o AEJ (seção 8.3).
4. **Gerador de AFD não deve usar `\|` como separador.** Gerador de AEJ deve.
5. **Registrar como dívida técnica explícita** (no mesmo padrão do `docs/backlog.md` do projeto) as lacunas 1, 2, 3, 4 e 5 da seção 1, com este documento como referência, assim que a Fase 12 for planejada em detalhe (`/gsd:plan-phase` ou equivalente).
6. Revisar `FASES-E-AGENTES.md` linha 320 para corrigir a menção a "separador `\|`" e "CRC-16" no registro tipo 7, conforme a seção 2 deste documento.

---

## 16. Metodologia desta pesquisa

Busca feita via WebSearch/WebFetch em 2026-07-30, priorizando domínios `.gov.br` e `in.gov.br` conforme instruído. Os dois documentos técnicos centrais (leiaute AFD e leiaute AEJ) foram obtidos como PDF binário diretamente do domínio oficial `gov.br` e lidos integralmente por extração de texto de PDF — não por resumo de um modelo intermediário, o que elimina o risco de paráfrase incorreta nas tabelas de campo (o WebFetch padrão, que usa um modelo pequeno para resumir PDFs, falhou em extrair essas tabelas corretamente nas primeiras tentativas; o PDF binário salvo foi então lido diretamente). A consistência aritmética de todas as somas de tamanho de campo contra a posição final declarada (seção 7) foi conferida manualmente registro por registro e bateu em 100% dos casos, o que é evidência de que a extração de texto do PDF não perdeu nem duplicou conteúdo nas tabelas do AFD.
