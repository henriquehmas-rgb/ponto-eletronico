"""Grupo 10 - Workflow, aprovacoes e notificacoes.

`tipos_solicitacao`, `solicitacoes`, `aprovacoes`, `anexos`, `notificacoes` e
`notificacao_preferencias`.

A solicitacao nunca altera marcacao diretamente: quando aprovada, materializa
um tratamento (modulo `apuracao`) ou um afastamento (modulo `jornada`).

`anexos` usa referencia polimorfica (`entidade` + `entidade_id`) SEM chave
estrangeira, com o conjunto de alvos fechado por CHECK. Divergencia deliberada,
registrada no glossario: nenhuma fase deve "consertar" isso por engano.
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
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)
from .tipos import DOM_SHA256

__all__ = [
    "Anexo",
    "Aprovacao",
    "Notificacao",
    "NotificacaoPreferencia",
    "Solicitacao",
    "TipoSolicitacao",
]


class TipoSolicitacao(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Catalogo configuravel de pedidos, com a cadeia de aprovacao de cada um."""

    __tablename__ = "tipos_solicitacao"

    codigo: Mapped[str] = mapped_column(nullable=False)
    nome: Mapped[str] = mapped_column(nullable=False)
    descricao: Mapped[str | None] = mapped_column()
    categoria: Mapped[str] = mapped_column(nullable=False)
    etapas: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )
    prazo_resposta_horas: Mapped[int | None] = mapped_column()
    escalonar_apos_horas: Mapped[int | None] = mapped_column()
    exige_anexo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))
    exige_justificativa: Mapped[bool] = mapped_column(
        nullable=False, server_default=sa.text("TRUE")
    )
    permite_retroativo_dias: Mapped[int | None] = mapped_column()
    tipo_tratamento_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("tipos_tratamento.id", ondelete="RESTRICT")
    )
    ativo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))

    __table_args__ = (
        sa.CheckConstraint(
            "categoria IN ('ajuste_ponto','abono','justificativa','ferias','folga',"
            "'compensacao','afastamento','troca_escala','hora_extra',"
            "'desbloqueio_dispositivo','outro')",
            name="tipos_solicitacao_categoria_check",
        ),
        sa.CheckConstraint(
            "prazo_resposta_horas IS NULL OR prazo_resposta_horas > 0",
            name="tipos_solicitacao_prazo_resposta_horas_check",
        ),
        sa.CheckConstraint(
            "escalonar_apos_horas IS NULL OR escalonar_apos_horas > 0",
            name="tipos_solicitacao_escalonar_apos_horas_check",
        ),
        sa.CheckConstraint(
            "permite_retroativo_dias IS NULL OR permite_retroativo_dias >= 0",
            name="tipos_solicitacao_permite_retroativo_dias_check",
        ),
        sa.Index(
            "uq_tipos_solicitacao_codigo",
            "tenant_id",
            "codigo",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        {
            "comment": (
                "Catalogo configuravel de pedidos que o colaborador ou o gestor podem "
                "abrir, com a cadeia de aprovacao de cada um."
            )
        },
    )


class Solicitacao(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Pedido aberto no workflow."""

    __tablename__ = "solicitacoes"

    tipo_solicitacao_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("tipos_solicitacao.id", ondelete="RESTRICT"), nullable=False
    )
    colaborador_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("colaboradores.id", ondelete="RESTRICT"), nullable=False
    )
    vinculo_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("vinculos.id", ondelete="RESTRICT")
    )
    solicitante_usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    protocolo: Mapped[str] = mapped_column(nullable=False)
    data_referencia: Mapped[_datetime.date | None] = mapped_column()
    data_inicio: Mapped[_datetime.date | None] = mapped_column()
    data_fim: Mapped[_datetime.date | None] = mapped_column()
    descricao: Mapped[str] = mapped_column(nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'pendente'"))
    etapa_atual: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("1"))
    prazo_em: Mapped[_datetime.datetime | None] = mapped_column()
    concluida_em: Mapped[_datetime.datetime | None] = mapped_column()
    resultado: Mapped[str | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('rascunho','pendente','em_aprovacao','aprovada','reprovada',"
            "'cancelada','expirada')",
            name="solicitacoes_status_check",
        ),
        sa.CheckConstraint("etapa_atual >= 1", name="solicitacoes_etapa_atual_check"),
        sa.UniqueConstraint("tenant_id", "protocolo", name="uq_solicitacoes_protocolo"),
        sa.CheckConstraint(
            "data_fim IS NULL OR data_inicio IS NULL OR data_fim >= data_inicio",
            name="ck_solicitacoes_periodo",
        ),
        sa.Index(
            "ix_solicitacoes_colaborador",
            "tenant_id",
            "colaborador_id",
            sa.text("criado_em DESC"),
        ),
        sa.Index(
            "ix_solicitacoes_pendentes",
            "tenant_id",
            "status",
            "prazo_em",
            postgresql_where=sa.text("status IN ('pendente','em_aprovacao')"),
        ),
        sa.Index("ix_solicitacoes_data", "tenant_id", "data_referencia"),
        {
            "comment": (
                "Pedido aberto no workflow. Percorre a cadeia definida no tipo e, quando "
                "aprovado, materializa um tratamento ou um afastamento."
            )
        },
    )


class Aprovacao(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Uma linha por etapa da cadeia de uma solicitacao."""

    __tablename__ = "aprovacoes"

    solicitacao_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("solicitacoes.id", ondelete="CASCADE"), nullable=False
    )
    etapa: Mapped[int] = mapped_column(nullable=False)
    papel: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'gestor'"))
    aprovador_usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    aprovador_delegacao_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("delegacoes.id", ondelete="SET NULL")
    )
    decisao: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'pendente'"))
    comentario: Mapped[str | None] = mapped_column()
    prazo_em: Mapped[_datetime.datetime | None] = mapped_column()
    notificado_em: Mapped[_datetime.datetime | None] = mapped_column()
    escalonado_em: Mapped[_datetime.datetime | None] = mapped_column()
    decidido_em: Mapped[_datetime.datetime | None] = mapped_column()
    ip: Mapped[str | None] = mapped_column(INET)

    __table_args__ = (
        sa.CheckConstraint("etapa >= 1", name="aprovacoes_etapa_check"),
        sa.CheckConstraint(
            "papel IN ('gestor','rh','diretoria','sistema')", name="aprovacoes_papel_check"
        ),
        sa.CheckConstraint(
            "decisao IN ('pendente','aprovada','reprovada','delegada','expirada','cancelada')",
            name="aprovacoes_decisao_check",
        ),
        sa.Index("uq_aprovacoes_etapa", "tenant_id", "solicitacao_id", "etapa", unique=True),
        sa.Index(
            "ix_aprovacoes_pendentes",
            "tenant_id",
            "aprovador_usuario_id",
            "decisao",
            postgresql_where=sa.text("decisao = 'pendente'"),
        ),
        {
            "comment": (
                "Uma linha por etapa da cadeia de uma solicitacao. E a prova de quem "
                "autorizou cada correcao de jornada."
            )
        },
    )


class Anexo(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Arquivos anexados a qualquer entidade do workflow (referencia polimorfica, sem FK)."""

    __tablename__ = "anexos"

    entidade: Mapped[str] = mapped_column(nullable=False)
    entidade_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    nome_arquivo: Mapped[str] = mapped_column(nullable=False)
    conteudo_ref: Mapped[str] = mapped_column(nullable=False)
    mime_type: Mapped[str | None] = mapped_column()
    tamanho_bytes: Mapped[int | None] = mapped_column(sa.BigInteger)
    hash_sha256: Mapped[str | None] = mapped_column(DOM_SHA256)
    descricao: Mapped[str | None] = mapped_column()
    confidencial: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))

    __table_args__ = (
        sa.CheckConstraint(
            "entidade IN ('solicitacao','tratamento','afastamento','colaborador',"
            "'fechamento','ocorrencia','marcacao','importacao')",
            name="anexos_entidade_check",
        ),
        sa.CheckConstraint(
            "tamanho_bytes IS NULL OR tamanho_bytes >= 0", name="anexos_tamanho_bytes_check"
        ),
        sa.Index(
            "ix_anexos_entidade",
            "tenant_id",
            "entidade",
            "entidade_id",
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        {
            "comment": (
                "Arquivos anexados a qualquer entidade do workflow. A referencia e "
                "polimorfica e por isso NAO tem chave estrangeira; a integridade e "
                "garantida na aplicacao."
            )
        },
    )


class Notificacao(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Mensagem enviada ao usuario. Uma linha por canal."""

    __tablename__ = "notificacoes"

    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("usuarios.id", ondelete="CASCADE")
    )
    colaborador_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("colaboradores.id", ondelete="CASCADE")
    )
    canal: Mapped[str] = mapped_column(nullable=False)
    evento: Mapped[str] = mapped_column(nullable=False)
    titulo: Mapped[str] = mapped_column(nullable=False)
    corpo: Mapped[str] = mapped_column(nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    prioridade: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'normal'"))
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'pendente'"))
    agendada_para: Mapped[_datetime.datetime | None] = mapped_column()
    enviada_em: Mapped[_datetime.datetime | None] = mapped_column()
    entregue_em: Mapped[_datetime.datetime | None] = mapped_column()
    lida_em: Mapped[_datetime.datetime | None] = mapped_column()
    tentativas: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    erro: Mapped[str | None] = mapped_column()
    provedor: Mapped[str | None] = mapped_column()
    provedor_mensagem_id: Mapped[str | None] = mapped_column()
    entidade: Mapped[str | None] = mapped_column()
    entidade_id: Mapped[uuid.UUID | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "canal IN ('push','email','whatsapp','in_app','sms')",
            name="notificacoes_canal_check",
        ),
        sa.CheckConstraint(
            "prioridade IN ('baixa','normal','alta','critica')",
            name="notificacoes_prioridade_check",
        ),
        sa.CheckConstraint(
            "status IN ('pendente','enviada','entregue','lida','falhou','descartada')",
            name="notificacoes_status_check",
        ),
        sa.CheckConstraint("tentativas >= 0", name="notificacoes_tentativas_check"),
        sa.CheckConstraint(
            "usuario_id IS NOT NULL OR colaborador_id IS NOT NULL",
            name="ck_notificacoes_destinatario",
        ),
        sa.Index("ix_notificacoes_usuario", "tenant_id", "usuario_id", sa.text("criado_em DESC")),
        sa.Index(
            "ix_notificacoes_pendentes",
            "tenant_id",
            "status",
            "agendada_para",
            postgresql_where=sa.text("status = 'pendente'"),
        ),
        sa.Index(
            "ix_notificacoes_nao_lidas",
            "tenant_id",
            "usuario_id",
            postgresql_where=sa.text("canal = 'in_app' AND lida_em IS NULL"),
        ),
        {
            "comment": (
                "Mensagem enviada ao usuario em qualquer canal. Uma linha por canal: o "
                "mesmo evento notificado por push e e-mail gera duas linhas."
            )
        },
    )


class NotificacaoPreferencia(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base
):
    """Preferencia do usuario por evento e canal."""

    __tablename__ = "notificacao_preferencias"

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    evento: Mapped[str] = mapped_column(nullable=False)
    canal: Mapped[str] = mapped_column(nullable=False)
    habilitado: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))
    janela_inicio: Mapped[_datetime.time | None] = mapped_column()
    janela_fim: Mapped[_datetime.time | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "canal IN ('push','email','whatsapp','in_app','sms')",
            name="notificacao_preferencias_canal_check",
        ),
        sa.UniqueConstraint(
            "tenant_id", "usuario_id", "evento", "canal", name="uq_notificacao_preferencias"
        ),
        {
            "comment": (
                "Preferencia do usuario por evento e canal. Ausencia de linha significa "
                "usar o padrao do tenant."
            )
        },
    )
