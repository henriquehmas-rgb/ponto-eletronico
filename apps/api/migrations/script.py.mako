"""${message}

Revisao: ${up_revision}
Revisao anterior: ${down_revision | comma,n}
Criada em: ${create_date}

Lembretes do contrato (ver packages/contracts/README.md):

* O autogenerate NAO enxerga extensoes, dominios, funcoes PL/pgSQL,
  particionamento, gatilhos, policies de RLS, roles nem privilegios. Se a
  mudanca envolve algum desses objetos, escreva o DDL a mao aqui.
* Tabela nova com `tenant_id` PRECISA sair desta migration ja com
  `ENABLE`/`FORCE ROW LEVEL SECURITY` e a policy `pol_isolamento_tenant`.
* Tabela append-only nao recebe UPDATE nem DELETE: adicione os gatilhos de
  `fn_registro_imutavel()` e revogue os privilegios de `ponto_app`.
* `downgrade()` precisa desfazer tudo, inclusive o DDL escrito a mao.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
