"""Pesos da composicao do score de confianca em `politicas_registro` (F14/A1).

Revisao: 0003_antifraude_pesos_score
Revisao anterior: 0002_idempotencia_chaves
Alvo: PostgreSQL 16

PCF F14 (secao 5, "A1 -- Score de confianca") e ADR-008 autorizam esta
migration explicitamente: "acrescente os campos de limiar que faltarem via
migration nova (aditiva, sem quebrar coluna existente)" -- unica migration
nova autorizada para este agente. `politicas_registro` ja tinha os limiares de
faixa (`limiar_bloqueio`/`limiar_revisao`/`limiar_facial`) desde a Fase 0; o
que faltava era ONDE guardar o peso de cada categoria de sinal na composicao
ponderada (ADR-008: "score composto... por sinais ponderados"). Cinco colunas
novas, todas com DEFAULT e NOT NULL, nenhuma coluna existente tocada:

* `peso_dispositivo`/`peso_biometria`/`peso_geolocalizacao`/`peso_comportamento`
  (SMALLINT 0-100 cada): peso da categoria. Sem CHECK de soma = 100 -- o motor
  de composicao (`app.antifraude.motor`) renormaliza pelas categorias
  disponiveis no momento do registro, entao pesos que nao somam 100 continuam
  produzindo um score valido de 0 a 100 (ver docstring daquele modulo).
* `perfil_confianca` (TEXT, enum 'rigoroso'/'equilibrado'/'tolerante'/
  'personalizado'): rotulo informativo do perfil de calibracao vigente
  (ADR-008, consequencia d, "tres perfis prontos"); nao interpretado pelo
  motor, so pelo painel/gestor.

Nao replicada em nenhuma outra fase: `politicas_registro` e propriedade do
grupo de score/antifraude por definicao do proprio schema.sql (secao 8).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_antifraude_pesos_score"
down_revision: str | None = "0002_idempotencia_chaves"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABELA = "politicas_registro"

_COLUNAS_PESO = (
    "peso_dispositivo",
    "peso_biometria",
    "peso_geolocalizacao",
    "peso_comportamento",
)


def upgrade() -> None:
    for coluna in _COLUNAS_PESO:
        op.add_column(
            _TABELA,
            sa.Column(coluna, sa.SmallInteger(), nullable=False, server_default=sa.text("25")),
        )
        op.create_check_constraint(
            f"{_TABELA}_{coluna}_check",
            _TABELA,
            f"{coluna} BETWEEN 0 AND 100",
        )

    op.add_column(
        _TABELA,
        sa.Column(
            "perfil_confianca",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'equilibrado'"),
        ),
    )
    op.create_check_constraint(
        f"{_TABELA}_perfil_confianca_check",
        _TABELA,
        "perfil_confianca IN ('rigoroso','equilibrado','tolerante','personalizado')",
    )


def downgrade() -> None:
    op.drop_constraint(f"{_TABELA}_perfil_confianca_check", _TABELA, type_="check")
    op.drop_column(_TABELA, "perfil_confianca")
    for coluna in _COLUNAS_PESO:
        op.drop_constraint(f"{_TABELA}_{coluna}_check", _TABELA, type_="check")
        op.drop_column(_TABELA, coluna)
