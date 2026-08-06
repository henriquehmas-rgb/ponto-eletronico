"""Grupo 7 - Marcacao (NUCLEO LEGAL).

`rep_ps`, `nsr_sequencias`, `marcacoes`, `nsr_emissoes`,
`marcacao_idempotencia`, `marcacoes_meta`, `fila_offline`, `comprovantes` e
`politicas_registro`.

Principio inegociavel: **marcacao e IMUTAVEL**. Nenhum endpoint, tela ou rotina
altera ou apaga um registro desta secao; a migration instala gatilhos que
abortam UPDATE, DELETE e TRUNCATE, e a role `ponto_app` sequer recebe esses
privilegios. Correcao vive em `tratamentos` (modulo `apuracao`).

`marcacoes` e PARTICIONADA POR MES em `datahora_marcacao`; por isso a chave
primaria e composta `(id, datahora_marcacao)` e todas as tabelas que a
referenciam usam chave estrangeira composta. As particoes mensais e a particao
padrao sao criadas pela migration, nao por model.

A unicidade GLOBAL do par REP-P + NSR nao pode ser imposta em `marcacoes` (o
PostgreSQL exige a chave de particao em constraint unica de tabela
particionada); quem a impoe e `nsr_emissoes`, que nao e particionada. O mesmo
vale para a idempotencia, imposta por `marcacao_idempotencia`.
"""

from __future__ import annotations

import datetime as _datetime
import decimal
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import BYTEA, INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import ORDEM_ID, Base
from .mixins import (
    AuditoriaMixin,
    ChavePrimariaUUIDMixin,
    CriacaoMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)
from .tipos import DOM_CNPJ, DOM_CPF, DOM_FUSO, DOM_PIS, DOM_SHA256

__all__ = [
    "Comprovante",
    "FilaOffline",
    "Marcacao",
    "MarcacaoIdempotencia",
    "MarcacaoMeta",
    "NsrEmissao",
    "NsrSequencia",
    "PoliticaRegistro",
    "RepP",
]

#: Expressao de particionamento de `marcacoes`. Usada pelo DDL e pela migration.
PARTICIONAMENTO_MARCACOES = "RANGE (datahora_marcacao)"


class RepP(
    ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, SoftDeleteMixin, Base
):
    """Identificacao de cada instancia de REP-P em operacao. O REP-P e o software."""

    __tablename__ = "rep_ps"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="RESTRICT"), nullable=False
    )
    identificador: Mapped[str] = mapped_column(nullable=False)
    tipo: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'rep_p'"))
    numero_inpi: Mapped[str] = mapped_column(nullable=False)
    cnpj_desenvolvedor: Mapped[str] = mapped_column(DOM_CNPJ, nullable=False)
    razao_social_desenvolvedor: Mapped[str] = mapped_column(nullable=False)
    cnpj_empregador: Mapped[str] = mapped_column(DOM_CNPJ, nullable=False)
    razao_social_empregador: Mapped[str] = mapped_column(nullable=False)
    cei_caepf: Mapped[str | None] = mapped_column()
    versao_programa: Mapped[str] = mapped_column(nullable=False)
    data_inicio_operacao: Mapped[_datetime.date] = mapped_column(nullable=False)
    data_fim_operacao: Mapped[_datetime.date | None] = mapped_column()
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'ativo'"))

    __table_args__ = (
        sa.CheckConstraint("tipo IN ('rep_p','rep_c','rep_a')", name="rep_ps_tipo_check"),
        sa.CheckConstraint(r"numero_inpi ~ '^[0-9]+$'", name="rep_ps_numero_inpi_check"),
        sa.CheckConstraint(
            "status IN ('ativo','inativo','substituido')", name="rep_ps_status_check"
        ),
        sa.CheckConstraint(
            "data_fim_operacao IS NULL OR data_fim_operacao >= data_inicio_operacao",
            name="ck_rep_ps_periodo",
        ),
        sa.Index(
            "uq_rep_ps_identificador",
            "tenant_id",
            "empresa_id",
            "identificador",
            unique=True,
            postgresql_where=sa.text("excluido_em IS NULL"),
        ),
        sa.Index(
            "ix_rep_ps_empresa",
            "tenant_id",
            "empresa_id",
            postgresql_where=sa.text("status = 'ativo'"),
        ),
        {
            "comment": (
                "Identificacao de cada instancia de REP-P em operacao. Cada um tem sua "
                "propria sequencia de NSR e seus proprios arquivos AFD."
            )
        },
    )


class NsrSequencia(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Alocador transacional do NSR, um por REP-P.

    Deliberadamente NAO usa SEQUENCE do PostgreSQL: sequence nao volta atras em
    rollback e produziria lacunas, o que a Portaria proibe. A alocacao e feita
    com `SELECT ... FOR UPDATE` nesta linha, dentro da mesma transacao da
    marcacao.
    """

    __tablename__ = "nsr_sequencias"

    rep_p_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("rep_ps.id", ondelete="RESTRICT"), nullable=False
    )
    proximo_nsr: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, server_default=sa.text("1")
    )
    ultimo_nsr_emitido: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, server_default=sa.text("0")
    )
    ultimo_hash: Mapped[str | None] = mapped_column(DOM_SHA256)
    ultima_emissao_em: Mapped[_datetime.datetime | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint("proximo_nsr >= 1", name="nsr_sequencias_proximo_nsr_check"),
        sa.CheckConstraint(
            "ultimo_nsr_emitido >= 0", name="nsr_sequencias_ultimo_nsr_emitido_check"
        ),
        sa.UniqueConstraint("tenant_id", "rep_p_id", name="uq_nsr_sequencias"),
        sa.CheckConstraint(
            "proximo_nsr = ultimo_nsr_emitido + 1", name="ck_nsr_sequencias_coerencia"
        ),
        {
            "comment": (
                "Alocador transacional do Numero Sequencial de Registro, um por REP-P. "
                "Nao usa SEQUENCE porque sequence nao volta atras em rollback e "
                "produziria lacunas, o que a Portaria proibe."
            )
        },
    )


class Marcacao(TenantMixin, CriacaoMixin, Base):
    """Registro de ponto. APPEND-ONLY e PARTICIONADA POR MES."""

    __tablename__ = "marcacoes"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
        sort_order=ORDEM_ID,
    )
    rep_p_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("rep_ps.id", ondelete="RESTRICT"), nullable=False
    )
    empresa_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="RESTRICT"), nullable=False
    )
    unidade_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("unidades.id", ondelete="RESTRICT")
    )
    colaborador_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("colaboradores.id", ondelete="RESTRICT")
    )
    vinculo_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("vinculos.id", ondelete="RESTRICT")
    )
    nsr: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    tipo_registro: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'7'"))
    sentido_informado: Mapped[str | None] = mapped_column()
    cpf: Mapped[str] = mapped_column(DOM_CPF, nullable=False)
    pis_nit: Mapped[str | None] = mapped_column(DOM_PIS)
    datahora_marcacao: Mapped[_datetime.datetime] = mapped_column(primary_key=True)
    datahora_gravacao: Mapped[_datetime.datetime] = mapped_column(
        nullable=False, server_default=sa.text("now()")
    )
    datahora_dispositivo: Mapped[_datetime.datetime | None] = mapped_column()
    fuso_horario: Mapped[str] = mapped_column(
        DOM_FUSO, nullable=False, server_default=sa.text("'America/Sao_Paulo'")
    )
    canal: Mapped[str] = mapped_column(nullable=False)
    dispositivo_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("dispositivos.id", ondelete="RESTRICT")
    )
    terminal_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("terminais.id", ondelete="RESTRICT")
    )
    external_id: Mapped[str | None] = mapped_column()
    log_externo_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    idempotency_key: Mapped[str | None] = mapped_column()
    # FK criada depois de `importacoes` (use_alter), como em schema.sql.
    origem_importacao_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey(
            "importacoes.id",
            ondelete="RESTRICT",
            name="fk_marcacoes_importacao",
            use_alter=True,
        )
    )
    crc16: Mapped[int] = mapped_column(nullable=False)
    hash_anterior: Mapped[str | None] = mapped_column(DOM_SHA256)
    hash_registro: Mapped[str] = mapped_column(DOM_SHA256, nullable=False)
    linha_afd: Mapped[str | None] = mapped_column()
    coletada_offline: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("FALSE"))

    __table_args__ = (
        sa.CheckConstraint("nsr >= 1", name="marcacoes_nsr_check"),
        sa.CheckConstraint(
            "tipo_registro IN ('2','3','4','5','6','7','9')",
            name="marcacoes_tipo_registro_check",
        ),
        sa.CheckConstraint(
            "sentido_informado IN ('entrada','saida','indefinido')",
            name="marcacoes_sentido_informado_check",
        ),
        sa.CheckConstraint(
            "canal IN ('terminal','mobile','web','totem','api','importacao')",
            name="marcacoes_canal_check",
        ),
        sa.CheckConstraint("crc16 BETWEEN 0 AND 65535", name="marcacoes_crc16_check"),
        sa.UniqueConstraint(
            "tenant_id", "rep_p_id", "nsr", "datahora_marcacao", name="uq_marcacoes_nsr"
        ),
        sa.Index(
            "ix_marcacoes_colaborador_data",
            "tenant_id",
            "colaborador_id",
            sa.text("datahora_marcacao DESC"),
        ),
        sa.Index("ix_marcacoes_vinculo_data", "tenant_id", "vinculo_id", "datahora_marcacao"),
        sa.Index("ix_marcacoes_rep_nsr", "tenant_id", "rep_p_id", "nsr"),
        sa.Index("ix_marcacoes_empresa_data", "tenant_id", "empresa_id", "datahora_marcacao"),
        sa.Index("ix_marcacoes_cpf", "tenant_id", "cpf", "datahora_marcacao"),
        sa.Index("ix_marcacoes_gravacao", "tenant_id", "datahora_gravacao"),
        sa.Index(
            "ix_marcacoes_idem_external",
            "tenant_id",
            "canal",
            "external_id",
            postgresql_where=sa.text("external_id IS NOT NULL"),
        ),
        sa.Index(
            "ix_marcacoes_idem_dispositivo",
            "tenant_id",
            "dispositivo_id",
            "log_externo_id",
            postgresql_where=sa.text("log_externo_id IS NOT NULL"),
        ),
        sa.Index(
            "ix_marcacoes_offline",
            "tenant_id",
            "datahora_marcacao",
            postgresql_where=sa.text("coletada_offline"),
        ),
        {
            "postgresql_partition_by": PARTICIONAMENTO_MARCACOES,
            "comment": (
                "Registro de ponto. APPEND-ONLY e PARTICIONADA POR MES em "
                "datahora_marcacao. Nunca sofre UPDATE nem DELETE: gatilhos abortam "
                "ambos. Toda correcao acontece em tratamentos, sem tocar aqui."
            ),
        },
    )


class NsrEmissao(ChavePrimariaUUIDMixin, TenantMixin, CriacaoMixin, Base):
    """Indice global de NSR emitidos. Impoe a unicidade que a tabela particionada nao pode."""

    __tablename__ = "nsr_emissoes"

    rep_p_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("rep_ps.id", ondelete="RESTRICT"), nullable=False
    )
    nsr: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    marcacao_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    datahora_marcacao: Mapped[_datetime.datetime] = mapped_column(nullable=False)
    hash_registro: Mapped[str] = mapped_column(DOM_SHA256, nullable=False)
    hash_anterior: Mapped[str | None] = mapped_column(DOM_SHA256)

    __table_args__ = (
        sa.CheckConstraint("nsr >= 1", name="nsr_emissoes_nsr_check"),
        sa.UniqueConstraint("tenant_id", "rep_p_id", "nsr", name="uq_nsr_emissoes"),
        sa.ForeignKeyConstraint(
            ["marcacao_id", "datahora_marcacao"],
            ["marcacoes.id", "marcacoes.datahora_marcacao"],
            name="fk_nsr_emissoes_marcacao",
            ondelete="RESTRICT",
        ),
        sa.Index("ix_nsr_emissoes_sequencia", "tenant_id", "rep_p_id", "nsr"),
        {
            "comment": (
                "Indice global de NSR emitidos. Nao e particionada e impoe a unicidade "
                "de (tenant_id, rep_p_id, nsr) globalmente, tornando a deteccao de "
                "lacuna uma consulta trivial."
            )
        },
    )


class MarcacaoIdempotencia(ChavePrimariaUUIDMixin, TenantMixin, CriacaoMixin, Base):
    """Guarda global de idempotencia de marcacao."""

    __tablename__ = "marcacao_idempotencia"

    escopo: Mapped[str] = mapped_column(nullable=False)
    chave: Mapped[str] = mapped_column(nullable=False)
    marcacao_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    datahora_marcacao: Mapped[_datetime.datetime] = mapped_column(nullable=False)

    __table_args__ = (
        sa.CheckConstraint(
            "escopo IN ('external_id','dispositivo_log','idempotency_key','offline_hmac')",
            name="marcacao_idempotencia_escopo_check",
        ),
        sa.UniqueConstraint("tenant_id", "escopo", "chave", name="uq_marcacao_idempotencia"),
        sa.ForeignKeyConstraint(
            ["marcacao_id", "datahora_marcacao"],
            ["marcacoes.id", "marcacoes.datahora_marcacao"],
            name="fk_marcacao_idempotencia_marcacao",
            ondelete="RESTRICT",
        ),
        sa.Index("ix_marcacao_idempotencia_marcacao", "tenant_id", "marcacao_id"),
        {
            "comment": (
                "Guarda global de idempotencia. Reenvio do mesmo registro offline colide "
                "aqui e nao duplica marcacao."
            )
        },
    )


class MarcacaoMeta(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Contexto e evidencia antifraude da marcacao. Separada para manter o nucleo legal imutavel."""

    __tablename__ = "marcacoes_meta"

    marcacao_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    marcacao_datahora: Mapped[_datetime.datetime] = mapped_column(nullable=False)
    latitude: Mapped[decimal.Decimal | None] = mapped_column(sa.Numeric(10, 7))
    longitude: Mapped[decimal.Decimal | None] = mapped_column(sa.Numeric(10, 7))
    precisao_metros: Mapped[decimal.Decimal | None] = mapped_column(sa.Numeric(8, 2))
    altitude: Mapped[decimal.Decimal | None] = mapped_column(sa.Numeric(8, 2))
    endereco_aproximado: Mapped[str | None] = mapped_column()
    unidade_geocerca_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("unidades.id", ondelete="SET NULL")
    )
    dentro_geocerca: Mapped[bool | None] = mapped_column()
    distancia_geocerca_metros: Mapped[decimal.Decimal | None] = mapped_column(sa.Numeric(10, 2))
    foto_ref: Mapped[str | None] = mapped_column()
    foto_hash: Mapped[str | None] = mapped_column(DOM_SHA256)
    score_facial: Mapped[decimal.Decimal | None] = mapped_column(sa.Numeric(5, 2))
    limiar_facial: Mapped[decimal.Decimal | None] = mapped_column(sa.Numeric(5, 2))
    versao_modelo_facial: Mapped[str | None] = mapped_column()
    liveness_aprovado: Mapped[bool | None] = mapped_column()
    liveness_metodo: Mapped[str | None] = mapped_column()
    score_confianca: Mapped[int | None] = mapped_column(sa.SmallInteger)
    classificacao_confianca: Mapped[str | None] = mapped_column()
    flags_integridade: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    attestation_veredito: Mapped[str | None] = mapped_column()
    root_detectado: Mapped[bool | None] = mapped_column()
    emulador_detectado: Mapped[bool | None] = mapped_column()
    modo_desenvolvedor: Mapped[bool | None] = mapped_column()
    mock_location: Mapped[bool | None] = mapped_column()
    camera_virtual: Mapped[bool | None] = mapped_column()
    velocidade_desde_ultima_kmh: Mapped[decimal.Decimal | None] = mapped_column(sa.Numeric(8, 2))
    wifi_bssid: Mapped[str | None] = mapped_column()
    celula_id: Mapped[str | None] = mapped_column()
    ip: Mapped[str | None] = mapped_column(INET)
    asn: Mapped[str | None] = mapped_column()
    pais: Mapped[str | None] = mapped_column()
    user_agent: Mapped[str | None] = mapped_column()
    fingerprint: Mapped[str | None] = mapped_column()
    revisao_status: Mapped[str] = mapped_column(
        nullable=False, server_default=sa.text("'nao_requer'")
    )
    revisado_por: Mapped[uuid.UUID | None] = mapped_column()
    revisado_em: Mapped[_datetime.datetime | None] = mapped_column()
    revisao_observacao: Mapped[str | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name="marcacoes_meta_latitude_check",
        ),
        sa.CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name="marcacoes_meta_longitude_check",
        ),
        sa.CheckConstraint(
            "precisao_metros IS NULL OR precisao_metros >= 0",
            name="marcacoes_meta_precisao_metros_check",
        ),
        sa.CheckConstraint(
            "score_facial IS NULL OR score_facial BETWEEN 0 AND 100",
            name="marcacoes_meta_score_facial_check",
        ),
        sa.CheckConstraint(
            "limiar_facial IS NULL OR limiar_facial BETWEEN 0 AND 100",
            name="marcacoes_meta_limiar_facial_check",
        ),
        sa.CheckConstraint(
            "liveness_metodo IN ('desafio_ativo','passivo','hibrido','nao_aplicavel')",
            name="marcacoes_meta_liveness_metodo_check",
        ),
        sa.CheckConstraint(
            "score_confianca IS NULL OR score_confianca BETWEEN 0 AND 100",
            name="marcacoes_meta_score_confianca_check",
        ),
        sa.CheckConstraint(
            "classificacao_confianca IN ('alta','media','baixa','bloqueada')",
            name="marcacoes_meta_classificacao_confianca_check",
        ),
        sa.CheckConstraint(
            "attestation_veredito IN ('aprovado','reprovado','indisponivel','nao_aplicavel')",
            name="marcacoes_meta_attestation_veredito_check",
        ),
        sa.CheckConstraint(
            "revisao_status IN ('nao_requer','pendente','aprovada','rejeitada')",
            name="marcacoes_meta_revisao_status_check",
        ),
        sa.UniqueConstraint("tenant_id", "marcacao_id", name="uq_marcacoes_meta"),
        sa.ForeignKeyConstraint(
            ["marcacao_id", "marcacao_datahora"],
            ["marcacoes.id", "marcacoes.datahora_marcacao"],
            name="fk_marcacoes_meta_marcacao",
            ondelete="RESTRICT",
        ),
        sa.Index(
            "ix_marcacoes_meta_revisao",
            "tenant_id",
            "revisao_status",
            postgresql_where=sa.text("revisao_status = 'pendente'"),
        ),
        sa.Index("ix_marcacoes_meta_score", "tenant_id", "score_confianca"),
        sa.Index(
            "ix_marcacoes_meta_fora_cerca",
            "tenant_id",
            "marcacao_datahora",
            postgresql_where=sa.text("dentro_geocerca = FALSE"),
        ),
        sa.Index("ix_marcacoes_meta_flags", "flags_integridade", postgresql_using="gin"),
        {
            "comment": (
                "Contexto e evidencia antifraude da marcacao. Separada de marcacoes para "
                "manter o nucleo legal enxuto e imutavel e permitir que o gestor revise o "
                "risco sem jamais tocar no registro legal."
            )
        },
    )


class FilaOffline(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Itens capturados sem rede e enviados depois. Estagio ANTES de virar registro legal."""

    __tablename__ = "fila_offline"

    colaborador_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("colaboradores.id", ondelete="RESTRICT")
    )
    dispositivo_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("dispositivos.id", ondelete="RESTRICT"), nullable=False
    )
    payload_cifrado: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    iv: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    hmac: Mapped[str] = mapped_column(nullable=False)
    contador_monotonico: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    datahora_dispositivo: Mapped[_datetime.datetime] = mapped_column(nullable=False)
    tempo_monotonico_ms: Mapped[int | None] = mapped_column(sa.BigInteger)
    capturado_em_offline: Mapped[bool] = mapped_column(
        nullable=False, server_default=sa.text("TRUE")
    )
    recebido_em: Mapped[_datetime.datetime] = mapped_column(
        nullable=False, server_default=sa.text("now()")
    )
    processado_em: Mapped[_datetime.datetime | None] = mapped_column()
    status: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'pendente'"))
    tentativas: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("0"))
    erro: Mapped[str | None] = mapped_column()
    marcacao_id: Mapped[uuid.UUID | None] = mapped_column()
    marcacao_datahora: Mapped[_datetime.datetime | None] = mapped_column()
    expira_em: Mapped[_datetime.datetime | None] = mapped_column()

    __table_args__ = (
        sa.CheckConstraint(
            "contador_monotonico >= 0", name="fila_offline_contador_monotonico_check"
        ),
        sa.CheckConstraint(
            "status IN ('pendente','processado','duplicado','rejeitado','expirado')",
            name="fila_offline_status_check",
        ),
        sa.CheckConstraint("tentativas >= 0", name="fila_offline_tentativas_check"),
        sa.UniqueConstraint(
            "tenant_id",
            "dispositivo_id",
            "contador_monotonico",
            name="uq_fila_offline_contador",
        ),
        sa.ForeignKeyConstraint(
            ["marcacao_id", "marcacao_datahora"],
            ["marcacoes.id", "marcacoes.datahora_marcacao"],
            name="fk_fila_offline_marcacao",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "(marcacao_id IS NULL AND marcacao_datahora IS NULL) OR "
            "(marcacao_id IS NOT NULL AND marcacao_datahora IS NOT NULL)",
            name="ck_fila_offline_marcacao",
        ),
        sa.Index(
            "ix_fila_offline_pendentes",
            "tenant_id",
            "status",
            "recebido_em",
            postgresql_where=sa.text("status = 'pendente'"),
        ),
        sa.Index(
            "ix_fila_offline_dispositivo",
            "tenant_id",
            "dispositivo_id",
            sa.text("contador_monotonico DESC"),
        ),
        {
            "comment": (
                "Itens capturados sem rede e enviados depois. Chegam cifrados e "
                "assinados; o servidor valida HMAC e contador antes de converter em "
                "marcacao. Esta tabela e mutavel de proposito."
            )
        },
    )


class Comprovante(ChavePrimariaUUIDMixin, TenantMixin, CriacaoMixin, Base):
    """Comprovante de registro emitido a cada marcacao. APPEND-ONLY."""

    __tablename__ = "comprovantes"

    marcacao_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    marcacao_datahora: Mapped[_datetime.datetime] = mapped_column(nullable=False)
    colaborador_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("colaboradores.id", ondelete="RESTRICT")
    )
    cpf: Mapped[str] = mapped_column(DOM_CPF, nullable=False)
    numero: Mapped[str] = mapped_column(nullable=False)
    nsr: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    conteudo_texto: Mapped[str] = mapped_column(nullable=False)
    conteudo_ref: Mapped[str | None] = mapped_column()
    hash_sha256: Mapped[str] = mapped_column(DOM_SHA256, nullable=False)
    assinatura_ref: Mapped[str | None] = mapped_column()
    emitido_em: Mapped[_datetime.datetime] = mapped_column(
        nullable=False, server_default=sa.text("now()")
    )
    disponivel_ate: Mapped[_datetime.datetime | None] = mapped_column()
    canal_entrega: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'app'"))

    __table_args__ = (
        sa.CheckConstraint(
            "canal_entrega IN ('app','web','email','impresso','api','terminal')",
            name="comprovantes_canal_entrega_check",
        ),
        sa.UniqueConstraint("tenant_id", "marcacao_id", name="uq_comprovantes_marcacao"),
        sa.UniqueConstraint("tenant_id", "numero", name="uq_comprovantes_numero"),
        sa.ForeignKeyConstraint(
            ["marcacao_id", "marcacao_datahora"],
            ["marcacoes.id", "marcacoes.datahora_marcacao"],
            name="fk_comprovantes_marcacao",
            ondelete="RESTRICT",
        ),
        sa.Index(
            "ix_comprovantes_colaborador",
            "tenant_id",
            "colaborador_id",
            sa.text("emitido_em DESC"),
        ),
        sa.Index("ix_comprovantes_48h", "tenant_id", sa.text("emitido_em DESC")),
        {
            "comment": (
                "Comprovante de registro emitido a cada marcacao. Append-only. A "
                "impressao no momento da marcacao e dispensada porque garantimos acesso "
                "eletronico permanente, com as ultimas 48 horas sempre disponiveis."
            )
        },
    )


class PoliticaRegistro(ChavePrimariaUUIDMixin, TenantMixin, TimestampMixin, AuditoriaMixin, Base):
    """Politica antifraude aplicada ao registro de ponto, por empresa, unidade e canal."""

    __tablename__ = "politicas_registro"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False
    )
    unidade_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("unidades.id", ondelete="CASCADE")
    )
    canal: Mapped[str | None] = mapped_column()
    exige_geocerca: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))
    exige_facial: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))
    exige_liveness: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))
    exige_attestation: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))
    exige_rede_permitida: Mapped[bool] = mapped_column(
        nullable=False, server_default=sa.text("FALSE")
    )
    limiar_facial: Mapped[decimal.Decimal] = mapped_column(
        sa.Numeric(5, 2), nullable=False, server_default=sa.text("75")
    )
    limiar_bloqueio: Mapped[int] = mapped_column(
        sa.SmallInteger, nullable=False, server_default=sa.text("40")
    )
    limiar_revisao: Mapped[int] = mapped_column(
        sa.SmallInteger, nullable=False, server_default=sa.text("70")
    )
    politica_modo_desenvolvedor: Mapped[str] = mapped_column(
        nullable=False, server_default=sa.text("'bloquear'")
    )
    politica_root: Mapped[str] = mapped_column(nullable=False, server_default=sa.text("'bloquear'"))
    politica_mock_location: Mapped[str] = mapped_column(
        nullable=False, server_default=sa.text("'bloquear'")
    )
    politica_fora_geocerca: Mapped[str] = mapped_column(
        nullable=False, server_default=sa.text("'sinalizar'")
    )
    bloquear_vpn_proxy: Mapped[bool] = mapped_column(
        nullable=False, server_default=sa.text("FALSE")
    )
    exige_reautenticacao: Mapped[bool] = mapped_column(
        nullable=False, server_default=sa.text("TRUE")
    )
    ttl_offline_horas: Mapped[int] = mapped_column(nullable=False, server_default=sa.text("72"))
    ativo: Mapped[bool] = mapped_column(nullable=False, server_default=sa.text("TRUE"))
    # F14/A1 (ADR-008): pesos da composicao ponderada do score de confianca.
    # Aditivo -- ver comentario de coluna em schema.sql para o porque de nao
    # haver CHECK de soma = 100 (o motor renormaliza pelas categorias
    # disponiveis, `app.antifraude.motor`).
    peso_dispositivo: Mapped[int] = mapped_column(
        sa.SmallInteger, nullable=False, server_default=sa.text("25")
    )
    peso_biometria: Mapped[int] = mapped_column(
        sa.SmallInteger, nullable=False, server_default=sa.text("25")
    )
    peso_geolocalizacao: Mapped[int] = mapped_column(
        sa.SmallInteger, nullable=False, server_default=sa.text("25")
    )
    peso_comportamento: Mapped[int] = mapped_column(
        sa.SmallInteger, nullable=False, server_default=sa.text("25")
    )
    perfil_confianca: Mapped[str] = mapped_column(
        nullable=False, server_default=sa.text("'equilibrado'")
    )

    __table_args__ = (
        sa.CheckConstraint(
            "canal IN ('terminal','mobile','web','totem','api')",
            name="politicas_registro_canal_check",
        ),
        sa.CheckConstraint(
            "limiar_facial BETWEEN 0 AND 100", name="politicas_registro_limiar_facial_check"
        ),
        sa.CheckConstraint(
            "limiar_bloqueio BETWEEN 0 AND 100",
            name="politicas_registro_limiar_bloqueio_check",
        ),
        sa.CheckConstraint(
            "limiar_revisao BETWEEN 0 AND 100",
            name="politicas_registro_limiar_revisao_check",
        ),
        sa.CheckConstraint(
            "politica_modo_desenvolvedor IN ('bloquear','sinalizar','permitir')",
            name="politicas_registro_politica_modo_desenvolvedor_check",
        ),
        sa.CheckConstraint(
            "politica_root IN ('bloquear','sinalizar','permitir')",
            name="politicas_registro_politica_root_check",
        ),
        sa.CheckConstraint(
            "politica_mock_location IN ('bloquear','sinalizar','permitir')",
            name="politicas_registro_politica_mock_location_check",
        ),
        sa.CheckConstraint(
            "politica_fora_geocerca IN ('bloquear','sinalizar','permitir')",
            name="politicas_registro_politica_fora_geocerca_check",
        ),
        sa.CheckConstraint(
            "ttl_offline_horas > 0", name="politicas_registro_ttl_offline_horas_check"
        ),
        sa.CheckConstraint(
            "limiar_revisao >= limiar_bloqueio", name="ck_politicas_registro_limiares"
        ),
        sa.CheckConstraint(
            "peso_dispositivo BETWEEN 0 AND 100", name="politicas_registro_peso_dispositivo_check"
        ),
        sa.CheckConstraint(
            "peso_biometria BETWEEN 0 AND 100", name="politicas_registro_peso_biometria_check"
        ),
        sa.CheckConstraint(
            "peso_geolocalizacao BETWEEN 0 AND 100",
            name="politicas_registro_peso_geolocalizacao_check",
        ),
        sa.CheckConstraint(
            "peso_comportamento BETWEEN 0 AND 100",
            name="politicas_registro_peso_comportamento_check",
        ),
        sa.CheckConstraint(
            "perfil_confianca IN ('rigoroso','equilibrado','tolerante','personalizado')",
            name="politicas_registro_perfil_confianca_check",
        ),
        sa.Index(
            "uq_politicas_registro",
            "tenant_id",
            "empresa_id",
            sa.text("COALESCE(unidade_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            sa.text("COALESCE(canal, '*')"),
            unique=True,
        ),
        {
            "comment": (
                "Politica antifraude aplicada ao registro de ponto, por empresa, unidade "
                "e canal. Guarda a decisao configuravel entre bloquear, sinalizar e "
                "permitir."
            )
        },
    )
