# F12 — Conformidade REP-P (AFD, AEJ, assinatura) ⭐ CRÍTICA

| | |
|---|---|
| **Onda** | 4 |
| **Agentes** | 3 · **A1** REP-P + gerador de **AFD** (T0 já concluída, tipos 1–6/9 com leiaute confirmado, tipo 7 com fórmula de melhor esforço do ADR-012, módulo comum de formatos) · **A2** gerador de **AEJ** (cabeçalho, REPs utilizados, vínculos, horário contratual, marcações, matrícula eSocial, ausências, banco de horas, PTRP, trailer) · **A3** assinatura **CAdES** em `.p7s` destacado, assinatura do comprovante, cofre de arquivos (listagem/download/histórico), validação cruzada |
| **Duração estimada** | 8 dias |
| **Depende de** | F5 (ingestão de marcações e NSR, concluída, commit `6a75b89`) · F4 (cálculo e banco de horas, concluída, commit `6350709`) · F10 (workflows, aprovações e fechamento, concluída, commit `d8673a9`) |
| **Criticidade** | ⭐ CRÍTICA — é a fase que produz os arquivos exigidos pela fiscalização trabalhista (Portaria MTP 671/2021) para uma empresa real (SEEG). Precisão factual pesa mais nesta fase do que em qualquer outra já construída. |
| **Branch** | `f12-conformidade-rep-p` |

---

## 1. Objetivo

Ao fim desta fase, a SEEG consegue **gerar um AFD e um AEJ reais** a partir dos dados que o sistema
já produziu em fases anteriores — marcações imutáveis com NSR sem lacunas (F5), tratamentos e banco de
horas apurados (F4), períodos fechados e espelhos assinados pelo colaborador (F10) — e **guardar esses
arquivos num cofre** com histórico, download e (quando o certificado existir) **assinatura eletrônica
CAdES verificável**. As operações da tag `fiscal` deixam de responder `501` e passam a implementar:
cadastro de REP-P com sequência de NSR própria; geração de AFD que **deriva exclusivamente das
marcações**, com verificação prévia de continuidade de NSR que recusa gerar um arquivo com lacuna;
geração de AEJ que **enxerga tratamento, ausência e banco de horas** além das marcações, com o bloco de
banco de horas batendo com o extrato real; assinatura CAdES em `.p7s` destacado quando um certificado
estiver configurado, e geração válida-porém-não-assinada quando não estiver (é o estado atual e
confirmado da SEEG, ver §2.4).

**O que esta fase explicitamente não faz:** cálculo de apuração, tratamento ou banco de horas (F4,
concluída — esta fase só **lê**); geração ou alocação de NSR (F5, concluída — esta fase só **consome** o
NSR que já existe); fechamento de período ou assinatura do espelho de ponto do colaborador (F10,
concluída — é uma assinatura diferente, ver §2.14); relatórios gerenciais/operacionais, exportação
CSV/XLSX, ou o PDF "de designer" do espelho (F11 — que provavelmente ainda não existe quando você lê
isto, ver §2.12); obtenção do certificado e-CNPJ A1 real da SEEG (decisão de negócio fora do alcance de
uma sessão de desenvolvimento, ver §2.4); fechar a Lacuna nº 1 do ADR-012 sobre a fórmula do hash do
registro tipo "7" (decisão já tomada: a fase **prossegue** com melhor esforço documentado, ver §2.3). Se
você está prestes a recalcular uma apuração, gerar um NSR novo, desenhar um PDF de relatório, ou tentar
"resolver" a fórmula do hash do tipo 7 sozinho, pare: não é desta fase.

## 2. Contexto mínimo

**O produto.** Sistema de ponto eletrônico brasileiro **REP-P** (Portaria MTP 671/2021), SaaS
multi-tenant. Toda tabela desta fase carrega `tenant_id` sob **Row Level Security**; a aplicação abre
cada transação publicando `app.tenant_id` (`apps/api/app/db/sessao.py::obter_sessao`, real, F1). Você
não desabilita RLS.

A sequência canônica do motor, com o elo desta fase no fim (`packages/contracts/glossario.md` §5):

```
marcação (F5, imutável, com NSR/CRC-16/hash PRÓPRIOS de F5 — NÃO são o leiaute, ver §2.5)
      ↓
tratamento aprovado, apuração, banco de horas (F4, já implementado)
      ↓
fechamento de período, espelho assinado pelo colaborador (F10, já implementado)
      ↓
AFD  (esta fase, A1 — deriva EXCLUSIVAMENTE das marcações, nunca vê tratamento)
AEJ  (esta fase, A2 — deriva de vínculo + horário contratual + marcações + tratamento + ausência +
      banco de horas — é quem "enxerga" a correção, o AFD nunca vê)
      ↓
assinatura CAdES + cofre (esta fase, A3)
```

A seta nunca aponta para trás: esta fase não recalcula nada e não aloca NSR novo. Ela **lê** o que F4/F5
já produziram e **empacota** no formato exigido pela Portaria.

### 2.1 A T0 já concluída — leia `docs/leiaute-afd-aej.md` inteiro antes de codificar

Antes de escrever qualquer linha do gerador, a tarefa T0 desta fase (já concluída em 30/07/2026)
conferiu o leiaute do AFD e do AEJ **campo a campo** contra os dois PDFs técnicos oficiais do MTE (não
contra resumo de terceiro, não contra memória do modelo), e está documentada por inteiro em
[`docs/leiaute-afd-aej.md`](../leiaute-afd-aej.md). Este PCF **não repete** o conteúdo técnico completo
daquele documento (as 15 seções com todas as tabelas de campo, posição, tamanho e tipo) — você lê o
documento inteiro, não só este resumo. O que este PCF faz é **resumir os pontos que mudam o desenho**
do gerador e **fixar decisões** que o documento deixou como recomendação para quem planejasse a fase em
detalhe — que é exatamente o papel deste PCF agora.

O item do `docs/backlog.md` (linha "2026-07-25 | F0 / verificação | Conferir o leiaute do AFD e do AEJ
campo a campo... | F12") que apontava para esta pesquisa como bloqueio **está resolvido** pela T0 — não é
mais um bloqueio, mas continua registrado no backlog como histórico de por que a pesquisa foi feita.

### 2.2 As três correções de premissa que `FASES-E-AGENTES.md` linha 320 tinha (já corrigida, mas leia aqui o resumo)

A T0 encontrou três divergências entre o que o projeto presumia sobre o leiaute e o que a norma
realmente diz (`docs/leiaute-afd-aej.md` §2). `FASES-E-AGENTES.md` linha 320 já foi corrigida para
refletir isto — mas a correção **não se propagou** para vários outros lugares do repositório que você vai
ler ou tocar nesta fase (§2.7). Fixe estas três regras na cabeça antes de tudo:

1. **O AFD não usa `|` (pipe) como separador.** É um arquivo de **largura fixa por posição** — cada
   campo tem posição inicial e final definidas (colunas "Posição" das tabelas de
   `docs/leiaute-afd-aej.md` §7). O `|` é exclusivo do **AEJ** (`docs/leiaute-afd-aej.md` §9, regra 3).
2. **O registro tipo "7" (a marcação de ponto do REP-P) não tem CRC-16.** O CRC-16 é obrigatório
   **apenas para os tipos "1" a "5"** (`docs/leiaute-afd-aej.md` §6, regra 8). O tipo "6" não tem CRC-16
   nem hash. O tipo "7" tem, no lugar, um campo de **hash SHA-256 encadeado** (campo nº 8, "código
   hash").
3. **Não existe hash de arquivo inteiro exigido pelo leiaute.** O SHA-256 do leiaute é **por registro**,
   só no tipo "7", encadeado ao hash do registro tipo "7" anterior — não um hash calculado sobre o
   arquivo completo. (Isto não impede que o **contrato** desta aplicação — não a norma — exija um campo
   `hashSha256` de integridade sobre o arquivo gerado como um todo; essas são duas coisas diferentes,
   ver §2.6.)

### 2.3 ADR-012 — a fórmula do hash do tipo "7" incorporada às tarefas de A1

[`docs/adr/ADR-012-formula-hash-registro-tipo-7-afd-nao-confirmada.md`](../adr/ADR-012-formula-hash-registro-tipo-7-afd-nao-confirmada.md)
já **decidiu** (dono do produto, 30/07/2026) que esta fase **prossegue** mesmo sem a fórmula de
concatenação do hash SHA-256 do tipo "7" confirmada contra uma fonte primária suficiente. Isto não é
algo para você redecidir, questionar ou tentar "resolver de vez" pesquisando mais — é uma decisão já
tomada, que vira tarefa concreta de A1 (T3, §6):

1. **Fórmula implementada** (a única, sem escolha sua): os 8 insumos —
   NSR, tipo do registro, data/hora da marcação, CPF, data/hora de gravação, identificador do coletor,
   indicador on-line/off-line, hash do registro tipo "7" anterior — concatenados **na representação de
   largura fixa que cada campo teria no próprio registro do AFD** (mesmo padding), **sem separador**
   entre eles, codificados em **ISO 8859-1**. O primeiro registro tipo "7" da sequência do REP-P omite o
   8º insumo inteiramente (string vazia) na ausência de um hash anterior.
2. **Isolada atrás de uma função nomeada**, não espalhada pelo gerador — `app/fiscal/afd/hash_tipo7.py`
   (§5), para trocar de interpretação rapidamente se uma referência externa (AFD de fabricante
   homologado, ou resposta formal da SIT/MTE) aparecer no futuro.
3. **O critério de aceite "comparação byte a byte contra AFD de sistema já aceito" fica marcado como
   NÃO VERIFICÁVEL especificamente para o registro tipo "7"** nesta entrega (§7, critério 1) — não
   escondido, não reclassificado como "atendido com ressalva". Os tipos 1–6, 9 e todo o AEJ **não** têm
   essa limitação: o leiaute deles foi confirmado com alta confiança pela T0 e a comparação byte a byte
   é um critério real e alcançável para eles.
4. **Nunca implemente um hash de arquivo inteiro em nome de "resolver" esta lacuna.** A lacuna é sobre a
   fórmula de concatenação do hash **por registro**, não sobre precisar de mais um hash em outro nível.

Se você (A1) descobrir uma referência externa real durante a fase, documente-a e traga para o
orquestrador decidir — não troque a fórmula sozinho "porque parece mais certo agora": a fórmula atual é
a decisão fixada pelo ADR-012, e uma ADR aceita só muda com nova decisão do dono do produto.

### 2.4 Certificado ICP-Brasil indisponível — o padrão do adaptador (mesmo precedente de F10 §2.8)

**Confirmado indisponível pelo dono do produto em 30/07/2026: não existe certificado e-CNPJ A1
ICP-Brasil da SEEG.** Isto não bloqueia a fase — você constrói **o mecanismo inteiro** de assinatura
(módulo de assinatura CAdES real, geração de `.p7s` destacado real, fluxo de assinatura real, cofre com
histórico e download reais), mas a **credencial real** não existe ainda. O padrão a seguir é
**exatamente o mesmo que F10/A3 já usou para os canais de push e e-mail**
(`docs/fases/F10-workflows-aprovacoes-fechamento.md` §2.8): implementar a interface completa, com o
ponto de plugue óbvio, e usar um caminho provisório enquanto a credencial real não chega — mas a
natureza do "provisório" aqui é diferente da de F10, e a diferença importa:

- **Push/e-mail (F10) não tinha SDK nenhum para chamar** — sem credencial FCM/SMTP não existe nada
  real para exercitar, então o adaptador provisório era "log + marca como enviada", sem nenhuma chamada
  de rede.
- **CAdES é diferente: você PODE produzir uma assinatura CMS/PKCS#7 estruturalmente válida com QUALQUER
  par de certificado/chave privada**, inclusive um autoassinado — o que falta sem o e-CNPJ A1 real não é
  a capacidade de assinar, é a **cadeia de confiança até uma Autoridade Certificadora da ICP-Brasil**.
  Por isso o "provisório" desta fase não é "não assinar de verdade" — é: o **código de assinatura é
  real e completo** (`app/fiscal/assinatura/cades.py`, T11), mas a **configuração de certificado no
  ambiente está ausente**, exatamente como `docs/leiaute-afd-aej.md` §11 e o próprio catálogo de erros
  já preveem:
  - `PONTO-FISC-004` ("Certificado ICP-Brasil indisponível", `errors.yaml`) já existe no catálogo e já é
    citado no `x-erros` de `assinarArquivoFiscal`/`gerarAfd`/`gerarAej` — você não inventa nada, só
    implementa o caminho que o contrato já descreveu: `gerarAfd`/`gerarAej` com `assinar=true` e sem
    certificado configurado **concluem normalmente com `status='gerado'`** (não `'assinado'`, não
    erro) — é a leitura literal da descrição de `gerarAfd` no `openapi.yaml`: *"Com assinar verdadeiro,
    o .p7s CAdES destacado é produzido em seguida; sem certificado disponível, a geração conclui
    normalmente e a assinatura fica pendente."* Já `assinarArquivoFiscal` chamado diretamente **sem**
    certificado configurado responde `424 PONTO-FISC-004` (o usuário pediu explicitamente para assinar
    e não há como).
  - **Configuração do certificado**: variável de ambiente nova, mesmo padrão de `infra/.env.example`
    bloco 6 (MinIO) — acrescente um bloco `# 7. ASSINATURA FISCAL (CAdES)` com
    `FISCAL_CERTIFICADO_PFX_PATH` e `FISCAL_CERTIFICADO_SENHA` (ambas comentadas/vazias, exatamente
    como o bloco de SMTP/FCM que F10 documentou como ausente), lidas por
    `app.core.config.Configuracao` no mesmo padrão de `minio_endpoint`/`minio_access_key` (T11). **Você
    não preenche essas variáveis com nada — elas ficam ausentes**, porque não há certificado real.
  - **Testes automatizados do módulo de assinatura usam um certificado autoassinado gerado NA PRÓPRIA
    FIXTURE de teste** (`cryptography.x509`, biblioteca já é dependência de `apps/api`, usada por F2
    para o vetor AES-256-GCM da biometria) — isto prova que o código de assinatura produz CMS/PKCS#7
    válido e que o fluxo completo (assinar → gravar `arquivo_assinaturas` → cofre → download) funciona,
    **sem** fingir que é um certificado ICP-Brasil. Rotule esse certificado de teste como tal em todo
    lugar (nome do titular no certificado de teste, docstring do módulo, nome do arquivo de fixture) —
    nunca o apresente como se fosse real.
  - **Trocar para o certificado real da SEEG quando ele existir é só apontar as duas variáveis de
    ambiente para o arquivo/senha reais** — nenhuma linha de código muda, mesmo padrão de "substituição
    sem RFC" que F10 §2.8 já fixou para push/e-mail e que RFC-012 já fixou para o HMAC offline de F5.

### 2.5 Achado crítico: `marcacoes.crc16`/`hash_anterior`/`hash_registro`/`linha_afd` NÃO são o leiaute — apesar do que os comentários dizem

Isto é o achado mais importante desta fase fora do que a T0 já documentou, e não está em
`docs/leiaute-afd-aej.md` porque só aparece lendo o código real de F5
(`apps/api/app/marcacao/dominio/nsr.py`, `registro.py`). **Leia com atenção, porque é o erro mais fácil
de cometer nesta fase.**

`marcacoes` já tem, desde F5, as colunas `crc16`, `hash_anterior`, `hash_registro` e `linha_afd`,
calculadas e congeladas na gravação de cada marcação. À primeira vista parece que o AFD já está pronto e
A1 só precisaria concatenar essas colunas. **Isso está errado, e o próprio código de F5 avisa disso
explicitamente**, mesmo que o comentário do `schema.sql` (linha 1980, "CRC-16 do registro **conforme o
leiaute do AFD**") e o do `glossario.md` (linha 153, "calculado por registro **conforme o leiaute do
AFD**") leiam como se já fosse leiaute oficial:

- **`crc16` usa o algoritmo errado.** `apps/api/app/marcacao/dominio/nsr.py::crc16()` implementa
  **CRC-16/ARC** (polinômio reverso `0xA001`, equivalente ao normal `0x8005`) — a docstring da própria
  função diz *"Documentado aqui, não certificado: a conformidade byte a byte com o validador oficial do
  leiaute do AFD é conferida pela F12."* O leiaute real exige **CRC-16/CCITT-TRUE (KERMIT)**, polinômio
  `0x1021` (confirmado pelo vetor de teste oficial `"123456789"` → `0x2189`,
  `docs/leiaute-afd-aej.md` §8.1). São dois algoritmos de CRC-16 diferentes — produzem valores
  diferentes para a mesma entrada.
- **`hash_registro`/`hash_anterior` usam uma fórmula diferente da do ADR-012.** A canonicalização de F5
  (`canonicalizar_registro`) concatena **7 campos** (`tenant_id`, `rep_p_id`, `nsr`, `cpf`,
  `tipo_registro`, `canal`, `datahora_marcacao`) com o separador ASCII "Unit Separator" (`0x1F`) entre
  eles — a fórmula do ADR-012 (§2.3 acima) concatena **8 insumos diferentes** (incluindo data/hora de
  **gravação**, identificador do **coletor**, indicador **on-line/off-line** — nenhum dos quais entra na
  fórmula de F5 — e **sem** `tenant_id`/`rep_p_id`, que não são insumos do leiaute) **sem separador**
  algum. São cadeias de hash **independentes**, com propósitos diferentes: a de F5 detecta
  adulteração/remoção silenciosa na própria tabela `marcacoes` (é o que
  `app.marcacao.dominio.verificacao_nsr::verificar_sequencia_nsr` verifica); a do ADR-012 é o campo nº 8
  do registro tipo "7" do AFD, exigido pela Portaria.
- **`linha_afd` é deliberadamente simplificada, não o leiaute posicional.** A docstring de
  `montar_linha_afd()` diz literalmente: *"Linha simplificada e determinística — NÃO o leiaute legal
  final do AFD... que é implementado pela F12."* É um espaço-separado de 6 campos, nada a ver com a
  largura fixa por posição do tipo "7" real (137 caracteres, `docs/leiaute-afd-aej.md` §7).

**Decisão fixada por este PCF: A1 NUNCA lê ou reutiliza `marcacoes.crc16`, `hash_anterior`,
`hash_registro` ou `linha_afd` como valor de campo do AFD.** O gerador de AFD calcula, do zero, sobre os
mesmos dados-fonte (não sobre esses campos derivados):

| O que A1 REAPROVEITA de `marcacoes` (dado-fonte, correto) | O que A1 NUNCA reaproveita (derivado por F5, algoritmo/fórmula diferentes) |
|---|---|
| `nsr` (o NSR de verdade, sem lacunas, ver §2.6) | `crc16` (CRC-16/ARC, não CCITT-TRUE) |
| `cpf`, `datahora_marcacao`, `datahora_dispositivo`, `canal`, `coletada_offline`, `tipo_registro`, `rep_p_id` | `hash_anterior`/`hash_registro` (fórmula de 7 campos com separador `0x1F`, não a do ADR-012) |
| `criado_em` (como aproximação de "data/hora de gravação do registro", campo 5 do tipo "7" — ver nota abaixo) | `linha_afd` (linha simplificada de depuração, não posicional) |

Nota sobre "data/hora de gravação do registro" (campo nº 5 do tipo "7", distinto do campo nº 3 "data/hora
da marcação"): confirme lendo o schema real de `marcacoes` qual coluna representa exatamente esse
instante (candidatos: `criado_em` da tabela, ou um campo específico de gravação) antes de fixar — se
não houver uma coluna que represente isso com precisão, é achado de contrato (RFC), não invenção sua.

Esta distinção também resolve, de quebra, uma aparente contradição entre o ADR-012 (que diz "não há
exigência de hash de arquivo inteiro") e o contrato (`AfdArquivo.hashSha256`, `afd_arquivos.hash_sha256`,
que é `NOT NULL`... na verdade nullable, mas exigido pelo evento `afd.gerado`) — ver §2.6.

### 2.6 Dois hashes SHA-256 diferentes no mesmo arquivo — não confunda

Depois do achado de §2.5, fique atento a mais uma distinção sutil, desta vez dentro do próprio AFD:

1. **Hash por registro, tipo "7", encadeado (ADR-012).** É o que a Portaria exige, campo nº 8 de cada
   registro tipo "7" dentro do conteúdo do arquivo. Calculado por A1 conforme §2.3.
2. **`afd_arquivos.hash_sha256` / `AfdArquivo.hashSha256` / o `hashSha256` do evento `afd.gerado`.** É um
   **hash do arquivo gerado como um todo** — mas este é um campo do **contrato desta aplicação** (não
   da norma), usado como checksum de integridade de armazenamento/transmissão (o mesmo tipo de hash que
   qualquer sistema calcularia sobre um objeto salvo no MinIO, para detectar corrupção ou adulteração do
   arquivo depois de gerado). **Calcular este campo é trivial e sem ambiguidade** — é literalmente
   `SHA256(bytes do arquivo completo)` — e você **precisa** preenchê-lo, porque é `required` no payload
   do evento `afd.gerado`/`aej.gerado` (`events.yaml`).

Os comentários do contrato (`AfdArquivo.description` no `openapi.yaml`, `afd_arquivos.hash_sha256`
`COMMENT` no `schema.sql`) descrevem esse campo como **"exigido pelo leiaute"** — isso é impreciso à luz
da T0 (o leiaute não exige hash de arquivo inteiro, só o hash por registro do tipo "7") e é um dos itens
do achado de §2.7. **Você preenche o campo normalmente** (é fácil e não ambíguo de calcular), só não
documenta em lugar nenhum do seu código que esse hash de arquivo é "o hash exigido pela Portaria" — ele
não é; é hash de integridade de armazenamento, decisão de engenharia deste produto, não da norma.

### 2.7 Achados de contrato: a premissa antiga ("`|`, CRC-16 por registro, SHA-256 do arquivo") ainda está escrita em 5 lugares

A correção de premissa da T0 (§2.2) chegou a `FASES-E-AGENTES.md` linha 320, mas **não** chegou aos
seguintes textos, todos ainda descrevendo o AFD com a premissa antiga e incorreta. Nenhum deles impede
você de trabalhar (são só **texto descritivo**, nenhum deles muda tipo de campo, obrigatoriedade ou
formato de dado no schema JSON/SQL) — mas um agente que confiasse neles em vez de em
`docs/leiaute-afd-aej.md` implementaria o AFD errado. **A fonte da verdade é sempre
`docs/leiaute-afd-aej.md`, nunca a prosa abaixo:**

1. `packages/contracts/openapi.yaml`, descrição da operação `gerarAfd` (linha ~14571): *"O arquivo sai em
   texto ASCII ISO-8859-1, campos separados por barra vertical, ... CRC-16 por registro e SHA-256 do
   arquivo."*
2. `packages/contracts/openapi.yaml`, `description` do schema `AfdArquivo` (linha ~34662): *"...campos
   separados por barra vertical, ... CRC-16 por registro e SHA-256 do arquivo."*
3. `packages/contracts/schema.sql`, `COMMENT ON TABLE afd_arquivos` (linha ~3246): mesma frase.
4. `packages/contracts/schema.sql`, `COMMENT ON COLUMN marcacoes.crc16`/`glossario.md` (linhas 1980 e
   153 respectivamente): "conforme o leiaute do AFD" — impreciso pelo motivo do §2.5.
5. `apps/worker/worker/tarefas/fiscal.py`, docstring do módulo (linha ~7): mesma frase da premissa
   antiga, herdada do texto original de `FASES-E-AGENTES.md`.

**Decisão fixada:** você não corrige esses textos por conta própria (são `packages/contracts/**`, exceto
o item 5 que é `apps/worker`, fora do ownership desta fase de qualquer forma — ver §5). Registre uma
entrada em `docs/backlog.md` apontando os cinco locais e citando este PCF/`docs/leiaute-afd-aej.md` como
fonte da correção, para o orquestrador decidir se vale uma RFC de limpeza cosmética (a régua de
`docs/rfc/README.md` é ambígua aqui — toca `packages/contracts/` literalmente, mas é só prosa
desatualizada, o tipo de achado que o próprio README classifica como backlog). **Não é bloqueante para
você codificar** — só não implemente o que essa prosa descreve.

Também note, sem que isso seja bloqueio: o exemplo de nome de arquivo do evento `afd.gerado`
(`AFD_60258502000149_20260701_20260731.txt`) não bate literalmente com a regra 10 da seção 6 de
`docs/leiaute-afd-aej.md` (que não menciona datas de período no nome, e inclui o número do INPI). A
decisão de nome de arquivo está fixada em §2.10 abaixo, reconciliando os dois.

### 2.8 NSR: o que é reaproveitado e o que nunca é gerado de novo

[`docs/adr/ADR-003-geração-nsr-sequencial-sem-lacunas.md`](../adr/ADR-003-geracao-nsr-sequencial-sem-lacunas.md)
já decidiu como o NSR é alocado (contador transacional com bloqueio de linha, `nsr_sequencias`, sem
`SEQUENCE` do PostgreSQL) e é **fase afetada: "F12 (consome no AFD)"** — a ADR já antecipa exatamente o
seu papel. Confirmado, campo a campo, contra `docs/leiaute-afd-aej.md` §12: é **o mesmo conceito** de
NSR — sequencial por REP-P (que na prática corresponde a "por estabelecimento", já que cada empresa
normalmente opera um único REP-P; `rep_ps.identificador` existe justamente para o caso raro de mais de
um), começando em 1, sem lacuna, sem reuso, nunca reiniciado. **Não há diferença a documentar aqui além
da que §2.5 já cobriu** (o CRC-16/hash que acompanham o NSR na tabela `marcacoes` não são o leiaute; o
NSR em si é).

Regras que decorrem disto:

- **A1 nunca aloca um NSR novo.** O gerador de AFD lê `marcacoes.nsr` (via `nsr_emissoes`, que garante
  unicidade global do par `(tenant_id, rep_p_id, nsr)` entre partições — `packages/contracts/glossario.md`
  §3.1) e nunca chama `alocar_nsr`/insere em `nsr_sequencias`.
- **A1 reaproveita `app.marcacao.dominio.verificacao_nsr::verificar_sequencia_nsr`** (F5, T4, já
  implementado e testado) para a verificação prévia de continuidade exigida antes de gerar (ver a
  descrição de `gerarAfd`: *"Antes de escrever qualquer byte, a continuidade da sequência de NSR é
  verificada. Havendo lacuna, o arquivo NÃO é gerado..."*). Chame com `verificar_cadeia_hash=False` —
  você só precisa da checagem de lacuna numérica (`integro`/`lacunas`), não da cadeia de hash interna de
  F5 (que não é o leiaute, §2.5, e não tem relação com o hash do ADR-012). **Não reimplemente a detecção
  de lacuna** — é o mesmo algoritmo (`_detectar_lacunas`) que F5 já escreveu e testou.
- **Ordenação: o AFD ordena por NSR, não por data/hora.** ADR-003, consequência (d), fixa que
  "relatório e espelho" ordenam por data/hora da marcação (porque o NSR não é cronológico — uma
  marcação offline registrada hoje pode ter data/hora de ontem). **O AFD é a exceção deliberada**: a
  regra 3 do leiaute (`docs/leiaute-afd-aej.md` §6) exige "registros ordenados pelo NSR", e é assim que
  A1 deve montar o arquivo — não copie o padrão de ordenação por data/hora que F10/F11 usam para
  espelho/relatório.
- **`canal='importacao'`** identifica marcação vinda de AFD de terceiro (fabricante concorrente,
  namespace de NSR separado — `packages/contracts/glossario.md`, comentário da coluna
  `marcacoes.canal`, e ADR-003 item 6). **A1 exclui explicitamente `canal='importacao'` da consulta que
  alimenta o AFD** — mesmo que hoje (antes de F13 implementar o importador) provavelmente não existam
  linhas com esse canal, a exclusão é defesa em profundidade, documentada, não um filtro adivinhado.

### 2.9 Módulo de fronteira A1/A2 — o que é compartilhado, o que não é

O PCF precisa decidir isto agora, não deixar cada agente descobrir sozinho (mesmo espírito do "T1-first"
que F10 usou para `materializar_ferias_ou_folga`). Avaliados os três candidatos que a T0/o planejamento
levantaram:

| Candidato | Compartilhado entre A1/A2? | Por quê |
|---|---|---|
| **Formatação de data/hora `AAAA-MM-ddThh:mm:00ZZZZZ`** | **Sim.** `app/fiscal/comum/formatos.py::formatar_data_hora` | O formato é **idêntico** nos dois arquivos (`docs/leiaute-afd-aej.md` §6 regra 6 e §9 regra 5) — mesma string, mesma exigência de segundos fixados em `"00"`, mesmo formato de fuso. Duplicar essa função em dois módulos é o tipo exato de risco que o "T1-first" evita: se um lado corrigir um bug de formatação e o outro não, os dois arquivos divergem silenciosamente. |
| **Formatação de data `AAAA-MM-dd`** | **Sim.** Mesmo módulo, `formatar_data` | Mesmo motivo — formato idêntico nos dois leiautes. |
| **Montagem de arquivo texto (junta linhas com CR+LF, codifica ISO-8859-1)** | **Sim.** Mesmo módulo, `montar_arquivo_texto(linhas: list[str]) -> bytes` | Regra 2 de ambos os leiautes (`docs/leiaute-afd-aej.md` §6/§9) é idêntica: terminador CR+LF, sem linha em branco, ISO 8859-1. A única diferença entre AFD e AEJ está **dentro** de cada linha (largura fixa vs. delimitado por `\|`), não na montagem do arquivo. |
| **CRC-16 CCITT-TRUE/KERMIT** | **Não — exclusivo de A1.** `app/fiscal/afd/crc16.py` | Confirmado lendo `docs/leiaute-afd-aej.md` §9/§10 por inteiro: o AEJ **não menciona CRC-16 em lugar nenhum**. A regra 8 do AFD (seção 6) limita o CRC-16 aos tipos "1" a "5" do **AFD**; não há equivalente no AEJ. Compartilhar esse módulo criaria um acoplamento falso — A2 nunca chama essa função. |
| **Formatação de campo de largura fixa (padding N/A)** | **Não — exclusivo de A1.** `app/fiscal/afd/registros.py` | O AEJ usa campos delimitados por `\|` com faixas de tamanho (`1 a 150`), não largura fixa posicional — não existe "padding" a decidir no AEJ da mesma forma. Compartilhar não faria sentido estrutural. |

`app/fiscal/comum/` é criado por **A1** na T1 (primeira tarefa de código da fase, mesmo padrão que F10
usou para `app/workflow/__init__.py`); A2 **importa e usa**, nunca edita.

**Duas decisões dentro do módulo comum, fixadas para não virar escolha de cada agente:**

- **Padding de campo N no AFD** (Lacuna nº 2 de `docs/leiaute-afd-aej.md` §1/§15): implemente os
  **dois modos** atrás de uma constante isolada e nomeada em `app/fiscal/afd/registros.py`
  (`MODO_PREENCHIMENTO_NUMERICO: Literal["zero_esquerda", "espaco_direita"] = "zero_esquerda"`) — o
  padrão ativo é zero à esquerda / alinhado à direita (prática de mercado herdada da Portaria
  1.510/2009, e a única leitura que preserva a ordenação lexicográfica correta por NSR exigida pela
  regra 4 do leiaute). Campos `A` (alfanumérico) são sempre espaço à direita / alinhado à esquerda —
  não há ambiguidade aí. **Documente a constante e o motivo no módulo**, exatamente como
  `docs/leiaute-afd-aej.md` §15 recomenda, para trocar rápido se um AFD de referência provar o
  contrário.
- **`montar_arquivo_texto` levanta erro claro, não mangling silencioso**, se algum caractere do
  conteúdo não for representável em ISO-8859-1 (ex.: um caractere Unicode fora do Latin-1 em razão
  social/nome) — isto não é uma preocupação teórica: nomes de pessoas em português usam só Latin-1, mas
  não presuma, verifique. Não é um código de erro novo da API (é um `AssertionError`/exceção interna que
  vira `PONTO-FISC-006` — "falha na geração do arquivo fiscal" — se acontecer durante a geração, código
  já existente no catálogo).

### 2.10 Nome de arquivo — decisão fixada (reconcilia a norma com o exemplo do contrato)

`docs/leiaute-afd-aej.md` §6 regra 10 (leitura literal do leiaute oficial) diz que o nome do AFD do
REP-P é a junção de `"AFD"` + número de registro no INPI + CNPJ do empregador + `"REP_P"`, **sem
especificar o separador exato** (NÃO CONFIRMADO). O exemplo do evento `afd.gerado` em `events.yaml`
(`AFD_60258502000149_20260701_20260731.txt`) usa um formato diferente: `AFD_<CNPJ>_<períodoInício>_
<períodoFim>.txt`, sem o número do INPI e sem o sufixo `REP_P`. **Decisão fixada, combinando as duas
fontes em vez de escolher uma e descartar a outra:**

```
AFD_<numeroInpi>_<cnpjEmpregador>_REP_P_<periodoInicio:AAAAMMDD>_<periodoFim:AAAAMMDD>.txt
```

satisfaz literalmente os três componentes exigidos pela norma (INPI, CNPJ, `REP_P`), na ordem que a
norma pede, com `_` como separador (mesma convenção do exemplo do contrato), e acrescenta as datas de
período como sufixo legível — a norma não proíbe conteúdo adicional no nome, só exige que os três
componentes estejam presentes. Quando fracionado, acrescente `_PARTE<N>DE<TOTAL>` antes da extensão.
**AEJ**: nenhuma regra de nome foi encontrada no leiaute oficial do AEJ pela T0 (`docs/leiaute-afd-aej.md`
§13, lacuna nº 5) — siga o exemplo do contrato diretamente, sem reconciliação necessária:
`AEJ_<cnpjEmpregador>_<periodoInicio:AAAAMMDD>_<periodoFim:AAAAMMDD>.txt`.

Registre em `docs/backlog.md` que o exemplo de `events.yaml` poderia ser atualizado para incluir o INPI
(cosmético, não bloqueante).

### 2.11 Fracionamento — o contrato já decidiu o critério, mesmo a norma não tendo decidido

`docs/leiaute-afd-aej.md` §1 lacuna nº 4/§13 confirma que a norma permite fracionar o AFD do REP-P mas
**não especifica o critério de corte** (por período? por tamanho?). Você não precisa resolver essa
lacuna da norma: **o contrato já escolheu um critério concreto** —
`AfdCriar.tamanhoFracaoRegistros` (registros por fração) — e você só implementa o que o schema já pede:
gerar o conjunto completo de registros do período pedido, então dividir em fatias de
`tamanhoFracaoRegistros` registros cada, gravando **uma linha de `afd_arquivos` por fração** (cada uma
com seu próprio `nsrInicial`/`nsrFinal`/`totalRegistros`/`hashSha256`/`fracaoNumero`/`fracaoTotal`,
cabeçalho tipo "1" e trailer tipo "9" próprios — cada fração é um AFD **completo e válido por si só**,
não um fragmento que precisa ser concatenado com outro para fazer sentido). **`AejCriar` não tem campo
de fracionamento** (confirme lendo o schema — não existe) — decisão fixada: **A2 não implementa
fracionamento de AEJ nesta fase**; se isso se provar necessário na prática, é achado de contrato
(`docs/backlog.md`), não uma feature que você adiciona por conta própria.

### 2.12 Fronteira com F11 — provavelmente ainda não escrita quando você começar

Verifique `docs/fases/F11-relatorios-espelho-exportacoes.md` — no momento em que este PCF foi escrito,
**o arquivo não existia ainda** (F11 pode estar sendo planejada em paralelo por outro agente). Se ele já
existir quando você começar, leia rapidamente as seções 1 e 4 (Objetivo, Contratos) só para confirmar que
não há sobreposição de ownership com esta fase — não deveria haver, porque a fronteira é conceitual e
estável: **F11 é sobre relatórios operacionais/gerenciais genéricos e exportação em massa (CSV/XLSX/PDF,
"os 24 relatórios do catálogo"); F12 é sobre conformidade legal específica do REP-P (AFD, AEJ,
assinatura CAdES)**. Nenhuma das duas fases gera a saída da outra. Se `F11-*.md` já existir e você
enxergar uma sobreposição real de arquivo/tabela, é achado de planejamento — pare e reporte ao
orquestrador, não resolva sozinho escolhendo quem "ganha" o arquivo.

### 2.13 Fronteira com F4 — reaproveitar, nunca duplicar

`tipos_tratamento.afeta_afd` tem `CHECK (afeta_afd = FALSE)` (`schema.sql` linha 2377) — **garantido
pelo banco, não configurável**: nenhum tratamento, de nenhum tipo, jamais entra no AFD. Isto já impõe
estruturalmente a regra "AFD deriva exclusivamente das marcações" — você não precisa filtrar tratamento
fora do AFD por lógica de aplicação, é impossível por construção. O AEJ é o oposto: **é** quem enxerga
tratamento, e para isso A2 **lê** (nunca recalcula) as tabelas/módulos que F4 já produziu:

- `apuracoes_dia`, `apuracao_componentes` — resultado já calculado do motor de apuração, para o bloco de
  ausências e o cruzamento com horário contratual.
- `bh_contas`, `bh_lancamentos` — extrato real de banco de horas, para o bloco tipo "07" do AEJ. O
  critério de aceite "AEJ contém banco de horas coerente com o extrato" (§7) significa: os totais que o
  AEJ exporta batem, linha a linha ou pelo menos em soma, com o que `app.apuracao.banco_horas.consulta`
  já devolveria para o mesmo vínculo/período — leia o módulo real (F4, só leitura) em vez de somar
  `bh_lancamentos` por conta própria com uma query paralela.
- `tratamentos` (via os módulos de leitura de F4, não `SELECT` direto se um módulo de consulta já
  existir) — para identificar lançamentos manuais no bloco de marcações/ausências do AEJ.
- `afastamentos`/`tipos_afastamento` (F3, já lido por F10) — para o bloco de ausências.

**Você não escreve em nenhuma dessas tabelas.** Se o formato de consulta que F4 expõe não bastar para o
que o AEJ precisa, é achado de contrato/RFC — não é escrita direta em tabela de outra fase.

### 2.14 Fronteira com F10 — duas assinaturas diferentes, mesma distinção que F10 §2.4 já fez do outro lado

F10 já documentou (§2.4 do próprio PCF de F10) que a assinatura do **espelho de ponto** (aceite
eletrônico do colaborador, `assinaturas_espelho`) e a assinatura **CAdES do AFD/AEJ** (fabricante/
desenvolvedor ou empregador, `arquivo_assinaturas`) são mecanismos **completamente diferentes**: métodos
diferentes (`aceite_eletronico` vs. certificado ICP-Brasil real), tabelas diferentes, e propósitos
diferentes (prova de ciência do colaborador vs. prova de autoria do arquivo fiscal perante o MTE). Esta
fase é dona da segunda. **Você não toca em `assinaturas_espelho`, `espelhos`, `fechamentos` nem em
nenhum router de F10.** Se precisar saber se um período está fechado antes de gerar o AFD/AEJ (não é um
requisito confirmado em lugar nenhum do contrato — confirme se realmente precisa antes de inventar essa
dependência), é leitura read-only de `fechamentos`/`periodos`, nunca escrita.

## 3. Leituras obrigatórias (lista fechada)

Leia isto e pare. Não leia código de F1/F2/F3/F6/F8/F9a/F9b além dos módulos explicitamente listados.

- **`docs/leiaute-afd-aej.md`, inteiro, antes de qualquer código.** Não é opcional, não é "ler por
  cima" — é a fonte de verdade de todo campo, posição, tamanho, tipo e algoritmo desta fase.
- **`docs/adr/ADR-012-formula-hash-registro-tipo-7-afd-nao-confirmada.md`**, inteiro — a decisão do §2.3
  já incorporada.
- **`docs/adr/ADR-003-geracao-nsr-sequencial-sem-lacunas.md`**, inteiro — o §2.8 já resume o que importa,
  mas leia a ADR completa para o raciocínio das alternativas descartadas.
- `FASES-E-AGENTES.md`, linhas ~315–327 (seção "F12 — Conformidade REP-P") — o escopo oficial dos 3
  agentes, já corrigido.
- `packages/contracts/openapi.yaml` — **apenas** a tag `fiscal` (7 caminhos: `/v1/fiscal/afd`,
  `/v1/fiscal/afd/{arquivoId}`, `/v1/fiscal/afd/{arquivoId}/download`, `/v1/fiscal/aej`,
  `/v1/fiscal/aej/{arquivoId}`, `/v1/fiscal/arquivos/{arquivoId}/assinar`, `/v1/fiscal/rep-ps`; 10
  operações: `gerarAfd`, `listarAfd`, `obterAfd`, `baixarAfd`, `gerarAej`, `listarAej`, `obterAej`,
  `assinarArquivoFiscal`, `listarRepPs`, `criarRepP`). Leia também, em `components/schemas`: `RepP`,
  `RepPCriar`, `AfdCriar`, `AfdArquivo`, `ListaAfdArquivo`, `AejCriar`, `AejArquivo`, `ListaAejArquivo`,
  `AssinaturaArquivoRequisicao`, `ArquivoAssinatura`, `ListaRepP`, `ProcessamentoAssincrono`. Note quais
  operações **não** existem — não invente `atualizarAfd`, `excluirAfd`, `atualizarRepP`,
  `regerarAfd` (é sempre `gerarAfd` de novo, um novo `arquivoId`), `PATCH`/`DELETE` em qualquer caminho
  de `fiscal`. Leia também as descrições longas dos textos-guia (`info.description`, tag `marcacoes`,
  tag `fiscal`, tag `afastamentos`) — mas lembre-se de que a prosa ali repete a premissa antiga em
  alguns pontos (§2.7), então **onde a prosa do `openapi.yaml` divergir de `docs/leiaute-afd-aej.md`,
  vence o segundo**.
- `packages/contracts/schema.sql` — seção **13 (ARQUIVOS FISCAIS)** por inteiro (`afd_arquivos`,
  `aej_arquivos`, `arquivo_assinaturas`); seção **8 (MARCAÇÃO)**, apenas `rep_ps`, `nsr_sequencias`
  (você não cria nem altera estas tabelas — só as consulta e escreve conforme o CRUD que o contrato já
  define), `marcacoes` (colunas `nsr`, `cpf`, `datahora_marcacao`, `datahora_dispositivo`, `canal`,
  `coletada_offline`, `tipo_registro`, `rep_p_id`, `criado_em` — leitura, nunca escrita) e
  `nsr_emissoes` (leitura); seção **5 (PESSOAS)**, apenas `vinculos.matricula_esocial`; seção **7
  (JORNADA, ESCALA E CALENDÁRIO)**, apenas `tipos_afastamento.codigo_esocial`, `afastamentos` (leitura),
  e `jornadas` (leitura, para o horário contratual do AEJ tipo "04"); seção **9 (TRATAMENTO E
  APURAÇÃO)**, apenas `tipos_tratamento.afeta_afd`, `tratamentos`, `apuracoes_dia` (leitura); seção
  **10 (BANCO DE HORAS)**, apenas `bh_contas`, `bh_lancamentos` (leitura, para o AEJ de A2); seção
  **12 (FECHAMENTO E ESPELHO)**, apenas `periodos` (leitura, `aej_arquivos.periodo_id` referencia esta
  tabela).
- `packages/contracts/models/fiscal.py` — `AfdArquivo`, `AejArquivo`, `ArquivoAssinatura` (SQLAlchemy).
  `packages/contracts/models/marcacao.py`, apenas `RepP`, `NsrEmissao` e a `Marcacao` (leitura de
  colunas). Confirme o nome exato de cada arquivo lendo o diretório, não adivinhe.
- `packages/contracts/errors.yaml` — categoria **FISC** (todos os 7 códigos: 001 lacuna de NSR, 002
  geração em andamento, 003 sem número INPI, 004 certificado indisponível, 005 certificado expirado/
  revogado, 006 falha de geração, **007 é do F10** — `assinarEspelho`, não desta fase, confirme lendo o
  `x-erros` de onde aparece antes de presumir que é sua). Leia também **CONF** (001, 003), **VAL** (001,
  003, 005, 006, 007, 011), **REC** (001, 002), e os transversais **AUTH**, **PERM**, **TEN**, **IDEM**,
  **RATE**, **INT**, **MARC-010**. Você **não cria código de erro novo** — os 7 `FISC` já cobrem tudo
  que a fase precisa.
- `packages/contracts/events.yaml` — os eventos `afd.gerado`, `aej.gerado`. Leia também `espelho.
  assinado` **só para não confundir com a assinatura desta fase** (§2.14) — você nunca publica esse
  evento.
- `packages/contracts/glossario.md` — verbetes **AFD**, **AEJ**, **NSR**, **REP-P**, **PTRP**, **CRC-16**,
  **Hash chain**, **eSocial** (matrícula), seção 1.1 (RLS), 1.2 (Imutabilidade), 3.1 (unicidade global
  de `nsr_emissoes`), 6 (termos proibidos).
- `apps/api/app/marcacao/dominio/nsr.py`, `registro.py`, `verificacao_nsr.py` — leia os três por inteiro,
  **só leitura, não edite** (ownership congelado de F5). É a base do achado de §2.5 e o módulo que A1
  reaproveita (`verificar_sequencia_nsr`) em §2.8.
- `apps/api/app/apuracao/banco_horas/consulta.py`, `lancamentos.py` (F4, só leitura) — para o extrato que
  o bloco de banco de horas do AEJ precisa bater. `apps/api/app/apuracao/tratamento/servico.py` (F4, só
  leitura, para saber como um tratamento aprovado fica identificável na apuração).
- `apps/api/app/comum/armazenamento.py` (F10, só leitura/reaproveitamento) — o cliente MinIO real, já
  implementado (`salvar_objeto`/`obter_url_assinada`). Você **não cria um segundo cliente de
  armazenamento de objetos**.
- `apps/worker/worker/tarefas/fiscal.py` — leia o arquivo inteiro. As assinaturas de `gerar_afd`/
  `gerar_aej` **já estão fixadas** (F0, scaffold) — você preenche o corpo, não muda a assinatura.
  `apps/worker/worker/filas.py` — leia por inteiro para confirmar que `FILA_FISCAL`, `FILA_POR_TAREFA`
  e `FASE_POR_TAREFA` já apontam `gerar_afd`/`gerar_aej` para `"F12"` — **nenhuma edição necessária
  nestes dois arquivos**, ao contrário do que F10 precisou fazer para suas próprias tarefas novas.
- `apps/api/app/routers/fiscal.py` — o *stub* gerado pela Fase 0 (hoje responde `501` com
  `PONTO-INT-005`). Leia como exemplo de assinatura de handler — não regere este arquivo à mão, e
  **nunca rode `python tools/gerar_do_contrato.py`** depois de começar a implementar (esse script
  **sobrescreve todos os routers já implementados de volta a stub**, inclusive os de F1–F11 — é
  destrutivo para o repositório inteiro, não só para esta fase; ver §9).
- `apps/api/app/routers/tratamentos.py`, `apps/api/app/workflow/fechamento/servico.py` (F10) — exemplos
  **vivos** de handler que enfileira tarefa assíncrona e devolve `ProcessamentoAssincrono`, para copiar
  o padrão (`criarFechamento`/`gerarEspelhos` fazem exatamente o mesmo tipo de "valida síncrono, depois
  enfileira" que `gerarAfd`/`gerarAej` precisam).
- `apps/api/app/schemas/contrato.py` (gerado) — apenas para confirmar que os modelos Pydantic já
  existem (`RepP`, `RepPCriar`, `AfdCriar`, `AfdArquivo`, `AejCriar`, `AejArquivo`,
  `AssinaturaArquivoRequisicao`, `ArquivoAssinatura`, `ProcessamentoAssincrono`) — **não edite**, é
  gerado.
- `apps/api/pyproject.toml` — confirme as dependências já disponíveis (`cryptography>=43.0`, `minio>=7.2`)
  antes de propor uma nova. `infra/.env.example` — bloco 6 (MinIO), para o padrão de variável de
  ambiente que o bloco novo de certificado (§2.4) deve seguir.
- `docs/rfc/README.md` e `docs/backlog.md` — protocolo de RFC e onde anotar achados. Releia
  **RFC-012** (fila offline sem contrato de chave simétrica — cita F12 como fase impactada; leia a
  decisão do orquestrador: é sobre o HMAC/AES-GCM da fila offline de F5/F6, **não afeta a geração de
  AFD/AEJ**, que lê `marcacoes` já persistidas independente de como a marcação chegou — trate como nota
  de contexto, não como bloqueio) e **RFC-003** (identidade visual — cita F12 tangencialmente por causa
  do cabeçalho do espelho, que é ownership de F10/F11, não desta fase; **F12 não toca `apps/web` nem gera
  PDF com identidade visual**, então RFC-003 não impõe trabalho novo aqui).
- `docs/fases/F10-workflows-aprovacoes-fechamento.md` — como **referência de formato** (a estrutura de 9
  seções que este PCF segue) e §2.4/§2.5/§2.8 como precedente direto de padrão de assinatura eletrônica,
  MinIO e adaptador provisório.

## 4. Contratos

**Consome** — já existe, esta fase apenas usa:

- Tabelas `rep_ps`, `nsr_sequencias` (F0/F5) — leitura para `criarRepP`/`listarRepPs` (você faz o CRUD
  que o contrato já define sobre `rep_ps`; `nsr_sequencias` é só leitura, nunca escrita — a única escrita
  nela é `alocar_nsr`/`fechar_nsr` de F5).
- Tabela `marcacoes` (F5) — leitura das colunas listadas em §2.5/§3. **Nunca** escrita.
- Tabela `nsr_emissoes` (F5) — leitura, para a faixa de NSR sem lacuna.
- Módulo `app.marcacao.dominio.verificacao_nsr.verificar_sequencia_nsr` (F5) — função real, reaproveitada
  integralmente por A1 (§2.8).
- Tabelas `tipos_tratamento`, `tratamentos`, `apuracoes_dia`, `apuracao_componentes`, `bh_contas`,
  `bh_lancamentos` (F4) — leitura, para o AEJ de A2. Módulos de consulta de
  `app.apuracao.banco_horas.*` (F4) — leitura, reaproveitados por A2 em vez de query paralela.
- Tabelas `afastamentos`, `tipos_afastamento`, `vinculos` (`matricula_esocial`) (F2/F3) — leitura, para
  o AEJ.
- Tabelas `periodos` (F10) — leitura, só para `aej_arquivos.periodo_id` quando informado.
- Módulo `app.comum.armazenamento` (F10) — `salvar_objeto`/`obter_url_assinada`, reaproveitado
  integralmente por A1 (AFD), A2 (AEJ) e A3 (`.p7s`).
- Andaime da API (`app/core/erros.py`, `app/core/catalogo_erros.py`, `app/core/contexto.py`, `app/
  core/seguranca.py`, `app/db/sessao.py`, `app/core/config.py`), modelos Pydantic gerados em `app/
  schemas/contrato.py`, modelos SQLAlchemy do pacote `ponto_contracts`.
- `apps/worker/worker/tarefas/fiscal.py` — assinaturas de `gerar_afd`/`gerar_aej` **já fixadas** pelo
  scaffold da Fase 0; você preenche o corpo, nunca muda parâmetro, nome ou tipo de retorno sem RFC.
  `apps/worker/worker/filas.py::FILA_FISCAL`/`FILA_POR_TAREFA`/`FASE_POR_TAREFA` — já apontam para esta
  fase, nenhuma edição necessária.
- `apps/api/app/routers/__init__.py` — já registra o roteador `fiscal` na ordem correta. Você não toca
  neste arquivo.

**Produz** — esta fase implementa:

*Endpoints (10 operações; hoje `501`):*

| Tag | Operações | Agente |
|---|---|---|
| `fiscal`/AFD (4) | `gerarAfd`, `listarAfd`, `obterAfd`, `baixarAfd` | A1 gera; **A3** implementa listagem/obtenção/download (cofre — ver tabela de agentes no cabeçalho e ownership §5) |
| `fiscal`/REP-P (2) | `listarRepPs`, `criarRepP` | A1 |
| `fiscal`/AEJ (3) | `gerarAej`, `listarAej`, `obterAej` | A2 gera; **A3** implementa listagem/obtenção |
| `fiscal`/assinatura (1) | `assinarArquivoFiscal` | A3 |

*Tabelas escritas:* `rep_ps` (CRUD via `criarRepP`, sem `UPDATE`/`DELETE` no contrato — só criação e
listagem), `afd_arquivos`, `aej_arquivos`, `arquivo_assinaturas`. Leitura em todo o resto listado acima
em "Consome". **Nunca** escrita em `marcacoes`, `nsr_sequencias`, `apuracoes_dia`,
`apuracao_componentes`, `bh_lancamentos`, `bh_contas`, `tratamentos`, `afastamentos`, `periodos`,
`fechamentos`, `espelhos`, `assinaturas_espelho`.

*Módulos internos publicados para outras fases (assinatura fixada por este PCF):*

- `app.fiscal.comum.formatos.formatar_data(d: date) -> str`,
  `formatar_data_hora(dt: datetime) -> str`, `montar_arquivo_texto(linhas: list[str]) -> bytes` — módulo
  de A1 (T1), importado por A2. Nenhuma fase futura precisa dele diretamente hoje, mas fica disponível
  pelo mesmo motivo que qualquer módulo comum fica.
- `app.fiscal.afd.crc16.crc16_ccitt(dados: bytes) -> int` — A1, T2.
- `app.fiscal.afd.hash_tipo7.calcular_hash_tipo7(insumos: InsumosHashTipo7, hash_anterior: str | None) -> str`
  (ou assinatura equivalente que A1 documente) — A1, T3, a fórmula do ADR-012 isolada.
- `app.fiscal.assinatura.cades.assinar_cades(conteudo: bytes, certificado: CertificadoConfig) -> bytes` e
  `validar_cades(conteudo: bytes, assinatura: bytes) -> ResultadoValidacao` — A3, T11, chamado tanto por
  `assinarArquivoFiscal` quanto pelos corpos de `gerar_afd`/`gerar_aej` quando `assinar=true` e há
  certificado configurado. **Assinatura fixada por este PCF** — se mudar, atualize todos os usos no
  mesmo commit.

*Eventos publicados:* `afd.gerado` (ao final de `gerar_afd`, quando `status` passa a `gerado`),
`aej.gerado` (idem, `gerar_aej`). Nenhum outro evento nasce nesta fase — em particular, **não existe**
`rep_p.criado`/`arquivo_assinado` em `events.yaml`; não invente.

**Não toca** — é de outra fase, mesmo que pareça relacionado:

- **Marcação, NSR, CRC-16/hash internos de F5** — só leitura, nunca escrita, nunca um segundo mecanismo
  de alocação (§2.5, §2.8).
- **Cálculo, apuração, banco de horas, tratamento** — F4, só leitura (§2.13).
- **Fechamento, espelho, assinatura do colaborador** — F10, só leitura eventual de `periodos`, nunca
  escrita, nunca confundida com a assinatura CAdES desta fase (§2.14).
- **Relatórios, exportação em massa, PDF "de designer"** — F11 (§2.12).
- **Webhooks, entrega HTTP a terceiros** — F13. Os eventos `afd.gerado`/`aej.gerado` já estão marcados
  `webhook_publico: true` em `events.yaml`; você só publica no barramento interno do seu próprio módulo
  (mesmo padrão `BARRAMENTO_INTERNO` que F2–F5/F10 já usam), nunca implementa entrega HTTP real.
- **Importador de AFD de terceiros, namespace de NSR separado** — F13 (tag `integracoes`). Você só
  **exclui** `canal='importacao'` da sua consulta (§2.8); não implementa o importador em si.
- **eSocial (S-2230 e demais eventos), envio para o governo** — fora do escopo de todo o projeto por
  enquanto (`PROJETO.md` §10). Você só **exporta o campo `matricula_esocial`/`codigo_esocial`** que já
  existe no schema; não integra com o eSocial.
- `packages/contracts/**` — **congelado**, sem exceção nesta fase (ao contrário de F10, que teve uma
  função `SECURITY DEFINER` nova autorizada — aqui não há nenhuma). Qualquer necessidade de mudança é
  RFC.
- `apps/mobile`, `apps/device-gw`, `apps/facial-svc`, `apps/web`.

## 5. Ownership de arquivos

Caminhos **exclusivos** desta fase.

| Agente | Caminhos |
|---|---|
| **A1** (REP-P + gerador de AFD) | `apps/api/app/fiscal/__init__.py` (T1, único criador)<br>`apps/api/app/fiscal/comum/**` (T1, único criador — A2 importa, não edita)<br>`apps/api/app/fiscal/rep_p/**`<br>`apps/api/app/fiscal/afd/**`<br>`apps/api/tests/f12/conftest.py` (T1, único criador)<br>`apps/api/tests/f12/afd/**`<br>`apps/api/tests/f12/rep_p/**` |
| **A2** (gerador de AEJ) | `apps/api/app/fiscal/aej/**`<br>`apps/api/tests/f12/aej/**` |
| **A3** (assinatura + cofre) | `apps/api/app/fiscal/assinatura/**`<br>`apps/api/app/fiscal/cofre/**`<br>`apps/api/tests/f12/assinatura/**`<br>`apps/api/tests/f12/cofre/**` |

**Compartilhado dentro da fase** (exige combinação entre os agentes da fase):

| Caminho | Regra |
|---|---|
| `apps/api/app/routers/fiscal.py` | Um único arquivo, três blocos: **A1** implementa `gerarAfd`, `listarRepPs`, `criarRepP`; **A2** implementa `gerarAej`; **A3** implementa `listarAfd`, `obterAfd`, `baixarAfd`, `listarAej`, `obterAej`, `assinarArquivoFiscal`. Cada agente edita **só o corpo das funções da sua lista**, na ordem em que o arquivo gerado já as apresenta — não reordene nem remova a função de outro agente. Combine a ordem de commit entre os três antes de mexer (evite três commits que se sobrescrevem). |
| `apps/worker/worker/tarefas/fiscal.py` | Um único arquivo, dois blocos: **A1** preenche o corpo de `gerar_afd`; **A2** preenche o corpo de `gerar_aej`. As assinaturas das duas funções já estão fixadas pelo scaffold (§3/§4) — não mude parâmetro, nome ou tipo de retorno. |
| `apps/api/tests/f12/e2e/**` | Criado por **A1** na T13 (primeira tarefa do conjunto de testes de propriedade/e2e), os três agentes acrescentam casos conforme §6 T13. |
| `infra/.env.example` | Só **A3** edita — acrescenta o bloco `# 7. ASSINATURA FISCAL (CAdES)` (§2.4), sem tocar em nenhum bloco existente. |
| `apps/api/pyproject.toml` | Se A3 precisar de uma dependência nova para CAdES além de `cryptography` (avalie primeiro se `cryptography.hazmat.primitives.serialization.pkcs7` basta — é dependência já presente), documente a escolha no mesmo padrão que F10 documentou `minio`/`reportlab` (comentário no bloco, motivo da escolha). Só A3 edita este arquivo nesta fase. |

**Explicitamente fora do seu ownership** (não edite, nem "só para arrumar"):
`packages/contracts/**` (nenhuma exceção nesta fase), `apps/api/app/schemas/contrato.py` (gerado),
`apps/api/app/core/catalogo_erros.py`, `apps/api/app/core/erros.py`, `apps/api/app/core/seguranca.py`,
`apps/api/app/core/middleware.py`, `apps/api/app/db/sessao.py`, `apps/api/app/main.py`,
`apps/api/app/routers/__init__.py`,
`apps/api/app/routers/{auth,tenants,admin,auditoria,empresas,unidades,organizacao,colaboradores,
contratos,biometria,dispositivos,terminais,jornadas,escalas,feriados,afastamentos,marcacoes,
comprovantes,tratamentos,apuracoes,banco_horas,relatorios,solicitacoes,aprovacoes,fechamentos,
espelhos,webhooks,integracoes}.py`, `apps/api/app/marcacao/**` (F5, só leitura),
`apps/api/app/apuracao/**` (F4, só leitura), `apps/api/app/workflow/**` (F10, só leitura),
`apps/api/app/notificacao/**` (F10), `apps/api/app/comum/armazenamento.py` (F10, só
reaproveitamento — não edite, se algo faltar é achado de contrato, não patch seu), `apps/api/app/
jornada/**`, `apps/api/app/identidade/**`, `apps/api/app/organizacao/**`, `apps/api/app/pessoas/**`,
`apps/api/migrations/**`, `apps/api/tests/test_andaime.py`,
`apps/worker/worker/tarefas/{apuracao,fechamento,notificacoes,relatorios,integracoes,lgpd,
importacoes}.py`, `apps/worker/worker/scheduler.py`, `apps/worker/worker/filas.py` (leitura apenas —
já está correto, nenhuma edição necessária), `apps/worker/worker/tarefas/__init__.py` (idem),
`.github/workflows/**`, `infra/**` (exceto `.env.example`, só A3), `Makefile`, `tasks.ps1`, `apps/
web/**`, `apps/mobile/**`.

> **Nenhuma migration nova nesta fase.** As três tabelas do grupo 13 (`afd_arquivos`, `aej_arquivos`,
> `arquivo_assinaturas`) e as tabelas `rep_ps`/`nsr_sequencias` já existem em `0001_inicial.py`. Se você
> achar que precisa de uma coluna ou tabela nova, o contrato está incompleto: abra RFC, não migre por
> conta própria.

> **NUNCA rode `python tools/gerar_do_contrato.py` depois de começar a implementar.** Esse script
> sobrescreve **todos** os routers já implementados de volta a stub — não só `fiscal.py`, mas também
> `tratamentos.py`, `solicitacoes.py`, `fechamentos.py` e todos os outros de F1–F11. É uma ferramenta de
> Fase 0 para regenerar o andaime a partir do contrato; usá-la depois que fases já implementaram lógica
> real destrói trabalho de outras fases sem aviso. Se você precisar conferir a assinatura de um handler
> gerado, leia o arquivo — não regere.

## 6. Tarefas (T1..T13)

### T1 — Módulo comum, fixture da fase e cadastro de REP-P
**Agente:** A1 (código) — T1 e T2 são pré-requisito de todo o resto
**Descrição:** Cria `apps/api/app/fiscal/__init__.py` (docstring e nada mais) e
`apps/api/app/fiscal/comum/formatos.py` (§2.9: `formatar_data`, `formatar_data_hora`,
`montar_arquivo_texto`). Cria `apps/api/tests/f12/conftest.py`: fixture com tenant + empresa + REP-P
ativo (`rep_ps` + `nsr_sequencias` inicializada em 1) + um conjunto pequeno de marcações reais geradas
**através do pipeline real de F5** (não `INSERT` direto — chame `app.marcacao.dominio.registro.
persistir_marcacao` ou o pipeline de ingestão, para que `nsr`/`crc16`/`hash_registro` de F5 sejam
gerados de verdade e a fixture não minta sobre como uma marcação chega ao banco) cobrindo pelo menos um
NSR sequencial de 5+ marcações. `apps/api/app/fiscal/rep_p/servico.py`: `criarRepP` (`numeroInpi`
somente dígitos — valide o `pattern`; inicializa `nsr_sequencias` com `proximo_nsr=1`), `listarRepPs`.
**Pronto quando:** `pytest apps/api/tests/f12 -q` coleta e a fixture sobe/derruba o banco sem erro;
teste prova que `criarRepP` cria a linha em `nsr_sequencias` corretamente inicializada.

### T2 — CRC-16 CCITT-TRUE/KERMIT com o vetor de teste oficial
**Agente:** A1
**Descrição:** `apps/api/app/fiscal/afd/crc16.py::crc16_ccitt(dados: bytes) -> int` — polinômio
`0x1021`, valor inicial `0x0000`, RefIn/RefOut verdadeiros, XorOut `0x0000` (`docs/leiaute-afd-aej.md`
§8.1). **Não copie a implementação de `app.marcacao.dominio.nsr.crc16`** — é CRC-16/ARC, um algoritmo
diferente (§2.5); esta função é nova, específica do leiaute.
**Pronto quando:** `apps/api/tests/f12/afd/test_crc16.py::test_vetor_oficial` prova
`crc16_ccitt(b"123456789") == 0x2189` — **este teste é obrigatório e não pode ser aproximado ou
"quase igual"**: é o único jeito de provar que a implementação bate com a norma sem precisar de um AFD
de referência externo (é exatamente o vetor de teste que a própria norma cita).

### T3 — Hash SHA-256 do registro tipo "7" (ADR-012)
**Agente:** A1
**Descrição:** `apps/api/app/fiscal/afd/hash_tipo7.py` — implementa a fórmula fixada em §2.3
(concatenação dos 8 insumos na representação de largura fixa, sem separador, ISO-8859-1; primeiro
registro da sequência omite o 8º insumo). Isole atrás de uma função nomeada e documente no topo do
módulo, citando `docs/adr/ADR-012-formula-hash-registro-tipo-7-afd-nao-confirmada.md` explicitamente no
docstring (para quem ler o código achar a ADR sem precisar procurar).
**Pronto quando:** teste prova que a função é determinística (mesma entrada, mesmo hash sempre); teste
prova que o primeiro registro da cadeia (sem hash anterior) produz um resultado diferente de um
registro com hash anterior não vazio; teste documenta explicitamente, no próprio arquivo de teste, que
esta fórmula é melhor esforço (ADR-012) e **não é verificada contra um AFD de referência externo** —
não finja que é uma prova de conformidade que ela não é.

### T4 — Registros AFD tipos 1, 2, 4, 5, 6, 9 e linha de assinatura
**Agente:** A1
**Descrição:** `apps/api/app/fiscal/afd/registros.py` — builders de largura fixa para os tipos 1
(cabeçalho), 2 (inclusão/alteração de empresa — provavelmente sem uso real ainda, já que não há operação
de edição de empresa no REP-P nesta fase; documente se ficar vazio/não exercitado), 4 (ajuste de
relógio — idem, sem gatilho automático nesta fase a menos que você encontre uma fonte real de dado),
5 (inclusão/alteração/exclusão de empregado — idem), 6 (eventos sensíveis — códigos `07`/`08`,
disponibilidade/indisponibilidade de serviço, exclusivos de REP-P; se não houver fonte de dado real
para isso ainda, documente como não populado nesta fase, não invente uma tabela de eventos de
disponibilidade), 9 (trailer, com as contagens por tipo). Implementa o `MODO_PREENCHIMENTO_NUMERICO`
(§2.9) e a linha de assinatura placeholder (`"ASSINATURA_DIGITAL_EM_ARQUIVO_P7S"` + espaços até 100
caracteres, `docs/leiaute-afd-aej.md` §7 "Linha final").
**Pronto quando:** teste prova que cada registro tem exatamente o tamanho de caractere especificado na
tabela de `docs/leiaute-afd-aej.md` §7 (302, 331, 73, 118, 36, 64 caracteres respectivamente); teste
prova o CRC-16 dos tipos 1–5 usando o `crc16_ccitt` de T2; teste prova que o trailer soma corretamente
as contagens por tipo, excluindo os tipos 1 e 9 de si mesmo (nota da tabela do leiaute).

### T5 — Registro AFD tipo "7" e verificação de continuidade de NSR
**Agente:** A1
**Descrição:** `apps/api/app/fiscal/afd/tipo7.py` — builder do registro tipo "7" (137 caracteres,
`docs/leiaute-afd-aej.md` §7), usando `hash_tipo7.calcular_hash_tipo7` (T3) e o mapeamento
`canal → identificador do coletor` fixado abaixo (decisão do PCF, para não improvisar):

| `marcacoes.canal` | Código do coletor (campo 6, tipo "7") |
|---|---|
| `mobile` | `01` (app mobile) |
| `web` | `02` (browser) |
| `terminal` | `04` (dispositivo eletrônico) |
| `totem` | `04` (dispositivo eletrônico — mesmo motivo de `terminal`: equipamento físico fixo, não um app que o usuário carrega) |
| `api` | `05` (outro não especificado) |
| `importacao` | **nunca aparece** — excluído da consulta (§2.8) |

Campo 7 (`"0"`/`"1"` on-line/off-line) vem direto de `marcacoes.coletada_offline`. Chama
`app.marcacao.dominio.verificacao_nsr.verificar_sequencia_nsr(verificar_cadeia_hash=False)` **antes**
de montar qualquer registro tipo "7"; se `integro=False`, a função levanta/devolve o suficiente para o
chamador (T6) responder `PONTO-FISC-001` sem escrever nenhum byte.
**Pronto quando:** teste prova o tamanho de 137 caracteres; teste prova que a função de verificação de
lacuna é chamada e que uma lacuna simulada (marcação removida via SQL direto só no teste, nunca em
produção — marcação é imutável) impede a geração, sem criar linha em `afd_arquivos` nem escrever
arquivo (é o teste do critério de aceite "lacuna de NSR é impossível de produzir", aplicado ao **AFD
gerado refletir a garantia que RFC-003/ADR-003 já dão sobre a marcação**, não uma reimplementação da
alocação de NSR em si — ADR-003 já prova que a lacuna é impossível na origem; este teste prova que,
mesmo que ela ocorresse por algum cenário não previsto, o gerador recusaria em vez de produzir um AFD
com buraco).

### T6 — Orquestrador do gerador de AFD, fracionamento, nome de arquivo, evento
**Agente:** A1
**Descrição:** `apps/api/app/fiscal/afd/gerador.py::gerar_afd_arquivo(sessao, tenant_id, *, rep_p_id,
inicio, fim, assinar, solicitante_id) -> AfdArquivo` — valida REP-P ativo e com `numeroInpi` preenchido
(senão `PONTO-FISC-003`), verifica se já existe geração `status='gerando'` sobreposta (`PONTO-FISC-002`),
roda a verificação de NSR (T5), monta o cabeçalho/trailer (T4) e todos os registros tipo "7" no intervalo
(T5) **ordenados por NSR** (§2.8 — não por data/hora), fraciona conforme `tamanhoFracaoRegistros` (§2.11),
monta o nome do arquivo (§2.10), calcula `hashSha256` do arquivo completo (§2.6 — hash de integridade,
trivial), grava via `app.comum.armazenamento.salvar_objeto`, grava a(s) linha(s) de `afd_arquivos`
(`status='gerado'`), chama `app.fiscal.assinatura.cades.assinar_cades` (A3, T11) quando `assinar=True` e
há certificado configurado — sem certificado, conclui com `status='gerado'` sem erro (§2.4). Publica
`afd.gerado` por arquivo gerado (uma vez por fração). Preenche o corpo de `apps/worker/worker/tarefas/
fiscal.py::gerar_afd` chamando esta função. `apps/api/app/routers/fiscal.py::gerar_afd` (handler HTTP):
valida síncrono o que precisa ser síncrono (REP-P existe, não há geração em andamento), cria a linha
inicial de controle e enfileira a tarefa do worker, devolve `202`/`ProcessamentoAssincrono` — mesmo
padrão de "válida síncrono, processa pesado async" que F10 T5 já usou para `criarFechamento`.
**Pronto quando:** teste prova que o AFD gerado para uma fixture pequena e conhecida tem os tipos 1, 7
(um por marcação), 9 e a linha de assinatura, nessa ordem, terminados em CR+LF, codificados em
ISO-8859-1; teste prova fracionamento (fixture com mais registros que `tamanhoFracaoRegistros`) produz
N linhas de `afd_arquivos` com faixas de NSR complementares e sem sobreposição; teste prova que sem
certificado configurado o resultado é `status='gerado'`, nunca erro.

### T7 — CRUD e validação de REP-P completo (fechamento de A1)
**Agente:** A1
**Descrição:** Completa `criarRepP`/`listarRepPs` com os filtros do contrato (`empresaId`, `status`),
paginação por cursor (mesmo padrão de outras listagens do projeto), e a validação de unicidade de
`identificador` por empresa (`uq_rep_ps_identificador`, traduzida para `PONTO-CONF-001` em vez de erro
cru do banco). Roda toda a suíte de A1 (`pytest apps/api/tests/f12/afd apps/api/tests/f12/rep_p -q`) e
corrige o que faltar antes de A2/A3 dependerem do módulo comum e do padrão de gerador.
**Pronto quando:** cobertura de `app.fiscal.rep_p`/`app.fiscal.afd`/`app.fiscal.comum` ≥ 90%; nenhum
teste pendente de T1–T6.

### T8 — Registros AEJ tipos 01–08 e trailer
**Agente:** A2
**Descrição:** `apps/api/app/fiscal/aej/registros.py` — builders delimitados por `\|` (não largura
fixa) para os tipos 01 (cabeçalho), 02 (REPs utilizados — um por REP-P ativo/já existente da empresa no
período, `idRepAej` como chave local sequencial dentro do arquivo), 03 (vínculos), 04 (horário
contratual — a partir de `jornadas`, F3, só leitura), 05 (marcações — o registro-chave, referenciando
tipo 03 e tipo 02; `fonteMarc` distingue `O` original do REP vs. `I`/`P`/`X`/`T` conforme a origem real:
uma marcação sem tratamento associado é `O`; se houver um tratamento aprovado que a afeta, ver o mapeamento
de `tipos_tratamento`/`tipo_operacao` para decidir `I`/`X`/`T` — documente a regra exata que você
escolher, é decisão de A2, não um valor arbitrário por marcação), 06 (matrícula eSocial — só para
colaboradores com mais de um vínculo, conforme o título da própria tabela do leiaute), 07 (ausências e
banco de horas — usa `afastamentos`/`bh_lancamentos`, §2.13), 08 (identificação do PTRP — dados fixos do
próprio sistema: nome do programa "SEEG Ponto", versão, CNPJ do desenvolvedor SEEG; **note que o campo
`emailDesenv` é tipado `N` no leiaute oficial**, provável erro de digitação da norma — trate como texto
livre mas não "corrija" a observação, documente no código exatamente como
`docs/leiaute-afd-aej.md` §10 tipo "08" descreve), trailer tipo "99" (contagens por tipo, sem contar a si
mesmo nem o tipo "01" — nota diferente do trailer do AFD, confirme lendo a nota da tabela). Usa
`app.fiscal.comum.formatos` (T1, A1) para `D`/`DH`; **não implementa CRC-16** (não existe no AEJ, §2.9).
**Pronto quando:** teste prova que cada linha termina em `\|` entre campos e sem `\|` depois do último
campo da linha (regra 3 do leiaute); teste prova que o registro tipo "05" referencia corretamente tipo
"02"/"03"/"04" já emitidos antes dele no mesmo arquivo (integridade referencial **dentro do arquivo**,
não do banco).

### T9 — Orquestrador do gerador de AEJ, reconciliação de banco de horas, evento
**Agente:** A2
**Descrição:** `apps/api/app/fiscal/aej/gerador.py::gerar_aej_arquivo(sessao, tenant_id, *, empresa_id,
inicio, fim, incluir_banco_horas, assinar, solicitante_id) -> AejArquivo` — monta todos os blocos (T8)
para os vínculos ativos da empresa no período, calcula `hashSha256` do arquivo (§2.6), grava via
`app.comum.armazenamento`, grava `aej_arquivos` (`total_vinculos`/`total_marcacoes`/`total_ausencias`/
`total_lancamentos_banco` populados de verdade, não zerados), chama `assinar_cades` (A3) quando
aplicável, publica `aej.gerado`. **Reconciliação obrigatória**: antes de concluir, soma os lançamentos
de banco de horas que o AEJ está exportando (bloco tipo "07", `tipoAusenOuComp="3"`) e compara com o que
`app.apuracao.banco_horas.consulta`/`lancamentos` (F4) devolveria para o mesmo vínculo/período — se
divergir, é `PONTO-FISC-006` (falha de geração), não um arquivo publicado com números que não fecham
(a descrição de `gerarAej` já exige isto: *"O bloco de banco de horas precisa fechar com o extrato do
período; divergência é defeito e interrompe a geração."*). Preenche o corpo de `apps/worker/worker/
tarefas/fiscal.py::gerar_aej`. `apps/api/app/routers/fiscal.py::gerar_aej` (handler HTTP) — mesmo
padrão de T6.
**Pronto quando:** teste prova que os totais do cabeçalho/trailer batem com a contagem real de linhas
de cada tipo; teste prova o critério de aceite "AEJ contém banco de horas coerente com o extrato"
comparando diretamente contra `bh_lancamentos`/o módulo de consulta de F4, não contra um número
recalculado por uma segunda lógica de A2; teste prova que uma divergência forçada (fixture manipulada só
no teste) interrompe a geração com `PONTO-FISC-006`.

### T10 — Fechamento de A2
**Agente:** A2
**Descrição:** Roda toda a suíte de A2 (`pytest apps/api/tests/f12/aej -q`) e corrige o que faltar.
Confirma que nenhuma linha de `app.fiscal.aej.**` escreve em `apuracoes_dia`, `bh_lancamentos`,
`tratamentos` ou qualquer tabela de F3/F4 (prova por `grep` + teste de integração, mesmo padrão do
critério de aceite 7 de F10).
**Pronto quando:** cobertura de `app.fiscal.aej` ≥ 90%; nenhum teste pendente de T8–T9.

### T11 — Módulo de assinatura CAdES
**Agente:** A3
**Descrição:** `apps/api/app/fiscal/assinatura/certificado.py`: lê `FISCAL_CERTIFICADO_PFX_PATH`/
`FISCAL_CERTIFICADO_SENHA` de `app.core.config.Configuracao` (novo bloco, mesmo padrão de
`minio_endpoint`; acrescente também o bloco correspondente comentado em `infra/.env.example`, §5);
devolve `None`/um tipo `CertificadoConfig | None` quando ausente (é o estado real hoje). `apps/api/app/
fiscal/assinatura/cades.py`: `assinar_cades(conteudo: bytes, certificado: CertificadoConfig) -> bytes`
constrói uma assinatura CMS/PKCS#7 destacada (perfil CAdES-BES: ContentType + MessageDigest + SigningTime
como atributos assinados, no mínimo) usando `cryptography.hazmat.primitives.serialization.pkcs7` (já
dependência de `apps/api`) — se essa API não for suficiente para os atributos exigidos pelo perfil
CAdES-BES, adicione a dependência mínima necessária e documente o motivo (`apps/api/pyproject.toml`,
§5). `validar_cades(conteudo: bytes, assinatura: bytes, certificado_esperado: bytes | None) ->
ResultadoValidacao` — verificação **independente** (não reaproveita nenhum estado interno da chamada que
assinou, para não ser uma verificação trivialmente circular): reconstrói a assinatura, confere que o
`MessageDigest` bate com o SHA-256 do `conteudo`, e (quando o certificado for autoassinado de teste)
confere a validade/expiração — grava o resultado em `arquivo_assinaturas.validacao_resultado` (campo
já existe no schema). **Testes usam um certificado autoassinado gerado na própria fixture**
(`cryptography.x509`, T11 mesma tarefa), rotulado como tal em todo lugar.
**Pronto quando:** teste prova que `assinar_cades` + `validar_cades`, com um certificado de teste,
produzem uma assinatura estruturalmente válida (parseável de volta como CMS/PKCS#7, `MessageDigest`
confere); teste prova que `certificado=None` nunca chega a `assinar_cades` (a checagem de
"certificado ausente" acontece antes, no chamador, respondendo `PONTO-FISC-004`).

### T12 — Cofre: listagem, obtenção, download, assinatura de arquivo fiscal e comprovante
**Agente:** A3
**Descrição:** `apps/api/app/fiscal/cofre/consulta.py`: lógica de `listarAfd`/`obterAfd`/`baixarAfd`
(devolve o conteúdo em `text/plain` ISO-8859-1 **sem reencodar** — a descrição do contrato já avisa que
converter para UTF-8 no caminho quebra o leiaute; com `incluirAssinatura=true`, empacota arquivo + `.p7s`
— formato de pacote à sua escolha, documente; registra o download na trilha de auditoria via
`app.identidade.auditoria.hash_chain.gravar_auditoria`, mesmo padrão que F10 já usa para
fechamento/reabertura/assinatura) e `listarAej`/`obterAej` (mesma lógica, sem download bruto exigido
pelo contrato — confirme lendo o `openapi.yaml`: não há `/v1/fiscal/aej/{arquivoId}/download`, só AFD
tem esse caminho; **não invente** um download de AEJ que o contrato não define). `apps/api/app/fiscal/
assinatura/servico.py::assinar_arquivo_fiscal` (handler de `assinarArquivoFiscal`): resolve o arquivo
(`afd_arquivos`/`aej_arquivos`/`espelhos`/`comprovantes`/`relatorios` conforme `tipoArquivo` — você só
implementa os casos `afd`/`aej`/`comprovante` nesta fase; `espelho`/`relatorio` já são de F10/F11 e não
devem passar por aqui se já tiverem endpoint próprio — confirme e documente se encontrar sobreposição),
sem certificado responde `PONTO-FISC-004`; com certificado, chama `cades.assinar_cades` (T11), grava
`arquivo_assinaturas`, atualiza `status='assinado'` no arquivo de origem. **Assinatura do comprovante**:
`tipoArquivo='comprovante'` usa **CAdES** (não PAdES) — decisão fixada, porque
`comprovantes.conteudo_texto` é texto puro, não um PDF embutido (confirme lendo `apps/api/app/
marcacao/comprovantes/emissor.py`); PAdES só se aplicaria a um comprovante em PDF, que não é o formato
que este produto emite (`docs/leiaute-afd-aej.md` §11 confirma PAdES é "quando emitido em PDF" — o
nosso não é).
**Pronto quando:** teste prova que `baixarAfd` devolve bytes idênticos aos gerados (round-trip
ISO-8859-1, sem qualquer transformação); teste prova que assinar duas vezes o mesmo arquivo não
sobrescreve a assinatura anterior (append-only, `arquivo_assinaturas` já tem gatilho que bloqueia
`DELETE` — prove com `UPDATE`/`DELETE` reais falhando com `ERRCODE 42501`, role de aplicação real, mesmo
padrão de evidência que F10 exigiu para `assinaturas_espelho`); teste prova o download registrado em
`auditoria`.

### T13 — Testes de propriedade e e2e completo
**Agentes:** A1, A2, A3 (conjunto)
**Descrição:** `apps/api/tests/f12/e2e/test_fluxo_completo.py`: cadastra REP-P → gera marcações reais via
pipeline de F5 (não `INSERT` direto) cobrindo pelo menos 20 NSR sequenciais, incluindo pelo menos uma
offline (`coletada_offline=true`) → `criarSolicitacao`/aprovação/tratamento via F10 (para o AEJ ter algo
de tratamento para exportar) → `gerarAfd` (prova: tipos corretos, tamanho de registro correto, ordenado
por NSR, sem lacuna) → `gerarAej` (prova: banco de horas bate com extrato, tratamento aparece só no AEJ
nunca no AFD) → `assinarArquivoFiscal` para os dois, com certificado de teste (prova: `.p7s` válido
estruturalmente, `arquivo_assinaturas` gravado, `status` avança) → `baixarAfd`/`obterAej` (prova:
conteúdo bate byte a byte com o que foi gerado). Também aqui: o teste do vetor CRC-16 (T2) e o teste de
lacuna de NSR impossível de produzir (T5) já existem em suas tarefas — este e2e não os duplica, só os
referencia no relatório final.
**Pronto quando:** o teste completo passa; a saída real é colada no relatório da fase, mostrando cada
etapa.

### T14 — Fechamento da fase
**Agentes:** A1, A2, A3
**Descrição:** Rodar todos os comandos da §8 e colar a saída real no relatório da fase, item a item
contra a §7. Acrescentar em `docs/backlog.md` os achados de §2.7 (prosa desatualizada em 5 locais) e
§2.10 (exemplo de nome de arquivo em `events.yaml`), se ainda não estiverem lá.
**Pronto quando:** todos os comandos verdes, com saída colada; `git status --short packages/contracts`
sem nenhuma saída (contrato intocado — sem exceção nesta fase, diferente de F10).

## 7. Critérios de aceite

O relatório final responde item a item, com saída real colada. Os critérios oficiais de
`FASES-E-AGENTES.md` estão adaptados aqui à luz do ADR-012 e do §2.4 — leia a nota de cada um.

1. **"AFD gerado passa em validador oficial/de mercado · comparação byte a byte contra AFD de sistema já
   aceito para o mesmo conjunto de marcações"** — **parcialmente atendido por desenho, não por
   limitação de esforço**: os registros tipos 1, 2, 4, 5, 6, 9, a linha de assinatura, e **todo** o AEJ
   têm leiaute confirmado com alta confiança pela T0 (`docs/leiaute-afd-aej.md`) e a comparação byte a
   byte é um critério real e alcançável para eles — prove com um teste que monta um AFD/AEJ de uma
   fixture conhecida e confere cada posição/campo manualmente contra a tabela do leiaute. **O registro
   tipo "7" (o mais importante do REP-P) NÃO tem essa garantia** — a fórmula do hash SHA-256 encadeado é
   melhor esforço documentado (ADR-012), e este critério fica **explicitamente marcado como não
   verificável** para esse tipo de registro especificamente, até que uma referência externa feche a
   Lacuna nº 1. Não declare este critério "atendido" sem essa ressalva explícita no relatório.
2. **CRC-16 bate com o vetor de teste oficial da norma**: `crc16_ccitt(b"123456789") == 0x2189` — teste
   automatizado (T2), sem depender de nenhum AFD de referência externo.
3. **`.p7s` estruturalmente válido (CMS/PKCS#7, perfil CAdES-BES)**: verificável com um certificado de
   teste (T11). **NÃO verificável contra uma cadeia de confiança ICP-Brasil real** — não há certificado
   e-CNPJ A1 da SEEG (§2.4), e este critério fica marcado como não verificável na parte de confiança de
   cadeia até que o certificado real chegue; a parte estrutural (o `.p7s` é um CMS/PKCS#7 bem formado,
   com os atributos exigidos pelo CAdES-BES) é verificável e verificada.
4. **AEJ contém banco de horas coerente com o extrato**: os totais e lançamentos do bloco tipo "07"
   batem com `bh_lancamentos`/`app.apuracao.banco_horas.consulta` para o mesmo vínculo/período (T9);
   divergência interrompe a geração (`PONTO-FISC-006`), nunca publica um arquivo com números que não
   fecham.
5. **Lacuna de NSR é impossível de produzir (teste adversarial)** — decomposto conforme §2.8: (a) a
   garantia de que a **alocação** de NSR nunca produz lacuna já está provada por ADR-003/F5 (você não
   reprova isso aqui); (b) o que esta fase prova é que o **AFD gerado reflete** essa garantia — um
   intervalo de NSR sem lacuna produz um AFD sem lacuna, e uma lacuna hipotética (simulada só em teste,
   nunca alcançável em produção porque marcação é imutável) faz o gerador **recusar** produzir o
   arquivo (`PONTO-FISC-001`) em vez de gerar um AFD com buraco.
6. **REP-P/NSR**: `criarRepP` inicializa `nsr_sequencias` corretamente; o AFD nunca inclui `canal=
   'importacao'`; a ordenação do AFD é por NSR, não por data/hora (diferente de relatório/espelho).
7. **Reaproveitamento de F4/F5, não duplicação**: nenhuma linha desta fase escreve em `marcacoes`,
   `nsr_sequencias`, `apuracoes_dia`, `apuracao_componentes`, `bh_lancamentos`, `bh_contas`,
   `tratamentos` — prova por análise estática (grep) mais teste de integração, mesmo padrão do critério
   7 de F10.
8. **`marcacoes.crc16`/`hash_registro`/`hash_anterior`/`linha_afd` nunca são copiados diretamente para
   um campo do AFD** — prova por análise estática: nenhuma referência a essas quatro colunas em
   `app/fiscal/afd/**` fora de uma eventual leitura defensiva/de log (se existir, justifique).
9. **Assinatura eletrônica não confundida com a do espelho**: nenhuma linha desta fase toca
   `assinaturas_espelho`, `espelhos`, `fechamentos`.
10. **Adaptador de certificado**: com `FISCAL_CERTIFICADO_PFX_PATH` ausente (o estado real hoje),
    `gerarAfd`/`gerarAej` concluem com `status='gerado'` sem erro, e `assinarArquivoFiscal` responde
    `424 PONTO-FISC-004` — os dois comportamentos provados por teste dedicado.
11. **Toda rota declara `Depends(exigir_permissao(...))`** com exatamente o `x-permissao` do contrato
    (`fiscal.executar`, `fiscal.ler`, `fiscal.exportar`, `fiscal.assinar`, `fiscal.criar`) — verificável
    pelo mesmo teste que percorre o `openapi.yaml` rota a rota que F4/F10 já escreveram.
12. **Eventos publicados batem campo a campo com `events.yaml`**: `afd.gerado`, `aej.gerado`.
13. **Cobertura ≥ 90%** em `app.fiscal` inteiro
    (`--cov=app.fiscal --cov-report=term-missing`), saída real colada.
14. **Contrato intocado**: `git status --short packages/contracts` sem nenhuma saída — diferente de
    F10 (que teve uma exceção autorizada), esta fase não tem nenhuma.
15. **`apps/web`/`apps/mobile` intocados**: `git status --short apps/web apps/mobile` sem saída.
16. Todos os comandos da §8 verdes, com saída real colada no relatório.

## 8. Comandos de verificação

Rode a partir da **raiz do repositório**, salvo onde indicado. Windows usa `.\tasks.ps1`;
Linux/macOS usa `make`.

Subir o banco:

```bash
docker compose --env-file infra/.env.example -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d postgres redis minio
```

```powershell
.\tasks.ps1 up
```

Migrar:

```bash
cd apps/api && alembic upgrade head
```

```powershell
cd apps/api; alembic upgrade head
```

Lint, formatação e tipos (versões fixadas no CI: ruff 0.7.4, mypy 1.13.0):

```bash
ruff check apps packages tests
ruff format --check apps packages tests
cd apps/api && mypy
cd apps/worker && mypy
```

```powershell
.\tasks.ps1 lint
.\tasks.ps1 typecheck
```

**Saída esperada:** `All checks passed!`, `NN files already formatted`,
`Success: no issues found in NNN source files`.

Testes da fase, com cobertura do pacote de domínio:

```bash
cd apps/api && pytest tests/f12 -q --cov=app.fiscal --cov-report=term-missing
```

```powershell
cd apps/api; pytest tests/f12 -q --cov=app.fiscal --cov-report=term-missing
```

**Saída esperada:** todos os testes passam; a linha `TOTAL` da cobertura ≥ 90%; nenhum `skip` nos
testes que exigem banco.

Vetor de teste oficial do CRC-16, isolado para evidência no relatório:

```bash
cd apps/api && pytest tests/f12/afd/test_crc16.py -v
```

**Saída esperada:** `test_vetor_oficial PASSED`, com o valor `0x2189` visível na asserção ou no log.

Lacuna de NSR impossível de produzir no AFD gerado:

```bash
cd apps/api && pytest tests/f12/afd -q -k "lacuna or gap or nsr" -s
```

Reconciliação de banco de horas do AEJ:

```bash
cd apps/api && pytest tests/f12/aej -q -k "banco_horas or extrato or reconcilia" -s
```

Imutabilidade da assinatura, isolada para evidência no relatório:

```bash
cd apps/api && pytest tests/f12/assinatura -q -k "imutavel or cades or assinatura" -s
```

Regressão de F4, F5 e F10 (não podem quebrar):

```bash
cd apps/api && pytest tests/f4 tests/f5 tests/f10 -q
```

E2e completo (o critério de aceite 5 do relatório oficial e vários dos §7 acima):

```bash
cd apps/api && pytest tests/f12/e2e -q -v
```

Regressão do andaime da Fase 0 (não pode quebrar):

```bash
cd apps/api && pytest tests/test_andaime.py -q
```

Inventário de rotas idêntico ao contrato:

```bash
cd apps/api && python tools/conferir_rotas.py
```

**Saída esperada:** `Inventario identico ao contrato (metodo, caminho e operationId).`

Contrato intocado (sem exceção nesta fase):

```bash
git status --short packages/contracts
```

**Saída esperada:** sem saída nenhuma.

`apps/web`/`apps/mobile` intocados:

```bash
git status --short apps/web apps/mobile
```

**Saída esperada:** sem saída nenhuma.

Migration continua reversível contra banco real (não deveria haver nenhuma nova nesta fase — este
comando é para provar isso, não para testar uma migration que você escreveu):

```bash
cd apps/api && alembic upgrade head && alembic downgrade base && alembic upgrade head
```

## 9. Proibições

1. **Não gere hash de arquivo inteiro em nome do leiaute.** O único hash que a norma exige é o SHA-256
   por registro, tipo "7", encadeado (ADR-012, §2.3). O campo `hashSha256` de `AfdArquivo`/`AejArquivo`
   é um hash de integridade do arquivo completo — do **contrato**, não da norma (§2.6) — calcule-o
   (é fácil), mas nunca o apresente em código, teste ou documentação como "o hash exigido pela
   Portaria".
2. **Não use `\|` no AFD.** É largura fixa por posição, sem delimitador (§2.2). `\|` é exclusivo do AEJ.
3. **Não implemente CRC-16 para os tipos 6, 7 ou 9 do AFD, nem em lugar nenhum do AEJ.** O CRC-16 é
   exclusivo dos tipos 1–5 do AFD (§2.2, §2.9).
4. **Não reutilize `marcacoes.crc16`, `hash_anterior`, `hash_registro` ou `linha_afd` como valor de
   campo do AFD.** São cálculos de F5 com algoritmo/fórmula diferentes dos exigidos pelo leiaute (§2.5)
   — calcule tudo de novo, sobre os dados-fonte, dentro desta fase.
5. **Não reimplemente cálculo de apuração, tratamento ou banco de horas.** F4 já fez isso; você só lê
   (§2.13).
6. **Não invente um segundo mecanismo de alocação de NSR.** F5/ADR-003 já resolveram isso; você só
   consome (`marcacoes.nsr`, `nsr_emissoes`) e reaproveita `verificar_sequencia_nsr` para a checagem de
   continuidade (§2.8). Nunca escreva em `nsr_sequencias`.
7. **Não redecida a fórmula do hash do registro tipo "7" sozinho.** É o ADR-012, decisão já tomada pelo
   dono do produto — implemente exatamente a fórmula fixada em §2.3, isolada atrás da função nomeada de
   T3. Se encontrar uma referência externa real durante a fase, documente e leve ao orquestrador; não
   troque a fórmula por conta própria.
8. **Não tente obter, gerar ou simular um certificado ICP-Brasil real.** Está confirmado indisponível
   (§2.4). O mecanismo de assinatura é real; a credencial de produção não é desta fase. Certificados de
   teste usados em testes automatizados nunca são apresentados como reais em código, log ou
   documentação.
9. **Não implemente nenhuma chamada a uma Autoridade Certificadora real ou serviço de carimbo de tempo
   real sem credencial configurada.** Se precisar de carimbo de tempo (`carimbo_tempo`/`politica_
   assinatura` de `arquivo_assinaturas`), use o relógio do servidor como já é o padrão do projeto
   (nunca um TSA externo sem credencial).
10. **Não toque em `apps/web` nem em `apps/mobile`.** Esta fase é backend puro.
11. **Não implemente relatórios, exportação em massa, ou o PDF "de designer" do espelho.** É F11 (§2.12).
12. **Não escreva em `assinaturas_espelho`, `espelhos`, `fechamentos`, `periodos` (exceto leitura).** É
    F10, e é uma assinatura conceitualmente diferente da desta fase (§2.14).
13. **Não invente endpoint que não existe no contrato** — em particular, não adicione `atualizarAfd`,
    `excluirAfd`, `atualizarAej`, `excluirAej`, `atualizarRepP`, `excluirRepP`, `regerarAfd`,
    `GET /v1/fiscal/aej/{arquivoId}/download` (não existe — só AFD tem download bruto no contrato).
    Se a ausência parecer defeito do contrato, é RFC.
14. **Não edite `packages/contracts/` de forma alguma nesta fase.** Ao contrário de F10, não há nenhuma
    exceção autorizada aqui. Achados de contrato (§2.7, §2.10) vão para `docs/backlog.md`, nunca para
    uma edição direta.
15. **NUNCA rode `python tools/gerar_do_contrato.py` depois de começar a implementar.** Sobrescreve
    todos os routers já implementados de volta a stub, de todas as fases já concluídas — não é um
    comando seguro de "conferir o gerado", é destrutivo (§5).
16. **Não use os termos proibidos** da seção 6 do glossário (*marcação*, nunca "batida"; *tratamento*,
    nunca "ajuste de marcação"; *apuração*; *colaborador*/*vínculo*, nunca "funcionário"; *tenant*,
    nunca "empresa" para dizer cliente do SaaS; *coletor*, nunca "relógio de ponto"/"catraca" — o REP-P
    é o software, não o terminal).
17. **Não declare a fase pronta sem rodar os comandos da §8 e colar a saída real.** Em especial o vetor
    de teste do CRC-16 (§7 critério 2) e a ressalva explícita do critério 1 sobre o registro tipo "7"
    (ADR-012) — declarar "critério 1 atendido" sem essa ressalva é uma afirmação factualmente incorreta
    sobre uma fase de conformidade legal para uma empresa real.
