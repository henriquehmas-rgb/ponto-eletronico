"""Grupo 13 - Integracao e API publica.

`api_clients`, `api_keys`, `oauth_tokens`, `webhooks`, `webhook_entregas`,
`integracoes_folha` e `importacoes`.

Webhook so aceita HTTPS, garantido por CHECK, e o corpo e assinado em HMAC com
segredo proprio, cifrado com chave externa ao banco.
"""

from __future__ import annotations

import datetime as _datetime
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, BYTEA, CIDR, INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .mixins import (
    AuditoriaMixin,
    ChavePrimariaUUIDMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)
from .tipos import DOM_EMAIL, DOM_SHA256

__all__ = [
    "ApiClient",
    "ApiKey",
    "Importacao",
    "IntegracaoFolha",
    "OauthToken",
    "Webhook",
    "WebhookEntrega",
]


class ApiClient(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Aplicacao integradora autorizada a consumir a API publica."""

    __tablename__ = "api_clients"

    nome: Mapped[str] = mapped_column(nullable=False)
    descricao: Mapped[str | None] = mapped_column()
    client_id: Mapped[str] = mapped_column(nullable=False)
    client_secret_hash: Mapped[str | None] = mapped_column()
    tipo: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'confidencial'"))
    ambiente: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'sandbox'"))
    escopos: Mapped[list[str]] = mapped_column(
        ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")
    )
    redirect_uris: Mapped[list[str] | None] = mapped_column(ARRAY(sa.Text()))
    ips_permitidos: Mapped[list[str] | None] = mapped_column(ARRAY(CIDR()))
    rate_limit_por_minuto: Mapped[int] = mapped_column(
        nullable=False, server_default=sa.text("600")
    )
    contato_email: Mapped[str | None] = mapped_column(DOM_EMAIL)
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'ativo'"))

    __table_args__ = (
        sa.CheckConstraint(
            "tipo IN ('confidencial','publico','maquina')", name="api_clients_tipo_check"
        ),
        sa.CheckConstraint("ambiente IN ('sandbox','producao')", name="api_clients_ambiente_check"),
        sa.CheckConstraint(
            "rate_limit_por_minuto > 0", name="api_clients_rate_limit_por_minuto_check"
        ),
        sa.CheckConstraint(
            "status IN ('ativo','suspenso','revogado')", name="api_clients_status_check"
        ),
        sa.UniqueConstraint("client_id", name="uq_api_clients_client_id"),
        sa.Index(
            "uq_api_clients_nome",
            "tenant_id",
            "nome",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index("ix_api_clients_tenant", "tenant_id", "status"),
        {
            "comment": (
                "Aplicacao integradora autorizada a consumir a API publica. Cada cliente "
                "vive em um ambiente (sandbox ou producao)."
            )
        },
    )


class ApiKey(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Chave de API para integracoes simples. Guardada por hash."""

    __tablename__ = "api_keys"

    api_client_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("api_clients.id", ondelete="CASCADE"), nullable=False
    )
    prefixo: Mapped[str] = mapped_column(nullable=False)
    hash: Mapped[str] = mapped_column(DOM_SHA256, nullable=False)
    rotulo: Mapped[str | None] = mapped_column()
    ambiente: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'sandbox'"))
    escopos: Mapped[list[str]] = mapped_column(
        ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")
    )
    expira_em: Mapped[_datetime.datetime | None] = mapped_column()
    ultimo_uso_em: Mapped[_datetime.datetime | None] = mapped_column()
    ultimo_ip: Mapped[str | None] = mapped_column(INET)
    revogada_em: Mapped[_datetime.datetime | None] = mapped_column()
    motivo_revogacao: Mapped[str | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint("ambiente IN ('sandbox','producao')", name="api_keys_ambiente_check"),
        sa.UniqueConstraint("tenant_id", "prefixo", name="uq_api_keys_prefixo"),
        sa.Index(
            "ix_api_keys_client",
            "tenant_id",
            "api_client_id",
            postgresql_where=sa.text("revogada_em IS NULL"),
        ),
        {
            "comment": (
                "Chave de API para integracoes simples que nao justificam o fluxo OAuth "
                "completo. Guardada por hash; o prefixo serve para identificar a chave."
            )
        },
    )


class OauthToken(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Tokens emitidos no fluxo client credentials."""

    __tablename__ = "oauth_tokens"

    api_client_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("api_clients.id", ondelete="CASCADE"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(nullable=False)
    token_hash: Mapped[str] = mapped_column(DOM_SHA256, nullable=False)
    escopos: Mapped[list[str]] = mapped_column(
        ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")
    )
    emitido_em: Mapped[_datetime.datetime] = mapped_column(
        nullable=False, server_default=sa.text("now()")
    )
    expira_em: Mapped[_datetime.datetime] = mapped_column(nullable=False)
    revogado_em: Mapped[_datetime.datetime | None] = mapped_column()
    ip: Mapped[str | None] = mapped_column(INET)

    __table_args__ = (
        sa.CheckConstraint("tipo IN ('access','refresh')", name="oauth_tokens_tipo_check"),
        sa.UniqueConstraint("tenant_id", "token_hash", name="uq_oauth_tokens_hash"),
        sa.Index("ix_oauth_tokens_client", "tenant_id", "api_client_id", "expira_em"),
        {
            "comment": (
                "Tokens emitidos no fluxo client credentials. Guardados por hash e "
                "revogaveis individualmente ou por cliente."
            )
        },
    )


class Webhook(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Assinatura de eventos por HTTP. Somente HTTPS."""

    __tablename__ = "webhooks"

    api_client_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("api_clients.id", ondelete="CASCADE")
    )
    nome: Mapped[str] = mapped_column(nullable=False)
    url: Mapped[str] = mapped_column(nullable=False)
    eventos: Mapped[list[str]] = mapped_column(ARRAY(sa.Text()), nullable=False)
    segredo_hmac_cifrado: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    chave_id: Mapped[str | None] = mapped_column()
    cabecalhos_extras: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    max_tentativas: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("8"))
    timeout_segundos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("10"))
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'ativo'"))
    falhas_consecutivas: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    ultima_entrega_em: Mapped[_datetime.datetime | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(r"url ~ '^https://'", name="webhooks_url_check"),
        sa.CheckConstraint("max_tentativas > 0", name="webhooks_max_tentativas_check"),
        sa.CheckConstraint("timeout_segundos > 0", name="webhooks_timeout_segundos_check"),
        sa.CheckConstraint(
            "status IN ('ativo','suspenso','desabilitado_por_falha')",
            name="webhooks_status_check",
        ),
        sa.CheckConstraint("falhas_consecutivas >= 0", name="webhooks_falhas_consecutivas_check"),
        sa.Index(
            "uq_webhooks_nome",
            "tenant_id",
            "nome",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index("ix_webhooks_eventos", "eventos", postgresql_using="gin"),
        {
            "comment": (
                "Assinatura de eventos por HTTP. Somente HTTPS, garantido por CHECK. O "
                "corpo e assinado em HMAC com segredo proprio de cada webhook."
            )
        },
    )


class WebhookEntrega(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Tentativa de entrega de um evento, com retentativa exponencial e dead letter."""

    __tablename__ = "webhook_entregas"

    webhook_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("webhooks.id", ondelete="CASCADE"), nullable=False
    )
    evento: Mapped[str] = mapped_column(nullable=False)
    evento_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    assinatura: Mapped[str | None] = mapped_column()
    tentativa: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("1"))
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'pendente'"))
    http_status: Mapped[int | None] = mapped_column()
    resposta: Mapped[str | None] = mapped_column()
    duracao_ms: Mapped[int | None] = mapped_column()
    erro: Mapped[str | None] = mapped_column()
    proxima_tentativa_em: Mapped[_datetime.datetime | None] = mapped_column()
    enviado_em: Mapped[_datetime.datetime | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint("tentativa >= 1", name="webhook_entregas_tentativa_check"),
        sa.CheckConstraint(
            "status IN ('pendente','enviando','sucesso','falha','dlq','cancelada')",
            name="webhook_entregas_status_check",
        ),
        sa.CheckConstraint(
            "duracao_ms IS NULL OR duracao_ms >= 0", name="webhook_entregas_duracao_ms_check"
        ),
        sa.Index(
            "ix_webhook_entregas_webhook", "tenant_id", "webhook_id", sa.text("criado_em DESC")
        ),
        sa.Index(
            "ix_webhook_entregas_pendentes",
            "tenant_id",
            "proxima_tentativa_em",
            postgresql_where=sa.text("status IN ('pendente','falha')"),
        ),
        sa.Index(
            "ix_webhook_entregas_dlq",
            "tenant_id",
            sa.text("criado_em DESC"),
            postgresql_where=sa.text("status = 'dlq'"),
        ),
        {
            "comment": (
                "Tentativa de entrega de um evento. Retentativa exponencial ate "
                "max_tentativas; esgotado, vai para dlq e pode ser reenviada manualmente."
            )
        },
    )


class IntegracaoFolha(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Configuracao de exportacao para um sistema de folha."""

    __tablename__ = "integracoes_folha"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="RESTRICT"), nullable=False
    )
    parceiro: Mapped[str] = mapped_column(nullable=False)
    nome: Mapped[str] = mapped_column(nullable=False)
    configuracao: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    mapeamento_rubricas: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    formato: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'csv'"))
    ativo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))
    ultima_exportacao_em: Mapped[_datetime.datetime | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "parceiro IN ('dominio','alterdata','totvs_rm','totvs_protheus','totvs_datasul',"
            "'senior','sankhya','questor','fortes','contmatic','generico_csv')",
            name="integracoes_folha_parceiro_check",
        ),
        sa.CheckConstraint(
            "formato IN ('csv','txt','xml','json','api')",
            name="integracoes_folha_formato_check",
        ),
        sa.Index(
            "uq_integracoes_folha_nome",
            "tenant_id",
            "empresa_id",
            "nome",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        {
            "comment": (
                "Configuracao de exportacao para um sistema de folha. O mapeamento de "
                "rubricas traduz nossos codigos de apuracao para os do parceiro."
            )
        },
    )


class Importacao(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Execucao de um importador, com resultado linha a linha."""

    __tablename__ = "importacoes"

    empresa_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="RESTRICT")
    )
    tipo: Mapped[str] = mapped_column(nullable=False)
    origem: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'csv'"))
    nome_arquivo: Mapped[str | None] = mapped_column()
    conteudo_ref: Mapped[str | None] = mapped_column()
    hash_sha256: Mapped[str | None] = mapped_column(DOM_SHA256)
    parametros: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'recebido'"))
    total_linhas: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    linhas_processadas: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    linhas_sucesso: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    linhas_erro: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    relatorio_ref: Mapped[str | None] = mapped_column()
    erros: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    iniciado_em: Mapped[_datetime.datetime | None] = mapped_column()
    concluido_em: Mapped[_datetime.datetime | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "tipo IN ('colaboradores','estrutura','escalas','feriados','marcacoes',"
            "'afd_terceiro','banco_horas','biometria','afastamentos')",
            name="importacoes_tipo_check",
        ),
        sa.CheckConstraint(
            "origem IN ('csv','xlsx','afd','api','manual')", name="importacoes_origem_check"
        ),
        sa.CheckConstraint(
            "status IN ('recebido','validando','processando','concluido',"
            "'concluido_com_erros','falhou','cancelado')",
            name="importacoes_status_check",
        ),
        sa.Index("ix_importacoes_tenant", "tenant_id", "tipo", sa.text("criado_em DESC")),
        sa.Index(
            "ix_importacoes_status",
            "tenant_id",
            "status",
            postgresql_where=sa.text("status IN ('recebido','validando','processando')"),
        ),
        {
            "comment": (
                "Execucao de um importador. Guarda o arquivo de origem, o resultado linha "
                "a linha e o relatorio de erros."
            )
        },
    )
