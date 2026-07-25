"""Grupo 1 - Tenancy: `tenants` e `tenant_configuracoes`.

Raiz da multi-tenancy. `tenants` e a unica tabela de dominio sem coluna
`tenant_id`: ela e o proprio tenant, e por isso a RLS dela compara `id` em vez
de `tenant_id` (declarada explicitamente na migration inicial).

Nota sobre nomes de constraint: as clausulas CHECK que em `schema.sql` sao
declaradas inline na coluna recebem aqui o nome que o proprio PostgreSQL geraria
(`<tabela>_<coluna>_check`), de modo que o DDL produzido pelos models seja
identico ao do contrato. Constraints ja nomeadas em `schema.sql` mantem o nome.
"""

from __future__ import annotations

import datetime as _datetime
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import ORDEM_TENANT, Base
from .mixins import (
    AuditoriaMixin,
    ChavePrimariaUUIDMixin,
    SoftDeleteMixin,
    TimestampMixin,
)
from .tipos import DOM_CNPJ, DOM_FUSO

__all__ = ["Tenant", "TenantConfiguracao"]


class Tenant(ChavePrimariaUUIDMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base):
    """Cliente do SaaS. Contem uma ou varias empresas (CNPJs)."""

    __tablename__ = "tenants"

    slug: Mapped[str] = mapped_column(nullable=False)
    razao_social: Mapped[str] = mapped_column(nullable=False)
    nome_exibicao: Mapped[str] = mapped_column(nullable=False)
    documento: Mapped[str | None] = mapped_column(DOM_CNPJ)
    plano: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'padrao'"))
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'trial'"))
    fuso_horario: Mapped[str] = mapped_column(
        DOM_FUSO, nullable=False, server_default=sa.text("'America/Sao_Paulo'")
    )
    locale: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'pt-BR'"))
    dominio_proprio: Mapped[str | None] = mapped_column()
    limite_colaboradores: Mapped[int | None] = mapped_column()
    data_contratacao: Mapped[_datetime.date | None] = mapped_column()
    data_cancelamento: Mapped[_datetime.date | None] = mapped_column()

    __table_args__ = (
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
        sa.CheckConstraint(
            "plano IN ('trial','padrao','avancado','enterprise')",
            name="tenants_plano_check",
        ),
        sa.CheckConstraint(
            "status IN ('trial','ativo','suspenso','cancelado')",
            name="tenants_status_check",
        ),
        sa.CheckConstraint(
            r"slug ~ '^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$'",
            name="ck_tenants_slug_formato",
        ),
        sa.Index(
            "ix_tenants_dominio_proprio",
            "dominio_proprio",
            unique=True,
            postgresql_where=sa.text("dominio_proprio IS NOT NULL"),
        ),
        sa.Index(
            "ix_tenants_status",
            "status",
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        {
            "comment": (
                "Raiz da multi-tenancy. Cada tenant e um cliente do SaaS e pode conter "
                "varias empresas (CNPJs). Unica tabela de dominio sem coluna tenant_id: "
                "ela e o proprio tenant."
            )
        },
    )


class TenantConfiguracao(ChavePrimariaUUIDMixin, TimestampMixin, AuditoriaMixin, Base):
    """Configuracoes chave/valor por tenant."""

    __tablename__ = "tenant_configuracoes"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        sort_order=ORDEM_TENANT,
    )
    categoria: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'geral'"))
    chave: Mapped[str] = mapped_column(nullable=False)
    valor: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    descricao: Mapped[str | None] = mapped_column()
    somente_leitura: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))

    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "chave", name="uq_tenant_configuracoes"),
        sa.CheckConstraint(
            "categoria IN ('geral','seguranca','jornada','banco_horas','fiscal',"
            "'notificacao','integracao','lgpd','aparencia')",
            name="tenant_configuracoes_categoria_check",
        ),
        sa.Index("ix_tenant_configuracoes_categoria", "tenant_id", "categoria"),
        {
            "comment": (
                "Configuracoes chave/valor por tenant. Usada para parametros que nao "
                "merecem coluna propria (limiares, textos, feature flags)."
            )
        },
    )
