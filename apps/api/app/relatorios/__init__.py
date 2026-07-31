"""Motor de relatorios (F11).

Implementa a tag `relatorios` de `packages/contracts/openapi.yaml`: seis
operacoes HTTP (mais os dois endpoints de preferencias de colunas da
RFC-015), executando um catalogo de 24 relatorios semeados por tenant em
`relatorio_definicoes` (`schema.sql` secao 16) atraves de um motor generico
unico -- nunca 24 rotas, 24 linhas de catalogo mais 24 funcoes de consulta
registradas num dicionario interno (`catalogo.py`).

Ownership dos modulos deste pacote (PCF F11 §5):

* `motor.py`, `catalogo.py`, `execucao.py`, `preferencias.py`, `paginacao.py`
  -- A1 (T1-T3), esta fase.
* `datasets/operacionais.py` -- A2 (T7/T8), relatorios 2-12.
* `datasets/gerenciais.py`, `exportadores/**`, `agendamentos.py`,
  `entrega/{email,webhook,minio}.py` -- A3 (T5/T9/T10/T11).
* `datasets/espelho_oficial.py`, `entrega/espelho_email.py` -- A4 (T12/T13).

Regra que vale para TODO modulo deste pacote (proibicao 1, PCF §9): nenhuma
funcao aqui chama `app.apuracao.dominio.servico.apurar_dia` nem
`app.apuracao.tratamento.recalculo.recalcular_periodo`, nem qualquer codigo
que dispare o resolvedor de jornada de F3. Um relatorio so LE o que ja foi
apurado -- ver ADR-004/ADR-010 e PCF §2.3.
"""

from __future__ import annotations
