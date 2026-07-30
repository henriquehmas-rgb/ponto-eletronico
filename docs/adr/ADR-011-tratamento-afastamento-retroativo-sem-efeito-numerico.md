# ADR-011 — Débito técnico aceito: `Tratamento` de categoria `afastamento` (retroativo) não altera a apuração

**Status:** Aceito · 28/07/2026
**Decisores:** Orquestrador, ao revisar o achado de A4 durante o fechamento da
F10; escalado como ADR (não RFC) porque não há mudança de contrato nem de
schema envolvida — é uma lacuna de comportamento em código Python já
congelado (F4)
**Fases afetadas:** F4 (`apurar_dia`, onde a lacuna está), F10 (onde a lacuna
foi descoberta — tipo de solicitação `afastamento`/`afastamento_retroativo`),
F11/F12 (relatórios e AFD/AEJ, que herdam a apuração como está)

---

## Contexto

O tipo de tratamento de fábrica `afastamento_retroativo` (`seed_dev.py`,
categoria `afastamento`) existe desde a F4 e sua própria descrição em
`seed_dev.py` diz: *"Aplica um afastamento sobre período já apurado,
**disparando reprocessamento**."* A F10 (`docs/fases/
F10-workflows-aprovacoes-fechamento.md`, §2.2, linha 114) descreve o mesmo
caso como *"o mesmo padrão de qualquer outro tratamento"* — ou seja, a F10
presumiu que aprovar essa solicitação teria efeito numérico na apuração do
dia, igual a `inclusao_manual`/`desconsideracao`/`abono_falta`.

Não tem. `app/apuracao/dominio/servico.py::_carregar_marcacoes_e_tratamentos`
só dá efeito numérico a três categorias de tratamento:
`inclusao_marcacao`, `desconsideracao_marcacao` e `abono`. A categoria
`afastamento` cai no ramo documentado como "demais categorias... sem efeito
numérico aqui" (linha 354-356 do módulo), com justificativa explícita no
docstring do módulo (ponto 4): *"`afastamento` já é insumo de F3 (via
`afastamentos`)"*.

Essa justificativa é verdadeira para o caso que a F4 tinha em mente —
afastamentos **futuros/vigentes** (`ferias`, licença médica programada, etc.),
que a F3 já resolve como `tipo_dia` não-útil antes mesmo de a apuração
rodar, via a tabela `afastamentos` (não `tratamentos`). Mas a F10 introduziu
um caso genuinamente novo que a F4 nunca cobriu: uma correção **retroativa**,
sobre um dia **já apurado no passado** como dia normal (ex.: atestado médico
entregue com atraso, depois que o sistema já processou o dia como falta).
Para esse caso, inserir uma linha em `afastamentos` não ajuda — o resolvedor
da F3 só influencia dias ainda não apurados — por isso a F10 corretamente
escolheu o caminho de `Tratamento` (para disparar `decidir_tratamento` →
reprocessamento via `recalcular_periodo`/`apurar_dia`). O problema é que,
ao chegar em `apurar_dia`, esse `Tratamento` é lido (conta para
`tem_tratamento`) mas não produz nenhuma mudança em `falta_minutos` nem em
qualquer outro componente — o dia é reprocessado e sai **idêntico** ao que
era antes.

## Por que isto importa

Um RH que aprova uma "comunicação de afastamento" retroativa (tipo de
solicitação `afastamento`, F10) recebe confirmação de que a solicitação foi
aprovada e o `Tratamento` foi criado e aprovado — mas o colaborador continua
aparecendo com falta não abonada na apuração do dia, no espelho de ponto
(F10) e, futuramente, no AFD/AEJ (F12). Isto é uma lacuna funcional real, não
cosmética: a rotina existe na UI/API mas não produz o efeito que o nome
promete.

## Por que não foi corrigido silenciosamente pelos agentes da F10

Protocolo do PCF da F10 (§9, proibição 4): *"Não reescreva nem duplique
lógica de F4... Se a assinatura de um módulo de F4 não bastar, é RFC — não
invente um segundo caminho."* `apurar_dia` é ownership de F4 (já commitada,
`6350709`), e o comportamento atual é **deliberado e documentado**, não um
descuido óbvio — corrigi-lo exige uma decisão de design (que efeito exato dar
à categoria `afastamento`: zerar `falta_minutos` como `abono`? um resultado
distinto de `'abonado'` para distinguir na apuração/relatórios/AFD que a
origem foi um afastamento e não um abono documental? como isso se relaciona
com `ApuracaoDia.resultado` e com o que F12 vai precisar emitir no AFD?).
Isso é decisão de arquitetura, não bug óbvio — corretamente escalada em vez
de "corrigida" por um agente sem visibilidade sobre F11/F12.

## Decisão

**A F10 é aceita e commitada com este débito técnico registrado
formalmente.**

1. O critério de aceite 6 do PCF da F10 (materialização correta por
   categoria) fica marcado como **parcialmente atendido**: a linha
   `afastamento` (retroativo) da tabela §2.2 cria e aprova o `Tratamento`
   corretamente (auditável, reversível, testado por A4 —
   `tests/f10/afastamentos_workflow/test_abono_e_retroativo.py`), mas **não**
   altera `apuracoes_dia`/`apuracao_componentes` como o nome do tipo de
   tratamento sugere. Não escondido, não reclassificado como "atendido com
   ressalva".
2. Nenhuma mudança foi feita em `apurar_dia` para mitigar isto agora — o
   comportamento entregue pela F10 é exatamente o que F4 já produzia.
3. Direção provável para quando isto for corrigido (não implementada agora,
   só registrada): estender `_carregar_marcacoes_e_tratamentos` com uma
   quarta categoria tratada (`afastamento`), decidindo primeiro se o efeito é
   idêntico a `abono_dia_inteiro` ou se precisa de um resultado distinto em
   `ApuracaoDia.resultado`/`ApuracaoComponente` para reportar corretamente no
   AFD (F12) a diferença entre "abonado por documento" e "afastamento
   retroativo aprovado" — essa distinção semântica deve ser decidida junto
   com quem planejar F12, não isoladamente aqui.
4. Até a correção, o backlog (`docs/backlog.md`, achado de A4/T13, F10)
   permanece como o rastreamento operacional do problema; este ADR é a fonte
   de verdade sobre a causa raiz e o porquê de não ter sido corrigido nesta
   fase.

## Alternativas consideradas

**Corrigir agora, tratando `afastamento` igual a `abono_dia_inteiro`.**
Resolveria o sintoma imediato (falta some da apuração), mas arriscaria
inventar uma regra sem base — nada no PCF da F10 nem no schema distingue os
dois resultados esperados para relatórios/AFD, e mudar `apurar_dia` sem
reverificar os critérios de aceite de F4 (17 critérios, já committados)
exigiria reabrir uma fase fechada por uma decisão de design que este
orquestrador não tem informação suficiente para tomar sozinho sem also
considerar F12 (AFD/AEJ), que ainda não foi planejada. Descartada por ora.

**Bloquear o fechamento da F10 até uma RFC decidir o efeito exato.**
Alongaria uma fase já extensa (4 agentes, MinIO, RFC-014) por uma lacuna que
não compromete os outros 14 critérios de aceite nem introduz dado incorreto
no banco (o `Tratamento` fica corretamente registrado, auditável e
reversível — só não produz o efeito automático esperado). Descartada: o
mesmo padrão da ADR-010 (aceitar o débito, registrar com precisão, seguir em
frente) se aplica aqui.

## Consequências

**Positivas.** A F10 fecha sem bloquear F11/F12 por uma decisão de design que
depende de conhecer os requisitos exatos de AFD/AEJ (F12) — decidir agora,
sem esse contexto, arriscaria a mesma inconsistência que a F10 já encontrou
(uma suposição do PCF que não bateu com F4). O achado fica com causa raiz
identificada (linha exata do código, linha exata do docstring que já avisava)
em vez de "parece que não funciona".

**Negativas e mitigações.** (a) Hoje, aprovar uma solicitação de tipo
`afastamento` (retroativo) no ambiente real não muda a falta do colaborador
na apuração nem no espelho — mitigação recomendada até a correção: RH deve
usar o tipo `abono_falta` (que já tem efeito numérico completo, via
categoria `abono`) para qualquer correção retroativa que precise zerar falta,
e tratar `afastamento` (retroativo) como registro administrativo/de
auditoria até a lacuna ser fechada; comunicar isso como limitação
operacional conhecida. (b) F11 (relatórios) e F12 (AFD/AEJ) vão expor este
mesmo dado — quem planejar essas fases deve ler este ADR antes de assumir que
toda solicitação de afastamento aprovada já reflete corretamente na apuração.
(c) O teste de A4 (`test_abono_e_retroativo.py`) documenta o comportamento
real (não fabrica um "efeito" que não existe) — deve ser revisitado e
estendido, não substituído, quando a correção acontecer.
