"""Fixture dos testes do golden dataset da F3 executado contra a apuracao
real (T11, agente A4).

**Decisao de desenho, documentada aqui e no relatorio da fase.** `Cenario.
montar` (`tests/f3/golden/formato.py`) tem o tipo `Callable[[AsyncSession,
"ContextoF3"], Awaitable[Montagem]]`: cada cenario grava jornada/escala/
turno/horario/feriado/afastamento usando os IDs especificos que `tests.f3.
conftest.ContextoF3` semeia (duas unidades em UFs diferentes, tres vinculos
com papeis fixos -- `vinculo_sp_id`, `vinculo_ba_id`,
`vinculo_sem_unidade_id`). Reproduzir esse contexto com uma fixture PROPRIA
seria recriar a massa da F3 nesta fase -- exatamente o que a T11 do PCF
proibe ("NAO recrie massa nova"). Este modulo, em vez disso, reusa as
fixtures de sessao/contexto de `tests/f3/conftest.py` diretamente via
`pytest_plugins`, o mecanismo padrao do pytest para compartilhar fixtures
entre pacotes de teste sem duplicar codigo nem editar o arquivo alheio
(`tests/f3/conftest.py` continua ownership exclusivo e ja concluido da F3;
nenhuma linha dele e tocada por este modulo).

Consequencia aceita e documentada: a role de LOGIN criada para estes testes
chama-se `ponto_f3_login_<nome_do_banco>` (formula de
`tests/f3/conftest.py::_nome_role_login`), nao `ponto_f4_login_<...>` como o
resto da fase -- e a MESMA role de LOGIN (nao-superusuario, sob RLS) contra
o MESMO banco `PONTO_TEST_DATABASE_URL` desta fase, so com um prefixo de
nome diferente porque o modulo de fixture reusado e o da F3. Nao afeta
isolamento nem seguranca: e uma role dedicada, criada (ou reaproveitada) no
banco exclusivo deste agente, nunca um superusuario.

**Nota tecnica:** `pytest_plugins` so e aceito em conftest de nivel raiz
(pytest >= 7 recusa a coleta se declarado num conftest nao-raiz, como este).
A reexportacao e feita importando as fixtures diretamente (`import X as X`,
convencao PEP 484 de reexportacao explicita que o proprio `ruff` reconhece
e por isso nao acusa como "unused import") -- mesmo efeito pratico de
`pytest_plugins`, sem a restricao de nivel: pytest descobre fixtures pelo
objeto marcado, nao importa se foi definido ou importado neste modulo.
"""

from __future__ import annotations

from tests.f3.conftest import ContextoF3 as ContextoF3
from tests.f3.conftest import aplicar_tenant_teste as aplicar_tenant_teste
from tests.f3.conftest import contexto_f3 as contexto_f3
from tests.f3.conftest import engine_f3 as engine_f3
from tests.f3.conftest import sessao_f3 as sessao_f3
from tests.f3.conftest import url_login_sessao as url_login_sessao
