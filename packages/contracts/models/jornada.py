"""Grupo 6 - Jornada, escala e calendario.

`horarios`, `jornadas`, `jornada_dias`, `turnos`, `escalas`, `escala_ciclos`,
`escala_atribuicoes`, `vinculo_jornadas`, `feriado_conjuntos`, `feriados`,
`unidade_feriado_conjuntos`, `tipos_afastamento` e `afastamentos`.

`horarios` e o gabarito (entrada, saida, intervalos, carga); `turnos` e o
gabarito nomeado e sequenciado para revezamento; `jornadas` e o conjunto de
regras de calculo; `escalas` e o padrao ciclico resolvido por aritmetica
modular a partir de `data_referencia`, sem materializar calendario.
"""

from __future__ import annotations

import datetime as _datetime
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .mixins import (
    AuditoriaMixin,
    ChavePrimariaUUIDMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)
from .tipos import DOM_IBGE, DOM_UF

__all__ = [
    "Afastamento",
    "Escala",
    "EscalaAtribuicao",
    "EscalaCiclo",
    "Feriado",
    "FeriadoConjunto",
    "Horario",
    "Jornada",
    "JornadaDia",
    "TipoAfastamento",
    "Turno",
    "UnidadeFeriadoConjunto",
    "VinculoJornada",
]


class Horario(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Gabarito de horario reutilizavel: entrada, saida e intervalos previstos."""

    __tablename__ = "horarios"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="RESTRICT"), nullable=False
    )
    codigo: Mapped[str] = mapped_column(nullable=False)
    nome: Mapped[str] = mapped_column(nullable=False)
    entrada: Mapped[_datetime.time | None] = mapped_column()
    saida: Mapped[_datetime.time | None] = mapped_column()
    intervalo_inicio: Mapped[_datetime.time | None] = mapped_column()
    intervalo_fim: Mapped[_datetime.time | None] = mapped_column()
    duracao_intervalo_minutos: Mapped[int | None] = mapped_column()
    intervalos_extras: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    cruza_meia_noite: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))
    carga_minutos: Mapped[int] = mapped_column(nullable=False)
    ativo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))

    __table_args__ = (
        sa.CheckConstraint(
            "duracao_intervalo_minutos IS NULL OR duracao_intervalo_minutos >= 0",
            name="horarios_duracao_intervalo_minutos_check",
        ),
        sa.CheckConstraint("carga_minutos BETWEEN 0 AND 1440", name="horarios_carga_minutos_check"),
        sa.Index(
            "uq_horarios_codigo",
            "tenant_id",
            "empresa_id",
            "codigo",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        {
            "comment": (
                "Gabarito de horario reutilizavel: entrada, saida e intervalos previstos "
                "de um dia de trabalho. E o bloco de montagem de jornadas e turnos."
            )
        },
    )


class Jornada(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Conjunto de regras de trabalho e de calculo aplicado a um vinculo."""

    __tablename__ = "jornadas"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="RESTRICT"), nullable=False
    )
    codigo: Mapped[str] = mapped_column(nullable=False)
    nome: Mapped[str] = mapped_column(nullable=False)
    descricao: Mapped[str | None] = mapped_column()
    tipo: Mapped[str] = mapped_column(nullable=False)
    carga_diaria_minutos: Mapped[int | None] = mapped_column()
    carga_semanal_minutos: Mapped[int | None] = mapped_column()
    carga_mensal_minutos: Mapped[int | None] = mapped_column()
    tolerancia_marcacao_minutos: Mapped[int] = mapped_column(
        nullable=False, server_default=sa.text("5")
    )
    tolerancia_diaria_minutos: Mapped[int] = mapped_column(
        nullable=False, server_default=sa.text("10")
    )
    descontar_tudo_se_exceder: Mapped[bool] = mapped_column(
        nullable=False, server_default=sa.text("FALSE")
    )
    janela_flexivel_minutos: Mapped[int | None] = mapped_column()
    intervalo_automatico: Mapped[bool] = mapped_column(
        nullable=False, server_default=sa.text("FALSE")
    )
    intervalo_minimo_minutos: Mapped[int | None] = mapped_column()
    intervalo_flexivel: Mapped[bool] = mapped_column(
        nullable=False, server_default=sa.text("FALSE")
    )
    interjornada_minima_minutos: Mapped[int] = mapped_column(
        nullable=False, server_default=sa.text("660")
    )
    noturno_inicio: Mapped[_datetime.time] = mapped_column(
        nullable=False, server_default=sa.text("'22:00'")
    )
    noturno_fim: Mapped[_datetime.time] = mapped_column(
        nullable=False, server_default=sa.text("'05:00'")
    )
    hora_ficta_noturna: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))
    prorrogacao_noturna: Mapped[bool] = mapped_column(
        nullable=False, server_default=sa.text("TRUE")
    )
    limite_extra_diario_minutos: Mapped[int] = mapped_column(
        nullable=False, server_default=sa.text("120")
    )
    limite_jornada_diaria_minutos: Mapped[int] = mapped_column(
        nullable=False, server_default=sa.text("600")
    )
    bloqueia_extra_acima_limite: Mapped[bool] = mapped_column(
        nullable=False, server_default=sa.text("FALSE")
    )
    compensa_sabado: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))
    fatores_extra: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    vigencia_inicio: Mapped[_datetime.date] = mapped_column(
        nullable=False, server_default=sa.text("CURRENT_DATE")
    )
    vigencia_fim: Mapped[_datetime.date | None] = mapped_column()
    ativo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))

    __table_args__ = (
        sa.CheckConstraint(
            "tipo IN ('fixa','flexivel','livre','escala','12x36','parcial','intermitente',"
            "'teletrabalho','motorista')",
            name="jornadas_tipo_check",
        ),
        sa.CheckConstraint(
            "carga_diaria_minutos IS NULL OR carga_diaria_minutos BETWEEN 0 AND 1440",
            name="jornadas_carga_diaria_minutos_check",
        ),
        sa.CheckConstraint(
            "carga_semanal_minutos IS NULL OR carga_semanal_minutos BETWEEN 0 AND 4200",
            name="jornadas_carga_semanal_minutos_check",
        ),
        sa.CheckConstraint(
            "carga_mensal_minutos IS NULL OR carga_mensal_minutos >= 0",
            name="jornadas_carga_mensal_minutos_check",
        ),
        sa.CheckConstraint(
            "tolerancia_marcacao_minutos BETWEEN 0 AND 60",
            name="jornadas_tolerancia_marcacao_minutos_check",
        ),
        sa.CheckConstraint(
            "tolerancia_diaria_minutos BETWEEN 0 AND 120",
            name="jornadas_tolerancia_diaria_minutos_check",
        ),
        sa.CheckConstraint(
            "janela_flexivel_minutos IS NULL OR janela_flexivel_minutos >= 0",
            name="jornadas_janela_flexivel_minutos_check",
        ),
        sa.CheckConstraint(
            "intervalo_minimo_minutos IS NULL OR intervalo_minimo_minutos >= 0",
            name="jornadas_intervalo_minimo_minutos_check",
        ),
        sa.CheckConstraint(
            "interjornada_minima_minutos >= 0",
            name="jornadas_interjornada_minima_minutos_check",
        ),
        sa.CheckConstraint(
            "limite_extra_diario_minutos >= 0",
            name="jornadas_limite_extra_diario_minutos_check",
        ),
        sa.CheckConstraint(
            "limite_jornada_diaria_minutos > 0",
            name="jornadas_limite_jornada_diaria_minutos_check",
        ),
        sa.CheckConstraint(
            "vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio",
            name="ck_jornadas_vigencia",
        ),
        sa.Index(
            "uq_jornadas_codigo",
            "tenant_id",
            "empresa_id",
            "codigo",
            "vigencia_inicio",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index(
            "ix_jornadas_empresa",
            "tenant_id",
            "empresa_id",
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        {
            "comment": (
                "Conjunto de regras de trabalho e de calculo aplicado a um vinculo: "
                "carga, tolerancias, tratamento do noturno, limites de extra e politica "
                "de intervalo."
            )
        },
    )


class JornadaDia(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Desdobramento da jornada por dia da semana."""

    __tablename__ = "jornada_dias"

    jornada_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("jornadas.id", ondelete="CASCADE"), nullable=False
    )
    dia_semana: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    tipo_dia: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'util'"))
    horario_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("horarios.id", ondelete="RESTRICT")
    )
    carga_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))

    __table_args__ = (
        sa.CheckConstraint("dia_semana BETWEEN 0 AND 6", name="jornada_dias_dia_semana_check"),
        sa.CheckConstraint(
            "tipo_dia IN ('util','dsr','folga','compensado','facultativo')",
            name="jornada_dias_tipo_dia_check",
        ),
        sa.CheckConstraint(
            "carga_minutos BETWEEN 0 AND 1440", name="jornada_dias_carga_minutos_check"
        ),
        sa.UniqueConstraint("tenant_id", "jornada_id", "dia_semana", name="uq_jornada_dias"),
        {
            "comment": (
                "Desdobramento da jornada por dia da semana. Define o horario previsto e "
                "o tipo do dia em jornadas fixas e flexiveis."
            )
        },
    )


class Turno(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Turno nomeado, com o horario que o materializa."""

    __tablename__ = "turnos"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="RESTRICT"), nullable=False
    )
    horario_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("horarios.id", ondelete="RESTRICT")
    )
    codigo: Mapped[str] = mapped_column(nullable=False)
    nome: Mapped[str] = mapped_column(nullable=False)
    tipo: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'diurno'"))
    sequencia: Mapped[int | None] = mapped_column()
    cor: Mapped[str | None] = mapped_column()
    ativo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))

    __table_args__ = (
        sa.CheckConstraint(
            "tipo IN ('diurno','noturno','misto','folga','dsr','sobreaviso','prontidao')",
            name="turnos_tipo_check",
        ),
        sa.CheckConstraint(r"cor IS NULL OR cor ~ '^#[0-9A-Fa-f]{6}$'", name="turnos_cor_check"),
        sa.Index(
            "uq_turnos_codigo",
            "tenant_id",
            "empresa_id",
            "codigo",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        {
            "comment": (
                "Turno nomeado, com o horario que o materializa. Em regime de "
                "revezamento, a sequencia define a ordem de rodizio."
            )
        },
    )


class Escala(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Padrao ciclico de trabalho e folga."""

    __tablename__ = "escalas"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="RESTRICT"), nullable=False
    )
    jornada_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("jornadas.id", ondelete="RESTRICT")
    )
    codigo: Mapped[str] = mapped_column(nullable=False)
    nome: Mapped[str] = mapped_column(nullable=False)
    descricao: Mapped[str | None] = mapped_column()
    tipo: Mapped[str] = mapped_column(nullable=False)
    dias_ciclo: Mapped[int] = mapped_column(nullable=False)
    data_referencia: Mapped[_datetime.date] = mapped_column(nullable=False)
    ativo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))

    __table_args__ = (
        sa.CheckConstraint(
            "tipo IN ('5x2','6x1','4x2','12x36','espanhola','rotativa','personalizada')",
            name="escalas_tipo_check",
        ),
        sa.CheckConstraint("dias_ciclo BETWEEN 1 AND 366", name="escalas_dias_ciclo_check"),
        sa.Index(
            "uq_escalas_codigo",
            "tenant_id",
            "empresa_id",
            "codigo",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        {
            "comment": (
                "Padrao ciclico de trabalho e folga. O ciclo se repete indefinidamente a "
                "partir de data_referencia; qualquer data e resolvida por aritmetica "
                "modular, sem materializar o calendario."
            )
        },
    )


class EscalaCiclo(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Uma linha por posicao do ciclo da escala."""

    __tablename__ = "escala_ciclos"

    escala_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("escalas.id", ondelete="CASCADE"), nullable=False
    )
    posicao: Mapped[int] = mapped_column(nullable=False)
    turno_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("turnos.id", ondelete="RESTRICT")
    )
    tipo_dia: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'trabalho'"))
    carga_minutos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))

    __table_args__ = (
        sa.CheckConstraint("posicao >= 1", name="escala_ciclos_posicao_check"),
        sa.CheckConstraint(
            "tipo_dia IN ('trabalho','folga','dsr','compensado')",
            name="escala_ciclos_tipo_dia_check",
        ),
        sa.CheckConstraint(
            "carga_minutos BETWEEN 0 AND 1440", name="escala_ciclos_carga_minutos_check"
        ),
        sa.UniqueConstraint("tenant_id", "escala_id", "posicao", name="uq_escala_ciclos"),
        {
            "comment": (
                "Uma linha por posicao do ciclo da escala. Em 12x36 sao duas linhas: "
                "posicao 1 trabalho de 12 horas, posicao 2 folga."
            )
        },
    )


class EscalaAtribuicao(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Atribuicao datada de uma escala a um vinculo."""

    __tablename__ = "escala_atribuicoes"

    vinculo_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("vinculos.id", ondelete="CASCADE"), nullable=False
    )
    escala_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("escalas.id", ondelete="RESTRICT"), nullable=False
    )
    posicao_inicial: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("1"))
    vigencia_inicio: Mapped[_datetime.date] = mapped_column(nullable=False)
    vigencia_fim: Mapped[_datetime.date | None] = mapped_column()
    motivo: Mapped[str | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint("posicao_inicial >= 1", name="escala_atribuicoes_posicao_inicial_check"),
        sa.CheckConstraint(
            "vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio",
            name="ck_escala_atribuicoes_vigencia",
        ),
        ExcludeConstraint(
            ("tenant_id", "="),
            ("vinculo_id", "="),
            (
                sa.text(
                    "daterange(vigencia_inicio, COALESCE(vigencia_fim, DATE 'infinity'), '[]')"
                ),
                "&&",
            ),
            name="ex_escala_atribuicoes_sobreposicao",
            using="gist",
        ),
        {
            "comment": (
                "Atribuicao datada de uma escala a um vinculo. Um vinculo tem no maximo "
                "uma escala vigente por data, garantido por constraint de exclusao."
            )
        },
    )


class VinculoJornada(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Historico de jornada vigente por vinculo."""

    __tablename__ = "vinculo_jornadas"

    vinculo_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("vinculos.id", ondelete="CASCADE"), nullable=False
    )
    jornada_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("jornadas.id", ondelete="RESTRICT"), nullable=False
    )
    vigencia_inicio: Mapped[_datetime.date] = mapped_column(nullable=False)
    vigencia_fim: Mapped[_datetime.date | None] = mapped_column()
    motivo: Mapped[str | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio",
            name="ck_vinculo_jornadas_vigencia",
        ),
        ExcludeConstraint(
            ("tenant_id", "="),
            ("vinculo_id", "="),
            (
                sa.text(
                    "daterange(vigencia_inicio, COALESCE(vigencia_fim, DATE 'infinity'), '[]')"
                ),
                "&&",
            ),
            name="ex_vinculo_jornadas_sobreposicao",
            using="gist",
        ),
        sa.Index(
            "ix_vinculo_jornadas_resolucao",
            "tenant_id",
            "vinculo_id",
            sa.text("vigencia_inicio DESC"),
        ),
        {
            "comment": (
                "Historico de jornada vigente por vinculo. Sem ela nao ha como trocar a "
                "jornada no meio do mes preservando a apuracao anterior."
            )
        },
    )


class FeriadoConjunto(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Agrupamento de feriados por abrangencia."""

    __tablename__ = "feriado_conjuntos"

    codigo: Mapped[str] = mapped_column(nullable=False)
    nome: Mapped[str] = mapped_column(nullable=False)
    abrangencia: Mapped[str] = mapped_column(nullable=False)
    uf: Mapped[str | None] = mapped_column(DOM_UF)
    codigo_ibge_municipio: Mapped[str | None] = mapped_column(DOM_IBGE)
    ativo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))

    __table_args__ = (
        sa.CheckConstraint(
            "abrangencia IN ('nacional','estadual','municipal','empresa','unidade')",
            name="feriado_conjuntos_abrangencia_check",
        ),
        sa.CheckConstraint(
            "(abrangencia = 'estadual'  AND uf IS NOT NULL) OR "
            "(abrangencia = 'municipal' AND codigo_ibge_municipio IS NOT NULL) OR "
            "(abrangencia IN ('nacional','empresa','unidade'))",
            name="ck_feriado_conjuntos_abrangencia",
        ),
        sa.Index(
            "uq_feriado_conjuntos_codigo",
            "tenant_id",
            "codigo",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        {
            "comment": (
                "Agrupamento de feriados por abrangencia. A unidade combina varios "
                "conjuntos (nacional mais estadual mais municipal)."
            )
        },
    )


class Feriado(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Feriado, ponto facultativo ou expediente reduzido."""

    __tablename__ = "feriados"

    feriado_conjunto_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("feriado_conjuntos.id", ondelete="CASCADE"), nullable=False
    )
    nome: Mapped[str] = mapped_column(nullable=False)
    data: Mapped[_datetime.date | None] = mapped_column()
    ano: Mapped[int | None] = mapped_column()
    tipo: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'feriado'"))
    movel: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))
    regra_movel: Mapped[str | None] = mapped_column()
    offset_dias: Mapped[int | None] = mapped_column()
    integral: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))
    carga_reduzida_minutos: Mapped[int | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint("ano IS NULL OR ano BETWEEN 1900 AND 2200", name="feriados_ano_check"),
        sa.CheckConstraint(
            "tipo IN ('feriado','ponto_facultativo','data_comemorativa','compensado')",
            name="feriados_tipo_check",
        ),
        sa.CheckConstraint(
            "regra_movel IN ('pascoa','carnaval','sexta_santa','corpus_christi',"
            "'quarta_cinzas','custom')",
            name="feriados_regra_movel_check",
        ),
        sa.CheckConstraint(
            "carga_reduzida_minutos IS NULL OR carga_reduzida_minutos >= 0",
            name="feriados_carga_reduzida_minutos_check",
        ),
        sa.CheckConstraint(
            "(movel = TRUE  AND regra_movel IS NOT NULL) OR "
            "(movel = FALSE AND data IS NOT NULL)",
            name="ck_feriados_definicao",
        ),
        sa.CheckConstraint(
            "integral = TRUE OR carga_reduzida_minutos IS NOT NULL",
            name="ck_feriados_parcial",
        ),
        sa.Index(
            "uq_feriados_fixos",
            "tenant_id",
            "feriado_conjunto_id",
            "data",
            "nome",
            unique=True,
            postgresql_where=sa.text("data IS NOT NULL"),
        ),
        sa.Index("ix_feriados_conjunto", "tenant_id", "feriado_conjunto_id"),
        sa.Index(
            "ix_feriados_data",
            "tenant_id",
            "data",
            postgresql_where=sa.text("data IS NOT NULL"),
        ),
        {
            "comment": (
                "Feriado, ponto facultativo ou expediente reduzido. Feriados moveis nao "
                "guardam data: sao calculados por regra a partir da Pascoa."
            )
        },
    )


class UnidadeFeriadoConjunto(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base
):
    """Associacao N:N entre unidade e conjuntos de feriados."""

    __tablename__ = "unidade_feriado_conjuntos"

    unidade_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("unidades.id", ondelete="CASCADE"), nullable=False
    )
    feriado_conjunto_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("feriado_conjuntos.id", ondelete="CASCADE"), nullable=False
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "feriado_conjunto_id",
            name="uq_unidade_feriado_conjuntos",
        ),
        {
            "comment": (
                "Associacao N para N entre unidade e conjuntos de feriados. Uma unidade "
                "precisa somar o calendario nacional, o estadual e o municipal."
            )
        },
    )


class TipoAfastamento(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Catalogo configuravel de motivos de ausencia e o efeito de cada um no calculo."""

    __tablename__ = "tipos_afastamento"

    codigo: Mapped[str] = mapped_column(nullable=False)
    nome: Mapped[str] = mapped_column(nullable=False)
    descricao: Mapped[str | None] = mapped_column()
    categoria: Mapped[str] = mapped_column(nullable=False)
    codigo_esocial: Mapped[str | None] = mapped_column()
    abona_dia: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))
    remunerado: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))
    computa_carga: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))
    computa_dsr: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))
    suspende_contrato: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))
    exige_documento: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))
    limite_dias: Mapped[int | None] = mapped_column()
    ativo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))

    __table_args__ = (
        sa.CheckConstraint(
            "categoria IN ('ferias','atestado','licenca_maternidade','licenca_paternidade',"
            "'inss','acidente_trabalho','suspensao','falta_justificada','falta_injustificada',"
            "'servico_militar','doacao_sangue','casamento','obito','treinamento',"
            "'licenca_nao_remunerada','outro')",
            name="tipos_afastamento_categoria_check",
        ),
        sa.CheckConstraint(
            "limite_dias IS NULL OR limite_dias > 0",
            name="tipos_afastamento_limite_dias_check",
        ),
        sa.Index(
            "uq_tipos_afastamento_codigo",
            "tenant_id",
            "codigo",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        {
            "comment": (
                "Catalogo configuravel de motivos de ausencia e o efeito de cada um no "
                "calculo. Os codigos de fabrica sao semeados por tenant."
            )
        },
    )


class Afastamento(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Periodo de ausencia legitima do colaborador."""

    __tablename__ = "afastamentos"

    colaborador_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("colaboradores.id", ondelete="RESTRICT"), nullable=False
    )
    vinculo_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("vinculos.id", ondelete="RESTRICT")
    )
    tipo_afastamento_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("tipos_afastamento.id", ondelete="RESTRICT"), nullable=False
    )
    data_inicio: Mapped[_datetime.date] = mapped_column(nullable=False)
    data_fim: Mapped[_datetime.date | None] = mapped_column()
    periodo_parcial: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))
    hora_inicio: Mapped[_datetime.time | None] = mapped_column()
    hora_fim: Mapped[_datetime.time | None] = mapped_column()
    motivo: Mapped[str | None] = mapped_column()
    cid: Mapped[str | None] = mapped_column()
    dias_previstos: Mapped[int | None] = mapped_column()
    documento_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("documentos.id", ondelete="SET NULL")
    )
    # FK criada depois de `solicitacoes` (use_alter), como em schema.sql.
    solicitacao_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey(
            "solicitacoes.id",
            ondelete="SET NULL",
            name="fk_afastamentos_solicitacao",
            use_alter=True,
        )
    )
    origem: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'manual'"))
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'aprovado'"))
    aprovado_por: Mapped[uuid.UUID | None] = mapped_column()
    aprovado_em: Mapped[_datetime.datetime | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "origem IN ('manual','solicitacao','integracao','importacao')",
            name="afastamentos_origem_check",
        ),
        sa.CheckConstraint(
            "status IN ('solicitado','aprovado','reprovado','cancelado','encerrado')",
            name="afastamentos_status_check",
        ),
        sa.CheckConstraint(
            "data_fim IS NULL OR data_fim >= data_inicio", name="ck_afastamentos_periodo"
        ),
        sa.CheckConstraint(
            "periodo_parcial = FALSE OR (hora_inicio IS NOT NULL AND hora_fim IS NOT NULL)",
            name="ck_afastamentos_parcial",
        ),
        ExcludeConstraint(
            ("tenant_id", "="),
            ("colaborador_id", "="),
            (
                sa.text("daterange(data_inicio, COALESCE(data_fim, DATE 'infinity'), '[]')"),
                "&&",
            ),
            name="ex_afastamentos_sobreposicao",
            using="gist",
            where=sa.text(
                "status = 'aprovado' AND periodo_parcial = FALSE AND excluido_em IS NULL"
            ),
        ),
        sa.Index(
            "ix_afastamentos_colaborador",
            "tenant_id",
            "colaborador_id",
            "data_inicio",
            "data_fim",
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index(
            "ix_afastamentos_vinculo",
            "tenant_id",
            "vinculo_id",
            "data_inicio",
            postgresql_where=sa.text("status = 'aprovado'"),
        ),
        sa.Index("ix_afastamentos_tipo", "tenant_id", "tipo_afastamento_id", "data_inicio"),
        {
            "comment": (
                "Periodo de ausencia legitima do colaborador. Entra na apuracao como "
                "insumo (nao como marcacao) e e exportado no bloco de ausencias do AEJ."
            )
        },
    )
