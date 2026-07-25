"""Base declarativa comum a todos os models do contrato de dados.

Este modulo define a unica `Base` do monorepo. Toda tabela de
`packages/contracts/schema.sql` tem um model declarativo pendurado nela, e
`Base.metadata` e o alvo do `target_metadata` do Alembic (ver
`apps/api/migrations/env.py`).

Convencoes herdadas de `schema.sql` (secao "Convencoes"):

1. Nomes de tabela e coluna em portugues do Brasil, snake_case.
2. Chave primaria UUID v4 (`gen_random_uuid()`) em todas as tabelas.
3. Enums de dominio sao TEXT + CHECK. Nao ha tipo ENUM nativo no modelo.
4. Auditoria: `criado_em` / `criado_por` / `atualizado_em` / `atualizado_por`.
   Tabelas append-only nao possuem `atualizado_em` / `atualizado_por`.
5. Soft delete (`excluido_em` / `excluido_por`) SOMENTE em cadastros.
6. Todas as colunas de tempo sao TIMESTAMPTZ. Datas civis sao DATE.
7. Duracoes sao INTEGER em MINUTOS (nunca float, nunca interval).
8. Todo dado de dominio carrega `tenant_id` e esta sob Row Level Security.
"""

from __future__ import annotations

import datetime as _datetime
import decimal
import uuid
from typing import Any, ClassVar

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase

__all__ = [
    "CONVENCAO_NOMES",
    "ORDEM_ATUALIZADO_EM",
    "ORDEM_ATUALIZADO_POR",
    "ORDEM_CRIADO_EM",
    "ORDEM_CRIADO_POR",
    "ORDEM_EXCLUIDO_EM",
    "ORDEM_EXCLUIDO_POR",
    "ORDEM_ID",
    "ORDEM_TENANT",
    "Base",
    "agora_no_banco",
    "metadata_contrato",
    "uuid_v4_no_banco",
]

# -----------------------------------------------------------------------------
# Convencao de nomes
#
# Reproduz o que o PostgreSQL geraria sozinho para PRIMARY KEY e FOREIGN KEY,
# de modo que os nomes produzidos por estes models sejam identicos aos de
# schema.sql. Constraints UNIQUE, CHECK, EXCLUDE e todos os indices sao SEMPRE
# nomeados explicitamente no model, exatamente como no contrato.
# -----------------------------------------------------------------------------
CONVENCAO_NOMES: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "fk": "%(table_name)s_%(column_0_name)s_fkey",
    "pk": "%(table_name)s_pkey",
}

metadata_contrato = sa.MetaData(naming_convention=CONVENCAO_NOMES)


# -----------------------------------------------------------------------------
# Ordem das colunas no DDL
#
# `mapped_column(sort_order=...)` existe para que as colunas herdadas dos mixins
# nao apareçam antes das colunas proprias da tabela. Sem isso o DDL gerado sairia
# com `criado_em` na frente de `id`, divergindo de schema.sql sem necessidade.
# -----------------------------------------------------------------------------
ORDEM_ID = -100
ORDEM_TENANT = -90
ORDEM_CRIADO_EM = 900
ORDEM_CRIADO_POR = 901
ORDEM_ATUALIZADO_EM = 902
ORDEM_ATUALIZADO_POR = 903
ORDEM_EXCLUIDO_EM = 910
ORDEM_EXCLUIDO_POR = 911


def agora_no_banco() -> sa.TextClause:
    """`now()` do PostgreSQL. O relogio do servidor e a fonte de verdade."""
    return sa.text("now()")


def uuid_v4_no_banco() -> sa.TextClause:
    """`gen_random_uuid()` da extensao pgcrypto."""
    return sa.text("gen_random_uuid()")


class Base(DeclarativeBase):
    """Base declarativa unica do contrato de dados."""

    metadata = metadata_contrato

    type_annotation_map: ClassVar[dict[Any, Any]] = {
        uuid.UUID: sa.Uuid(as_uuid=True),
        _datetime.datetime: sa.DateTime(timezone=True),
        _datetime.date: sa.Date(),
        _datetime.time: sa.Time(),
        str: sa.Text(),
        int: sa.Integer(),
        bool: sa.Boolean(),
        bytes: sa.LargeBinary(),
        decimal.Decimal: sa.Numeric(),
        dict[str, Any]: JSONB(),
        list[str]: ARRAY(sa.Text()),
        list[int]: ARRAY(sa.Integer()),
    }

    def __repr__(self) -> str:  # pragma: no cover - conveniencia de depuracao
        identificador = getattr(self, "id", None)
        return f"<{type(self).__name__} id={identificador}>"
