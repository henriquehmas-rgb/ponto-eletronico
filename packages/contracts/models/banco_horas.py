"""Grupo 9 - Banco de horas.

`bh_politicas`, `bh_contas`, `bh_lancamentos`, `bh_saldos` e `bh_quitacoes`.

O limite legal esta no proprio schema: acordo individual escrito compensa em
ate 6 meses; acordo ou convencao coletiva, em ate 12. O teto de 10 horas
diarias vive em `bh_politicas.limite_jornada_diaria_minutos`.

`bh_lancamentos` e o EXTRATO IMUTAVEL, com cadeia de hash. Gatilhos barram
DELETE, TRUNCATE e qualquer UPDATE que nao seja exclusivamente em
`consumido_minutos` - unica excecao do modelo inteiro, exigida pela rotina de
consumo FIFO/LIFO. Corrigir um lancamento significa emitir um estorno.
"""

from __future__ import annotations

import datetime as _datetime
import decimal
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .mixins import (
    AuditoriaMixin,
    ChavePrimariaUUIDMixin,
    CriacaoMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)
from .tipos import DOM_COMPETENCIA, DOM_SHA256

__all__ = [
    "BhConta",
    "BhLancamento",
    "BhPolitica",
    "BhQuitacao",
    "BhSaldo",
]


class BhPolitica(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Regras do banco de horas por empresa."""

    __tablename__ = "bh_politicas"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="RESTRICT"), nullable=False
    )
    codigo: Mapped[str] = mapped_column(nullable=False)
    nome: Mapped[str] = mapped_column(nullable=False)
    descricao: Mapped[str | None] = mapped_column()
    regime: Mapped[str] = mapped_column(nullable=False)
    periodo_meses: Mapped[int] = mapped_column(nullable=False)
    metodo_consumo: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'fifo'"))
    fator_credito_padrao: Mapped[decimal.Decimal] = mapped_column(
        sa.Numeric(6, 4), nullable=False, server_default=sa.text("1.0")
    )
    fator_debito_padrao: Mapped[decimal.Decimal] = mapped_column(
        sa.Numeric(6, 4), nullable=False, server_default=sa.text("1.0")
    )
    fatores_por_faixa: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    teto_positivo_minutos: Mapped[int | None] = mapped_column()
    teto_negativo_minutos: Mapped[int | None] = mapped_column()
    limite_diario_minutos: Mapped[int] = mapped_column(
        nullable=False, server_default=sa.text("120")
    )
    limite_jornada_diaria_minutos: Mapped[int] = mapped_column(
        nullable=False, server_default=sa.text("600")
    )
    acao_vencimento: Mapped[str] = mapped_column(
        nullable=False, server_default=sa.text("'quitar_folha'")
    )
    dias_pre_aviso: Mapped[list[int]] = mapped_column(
        ARRAY(sa.Integer()), nullable=False, server_default=sa.text("'{30,15,7}'")
    )
    bloqueia_extra_no_teto: Mapped[bool] = mapped_column(
        nullable=False, server_default=sa.text("FALSE")
    )
    permite_saldo_negativo: Mapped[bool] = mapped_column(
        nullable=False, server_default=sa.text("TRUE")
    )
    documento_acordo_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("documentos.id", ondelete="SET NULL")
    )
    vigencia_inicio: Mapped[_datetime.date] = mapped_column(nullable=False)
    vigencia_fim: Mapped[_datetime.date | None] = mapped_column()
    ativo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))

    __table_args__ = (
        sa.CheckConstraint(
            "regime IN ('individual','coletivo','convencao','especial')",
            name="bh_politicas_regime_check",
        ),
        sa.CheckConstraint(
            "periodo_meses BETWEEN 1 AND 12", name="bh_politicas_periodo_meses_check"
        ),
        sa.CheckConstraint(
            "metodo_consumo IN ('fifo','lifo')", name="bh_politicas_metodo_consumo_check"
        ),
        sa.CheckConstraint(
            "fator_credito_padrao > 0", name="bh_politicas_fator_credito_padrao_check"
        ),
        sa.CheckConstraint(
            "fator_debito_padrao > 0", name="bh_politicas_fator_debito_padrao_check"
        ),
        sa.CheckConstraint(
            "teto_positivo_minutos IS NULL OR teto_positivo_minutos >= 0",
            name="bh_politicas_teto_positivo_minutos_check",
        ),
        sa.CheckConstraint(
            "teto_negativo_minutos IS NULL OR teto_negativo_minutos >= 0",
            name="bh_politicas_teto_negativo_minutos_check",
        ),
        sa.CheckConstraint(
            "limite_diario_minutos >= 0", name="bh_politicas_limite_diario_minutos_check"
        ),
        sa.CheckConstraint(
            "limite_jornada_diaria_minutos > 0",
            name="bh_politicas_limite_jornada_diaria_minutos_check",
        ),
        sa.CheckConstraint(
            "acao_vencimento IN ('quitar_folha','expirar','prorrogar','manter')",
            name="bh_politicas_acao_vencimento_check",
        ),
        sa.CheckConstraint(
            "vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio",
            name="ck_bh_politicas_vigencia",
        ),
        sa.CheckConstraint(
            "(regime = 'individual' AND periodo_meses <= 6) OR "
            "(regime IN ('coletivo','convencao') AND periodo_meses <= 12) OR "
            "(regime = 'especial')",
            name="ck_bh_politicas_periodo_legal",
        ),
        sa.Index(
            "uq_bh_politicas_codigo",
            "tenant_id",
            "empresa_id",
            "codigo",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        {
            "comment": (
                "Regras do banco de horas por empresa. O limite legal esta no CHECK: "
                "acordo individual escrito compensa em ate 6 meses; acordo ou convencao "
                "coletiva, em ate 12."
            )
        },
    )


class BhConta(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Conta-corrente de horas de um vinculo dentro de um periodo de apuracao do banco."""

    __tablename__ = "bh_contas"

    colaborador_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("colaboradores.id", ondelete="RESTRICT"), nullable=False
    )
    vinculo_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("vinculos.id", ondelete="RESTRICT"), nullable=False
    )
    bh_politica_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("bh_politicas.id", ondelete="RESTRICT"), nullable=False
    )
    codigo: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'normal'"))
    nome: Mapped[str] = mapped_column(nullable=False)
    periodo_inicio: Mapped[_datetime.date] = mapped_column(nullable=False)
    periodo_fim: Mapped[_datetime.date] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'aberta'"))
    saldo_atual_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    ultima_sequencia: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, server_default=sa.text("0")
    )
    ultimo_hash: Mapped[str | None] = mapped_column(DOM_SHA256)
    encerrada_em: Mapped[_datetime.datetime | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('aberta','encerrada','quitada','expirada','suspensa')",
            name="bh_contas_status_check",
        ),
        sa.CheckConstraint("ultima_sequencia >= 0", name="bh_contas_ultima_sequencia_check"),
        sa.UniqueConstraint(
            "tenant_id", "vinculo_id", "codigo", "periodo_inicio", name="uq_bh_contas"
        ),
        sa.CheckConstraint("periodo_fim > periodo_inicio", name="ck_bh_contas_periodo"),
        sa.Index("ix_bh_contas_vinculo", "tenant_id", "vinculo_id", "status"),
        sa.Index(
            "ix_bh_contas_vencimento",
            "tenant_id",
            "periodo_fim",
            postgresql_where=sa.text("status = 'aberta'"),
        ),
        {
            "comment": (
                "Conta-corrente de horas de um vinculo dentro de um periodo de apuracao "
                "do banco. Um vinculo pode ter varias contas simultaneas com fatores "
                "diferentes."
            )
        },
    )


class BhLancamento(ChavePrimariaUUIDMixin, TenantMixin, CriacaoMixin, Base):
    """EXTRATO IMUTAVEL do banco de horas, com cadeia de hash."""

    __tablename__ = "bh_lancamentos"

    bh_conta_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("bh_contas.id", ondelete="RESTRICT"), nullable=False
    )
    sequencia: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    data_competencia: Mapped[_datetime.date] = mapped_column(nullable=False)
    tipo: Mapped[str] = mapped_column(nullable=False)
    origem: Mapped[str] = mapped_column(nullable=False)
    apuracao_dia_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("apuracoes_dia.id", ondelete="RESTRICT")
    )
    tratamento_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("tratamentos.id", ondelete="RESTRICT")
    )
    # FK criada depois de `bh_quitacoes` (use_alter), como em schema.sql.
    quitacao_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey(
            "bh_quitacoes.id",
            ondelete="RESTRICT",
            name="fk_bh_lancamentos_quitacao",
            use_alter=True,
        )
    )
    estorna_lancamento_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("bh_lancamentos.id", ondelete="RESTRICT")
    )
    minutos: Mapped[int] = mapped_column(nullable=False)
    fator: Mapped[decimal.Decimal] = mapped_column(
        sa.Numeric(6, 4), nullable=False, server_default=sa.text("1.0")
    )
    minutos_equivalentes: Mapped[int] = mapped_column(nullable=False)
    saldo_apos_minutos: Mapped[int] = mapped_column(nullable=False)
    vence_em: Mapped[_datetime.date | None] = mapped_column()
    consumido_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    descricao: Mapped[str] = mapped_column(nullable=False)
    hash_anterior: Mapped[str | None] = mapped_column(DOM_SHA256)
    hash_registro: Mapped[str] = mapped_column(DOM_SHA256, nullable=False)

    __table_args__ = (
        sa.CheckConstraint("sequencia >= 1", name="bh_lancamentos_sequencia_check"),
        sa.CheckConstraint(
            "tipo IN ('credito','debito','quitacao','expiracao','ajuste','transferencia',"
            "'estorno')",
            name="bh_lancamentos_tipo_check",
        ),
        sa.CheckConstraint(
            "origem IN ('apuracao','tratamento','solicitacao','quitacao','expiracao',"
            "'ajuste_manual','importacao','fechamento','rescisao')",
            name="bh_lancamentos_origem_check",
        ),
        sa.CheckConstraint("minutos <> 0", name="bh_lancamentos_minutos_check"),
        sa.CheckConstraint("fator > 0", name="bh_lancamentos_fator_check"),
        sa.CheckConstraint("consumido_minutos >= 0", name="bh_lancamentos_consumido_minutos_check"),
        sa.UniqueConstraint(
            "tenant_id", "bh_conta_id", "sequencia", name="uq_bh_lancamentos_sequencia"
        ),
        sa.Index("ix_bh_lancamentos_conta", "tenant_id", "bh_conta_id", "sequencia"),
        sa.Index("ix_bh_lancamentos_competencia", "tenant_id", "data_competencia"),
        sa.Index(
            "ix_bh_lancamentos_vencimento",
            "tenant_id",
            "vence_em",
            postgresql_where=sa.text("vence_em IS NOT NULL AND tipo = 'credito'"),
        ),
        sa.Index(
            "ix_bh_lancamentos_apuracao",
            "tenant_id",
            "apuracao_dia_id",
            postgresql_where=sa.text("apuracao_dia_id IS NOT NULL"),
        ),
        {
            "comment": (
                "EXTRATO IMUTAVEL do banco de horas, com cadeia de hash. Gatilhos barram "
                "DELETE, TRUNCATE e qualquer UPDATE que nao seja exclusivamente em "
                "consumido_minutos. Corrigir significa emitir um estorno."
            )
        },
    )


class BhSaldo(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Fotografia diaria do saldo de cada conta. Sempre reconstrutivel a partir do extrato."""

    __tablename__ = "bh_saldos"

    bh_conta_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("bh_contas.id", ondelete="CASCADE"), nullable=False
    )
    data_referencia: Mapped[_datetime.date] = mapped_column(nullable=False)
    saldo_minutos: Mapped[int] = mapped_column(nullable=False)
    credito_periodo_minutos: Mapped[int] = mapped_column(
        nullable=False, server_default=sa.text("0")
    )
    debito_periodo_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    a_vencer_30_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    a_vencer_15_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    a_vencer_7_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    projecao_vencimento_minutos: Mapped[int] = mapped_column(
        nullable=False, server_default=sa.text("0")
    )
    calculado_em: Mapped[_datetime.datetime] = mapped_column(
        nullable=False, server_default=sa.text("now()")
    )

    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "bh_conta_id", "data_referencia", name="uq_bh_saldos"),
        sa.Index("ix_bh_saldos_data", "tenant_id", sa.text("data_referencia DESC")),
        {
            "comment": (
                "Fotografia diaria do saldo de cada conta. Existe para relatorio, "
                "dashboard e simulador responderem rapido sem varrer o extrato inteiro."
            )
        },
    )


class BhQuitacao(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Liquidacao de saldo de banco de horas."""

    __tablename__ = "bh_quitacoes"

    bh_conta_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("bh_contas.id", ondelete="RESTRICT"), nullable=False
    )
    colaborador_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("colaboradores.id", ondelete="RESTRICT"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(nullable=False)
    minutos: Mapped[int] = mapped_column(nullable=False)
    fator: Mapped[decimal.Decimal] = mapped_column(
        sa.Numeric(6, 4), nullable=False, server_default=sa.text("1.0")
    )
    valor: Mapped[decimal.Decimal | None] = mapped_column(sa.Numeric(14, 2))
    competencia_folha: Mapped[str | None] = mapped_column(DOM_COMPETENCIA)
    data_prevista: Mapped[_datetime.date | None] = mapped_column()
    data_efetivacao: Mapped[_datetime.date | None] = mapped_column()
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'planejada'"))
    aprovado_por: Mapped[uuid.UUID | None] = mapped_column()
    aprovado_em: Mapped[_datetime.datetime | None] = mapped_column()
    observacao: Mapped[str | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "tipo IN ('folha','folga','rescisao','expiracao','compensacao_programada')",
            name="bh_quitacoes_tipo_check",
        ),
        sa.CheckConstraint("minutos > 0", name="bh_quitacoes_minutos_check"),
        sa.CheckConstraint("fator > 0", name="bh_quitacoes_fator_check"),
        sa.CheckConstraint("valor IS NULL OR valor >= 0", name="bh_quitacoes_valor_check"),
        sa.CheckConstraint(
            "status IN ('planejada','aprovada','efetivada','cancelada')",
            name="bh_quitacoes_status_check",
        ),
        sa.Index("ix_bh_quitacoes_conta", "tenant_id", "bh_conta_id", "status"),
        sa.Index(
            "ix_bh_quitacoes_competencia",
            "tenant_id",
            "competencia_folha",
            postgresql_where=sa.text("tipo = 'folha'"),
        ),
        {
            "comment": (
                "Liquidacao de saldo de banco de horas: pagamento em folha, folga "
                "programada, acerto na rescisao ou expiracao."
            )
        },
    )
