"""Tabela `idempotencia_chaves` -- idempotência genérica (F13/A1, T3).

Revisao: 0002_idempotencia_chaves
Revisao anterior: 0001_inicial
Alvo: PostgreSQL 16

Única migration nova autorizada nesta fase (PCF F13 §5.4, nota sob a tabela de
ownership): `app.comum.idempotencia_generica` (T3) precisa de uma tabela
própria para `Depends(exigir_idempotencia())`/`abrir_operacao`/
`concluir_operacao`. NÃO replicada em `packages/contracts/schema.sql` nem em
`ponto_contracts` (pacote congelado fora das três RFCs nomeadas no PCF §2.1,
nenhuma delas cobre esta tabela) -- o modelo Python mora em
`app.comum.idempotencia_generica` como `sqlalchemy.Table` solto (Core), nunca
um segundo model ORM registrado num `Base` de pacote alheio. Ver docstring
daquele módulo para o desenho completo (trava consultiva, TTL de 24h,
replay).

Mesmo padrão de RLS/privilégio que TODA tabela com `tenant_id` recebe em
`schema.sql` seção 19/20 (o laço dinâmico daquela migration já rodou em
`0001_inicial` e não alcança tabelas criadas depois -- reaplica-se aqui à
mão, para esta tabela nova, exatamente as mesmas três instruções e o mesmo
GRANT/REVOKE que o laço aplicaria).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_idempotencia_chaves"
down_revision: str | None = "0001_inicial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOME_TABELA = "idempotencia_chaves"


def upgrade() -> None:
    op.create_table(
        _NOME_TABELA,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("escopo", sa.Text(), nullable=False),
        sa.Column("chave", sa.Text(), nullable=False),
        sa.Column("corpo_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("resposta_status", sa.Integer(), nullable=True),
        sa.Column("resposta_corpo", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('em_andamento','concluido')", name="ck_idempotencia_chaves_status"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="RESTRICT", name="fk_idempotencia_chaves_tenant"
        ),
        sa.UniqueConstraint(
            "tenant_id", "escopo", "chave", name="uq_idempotencia_chaves_tenant_escopo_chave"
        ),
        comment=(
            "Idempotência genérica de escrita (F13/T3): uma linha por "
            "(tenant, escopo, Idempotency-Key), com o corpo da resposta "
            "original para replay dentro do TTL de 24h."
        ),
    )
    op.create_index(
        "ix_idempotencia_chaves_expira",
        _NOME_TABELA,
        ["expira_em"],
    )

    # RLS -- mesmo template de `schema.sql` seção 19, aplicado à mão para esta
    # tabela nova (o laço dinâmico daquela migration só cobriu as tabelas que
    # já existiam quando `0001_inicial` rodou).
    op.execute(f"ALTER TABLE {_NOME_TABELA} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_NOME_TABELA} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY pol_isolamento_tenant ON {_NOME_TABELA} "
        "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
    )

    # Privilégios -- mesmo padrão de `schema.sql` seção 20 (tolera ausência da
    # role, para a migration continuar executável num Postgres sem os roles
    # provisionados, mesma defesa que `0001_inicial` já usa).
    # `_NOME_TABELA` e constante de modulo (nunca entrada de usuario) -- o
    # f-string so escolhe o nome da tabela desta migration, mesmo espirito de
    # `EXECUTE format(...)` que `0001_inicial.py` usa com identificador
    # dinamico. `
    # entrada externa.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ponto_app') THEN
                EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON {_NOME_TABELA} TO ponto_app';
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ponto_leitura') THEN
                EXECUTE 'GRANT SELECT ON {_NOME_TABELA} TO ponto_leitura';
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ponto_suporte') THEN
                EXECUTE 'GRANT SELECT ON {_NOME_TABELA} TO ponto_suporte';
            END IF;
        EXCEPTION
            WHEN insufficient_privilege THEN
                RAISE NOTICE 'Sem privilegio para conceder permissoes em {_NOME_TABELA}.';
        END $$;
        """  # noqa: S608
    )


def downgrade() -> None:
    op.drop_table(_NOME_TABELA)
