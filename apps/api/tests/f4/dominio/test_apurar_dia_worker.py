"""Reparo do agente A1: prova que `worker.tarefas.apuracao.apurar_dia` (o
wrapper ARQ que a fila `apuracao` de fato chama) persiste `apuracoes_dia`
contra banco de teste -- nao so a funcao de dominio que ele chama por baixo
(`app.apuracao.dominio.servico.apurar_dia`, ja coberta linha a linha pelo
golden dataset em `tests/f4/golden/` e por `test_consulta.py` deste mesmo
diretorio).

Roda `worker.tarefas.apuracao` a partir de `apps/api/tests` -- mesmo padrao
de `tests/f2/importadores/test_worker_tarefa.py` (F2) e de
`tests/f4/banco_horas/test_vencimento.py` (F4/A2): o venv de `apps/api`
instala `ponto-worker` em modo editavel, entao `import worker` funciona
daqui. `apps/worker/.venv` (o venv ISOLADO por app) nao tem `ponto-api`
instalado -- ver achado no relatorio da fase.

`worker.tarefas.apuracao.apurar_dia` abre a PROPRIA sessao (via
`app.db.sessao.fabrica_de_sessoes()`, engine cacheada no processo) em vez de
reusar `sessao_tratamento` deste modulo -- por isso aponta `DATABASE_URL`
para a MESMA role de LOGIN da fixture (RLS, nunca superusuario -- ADR-001),
mesmo padrao de `ambiente_worker_banco_horas` em `test_vencimento.py`, e
confirma o resultado consultando de volta pela sessao do teste (o commit do
worker ja tornou a linha visivel para qualquer outra sessao do mesmo banco).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
import sqlalchemy as sa
from ponto_contracts import ApuracaoDia as ApuracaoDiaOrm
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession

from tests.f4.tratamento.conftest import ContextoTratamento

_DATA_APURADA = "2026-02-10"


@pytest.fixture
def ambiente_app_apontado_para_teste(
    url_login_sessao_tratamento: URL, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Aponta `app.core.config.Configuracao` (`DATABASE_URL`) para o mesmo
    banco de teste desta fase, autenticado como a MESMA role de LOGIN --
    mesmo padrao de `ambiente_worker_banco_horas`
    (`tests/f4/banco_horas/test_vencimento.py`, F4/A2).

    `monkeypatch.setenv` (nunca `os.environ[...] =` direto) e reset da
    engine cacheada de `app.db.sessao` (achado do orquestrador no fechamento
    da F13, ao rodar `tests/f4` combinado com outras fases pela primeira
    vez -- nunca reproduz com este arquivo isolado): sem os dois, (1)
    `DATABASE_URL` vazava para qualquer teste que rodasse depois no mesmo
    processo (mesma classe de bug ja corrigida em `tests/f13/sso/oidc/
    conftest.py`/`tests/f13/webhooks/conftest.py`); e (2)
    `worker.tarefas.apuracao.apurar_dia` reusa a engine cacheada de
    `app.db.sessao` (docstring do modulo) -- se essa engine ja existia,
    criada por um teste ANTERIOR e presa ao event loop JA FECHADO dele
    (`pytest-asyncio`, escopo `function`, um loop novo por teste), o
    checkout de conexao deste teste falha com `RuntimeError: Event loop is
    closed`, mesmo padrao ja documentado e corrigido em
    `tests/f13/sso/oidc/test_router_fluxo_completo.py::
    _engine_da_app_no_loop_do_teste`."""
    from app.core.config import obter_configuracao
    from app.db import sessao as db_sessao

    monkeypatch.setenv(
        "DATABASE_URL", url_login_sessao_tratamento.render_as_string(hide_password=False)
    )
    obter_configuracao.cache_clear()
    db_sessao._engine = None
    db_sessao._fabrica = None


@pytest.mark.asyncio
async def test_apurar_dia_worker_persiste_apuracao_dia(
    sessao_tratamento: AsyncSession,
    contexto_tratamento: ContextoTratamento,
    ambiente_app_apontado_para_teste: None,
) -> None:
    from worker.tarefas.apuracao import apurar_dia as apurar_dia_worker

    ctx: dict[str, Any] = {"job_id": "teste-reparo-a1", "job_try": 1}

    resultado = await apurar_dia_worker(
        ctx,
        tenant_id=str(contexto_tratamento.tenant_id),
        vinculo_id=str(contexto_tratamento.vinculo_id),
        data=_DATA_APURADA,
        motivo="teste de integracao (reparo A1)",
    )

    assert resultado["implementado"] is True
    assert resultado["tipoDia"] == "nao_apurado"
    assert resultado["status"] == "com_ocorrencia"
    assert resultado["apuracaoId"] is not None

    apuracao_id = UUID(resultado["apuracaoId"])
    linha = (
        await sessao_tratamento.execute(
            sa.select(ApuracaoDiaOrm).where(ApuracaoDiaOrm.id == apuracao_id)
        )
    ).scalar_one()
    assert linha.tenant_id == contexto_tratamento.tenant_id
    assert linha.vinculo_id == contexto_tratamento.vinculo_id
    assert linha.data.isoformat() == _DATA_APURADA
    assert linha.tipo_dia == "nao_apurado"
