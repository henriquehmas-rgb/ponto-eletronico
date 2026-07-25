"""Grupo 8 - Tratamento e apuracao.

`tipos_tratamento`, `tratamentos`, `apuracoes_dia`, `apuracao_componentes` e
`ocorrencias`.

Sequencia canonica do motor:

    marcacoes imutaveis -> regras da jornada do dia -> tratamentos aplicaveis
    -> apuracao do dia -> lancamentos de banco de horas -> fechamento

Tratamento e a UNICA forma de corrigir a jornada, e ele nunca altera a
marcacao: ele se soma a ela na apuracao. `tipos_tratamento.afeta_afd` carrega
um `CHECK (afeta_afd = FALSE)` para tornar a regra legal explicita no proprio
schema - nenhum tratamento entra no AFD, jamais.
"""

from __future__ import annotations

import datetime as _datetime
import decimal
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .mixins import (
    AuditoriaMixin,
    ChavePrimariaUUIDMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)
from .tipos import DOM_SHA256

__all__ = [
    "ApuracaoComponente",
    "ApuracaoDia",
    "Ocorrencia",
    "TipoTratamento",
    "Tratamento",
]


class TipoTratamento(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Catalogo configuravel de tipos de tratamento."""

    __tablename__ = "tipos_tratamento"

    codigo: Mapped[str] = mapped_column(nullable=False)
    nome: Mapped[str] = mapped_column(nullable=False)
    descricao: Mapped[str | None] = mapped_column()
    categoria: Mapped[str] = mapped_column(nullable=False)
    exige_aprovacao: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))
    exige_anexo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))
    exige_motivo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))
    afeta_afd: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))
    afeta_aej: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))
    permite_retroativo_dias: Mapped[int | None] = mapped_column()
    ativo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))

    __table_args__ = (
        sa.CheckConstraint(
            "categoria IN ('inclusao_marcacao','desconsideracao_marcacao','ajuste_intervalo',"
            "'abono','justificativa','afastamento','compensacao','ajuste_saldo')",
            name="tipos_tratamento_categoria_check",
        ),
        sa.CheckConstraint(
            "permite_retroativo_dias IS NULL OR permite_retroativo_dias >= 0",
            name="tipos_tratamento_permite_retroativo_dias_check",
        ),
        sa.CheckConstraint("afeta_afd = FALSE", name="ck_tipos_tratamento_afd"),
        sa.Index(
            "uq_tipos_tratamento_codigo",
            "tenant_id",
            "codigo",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        {
            "comment": (
                "Catalogo configuravel de tipos de tratamento. Tratamento e a UNICA forma "
                "de corrigir a jornada, e ele nunca altera a marcacao."
            )
        },
    )


class Tratamento(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """CAMADA DE CORRECAO. Refere-se a um dia e, opcionalmente, a uma marcacao existente."""

    __tablename__ = "tratamentos"

    colaborador_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("colaboradores.id", ondelete="RESTRICT"), nullable=False
    )
    vinculo_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("vinculos.id", ondelete="RESTRICT"), nullable=False
    )
    tipo_tratamento_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("tipos_tratamento.id", ondelete="RESTRICT"), nullable=False
    )
    data_referencia: Mapped[_datetime.date] = mapped_column(nullable=False)
    marcacao_id: Mapped[uuid.UUID | None] = mapped_column()
    marcacao_datahora: Mapped[_datetime.datetime | None] = mapped_column()
    datahora_proposta: Mapped[_datetime.datetime | None] = mapped_column()
    sentido: Mapped[str | None] = mapped_column()
    minutos_ajuste: Mapped[int | None] = mapped_column()
    tipo_afastamento_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("tipos_afastamento.id", ondelete="RESTRICT")
    )
    motivo: Mapped[str] = mapped_column(nullable=False)
    observacao: Mapped[str | None] = mapped_column()
    origem: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'gestor'"))
    # FK criada depois de `solicitacoes` (use_alter), como em schema.sql.
    solicitacao_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey(
            "solicitacoes.id",
            ondelete="SET NULL",
            name="fk_tratamentos_solicitacao",
            use_alter=True,
        )
    )
    documento_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("documentos.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'pendente'"))
    aprovado_por: Mapped[uuid.UUID | None] = mapped_column()
    aprovado_em: Mapped[_datetime.datetime | None] = mapped_column()
    reprovado_motivo: Mapped[str | None] = mapped_column()
    aplicado_em: Mapped[_datetime.datetime | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "sentido IN ('entrada','saida','indefinido')", name="tratamentos_sentido_check"
        ),
        sa.CheckConstraint(
            "origem IN ('colaborador','gestor','rh','sistema','integracao','importacao')",
            name="tratamentos_origem_check",
        ),
        sa.CheckConstraint(
            "status IN ('rascunho','pendente','aprovado','reprovado','cancelado','aplicado')",
            name="tratamentos_status_check",
        ),
        sa.ForeignKeyConstraint(
            ["marcacao_id", "marcacao_datahora"],
            ["marcacoes.id", "marcacoes.datahora_marcacao"],
            name="fk_tratamentos_marcacao",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "(marcacao_id IS NULL AND marcacao_datahora IS NULL) OR "
            "(marcacao_id IS NOT NULL AND marcacao_datahora IS NOT NULL)",
            name="ck_tratamentos_marcacao",
        ),
        sa.Index("ix_tratamentos_vinculo_data", "tenant_id", "vinculo_id", "data_referencia"),
        sa.Index(
            "ix_tratamentos_pendentes",
            "tenant_id",
            "status",
            "data_referencia",
            postgresql_where=sa.text("status = 'pendente'"),
        ),
        sa.Index(
            "ix_tratamentos_marcacao",
            "tenant_id",
            "marcacao_id",
            postgresql_where=sa.text("marcacao_id IS NOT NULL"),
        ),
        {
            "comment": (
                "CAMADA DE CORRECAO. Um tratamento se refere a um dia e, opcionalmente, a "
                "uma marcacao existente, mas NUNCA a modifica."
            )
        },
    )


class ApuracaoDia(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Resultado consolidado do calculo de um dia para um vinculo. Derivada e recalculavel."""

    __tablename__ = "apuracoes_dia"

    vinculo_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("vinculos.id", ondelete="CASCADE"), nullable=False
    )
    colaborador_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("colaboradores.id", ondelete="CASCADE"), nullable=False
    )
    data: Mapped[_datetime.date] = mapped_column(nullable=False)
    empresa_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="RESTRICT"), nullable=False
    )
    unidade_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("unidades.id", ondelete="RESTRICT")
    )
    departamento_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("departamentos.id", ondelete="RESTRICT")
    )
    centro_custo_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("centros_custo.id", ondelete="RESTRICT")
    )
    jornada_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("jornadas.id", ondelete="RESTRICT")
    )
    escala_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("escalas.id", ondelete="RESTRICT")
    )
    turno_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("turnos.id", ondelete="RESTRICT")
    )
    horario_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("horarios.id", ondelete="RESTRICT")
    )
    feriado_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("feriados.id", ondelete="RESTRICT")
    )
    afastamento_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("afastamentos.id", ondelete="RESTRICT")
    )
    tipo_dia: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'util'"))
    previsto_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    trabalhado_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    normais_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    extras_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    extras_noturnas_minutos: Mapped[int] = mapped_column(
        nullable=False, server_default=sa.text("0")
    )
    noturno_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    noturno_ficta_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    intervalo_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    intervalo_previsto_minutos: Mapped[int] = mapped_column(
        nullable=False, server_default=sa.text("0")
    )
    intrajornada_suprimida_minutos: Mapped[int] = mapped_column(
        nullable=False, server_default=sa.text("0")
    )
    interjornada_minutos: Mapped[int | None] = mapped_column()
    interjornada_violada: Mapped[bool] = mapped_column(
        nullable=False, server_default=sa.text("FALSE")
    )
    atraso_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    saida_antecipada_minutos: Mapped[int] = mapped_column(
        nullable=False, server_default=sa.text("0")
    )
    falta_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    abono_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    sobreaviso_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    prontidao_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    pausas_nr17_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    dsr_credito_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    dsr_debito_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    banco_credito_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    banco_debito_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    tolerancia_aplicada_minutos: Mapped[int] = mapped_column(
        nullable=False, server_default=sa.text("0")
    )
    saldo_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    quantidade_marcacoes: Mapped[int] = mapped_column(
        sa.SmallInteger, nullable=False, server_default=sa.text("0")
    )
    marcacoes_impares: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))
    tem_tratamento: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'pendente'"))
    versao: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("1"))
    hash_entrada: Mapped[str | None] = mapped_column(DOM_SHA256)
    # FK criada depois de `fechamentos` (use_alter), como em schema.sql.
    fechamento_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey(
            "fechamentos.id",
            ondelete="SET NULL",
            name="fk_apuracoes_dia_fechamento",
            use_alter=True,
        )
    )
    apurado_em: Mapped[_datetime.datetime | None] = mapped_column()
    apurado_por: Mapped[uuid.UUID | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "tipo_dia IN ('util','dsr','folga','feriado','ponto_facultativo','afastamento',"
            "'compensado','nao_apurado')",
            name="apuracoes_dia_tipo_dia_check",
        ),
        sa.CheckConstraint(
            "quantidade_marcacoes >= 0", name="apuracoes_dia_quantidade_marcacoes_check"
        ),
        sa.CheckConstraint(
            "status IN ('pendente','apurado','com_ocorrencia','fechado','reaberto')",
            name="apuracoes_dia_status_check",
        ),
        sa.CheckConstraint("versao >= 1", name="apuracoes_dia_versao_check"),
        sa.UniqueConstraint("tenant_id", "vinculo_id", "data", name="uq_apuracoes_dia"),
        sa.Index("ix_apuracoes_dia_periodo", "tenant_id", "empresa_id", "data"),
        sa.Index(
            "ix_apuracoes_dia_colaborador", "tenant_id", "colaborador_id", sa.text("data DESC")
        ),
        sa.Index(
            "ix_apuracoes_dia_status",
            "tenant_id",
            "status",
            "data",
            postgresql_where=sa.text("status IN ('pendente','com_ocorrencia')"),
        ),
        sa.Index(
            "ix_apuracoes_dia_fechamento",
            "tenant_id",
            "fechamento_id",
            postgresql_where=sa.text("fechamento_id IS NOT NULL"),
        ),
        sa.Index("ix_apuracoes_dia_unidade", "tenant_id", "unidade_id", "data"),
        {
            "comment": (
                "Resultado consolidado do calculo de um dia para um vinculo. E derivada e "
                "recalculavel: apagar e recalcular precisa produzir exatamente o mesmo "
                "resultado."
            )
        },
    )


class ApuracaoComponente(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Decomposicao auditavel da apuracao do dia."""

    __tablename__ = "apuracao_componentes"

    apuracao_dia_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("apuracoes_dia.id", ondelete="CASCADE"), nullable=False
    )
    codigo: Mapped[str] = mapped_column(nullable=False)
    descricao: Mapped[str | None] = mapped_column()
    categoria: Mapped[str] = mapped_column(nullable=False)
    minutos: Mapped[int] = mapped_column(nullable=False)
    fator: Mapped[decimal.Decimal] = mapped_column(
        sa.Numeric(6, 4), nullable=False, server_default=sa.text("1.0")
    )
    minutos_equivalentes: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    origem: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'marcacao'"))
    inicio: Mapped[_datetime.datetime | None] = mapped_column()
    fim: Mapped[_datetime.datetime | None] = mapped_column()
    detalhes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        sa.CheckConstraint(
            "categoria IN ('normal','extra','noturno','falta','abono','intervalo',"
            "'sobreaviso','prontidao','dsr','banco','indenizacao','pausa')",
            name="apuracao_componentes_categoria_check",
        ),
        sa.CheckConstraint("fator >= 0", name="apuracao_componentes_fator_check"),
        sa.CheckConstraint(
            "origem IN ('marcacao','tratamento','afastamento','regra','banco','feriado')",
            name="apuracao_componentes_origem_check",
        ),
        sa.Index("ix_apuracao_componentes_apuracao", "tenant_id", "apuracao_dia_id"),
        sa.Index("ix_apuracao_componentes_codigo", "tenant_id", "codigo", "categoria"),
        {
            "comment": (
                "Decomposicao auditavel da apuracao do dia. Cada linha explica de onde "
                "saiu cada bloco de minutos."
            )
        },
    )


class Ocorrencia(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Inconsistencia ou desvio detectado pelo motor. Ocorrencia nao corrige: chama o humano."""

    __tablename__ = "ocorrencias"

    colaborador_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("colaboradores.id", ondelete="CASCADE"), nullable=False
    )
    vinculo_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("vinculos.id", ondelete="CASCADE")
    )
    apuracao_dia_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("apuracoes_dia.id", ondelete="CASCADE")
    )
    data: Mapped[_datetime.date] = mapped_column(nullable=False)
    codigo: Mapped[str] = mapped_column(nullable=False)
    severidade: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'atencao'"))
    descricao: Mapped[str] = mapped_column(nullable=False)
    detalhes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'aberta'"))
    tratamento_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("tratamentos.id", ondelete="SET NULL")
    )
    resolucao: Mapped[str | None] = mapped_column()
    resolvida_em: Mapped[_datetime.datetime | None] = mapped_column()
    resolvida_por: Mapped[uuid.UUID | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "codigo IN ('marcacao_impar','sem_marcacao','falta','atraso','saida_antecipada',"
            "'extra_excedida','jornada_excedida','intrajornada_suprimida',"
            "'interjornada_violada','dsr_violado','pausa_nr17','fora_geocerca','score_baixo',"
            "'marcacao_duplicada','offline_tardio','banco_teto','banco_vencendo',"
            "'terminal_offline')",
            name="ocorrencias_codigo_check",
        ),
        sa.CheckConstraint(
            "severidade IN ('info','atencao','alta','critica')",
            name="ocorrencias_severidade_check",
        ),
        sa.CheckConstraint(
            "status IN ('aberta','em_tratamento','resolvida','ignorada')",
            name="ocorrencias_status_check",
        ),
        sa.Index(
            "ix_ocorrencias_abertas",
            "tenant_id",
            "status",
            sa.text("data DESC"),
            postgresql_where=sa.text("status IN ('aberta','em_tratamento')"),
        ),
        sa.Index("ix_ocorrencias_colaborador", "tenant_id", "colaborador_id", sa.text("data DESC")),
        sa.Index("ix_ocorrencias_codigo", "tenant_id", "codigo", "data"),
        {
            "comment": (
                "Inconsistencia ou desvio detectado pelo motor. E a fila de trabalho do "
                "gestor e do RH e a base do relatorio de ocorrencias."
            )
        },
    )
