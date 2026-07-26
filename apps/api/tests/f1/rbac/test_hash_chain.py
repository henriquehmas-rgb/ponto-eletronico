"""T10 -- trilha de auditoria encadeada por hash: cadeia integra, deteccao de
adulteracao, imutabilidade para a role da aplicacao e sequencia sem lacuna sob
concorrencia (criterios de aceite 4 e 5).

Todos os testes usam `tenant_b_id`, exclusivo desta suite dentro da fixture de
RBAC, e tiram um "retrato" da sequencia mais alta ja gravada antes de escrever
--para nao depender da ordem de execucao dos demais arquivos deste diretorio
(alguns tambem gravam em `auditoria` via `registrar_auditoria_de_sujeito`).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.identidade.auditoria.hash_chain import gravar_auditoria, verificar_cadeia
from tests.f1.rbac.conftest import aplicar_tenant


async def _maior_sequencia(sessao: AsyncSession, *, tenant_id: uuid.UUID) -> int:
    valor = (
        await sessao.execute(
            text("SELECT COALESCE(MAX(sequencia), 0) FROM auditoria WHERE tenant_id = :tenant"),
            {"tenant": str(tenant_id)},
        )
    ).scalar_one()
    return int(valor)


async def test_cadeia_integra_apos_escritas_sequenciais(
    fabrica_sessoes: async_sessionmaker[AsyncSession], tenant_b_id: uuid.UUID
) -> None:
    async with fabrica_sessoes() as sessao:
        await aplicar_tenant(sessao, tenant_b_id)
        base = await _maior_sequencia(sessao, tenant_id=tenant_b_id)
        for i in range(3):
            await gravar_auditoria(
                sessao,
                tenant_id=tenant_b_id,
                evento="identidade.teste.hash_chain",
                entidade="testes",
                acao="criar",
                valor_novo={"i": i},
            )
        await sessao.commit()
        # `commit()` fecha a transacao onde `SET LOCAL app.tenant_id` valia;
        # sem reaplicar, a consulta seguinte nesta mesma sessao roda sem
        # tenant publicado e o RLS devolve zero linhas.
        await aplicar_tenant(sessao, tenant_b_id)

        resultado = await verificar_cadeia(
            sessao, tenant_id=tenant_b_id, sequencia_de=base + 1, sequencia_ate=base + 3
        )

    assert resultado.integra is True
    assert resultado.total_verificado == 3
    assert resultado.sequencia_inicial == base + 1
    assert resultado.sequencia_final == base + 3
    assert resultado.primeira_divergencia_sequencia is None


async def test_verificador_detecta_remocao_por_superusuario(
    fabrica_sessoes: async_sessionmaker[AsyncSession],
    admin_engine_sync: sa.engine.Engine,
    tenant_b_id: uuid.UUID,
) -> None:
    """A role da aplicacao nao consegue apagar a linha (ver teste seguinte);
    aqui simulamos deliberadamente uma remocao adversarial via superusuario,
    que so e possivel desligando o gatilho de imutabilidade na mao -- e
    exatamente o cenario que a cadeia de hash existe para detectar."""
    async with fabrica_sessoes() as sessao:
        await aplicar_tenant(sessao, tenant_b_id)
        base = await _maior_sequencia(sessao, tenant_id=tenant_b_id)
        for i in range(5):
            await gravar_auditoria(
                sessao,
                tenant_id=tenant_b_id,
                evento="identidade.teste.hash_chain_remocao",
                entidade="testes",
                acao="criar",
                valor_novo={"i": i},
            )
        await sessao.commit()

    sequencia_removida = base + 3
    with admin_engine_sync.begin() as conexao:
        conexao.execute(
            sa.text("ALTER TABLE auditoria DISABLE TRIGGER trg_auditoria_bloqueia_delete")
        )
        try:
            conexao.execute(
                sa.text("DELETE FROM auditoria WHERE tenant_id = :tenant AND sequencia = :seq"),
                {"tenant": str(tenant_b_id), "seq": sequencia_removida},
            )
        finally:
            conexao.execute(
                sa.text("ALTER TABLE auditoria ENABLE TRIGGER trg_auditoria_bloqueia_delete")
            )

    async with fabrica_sessoes() as sessao:
        await aplicar_tenant(sessao, tenant_b_id)
        resultado = await verificar_cadeia(
            sessao, tenant_id=tenant_b_id, sequencia_de=base + 1, sequencia_ate=base + 5
        )

    assert resultado.integra is False
    assert resultado.lacunas == {"faixas": [{"de": sequencia_removida, "ate": sequencia_removida}]}


async def test_role_da_aplicacao_nao_consegue_apagar_registro(
    fabrica_sessoes: async_sessionmaker[AsyncSession], tenant_b_id: uuid.UUID
) -> None:
    """`ponto_app_login` (a role sob a qual os testes de RLS/RBAC rodam, ver
    docstring de `conftest.py`) nao tem como remover uma linha de `auditoria`:
    o gatilho aborta com ERRCODE 42501 independentemente de GRANT."""
    async with fabrica_sessoes() as sessao:
        await aplicar_tenant(sessao, tenant_b_id)
        registro = await gravar_auditoria(
            sessao,
            tenant_id=tenant_b_id,
            evento="identidade.teste.imutabilidade",
            entidade="testes",
            acao="criar",
        )
        await sessao.commit()
        await aplicar_tenant(sessao, tenant_b_id)

        with pytest.raises(DBAPIError) as excinfo:
            await sessao.execute(
                text("DELETE FROM auditoria WHERE id = :id"), {"id": str(registro.id)}
            )
        assert getattr(excinfo.value.orig, "sqlstate", None) == "42501"
        await sessao.rollback()


async def test_concorrencia_100_escritas_paralelas_sem_lacuna(
    fabrica_sessoes: async_sessionmaker[AsyncSession], tenant_b_id: uuid.UUID
) -> None:
    """Criterio de aceite 5: 100 escritas concorrentes produzem `sequencia`
    contigua, sem buraco e sem repeticao (o `pg_advisory_xact_lock` de
    `gravar_auditoria`/`_travar_e_ler_estado_cadeia` e o que garante isso).

    As 100 escritas sao disparadas concorrentemente via `asyncio.gather`, mas
    um `Semaphore` limita quantas SESSOES DE BANCO ficam abertas ao mesmo
    tempo: esta instancia de teste (`max_connections`) e compartilhada por
    todos os agentes da Onda 1 rodando em paralelo na mesma VPS, e um teste
    que abrisse 100 conexoes simultaneas de verdade excederia esse limite
    global e derrubaria os outros agentes com `TooManyConnectionsError`. O
    semaforo restringe apenas a CONCORRENCIA DE CONEXAO, nunca a corretude: a
    serializacao que a sequencia sem lacuna depende (`pg_advisory_xact_lock`)
    continua sendo o banco, nao o teste.
    """
    limite_conexoes_simultaneas = asyncio.Semaphore(8)

    async with fabrica_sessoes() as sessao:
        await aplicar_tenant(sessao, tenant_b_id)
        base = await _maior_sequencia(sessao, tenant_id=tenant_b_id)

    async def _escrever(i: int) -> None:
        async with limite_conexoes_simultaneas, fabrica_sessoes() as sessao:
            await aplicar_tenant(sessao, tenant_b_id)
            await gravar_auditoria(
                sessao,
                tenant_id=tenant_b_id,
                evento="identidade.teste.concorrencia",
                entidade="testes",
                acao="criar",
                valor_novo={"i": i},
            )
            await sessao.commit()

    await asyncio.gather(*(_escrever(i) for i in range(100)))

    async with fabrica_sessoes() as sessao:
        await aplicar_tenant(sessao, tenant_b_id)
        sequencias = sorted(
            (
                await sessao.execute(
                    text(
                        "SELECT sequencia FROM auditoria "
                        "WHERE tenant_id = :tenant AND sequencia > :base"
                    ),
                    {"tenant": str(tenant_b_id), "base": base},
                )
            )
            .scalars()
            .all()
        )
        resultado = await verificar_cadeia(
            sessao, tenant_id=tenant_b_id, sequencia_de=base + 1, sequencia_ate=base + 100
        )

    assert len(sequencias) == 100
    assert len(set(sequencias)) == 100, "sequencia repetida sob concorrencia"
    assert sequencias == list(range(base + 1, base + 101)), "buraco na sequencia sob concorrencia"
    assert resultado.integra is True
