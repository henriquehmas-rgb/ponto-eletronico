"""Fixture local dos testes de `apuracao.dominio` que precisam de banco real
(reparo do agente A1 -- ver `docs/fases/F04-calculo-banco-de-horas.md`).

Reusa as fixtures ja estabelecidas por `tests/f4/tratamento/conftest.py`
(A3 -- role de LOGIN + engine + sessao sob RLS, e a semente minima de 1
tenant/1 empresa/1 unidade/1 colaborador/1 vinculo `apura_ponto=true`, SEM
jornada) em vez de duplicar o bootstrap inteiro (ja replicado em tres
modulos desta fase: `tests/f4/tratamento`, `tests/f4/banco_horas`,
`tests/f4/propriedade`). Mesma decisao de desenho documentada por
`tests/f4/golden/conftest.py` ao reusar `tests/f3/conftest.py`:
reexportacao via `import X as X` (convencao PEP 484 de reexportacao
explicita que o proprio `ruff` reconhece, entao nao acusa como import nao
usado) -- nunca copia do arquivo alheio. `tests/f4/tratamento/**` continua
ownership exclusivo de A3; nenhuma linha dele e tocada por este modulo.

Vinculo sem jornada/escala vigente e exatamente o que os testes deste
modulo precisam: faz `app.apuracao.dominio.servico.apurar_dia` cair no ramo
`PONTO-APUR-002` (`_gravar_nao_apurado`), que grava uma linha real em
`apuracoes_dia` e abre uma `ocorrencia` sem depender da massa de jornada da
F3 -- essa outra combinacao (jornada real, zero marcacoes) ja e coberta
pelo golden dataset em `tests/f4/golden/`.
"""

from __future__ import annotations

from tests.f4.tratamento.conftest import ContextoTratamento as ContextoTratamento
from tests.f4.tratamento.conftest import aplicar_tenant_teste as aplicar_tenant_teste
from tests.f4.tratamento.conftest import contexto_tratamento as contexto_tratamento
from tests.f4.tratamento.conftest import engine_tratamento as engine_tratamento
from tests.f4.tratamento.conftest import sessao_tratamento as sessao_tratamento
from tests.f4.tratamento.conftest import url_login_sessao_tratamento as url_login_sessao_tratamento
