"""Expansão de 2026-08-07/08 da amostra representativa de `IdempotenciaRetrofitMiddleware`
(`app/comum/idempotencia_middleware.py`, `ROTAS_COM_DEDUP_REAL`) -- de 10 para 36
rotas, ver comentário no próprio módulo para o critério de seleção/exclusão.

Dois níveis de prova, mesmo espírito do teste original
(`test_idempotencia_middleware_http_e2e.py`, `POST /v1/empresas`):

1. Um teste HTTP de ponta a ponta real (`POST /v1/feriado-conjuntos`, F3 --
   escolhida por não depender de nenhum recurso pré-existente além do
   tenant, ao contrário da maioria das novas rotas que exigem uma empresa/
   estrutura organizacional já semeada) -- mesma prova de replay real que o
   teste original: só existe UMA linha na tabela depois de duas chamadas com
   a mesma chave.
2. Um teste de regressão barato (sem HTTP, sem banco) que confere que toda
   rota desta expansão continua na allowlist -- protege contra alguém
   remover uma entrada sem querer numa edição futura do módulo.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from ponto_contracts.jornada import FeriadoConjunto
from sqlalchemy.ext.asyncio import AsyncSession

from app.comum.idempotencia_middleware import ROTAS_COM_DEDUP_REAL
from tests.f14.hardening.conftest import (
    ContextoF14A2,
    cabecalhos,
    sobrescrever_sujeito,
    sujeito_de_teste,
)

pytestmark = pytest.mark.asyncio

#: Mesma lista de `ROTAS_COM_DEDUP_REAL` menos as 10 originais (já cobertas
#: pelo teste de `POST /v1/empresas` e pela suíte de F1-F12 correspondente) --
#: escrita por extenso (não por subtração em runtime) para que o teste falhe
#: de forma legível se uma entrada específica sumir.
_ROTAS_DA_EXPANSAO: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/v1/admin/perfis"),
        ("POST", "/v1/admin/usuarios"),
        ("POST", "/v1/banco-horas/contas"),
        ("POST", "/v1/banco-horas/politicas"),
        ("POST", "/v1/banco-horas/quitacoes"),
        ("POST", "/v1/cargos"),
        ("POST", "/v1/centros-custo"),
        ("POST", "/v1/delegacoes"),
        ("POST", "/v1/equipes"),
        ("POST", "/v1/fechamentos"),
        ("POST", "/v1/feriado-conjuntos"),
        ("POST", "/v1/integracoes/folha"),
        ("POST", "/v1/jornadas"),
        ("POST", "/v1/lgpd/consentimentos"),
        ("POST", "/v1/lgpd/solicitacoes-titular"),
        ("POST", "/v1/periodos"),
        ("POST", "/v1/relatorios/agendamentos"),
        ("POST", "/v1/solicitacoes"),
        ("POST", "/v1/terminais"),
        ("POST", "/v1/tipos-afastamento"),
        ("POST", "/v1/tipos-solicitacao"),
        ("POST", "/v1/tratamentos"),
        ("POST", "/v1/turnos"),
        ("POST", "/v1/vinculos"),
        ("POST", "/v1/biometrias"),
        ("POST", "/v1/espelhos"),  # segunda passada, 2026-08-08
    }
)


def test_todas_as_rotas_da_expansao_continuam_na_allowlist() -> None:
    faltando = _ROTAS_DA_EXPANSAO - ROTAS_COM_DEDUP_REAL
    assert not faltando, f"rota(s) removida(s) de ROTAS_COM_DEDUP_REAL sem querer: {faltando}"


async def _contar_feriado_conjuntos(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, codigo: str
) -> int:
    await sessao.execute(
        sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
    )
    resultado = await sessao.execute(
        sa.select(sa.func.count())
        .select_from(FeriadoConjunto)
        .where(FeriadoConjunto.tenant_id == tenant_id, FeriadoConjunto.codigo == codigo)
    )
    return int(resultado.scalar_one())


async def test_replay_feriado_conjunto_nao_reexecuta_e_devolve_resposta_armazenada(
    cliente_http_f14a2: AsyncClient, contexto_f14a2: ContextoF14A2, sessao_f14a2: AsyncSession
) -> None:
    sobrescrever_sujeito(
        cliente_http_f14a2,
        sujeito_de_teste(contexto_f14a2, permissoes=frozenset({"feriados.criar"})),
    )
    codigo = f"conj-{uuid.uuid4().hex[:10]}"
    corpo = {"codigo": codigo, "nome": "Feriados Nacionais", "abrangencia": "nacional"}
    chave = f"e2e-replay-feriado-{uuid.uuid4()}"

    resp1 = await cliente_http_f14a2.post(
        "/v1/feriado-conjuntos",
        json=corpo,
        headers=cabecalhos(contexto_f14a2.tenant_slug, idempotencia=chave),
    )
    assert resp1.status_code == 201, resp1.text
    assert resp1.headers.get("Idempotency-Replayed") == "false"
    corpo1 = resp1.json()

    resp2 = await cliente_http_f14a2.post(
        "/v1/feriado-conjuntos",
        json=corpo,
        headers=cabecalhos(contexto_f14a2.tenant_slug, idempotencia=chave),
    )
    assert resp2.status_code == 201, resp2.text
    assert resp2.headers.get("Idempotency-Replayed") == "true"
    corpo2 = resp2.json()
    assert corpo2["id"] == corpo1["id"], "replay deve devolver o MESMO conjunto, não criar outro"

    # A prova real: só existe UMA linha com este código -- a segunda chamada
    # NUNCA executou o serviço de criação.
    total = await _contar_feriado_conjuntos(
        sessao_f14a2, tenant_id=contexto_f14a2.tenant_id, codigo=codigo
    )
    assert total == 1
