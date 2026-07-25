"""Grupo 12 - Arquivos fiscais (AFD, AEJ e assinatura).

`afd_arquivos`, `aej_arquivos` e `arquivo_assinaturas`.

O **AFD** e gerado EXCLUSIVAMENTE pelo REP-P e deriva apenas das marcacoes:
nenhum tratamento entra nele. O **AEJ** e gerado pelo Programa de Tratamento de
Registro de Ponto e e onde a correcao legitimamente aparece. Confundir os dois
e o erro que invalida o sistema numa fiscalizacao.

O leiaute campo a campo deve ser conferido contra os anexos da Portaria MTP
671/2021 na Fase 12 (tarefa bloqueante). Aqui so existe o contrato de dados.
"""

from __future__ import annotations

import datetime as _datetime
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .mixins import (
    AuditoriaMixin,
    ChavePrimariaUUIDMixin,
    CriacaoMixin,
    TenantMixin,
    TimestampMixin,
)
from .tipos import DOM_CNPJ, DOM_SHA256

__all__ = ["AejArquivo", "AfdArquivo", "ArquivoAssinatura"]


class AfdArquivo(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Arquivo Fonte de Dados gerado EXCLUSIVAMENTE pelo REP-P."""

    __tablename__ = "afd_arquivos"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="RESTRICT"), nullable=False
    )
    rep_p_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("rep_ps.id", ondelete="RESTRICT"), nullable=False
    )
    periodo_inicio: Mapped[_datetime.date] = mapped_column(nullable=False)
    periodo_fim: Mapped[_datetime.date] = mapped_column(nullable=False)
    nsr_inicial: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    nsr_final: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    total_registros: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, server_default=sa.text("0")
    )
    nome_arquivo: Mapped[str] = mapped_column(nullable=False)
    conteudo_ref: Mapped[str | None] = mapped_column()
    tamanho_bytes: Mapped[int | None] = mapped_column(sa.BigInteger)
    encoding: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'ISO-8859-1'"))
    hash_sha256: Mapped[str | None] = mapped_column(DOM_SHA256)
    versao_leiaute: Mapped[str] = mapped_column(
        nullable=False, server_default=sa.text("'671/2021'")
    )
    fracionado: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))
    fracao_numero: Mapped[int | None] = mapped_column()
    fracao_total: Mapped[int | None] = mapped_column()
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'gerando'"))
    solicitado_por: Mapped[uuid.UUID | None] = mapped_column()
    gerado_em: Mapped[_datetime.datetime | None] = mapped_column()
    erro: Mapped[str | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint("nsr_inicial >= 1", name="afd_arquivos_nsr_inicial_check"),
        sa.CheckConstraint("nsr_final >= 1", name="afd_arquivos_nsr_final_check"),
        sa.CheckConstraint("total_registros >= 0", name="afd_arquivos_total_registros_check"),
        sa.CheckConstraint(
            "tamanho_bytes IS NULL OR tamanho_bytes >= 0",
            name="afd_arquivos_tamanho_bytes_check",
        ),
        sa.CheckConstraint(
            "fracao_numero IS NULL OR fracao_numero >= 1",
            name="afd_arquivos_fracao_numero_check",
        ),
        sa.CheckConstraint(
            "fracao_total IS NULL OR fracao_total >= 1", name="afd_arquivos_fracao_total_check"
        ),
        sa.CheckConstraint(
            "status IN ('gerando','gerado','assinado','falhou','cancelado')",
            name="afd_arquivos_status_check",
        ),
        sa.CheckConstraint("periodo_fim >= periodo_inicio", name="ck_afd_arquivos_periodo"),
        sa.CheckConstraint("nsr_final >= nsr_inicial", name="ck_afd_arquivos_nsr"),
        sa.CheckConstraint(
            "(fracionado = FALSE AND fracao_numero IS NULL AND fracao_total IS NULL) OR "
            "(fracionado = TRUE  AND fracao_numero IS NOT NULL AND fracao_total IS NOT NULL "
            "AND fracao_numero <= fracao_total)",
            name="ck_afd_arquivos_fracao",
        ),
        sa.Index(
            "ix_afd_arquivos_empresa",
            "tenant_id",
            "empresa_id",
            sa.text("periodo_inicio DESC"),
        ),
        sa.Index("ix_afd_arquivos_rep", "tenant_id", "rep_p_id", "nsr_inicial"),
        {
            "comment": (
                "Arquivo Fonte de Dados gerado EXCLUSIVAMENTE pelo REP-P. Texto ASCII "
                "ISO 8859-1, separador barra vertical, CR+LF, CRC-16 por registro e "
                "SHA-256 do arquivo. Nenhum tratamento entra aqui."
            )
        },
    )


class AejArquivo(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Arquivo Eletronico de Jornada, gerado pelo Programa de Tratamento."""

    __tablename__ = "aej_arquivos"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="RESTRICT"), nullable=False
    )
    periodo_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("periodos.id", ondelete="RESTRICT")
    )
    periodo_inicio: Mapped[_datetime.date] = mapped_column(nullable=False)
    periodo_fim: Mapped[_datetime.date] = mapped_column(nullable=False)
    nome_arquivo: Mapped[str] = mapped_column(nullable=False)
    conteudo_ref: Mapped[str | None] = mapped_column()
    tamanho_bytes: Mapped[int | None] = mapped_column(sa.BigInteger)
    encoding: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'ISO-8859-1'"))
    hash_sha256: Mapped[str | None] = mapped_column(DOM_SHA256)
    versao_leiaute: Mapped[str] = mapped_column(
        nullable=False, server_default=sa.text("'671/2021'")
    )
    total_vinculos: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    total_marcacoes: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, server_default=sa.text("0")
    )
    total_ausencias: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    total_lancamentos_banco: Mapped[int] = mapped_column(
        nullable=False, server_default=sa.text("0")
    )
    ptrp_identificacao: Mapped[str] = mapped_column(nullable=False)
    ptrp_cnpj: Mapped[str | None] = mapped_column(DOM_CNPJ)
    ptrp_versao: Mapped[str | None] = mapped_column()
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'gerando'"))
    solicitado_por: Mapped[uuid.UUID | None] = mapped_column()
    gerado_em: Mapped[_datetime.datetime | None] = mapped_column()
    erro: Mapped[str | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "tamanho_bytes IS NULL OR tamanho_bytes >= 0",
            name="aej_arquivos_tamanho_bytes_check",
        ),
        sa.CheckConstraint(
            "status IN ('gerando','gerado','assinado','falhou','cancelado')",
            name="aej_arquivos_status_check",
        ),
        sa.CheckConstraint("periodo_fim >= periodo_inicio", name="ck_aej_arquivos_periodo"),
        sa.Index(
            "ix_aej_arquivos_empresa",
            "tenant_id",
            "empresa_id",
            sa.text("periodo_inicio DESC"),
        ),
        {
            "comment": (
                "Arquivo Eletronico de Jornada, gerado pelo Programa de Tratamento de "
                "Registro de Ponto. Substitui AFDT e ACJEF."
            )
        },
    )


class ArquivoAssinatura(ChavePrimariaUUIDMixin, TenantMixin, CriacaoMixin, Base):
    """Assinatura digital CAdES de arquivos fiscais, em .p7s destacado."""

    __tablename__ = "arquivo_assinaturas"

    tipo_arquivo: Mapped[str] = mapped_column(nullable=False)
    arquivo_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    padrao: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'CAdES'"))
    formato: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'detached'"))
    assinatura_ref: Mapped[str] = mapped_column(nullable=False)
    certificado_titular: Mapped[str | None] = mapped_column()
    certificado_serial: Mapped[str | None] = mapped_column()
    certificado_emissor: Mapped[str | None] = mapped_column()
    certificado_validade_inicio: Mapped[_datetime.datetime | None] = mapped_column()
    certificado_validade_fim: Mapped[_datetime.datetime | None] = mapped_column()
    politica_assinatura: Mapped[str | None] = mapped_column()
    carimbo_tempo: Mapped[_datetime.datetime | None] = mapped_column()
    hash_arquivo: Mapped[str] = mapped_column(DOM_SHA256, nullable=False)
    algoritmo_hash: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'SHA-256'"))
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'assinado'"))
    validado_em: Mapped[_datetime.datetime | None] = mapped_column()
    validacao_resultado: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        sa.CheckConstraint(
            "tipo_arquivo IN ('afd','aej','espelho','comprovante','relatorio')",
            name="arquivo_assinaturas_tipo_arquivo_check",
        ),
        sa.CheckConstraint(
            "padrao IN ('CAdES','XAdES','PAdES')", name="arquivo_assinaturas_padrao_check"
        ),
        sa.CheckConstraint(
            "formato IN ('detached','attached')", name="arquivo_assinaturas_formato_check"
        ),
        sa.CheckConstraint(
            "status IN ('pendente','assinado','invalido','revogado')",
            name="arquivo_assinaturas_status_check",
        ),
        sa.Index("ix_arquivo_assinaturas_alvo", "tenant_id", "tipo_arquivo", "arquivo_id"),
        {
            "comment": (
                "Assinatura digital de arquivos fiscais no padrao CAdES, em .p7s "
                "destacado, com certificado ICP-Brasil. Referencia polimorfica sem chave "
                "estrangeira. Somente-acrescimo: DELETE e barrado por gatilho."
            )
        },
    )
