"""T2 -- resolucao de tenant e ligacao do Row Level Security.

Cobre os tres "pronto quando" do PCF: cabecalho ausente em rota que exige
tenant responde `PONTO-VAL-011`; tenant inexistente responde `PONTO-TEN-001`;
e a transacao da requisicao publica o UUID correto em `current_setting`.
Acrescenta o caminho irmao (tenant `suspenso`/`cancelado` responde
`PONTO-TEN-003`), citado na descricao da fase mas fora da lista literal de
"pronto quando" -- comportamento simetrico ao TEN-001, mesmo mecanismo.
"""

from __future__ import annotations

import secrets
import uuid

from fastapi.testclient import TestClient
from ponto_contracts import Tenant
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.f1.conftest import AbrirSessaoTenant, ContextoF1, cabecalhos

MEDIA_TYPE_PROBLEMA = "application/problem+json"


# -----------------------------------------------------------------------------
# Cabecalho ausente em rota que exige tenant -> PONTO-VAL-011
# -----------------------------------------------------------------------------
def test_sem_x_tenant_em_rota_que_toca_banco_responde_val_011(cliente: TestClient) -> None:
    """`GET /v1/tenants/atual` declara `SessaoDb`: sem tenant resolvido,
    `app/db/sessao.py:obter_sessao` recusa abrir sessao antes de tocar o banco."""
    resposta = cliente.get("/v1/tenants/atual")
    assert resposta.status_code == 400
    assert resposta.headers["content-type"].startswith(MEDIA_TYPE_PROBLEMA)
    assert resposta.json()["codigo"] == "PONTO-VAL-011"


def test_rota_ainda_stub_sem_x_tenant_nao_e_bloqueada_pelo_middleware(
    cliente: TestClient,
) -> None:
    """Regressao do andaime: uma rota de dominio que AINDA nao declara
    `SessaoDb` (ainda `501`) nao e bloqueada pelo `TenantMiddleware` so por
    faltar `X-Tenant` -- a exigencia de tenant e da dependencia de sessao, nao
    de todo `/v1/...` incondicionalmente (ver docstring de
    `app/core/middleware.py:TenantMiddleware`).

    `/v1/fiscal/afd` era o exemplo original (F1) mas F12 implementou a tag
    `fiscal` de verdade -- trocado por `/v1/lgpd/consentimentos` (orquestrador,
    fechamento da F13, 03/08/2026): `app/routers/lgpd.py` ainda e o stub
    GERADO original, tag inteira reservada a uma fase futura (F14, `Onda 5`,
    segurança/antifraude/LGPD -- ver `docs/backlog.md`/status das ondas),
    ninguem a tocou ainda."""
    resposta = cliente.get("/v1/lgpd/consentimentos")
    assert resposta.status_code == 501
    assert resposta.json()["codigo"] == "PONTO-INT-005"


# -----------------------------------------------------------------------------
# Tenant inexistente -> PONTO-TEN-001
# -----------------------------------------------------------------------------
def test_tenant_inexistente_responde_ten_001(cliente: TestClient) -> None:
    slug_inexistente = f"tenant-que-nao-existe-{secrets.token_hex(4)}"
    resposta = cliente.get("/v1/tenants/atual", headers=cabecalhos(slug_inexistente))
    assert resposta.status_code == 404
    assert resposta.headers["content-type"].startswith(MEDIA_TYPE_PROBLEMA)
    assert resposta.json()["codigo"] == "PONTO-TEN-001"


# -----------------------------------------------------------------------------
# Tenant suspenso/cancelado -> PONTO-TEN-003 (simetrico ao TEN-001)
# -----------------------------------------------------------------------------
async def _semear_tenant_com_status(
    fabrica_f1: async_sessionmaker[AsyncSession], status: str
) -> str:
    """Tenant minimo dedicado a este teste, so com o `status` pedido.

    Nao reusa `tenant_a`/`tenant_b` (ambos `ativo`, compartilhados por toda a
    suite) de proposito: mudar o status deles no meio da suite quebraria
    qualquer teste que rode depois em paralelo/fora de ordem.
    """
    slug = f"tenant-{status}-{secrets.token_hex(4)}"
    tenant_id = uuid.uuid4()
    async with fabrica_f1() as sessao:
        await sessao.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_id)}
        )
        sessao.add(
            Tenant(
                id=tenant_id,
                slug=slug,
                razao_social=f"Tenant de teste ({status})",
                nome_exibicao=f"Tenant {status}",
                status=status,
                plano="padrao",
            )
        )
        await sessao.commit()
    return slug


async def test_tenant_suspenso_responde_ten_003(
    cliente: TestClient, fabrica_f1: async_sessionmaker[AsyncSession]
) -> None:
    slug = await _semear_tenant_com_status(fabrica_f1, "suspenso")
    resposta = cliente.get("/v1/tenants/atual", headers=cabecalhos(slug))
    assert resposta.status_code == 403
    assert resposta.json()["codigo"] == "PONTO-TEN-003"


async def test_tenant_cancelado_responde_ten_003(
    cliente: TestClient, fabrica_f1: async_sessionmaker[AsyncSession]
) -> None:
    slug = await _semear_tenant_com_status(fabrica_f1, "cancelado")
    resposta = cliente.get("/v1/tenants/atual", headers=cabecalhos(slug))
    assert resposta.status_code == 403
    assert resposta.json()["codigo"] == "PONTO-TEN-003"


def test_tenant_ativo_nao_e_bloqueado(cliente: TestClient, contexto_f1: ContextoF1) -> None:
    resposta = cliente.get("/v1/tenants/atual", headers=cabecalhos(contexto_f1.tenant_a.slug))
    assert resposta.status_code == 200


# -----------------------------------------------------------------------------
# A transacao publica o UUID correto em current_setting('app.tenant_id')
# -----------------------------------------------------------------------------
async def test_current_setting_traz_o_uuid_correto_do_tenant(
    contexto_f1: ContextoF1, abrir_sessao_tenant: AbrirSessaoTenant
) -> None:
    async with abrir_sessao_tenant(contexto_f1.tenant_a.id) as sessao:
        valor = (
            await sessao.execute(text("SELECT current_setting('app.tenant_id', true)::uuid"))
        ).scalar_one()
        assert valor == contexto_f1.tenant_a.id

    async with abrir_sessao_tenant(contexto_f1.tenant_b.id) as sessao:
        valor = (
            await sessao.execute(text("SELECT current_setting('app.tenant_id', true)::uuid"))
        ).scalar_one()
        assert valor == contexto_f1.tenant_b.id


async def test_sessao_sem_tenant_aplicado_nao_enxerga_nenhum_tenant(
    fabrica_f1: async_sessionmaker[AsyncSession],
) -> None:
    """Sessao aberta SEM passar por `abrir_sessao_tenant` (nenhum `SET LOCAL`):
    `current_setting` devolve NULL, e e exatamente o comportamento de falha
    fechada que o ADR-001 exige."""
    async with fabrica_f1() as sessao:
        valor = (
            await sessao.execute(text("SELECT current_setting('app.tenant_id', true)"))
        ).scalar_one()
        assert valor in (None, "")


async def test_current_setting_por_requisicao_http_bate_com_o_tenant_do_cabecalho(
    cliente: TestClient, contexto_f1: ContextoF1
) -> None:
    """A mesma prova acima, mas de ponta a ponta pela API: o valor que
    `TenantMiddleware` resolveu (UUID, nao slug) e o que a transacao da
    requisicao publica -- provado indiretamente pela resposta de
    `obterTenantAtual`, que so pode devolver a linha certa se a RLS estiver
    vendo o UUID certo."""
    resposta = cliente.get("/v1/tenants/atual", headers=cabecalhos(contexto_f1.tenant_a.slug))
    assert resposta.status_code == 200
    assert resposta.json()["id"] == str(contexto_f1.tenant_a.id)
    assert resposta.json()["slug"] == "tenant-a"
