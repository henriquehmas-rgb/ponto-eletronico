"""A2 -- auditoria de RLS (PCF F14 §5: "script de auditoria que confirma
policy em toda tabela tenant_id"; critério de aceite: "RLS audit não
encontra tabela tenant_id sem policy").

Estende o padrão já estabelecido por `tests/f1/tenancy/test_catalogo_rls.py`
(T3 da F1) -- não reescreve policy manualmente tabela por tabela: a consulta
já é genérica (percorre `pg_class`/`pg_attribute`/`pg_policies` em tempo de
execução, não uma lista hardcoded de nomes), então ela automaticamente cobre
QUALQUER tabela nova criada por F2-F13 desde que a F1 escreveu o padrão --
esta cópia (mesma consulta, executada de novo contra o schema COMPLETO
pós-F1-F13) é o "gate" desta fase: se alguma tabela nova tivesse ficado sem
`ENABLE ROW LEVEL SECURITY`/`FORCE ROW LEVEL SECURITY`/a policy
`pol_isolamento_tenant`, este teste falharia.

Resultado desta auditoria (F14/A2, ver relatório da fase): a suíte de F1 já
cobre 100% das tabelas atuais -- rodada contra o schema completo (F1-F13,
`alembic upgrade head`), nenhuma tabela com `tenant_id` ficou sem RLS. Nada
foi corrigido nesta fase porque a auditoria não encontrou lacuna real.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

#: Mesmas duas exceções documentadas em `tests/f1/tenancy/test_catalogo_rls.py`
#: e no glossário do projeto (seção 3.2): `tenants` é isolada por `id`, não
#: por `tenant_id`; `permissoes` é catálogo global, sem `tenant_id`.
EXCECOES_SEM_TENANT_ID = frozenset({"tenants", "permissoes"})

_CONSULTA_TABELAS_COM_TENANT_ID = """
    SELECT DISTINCT c.relname
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relkind IN ('r', 'p')
       AND EXISTS (
             SELECT 1 FROM pg_attribute a
              WHERE a.attrelid = c.oid
                AND a.attname = 'tenant_id'
                AND NOT a.attisdropped
           )
     ORDER BY c.relname
"""

_CONSULTA_RLS_DA_TABELA = """
    SELECT c.relrowsecurity, c.relforcerowsecurity,
           EXISTS (
             SELECT 1 FROM pg_policies p
              WHERE p.schemaname = 'public'
                AND p.tablename = c.relname
                AND p.policyname = 'pol_isolamento_tenant'
           ) AS tem_policy
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relname = :nome
"""

_CONSULTA_TABELAS_SEM_TENANT_ID = """
    SELECT c.relname
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relkind IN ('r', 'p')
       AND c.relispartition = FALSE
       AND c.relname <> 'alembic_version'
       AND NOT EXISTS (
             SELECT 1 FROM pg_attribute a
              WHERE a.attrelid = c.oid
                AND a.attname = 'tenant_id'
                AND NOT a.attisdropped
           )
     ORDER BY c.relname
"""


async def test_toda_tabela_com_tenant_id_tem_rls_forcada_e_policy(
    engine_f14a2: AsyncEngine,
) -> None:
    """Critério de aceite de A2: "RLS audit não encontra tabela tenant_id
    sem policy" -- roda contra o schema completo (F1-F13) desta suíte."""
    fabrica: async_sessionmaker[AsyncSession] = async_sessionmaker(engine_f14a2)
    async with fabrica() as sessao:
        tabelas = (await sessao.execute(text(_CONSULTA_TABELAS_COM_TENANT_ID))).scalars().all()
        assert tabelas, "nenhuma tabela com tenant_id encontrada -- migracao nao aplicada?"

        sem_rls: list[str] = []
        sem_force: list[str] = []
        sem_policy: list[str] = []
        for nome in tabelas:
            linha = (await sessao.execute(text(_CONSULTA_RLS_DA_TABELA), {"nome": nome})).one()
            if not linha.relrowsecurity:
                sem_rls.append(nome)
            if not linha.relforcerowsecurity:
                sem_force.append(nome)
            if not linha.tem_policy:
                sem_policy.append(nome)

        assert sem_rls == [], f"tabelas com tenant_id sem ENABLE ROW LEVEL SECURITY: {sem_rls}"
        assert sem_force == [], f"tabelas com tenant_id sem FORCE ROW LEVEL SECURITY: {sem_force}"
        assert (
            sem_policy == []
        ), f"tabelas com tenant_id sem a policy pol_isolamento_tenant: {sem_policy}"


async def test_excecoes_sao_exatamente_tenants_e_permissoes(engine_f14a2: AsyncEngine) -> None:
    """Nenhuma tabela nova de F2-F13 escapou de `tenant_id` além das duas
    exceções conscientes já documentadas."""
    fabrica: async_sessionmaker[AsyncSession] = async_sessionmaker(engine_f14a2)
    async with fabrica() as sessao:
        sem_tenant_id = set(
            (await sessao.execute(text(_CONSULTA_TABELAS_SEM_TENANT_ID))).scalars().all()
        )

    faltando_das_excecoes = EXCECOES_SEM_TENANT_ID - sem_tenant_id
    assert (
        faltando_das_excecoes == set()
    ), f"tabelas esperadas sem tenant_id que sumiram do banco: {faltando_das_excecoes}"
    extras_inesperadas = sem_tenant_id - EXCECOES_SEM_TENANT_ID
    assert extras_inesperadas == set(), (
        "tabela(s) de dominio sem tenant_id alem das duas excecoes documentadas "
        f"(tenants, permissoes): {extras_inesperadas}. Se for legitimo, "
        "atualize o glossario (secao 3.2) e este teste (mais o original de "
        "tests/f1/tenancy/test_catalogo_rls.py) juntos."
    )
