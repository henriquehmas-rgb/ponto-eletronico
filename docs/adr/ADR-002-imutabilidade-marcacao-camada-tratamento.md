# ADR-002 — Imutabilidade da marcação e camada de tratamento separada

**Status:** Aceito · 25/07/2026
**Decisores:** SEEG — arquitetura
**Fases afetadas:** F5 (implementa), F4 (consome), F9b e F10 (interface), F12 (AFD/AEJ)

---

## Contexto

A Portaria MTP 671/2021 é explícita em duas vedações que, juntas, definem a
arquitetura do sistema inteiro: é vedado ao REP **alterar ou apagar** dados de
marcação de ponto, e é vedado **inserir marcação** que não corresponda ao fato
real ocorrido no momento do registro. O AFD, gerado exclusivamente pelo REP-P,
tem que ser um espelho fiel do que os coletores produziram.

Ao mesmo tempo, a realidade operacional de RH é feita de correção: o
colaborador esqueceu de bater na volta do almoço, o terminal ficou sem energia,
a marcação da madrugada entrou no dia errado, o atestado chegou depois. Se essas
correções tocarem a marcação, o AFD deixa de ser fidedigno e o sistema não
sobrevive a uma fiscalização. Se as correções não existirem, o sistema é
inutilizável.

Há ainda um agravante de produto: em fiscalização, a defesa do empregador é
justamente conseguir demonstrar **o que foi registrado** e, separadamente,
**quem alterou o quê, quando e por quê**. Um sistema que mistura as duas coisas
destrói a própria evidência que deveria produzir.

## Decisão

Duas camadas fisicamente separadas, com fronteira imposta pelo banco:

1. **`marcacoes` é append-only.** Contém o fato registrado: NSR, data/hora do
   servidor, CPF do trabalhador, REP-P de origem, canal, CRC-16 e hash
   encadeado. Nunca sofre `UPDATE` nem `DELETE`.
2. **`tratamentos` é a única camada de correção.** Inclusão manual de horário,
   desconsideração de batida duplicada, ajuste de intervalo, abono e
   justificativa vivem aqui, cada um com autor, momento, motivo, anexo e cadeia
   de aprovação.
3. A apuração (`apuracoes_dia`) é sempre o resultado de
   `marcações ⊕ tratamentos ⊕ afastamentos` sob as regras da jornada do dia.
4. **AFD deriva exclusivamente de `marcacoes`. AEJ é quem enxerga tratamento,
   ausência e banco de horas.** Confundir o escopo dos dois arquivos é o erro
   que invalida o sistema.

A vedação é imposta em **três camadas independentes**, porque uma só é uma
promessa:

- **API:** não existe `PUT`, `PATCH` nem `DELETE` em `/v1/marcacoes`, e essas
  rotas não serão adicionadas em versão futura (`openapi.yaml`, tag
  `marcacoes`). Tentativa responde `PONTO-MARC-001` / `PONTO-MARC-002`.
- **Banco:** gatilho `fn_registro_imutavel()` aborta `UPDATE`, `DELETE` e
  `TRUNCATE` com `ERRCODE 42501` (`packages/contracts/schema.sql`).
- **Privilégio:** a role da aplicação tem apenas `SELECT` e `INSERT` na tabela.

## Alternativas consideradas

**Soft delete / campo `ativo` na marcação.** É o padrão de mercado e foi
descartado: uma marcação com `ativo = false` continua sendo uma alteração de
registro, o AFD passa a depender de um filtro, e o filtro é exatamente o tipo de
detalhe que se perde numa refatoração. A desconsideração de uma batida duplicada
existe — mas como **tratamento**, visível no espelho e no AEJ, com a marcação
original intacta no AFD.

**Versionamento da própria marcação (linha nova com `versao + 1`).** Preserva
histórico, mas cria ambiguidade sobre qual versão entra no AFD e obriga o
gerador a decidir semântica legal em tempo de escrita. A separação por tabela
elimina a pergunta.

**Log de auditoria como única defesa.** Insuficiente: auditoria registra o que
aconteceu, não impede. Com privilégio de `UPDATE` na tabela, um bug de ORM ou um
script de correção "só dessa vez" apaga a evidência.

**Permitir edição dentro de uma janela curta (ex.: 5 minutos).** Tentador para
corrigir erro de digitação de canal, e descartado porque a Portaria não abre
janela. Erro de ingestão se resolve com idempotência e com tratamento, não com
edição.

## Consequências

**Positivas.** O AFD é fidedigno por construção, e a defesa em fiscalização
passa a ser uma consulta, não uma reconstrução. A trilha de correção é completa
e nominal. O motor de cálculo fica mais simples: ele lê fatos imutáveis e
sobreposições declarativas, o que é justamente o que torna o recálculo
determinístico (ADR-004).

**Negativas e mitigações.** (a) Toda tela de RH precisa educar: não existe
"editar marcação", existe "lançar tratamento". A F9b assume esse vocabulário na
interface, e o glossário proíbe o termo "editar marcação" na documentação.
(b) Duplicata real de ingestão (mesmo evento chegando duas vezes) não pode ser
apagada depois — tem que ser evitada **antes**, o que empurra a idempotência
para requisito de primeira ordem da F5 (`marcacao_idempotencia`, chaves
`external_id`, `device_id + log_id`, `Idempotency-Key`). (c) A tabela cresce
sem nunca encolher: mitigado por particionamento mensal de `marcacoes` e
política de retenção de 5 anos com arquivamento, nunca exclusão dentro do prazo
legal. (d) Correção de dado cadastral que se reflete na marcação (CPF digitado
errado) exige processo próprio, documentado, e não passa por `UPDATE` na tabela.
