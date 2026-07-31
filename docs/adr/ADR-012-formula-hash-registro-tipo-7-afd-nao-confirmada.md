# ADR-012 — Débito técnico aceito: fórmula de concatenação do hash SHA-256 do registro tipo "7" do AFD não confirmada contra fonte primária suficiente

**Status:** Aceito · 30/07/2026
**Decisores:** Henrique Matias (dono do produto) — decisão de prosseguir com melhor
esforço documentado em vez de bloquear a fase esperando uma referência externa,
escalada pelo orquestrador ao planejar a F12 dado o risco de conformidade legal
envolvido
**Fases afetadas:** F12 (gerador de AFD, registro tipo "7", ownership de A1)

---

## Contexto

A tarefa T0 da F12 (pesquisa bloqueante do leiaute AFD/AEJ contra a Portaria MTP
671/2021, documentada em `docs/leiaute-afd-aej.md`) leu diretamente os dois PDFs
técnicos oficiais do MTE (leiaute do AFD e leiaute do AEJ, ambos em `gov.br`) e
confirmou, com alta confiança, o leiaute completo campo a campo de todos os tipos
de registro do AFD e do AEJ — inclusive o algoritmo exato de CRC-16 (CRC-16
CCITT-TRUE/KERMIT, polinômio `0x1021`, confirmado pelo vetor de teste `"123456789"`
→ `0x2189` publicado na própria norma).

O registro tipo "7" do AFD — exclusivo do REP-P, o modelo do SEEG Ponto, e citado
como "o coração do REP-P" pela pesquisa — usa um mecanismo diferente: um **hash
SHA-256 encadeado** (campo nº 8, "código hash"), em vez de CRC-16. A norma
(`docs/leiaute-afd-aej.md`, §8.2) lista os 8 insumos do hash com precisão (NSR,
tipo do registro, data/hora da marcação, CPF, data/hora de gravação, identificador
do coletor, indicador on-line/off-line, hash do registro tipo "7" anterior), mas
**não especifica**:

1. Se os campos entram na concatenação em sua representação de largura fixa (com
   os *paddings* de espaço/zero do próprio registro AFD) ou em formato "cru" sem
   padding.
2. Se há algum caractere separador entre os campos concatenados, ou concatenação
   direta.
3. A codificação de bytes exata usada para essa concatenação especificamente
   (ISO 8859-1 é a codificação do arquivo como um todo, mas isso não foi afirmado
   explicitamente para o cálculo do hash em si).
4. O que substitui o 8º insumo ("hash do registro anterior, caso exista") quando
   não existe registro tipo "7" anterior — campo vazio, string vazia, ausência
   total do insumo, ou outro valor sentinela.

Duas implementações que sigam apenas o texto da norma podem produzir hashes
SHA-256 diferentes para o mesmo evento de marcação. Isso bloqueia diretamente o
critério de aceite oficial da F12 (`FASES-E-AGENTES.md`): *"comparação byte a
byte contra AFD de sistema já aceito para o mesmo conjunto de marcações"* —
especificamente para o tipo de registro mais importante do arquivo.

## Por que isto importa

O AFD é um arquivo de conformidade legal (Portaria MTP 671/2021) usado para
fiscalização trabalhista de uma empresa real (SEEG). Um hash calculado com a
fórmula errada não é um bug cosmético — é um arquivo que pode ser considerado
inválido ou inconsistente por um auditor/fiscal que compare contra a mesma
marcação processada por outro sistema, ou contra a cadeia de hash anterior em
caso de auditoria de integridade.

## Por que não foi resolvido nesta pesquisa

A pesquisa (T0) esgotou as fontes primárias razoavelmente acessíveis: os dois
PDFs técnicos oficiais dedicados ao leiaute (lidos por extração direta de PDF
binário, não resumo intermediário — ver metodologia em
`docs/leiaute-afd-aej.md` §16), a portaria de alteração mais recente sobre
assinatura (4.198/2022, lida integralmente), e o FAQ oficial do MTE. Nenhuma
dessas fontes especifica o formato de concatenação com precisão suficiente. As
duas formas de fechar essa lacuna de verdade — obter um AFD de referência de um
fabricante REP-P já homologado, ou abrir consulta formal à Secretaria de
Inspeção do Trabalho/MTE — dependem de ação externa ao alcance de uma sessão de
desenvolvimento (acesso a um fornecedor concorrente já homologado, ou um canal
formal de comunicação com o órgão regulador), não de mais pesquisa em fontes
públicas.

## Decisão

**A F12 prossegue sem bloquear no registro tipo "7", implementando a
interpretação mais razoável da norma, documentada e isolada atrás de uma
constante/flag, com esta lacuna registrada formalmente como débito técnico.**

1. O gerador do registro tipo "7" (F12/A1) implementa a concatenação dos 8
   insumos na representação de largura fixa do próprio registro (mesmo padding
   que o campo teria no AFD), sem separador entre eles, em ISO 8859-1 — a leitura
   mais consistente com o resto da norma (que já usa largura fixa e ISO 8859-1
   em todo o arquivo) — com o primeiro registro tipo "7" da sequência omitindo o
   8º insumo inteiramente (string vazia) na ausência de um hash anterior. Esta é
   uma hipótese razoável, **não uma garantia confirmada**.
2. A implementação isola essa fórmula de concatenação atrás de uma função/
   constante nomeada (não espalhada pelo código), especificamente para permitir
   trocar rapidamente de interpretação assim que uma referência real aparecer,
   sem precisar reescrever o gerador inteiro.
3. O critério de aceite oficial da F12 ("comparação byte a byte contra AFD já
   aceito") fica marcado como **não verificável para o registro tipo "7"**
   nesta entrega — não escondido, não reclassificado como "atendido com
   ressalva". Os demais tipos de registro do AFD (1-6, 9) e todo o AEJ, cujo
   leiaute foi confirmado com alta confiança pela T0, não têm essa limitação.
4. Este ADR é a fonte de verdade sobre o estado real dessa lacuna até que uma
   referência externa (AFD de fabricante homologado, ou resposta formal do
   MTE/SIT) resolva ou revise a fórmula.

## Alternativas consideradas

**Bloquear a F12 até obter uma referência externa.** Pausaria a fase inteira
(ou pelo menos o gerador de AFD, o entregável mais crítico) por um prazo
indefinido, dependente de terceiros (concorrente homologado ou órgão público)
fora do controle do time. Descartada: os demais 90%+ do escopo da fase (AEJ
completo, demais tipos de registro do AFD, assinatura CAdES, cofre de arquivos)
não dependem dessa lacuna específica e não há razão para atrasá-los.

**Escolher arbitrariamente uma interpretação sem documentar a incerteza.**
Esconderia o risco real de um auditor encontrar um AFD com hash que não bate
contra outro sistema, sem que ninguém soubesse por quê. Descartada pela mesma
razão que ADR-010/ADR-011 preferem débito documentado a "parece que está certo".

## Consequências

**Positivas.** F12 entrega a esmagadora maioria do seu escopo (AEJ inteiro,
demais registros do AFD, assinatura eletrônica, cofre de arquivos) sem esperar
por uma dependência externa fora do controle do time. A lacuna fica registrada
com precisão cirúrgica (o campo exato, a norma exata, as fontes já esgotadas) —
quem resolver no futuro começa de um diagnóstico completo, não do zero.

**Negativas e mitigações.** (a) O AFD gerado por esta fase **não deve ser usado
para homologação oficial ou fiscalização real** até essa lacuna ser fechada —
comunicar isso como limitação operacional conhecida ao time de RH/jurídico da
SEEG antes de qualquer uso em produção. (b) Se a interpretação escolhida
estiver errada, toda a cadeia de hash de tipo "7" já gerada muda quando a
fórmula for corrigida (é uma cadeia — mudar a fórmula recalcula tudo a partir
do ponto da correção) — mitigação: não há histórico real de produção ainda,
então o custo de uma correção futura é puramente de código, não de dado já
publicado/auditado. (c) Buscar ativamente uma referência (AFD de outro sistema
homologado, ou abertura de chamado formal com a SIT/MTE) deveria ser tratado
como prioridade de negócio, não só técnica — o dono do produto decide o canal e
o prazo dessa busca, fora do escopo desta sessão de desenvolvimento.
