"""Grupo 2 - Organizacao: empresas, unidades, redes, departamentos, centros de custo e cargos.

Estrutura organizacional: Tenant -> Empresas (CNPJ matriz/filiais) -> Unidades
(endereco, geocerca, fuso, feriados) -> Departamentos -> Centros de custo ->
Cargos. `redes_permitidas` guarda a allowlist CIDR do registro por navegador.
"""

from __future__ import annotations

import decimal
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import CIDR, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .mixins import (
    AuditoriaMixin,
    ChavePrimariaUUIDMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)
from .tipos import DOM_CBO, DOM_CEP, DOM_CNPJ, DOM_EMAIL, DOM_FUSO, DOM_IBGE, DOM_UF

__all__ = [
    "Cargo",
    "CentroCusto",
    "Departamento",
    "Empresa",
    "RedePermitida",
    "Unidade",
]


class Empresa(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Pessoa juridica empregadora dentro do tenant."""

    __tablename__ = "empresas"

    matriz_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="RESTRICT")
    )
    tipo: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'matriz'"))
    cnpj: Mapped[str] = mapped_column(DOM_CNPJ, nullable=False)
    razao_social: Mapped[str] = mapped_column(nullable=False)
    nome_fantasia: Mapped[str | None] = mapped_column()
    inscricao_estadual: Mapped[str | None] = mapped_column()
    inscricao_municipal: Mapped[str | None] = mapped_column()
    cnae_principal: Mapped[str | None] = mapped_column()
    cei_caepf: Mapped[str | None] = mapped_column()
    natureza_juridica: Mapped[str | None] = mapped_column()
    logradouro: Mapped[str | None] = mapped_column()
    numero: Mapped[str | None] = mapped_column()
    complemento: Mapped[str | None] = mapped_column()
    bairro: Mapped[str | None] = mapped_column()
    municipio: Mapped[str | None] = mapped_column()
    uf: Mapped[str | None] = mapped_column(DOM_UF)
    cep: Mapped[str | None] = mapped_column(DOM_CEP)
    codigo_ibge_municipio: Mapped[str | None] = mapped_column(DOM_IBGE)
    telefone: Mapped[str | None] = mapped_column()
    email: Mapped[str | None] = mapped_column(DOM_EMAIL)
    fuso_horario: Mapped[str] = mapped_column(
        DOM_FUSO, nullable=False, server_default=sa.text("'America/Sao_Paulo'")
    )
    logo_ref: Mapped[str | None] = mapped_column()
    ativo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))

    __table_args__ = (
        sa.CheckConstraint("tipo IN ('matriz','filial')", name="empresas_tipo_check"),
        sa.CheckConstraint(
            "(tipo = 'matriz' AND matriz_id IS NULL) OR "
            "(tipo = 'filial' AND matriz_id IS NOT NULL)",
            name="ck_empresas_matriz",
        ),
        sa.Index(
            "uq_empresas_cnpj",
            "tenant_id",
            "cnpj",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index(
            "ix_empresas_tenant",
            "tenant_id",
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index("ix_empresas_matriz", "tenant_id", "matriz_id"),
        {
            "comment": (
                "Pessoa juridica empregadora dentro do tenant. Matriz e filiais sao "
                "linhas distintas ligadas por matriz_id, cada uma com seu proprio CNPJ "
                "e seus proprios arquivos fiscais."
            )
        },
    )


class Unidade(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Local fisico de trabalho de uma empresa."""

    __tablename__ = "unidades"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="RESTRICT"), nullable=False
    )
    codigo: Mapped[str] = mapped_column(nullable=False)
    nome: Mapped[str] = mapped_column(nullable=False)
    tipo: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'filial'"))
    logradouro: Mapped[str | None] = mapped_column()
    numero: Mapped[str | None] = mapped_column()
    complemento: Mapped[str | None] = mapped_column()
    bairro: Mapped[str | None] = mapped_column()
    municipio: Mapped[str | None] = mapped_column()
    uf: Mapped[str | None] = mapped_column(DOM_UF)
    cep: Mapped[str | None] = mapped_column(DOM_CEP)
    codigo_ibge_municipio: Mapped[str | None] = mapped_column(DOM_IBGE)
    fuso_horario: Mapped[str] = mapped_column(
        DOM_FUSO, nullable=False, server_default=sa.text("'America/Sao_Paulo'")
    )
    geocerca_latitude: Mapped[decimal.Decimal | None] = mapped_column(sa.Numeric(10, 7))
    geocerca_longitude: Mapped[decimal.Decimal | None] = mapped_column(sa.Numeric(10, 7))
    geocerca_raio_metros: Mapped[int | None] = mapped_column()
    geocerca_poligono: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    geocerca_obrigatoria: Mapped[bool] = mapped_column(
        nullable=False, server_default=sa.text("TRUE")
    )
    geocerca_tolerancia_metros: Mapped[int] = mapped_column(
        nullable=False, server_default=sa.text("50")
    )
    ativo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))

    __table_args__ = (
        sa.CheckConstraint(
            "tipo IN ('sede','filial','obra','cliente','home_office','movel','deposito')",
            name="unidades_tipo_check",
        ),
        sa.CheckConstraint(
            "geocerca_raio_metros > 0 AND geocerca_raio_metros <= 100000",
            name="unidades_geocerca_raio_metros_check",
        ),
        sa.CheckConstraint(
            "geocerca_tolerancia_metros >= 0",
            name="unidades_geocerca_tolerancia_metros_check",
        ),
        sa.CheckConstraint(
            "(geocerca_latitude IS NULL AND geocerca_longitude IS NULL "
            "AND geocerca_raio_metros IS NULL) "
            "OR (geocerca_latitude IS NOT NULL AND geocerca_longitude IS NOT NULL "
            "AND geocerca_raio_metros IS NOT NULL)",
            name="ck_unidades_geocerca_ponto",
        ),
        sa.CheckConstraint(
            "geocerca_latitude IS NULL OR geocerca_latitude BETWEEN -90 AND 90",
            name="ck_unidades_latitude",
        ),
        sa.CheckConstraint(
            "geocerca_longitude IS NULL OR geocerca_longitude BETWEEN -180 AND 180",
            name="ck_unidades_longitude",
        ),
        sa.CheckConstraint(
            "geocerca_poligono IS NULL OR jsonb_typeof(geocerca_poligono) = 'object'",
            name="ck_unidades_poligono",
        ),
        sa.Index(
            "uq_unidades_codigo",
            "tenant_id",
            "empresa_id",
            "codigo",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index(
            "ix_unidades_empresa",
            "tenant_id",
            "empresa_id",
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index("ix_unidades_municipio", "tenant_id", "codigo_ibge_municipio"),
        {
            "comment": (
                "Local fisico de trabalho de uma empresa. Carrega o fuso horario efetivo "
                "do calculo de jornada, a geocerca do registro por app e o conjunto de "
                "feriados aplicavel."
            )
        },
    )


class RedePermitida(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Allowlist de faixas CIDR autorizadas a registrar ponto."""

    __tablename__ = "redes_permitidas"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False
    )
    unidade_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("unidades.id", ondelete="CASCADE")
    )
    cidr: Mapped[str] = mapped_column(CIDR, nullable=False)
    descricao: Mapped[str | None] = mapped_column()
    canal: Mapped[str | None] = mapped_column()
    ativo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))

    __table_args__ = (
        sa.CheckConstraint(
            "canal IN ('web','mobile','totem','api','terminal')",
            name="redes_permitidas_canal_check",
        ),
        sa.Index(
            "uq_redes_permitidas",
            "tenant_id",
            "empresa_id",
            sa.text("COALESCE(unidade_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            sa.text("COALESCE(canal, '*')"),
            "cidr",
            unique=True,
        ),
        sa.Index(
            "ix_redes_permitidas_lookup",
            "tenant_id",
            "empresa_id",
            "unidade_id",
            postgresql_where=sa.text("ativo"),
        ),
        {
            "comment": (
                "Allowlist de faixas CIDR (IPv4 e IPv6) autorizadas a registrar ponto. "
                "Escopo por empresa e, opcionalmente, por unidade e por canal."
            )
        },
    )


class Departamento(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Estrutura departamental hierarquica da empresa."""

    __tablename__ = "departamentos"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="RESTRICT"), nullable=False
    )
    departamento_pai_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("departamentos.id", ondelete="RESTRICT")
    )
    # FK criada depois de `colaboradores` (use_alter), como em schema.sql.
    responsavel_colaborador_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey(
            "colaboradores.id",
            ondelete="SET NULL",
            name="fk_departamentos_responsavel",
            use_alter=True,
        )
    )
    codigo: Mapped[str] = mapped_column(nullable=False)
    nome: Mapped[str] = mapped_column(nullable=False)
    descricao: Mapped[str | None] = mapped_column()
    ativo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))

    __table_args__ = (
        sa.Index(
            "uq_departamentos_codigo",
            "tenant_id",
            "empresa_id",
            "codigo",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index("ix_departamentos_pai", "tenant_id", "departamento_pai_id"),
        {
            "comment": (
                "Estrutura departamental hierarquica da empresa. Usada para escopo de "
                "perfil, agrupamento de relatorio e roteamento de aprovacao."
            )
        },
    )


class CentroCusto(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Centro de custo, projeto ou cliente ao qual as horas sao apropriadas."""

    __tablename__ = "centros_custo"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="RESTRICT"), nullable=False
    )
    centro_custo_pai_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("centros_custo.id", ondelete="RESTRICT")
    )
    codigo: Mapped[str] = mapped_column(nullable=False)
    nome: Mapped[str] = mapped_column(nullable=False)
    descricao: Mapped[str | None] = mapped_column()
    codigo_externo: Mapped[str | None] = mapped_column()
    ativo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))

    __table_args__ = (
        sa.Index(
            "uq_centros_custo_codigo",
            "tenant_id",
            "empresa_id",
            "codigo",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index("ix_centros_custo_pai", "tenant_id", "centro_custo_pai_id"),
        {
            "comment": (
                "Centro de custo, projeto ou cliente ao qual as horas sao apropriadas. "
                "Base do relatorio de horas por centro de custo e do rateio para a folha."
            )
        },
    )


class Cargo(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Cargo ocupado pelo colaborador, com CBO para o eSocial."""

    __tablename__ = "cargos"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="RESTRICT"), nullable=False
    )
    codigo: Mapped[str] = mapped_column(nullable=False)
    nome: Mapped[str] = mapped_column(nullable=False)
    cbo: Mapped[str | None] = mapped_column(DOM_CBO)
    descricao: Mapped[str | None] = mapped_column()
    nivel: Mapped[str | None] = mapped_column()
    salario_base: Mapped[decimal.Decimal | None] = mapped_column(sa.Numeric(14, 2))
    cargo_confianca: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))
    ativo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))

    __table_args__ = (
        sa.CheckConstraint(
            "nivel IN ('estagio','aprendiz','junior','pleno','senior','especialista',"
            "'coordenacao','gerencia','diretoria')",
            name="cargos_nivel_check",
        ),
        sa.CheckConstraint(
            "salario_base IS NULL OR salario_base >= 0", name="cargos_salario_base_check"
        ),
        sa.Index(
            "uq_cargos_codigo",
            "tenant_id",
            "empresa_id",
            "codigo",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index(
            "ix_cargos_empresa",
            "tenant_id",
            "empresa_id",
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        {"comment": "Cargo ocupado pelo colaborador, com CBO para o eSocial."},
    )
