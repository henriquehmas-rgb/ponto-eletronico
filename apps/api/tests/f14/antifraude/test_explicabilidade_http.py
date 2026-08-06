"""Aceite de A1: "explicabilidade gravada em `marcacoes_meta` sobrevive a
consulta por API". Este e o teste de ponta a ponta de verdade: `TestClient`
real contra `app.main:app` (mesmo padrao que `tests/f13/nucleo/
test_admin_api_keys.py` ja usa) -- `POST /v1/marcacoes` grava, `GET /v1/
marcacoes/{marcacaoId}/meta` le de volta pela API HTTP, nao por consulta
direta ao banco (essa cobertura fica em `test_pipeline_integracao.py`).

`app.dependency_overrides[obter_sujeito]` substitui a resolucao de RBAC por
um `Sujeito` fixo com as permissoes que este teste precisa
(`marcacoes.criar`/`marcacoes.ler_sensivel`) -- isolando "o motor de score e
a explicabilidade desta fase funcionam" de "o RBAC do F1 concede a permissao
certa" (ja coberto pela propria suite de F1).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager

import pytest_asyncio
from fastapi.testclient import TestClient

import app.db.sessao as _db_sessao
from app.core.seguranca import Sujeito, obter_sujeito
from tests.f14.antifraude.conftest import (
    GEOCERCA_LATITUDE,
    GEOCERCA_LONGITUDE,
    ContextoF14A1,
)


@pytest_asyncio.fixture(autouse=True)
async def _engine_global_isolada_por_teste() -> AsyncIterator[None]:
    """Mesmo padrao de `tests/f13/conftest.py::_engine_global_isolada_por_teste`
    (nao herdado automaticamente -- so aplica a arquivos sob `tests/f13/**`):
    zera a engine GLOBAL de `app.db.sessao` a cada teste para que o
    `TestClient` (que abre sessao pela fabrica singleton) nao reuse uma
    engine presa ao event loop de um teste anterior."""
    from app.core.config import obter_configuracao

    obter_configuracao.cache_clear()
    _db_sessao._engine = None  # type: ignore[attr-defined]
    _db_sessao._fabrica = None  # type: ignore[attr-defined]
    _db_sessao._engine_loop = None  # type: ignore[attr-defined]
    yield
    if _db_sessao._engine is not None:  # type: ignore[attr-defined]
        await _db_sessao.encerrar_engine()


def _sujeito_fixo(tenant_id: uuid.UUID, permissoes: set[str]):
    usuario_id = uuid.uuid4()

    async def _fake() -> Sujeito:
        return Sujeito(
            usuario_id=usuario_id,
            tenant_id=tenant_id,
            email="gestor-teste@exemplo.com.br",
            perfis=("teste",),
            permissoes=frozenset(permissoes),
            autenticado=True,
        )

    return _fake


@contextmanager
def _cliente_com_permissoes(tenant_id: uuid.UUID, permissoes: set[str]) -> Iterator[TestClient]:
    from app.main import app

    app.dependency_overrides[obter_sujeito] = _sujeito_fixo(tenant_id, permissoes)
    try:
        # `client=(...)`: o padrao de `starlette.testclient.TestClient` e
        # `("testclient", 50000)` -- `request.client.host` (usado sem
        # validacao por `app.routers.marcacoes.criar_marcacao` para popular
        # `marcacoes_meta.ip`, coluna `INET`) rejeita essa string com
        # `asyncpg.exceptions.DataError` (achado real, registrado em
        # `docs/backlog.md`: a rota confia em `request.client.host` sem
        # validar formato de IP -- fora do ownership de A1, mandato de A2/
        # "mecanismo de IP confiavel"). Um IP sintatico valido aqui e
        # workaround LEGITIMO do teste, nao contorno do achado.
        with TestClient(
            app, raise_server_exceptions=True, client=("203.0.113.77", 51000)
        ) as cliente:
            yield cliente
    finally:
        app.dependency_overrides.pop(obter_sujeito, None)


async def test_registrar_e_consultar_meta_por_http_explicabilidade_sobrevive(
    contexto_f14a1: ContextoF14A1,
) -> None:
    with _cliente_com_permissoes(
        contexto_f14a1.tenant_id, {"marcacoes.criar", "marcacoes.ler_sensivel"}
    ) as cliente:
        resposta_post = cliente.post(
            "/v1/marcacoes",
            json={
                "colaboradorId": str(contexto_f14a1.colaborador_id),
                "empresaId": str(contexto_f14a1.empresa_id),
                "unidadeId": str(contexto_f14a1.unidade_id),
                "canal": "mobile",
                "dispositivoId": str(contexto_f14a1.dispositivo_id),
                "latitude": GEOCERCA_LATITUDE,
                "longitude": GEOCERCA_LONGITUDE,
                "precisaoMetros": 5.0,
            },
            headers={
                "X-Tenant": contexto_f14a1.tenant_slug,
                "Idempotency-Key": str(uuid.uuid4()),
            },
        )
        assert resposta_post.status_code == 201, resposta_post.text
        corpo_post = resposta_post.json()
        marcacao_id = corpo_post["marcacao"]["id"]
        assert corpo_post["scoreConfianca"] is not None

        resposta_meta = cliente.get(
            f"/v1/marcacoes/{marcacao_id}/meta",
            headers={"X-Tenant": contexto_f14a1.tenant_slug},
        )
        assert resposta_meta.status_code == 200, resposta_meta.text
        meta = resposta_meta.json()
        bloco = meta["flagsIntegridade"]["_antifraude"]
        assert bloco["scoreExplicabilidade"], "explicabilidade vazia na resposta HTTP"
        sinais = {s["sinal"] for s in bloco["scoreExplicabilidade"]}
        assert "geocerca" in sinais
        assert bloco["limiarBloqueio"] == 40
        assert bloco["limiarRevisao"] == 70


async def test_sem_permissao_sensivel_nao_ve_explicabilidade(
    contexto_f14a1: ContextoF14A1,
) -> None:
    """`marcacoes.ler_sensivel` e permissao PROPRIA (docstring de
    `obterMetaMarcacao` no contrato) -- quem so tem `marcacoes.criar` nao
    consegue ler `flagsIntegridade`/explicabilidade pela API."""
    with _cliente_com_permissoes(contexto_f14a1.tenant_id, {"marcacoes.criar"}) as cliente_escrita:
        resposta_post = cliente_escrita.post(
            "/v1/marcacoes",
            json={
                "colaboradorId": str(contexto_f14a1.colaborador_id),
                "empresaId": str(contexto_f14a1.empresa_id),
                "unidadeId": str(contexto_f14a1.unidade_id),
                "canal": "mobile",
                "dispositivoId": str(contexto_f14a1.dispositivo_id),
                "latitude": GEOCERCA_LATITUDE,
                "longitude": GEOCERCA_LONGITUDE,
                "precisaoMetros": 5.0,
            },
            headers={
                "X-Tenant": contexto_f14a1.tenant_slug,
                "Idempotency-Key": str(uuid.uuid4()),
            },
        )
        assert resposta_post.status_code == 201, resposta_post.text
        marcacao_id = resposta_post.json()["marcacao"]["id"]

        resposta_meta = cliente_escrita.get(
            f"/v1/marcacoes/{marcacao_id}/meta",
            headers={"X-Tenant": contexto_f14a1.tenant_slug},
        )
        assert resposta_meta.status_code == 403, resposta_meta.text
        assert "detail" not in resposta_meta.json()
