"""A2 -- `app.comum.limitador_taxa.exigir_limite_taxa_sessao` (retrofit do
limitador de taxa para rotas de SESSÃO HUMANA, F1-F12).

Mesmo estilo de `tests/f13/nucleo/test_limitador_taxa.py` (que prova
`exigir_limite_taxa`, a variante de `ClienteAutenticado`): teste de carga
simples (N+1 requisições na mesma janela) contra o Redis REAL
(`PONTO_TEST_REDIS_URL`), provando o `429` na N+1ª com os cabeçalhos
corretos -- "comprovado por teste real, não só existência do Depends"
(critério de aceite de A2, PCF F14 §5).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from uuid import UUID

import pytest
import pytest_asyncio
from starlette.responses import Response

import app.comum.limitador_taxa as limitador_mod
from app.core.erros import ErroDeAplicacao
from app.core.seguranca import AlcanceEfetivo, Sujeito

_URL_REDIS_PADRAO_LOCAL = "redis://localhost:6379/1"


@pytest_asyncio.fixture(autouse=True)
async def _redis_de_teste(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Idêntico em espírito a `tests/f13/nucleo/test_limitador_taxa.py` --
    aponta o módulo para o Redis real desta sessão e força um cliente novo
    por teste (cada teste roda num event loop novo)."""
    url = os.environ.get("PONTO_TEST_REDIS_URL", _URL_REDIS_PADRAO_LOCAL)
    monkeypatch.setenv("REDIS_URL", url)
    limitador_mod.obter_configuracao.cache_clear()
    await limitador_mod._para_teste["encerrar_cliente_redis"]()

    yield

    await limitador_mod._para_teste["encerrar_cliente_redis"]()
    limitador_mod.obter_configuracao.cache_clear()


def _sujeito(
    *, tenant_id: UUID | None = None, usuario_id: UUID | None = None, autenticado: bool = True
) -> Sujeito:
    return Sujeito(
        usuario_id=usuario_id or uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        email="teste@exemplo.com",
        perfis=("perfil-teste",),
        permissoes=frozenset({"colaboradores.criar"}),
        autenticado=autenticado,
        alcance=AlcanceEfetivo(amplo_tenant=True),
    )


async def test_dentro_da_cota_escreve_cabecalhos_e_nao_levanta() -> None:
    dependencia = limitador_mod.exigir_limite_taxa_sessao(limite_por_minuto=5)
    response = Response()

    await dependencia(response=response, sujeito=_sujeito())

    assert response.headers["RateLimit-Limit"] == "5"
    assert response.headers["RateLimit-Remaining"] == "4"
    assert int(response.headers["RateLimit-Reset"]) <= 60
    assert response.headers["RateLimit-Policy"] == "5;w=60"


async def test_np1_esima_requisicao_responde_429_com_cabecalhos() -> None:
    limite = 3
    dependencia = limitador_mod.exigir_limite_taxa_sessao(limite_por_minuto=limite)
    sujeito = _sujeito()

    for _ in range(limite):
        await dependencia(response=Response(), sujeito=sujeito)

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await dependencia(response=Response(), sujeito=sujeito)

    assert excinfo.value.codigo == "PONTO-RATE-001"
    cabecalhos = excinfo.value.cabecalhos
    assert cabecalhos["RateLimit-Limit"] == str(limite)
    assert cabecalhos["RateLimit-Remaining"] == "0"
    assert cabecalhos["Retry-After"]


async def test_dois_usuarios_do_mesmo_tenant_tem_cotas_independentes() -> None:
    """A chave é `tenant_id:usuario_id`, não só `tenant_id` -- um usuário
    esgotando a própria cota não afeta outro usuário do mesmo tenant."""
    limite = 2
    tenant_id = uuid.uuid4()
    dependencia = limitador_mod.exigir_limite_taxa_sessao(limite_por_minuto=limite)
    usuario_a = _sujeito(tenant_id=tenant_id)
    usuario_b = _sujeito(tenant_id=tenant_id)

    for _ in range(limite):
        await dependencia(response=Response(), sujeito=usuario_a)
    with pytest.raises(ErroDeAplicacao):
        await dependencia(response=Response(), sujeito=usuario_a)

    # Usuário B, mesmo tenant: cota própria, ainda intacta.
    response_b = Response()
    await dependencia(response=response_b, sujeito=usuario_b)
    assert response_b.headers["RateLimit-Remaining"] == "1"


async def test_sujeito_anonimo_nao_e_limitado_falha_aberta() -> None:
    """Sujeito não autenticado: `exigir_permissao` da própria rota já recusa
    por credencial ausente antes que o limite importe -- esta dependência
    apenas não faz nada (nem consome Redis) nesse caso."""
    dependencia = limitador_mod.exigir_limite_taxa_sessao(limite_por_minuto=1)
    resposta = Response()

    await dependencia(response=resposta, sujeito=_sujeito(autenticado=False))
    await dependencia(response=resposta, sujeito=_sujeito(autenticado=False))

    assert "RateLimit-Limit" not in resposta.headers
