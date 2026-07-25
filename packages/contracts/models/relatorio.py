"""Grupo 15 - Relatorios.

`relatorio_definicoes`, `relatorio_agendamentos`, `relatorio_execucoes` e
`preferencias_colunas`.

`relatorio_definicoes.dataset` e um identificador de conjunto de dados no
backend - NUNCA SQL cru vindo do usuario. E isso que impede injecao por
configuracao de relatorio.
"""

from __future__ import annotations

import datetime as _datetime
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .mixins import (
    AuditoriaMixin,
    ChavePrimariaUUIDMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)
from .tipos import DOM_FUSO, DOM_SHA256

__all__ = [
    "PreferenciaColunas",
    "RelatorioAgendamento",
    "RelatorioDefinicao",
    "RelatorioExecucao",
]


class RelatorioDefinicao(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Catalogo dos relatorios disponiveis."""

    __tablename__ = "relatorio_definicoes"

    codigo: Mapped[str] = mapped_column(nullable=False)
    nome: Mapped[str] = mapped_column(nullable=False)
    descricao: Mapped[str | None] = mapped_column()
    categoria: Mapped[str] = mapped_column(nullable=False)
    sistema: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))
    dataset: Mapped[str] = mapped_column(nullable=False)
    colunas_disponiveis: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )
    filtros_disponiveis: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )
    agrupamentos: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )
    formatos: Mapped[list[str]] = mapped_column(
        ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{csv,xlsx,pdf}'")
    )
    permissao_codigo: Mapped[str | None] = mapped_column()
    assincrono: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))
    ativo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))

    __table_args__ = (
        sa.CheckConstraint(
            "categoria IN ('operacional','gerencial','fiscal','financeiro','lgpd')",
            name="relatorio_definicoes_categoria_check",
        ),
        sa.Index(
            "uq_relatorio_definicoes_codigo",
            "tenant_id",
            "codigo",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        {
            "comment": (
                "Catalogo dos relatorios disponiveis. Os 24 relatorios do produto sao "
                "semeados por tenant com sistema = true."
            )
        },
    )


class RelatorioAgendamento(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Envio recorrente de relatorio."""

    __tablename__ = "relatorio_agendamentos"

    relatorio_definicao_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("relatorio_definicoes.id", ondelete="CASCADE"), nullable=False
    )
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    nome: Mapped[str] = mapped_column(nullable=False)
    parametros: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    formato: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'pdf'"))
    cron: Mapped[str] = mapped_column(nullable=False)
    fuso_horario: Mapped[str] = mapped_column(
        DOM_FUSO, nullable=False, server_default=sa.text("'America/Sao_Paulo'")
    )
    canal: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'email'"))
    destinatarios: Mapped[list[str]] = mapped_column(
        ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")
    )
    ativo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))
    ultima_execucao_em: Mapped[_datetime.datetime | None] = mapped_column()
    proxima_execucao_em: Mapped[_datetime.datetime | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "formato IN ('csv','xlsx','pdf','json')", name="relatorio_agendamentos_formato_check"
        ),
        sa.CheckConstraint(
            "canal IN ('email','webhook','minio')", name="relatorio_agendamentos_canal_check"
        ),
        sa.Index(
            "uq_relatorio_agendamentos_nome",
            "tenant_id",
            "nome",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index(
            "ix_relatorio_agendamentos_proxima",
            "tenant_id",
            "proxima_execucao_em",
            postgresql_where=sa.text("ativo"),
        ),
        {
            "comment": (
                "Envio recorrente de relatorio. A expressao cron e interpretada no fuso "
                "indicado, nao no fuso do servidor."
            )
        },
    )


class RelatorioExecucao(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Execucao de um relatorio, sincrona ou assincrona."""

    __tablename__ = "relatorio_execucoes"

    relatorio_definicao_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("relatorio_definicoes.id", ondelete="RESTRICT"), nullable=False
    )
    agendamento_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("relatorio_agendamentos.id", ondelete="SET NULL")
    )
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    parametros: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    formato: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'csv'"))
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'enfileirado'"))
    progresso: Mapped[int] = mapped_column(
        sa.SmallInteger, nullable=False, server_default=sa.text("0")
    )
    total_linhas: Mapped[int | None] = mapped_column(sa.BigInteger)
    conteudo_ref: Mapped[str | None] = mapped_column()
    tamanho_bytes: Mapped[int | None] = mapped_column(sa.BigInteger)
    hash_sha256: Mapped[str | None] = mapped_column(DOM_SHA256)
    iniciado_em: Mapped[_datetime.datetime | None] = mapped_column()
    concluido_em: Mapped[_datetime.datetime | None] = mapped_column()
    duracao_ms: Mapped[int | None] = mapped_column()
    expira_em: Mapped[_datetime.datetime | None] = mapped_column()
    erro: Mapped[str | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "formato IN ('csv','xlsx','pdf','json')", name="relatorio_execucoes_formato_check"
        ),
        sa.CheckConstraint(
            "status IN ('enfileirado','processando','concluido','falhou','cancelado',"
            "'expirado')",
            name="relatorio_execucoes_status_check",
        ),
        sa.CheckConstraint(
            "progresso BETWEEN 0 AND 100", name="relatorio_execucoes_progresso_check"
        ),
        sa.CheckConstraint(
            "tamanho_bytes IS NULL OR tamanho_bytes >= 0",
            name="relatorio_execucoes_tamanho_bytes_check",
        ),
        sa.CheckConstraint(
            "duracao_ms IS NULL OR duracao_ms >= 0", name="relatorio_execucoes_duracao_ms_check"
        ),
        sa.Index(
            "ix_relatorio_execucoes_usuario",
            "tenant_id",
            "usuario_id",
            sa.text("criado_em DESC"),
        ),
        sa.Index(
            "ix_relatorio_execucoes_fila",
            "tenant_id",
            "status",
            "criado_em",
            postgresql_where=sa.text("status IN ('enfileirado','processando')"),
        ),
        {
            "comment": (
                "Execucao de um relatorio, sincrona ou assincrona. Guarda parametros, "
                "progresso e o artefato gerado, com expiracao."
            )
        },
    )


class PreferenciaColunas(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Layout de colunas salvo por usuario, para relatorios e grades da interface."""

    __tablename__ = "preferencias_colunas"

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    relatorio_definicao_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("relatorio_definicoes.id", ondelete="CASCADE")
    )
    tela: Mapped[str | None] = mapped_column()
    nome: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'padrao'"))
    colunas: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    ordenacao: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    filtros: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    larguras: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    padrao: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))

    __table_args__ = (
        sa.CheckConstraint(
            "relatorio_definicao_id IS NOT NULL OR tela IS NOT NULL",
            name="ck_preferencias_colunas_alvo",
        ),
        sa.Index(
            "uq_preferencias_colunas",
            "tenant_id",
            "usuario_id",
            sa.text(
                "COALESCE(relatorio_definicao_id, " "'00000000-0000-0000-0000-000000000000'::uuid)"
            ),
            sa.text("COALESCE(tela, '')"),
            "nome",
            unique=True,
        ),
        {
            "comment": (
                "Layout de colunas salvo por usuario, tanto para relatorios quanto para "
                "grades da interface."
            )
        },
    )
