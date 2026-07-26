"""Dominio PESSOAS da fase F2: colaboradores, contratos, vinculos, hierarquia
de gestores e os eventos de admissao e desligamento.

Fronteira que o glossario fixa (ver `packages/contracts/glossario.md`, secao
3.2) e que este pacote nunca borra:

* `colaboradores` e a PESSOA -- dados cadastrais e pessoais.
* `contratos` e o INSTRUMENTO JURIDICO -- tipo de contratacao, cargo, salario,
  carga contratada, a clausula do art. 62 da CLT.
* `vinculos` e a RELACAO DE TRABALHO operacional, na granularidade que o
  eSocial e o AEJ exigem. **Todo o motor de apuracao das fases seguintes
  pendura em `vinculo_id`, nunca em `colaborador_id`.**

Ownership exclusivo do agente A2 da fase F2 (ver PCF
`docs/fases/F02-cadastros-organizacionais-pessoas.md`, secao 5).
"""

from __future__ import annotations
