"""F14/A4 -- vetor 6: bypass do score de confianca manipulando o payload para
forcar `score_confianca` alto sem o backend recalcular.

ADR-008 regra 1: **"o cliente que manda `score: 100` e ignorado por
construcao -- o campo nao existe na entrada."** A4/A1 ja tem um teste que
confirma isto a nivel de dominio (`tests/f14/antifraude/
test_pipeline_integracao.py::test_cliente_nao_pode_forcar_score_alto_campo_nao_existe_na_entrada`),
mas aquele teste usa `contrato.MarcacaoCriar.model_validate(...)` (um dict
Python já dentro do processo) e conjuga o "score injetado" com um sinal
DECISIVO (`mockLocation: true`, que bloqueia a requisicao inteira antes de
qualquer score aparecer na resposta) -- prova que o campo e ignorado, mas
nunca mostra o NUMERO REAL que o servidor calculou sobrevivendo ao lado do
campo injetado.

Este arquivo fecha essa lacuna com o vetor no seu formato mais realista
(POST HTTP cru via `TestClient`, JSON bruto exatamente como um atacante
enviaria, sem nenhum sinal decisivo -- so um sinal FRACO, nao bloqueante)
e prova as DUAS metades da regra ao mesmo tempo:

1. `scoreConfianca: 100` no corpo bruto NAO faz a marcacao ser aceita com
   score 100 quando o sinal real e ruim (fora da geocerca, sinalizado) --
   o numero devolvido e o CALCULADO pelo servidor, nao o injetado.
2. O mesmo vale para `revisaoRequerida: false`/`classificacaoConfianca:
   "alta"` injetados junto -- nenhum dos tres campos de veredito aceita
   valor vindo do cliente.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager

import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import app.db.sessao as _db_sessao
from app.core.seguranca import Sujeito, obter_sujeito
from tests.f14.adversarial.conftest import ContextoDoisTenants


@pytest_asyncio.fixture(autouse=True)
async def _engine_global_isolada_por_teste() -> AsyncIterator[None]:
    """Mesmo padrao de `tests/f13/conftest.py`/`tests/f14/antifraude/
    test_explicabilidade_http.py`: zera a engine GLOBAL de `app.db.sessao`
    a cada teste para o `TestClient` (que abre sessao pela fabrica
    singleton, nunca por `sessao_f14a4`) nao reusar uma engine presa ao
    event loop de um teste anterior."""
    from app.core.config import obter_configuracao

    obter_configuracao.cache_clear()
    _db_sessao._engine = None  # type: ignore[attr-defined]
    _db_sessao._fabrica = None  # type: ignore[attr-defined]
    _db_sessao._engine_loop = None  # type: ignore[attr-defined]
    yield
    if _db_sessao._engine is not None:  # type: ignore[attr-defined]
        await _db_sessao.encerrar_engine()


def _sujeito_fixo(tenant_id: uuid.UUID, usuario_id: uuid.UUID, permissoes: set[str]):
    async def _fake() -> Sujeito:
        return Sujeito(
            usuario_id=usuario_id,
            tenant_id=tenant_id,
            email="atacante-teste@exemplo.com.br",
            perfis=("teste",),
            permissoes=frozenset(permissoes),
            autenticado=True,
        )

    return _fake


@contextmanager
def _cliente_com_permissoes(
    tenant_id: uuid.UUID, usuario_id: uuid.UUID, permissoes: set[str]
) -> Iterator[TestClient]:
    from app.main import app

    app.dependency_overrides[obter_sujeito] = _sujeito_fixo(tenant_id, usuario_id, permissoes)
    try:
        # IP sintaticamente valido (ver achado ja corrigido por A2,
        # `app.comum.ip_confiavel`): `TestClient` sem transporte de rede
        # real usa "testclient" por padrao, que nao e um IP valido.
        with TestClient(
            app, raise_server_exceptions=True, client=("203.0.113.90", 51000)
        ) as cliente:
            yield cliente
    finally:
        app.dependency_overrides.pop(obter_sujeito, None)


async def test_score_injetado_no_json_bruto_via_http_nunca_substitui_o_score_real(
    sessao_f14a4: AsyncSession, contexto_dois_tenants: ContextoDoisTenants
) -> None:
    """Fora da geocerca (a unidade so existe em Goiania/GO; a coordenada
    enviada e de Sao Paulo/SP, ~900km de distancia) com a politica DEFAULT
    (`politica_fora_geocerca='sinalizar'`) produz um sinal ruim mas NAO
    decisivo -- a marcacao e aceita (201), mas com score baixo/medio e
    revisao requerida. O corpo bruto injeta `scoreConfianca: 100`,
    `classificacaoConfianca: "alta"` e `revisaoRequerida: false` -- nenhum
    dos tres deveria sobreviver a resposta real."""
    tenant = contexto_dois_tenants.tenant_a

    # Limiar de bloqueio bem baixo: garante que o sinal fraco (fora da
    # geocerca, unica categoria disponivel) nao vira PONTO-GEO-001/SCORE-001
    # -- o objetivo aqui e observar o NUMERO na resposta, nao um bloqueio.
    await sessao_f14a4.execute(
        text(
            "INSERT INTO politicas_registro "
            "(tenant_id, empresa_id, unidade_id, canal, exige_geocerca, "
            " politica_fora_geocerca, limiar_bloqueio, limiar_revisao, ativo) "
            "VALUES (:tenant_id, :empresa_id, NULL, 'mobile', TRUE, 'sinalizar', 0, 70, TRUE)"
        ),
        {"tenant_id": tenant.tenant_id, "empresa_id": tenant.empresa_id},
    )
    await sessao_f14a4.commit()

    with _cliente_com_permissoes(
        tenant.tenant_id, tenant.usuario_id, {"marcacoes.criar"}
    ) as cliente:
        corpo_bruto_do_atacante = {
            "colaboradorId": str(tenant.colaborador_id),
            "empresaId": str(tenant.empresa_id),
            "unidadeId": str(tenant.unidade_id),
            "canal": "mobile",
            "dispositivoId": str(tenant.dispositivo_id),
            # Sao Paulo/SP -- bem fora da geocerca da sede em Goiania/GO.
            "latitude": -23.5505,
            "longitude": -46.6333,
            "precisaoMetros": 5.0,
            # --- campos que o ATACANTE injeta, nenhum existe no schema de
            # entrada (`MarcacaoCriar`) -- devem ser silenciosamente
            # ignorados pelo Pydantic (`model_config` sem `extra="forbid"`,
            # confirmado por leitura de `app/schemas/contrato.py`).
            "scoreConfianca": 100,
            "classificacaoConfianca": "alta",
            "revisaoRequerida": False,
            "score": 100,
        }
        resposta = cliente.post(
            "/v1/marcacoes",
            json=corpo_bruto_do_atacante,
            headers={
                "X-Tenant": tenant.tenant_slug,
                "Idempotency-Key": str(uuid.uuid4()),
            },
        )

    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()

    score_real = corpo["scoreConfianca"]
    assert score_real is not None
    assert score_real < 100, (
        "VULNERAVEL: scoreConfianca da resposta e 100 -- o valor injetado "
        "pelo atacante sobreviveu, apesar do sinal real (fora da geocerca) "
        "ser ruim."
    )
    # Nao fixamos o numero exato (a composicao pondera mais categorias do
    # que so geolocalizacao no canal mobile -- reputacao de dispositivo
    # tambem entra): o que importa e que o valor devolvido e o CALCULADO
    # pelo motor (< limiar de "alta", que e 70 nesta politica), nunca o 100
    # injetado.
    assert score_real < 70, (
        f"esperava um score abaixo do limiar de revisao (70) por causa do "
        f"sinal fora-da-geocerca sinalizado; recebido {score_real} -- "
        f"confirme se o cenario de teste ainda produz o sinal esperado "
        f"antes de reinterpretar este achado."
    )
    assert (
        corpo["classificacaoConfianca"] != "alta"
    ), "VULNERAVEL: classificacaoConfianca 'alta' injetada sobreviveu."
    assert corpo["revisaoRequerida"] is True, (
        "VULNERAVEL: revisaoRequerida=false injetado sobreviveu -- um sinal "
        "ruim que deveria acionar a fila de revisao do gestor foi suprimido."
    )

    # Confirma tambem NO BANCO (nao so na resposta HTTP): a marcacao gravada
    # tem o score REAL, nao o injetado -- o atacante nao conseguiu nem
    # sequer persistir um numero falso para uso futuro (relatorio, auditoria).
    marcacao_id = corpo["marcacao"]["id"]
    linha = (
        (
            await sessao_f14a4.execute(
                text(
                    "SELECT score_confianca, revisao_status FROM marcacoes_meta "
                    "WHERE tenant_id = :tenant AND marcacao_id = :marcacao"
                ),
                {"tenant": str(tenant.tenant_id), "marcacao": marcacao_id},
            )
        )
        .mappings()
        .one()
    )
    assert linha["score_confianca"] == score_real
    assert linha["revisao_status"] == "pendente"


async def test_score_injetado_nao_afeta_cross_tenant_via_header_x_tenant(
    sessao_f14a4: AsyncSession, contexto_dois_tenants: ContextoDoisTenants
) -> None:
    """Reforco combinando os vetores 3 e 6: mesmo que o atacante autenticado
    no tenant A tente enviar `X-Tenant` do tenant B JUNTO com o score
    injetado, a marcacao nunca vaza dado de A sob o escopo de B.

    Achado real desta sessao (2026-08-07): a asercao original ("X-Tenant e
    vestigial aqui, dependency override resolve tudo") estava ERRADA sobre
    a propria arquitetura. `app.dependency_overrides[obter_sujeito]`
    substitui a dependencia do FastAPI, mas `TenantMiddleware`
    (`app/core/middleware.py`) e ASGI puro, roda ANTES da injecao de
    dependencia, e continua publicando o tenant resolvido do cabecalho
    `X-Tenant` em `contexto.tenant_atual()` -- e essa ContextVar, nao
    `sujeito.tenant_id`, que `app/db/sessao.py::obter_sessao` usa para
    `SET LOCAL app.tenant_id` (RLS). Com sujeito fixado em A mas RLS
    escopada em B, os registros do colaborador/empresa/unidade/dispositivo
    (que so existem em A) ficam invisiveis para a sessao -- resultado
    real, reproduzido contra Postgres de verdade: 404 `PONTO-REC-001`, nao
    201 gravado em A como a asercao original esperava.

    Isso NAO e um bypass nem um vazamento cross-tenant: e o RLS recusando
    (fail-closed) por escopo vazio, o resultado mais seguro possivel. Mas
    tambem significa que este teste, do jeito que esta construido, nunca
    exercita a checagem real de divergencia token/cabecalho
    (`PONTO-TEN-002`, `app/core/seguranca.py`) -- substituir
    `obter_sujeito` inteiro remove essa logica do caminho testado junto
    com o resto da dependencia. A defesa de identidade contra esse ataque
    especifico (colaborador de A referenciado sob sessao de B) ja esta
    coberta por outro caminho, verificado nesta investigacao:
    `resolver_sujeito` (`app/identidade/rbac/resolucao.py`) recusa
    explicitamente sujeito/tenant divergentes com um JWT real, antes de
    qualquer coisa aqui. Cobertura direta de `PONTO-TEN-002` com um JWT de
    verdade (nao dependency override) fica registrada como lacuna em
    `docs/backlog.md`."""
    tenant_a = contexto_dois_tenants.tenant_a
    tenant_b = contexto_dois_tenants.tenant_b

    with _cliente_com_permissoes(
        tenant_a.tenant_id, tenant_a.usuario_id, {"marcacoes.criar"}
    ) as cliente:
        resposta = cliente.post(
            "/v1/marcacoes",
            json={
                "colaboradorId": str(tenant_a.colaborador_id),
                "empresaId": str(tenant_a.empresa_id),
                "unidadeId": str(tenant_a.unidade_id),
                "canal": "mobile",
                "dispositivoId": str(tenant_a.dispositivo_id),
                "scoreConfianca": 100,
            },
            headers={
                # TenantMiddleware roda fora da injecao de dependencia do
                # FastAPI e publica o tenant deste cabecalho em
                # `contexto.tenant_atual()` independente do override de
                # `obter_sujeito` abaixo -- por isso a RLS da sessao fica
                # escopada em B mesmo com o sujeito fixado em A (ver
                # docstring da funcao).
                "X-Tenant": tenant_b.tenant_slug,
                "Idempotency-Key": str(uuid.uuid4()),
            },
        )

    # RLS escopada em B nao enxerga o colaborador/empresa/unidade/
    # dispositivo de A -- 404, nao 201. Nenhum dado de A vaza sob B.
    assert resposta.status_code == 404, resposta.text
    assert resposta.json()["codigo"] == "PONTO-REC-001"
