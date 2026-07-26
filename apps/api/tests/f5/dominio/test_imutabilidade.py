"""T4 -- prova de imutabilidade por execucao real (criterio de aceite 2) e
deteccao de lacuna via `verificarSequenciaNsr` (criterio de aceite 3, parte
qualitativa -- a prova de carga com 10.000 fica em `test_concorrencia_nsr.py`,
T9).

Os quatro testes de `UPDATE`/`DELETE` bloqueado conectam SEMPRE como a role
da aplicacao (`ponto_f5_a1_login`, via `sessao_f5`/`engine_f5`) -- nunca como
superusuario, porque testar como superusuario mascararia exatamente o defeito
que estes testes existem para achar (o `REVOKE`/gatilho nao se aplica a ele).
O teste de deteccao de lacuna e o UNICO que usa a conexao administrativa
(`admin_engine_sync_f5`), e so para simular, deliberadamente, uma remocao
externa via `ALTER TABLE ... DISABLE/ENABLE TRIGGER` -- exatamente o padrao
ja usado por `tests/f1/rbac/test_hash_chain.py`.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.marcacao.dominio.registro import DadosMarcacao, persistir_marcacao
from app.marcacao.dominio.verificacao_nsr import verificar_sequencia_nsr
from tests.f5.conftest import ContextoF5, aplicar_tenant_teste

ERRCODE_IMUTAVEL = "42501"


async def _gravar_marcacao_de_teste(
    sessao: AsyncSession, contexto: ContextoF5, *, external_id: str
) -> tuple[uuid.UUID, dt.datetime]:
    dados = DadosMarcacao(
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
    marcacao = await persistir_marcacao(sessao, tenant_id=contexto.tenant_id, dados=dados)
    await sessao.flush()
    return marcacao.id, marcacao.datahora_marcacao


async def test_update_e_delete_bloqueados_em_marcacoes(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    marcacao_id, datahora = await _gravar_marcacao_de_teste(
        sessao_f5, contexto_f5, external_id="ext-imut-marcacoes"
    )
    await sessao_f5.commit()
    await aplicar_tenant_teste(sessao_f5, contexto_f5.tenant_id)

    with pytest.raises(DBAPIError) as excinfo_update:
        await sessao_f5.execute(
            text("UPDATE marcacoes SET canal = 'web' WHERE id = :id"), {"id": marcacao_id}
        )
    assert getattr(excinfo_update.value.orig, "sqlstate", None) == ERRCODE_IMUTAVEL
    await sessao_f5.rollback()
    await aplicar_tenant_teste(sessao_f5, contexto_f5.tenant_id)

    with pytest.raises(DBAPIError) as excinfo_delete:
        await sessao_f5.execute(
            text("DELETE FROM marcacoes WHERE id = :id AND datahora_marcacao = :dh"),
            {"id": marcacao_id, "dh": datahora},
        )
    assert getattr(excinfo_delete.value.orig, "sqlstate", None) == ERRCODE_IMUTAVEL
    await sessao_f5.rollback()


async def test_update_e_delete_bloqueados_em_nsr_emissoes(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    await _gravar_marcacao_de_teste(sessao_f5, contexto_f5, external_id="ext-imut-nsr-emissoes")
    await sessao_f5.commit()
    await aplicar_tenant_teste(sessao_f5, contexto_f5.tenant_id)

    with pytest.raises(DBAPIError) as excinfo_update:
        await sessao_f5.execute(
            text(
                "UPDATE nsr_emissoes SET hash_registro = repeat('0', 64) "
                "WHERE tenant_id = :tenant_id AND rep_p_id = :rep_p_id AND nsr = 1"
            ),
            {"tenant_id": contexto_f5.tenant_id, "rep_p_id": contexto_f5.rep_p_id},
        )
    assert getattr(excinfo_update.value.orig, "sqlstate", None) == ERRCODE_IMUTAVEL
    await sessao_f5.rollback()
    await aplicar_tenant_teste(sessao_f5, contexto_f5.tenant_id)

    with pytest.raises(DBAPIError) as excinfo_delete:
        await sessao_f5.execute(
            text(
                "DELETE FROM nsr_emissoes "
                "WHERE tenant_id = :tenant_id AND rep_p_id = :rep_p_id AND nsr = 1"
            ),
            {"tenant_id": contexto_f5.tenant_id, "rep_p_id": contexto_f5.rep_p_id},
        )
    assert getattr(excinfo_delete.value.orig, "sqlstate", None) == ERRCODE_IMUTAVEL
    await sessao_f5.rollback()


async def test_update_e_delete_bloqueados_em_marcacao_idempotencia(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    marcacao_id, datahora = await _gravar_marcacao_de_teste(
        sessao_f5, contexto_f5, external_id="ext-imut-idempotencia"
    )
    idempotencia_id = uuid.uuid4()
    await sessao_f5.execute(
        text(
            "INSERT INTO marcacao_idempotencia "
            "(id, tenant_id, escopo, chave, marcacao_id, datahora_marcacao) "
            "VALUES (:id, :tenant_id, 'idempotency_key', :chave, :marcacao_id, :datahora)"
        ),
        {
            "id": idempotencia_id,
            "tenant_id": contexto_f5.tenant_id,
            "chave": f"chave-teste-{uuid.uuid4()}",
            "marcacao_id": marcacao_id,
            "datahora": datahora,
        },
    )
    await sessao_f5.commit()
    await aplicar_tenant_teste(sessao_f5, contexto_f5.tenant_id)

    with pytest.raises(DBAPIError) as excinfo_update:
        await sessao_f5.execute(
            text("UPDATE marcacao_idempotencia SET chave = 'outra' WHERE id = :id"),
            {"id": idempotencia_id},
        )
    assert getattr(excinfo_update.value.orig, "sqlstate", None) == ERRCODE_IMUTAVEL
    await sessao_f5.rollback()
    await aplicar_tenant_teste(sessao_f5, contexto_f5.tenant_id)

    with pytest.raises(DBAPIError) as excinfo_delete:
        await sessao_f5.execute(
            text("DELETE FROM marcacao_idempotencia WHERE id = :id"), {"id": idempotencia_id}
        )
    assert getattr(excinfo_delete.value.orig, "sqlstate", None) == ERRCODE_IMUTAVEL
    await sessao_f5.rollback()


async def test_update_e_delete_bloqueados_em_comprovantes(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    marcacao_id, datahora = await _gravar_marcacao_de_teste(
        sessao_f5, contexto_f5, external_id="ext-imut-comprovantes"
    )
    comprovante_id = uuid.uuid4()
    await sessao_f5.execute(
        text(
            "INSERT INTO comprovantes "
            "(id, tenant_id, marcacao_id, marcacao_datahora, cpf, numero, nsr, "
            " conteudo_texto, hash_sha256) "
            "VALUES (:id, :tenant_id, :marcacao_id, :datahora, :cpf, :numero, 1, "
            "        'COMPROVANTE DE TESTE', repeat('a', 64))"
        ),
        {
            "id": comprovante_id,
            "tenant_id": contexto_f5.tenant_id,
            "marcacao_id": marcacao_id,
            "datahora": datahora,
            "cpf": contexto_f5.colaborador_cpf,
            "numero": f"NUM-{uuid.uuid4().hex[:12]}",
        },
    )
    await sessao_f5.commit()
    await aplicar_tenant_teste(sessao_f5, contexto_f5.tenant_id)

    with pytest.raises(DBAPIError) as excinfo_update:
        await sessao_f5.execute(
            text("UPDATE comprovantes SET numero = 'outro' WHERE id = :id"),
            {"id": comprovante_id},
        )
    assert getattr(excinfo_update.value.orig, "sqlstate", None) == ERRCODE_IMUTAVEL
    await sessao_f5.rollback()
    await aplicar_tenant_teste(sessao_f5, contexto_f5.tenant_id)

    with pytest.raises(DBAPIError) as excinfo_delete:
        await sessao_f5.execute(
            text("DELETE FROM comprovantes WHERE id = :id"), {"id": comprovante_id}
        )
    assert getattr(excinfo_delete.value.orig, "sqlstate", None) == ERRCODE_IMUTAVEL
    await sessao_f5.rollback()


async def test_verificador_detecta_remocao_por_superusuario(
    sessao_f5: AsyncSession,
    contexto_f5: ContextoF5,
    admin_engine_sync_f5: sa.engine.Engine,
) -> None:
    """A role da aplicacao nao consegue apagar a linha (testes acima); aqui
    simulamos deliberadamente uma remocao adversarial via superusuario, que
    so e possivel desligando o gatilho de imutabilidade na mao -- e
    exatamente o cenario que `verificarSequenciaNsr` existe para acusar."""
    for indice in range(3):
        await _gravar_marcacao_de_teste(sessao_f5, contexto_f5, external_id=f"ext-lacuna-{indice}")
    await sessao_f5.commit()

    with admin_engine_sync_f5.begin() as conexao:
        conexao.execute(
            text("ALTER TABLE nsr_emissoes DISABLE TRIGGER trg_nsr_emissoes_bloqueia_delete")
        )
        try:
            conexao.execute(
                text(
                    "DELETE FROM nsr_emissoes "
                    "WHERE tenant_id = :tenant_id AND rep_p_id = :rep_p_id AND nsr = 2"
                ),
                {"tenant_id": str(contexto_f5.tenant_id), "rep_p_id": str(contexto_f5.rep_p_id)},
            )
        finally:
            conexao.execute(
                text("ALTER TABLE nsr_emissoes ENABLE TRIGGER trg_nsr_emissoes_bloqueia_delete")
            )

    await aplicar_tenant_teste(sessao_f5, contexto_f5.tenant_id)
    resultado = await verificar_sequencia_nsr(
        sessao_f5,
        tenant_id=contexto_f5.tenant_id,
        rep_p_id=contexto_f5.rep_p_id,
        nsr_de=1,
        nsr_ate=3,
    )

    assert resultado.integro is False
    assert resultado.total_esperado == 3
    assert resultado.total_encontrado == 2
    assert resultado.lacunas == {"faixas": [{"nsrDe": 2, "nsrAte": 2}]}
