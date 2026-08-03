"""T3 -- `app.comum.idempotencia_generica` (F13/A1).

Prova as três semânticas do catálogo (`PONTO-IDEM-001/002/003`) chamando
`abrir_operacao`/`concluir_operacao` diretamente contra o banco real (sem
precisar de uma rota HTTP montada) -- o mesmo espírito de teste direto que
`app.marcacao.pipeline.idempotencia` (F5) já usa para o próprio mecanismo
que este módulo generaliza.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.comum.idempotencia_generica import (
    ChaveIdempotencia,
    abrir_operacao,
    concluir_operacao,
)
from app.core.erros import ErroDeAplicacao
from tests.f13.conftest import ContextoF13, aplicar_tenant_teste


def _chave(valor: str, corpo: str = "corpo-a") -> ChaveIdempotencia:
    import hashlib

    return ChaveIdempotencia(valor=valor, corpo_hash=hashlib.sha256(corpo.encode()).hexdigest())


async def test_primeira_chamada_prossegue_e_conclusao_fica_disponivel_para_replay(
    sessao_f13, contexto_f13: ContextoF13
) -> None:
    chave = _chave("op-1")
    resultado = await abrir_operacao(
        sessao_f13, tenant_id=contexto_f13.tenant_id, escopo="teste", chave=chave
    )
    assert resultado.ja_concluido is False

    await concluir_operacao(
        sessao_f13,
        registro_id=resultado.registro_id,
        status_http=201,
        corpo_resposta={"ok": True},
    )
    await sessao_f13.commit()
    await aplicar_tenant_teste(sessao_f13, contexto_f13.tenant_id)

    replay = await abrir_operacao(
        sessao_f13, tenant_id=contexto_f13.tenant_id, escopo="teste", chave=chave
    )
    assert replay.ja_concluido is True
    assert replay.resposta_status == 201
    assert replay.resposta_corpo == {"ok": True}


async def test_mesma_chave_corpo_diferente_responde_idem_002(
    sessao_f13, contexto_f13: ContextoF13
) -> None:
    chave_a = _chave("op-2", corpo="corpo-a")
    resultado = await abrir_operacao(
        sessao_f13, tenant_id=contexto_f13.tenant_id, escopo="teste", chave=chave_a
    )
    await concluir_operacao(
        sessao_f13, registro_id=resultado.registro_id, status_http=200, corpo_resposta={}
    )
    await sessao_f13.commit()
    await aplicar_tenant_teste(sessao_f13, contexto_f13.tenant_id)

    chave_b = _chave("op-2", corpo="corpo-b")
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await abrir_operacao(
            sessao_f13, tenant_id=contexto_f13.tenant_id, escopo="teste", chave=chave_b
        )
    assert excinfo.value.codigo == "PONTO-IDEM-002"


async def test_requisicao_concorrente_responde_idem_003(
    engine_f13, contexto_f13: ContextoF13
) -> None:
    """Duas TRANSAÇÕES concorrentes com a mesma chave: a segunda, ainda com
    a primeira em voo (sem commit), recebe `PONTO-IDEM-003` na hora --
    prova a trava consultiva (`pg_try_advisory_xact_lock`), não uma
    verificação sequencial de linha já commitada."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    fabrica = async_sessionmaker(engine_f13, expire_on_commit=False, autoflush=False)
    chave = _chave("op-concorrente")

    async with fabrica() as sessao_a, fabrica() as sessao_b:
        await aplicar_tenant_teste(sessao_a, contexto_f13.tenant_id)
        await aplicar_tenant_teste(sessao_b, contexto_f13.tenant_id)
        try:
            # `sessao_a` obtem a trava e NUNCA comita nesta chamada -- segura
            # a transacao aberta de proposito, simulando a operacao "em voo".
            resultado_a = await abrir_operacao(
                sessao_a, tenant_id=contexto_f13.tenant_id, escopo="teste", chave=chave
            )
            assert resultado_a.ja_concluido is False

            with pytest.raises(ErroDeAplicacao) as excinfo:
                await abrir_operacao(
                    sessao_b, tenant_id=contexto_f13.tenant_id, escopo="teste", chave=chave
                )
            assert excinfo.value.codigo == "PONTO-IDEM-003"
            assert excinfo.value.cabecalhos.get("Retry-After")
        finally:
            await sessao_a.rollback()
            await sessao_b.rollback()


async def test_falha_no_meio_libera_a_chave_para_nova_tentativa(
    sessao_f13, contexto_f13: ContextoF13
) -> None:
    """Uma tentativa que nunca chega a `concluir_operacao` e cuja transação
    sofre ROLLBACK não deixa rastro -- a mesma chave pode ser usada de novo
    (inclusive com corpo diferente), porque não houve operação concluída
    para proteger (ver docstring do módulo)."""
    chave = _chave("op-3", corpo="tentativa-1")
    await abrir_operacao(sessao_f13, tenant_id=contexto_f13.tenant_id, escopo="teste", chave=chave)
    await sessao_f13.rollback()
    await aplicar_tenant_teste(sessao_f13, contexto_f13.tenant_id)

    chave_novo_corpo = _chave("op-3", corpo="tentativa-2-corpo-diferente")
    resultado = await abrir_operacao(
        sessao_f13, tenant_id=contexto_f13.tenant_id, escopo="teste", chave=chave_novo_corpo
    )
    assert resultado.ja_concluido is False


async def test_chave_expirada_fica_livre_para_operacao_nova(
    sessao_f13, contexto_f13: ContextoF13
) -> None:
    """`PONTO-IDEM-002` só vale "nas últimas 24 horas" (texto do catálogo);
    uma linha expirada é tratada como inexistente, mesmo com corpo
    diferente."""
    chave_a = _chave("op-4", corpo="corpo-a")
    resultado = await abrir_operacao(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        escopo="teste",
        chave=chave_a,
        agora=dt.datetime.now(dt.UTC) - dt.timedelta(hours=25),
    )
    await concluir_operacao(
        sessao_f13, registro_id=resultado.registro_id, status_http=200, corpo_resposta={}
    )
    await sessao_f13.commit()
    await aplicar_tenant_teste(sessao_f13, contexto_f13.tenant_id)

    chave_b = _chave("op-4", corpo="corpo-completamente-diferente")
    resultado_novo = await abrir_operacao(
        sessao_f13, tenant_id=contexto_f13.tenant_id, escopo="teste", chave=chave_b
    )
    assert resultado_novo.ja_concluido is False


async def test_escopos_diferentes_nunca_colidem(sessao_f13, contexto_f13: ContextoF13) -> None:
    """A mesma string de `Idempotency-Key`, em dois escopos (operações)
    diferentes, são chaves independentes -- nunca IDEM-002 uma com a
    outra."""
    chave = _chave("op-compartilhada", corpo="corpo-x")
    resultado_a = await abrir_operacao(
        sessao_f13, tenant_id=contexto_f13.tenant_id, escopo="criarWebhook", chave=chave
    )
    resultado_b = await abrir_operacao(
        sessao_f13, tenant_id=contexto_f13.tenant_id, escopo="criarApiKey", chave=chave
    )
    assert resultado_a.registro_id != resultado_b.registro_id


async def test_exigir_idempotencia_extrai_chave_e_hash_do_corpo() -> None:
    """`Depends(exigir_idempotencia())` -- a parte pura leitura de
    cabeçalho/corpo, chamada como função simples (sem passar pelo FastAPI)."""
    from starlette.requests import Request

    from app.comum.idempotencia_generica import exigir_idempotencia

    corpo = b'{"a": 1}'

    async def _receive() -> dict[str, object]:
        return {"type": "http.request", "body": corpo, "more_body": False}

    scope = {"type": "http", "headers": [], "method": "POST", "path": "/v1/teste"}
    requisicao = Request(scope, _receive)

    dependencia = exigir_idempotencia()
    resultado = await dependencia(request=requisicao, idempotency_key="minha-chave")
    assert resultado.valor == "minha-chave"

    import hashlib

    assert resultado.corpo_hash == hashlib.sha256(corpo).hexdigest()


async def test_exigir_idempotencia_sem_cabecalho_responde_idem_001() -> None:
    from starlette.requests import Request

    from app.comum.idempotencia_generica import exigir_idempotencia

    async def _receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"{}", "more_body": False}

    scope = {"type": "http", "headers": [], "method": "POST", "path": "/v1/teste"}
    requisicao = Request(scope, _receive)

    dependencia = exigir_idempotencia()
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await dependencia(request=requisicao, idempotency_key=None)
    assert excinfo.value.codigo == "PONTO-IDEM-001"
