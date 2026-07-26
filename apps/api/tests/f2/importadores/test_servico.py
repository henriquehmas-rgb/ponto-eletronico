"""Testes de `app/importadores/servico.py` (lado API do importador, T10).

`criar_importacao_colaboradores` e o unico ponto de entrada: grava
`importacoes` e enfileira o job de verdade no Redis de teste. O processamento
em si (o worker) tem testes proprios em `test_worker_tarefa.py`.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from arq.connections import RedisSettings, create_pool
from ponto_contracts import Importacao
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.importadores.servico import (
    NOME_TAREFA_IMPORTAR_COLABORADORES,
    criar_importacao_colaboradores,
)
from tests.f2.conftest import ContextoOrganizacional


@pytest.mark.asyncio
async def test_cria_importacao_e_enfileira_job_de_verdade(
    sessao_f2: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    redis_teste_url: str,
) -> None:
    importacao = await criar_importacao_colaboradores(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        empresa_id=contexto_organizacional.empresa_matriz_id,
        nome_arquivo="colaboradores.csv",
        origem="csv",
        conteudo_ref=f"testes/{uuid4()}.csv",
        parametros=None,
        usuario_id=None,
        redis_url=redis_teste_url,
    )
    # Sem commit: `SET LOCAL app.tenant_id` (RLS) vale so na transacao
    # corrente. `sessao_f2` da fixture da fase faz rollback ao fim do teste.

    assert importacao.id is not None
    assert importacao.status == "recebido"
    assert importacao.tipo == "colaboradores"

    linha = (
        await sessao_f2.execute(select(Importacao).where(Importacao.id == importacao.id))
    ).scalar_one()
    assert linha.empresa_id == contexto_organizacional.empresa_matriz_id

    pool = await create_pool(RedisSettings.from_dsn(redis_teste_url))
    try:
        job_ids = await pool.queued_jobs()
        nomes = {job.function for job in job_ids}
        assert NOME_TAREFA_IMPORTAR_COLABORADORES in nomes
    finally:
        await pool.aclose()


@pytest.mark.asyncio
async def test_segunda_importacao_em_andamento_e_recusada(
    sessao_f2: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    redis_teste_url: str,
) -> None:
    await criar_importacao_colaboradores(
        sessao_f2,
        tenant_id=contexto_organizacional.tenant_id,
        empresa_id=contexto_organizacional.empresa_matriz_id,
        nome_arquivo="a.csv",
        origem="csv",
        conteudo_ref="testes/a.csv",
        parametros=None,
        usuario_id=None,
        redis_url=redis_teste_url,
    )

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await criar_importacao_colaboradores(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            empresa_id=contexto_organizacional.empresa_matriz_id,
            nome_arquivo="b.csv",
            origem="csv",
            conteudo_ref="testes/b.csv",
            parametros=None,
            usuario_id=None,
            redis_url=redis_teste_url,
        )
    assert excinfo.value.codigo == "PONTO-IMP-002"


@pytest.mark.asyncio
async def test_origem_nao_suportada_e_recusada(
    sessao_f2: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    redis_teste_url: str,
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await criar_importacao_colaboradores(
            sessao_f2,
            tenant_id=contexto_organizacional.tenant_id,
            empresa_id=contexto_organizacional.empresa_matriz_id,
            nome_arquivo="a.pdf",
            origem="afd",
            conteudo_ref="testes/a.pdf",
            parametros=None,
            usuario_id=None,
            redis_url=redis_teste_url,
        )
    assert excinfo.value.codigo == "PONTO-VAL-009"
