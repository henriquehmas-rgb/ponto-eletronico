"""Mixins reutilizaveis dos models do contrato.

Cinco blocos, combinados conforme a natureza da tabela:

| Mixin                   | Colunas                                    | Onde entra |
|-------------------------|--------------------------------------------|------------|
| `ChavePrimariaUUIDMixin`| `id`                                       | todas, exceto `marcacoes` (PK composta) |
| `TenantMixin`           | `tenant_id`                                | toda tabela de dominio, exceto `tenants` e `permissoes` |
| `TimestampMixin`        | `criado_em`, `atualizado_em`               | tabelas mutaveis |
| `AuditoriaMixin`        | `criado_por`, `atualizado_por`             | tabelas mutaveis |
| `SoftDeleteMixin`       | `excluido_em`, `excluido_por`              | somente cadastros |
| `CriacaoMixin`          | `criado_em`, `criado_por`                  | tabelas append-only |

`CriacaoMixin` existe porque tabela append-only (marcacao, extrato de banco de
horas, auditoria, comprovante) NAO pode ter `atualizado_em`/`atualizado_por`:
a coluna sugeriria que a linha muda, e ela nao muda. A ausencia e contrato,
nao esquecimento.

`criado_por`, `atualizado_por` e `excluido_por` sao referencias LOGICAS a
`usuarios.id`, deliberadamente SEM chave estrangeira. Tres motivos, registrados
no glossario: evitam ciclo entre `tenants`, `usuarios` e `colaboradores`;
preservam a autoria em registros legais depois do expurgo LGPD do usuario; e
permitem autoria de processos que nao sao usuarios (worker, migracao,
importador).
"""

from __future__ import annotations

import datetime as _datetime
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import (
    ORDEM_ATUALIZADO_EM,
    ORDEM_ATUALIZADO_POR,
    ORDEM_CRIADO_EM,
    ORDEM_CRIADO_POR,
    ORDEM_EXCLUIDO_EM,
    ORDEM_EXCLUIDO_POR,
    ORDEM_ID,
    ORDEM_TENANT,
    agora_no_banco,
    uuid_v4_no_banco,
)

__all__ = [
    "AuditoriaMixin",
    "ChavePrimariaUUIDMixin",
    "CriacaoMixin",
    "SoftDeleteMixin",
    "TenantMixin",
    "TimestampMixin",
]


class ChavePrimariaUUIDMixin:
    """Chave primaria UUID v4 gerada pelo banco."""

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=uuid_v4_no_banco(),
        sort_order=ORDEM_ID,
    )


class TenantMixin:
    """Coluna de isolamento multi-tenant.

    Toda tabela que herda este mixin fica automaticamente sob a policy
    `pol_isolamento_tenant` aplicada pela migration inicial, que compara
    `tenant_id` com `current_setting('app.tenant_id')`. Sem o `SET LOCAL
    app.tenant_id` no inicio da transacao, nenhuma linha e visivel.

    O padrao e `ON DELETE RESTRICT`: apagar um tenant com dado de ponto e
    proibido pela retencao legal de cinco anos. As poucas tabelas que usam
    CASCADE declaram a propria coluna.
    """

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        sort_order=ORDEM_TENANT,
    )


class TimestampMixin:
    """Carimbos de tempo de criacao e ultima alteracao.

    `atualizado_em` e mantido pelo gatilho `fn_atualiza_timestamp()`, aplicado
    pela migration a toda tabela que possui a coluna. A aplicacao nao precisa
    preencher.
    """

    criado_em: Mapped[_datetime.datetime] = mapped_column(
        nullable=False,
        server_default=agora_no_banco(),
        sort_order=ORDEM_CRIADO_EM,
    )
    atualizado_em: Mapped[_datetime.datetime | None] = mapped_column(
        sort_order=ORDEM_ATUALIZADO_EM,
    )


class AuditoriaMixin:
    """Autoria da criacao e da ultima alteracao (referencia logica a `usuarios.id`)."""

    criado_por: Mapped[uuid.UUID | None] = mapped_column(sort_order=ORDEM_CRIADO_POR)
    atualizado_por: Mapped[uuid.UUID | None] = mapped_column(
        sort_order=ORDEM_ATUALIZADO_POR,
    )


class SoftDeleteMixin:
    """Exclusao logica. SOMENTE em cadastros.

    Nunca em marcacoes, lancamentos, auditoria ou qualquer trilha legal: nessas
    tabelas o registro simplesmente nao sai.
    """

    excluido_em: Mapped[_datetime.datetime | None] = mapped_column(
        sort_order=ORDEM_EXCLUIDO_EM,
    )
    excluido_por: Mapped[uuid.UUID | None] = mapped_column(sort_order=ORDEM_EXCLUIDO_POR)


class CriacaoMixin:
    """Autoria e carimbo de criacao para tabelas APPEND-ONLY.

    Nao inclui `atualizado_em` nem `atualizado_por` de proposito: registros
    dessas tabelas nao sofrem UPDATE, e gatilhos abortam a tentativa.
    """

    criado_em: Mapped[_datetime.datetime] = mapped_column(
        nullable=False,
        server_default=agora_no_banco(),
        sort_order=ORDEM_CRIADO_EM,
    )
    criado_por: Mapped[uuid.UUID | None] = mapped_column(sort_order=ORDEM_CRIADO_POR)
