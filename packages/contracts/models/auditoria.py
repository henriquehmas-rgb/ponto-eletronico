"""Grupo 14 - Auditoria e LGPD.

`auditoria`, `acessos_dados_sensiveis`, `consentimentos`, `politicas_retencao`
e `solicitacoes_titular`.

A trilha de auditoria e ENCADEADA: cada linha carrega o hash da anterior,
formando uma cadeia por tenant. Remover uma linha silenciosamente quebra a
cadeia e e detectavel. Gatilhos barram UPDATE, DELETE e TRUNCATE.

O registro de ponto se apoia em obrigacao legal, mas a BIOMETRIA exige
consentimento especifico: sem linha concedida vigente em `consentimentos`, o
template nao pode ser usado.
"""

from __future__ import annotations

import datetime as _datetime
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .mixins import (
    AuditoriaMixin,
    ChavePrimariaUUIDMixin,
    CriacaoMixin,
    TenantMixin,
    TimestampMixin,
)
from .tipos import DOM_CPF, DOM_EMAIL, DOM_SHA256

__all__ = [
    "AcessoDadoSensivel",
    "Auditoria",
    "Consentimento",
    "PoliticaRetencao",
    "SolicitacaoTitular",
]


class Auditoria(ChavePrimariaUUIDMixin, TenantMixin, CriacaoMixin, Base):
    """Trilha de auditoria ENCADEADA. APPEND-ONLY."""

    __tablename__ = "auditoria"

    sequencia: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    evento: Mapped[str] = mapped_column(nullable=False)
    entidade: Mapped[str] = mapped_column(nullable=False)
    entidade_id: Mapped[uuid.UUID | None] = mapped_column()
    acao: Mapped[str] = mapped_column(nullable=False)
    usuario_id: Mapped[uuid.UUID | None] = mapped_column()
    usuario_email: Mapped[str | None] = mapped_column()
    perfil: Mapped[str | None] = mapped_column()
    delegacao_id: Mapped[uuid.UUID | None] = mapped_column()
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column()
    origem: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'api'"))
    requisicao_id: Mapped[str | None] = mapped_column()
    valor_anterior: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    valor_novo: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    diferenca: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    metadados: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    resultado: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'sucesso'"))
    mensagem: Mapped[str | None] = mapped_column()
    ocorrido_em: Mapped[_datetime.datetime] = mapped_column(
        nullable=False, server_default=sa.text("now()")
    )
    hash_anterior: Mapped[str | None] = mapped_column(DOM_SHA256)
    hash_registro: Mapped[str] = mapped_column(DOM_SHA256, nullable=False)

    __table_args__ = (
        sa.CheckConstraint("sequencia >= 1", name="auditoria_sequencia_check"),
        sa.CheckConstraint(
            "acao IN ('criar','ler','atualizar','excluir','aprovar','reprovar','exportar',"
            "'login','logout','falha_login','fechar','reabrir','assinar','revogar',"
            "'configurar','recalcular')",
            name="auditoria_acao_check",
        ),
        sa.CheckConstraint(
            "origem IN ('web','mobile','api','terminal','worker','cli','sistema')",
            name="auditoria_origem_check",
        ),
        sa.CheckConstraint(
            "resultado IN ('sucesso','falha','negado')", name="auditoria_resultado_check"
        ),
        sa.UniqueConstraint("tenant_id", "sequencia", name="uq_auditoria_sequencia"),
        sa.UniqueConstraint("tenant_id", "hash_registro", name="uq_auditoria_hash"),
        sa.Index(
            "ix_auditoria_entidade",
            "tenant_id",
            "entidade",
            "entidade_id",
            sa.text("ocorrido_em DESC"),
        ),
        sa.Index("ix_auditoria_usuario", "tenant_id", "usuario_id", sa.text("ocorrido_em DESC")),
        sa.Index("ix_auditoria_ocorrido", "tenant_id", sa.text("ocorrido_em DESC")),
        sa.Index("ix_auditoria_acao", "tenant_id", "acao", sa.text("ocorrido_em DESC")),
        {
            "comment": (
                "Trilha de auditoria ENCADEADA. Cada linha carrega o hash da anterior, "
                "formando uma cadeia por tenant: remover uma linha silenciosamente quebra "
                "a cadeia e e detectavel."
            )
        },
    )


class AcessoDadoSensivel(ChavePrimariaUUIDMixin, TenantMixin, CriacaoMixin, Base):
    """Registro de TODA leitura de dado pessoal sensivel. APPEND-ONLY."""

    __tablename__ = "acessos_dados_sensiveis"

    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    colaborador_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("colaboradores.id", ondelete="SET NULL")
    )
    categoria: Mapped[str] = mapped_column(nullable=False)
    entidade: Mapped[str | None] = mapped_column()
    entidade_id: Mapped[uuid.UUID | None] = mapped_column()
    finalidade: Mapped[str] = mapped_column(nullable=False)
    base_legal: Mapped[str] = mapped_column(nullable=False)
    acao: Mapped[str] = mapped_column(nullable=False)
    quantidade_registros: Mapped[int | None] = mapped_column()
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column()
    origem: Mapped[str | None] = mapped_column()
    ocorrido_em: Mapped[_datetime.datetime] = mapped_column(
        nullable=False, server_default=sa.text("now()")
    )

    __table_args__ = (
        sa.CheckConstraint(
            "categoria IN ('biometria','documento','saude','remuneracao','geolocalizacao',"
            "'foto','cpf','dados_pessoais')",
            name="acessos_dados_sensiveis_categoria_check",
        ),
        sa.CheckConstraint(
            "base_legal IN ('obrigacao_legal','consentimento','execucao_contrato',"
            "'legitimo_interesse','exercicio_direitos','protecao_vida')",
            name="acessos_dados_sensiveis_base_legal_check",
        ),
        sa.CheckConstraint(
            "acao IN ('leitura','exportacao','impressao','compartilhamento','eliminacao')",
            name="acessos_dados_sensiveis_acao_check",
        ),
        sa.CheckConstraint(
            "origem IN ('web','mobile','api','terminal','worker','cli','sistema')",
            name="acessos_dados_sensiveis_origem_check",
        ),
        sa.Index(
            "ix_acessos_sensiveis_usuario",
            "tenant_id",
            "usuario_id",
            sa.text("ocorrido_em DESC"),
        ),
        sa.Index(
            "ix_acessos_sensiveis_colaborador",
            "tenant_id",
            "colaborador_id",
            sa.text("ocorrido_em DESC"),
        ),
        sa.Index(
            "ix_acessos_sensiveis_categoria",
            "tenant_id",
            "categoria",
            sa.text("ocorrido_em DESC"),
        ),
        {
            "comment": (
                "Registro de TODA leitura de dado pessoal sensivel. Append-only. E a "
                "evidencia que a LGPD exige, incluindo o acesso de suporte da SEEG."
            )
        },
    )


class Consentimento(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Consentimento LGPD versionado."""

    __tablename__ = "consentimentos"

    colaborador_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("colaboradores.id", ondelete="RESTRICT"), nullable=False
    )
    finalidade: Mapped[str] = mapped_column(nullable=False)
    versao_termo: Mapped[str] = mapped_column(nullable=False)
    texto_termo_ref: Mapped[str] = mapped_column(nullable=False)
    hash_termo: Mapped[str] = mapped_column(DOM_SHA256, nullable=False)
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'concedido'"))
    concedido_em: Mapped[_datetime.datetime | None] = mapped_column()
    revogado_em: Mapped[_datetime.datetime | None] = mapped_column()
    expira_em: Mapped[_datetime.datetime | None] = mapped_column()
    canal: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'app'"))
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column()
    evidencia_ref: Mapped[str | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "finalidade IN ('biometria_facial','biometria_digital','geolocalizacao',"
            "'foto_registro','uso_imagem','comunicacao')",
            name="consentimentos_finalidade_check",
        ),
        sa.CheckConstraint(
            "status IN ('pendente','concedido','revogado','expirado')",
            name="consentimentos_status_check",
        ),
        sa.CheckConstraint(
            "canal IN ('app','web','terminal','papel','importacao')",
            name="consentimentos_canal_check",
        ),
        sa.Index(
            "uq_consentimentos_vigente",
            "tenant_id",
            "colaborador_id",
            "finalidade",
            unique=True,
            postgresql_where=sa.text("status = 'concedido'"),
        ),
        sa.Index("ix_consentimentos_colaborador", "tenant_id", "colaborador_id"),
        {
            "comment": (
                "Consentimento LGPD versionado. A BIOMETRIA exige consentimento "
                "especifico: sem linha concedida vigente aqui, o template nao pode ser "
                "usado."
            )
        },
    )


class PoliticaRetencao(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Prazo de guarda por tipo de dado e o que fazer no vencimento."""

    __tablename__ = "politicas_retencao"

    entidade: Mapped[str] = mapped_column(nullable=False)
    prazo_dias: Mapped[int] = mapped_column(nullable=False)
    base_legal: Mapped[str] = mapped_column(nullable=False)
    acao: Mapped[str] = mapped_column(nullable=False)
    ativo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))
    ultima_execucao_em: Mapped[_datetime.datetime | None] = mapped_column()
    proxima_execucao_em: Mapped[_datetime.datetime | None] = mapped_column()
    registros_ultima_execucao: Mapped[int | None] = mapped_column(sa.BigInteger)

    __table_args__ = (
        sa.CheckConstraint(
            "entidade IN ('marcacao','foto_registro','biometria','documento','auditoria',"
            "'notificacao','espelho','afd','aej','log_acesso','fila_offline',"
            "'relatorio_execucao','sessao')",
            name="politicas_retencao_entidade_check",
        ),
        sa.CheckConstraint("prazo_dias > 0", name="politicas_retencao_prazo_dias_check"),
        sa.CheckConstraint(
            "acao IN ('anonimizar','eliminar','arquivar')",
            name="politicas_retencao_acao_check",
        ),
        sa.UniqueConstraint("tenant_id", "entidade", name="uq_politicas_retencao"),
        {
            "comment": (
                "Prazo de guarda por tipo de dado e o que fazer no vencimento. Marcacao "
                "retem 5 anos por obrigacao legal; foto de captura retem prazo curto."
            )
        },
    )


class SolicitacaoTitular(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Pedido de titular de dados previsto na LGPD."""

    __tablename__ = "solicitacoes_titular"

    colaborador_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("colaboradores.id", ondelete="SET NULL")
    )
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    protocolo: Mapped[str] = mapped_column(nullable=False)
    requerente_nome: Mapped[str] = mapped_column(nullable=False)
    requerente_cpf: Mapped[str | None] = mapped_column(DOM_CPF)
    requerente_email: Mapped[str | None] = mapped_column(DOM_EMAIL)
    tipo: Mapped[str] = mapped_column(nullable=False)
    descricao: Mapped[str | None] = mapped_column()
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'recebida'"))
    prazo_em: Mapped[_datetime.date | None] = mapped_column()
    resposta: Mapped[str | None] = mapped_column()
    resposta_ref: Mapped[str | None] = mapped_column()
    respondido_em: Mapped[_datetime.datetime | None] = mapped_column()
    respondido_por: Mapped[uuid.UUID | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "tipo IN ('acesso','correcao','portabilidade','eliminacao','anonimizacao',"
            "'revogacao_consentimento','informacao_compartilhamento','oposicao')",
            name="solicitacoes_titular_tipo_check",
        ),
        sa.CheckConstraint(
            "status IN ('recebida','em_analise','atendida','parcialmente_atendida',"
            "'recusada','cancelada')",
            name="solicitacoes_titular_status_check",
        ),
        sa.UniqueConstraint("tenant_id", "protocolo", name="uq_solicitacoes_titular_protocolo"),
        sa.Index("ix_solicitacoes_titular_status", "tenant_id", "status", "prazo_em"),
        {
            "comment": (
                "Pedido de titular de dados previsto na LGPD. Guarda protocolo, prazo de "
                "resposta e o arquivo entregue."
            )
        },
    )
