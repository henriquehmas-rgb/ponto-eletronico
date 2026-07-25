"""Grupo 3 - Identidade, acesso e RBAC.

`usuarios`, `credenciais`, `sessoes`, `refresh_tokens`, `mfa_dispositivos`,
`perfis`, `permissoes`, `perfil_permissoes`, `usuario_perfis` e `delegacoes`.

Duas particularidades do contrato aparecem aqui:

* `permissoes` e a UNICA tabela de dominio, alem de `tenants`, sem `tenant_id`.
  E o catalogo global de recursos e acoes do produto, identico em todos os
  tenants e somente leitura para a aplicacao. Fica fora da RLS por decisao
  consciente, registrada no glossario.
* Usuario nao e colaborador. Nem todo colaborador tem usuario (quem so bate
  ponto no terminal nao precisa) e nem todo usuario e colaborador (suporte
  SEEG, contas de integracao).
"""

from __future__ import annotations

import datetime as _datetime
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import BYTEA, INET, JSONB, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .mixins import (
    AuditoriaMixin,
    ChavePrimariaUUIDMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)
from .tipos import DOM_EMAIL, DOM_FUSO, DOM_SHA256

__all__ = [
    "Credencial",
    "Delegacao",
    "MfaDispositivo",
    "Perfil",
    "PerfilPermissao",
    "Permissao",
    "RefreshToken",
    "Sessao",
    "Usuario",
    "UsuarioPerfil",
]


class Usuario(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Identidade de acesso ao sistema."""

    __tablename__ = "usuarios"

    # FK criada depois de `colaboradores` (use_alter), como em schema.sql.
    colaborador_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey(
            "colaboradores.id",
            ondelete="SET NULL",
            name="fk_usuarios_colaborador",
            use_alter=True,
        )
    )
    email: Mapped[str] = mapped_column(DOM_EMAIL, nullable=False)
    email_verificado_em: Mapped[_datetime.datetime | None] = mapped_column()
    nome_completo: Mapped[str] = mapped_column(nullable=False)
    telefone: Mapped[str | None] = mapped_column()
    avatar_ref: Mapped[str | None] = mapped_column()
    tipo: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'humano'"))
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'convidado'"))
    idioma: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'pt-BR'"))
    fuso_horario: Mapped[str] = mapped_column(
        DOM_FUSO, nullable=False, server_default=sa.text("'America/Sao_Paulo'")
    )
    mfa_obrigatorio: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))
    ultimo_acesso_em: Mapped[_datetime.datetime | None] = mapped_column()
    ultimo_acesso_ip: Mapped[str | None] = mapped_column(INET)
    aceite_termos_em: Mapped[_datetime.datetime | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint("tipo IN ('humano','servico','suporte')", name="usuarios_tipo_check"),
        sa.CheckConstraint(
            "status IN ('convidado','ativo','bloqueado','inativo')",
            name="usuarios_status_check",
        ),
        sa.Index(
            "uq_usuarios_email",
            "tenant_id",
            sa.text("lower(email)"),
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index(
            "uq_usuarios_colaborador",
            "tenant_id",
            "colaborador_id",
            unique=True,
            postgresql_where=sa.text("colaborador_id IS NOT NULL AND excluido_em IS NULL"),
        ),
        sa.Index(
            "ix_usuarios_status",
            "tenant_id",
            "status",
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        {
            "comment": (
                "Identidade de acesso ao sistema. Distinta de colaborador: nem todo "
                "colaborador tem usuario e nem todo usuario e colaborador."
            )
        },
    )


class Credencial(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Segredos de autenticacao do usuario. A coluna `hash` nunca guarda o segredo em claro."""

    __tablename__ = "credenciais"

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(nullable=False)
    hash: Mapped[str] = mapped_column(nullable=False)
    algoritmo: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'argon2id'"))
    provedor_sso: Mapped[str | None] = mapped_column()
    identificador_externo: Mapped[str | None] = mapped_column()
    trocar_no_proximo_acesso: Mapped[bool] = mapped_column(
        nullable=False, server_default=sa.text("FALSE")
    )
    expira_em: Mapped[_datetime.datetime | None] = mapped_column()
    tentativas_falhas: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    bloqueado_ate: Mapped[_datetime.datetime | None] = mapped_column()
    ultima_troca_em: Mapped[_datetime.datetime | None] = mapped_column()
    ativo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))

    __table_args__ = (
        sa.CheckConstraint(
            "tipo IN ('senha','pin','certificado','sso','recuperacao')",
            name="credenciais_tipo_check",
        ),
        sa.CheckConstraint(
            "algoritmo IN ('argon2id','bcrypt','scrypt','pbkdf2','nenhum')",
            name="credenciais_algoritmo_check",
        ),
        sa.CheckConstraint(
            "provedor_sso IN ('google','entra_id','saml','okta')",
            name="credenciais_provedor_sso_check",
        ),
        sa.CheckConstraint("tentativas_falhas >= 0", name="credenciais_tentativas_falhas_check"),
        sa.Index(
            "uq_credenciais_ativa",
            "tenant_id",
            "usuario_id",
            "tipo",
            unique=True,
            postgresql_where=sa.text("ativo"),
        ),
        sa.Index("ix_credenciais_usuario", "tenant_id", "usuario_id"),
        sa.Index(
            "ix_credenciais_sso",
            "tenant_id",
            "provedor_sso",
            "identificador_externo",
            postgresql_where=sa.text("provedor_sso IS NOT NULL"),
        ),
        {
            "comment": (
                "Segredos de autenticacao do usuario. Uma linha ativa por tipo. Senhas "
                "em Argon2id; a coluna hash nunca guarda o segredo em claro."
            )
        },
    )


class Sessao(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Sessao de acesso ativa ou encerrada."""

    __tablename__ = "sessoes"

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    # FK criada depois de `dispositivos` (use_alter), como em schema.sql.
    dispositivo_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey(
            "dispositivos.id",
            ondelete="SET NULL",
            name="fk_sessoes_dispositivo",
            use_alter=True,
        )
    )
    canal: Mapped[str] = mapped_column(nullable=False)
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column()
    fingerprint: Mapped[str | None] = mapped_column()
    geolocalizacao: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    iniciada_em: Mapped[_datetime.datetime] = mapped_column(
        nullable=False, server_default=sa.text("now()")
    )
    ultima_atividade_em: Mapped[_datetime.datetime] = mapped_column(
        nullable=False, server_default=sa.text("now()")
    )
    expira_em: Mapped[_datetime.datetime] = mapped_column(nullable=False)
    encerrada_em: Mapped[_datetime.datetime | None] = mapped_column()
    motivo_encerramento: Mapped[str | None] = mapped_column()
    mfa_validado_em: Mapped[_datetime.datetime | None] = mapped_column()
    reautenticado_em: Mapped[_datetime.datetime | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "canal IN ('web','mobile','totem','api','terminal')", name="sessoes_canal_check"
        ),
        sa.CheckConstraint(
            "motivo_encerramento IN ('logout','expiracao','inatividade','revogacao_admin',"
            "'troca_senha','reuso_token','dispositivo_revogado')",
            name="sessoes_motivo_encerramento_check",
        ),
        sa.CheckConstraint("expira_em > iniciada_em", name="ck_sessoes_expiracao"),
        sa.Index("ix_sessoes_usuario", "tenant_id", "usuario_id", sa.text("iniciada_em DESC")),
        sa.Index(
            "ix_sessoes_ativas",
            "tenant_id",
            "expira_em",
            postgresql_where=sa.text("encerrada_em IS NULL"),
        ),
        sa.Index(
            "ix_sessoes_dispositivo",
            "tenant_id",
            "dispositivo_id",
            postgresql_where=sa.text("dispositivo_id IS NOT NULL"),
        ),
        {
            "comment": (
                "Sessao de acesso ativa ou encerrada. Uma sessao agrupa a familia de "
                "refresh tokens e permite revogacao em massa por usuario ou dispositivo."
            )
        },
    )


class RefreshToken(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Refresh tokens com rotacao e deteccao de reuso por familia."""

    __tablename__ = "refresh_tokens"

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    sessao_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("sessoes.id", ondelete="CASCADE"), nullable=False
    )
    familia_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    antecessor_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )
    token_hash: Mapped[str] = mapped_column(DOM_SHA256, nullable=False)
    emitido_em: Mapped[_datetime.datetime] = mapped_column(
        nullable=False, server_default=sa.text("now()")
    )
    expira_em: Mapped[_datetime.datetime] = mapped_column(nullable=False)
    usado_em: Mapped[_datetime.datetime | None] = mapped_column()
    revogado_em: Mapped[_datetime.datetime | None] = mapped_column()
    motivo_revogacao: Mapped[str | None] = mapped_column()
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "motivo_revogacao IN ('rotacao','logout','reuso_detectado','expiracao',"
            "'revogacao_admin','troca_senha')",
            name="refresh_tokens_motivo_revogacao_check",
        ),
        sa.UniqueConstraint("tenant_id", "token_hash", name="uq_refresh_tokens_hash"),
        sa.Index("ix_refresh_tokens_familia", "tenant_id", "familia_id"),
        sa.Index(
            "ix_refresh_tokens_usuario",
            "tenant_id",
            "usuario_id",
            sa.text("emitido_em DESC"),
        ),
        sa.Index(
            "ix_refresh_tokens_validos",
            "tenant_id",
            "expira_em",
            postgresql_where=sa.text("revogado_em IS NULL AND usado_em IS NULL"),
        ),
        {
            "comment": (
                "Refresh tokens com rotacao. Reapresentar um token ja usado invalida a "
                "familia inteira (deteccao de reuso)."
            )
        },
    )


class MfaDispositivo(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Segundo fator registrado pelo usuario."""

    __tablename__ = "mfa_dispositivos"

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(nullable=False)
    rotulo: Mapped[str] = mapped_column(nullable=False)
    segredo_cifrado: Mapped[bytes | None] = mapped_column(BYTEA)
    iv: Mapped[bytes | None] = mapped_column(BYTEA)
    chave_id: Mapped[str | None] = mapped_column()
    credencial_publica: Mapped[bytes | None] = mapped_column(BYTEA)
    contador: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, server_default=sa.text("0")
    )
    confirmado_em: Mapped[_datetime.datetime | None] = mapped_column()
    ultimo_uso_em: Mapped[_datetime.datetime | None] = mapped_column()
    ativo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))

    __table_args__ = (
        sa.CheckConstraint(
            "tipo IN ('totp','sms','email','webauthn','codigos_backup')",
            name="mfa_dispositivos_tipo_check",
        ),
        sa.Index(
            "ix_mfa_dispositivos_usuario",
            "tenant_id",
            "usuario_id",
            postgresql_where=sa.text("ativo"),
        ),
        {
            "comment": (
                "Segundo fator registrado pelo usuario. O segredo TOTP e guardado "
                "cifrado com chave externa ao banco."
            )
        },
    )


class Perfil(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Papel do RBAC."""

    __tablename__ = "perfis"

    codigo: Mapped[str] = mapped_column(nullable=False)
    nome: Mapped[str] = mapped_column(nullable=False)
    descricao: Mapped[str | None] = mapped_column()
    sistema: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))
    escopo_padrao: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'tenant'"))
    somente_leitura: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))
    ativo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))

    __table_args__ = (
        sa.CheckConstraint(
            "escopo_padrao IN ('global','tenant','empresa','unidade','departamento',"
            "'equipe','proprio')",
            name="perfis_escopo_padrao_check",
        ),
        sa.Index(
            "uq_perfis_codigo",
            "tenant_id",
            "codigo",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        {
            "comment": (
                "Papel do RBAC. Os perfis de fabrica sao super_admin, admin_empresa, rh, "
                "gestor, colaborador, auditor e integracao; o tenant pode criar os seus."
            )
        },
    )


class Permissao(ChavePrimariaUUIDMixin, TimestampMixin, AuditoriaMixin, Base):
    """Catalogo GLOBAL de permissoes do produto (recurso + acao). Sem `tenant_id`."""

    __tablename__ = "permissoes"

    codigo: Mapped[str] = mapped_column(nullable=False)
    recurso: Mapped[str] = mapped_column(nullable=False)
    acao: Mapped[str] = mapped_column(nullable=False)
    descricao: Mapped[str] = mapped_column(nullable=False)
    sensivel: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))
    modulo: Mapped[str] = mapped_column(nullable=False)

    __table_args__ = (
        sa.CheckConstraint(
            "acao IN ('ler','criar','editar','excluir','aprovar','exportar','executar',"
            "'assinar','administrar','configurar','reabrir','ler_sensivel')",
            name="permissoes_acao_check",
        ),
        sa.UniqueConstraint("codigo", name="uq_permissoes_codigo"),
        sa.UniqueConstraint("recurso", "acao", name="uq_permissoes_recurso_acao"),
        sa.Index("ix_permissoes_modulo", "modulo", "recurso"),
        {
            "comment": (
                "Catalogo GLOBAL de permissoes do produto (recurso mais acao). Unica "
                "tabela sem tenant_id alem de tenants: as permissoes correspondem a "
                "endpoints do codigo e sao somente leitura para a aplicacao."
            )
        },
    )


class PerfilPermissao(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Associacao entre perfil e permissao."""

    __tablename__ = "perfil_permissoes"

    perfil_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("perfis.id", ondelete="CASCADE"), nullable=False
    )
    permissao_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("permissoes.id", ondelete="CASCADE"), nullable=False
    )
    concedida: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))
    condicao: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "perfil_id", "permissao_id", name="uq_perfil_permissoes"),
        sa.Index("ix_perfil_permissoes_perfil", "tenant_id", "perfil_id"),
        {
            "comment": (
                "Associacao entre perfil e permissao. A linha com concedida = false nega "
                "explicitamente uma permissao herdada de um perfil de fabrica."
            )
        },
    )


class UsuarioPerfil(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Atribuicao de perfil a usuario COM ESCOPO."""

    __tablename__ = "usuario_perfis"

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    perfil_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("perfis.id", ondelete="RESTRICT"), nullable=False
    )
    escopo_tipo: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'tenant'"))
    empresa_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="CASCADE")
    )
    unidade_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("unidades.id", ondelete="CASCADE")
    )
    departamento_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("departamentos.id", ondelete="CASCADE")
    )
    # FK criada depois de `equipes` (use_alter), como em schema.sql.
    equipe_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey(
            "equipes.id", ondelete="CASCADE", name="fk_usuario_perfis_equipe", use_alter=True
        )
    )
    incluir_subordinados: Mapped[bool] = mapped_column(
        nullable=False, server_default=sa.text("TRUE")
    )
    vigencia_inicio: Mapped[_datetime.date] = mapped_column(
        nullable=False, server_default=sa.text("CURRENT_DATE")
    )
    vigencia_fim: Mapped[_datetime.date | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "escopo_tipo IN ('tenant','empresa','unidade','departamento','equipe','proprio')",
            name="usuario_perfis_escopo_tipo_check",
        ),
        sa.CheckConstraint(
            "vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio",
            name="ck_usuario_perfis_vigencia",
        ),
        sa.CheckConstraint(
            "(escopo_tipo = 'empresa'      AND empresa_id      IS NOT NULL) OR "
            "(escopo_tipo = 'unidade'      AND unidade_id      IS NOT NULL) OR "
            "(escopo_tipo = 'departamento' AND departamento_id IS NOT NULL) OR "
            "(escopo_tipo = 'equipe'       AND equipe_id       IS NOT NULL) OR "
            "(escopo_tipo IN ('tenant','proprio'))",
            name="ck_usuario_perfis_escopo",
        ),
        sa.Index(
            "uq_usuario_perfis",
            "tenant_id",
            "usuario_id",
            "perfil_id",
            "escopo_tipo",
            sa.text("COALESCE(empresa_id,      '00000000-0000-0000-0000-000000000000'::uuid)"),
            sa.text("COALESCE(unidade_id,      '00000000-0000-0000-0000-000000000000'::uuid)"),
            sa.text("COALESCE(departamento_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            sa.text("COALESCE(equipe_id,       '00000000-0000-0000-0000-000000000000'::uuid)"),
            "vigencia_inicio",
            unique=True,
        ),
        sa.Index("ix_usuario_perfis_usuario", "tenant_id", "usuario_id"),
        sa.Index(
            "ix_usuario_perfis_vigentes",
            "tenant_id",
            "usuario_id",
            "vigencia_inicio",
            "vigencia_fim",
        ),
        {
            "comment": (
                "Atribuicao de perfil a usuario COM ESCOPO. O mesmo usuario pode ser "
                "gestor de uma unidade e colaborador comum no resto da empresa."
            )
        },
    )


class Delegacao(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Delegacao temporaria de atribuicoes, tipicamente ferias do gestor."""

    __tablename__ = "delegacoes"

    delegante_usuario_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    delegado_usuario_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    perfil_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("perfis.id", ondelete="RESTRICT")
    )
    motivo: Mapped[str] = mapped_column(nullable=False)
    escopo: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    inicio_em: Mapped[_datetime.datetime] = mapped_column(nullable=False)
    fim_em: Mapped[_datetime.datetime] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'agendada'"))
    revogada_em: Mapped[_datetime.datetime | None] = mapped_column()
    revogada_por: Mapped[uuid.UUID | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('agendada','ativa','encerrada','cancelada')",
            name="delegacoes_status_check",
        ),
        sa.CheckConstraint("fim_em > inicio_em", name="ck_delegacoes_periodo"),
        sa.CheckConstraint(
            "delegante_usuario_id <> delegado_usuario_id", name="ck_delegacoes_pessoas"
        ),
        ExcludeConstraint(
            ("tenant_id", "="),
            ("delegante_usuario_id", "="),
            ("delegado_usuario_id", "="),
            (sa.text("tstzrange(inicio_em, fim_em)"), "&&"),
            name="ex_delegacoes_sobreposicao",
            using="gist",
            where=sa.text("status IN ('agendada','ativa')"),
        ),
        sa.Index("ix_delegacoes_delegado", "tenant_id", "delegado_usuario_id", "status"),
        sa.Index(
            "ix_delegacoes_periodo",
            "tenant_id",
            "inicio_em",
            "fim_em",
            postgresql_where=sa.text("status IN ('agendada','ativa')"),
        ),
        {
            "comment": (
                "Delegacao temporaria de atribuicoes, tipicamente ferias do gestor. Toda "
                "acao exercida por delegacao e marcada como tal na auditoria."
            )
        },
    )
