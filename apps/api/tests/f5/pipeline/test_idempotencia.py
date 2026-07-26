"""T5 -- idempotencia de quatro chaves (`app.marcacao.pipeline.idempotencia`)."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.marcacao.dominio.registro import DadosMarcacao, persistir_marcacao
from app.marcacao.pipeline import idempotencia
from tests.f5.conftest import ContextoF5, aplicar_tenant_teste


def _dados(contexto: ContextoF5, *, external_id: str) -> DadosMarcacao:
    return DadosMarcacao(
        rep_p_id=contexto.rep_p_id,
        empresa_id=contexto.empresa_id,
        cpf=contexto.colaborador_cpf,
        canal="api",
        datahora_marcacao=dt.datetime.now(tz=dt.UTC),
        unidade_id=contexto.unidade_id,
        colaborador_id=contexto.colaborador_id,
        vinculo_id=contexto.vinculo_id,
        external_id=external_id,
    )


def test_calcular_hash_identidade_e_estavel() -> None:
    campos: dict[str, object] = {
        "colaborador_id": uuid.uuid4(),
        "empresa_id": uuid.uuid4(),
        "unidade_id": uuid.uuid4(),
        "canal": "api",
        "dispositivo_id": None,
        "terminal_id": None,
        "sentido_informado": None,
        "cpf": "12345678901",
        "external_id": "ext-1",
        "log_externo_id": None,
    }
    hash_a = idempotencia.calcular_hash_identidade(**campos)  # type: ignore[arg-type]
    hash_b = idempotencia.calcular_hash_identidade(**campos)  # type: ignore[arg-type]
    assert hash_a == hash_b
    assert len(hash_a) == 64


def test_calcular_hash_identidade_muda_com_qualquer_campo() -> None:
    base: dict[str, object] = {
        "colaborador_id": uuid.uuid4(),
        "empresa_id": uuid.uuid4(),
        "unidade_id": None,
        "canal": "api",
        "dispositivo_id": None,
        "terminal_id": None,
        "sentido_informado": None,
        "cpf": "12345678901",
        "external_id": "ext-1",
        "log_externo_id": None,
    }
    hash_base = idempotencia.calcular_hash_identidade(**base)  # type: ignore[arg-type]
    variado = dict(base, external_id="ext-2")
    assert idempotencia.calcular_hash_identidade(**variado) != hash_base  # type: ignore[arg-type]
    variado_canal = dict(base, canal="web")
    assert idempotencia.calcular_hash_identidade(**variado_canal) != hash_base  # type: ignore[arg-type]


def test_chave_helpers_formam_o_par_esperado() -> None:
    dispositivo_id = uuid.uuid4()
    assert idempotencia.chave_external_id("api", "ext-42") == "api:ext-42"
    assert idempotencia.chave_dispositivo_log(dispositivo_id, 7) == f"{dispositivo_id}:7"
    assert idempotencia.chave_offline_hmac(dispositivo_id, "abc") == f"{dispositivo_id}:abc"
    assert idempotencia.chave_idempotency_key("chave-x") == "chave-x"


async def test_registrar_e_buscar_chave_por_escopo(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    dados = _dados(contexto_f5, external_id="ext-idem-1")
    marcacao = await persistir_marcacao(sessao_f5, tenant_id=contexto_f5.tenant_id, dados=dados)
    await sessao_f5.flush()

    chave = idempotencia.chave_idempotency_key("01JZIDEMTESTE0001")
    await idempotencia.registrar_chave(
        sessao_f5,
        tenant_id=contexto_f5.tenant_id,
        escopo=idempotencia.ESCOPO_IDEMPOTENCY_KEY,
        chave=chave,
        marcacao_id=marcacao.id,
        datahora_marcacao=marcacao.datahora_marcacao,
    )

    encontrada = await idempotencia.buscar_marcacao_por_chave(
        sessao_f5,
        tenant_id=contexto_f5.tenant_id,
        escopo=idempotencia.ESCOPO_IDEMPOTENCY_KEY,
        chave=chave,
    )
    assert encontrada is not None
    assert encontrada.id == marcacao.id
    assert idempotencia.hash_identidade_da_marcacao(
        encontrada
    ) == idempotencia.calcular_hash_identidade(
        colaborador_id=marcacao.colaborador_id,
        empresa_id=marcacao.empresa_id,
        unidade_id=marcacao.unidade_id,
        canal=marcacao.canal,
        dispositivo_id=marcacao.dispositivo_id,
        terminal_id=marcacao.terminal_id,
        sentido_informado=marcacao.sentido_informado,
        cpf=marcacao.cpf,
        external_id=marcacao.external_id,
        log_externo_id=marcacao.log_externo_id,
    )

    ausente = await idempotencia.buscar_marcacao_por_chave(
        sessao_f5,
        tenant_id=contexto_f5.tenant_id,
        escopo=idempotencia.ESCOPO_EXTERNAL_ID,
        chave="api:nao-existe",
    )
    assert ausente is None


async def test_registrar_chave_duplicada_no_mesmo_escopo_e_recusada(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    dados_1 = _dados(contexto_f5, external_id="ext-idem-dup-1")
    marcacao_1 = await persistir_marcacao(sessao_f5, tenant_id=contexto_f5.tenant_id, dados=dados_1)
    await sessao_f5.flush()
    dados_2 = _dados(contexto_f5, external_id="ext-idem-dup-2")
    marcacao_2 = await persistir_marcacao(sessao_f5, tenant_id=contexto_f5.tenant_id, dados=dados_2)
    await sessao_f5.flush()

    chave = idempotencia.chave_external_id("api", "mesma-chave-de-dominio")
    await idempotencia.registrar_chave(
        sessao_f5,
        tenant_id=contexto_f5.tenant_id,
        escopo=idempotencia.ESCOPO_EXTERNAL_ID,
        chave=chave,
        marcacao_id=marcacao_1.id,
        datahora_marcacao=marcacao_1.datahora_marcacao,
    )
    with pytest.raises(Exception) as excinfo:
        await idempotencia.registrar_chave(
            sessao_f5,
            tenant_id=contexto_f5.tenant_id,
            escopo=idempotencia.ESCOPO_EXTERNAL_ID,
            chave=chave,
            marcacao_id=marcacao_2.id,
            datahora_marcacao=marcacao_2.datahora_marcacao,
        )
    assert getattr(excinfo.value, "codigo", None) == "PONTO-MARC-003"


async def test_travar_idempotency_key_bloqueia_chamada_concorrente(
    engine_f5: AsyncEngine, contexto_f5: ContextoF5
) -> None:
    """Duas transacoes distintas disputando a MESMA `Idempotency-Key`: a
    primeira obtem o lock consultivo, a segunda falha enquanto a primeira
    nao commita nem faz rollback (`PONTO-IDEM-003`, do lado de quem chama)."""
    fabrica = async_sessionmaker(engine_f5, expire_on_commit=False, autoflush=False)
    chave = "chave-em-voo-concorrente"
    async with fabrica() as sessao_a, fabrica() as sessao_b:
        await aplicar_tenant_teste(sessao_a, contexto_f5.tenant_id)
        await aplicar_tenant_teste(sessao_b, contexto_f5.tenant_id)

        obteve_a = await idempotencia.travar_idempotency_key(
            sessao_a, tenant_id=contexto_f5.tenant_id, idempotency_key=chave
        )
        obteve_b = await idempotencia.travar_idempotency_key(
            sessao_b, tenant_id=contexto_f5.tenant_id, idempotency_key=chave
        )
        assert obteve_a is True
        assert obteve_b is False

        await sessao_a.rollback()
        await sessao_b.rollback()
