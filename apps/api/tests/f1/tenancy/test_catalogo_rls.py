"""T3 -- cobertura de RLS provada por catalogo (criterio de aceite 2 do PCF).

Percorre `pg_class`/`pg_attribute`/`pg_policies` e falha se QUALQUER tabela com
coluna `tenant_id` estiver sem `relrowsecurity`, sem `relforcerowsecurity` ou
sem a policy `pol_isolamento_tenant`. As unicas duas excecoes aceitas sao
`tenants` (isolada por `id`, nao por `tenant_id`) e `permissoes` (catalogo
global, sem `tenant_id`).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

#: As duas excecoes conscientes documentadas no glossario (secao 3.2) e no
#: PCF da fase (criterio de aceite 2). Nenhuma outra tabela pode faltar RLS.
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


async def test_toda_tabela_com_tenant_id_tem_rls_forcada_e_policy(
    fabrica_f1: async_sessionmaker[AsyncSession],
) -> None:
    """Criterio de aceite 2: nenhuma tabela de dominio escapa da RLS."""
    async with fabrica_f1() as sessao:
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


async def test_excecoes_sao_exatamente_tenants_e_permissoes(
    fabrica_f1: async_sessionmaker[AsyncSession],
) -> None:
    """`tenants` e `permissoes` sao as UNICAS tabelas de dominio sem `tenant_id`.

    Contrasta com o teste acima: aqui provamos que a lista de tabelas SEM
    `tenant_id` (entre as que evidentemente sao dominio, nao infraestrutura do
    Postgres) e exatamente as duas excecoes documentadas -- nem uma a mais.
    """
    consulta = """
        SELECT c.relname
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public'
           AND c.relkind IN ('r', 'p')
           AND c.relispartition = FALSE
           -- Infraestrutura do proprio Alembic, nao tabela de dominio do
           -- contrato: nao e uma terceira excecao, e simplesmente nao
           -- pertence ao universo que este teste avalia.
           AND c.relname <> 'alembic_version'
           AND NOT EXISTS (
                 SELECT 1 FROM pg_attribute a
                  WHERE a.attrelid = c.oid
                    AND a.attname = 'tenant_id'
                    AND NOT a.attisdropped
               )
         ORDER BY c.relname
    """
    async with fabrica_f1() as sessao:
        sem_tenant_id = set((await sessao.execute(text(consulta))).scalars().all())

    faltando_das_excecoes = EXCECOES_SEM_TENANT_ID - sem_tenant_id
    assert (
        faltando_das_excecoes == set()
    ), f"tabelas esperadas sem tenant_id que sumiram do banco: {faltando_das_excecoes}"
    extras_inesperadas = sem_tenant_id - EXCECOES_SEM_TENANT_ID
    assert extras_inesperadas == set(), (
        "tabela(s) de dominio sem tenant_id alem das duas excecoes documentadas "
        f"(tenants, permissoes): {extras_inesperadas}. Se for legitimo, atualize "
        "o glossario (secao 3.2) e este teste juntos -- e RFC se o contrato mudar."
    )
