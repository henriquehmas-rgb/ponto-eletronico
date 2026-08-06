"""Motor de composicao do score de confianca antifraude (F14/A1, ADR-008).

Territorio exclusivo de A1 (PCF F14 secao 3). Este pacote NUNCA importa nem e
importado por `app.marcacao.dominio.registro`/`app.marcacao.dominio.nsr`
(logica de NSR/hash de F5, travada) -- o unico ponto de integracao com o
pipeline de marcacao e `app.marcacao.pipeline.ingestao`, que chama as funcoes
publicas deste pacote depois que a marcacao ja passou pelos gates legais
(vinculo, REP-P, geocerca dura, rede) e antes de persistir.

Modulos:

* `politicas.py` -- `PoliticaAntifraude`/`PesosScore`: leitura de
  `politicas_registro` (incluindo os pesos acrescentados pela migration
  `0003_antifraude_pesos_score`) num formato pronto para o motor.
* `reputacao.py` -- reputacao de dispositivo por estado conhecido +
  historico de marcacoes suspeitas do mesmo aparelho.
* `geografia.py` -- coerencia geografica e velocidade implicita entre a
  marcacao atual e a anterior do mesmo colaborador.
* `motor.py` -- `compor_score`: composicao ponderada + sinais decisivos
  (ADR-008 regra 7) + explicabilidade.
* `fila.py` -- fila de revisao do gestor (leitura/decisao sobre
  `marcacoes_meta.revisao_status`, sem mecanismo de fila novo -- ver
  docstring do modulo sobre por que o motor de aprovacao de F10 nao serve).
"""

from __future__ import annotations
