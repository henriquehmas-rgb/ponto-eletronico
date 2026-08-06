"""A2 -- prova de ponta a ponta HTTP real de `IdempotenciaRetrofitMiddleware`
(`app/comum/idempotencia_middleware.py`) sobre `POST /v1/empresas`, uma das
rotas da amostra representativa de F1-F12 (F14/A2).

Contra a aplicação FastAPI real (`app.main.criar_aplicacao`) e o Postgres
real desta suíte -- "comprovado por teste real, não só existência do
Depends" (critério de aceite de A2). Autenticação por
`dependency_overrides[obter_sujeito]` (ver `conftest.py`).
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from ponto_contracts import Empresa
from sqlalchemy.ext.asyncio import AsyncSession

from tests.f14.hardening.conftest import (
    ContextoF14A2,
    cabecalhos,
    sobrescrever_sujeito,
    sujeito_de_teste,
)

pytestmark = pytest.mark.asyncio

_contador_cnpj = iter(range(1, 10_000_000))


def _digito_modulo_11(base: str, pesos: list[int]) -> int:
    soma = sum(int(d) * p for d, p in zip(base, pesos, strict=True))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def _gerar_cnpj_valido() -> str:
    """CNPJ com dígitos verificadores REAIS (mesmo algoritmo de
    `app.comum.documentos.cnpj_valido`, módulo 11) -- `POST /v1/empresas`
    valida checksum de verdade (`PONTO-VAL-003`), então um CNPJ aleatório
    "quase certo" (14 dígitos sem checksum) é rejeitado antes de chegar
    perto de idempotência nenhuma."""
    base = f"{next(_contador_cnpj):012d}"
    dv1 = _digito_modulo_11(base, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    dv2 = _digito_modulo_11(base + str(dv1), [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return f"{base}{dv1}{dv2}"


def _corpo_empresa(cnpj: str, razao_social: str) -> dict[str, object]:
    return {
        "cnpj": cnpj,
        "razaoSocial": razao_social,
        "municipio": "Goiania",
        "uf": "GO",
        "fusoHorario": "America/Sao_Paulo",
    }


async def _contar_empresas_com_cnpj(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, cnpj: str
) -> int:
    await sessao.execute(
        sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
    )
    resultado = await sessao.execute(
        sa.select(sa.func.count())
        .select_from(Empresa)
        .where(Empresa.tenant_id == tenant_id, Empresa.cnpj == cnpj)
    )
    return int(resultado.scalar_one())


async def test_replay_mesma_chave_mesmo_corpo_nao_reexecuta_e_devolve_resposta_armazenada(
    cliente_http_f14a2: AsyncClient, contexto_f14a2: ContextoF14A2, sessao_f14a2: AsyncSession
) -> None:
    sobrescrever_sujeito(
        cliente_http_f14a2,
        sujeito_de_teste(contexto_f14a2, permissoes=frozenset({"empresas.criar"})),
    )
    cnpj = _gerar_cnpj_valido()
    corpo = _corpo_empresa(cnpj, "Empresa Replay Ltda")
    chave = f"e2e-replay-{uuid.uuid4()}"

    resp1 = await cliente_http_f14a2.post(
        "/v1/empresas",
        json=corpo,
        headers=cabecalhos(contexto_f14a2.tenant_slug, idempotencia=chave),
    )
    assert resp1.status_code == 201, resp1.text
    assert resp1.headers.get("Idempotency-Replayed") == "false"
    corpo1 = resp1.json()

    resp2 = await cliente_http_f14a2.post(
        "/v1/empresas",
        json=corpo,
        headers=cabecalhos(contexto_f14a2.tenant_slug, idempotencia=chave),
    )
    assert resp2.status_code == 201, resp2.text
    assert resp2.headers.get("Idempotency-Replayed") == "true"
    corpo2 = resp2.json()
    assert corpo2["id"] == corpo1["id"], "replay deve devolver a MESMA empresa, não criar outra"

    # A prova real: só existe UMA linha em `empresas` com este CNPJ -- a
    # segunda chamada NUNCA executou `servico.criar_empresa`.
    total = await _contar_empresas_com_cnpj(
        sessao_f14a2, tenant_id=contexto_f14a2.tenant_id, cnpj=cnpj
    )
    assert total == 1


async def test_mesma_chave_corpo_diferente_e_409_idem_002(
    cliente_http_f14a2: AsyncClient, contexto_f14a2: ContextoF14A2
) -> None:
    sobrescrever_sujeito(
        cliente_http_f14a2,
        sujeito_de_teste(contexto_f14a2, permissoes=frozenset({"empresas.criar"})),
    )
    chave = f"e2e-conflito-{uuid.uuid4()}"
    cnpj1 = _gerar_cnpj_valido()
    cnpj2 = _gerar_cnpj_valido()

    resp1 = await cliente_http_f14a2.post(
        "/v1/empresas",
        json=_corpo_empresa(cnpj1, "Empresa Um"),
        headers=cabecalhos(contexto_f14a2.tenant_slug, idempotencia=chave),
    )
    assert resp1.status_code == 201, resp1.text

    resp2 = await cliente_http_f14a2.post(
        "/v1/empresas",
        json=_corpo_empresa(cnpj2, "Empresa Dois -- corpo diferente"),
        headers=cabecalhos(contexto_f14a2.tenant_slug, idempotencia=chave),
    )
    assert resp2.status_code == 409, resp2.text
    assert resp2.json()["codigo"] == "PONTO-IDEM-002"


async def test_idempotency_key_ausente_e_400_idem_001(
    cliente_http_f14a2: AsyncClient, contexto_f14a2: ContextoF14A2
) -> None:
    sobrescrever_sujeito(
        cliente_http_f14a2,
        sujeito_de_teste(contexto_f14a2, permissoes=frozenset({"empresas.criar"})),
    )
    cabecalhos_sem_idem = {"X-Tenant": contexto_f14a2.tenant_slug}

    resp = await cliente_http_f14a2.post(
        "/v1/empresas",
        json=_corpo_empresa(_gerar_cnpj_valido(), "Empresa Sem Chave"),
        headers=cabecalhos_sem_idem,
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["codigo"] == "PONTO-IDEM-001"


async def test_tentativa_com_erro_de_negocio_nao_envenena_a_chave(
    cliente_http_f14a2: AsyncClient, contexto_f14a2: ContextoF14A2
) -> None:
    """Uma primeira tentativa que FALHA (CNPJ com formato inválido -- `400
    PONTO-VAL-001` da própria validação Pydantic do corpo, nunca chega a
    `servico.criar_empresa`) não deve bloquear uma segunda tentativa com a
    MESMA chave e um corpo válido."""
    sobrescrever_sujeito(
        cliente_http_f14a2,
        sujeito_de_teste(contexto_f14a2, permissoes=frozenset({"empresas.criar"})),
    )
    chave = f"e2e-retry-{uuid.uuid4()}"

    resp_falha = await cliente_http_f14a2.post(
        "/v1/empresas",
        json={"cnpj": "123", "razaoSocial": "CNPJ invalido"},
        headers=cabecalhos(contexto_f14a2.tenant_slug, idempotencia=chave),
    )
    assert resp_falha.status_code == 400
    assert resp_falha.json()["codigo"] == "PONTO-VAL-001"

    resp_ok = await cliente_http_f14a2.post(
        "/v1/empresas",
        json=_corpo_empresa(_gerar_cnpj_valido(), "Empresa Retentativa"),
        headers=cabecalhos(contexto_f14a2.tenant_slug, idempotencia=chave),
    )
    assert resp_ok.status_code == 201, resp_ok.text
    assert resp_ok.headers.get("Idempotency-Replayed") == "false"
