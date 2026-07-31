"""Gerador do AEJ (Arquivo Eletronico de Jornada), F12/A2.

Diferente do AFD (`app.fiscal.afd`, A1), que deriva EXCLUSIVAMENTE das
marcacoes, o AEJ e quem ENXERGA tratamento, ausencia e banco de horas: alem
das marcacoes, carrega cabecalho, REPs utilizados, vinculos, horario
contratual, matricula eSocial (multiplos vinculos), ausencias, banco de
horas, identificacao do PTRP (Programa de Tratamento de Registro de Ponto) e
trailer (`docs/leiaute-afd-aej.md`, secao 9-10).

Modulos:

- `registros.py` (T8): builders puros, um por tipo de registro (01 a 08, 99,
  linha de assinatura), delimitados por `"|"` (nunca largura fixa -- isso e
  exclusivo do AFD). Nenhuma consulta a banco aqui.
- `eventos.py`: publica `aej.gerado` no barramento interno do dominio, mesmo
  padrao de `app.workflow.fechamento.eventos` (F10).
- `gerador.py` (T9): orquestra a consulta (vinculos, marcacoes, tratamentos,
  ausencias, banco de horas), monta o arquivo completo, reconcilia o bloco de
  banco de horas contra o extrato real de `app.apuracao.banco_horas.consulta`
  (F4, leitura) e grava `aej_arquivos`.

Este pacote **nunca** escreve em `marcacoes`, `apuracoes_dia`,
`apuracao_componentes`, `bh_lancamentos`, `bh_contas`, `tratamentos`,
`afastamentos`, `periodos` -- so leitura (PCF da fase, secao 4 e criterio de
aceite 7). Usa `app.fiscal.comum.formatos` (A1, T1) para formatacao de
data/data-hora e montagem do arquivo texto; nunca implementa CRC-16 (o AEJ
nao tem, PCF secao 2.9).
"""

from __future__ import annotations
