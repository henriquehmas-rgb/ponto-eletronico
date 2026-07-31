"""`app.relatorios.entrega.{email,webhook,minio}` (F11, T11/A3).

Instancia `RelatorioExecucao`/`RelatorioAgendamento` (SQLAlchemy) diretamente
em memoria, sem sessao/banco: os tres canais so leem atributos (nunca
consultam o banco), e instanciar o model real (em vez de um stand-in solto)
mantem o teste sob o mesmo tipo que o mypy --strict verifica, sem perder a
independencia da fixture de banco de A1 (`conftest.py`, T1).
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import uuid4

import httpx
import pytest
from ponto_contracts import RelatorioAgendamento, RelatorioExecucao

from app.relatorios.entrega import email as canal_email
from app.relatorios.entrega import minio as canal_minio
from app.relatorios.entrega import webhook as canal_webhook


def _execucao(**sobrescreve: Any) -> RelatorioExecucao:
    base: dict[str, Any] = {
        "id": uuid4(),
        "relatorio_definicao_id": uuid4(),
        "formato": "xlsx",
        "status": "concluido",
        "total_linhas": 42,
        "tamanho_bytes": 1024,
        "hash_sha256": "a" * 64,
        "conteudo_ref": "relatorios/2026-08/exemplo.xlsx",
        "concluido_em": dt.datetime(2026, 8, 1, tzinfo=dt.UTC),
    }
    base.update(sobrescreve)
    return RelatorioExecucao(**base)


def _agendamento(**sobrescreve: Any) -> RelatorioAgendamento:
    base: dict[str, Any] = {
        "id": uuid4(),
        "destinatarios": ["rh@exemplo.com"],
        "canal": "email",
    }
    base.update(sobrescreve)
    return RelatorioAgendamento(**base)


# --- email ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_email_entrega_com_destinatarios() -> None:
    execucao = _execucao()
    agendamento = _agendamento(destinatarios=["rh@exemplo.com", "diretoria@exemplo.com"])
    assert await canal_email.entregar(execucao, agendamento) is True


@pytest.mark.asyncio
async def test_email_sem_destinatarios_falha_sem_levantar() -> None:
    execucao = _execucao()
    agendamento = _agendamento(destinatarios=[])
    assert await canal_email.entregar(execucao, agendamento) is False


# --- webhook ------------------------------------------------------------------


class _RespostaFalsa:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "erro",
                request=httpx.Request("POST", "https://exemplo.com"),
                response=None,  # type: ignore[arg-type]
            )


@pytest.mark.asyncio
async def test_webhook_entrega_com_payload_correto(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas: list[tuple[str, dict[str, object]]] = []

    class _ClienteFalso:
        async def __aenter__(self) -> _ClienteFalso:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(self, url: str, *, json: dict[str, object]) -> _RespostaFalsa:
            chamadas.append((url, json))
            return _RespostaFalsa(200)

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: _ClienteFalso())

    execucao = _execucao()
    agendamento = _agendamento(canal="webhook", destinatarios=["https://cliente.exemplo.com/hook"])
    assert await canal_webhook.entregar(execucao, agendamento) is True

    assert len(chamadas) == 1
    url, payload = chamadas[0]
    assert url == "https://cliente.exemplo.com/hook"
    assert payload["execucaoId"] == str(execucao.id)
    assert payload["agendamentoId"] == str(agendamento.id)
    assert payload["formato"] == "xlsx"
    assert payload["hashSha256"] == execucao.hash_sha256
    assert payload["conteudoRef"] == execucao.conteudo_ref


@pytest.mark.asyncio
async def test_webhook_falha_de_rede_devolve_falso_sem_levantar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ClienteFalso:
        async def __aenter__(self) -> _ClienteFalso:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(self, url: str, *, json: dict[str, object]) -> _RespostaFalsa:
            raise httpx.ConnectError("recusado", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: _ClienteFalso())

    execucao = _execucao()
    agendamento = _agendamento(canal="webhook", destinatarios=["https://fora-do-ar.exemplo.com"])
    assert await canal_webhook.entregar(execucao, agendamento) is False


@pytest.mark.asyncio
async def test_webhook_sem_destinatarios_falha_sem_levantar() -> None:
    execucao = _execucao()
    agendamento = _agendamento(canal="webhook", destinatarios=[])
    assert await canal_webhook.entregar(execucao, agendamento) is False


# --- minio ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_minio_confirma_objeto_real_quando_conteudo_ref_presente() -> None:
    execucao = _execucao(conteudo_ref="relatorios/2026-08/exemplo.xlsx")
    agendamento = _agendamento(canal="minio", destinatarios=[])
    assert await canal_minio.entregar(execucao, agendamento) is True


@pytest.mark.asyncio
async def test_minio_sem_conteudo_ref_falha_sem_levantar() -> None:
    execucao = _execucao(conteudo_ref=None)
    agendamento = _agendamento(canal="minio", destinatarios=[])
    assert await canal_minio.entregar(execucao, agendamento) is False
