"""Grupo 4 - Pessoas: colaboradores, contratos, vinculos, gestores, equipes e documentos.

Fronteira que o glossario fixa e que nenhuma fase pode borrar:

* `colaboradores` e a PESSOA (dados cadastrais e pessoais).
* `contratos` e o INSTRUMENTO JURIDICO (tipo de contratacao, cargo, salario,
  carga contratada, art. 62, vigencia).
* `vinculos` e a RELACAO DE TRABALHO na granularidade do AEJ e do eSocial.
  **Todo o motor de apuracao pendura em `vinculo_id`, nunca em
  `colaborador_id`.**
"""

from __future__ import annotations

import datetime as _datetime
import decimal
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .mixins import (
    AuditoriaMixin,
    ChavePrimariaUUIDMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)
from .tipos import DOM_CEP, DOM_CPF, DOM_EMAIL, DOM_IBGE, DOM_PIS, DOM_SHA256, DOM_UF

__all__ = [
    "Colaborador",
    "ColaboradorGestor",
    "Contrato",
    "Documento",
    "Equipe",
    "EquipeMembro",
    "Vinculo",
]


class Colaborador(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """A PESSOA que trabalha."""

    __tablename__ = "colaboradores"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="RESTRICT"), nullable=False
    )
    matricula: Mapped[str] = mapped_column(nullable=False)
    cpf: Mapped[str] = mapped_column(DOM_CPF, nullable=False)
    pis_nit: Mapped[str | None] = mapped_column(DOM_PIS)
    nome_completo: Mapped[str] = mapped_column(nullable=False)
    nome_social: Mapped[str | None] = mapped_column()
    data_nascimento: Mapped[_datetime.date | None] = mapped_column()
    sexo: Mapped[str | None] = mapped_column()
    estado_civil: Mapped[str | None] = mapped_column()
    nacionalidade: Mapped[str | None] = mapped_column()
    naturalidade: Mapped[str | None] = mapped_column()
    nome_mae: Mapped[str | None] = mapped_column()
    rg_numero: Mapped[str | None] = mapped_column()
    rg_orgao_emissor: Mapped[str | None] = mapped_column()
    rg_uf: Mapped[str | None] = mapped_column(DOM_UF)
    ctps_numero: Mapped[str | None] = mapped_column()
    ctps_serie: Mapped[str | None] = mapped_column()
    ctps_uf: Mapped[str | None] = mapped_column(DOM_UF)
    titulo_eleitor: Mapped[str | None] = mapped_column()
    email: Mapped[str | None] = mapped_column(DOM_EMAIL)
    telefone: Mapped[str | None] = mapped_column()
    telefone_alternativo: Mapped[str | None] = mapped_column()
    foto_ref: Mapped[str | None] = mapped_column()
    logradouro: Mapped[str | None] = mapped_column()
    numero: Mapped[str | None] = mapped_column()
    complemento: Mapped[str | None] = mapped_column()
    bairro: Mapped[str | None] = mapped_column()
    municipio: Mapped[str | None] = mapped_column()
    uf: Mapped[str | None] = mapped_column(DOM_UF)
    cep: Mapped[str | None] = mapped_column(DOM_CEP)
    codigo_ibge_municipio: Mapped[str | None] = mapped_column(DOM_IBGE)
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'ativo'"))
    data_admissao: Mapped[_datetime.date | None] = mapped_column()
    data_desligamento: Mapped[_datetime.date | None] = mapped_column()
    pcd: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))
    observacoes: Mapped[str | None] = mapped_column()
    codigo_externo: Mapped[str | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "sexo IN ('feminino','masculino','outro','nao_informado')",
            name="colaboradores_sexo_check",
        ),
        sa.CheckConstraint(
            "estado_civil IN ('solteiro','casado','divorciado','viuvo','uniao_estavel',"
            "'separado')",
            name="colaboradores_estado_civil_check",
        ),
        sa.CheckConstraint(
            "status IN ('pre_admissao','ativo','afastado','ferias','suspenso','desligado')",
            name="colaboradores_status_check",
        ),
        sa.CheckConstraint(
            "data_desligamento IS NULL OR data_admissao IS NULL "
            "OR data_desligamento >= data_admissao",
            name="ck_colaboradores_desligamento",
        ),
        sa.Index(
            "uq_colaboradores_matricula",
            "tenant_id",
            "empresa_id",
            "matricula",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index(
            "uq_colaboradores_cpf",
            "tenant_id",
            "empresa_id",
            "cpf",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index(
            "ix_colaboradores_empresa_status",
            "tenant_id",
            "empresa_id",
            "status",
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index("ix_colaboradores_cpf", "tenant_id", "cpf"),
        sa.Index(
            "ix_colaboradores_nome_trgm",
            "nome_completo",
            postgresql_using="gin",
            postgresql_ops={"nome_completo": "gin_trgm_ops"},
        ),
        {
            "comment": (
                "A PESSOA que trabalha. Guarda os dados cadastrais e pessoais. As "
                "condicoes de trabalho vivem em contratos e vinculos."
            )
        },
    )


class Contrato(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Instrumento juridico entre colaborador e empresa."""

    __tablename__ = "contratos"

    colaborador_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("colaboradores.id", ondelete="RESTRICT"), nullable=False
    )
    empresa_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="RESTRICT"), nullable=False
    )
    numero: Mapped[str | None] = mapped_column()
    tipo: Mapped[str] = mapped_column(nullable=False)
    regime_jornada: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'fixa'"))
    cargo_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("cargos.id", ondelete="RESTRICT")
    )
    departamento_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("departamentos.id", ondelete="RESTRICT")
    )
    centro_custo_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("centros_custo.id", ondelete="RESTRICT")
    )
    unidade_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("unidades.id", ondelete="RESTRICT")
    )
    data_inicio: Mapped[_datetime.date] = mapped_column(nullable=False)
    data_fim: Mapped[_datetime.date | None] = mapped_column()
    experiencia_dias: Mapped[int | None] = mapped_column()
    salario: Mapped[decimal.Decimal | None] = mapped_column(sa.Numeric(14, 2))
    tipo_salario: Mapped[str | None] = mapped_column()
    carga_horaria_semanal_minutos: Mapped[int | None] = mapped_column()
    carga_horaria_mensal_minutos: Mapped[int | None] = mapped_column()
    controle_jornada: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))
    dispensa_controle_motivo: Mapped[str | None] = mapped_column()
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'ativo'"))
    motivo_encerramento: Mapped[str | None] = mapped_column()
    # FK criada depois de `documentos` (use_alter): quebra o ciclo
    # contratos -> documentos -> vinculos -> contratos, como em schema.sql.
    documento_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey(
            "documentos.id",
            ondelete="SET NULL",
            name="fk_contratos_documento",
            use_alter=True,
        )
    )

    __table_args__ = (
        sa.CheckConstraint(
            "tipo IN ('clt','aprendiz','estagio','temporario','intermitente','avulso',"
            "'autonomo','pj','socio','servidor')",
            name="contratos_tipo_check",
        ),
        sa.CheckConstraint(
            "regime_jornada IN ('fixa','flexivel','livre','escala','12x36','parcial',"
            "'teletrabalho','externo','sobreaviso')",
            name="contratos_regime_jornada_check",
        ),
        sa.CheckConstraint(
            "experiencia_dias IS NULL OR experiencia_dias BETWEEN 0 AND 90",
            name="contratos_experiencia_dias_check",
        ),
        sa.CheckConstraint("salario IS NULL OR salario >= 0", name="contratos_salario_check"),
        sa.CheckConstraint(
            "tipo_salario IN ('mensal','horista','diarista','semanal','comissionado','tarefa')",
            name="contratos_tipo_salario_check",
        ),
        sa.CheckConstraint(
            "carga_horaria_semanal_minutos IS NULL "
            "OR carga_horaria_semanal_minutos BETWEEN 0 AND 4200",
            name="contratos_carga_horaria_semanal_minutos_check",
        ),
        sa.CheckConstraint(
            "carga_horaria_mensal_minutos IS NULL OR carga_horaria_mensal_minutos >= 0",
            name="contratos_carga_horaria_mensal_minutos_check",
        ),
        sa.CheckConstraint(
            "dispensa_controle_motivo IN ('art62_i_externo','art62_ii_gestao',"
            "'art62_iii_teletrabalho')",
            name="contratos_dispensa_controle_motivo_check",
        ),
        sa.CheckConstraint(
            "status IN ('rascunho','ativo','suspenso','encerrado')",
            name="contratos_status_check",
        ),
        sa.CheckConstraint(
            "data_fim IS NULL OR data_fim >= data_inicio", name="ck_contratos_periodo"
        ),
        sa.CheckConstraint(
            "(controle_jornada = TRUE  AND dispensa_controle_motivo IS NULL) OR "
            "(controle_jornada = FALSE AND dispensa_controle_motivo IS NOT NULL)",
            name="ck_contratos_dispensa",
        ),
        sa.Index(
            "ix_contratos_colaborador",
            "tenant_id",
            "colaborador_id",
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index(
            "ix_contratos_vigentes",
            "tenant_id",
            "empresa_id",
            "data_inicio",
            "data_fim",
            postgresql_where=sa.text("status = 'ativo'"),
        ),
        {
            "comment": (
                "Instrumento juridico entre colaborador e empresa: tipo de contratacao, "
                "cargo, remuneracao, carga contratada e vigencia."
            )
        },
    )


class Vinculo(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """A RELACAO DE TRABALHO efetiva. Chave de apuracao."""

    __tablename__ = "vinculos"

    colaborador_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("colaboradores.id", ondelete="RESTRICT"), nullable=False
    )
    empresa_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="RESTRICT"), nullable=False
    )
    contrato_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("contratos.id", ondelete="RESTRICT")
    )
    matricula_esocial: Mapped[str] = mapped_column(nullable=False)
    categoria_esocial: Mapped[int | None] = mapped_column(sa.SmallInteger)
    tipo_vinculo: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'empregado'"))
    unidade_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("unidades.id", ondelete="RESTRICT")
    )
    departamento_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("departamentos.id", ondelete="RESTRICT")
    )
    centro_custo_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("centros_custo.id", ondelete="RESTRICT")
    )
    cargo_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("cargos.id", ondelete="RESTRICT")
    )
    data_inicio: Mapped[_datetime.date] = mapped_column(nullable=False)
    data_fim: Mapped[_datetime.date | None] = mapped_column()
    motivo_desligamento: Mapped[str | None] = mapped_column()
    principal: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))
    apura_ponto: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'ativo'"))

    __table_args__ = (
        sa.CheckConstraint(
            "tipo_vinculo IN ('empregado','estagiario','aprendiz','temporario','avulso',"
            "'autonomo','cooperado','diretor','servidor')",
            name="vinculos_tipo_vinculo_check",
        ),
        sa.CheckConstraint(
            "status IN ('ativo','suspenso','encerrado')", name="vinculos_status_check"
        ),
        sa.CheckConstraint(
            "data_fim IS NULL OR data_fim >= data_inicio", name="ck_vinculos_periodo"
        ),
        ExcludeConstraint(
            ("tenant_id", "="),
            ("colaborador_id", "="),
            ("empresa_id", "="),
            (
                sa.text("daterange(data_inicio, COALESCE(data_fim, DATE 'infinity'), '[]')"),
                "&&",
            ),
            name="ex_vinculos_sobreposicao",
            using="gist",
            where=sa.text("excluido_em IS NULL AND status <> 'encerrado'"),
        ),
        sa.Index(
            "uq_vinculos_matricula_esocial",
            "tenant_id",
            "empresa_id",
            "matricula_esocial",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index(
            "ix_vinculos_colaborador",
            "tenant_id",
            "colaborador_id",
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index(
            "ix_vinculos_apuracao",
            "tenant_id",
            "empresa_id",
            "status",
            "data_inicio",
            "data_fim",
            postgresql_where=sa.text("apura_ponto"),
        ),
        sa.Index(
            "ix_vinculos_unidade",
            "tenant_id",
            "unidade_id",
            postgresql_where=sa.text("status = 'ativo'"),
        ),
        {
            "comment": (
                "A RELACAO DE TRABALHO efetiva, na granularidade que o AEJ e o eSocial "
                "exigem. Toda apuracao pendura em um vinculo, nao no colaborador."
            )
        },
    )


class ColaboradorGestor(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Hierarquia de gestao com historico."""

    __tablename__ = "colaborador_gestores"

    colaborador_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("colaboradores.id", ondelete="CASCADE"), nullable=False
    )
    gestor_colaborador_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("colaboradores.id", ondelete="RESTRICT"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'imediato'"))
    vigencia_inicio: Mapped[_datetime.date] = mapped_column(
        nullable=False, server_default=sa.text("CURRENT_DATE")
    )
    vigencia_fim: Mapped[_datetime.date | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "tipo IN ('imediato','substituto','matricial','rh')",
            name="colaborador_gestores_tipo_check",
        ),
        sa.CheckConstraint(
            "colaborador_id <> gestor_colaborador_id",
            name="ck_colaborador_gestores_distintos",
        ),
        sa.CheckConstraint(
            "vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio",
            name="ck_colaborador_gestores_vigencia",
        ),
        ExcludeConstraint(
            ("tenant_id", "="),
            ("colaborador_id", "="),
            (
                sa.text(
                    "daterange(vigencia_inicio, COALESCE(vigencia_fim, DATE 'infinity'), '[]')"
                ),
                "&&",
            ),
            name="ex_colaborador_gestores_imediato",
            using="gist",
            where=sa.text("tipo = 'imediato'"),
        ),
        sa.Index(
            "ix_colaborador_gestores_gestor",
            "tenant_id",
            "gestor_colaborador_id",
            "vigencia_inicio",
            "vigencia_fim",
        ),
        sa.Index("ix_colaborador_gestores_colaborador", "tenant_id", "colaborador_id"),
        {
            "comment": (
                "Hierarquia de gestao com historico. Define a arvore de subordinados que "
                "o perfil gestor enxerga e a cadeia de aprovacao das solicitacoes."
            )
        },
    )


class Equipe(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Agrupamento operacional de colaboradores para escala e cobertura de turno."""

    __tablename__ = "equipes"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="RESTRICT"), nullable=False
    )
    unidade_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("unidades.id", ondelete="RESTRICT")
    )
    departamento_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("departamentos.id", ondelete="RESTRICT")
    )
    gestor_colaborador_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("colaboradores.id", ondelete="SET NULL")
    )
    codigo: Mapped[str] = mapped_column(nullable=False)
    nome: Mapped[str] = mapped_column(nullable=False)
    descricao: Mapped[str | None] = mapped_column()
    cor: Mapped[str | None] = mapped_column()
    ativo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))

    __table_args__ = (
        sa.CheckConstraint(r"cor IS NULL OR cor ~ '^#[0-9A-Fa-f]{6}$'", name="equipes_cor_check"),
        sa.Index(
            "uq_equipes_codigo",
            "tenant_id",
            "empresa_id",
            "codigo",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index("ix_equipes_gestor", "tenant_id", "gestor_colaborador_id"),
        {
            "comment": (
                "Agrupamento operacional de colaboradores para escala, cobertura de turno "
                "e visao do gestor. Ortogonal ao departamento."
            )
        },
    )


class EquipeMembro(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Participacao datada de um colaborador em uma equipe."""

    __tablename__ = "equipe_membros"

    equipe_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("equipes.id", ondelete="CASCADE"), nullable=False
    )
    colaborador_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("colaboradores.id", ondelete="CASCADE"), nullable=False
    )
    papel: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'membro'"))
    vigencia_inicio: Mapped[_datetime.date] = mapped_column(
        nullable=False, server_default=sa.text("CURRENT_DATE")
    )
    vigencia_fim: Mapped[_datetime.date | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "papel IN ('membro','lider','substituto')", name="equipe_membros_papel_check"
        ),
        sa.CheckConstraint(
            "vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio",
            name="ck_equipe_membros_vigencia",
        ),
        ExcludeConstraint(
            ("tenant_id", "="),
            ("equipe_id", "="),
            ("colaborador_id", "="),
            (
                sa.text(
                    "daterange(vigencia_inicio, COALESCE(vigencia_fim, DATE 'infinity'), '[]')"
                ),
                "&&",
            ),
            name="ex_equipe_membros_sobreposicao",
            using="gist",
        ),
        sa.Index("ix_equipe_membros_colaborador", "tenant_id", "colaborador_id"),
        sa.Index("ix_equipe_membros_equipe", "tenant_id", "equipe_id", "vigencia_inicio"),
        {"comment": "Participacao datada de um colaborador em uma equipe."},
    )


class Documento(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Documentos digitalizados de pessoas, vinculos e empresas."""

    __tablename__ = "documentos"

    colaborador_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("colaboradores.id", ondelete="CASCADE")
    )
    vinculo_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("vinculos.id", ondelete="CASCADE")
    )
    empresa_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="CASCADE")
    )
    tipo: Mapped[str] = mapped_column(nullable=False)
    nome_arquivo: Mapped[str] = mapped_column(nullable=False)
    conteudo_ref: Mapped[str] = mapped_column(nullable=False)
    mime_type: Mapped[str | None] = mapped_column()
    tamanho_bytes: Mapped[int | None] = mapped_column(sa.BigInteger)
    hash_sha256: Mapped[str | None] = mapped_column(DOM_SHA256)
    data_emissao: Mapped[_datetime.date | None] = mapped_column()
    data_validade: Mapped[_datetime.date | None] = mapped_column()
    confidencial: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))
    descricao: Mapped[str | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "tipo IN ('rg','cpf','ctps','comprovante_residencia','atestado','contrato',"
            "'acordo_banco_horas','acordo_compensacao','termo_consentimento','certificado',"
            "'aso','advertencia','rescisao','outro')",
            name="documentos_tipo_check",
        ),
        sa.CheckConstraint(
            "tamanho_bytes IS NULL OR tamanho_bytes >= 0",
            name="documentos_tamanho_bytes_check",
        ),
        sa.CheckConstraint(
            "colaborador_id IS NOT NULL OR vinculo_id IS NOT NULL OR empresa_id IS NOT NULL",
            name="ck_documentos_alvo",
        ),
        sa.Index(
            "ix_documentos_colaborador",
            "tenant_id",
            "colaborador_id",
            "tipo",
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index(
            "ix_documentos_validade",
            "tenant_id",
            "data_validade",
            postgresql_where=sa.text("data_validade IS NOT NULL AND excluido_em IS NULL"),
        ),
        {
            "comment": (
                "Documentos digitalizados de pessoas, vinculos e empresas. O binario fica "
                "no MinIO; aqui ficam metadados, hash e classificacao de confidencialidade."
            )
        },
    )
