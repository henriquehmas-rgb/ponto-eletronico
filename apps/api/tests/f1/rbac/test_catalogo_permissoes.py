"""Criterio de aceite 6.1: os 145 `x-permissao` do openapi.yaml existem em
`permissoes`, sem excecao (RFC-002 ja decidida: as 4 acoes antes bloqueadas
pelo CHECK -- configurar/reabrir/ler_sensivel -- agora sao aceitas).

Numero atualizado de 142 para 144 no fechamento da F13 (orquestrador,
03/08/2026): duas permissoes novas, unicas, confirmadas por diff programatico
contra o `openapi.yaml` da F12 (commit 5c3b18a) -- `admin.configurar`
(GET/PUT /v1/admin/sso/provedores, RFC-018) e `api_clients.editar`
(PUT/PATCH de cliente de API, RFC-016).

Atualizado de 144 para 145 no fechamento da F14 (orquestrador, 06/08/2026,
RFC-020): `marcacoes.aprovar`, nova em `POST /v1/marcacoes/{marcacaoId}/
meta/decisao` -- reaproveita a acao `aprovar` ja liberada pela RFC-002, so o
par (recurso, acao) e novo."""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
import yaml
from sqlalchemy.ext.asyncio import async_sessionmaker

_RAIZ_REPO = Path(__file__).resolve().parents[5]
_OPENAPI = _RAIZ_REPO / "packages" / "contracts" / "openapi.yaml"


def _permissoes_exigidas() -> set[str]:
    documento = yaml.safe_load(_OPENAPI.read_text(encoding="utf-8"))
    exigidas: set[str] = set()
    for caminho in documento["paths"].values():
        for operacao in caminho.values():
            if isinstance(operacao, dict) and operacao.get("x-permissao"):
                exigidas.add(operacao["x-permissao"])
    return exigidas


def test_openapi_exige_145_permissoes() -> None:
    """Trava o numero: se o contrato mudar, este teste avisa antes do resto."""
    assert len(_permissoes_exigidas()) == 145


async def test_todas_as_142_permissoes_existem_no_catalogo(
    fabrica_sessoes: async_sessionmaker,
) -> None:
    exigidas = _permissoes_exigidas()
    async with fabrica_sessoes() as sessao:
        existentes = set(
            (await sessao.execute(sa.text("SELECT codigo FROM permissoes"))).scalars().all()
        )
    faltando = sorted(exigidas - existentes)
    assert not faltando, f"permissoes exigidas pelo openapi.yaml e ausentes do catalogo: {faltando}"


async def test_acoes_liberadas_pela_rfc_002_estao_no_catalogo(
    fabrica_sessoes: async_sessionmaker,
) -> None:
    """As quatro permissoes que antes violavam o CHECK (RFC-002) existem de verdade."""
    async with fabrica_sessoes() as sessao:
        linhas = dict(
            (
                await sessao.execute(
                    sa.text("SELECT codigo, acao FROM permissoes WHERE codigo = ANY(:codigos)"),
                    {
                        "codigos": [
                            "tenants.configurar",
                            "banco_horas.configurar",
                            "fechamentos.reabrir",
                            "marcacoes.ler_sensivel",
                        ]
                    },
                )
            ).all()
        )
    assert linhas == {
        "tenants.configurar": "configurar",
        "banco_horas.configurar": "configurar",
        "fechamentos.reabrir": "reabrir",
        "marcacoes.ler_sensivel": "ler_sensivel",
    }
