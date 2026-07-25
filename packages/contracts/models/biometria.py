"""Grupo 5 - Biometria e dispositivos.

`biometrias`, `biometria_templates`, `dispositivos`, `dispositivo_vinculos`,
`terminais` e `terminal_saude`.

O template biometrico e dado pessoal sensivel (LGPD art. 5, II): fica cifrado
em `biometria_templates`, com a chave FORA do banco (referenciada por
`chave_id`), e a role `ponto_suporte` nao tem SELECT nessa tabela.

O terminal NAO e o REP-P. Ele identifica a pessoa e produz um `access_log`; o
REP-P e o nosso software, que atribui o NSR e grava no AFD.
"""

from __future__ import annotations

import datetime as _datetime
import decimal
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import BYTEA, INET
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
from .tipos import DOM_SHA256

__all__ = [
    "Biometria",
    "BiometriaTemplate",
    "Dispositivo",
    "DispositivoVinculo",
    "Terminal",
    "TerminalSaude",
]


class Biometria(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Credencial biometrica ou equivalente de um colaborador."""

    __tablename__ = "biometrias"

    colaborador_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("colaboradores.id", ondelete="RESTRICT"), nullable=False
    )
    modalidade: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'facial'"))
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'pendente'"))
    origem_cadastro: Mapped[str] = mapped_column(nullable=False)
    qualidade: Mapped[decimal.Decimal | None] = mapped_column(sa.Numeric(5, 2))
    # FK criada depois de `consentimentos` (use_alter), como em schema.sql.
    consentimento_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey(
            "consentimentos.id",
            ondelete="RESTRICT",
            name="fk_biometrias_consentimento",
            use_alter=True,
        )
    )
    identificador_cartao: Mapped[str | None] = mapped_column()
    cadastrada_em: Mapped[_datetime.datetime | None] = mapped_column()
    cadastrada_por: Mapped[uuid.UUID | None] = mapped_column()
    validada_em: Mapped[_datetime.datetime | None] = mapped_column()
    validada_por: Mapped[uuid.UUID | None] = mapped_column()
    revogada_em: Mapped[_datetime.datetime | None] = mapped_column()
    motivo_revogacao: Mapped[str | None] = mapped_column()
    expira_em: Mapped[_datetime.datetime | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "modalidade IN ('facial','digital','cartao','pin','qrcode')",
            name="biometrias_modalidade_check",
        ),
        sa.CheckConstraint(
            "status IN ('pendente','ativa','reprovada','revogada','expirada')",
            name="biometrias_status_check",
        ),
        sa.CheckConstraint(
            "origem_cadastro IN ('terminal','app','web','importacao','rh')",
            name="biometrias_origem_cadastro_check",
        ),
        sa.CheckConstraint(
            "qualidade IS NULL OR qualidade BETWEEN 0 AND 100",
            name="biometrias_qualidade_check",
        ),
        sa.Index(
            "uq_biometrias_ativa",
            "tenant_id",
            "colaborador_id",
            "modalidade",
            unique=True,
            postgresql_where=sa.text("status = 'ativa'"),
        ),
        sa.Index("ix_biometrias_colaborador", "tenant_id", "colaborador_id"),
        sa.Index(
            "ix_biometrias_expurgo",
            "tenant_id",
            "expira_em",
            postgresql_where=sa.text("expira_em IS NOT NULL"),
        ),
        {
            "comment": (
                "Credencial biometrica ou equivalente de um colaborador. Guarda o ciclo "
                "de vida; o vetor em si fica em biometria_templates."
            )
        },
    )


class BiometriaTemplate(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Vetor biometrico CIFRADO. Dado pessoal sensivel."""

    __tablename__ = "biometria_templates"

    biometria_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("biometrias.id", ondelete="CASCADE"), nullable=False
    )
    versao_modelo: Mapped[str] = mapped_column(nullable=False)
    provedor: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'facial-svc'"))
    dimensao: Mapped[int | None] = mapped_column()
    template_cifrado: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    iv: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    tag_autenticacao: Mapped[bytes | None] = mapped_column(BYTEA)
    algoritmo_cifra: Mapped[str] = mapped_column(
        nullable=False, server_default=sa.text("'AES-256-GCM'")
    )
    chave_id: Mapped[str] = mapped_column(nullable=False)
    hash_template: Mapped[str | None] = mapped_column(DOM_SHA256)
    ativo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))
    gerado_em: Mapped[_datetime.datetime] = mapped_column(
        nullable=False, server_default=sa.text("now()")
    )

    __table_args__ = (
        sa.CheckConstraint(
            "dimensao IS NULL OR dimensao > 0", name="biometria_templates_dimensao_check"
        ),
        sa.CheckConstraint(
            "algoritmo_cifra IN ('AES-256-GCM','AES-256-CBC','ChaCha20-Poly1305')",
            name="biometria_templates_algoritmo_cifra_check",
        ),
        sa.UniqueConstraint(
            "tenant_id", "biometria_id", "versao_modelo", name="uq_biometria_templates_versao"
        ),
        sa.Index(
            "ix_biometria_templates_biometria",
            "tenant_id",
            "biometria_id",
            postgresql_where=sa.text("ativo"),
        ),
        sa.Index("ix_biometria_templates_modelo", "tenant_id", "versao_modelo"),
        {
            "comment": (
                "Vetor biometrico CIFRADO. Dado pessoal sensivel (LGPD art. 5, II). "
                "Versionado por modelo. A role ponto_suporte NAO tem SELECT nesta tabela."
            )
        },
    )


class Dispositivo(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Qualquer aparelho capaz de originar uma marcacao."""

    __tablename__ = "dispositivos"

    empresa_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="RESTRICT")
    )
    unidade_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("unidades.id", ondelete="RESTRICT")
    )
    tipo: Mapped[str] = mapped_column(nullable=False)
    plataforma: Mapped[str | None] = mapped_column()
    identificador: Mapped[str] = mapped_column(nullable=False)
    nome: Mapped[str | None] = mapped_column()
    fabricante: Mapped[str | None] = mapped_column()
    modelo: Mapped[str | None] = mapped_column()
    versao_so: Mapped[str | None] = mapped_column()
    versao_app: Mapped[str | None] = mapped_column()
    chave_publica: Mapped[str | None] = mapped_column()
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'pendente'"))
    attestation_status: Mapped[str] = mapped_column(
        nullable=False, server_default=sa.text("'nao_verificado'")
    )
    attestation_verificado_em: Mapped[_datetime.datetime | None] = mapped_column()
    root_detectado: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))
    emulador_detectado: Mapped[bool] = mapped_column(
        nullable=False, server_default=sa.text("FALSE")
    )
    modo_desenvolvedor: Mapped[bool] = mapped_column(
        nullable=False, server_default=sa.text("FALSE")
    )
    depuracao_usb: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))
    ultimo_acesso_em: Mapped[_datetime.datetime | None] = mapped_column()
    ultimo_ip: Mapped[str | None] = mapped_column(INET)
    observacoes: Mapped[str | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "tipo IN ('terminal','celular','tablet','navegador','totem','integracao')",
            name="dispositivos_tipo_check",
        ),
        sa.CheckConstraint(
            "plataforma IN ('android','ios','web','linux','windows','macos','embarcado')",
            name="dispositivos_plataforma_check",
        ),
        sa.CheckConstraint(
            "status IN ('pendente','ativo','bloqueado','revogado','substituido')",
            name="dispositivos_status_check",
        ),
        sa.CheckConstraint(
            "attestation_status IN ('nao_verificado','aprovado','reprovado','indisponivel')",
            name="dispositivos_attestation_status_check",
        ),
        sa.Index(
            "uq_dispositivos_identificador",
            "tenant_id",
            "identificador",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index(
            "ix_dispositivos_empresa",
            "tenant_id",
            "empresa_id",
            "tipo",
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index("ix_dispositivos_status", "tenant_id", "status"),
        {
            "comment": (
                "Qualquer aparelho capaz de originar uma marcacao: terminal facial, "
                "celular, tablet de quiosque, navegador ou cliente de API."
            )
        },
    )


class DispositivoVinculo(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Vinculo entre aparelho pessoal e colaborador: um unico ativo por colaborador."""

    __tablename__ = "dispositivo_vinculos"

    dispositivo_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("dispositivos.id", ondelete="CASCADE"), nullable=False
    )
    colaborador_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("colaboradores.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'pendente'"))
    vinculado_em: Mapped[_datetime.datetime] = mapped_column(
        nullable=False, server_default=sa.text("now()")
    )
    aprovado_por: Mapped[uuid.UUID | None] = mapped_column()
    aprovado_em: Mapped[_datetime.datetime | None] = mapped_column()
    revogado_em: Mapped[_datetime.datetime | None] = mapped_column()
    motivo_revogacao: Mapped[str | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('pendente','ativo','revogado','recusado')",
            name="dispositivo_vinculos_status_check",
        ),
        sa.Index(
            "uq_dispositivo_vinculos_ativo",
            "tenant_id",
            "colaborador_id",
            unique=True,
            postgresql_where=sa.text("status = 'ativo'"),
        ),
        sa.Index("ix_dispositivo_vinculos_dispositivo", "tenant_id", "dispositivo_id"),
        {
            "comment": (
                "Vinculo entre aparelho pessoal e colaborador. Um unico dispositivo ativo "
                "por colaborador; a troca exige aprovacao do RH e fica registrada."
            )
        },
    )


class Terminal(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Coletor fisico de marcacao, tipicamente um Control iD iDFace."""

    __tablename__ = "terminais"

    dispositivo_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("dispositivos.id", ondelete="RESTRICT"), nullable=False
    )
    empresa_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="RESTRICT"), nullable=False
    )
    unidade_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("unidades.id", ondelete="RESTRICT")
    )
    # FK criada depois de `rep_ps` (use_alter), como em schema.sql.
    rep_p_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("rep_ps.id", ondelete="RESTRICT", name="fk_terminais_rep_p", use_alter=True)
    )
    fabricante: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'control_id'"))
    modelo: Mapped[str | None] = mapped_column()
    numero_serie: Mapped[str] = mapped_column(nullable=False)
    endereco_ip: Mapped[str | None] = mapped_column(INET)
    porta: Mapped[int | None] = mapped_column()
    mac: Mapped[str | None] = mapped_column()
    modo_comunicacao: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'push'"))
    usuario_api: Mapped[str | None] = mapped_column()
    senha_api_cifrada: Mapped[bytes | None] = mapped_column(BYTEA)
    chave_id: Mapped[str | None] = mapped_column()
    token_push: Mapped[str | None] = mapped_column()
    capacidade_faces: Mapped[int | None] = mapped_column()
    ultimo_log_externo_id: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, server_default=sa.text("0")
    )
    ultima_sincronizacao_em: Mapped[_datetime.datetime | None] = mapped_column()
    ultimo_contato_em: Mapped[_datetime.datetime | None] = mapped_column()
    intervalo_push_segundos: Mapped[int] = mapped_column(
        nullable=False, server_default=sa.text("30")
    )
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'ativo'"))

    __table_args__ = (
        sa.CheckConstraint(
            "fabricante IN ('control_id','henry','topdata','madis','dimep','inner','outro')",
            name="terminais_fabricante_check",
        ),
        sa.CheckConstraint(
            "porta IS NULL OR porta BETWEEN 1 AND 65535", name="terminais_porta_check"
        ),
        sa.CheckConstraint(
            "modo_comunicacao IN ('push','monitor','polling','direto')",
            name="terminais_modo_comunicacao_check",
        ),
        sa.CheckConstraint(
            "intervalo_push_segundos > 0", name="terminais_intervalo_push_segundos_check"
        ),
        sa.CheckConstraint(
            "status IN ('ativo','inativo','manutencao','desativado')",
            name="terminais_status_check",
        ),
        sa.Index(
            "uq_terminais_serie",
            "tenant_id",
            "numero_serie",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index(
            "uq_terminais_dispositivo",
            "tenant_id",
            "dispositivo_id",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index(
            "ix_terminais_unidade",
            "tenant_id",
            "unidade_id",
            postgresql_where=sa.text("status = 'ativo'"),
        ),
        sa.Index(
            "ix_terminais_contato",
            "tenant_id",
            "ultimo_contato_em",
            postgresql_where=sa.text("status = 'ativo'"),
        ),
        {
            "comment": (
                "Coletor fisico de marcacao, tipicamente um Control iD iDFace. O terminal "
                "NAO e o REP-P: ele identifica a pessoa e produz um access_log."
            )
        },
    )


class TerminalSaude(ChavePrimariaUUIDMixin, TenantMixin, CriacaoMixin, Base):
    """Serie temporal de saude dos coletores. APPEND-ONLY."""

    __tablename__ = "terminal_saude"

    terminal_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("terminais.id", ondelete="CASCADE"), nullable=False
    )
    verificado_em: Mapped[_datetime.datetime] = mapped_column(
        nullable=False, server_default=sa.text("now()")
    )
    online: Mapped[bool] = mapped_column(nullable=False)
    latencia_ms: Mapped[int | None] = mapped_column()
    firmware: Mapped[str | None] = mapped_column()
    faces_cadastradas: Mapped[int | None] = mapped_column()
    logs_pendentes: Mapped[int | None] = mapped_column()
    memoria_livre_pct: Mapped[decimal.Decimal | None] = mapped_column(sa.Numeric(5, 2))
    temperatura: Mapped[decimal.Decimal | None] = mapped_column(sa.Numeric(5, 2))
    alarme: Mapped[str | None] = mapped_column()
    mensagem: Mapped[str | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "latencia_ms IS NULL OR latencia_ms >= 0", name="terminal_saude_latencia_ms_check"
        ),
        sa.Index(
            "ix_terminal_saude_terminal",
            "tenant_id",
            "terminal_id",
            sa.text("verificado_em DESC"),
        ),
        sa.Index(
            "ix_terminal_saude_offline",
            "tenant_id",
            sa.text("verificado_em DESC"),
            postgresql_where=sa.text("NOT online"),
        ),
        {
            "comment": (
                "Serie temporal de saude dos coletores. Append-only: cada verificacao "
                "gera uma linha nova, nunca atualiza a anterior."
            )
        },
    )
