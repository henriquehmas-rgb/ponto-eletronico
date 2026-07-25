"""Grupo 11 - Fechamento e espelho.

`periodos`, `fechamentos`, `espelhos` e `assinaturas_espelho`.

Fechado, o dia nao recalcula. A reabertura e sempre nominal e justificada,
garantido por CHECK, e fica na auditoria. O espelho oficial e o documento que o
colaborador assina; retificacao gera versao nova, jamais sobrescreve.
"""

from __future__ import annotations

import datetime as _datetime
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import BYTEA, INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .mixins import (
    AuditoriaMixin,
    ChavePrimariaUUIDMixin,
    CriacaoMixin,
    TenantMixin,
    TimestampMixin,
)
from .tipos import DOM_COMPETENCIA, DOM_SHA256

__all__ = ["AssinaturaEspelho", "Espelho", "Fechamento", "Periodo"]


class Periodo(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Janela de apuracao da empresa."""

    __tablename__ = "periodos"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="RESTRICT"), nullable=False
    )
    codigo: Mapped[str] = mapped_column(nullable=False)
    tipo: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'mensal'"))
    data_inicio: Mapped[_datetime.date] = mapped_column(nullable=False)
    data_fim: Mapped[_datetime.date] = mapped_column(nullable=False)
    competencia_folha: Mapped[str | None] = mapped_column(DOM_COMPETENCIA)
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'aberto'"))

    __table_args__ = (
        sa.CheckConstraint(
            "tipo IN ('mensal','quinzenal','semanal','personalizado','banco_horas')",
            name="periodos_tipo_check",
        ),
        sa.CheckConstraint(
            "status IN ('aberto','em_conferencia','fechado','reaberto','exportado')",
            name="periodos_status_check",
        ),
        sa.UniqueConstraint("tenant_id", "empresa_id", "tipo", "codigo", name="uq_periodos_codigo"),
        sa.CheckConstraint("data_fim >= data_inicio", name="ck_periodos_intervalo"),
        sa.Index("ix_periodos_empresa", "tenant_id", "empresa_id", sa.text("data_inicio DESC")),
        {
            "comment": (
                "Janela de apuracao da empresa. O periodo do ponto e independente do "
                "periodo do banco de horas."
            )
        },
    )


class Fechamento(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Trava do periodo para um escopo."""

    __tablename__ = "fechamentos"

    periodo_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("periodos.id", ondelete="RESTRICT"), nullable=False
    )
    empresa_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="RESTRICT"), nullable=False
    )
    unidade_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("unidades.id", ondelete="RESTRICT")
    )
    departamento_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("departamentos.id", ondelete="RESTRICT")
    )
    escopo: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'empresa'"))
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'em_andamento'"))
    total_colaboradores: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    total_ocorrencias: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    total_pendencias: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    hash_conteudo: Mapped[str | None] = mapped_column(DOM_SHA256)
    conferido_em: Mapped[_datetime.datetime | None] = mapped_column()
    conferido_por: Mapped[uuid.UUID | None] = mapped_column()
    fechado_em: Mapped[_datetime.datetime | None] = mapped_column()
    fechado_por: Mapped[uuid.UUID | None] = mapped_column()
    reaberto_em: Mapped[_datetime.datetime | None] = mapped_column()
    reaberto_por: Mapped[uuid.UUID | None] = mapped_column()
    motivo_reabertura: Mapped[str | None] = mapped_column()
    exportado_em: Mapped[_datetime.datetime | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "escopo IN ('empresa','unidade','departamento','equipe','colaborador')",
            name="fechamentos_escopo_check",
        ),
        sa.CheckConstraint(
            "status IN ('em_andamento','conferido','fechado','reaberto','cancelado')",
            name="fechamentos_status_check",
        ),
        sa.CheckConstraint(
            "reaberto_em IS NULL OR "
            "(motivo_reabertura IS NOT NULL AND reaberto_por IS NOT NULL)",
            name="ck_fechamentos_reabertura",
        ),
        sa.Index("ix_fechamentos_periodo", "tenant_id", "periodo_id", "status"),
        sa.Index("ix_fechamentos_empresa", "tenant_id", "empresa_id", sa.text("fechado_em DESC")),
        {
            "comment": (
                "Trava do periodo para um escopo. Fechado, o dia nao recalcula. A "
                "reabertura e sempre nominal e justificada, garantido por CHECK."
            )
        },
    )


class Espelho(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Espelho de ponto do periodo para um vinculo."""

    __tablename__ = "espelhos"

    periodo_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("periodos.id", ondelete="RESTRICT"), nullable=False
    )
    fechamento_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("fechamentos.id", ondelete="RESTRICT")
    )
    colaborador_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("colaboradores.id", ondelete="RESTRICT"), nullable=False
    )
    vinculo_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("vinculos.id", ondelete="RESTRICT"), nullable=False
    )
    versao: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("1"))
    tipo: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'previo'"))
    conteudo: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    conteudo_ref: Mapped[str | None] = mapped_column()
    hash_sha256: Mapped[str] = mapped_column(DOM_SHA256, nullable=False)
    total_previsto_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    total_trabalhado_minutos: Mapped[int] = mapped_column(
        nullable=False, server_default=sa.text("0")
    )
    total_extras_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    total_faltas_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    total_noturno_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    saldo_banco_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    gerado_em: Mapped[_datetime.datetime] = mapped_column(
        nullable=False, server_default=sa.text("now()")
    )
    gerado_por: Mapped[uuid.UUID | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint("versao >= 1", name="espelhos_versao_check"),
        sa.CheckConstraint("tipo IN ('previo','oficial','retificado')", name="espelhos_tipo_check"),
        sa.UniqueConstraint(
            "tenant_id", "periodo_id", "vinculo_id", "versao", name="uq_espelhos_versao"
        ),
        sa.Index(
            "ix_espelhos_colaborador", "tenant_id", "colaborador_id", sa.text("gerado_em DESC")
        ),
        sa.Index(
            "ix_espelhos_fechamento",
            "tenant_id",
            "fechamento_id",
            postgresql_where=sa.text("fechamento_id IS NOT NULL"),
        ),
        {
            "comment": (
                "Espelho de ponto do periodo para um vinculo. O tipo oficial e emitido no "
                "fechamento e e o documento que o colaborador assina."
            )
        },
    )


class AssinaturaEspelho(ChavePrimariaUUIDMixin, TenantMixin, CriacaoMixin, Base):
    """Aceite eletronico do espelho de ponto. APPEND-ONLY."""

    __tablename__ = "assinaturas_espelho"

    espelho_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("espelhos.id", ondelete="RESTRICT"), nullable=False
    )
    signatario_tipo: Mapped[str] = mapped_column(nullable=False)
    signatario_usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    signatario_colaborador_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("colaboradores.id", ondelete="SET NULL")
    )
    metodo: Mapped[str] = mapped_column(
        nullable=False, server_default=sa.text("'aceite_eletronico'")
    )
    hash_assinado: Mapped[str] = mapped_column(DOM_SHA256, nullable=False)
    assinatura: Mapped[bytes | None] = mapped_column(BYTEA)
    certificado_ref: Mapped[str | None] = mapped_column()
    carimbo_tempo: Mapped[_datetime.datetime] = mapped_column(
        nullable=False, server_default=sa.text("now()")
    )
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column()
    geolocalizacao: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'pendente'"))
    recusa_motivo: Mapped[str | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "signatario_tipo IN ('colaborador','gestor','rh','empregador')",
            name="assinaturas_espelho_signatario_tipo_check",
        ),
        sa.CheckConstraint(
            "metodo IN ('aceite_eletronico','icp_brasil','biometria','senha','token_email')",
            name="assinaturas_espelho_metodo_check",
        ),
        sa.CheckConstraint(
            "status IN ('pendente','assinado','recusado','expirado')",
            name="assinaturas_espelho_status_check",
        ),
        sa.Index(
            "uq_assinaturas_espelho",
            "tenant_id",
            "espelho_id",
            "signatario_tipo",
            sa.text(
                "COALESCE(signatario_colaborador_id, "
                "'00000000-0000-0000-0000-000000000000'::uuid)"
            ),
            unique=True,
            postgresql_where=sa.text("status = 'assinado'"),
        ),
        sa.Index("ix_assinaturas_espelho_espelho", "tenant_id", "espelho_id"),
        {
            "comment": (
                "Aceite eletronico do espelho de ponto. Append-only: recusar e depois "
                "assinar gera duas linhas, preservando o historico."
            )
        },
    )
