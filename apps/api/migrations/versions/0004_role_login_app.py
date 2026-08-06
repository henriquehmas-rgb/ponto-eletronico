"""Role de LOGIN de privilegio minimo para a aplicacao (F14, ADR-001 regra 4).

Revisao: 0004_role_login_app
Revisao anterior: 0003_antifraude_pesos_score
Alvo: PostgreSQL 16

Achado da verificacao adversarial da F14 (A4, teste `test_bypass_rls.py`):
`ponto_app` (criado por `0001_inicial.py`) e uma role NOLOGIN pensada para ser
herdada por uma role de LOGIN separada -- a propria migration 0001 ja avisa
"Crie ponto_app... manualmente (ver infra/)" -- mas nenhum arquivo em `infra/`
jamais criou essa role de LOGIN. Resultado, confirmado por leitura de
`infra/docker-compose.yml` e reproduzido contra Postgres real: toda instancia
deste sistema (a stack de "producao/homologacao" que aquele arquivo descreve,
premissas fechadas em PROJETO.md §11.2) roda com `DATABASE_URL` apontando para
`POSTGRES_USER` -- que a imagem oficial do Postgres sempre cria como
SUPERUSER. RLS nunca se aplica a superusuario, mesmo com `FORCE ROW LEVEL
SECURITY` em toda tabela (ADR-001). A *policy* de isolamento por tenant estava
correta (`pol_isolamento_tenant`, confirmada por teste com a role certa); a
credencial que a aplicacao usa para conectar nunca foi.

Esta migration fecha a lacuna: cria (ou atualiza a senha de) uma role de LOGIN
chamada `ponto_app_runtime`, membro de `ponto_app`, SEM BYPASSRLS, SEM
CREATEROLE, sem nenhum privilegio alem do que `ponto_app` ja concede
(0001_inicial.py, secao 11). NAO chamada `ponto_app_login` de proposito:
`tests/f1/rbac/conftest.py` ja usa esse nome exato, com senha propria
(`testeSomenteLocal_2026`), para uma role de teste isolada havia meses --
reusar o nome faria esta migration sobrescrever a senha que aqueles testes
esperam, quebrando toda a suite de RBAC/RLS de F1 (achado real, reproduzido
ao rodar a regressao combinada apos escrever a primeira versao desta
migration com o nome errado). A senha vem da variavel de ambiente
`POSTGRES_APP_PASSWORD` (mesmo nome que `infra/.env.example` passa a
documentar) -- nunca gravada neste arquivo como segredo real. Quando a
variavel nao esta definida (execucao manual fora de `infra/`, por exemplo em
ambiente de desenvolvimento local), usa um valor padrao fixo e publico,
claramente marcado como uso exclusivo de dev -- mesmo espirito de outros
fallbacks locais deste projeto (nunca falha silenciosamente, nunca finge
seguranca que nao existe).

`infra/docker-compose.yml` (mesmo commit) passa a apontar `DATABASE_URL` dos
servicos `api`/`worker`/`scheduler`/`device-gw` para `ponto_app_runtime`,
nunca mais para `POSTGRES_USER`. `POSTGRES_USER`/`POSTGRES_PASSWORD`
continuam existindo e sao usados SOMENTE por quem roda migration (Alembic,
humano ou CI) -- nunca pela aplicacao em runtime.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from alembic import op

revision: str = "0004_role_login_app"
down_revision: str | None = "0003_antifraude_pesos_score"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLE_LOGIN = "ponto_app_runtime"
_ROLE_GRUPO = "ponto_app"

#: So usado quando POSTGRES_APP_PASSWORD nao esta definida -- infra/docker-
#: compose.yml sempre define a variavel via .env (obrigatoria, sem default,
#: ver infra/.env.example). Publico e documentado de proposito: um fallback
#: escondido pareceria seguranca onde nao ha.
_SENHA_PADRAO_DEV = "ponto-app-dev-nao-use-em-producao"


def _senha_escapada() -> str:
    senha = os.environ.get("POSTGRES_APP_PASSWORD", _SENHA_PADRAO_DEV)
    # Escape de literal SQL (dobra aspas simples) -- suficiente aqui porque
    # quem controla o valor e o operador da migration, nunca entrada de
    # requisicao HTTP; mesmo assim nunca interpolado sem escape.
    return senha.replace("'", "''")


def upgrade() -> None:
    # Supressao de S608 abaixo justificada: `_ROLE_LOGIN`/`_ROLE_GRUPO` sao
    # constantes literais deste modulo (nunca entrada de requisicao), e a
    # senha ja passa por `_senha_escapada()` (escape de aspas simples) antes
    # de entrar no literal SQL -- nao ha superficie de injecao real aqui.
    sql = f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_ROLE_LOGIN}') THEN
                EXECUTE 'CREATE ROLE {_ROLE_LOGIN} LOGIN PASSWORD ''{_senha_escapada()}'' IN ROLE {_ROLE_GRUPO}';
            ELSE
                -- LOGIN explicito aqui (nao so PASSWORD): se um downgrade()
                -- anterior tiver deixado a role NOLOGIN, um upgrade() precisa
                -- restaurar os dois atributos, nunca so a senha.
                EXECUTE 'ALTER ROLE {_ROLE_LOGIN} LOGIN PASSWORD ''{_senha_escapada()}''';
            END IF;
        EXCEPTION
            WHEN insufficient_privilege THEN
                RAISE NOTICE 'Sem privilegio para criar/alterar {_ROLE_LOGIN}. Crie manualmente (ver infra/), membro de {_ROLE_GRUPO}, sem BYPASSRLS.';
        END $$
        """  # noqa: S608
    op.execute(sql)


def downgrade() -> None:
    # Supressao de S608 abaixo: mesma razao de upgrade() acima.
    sql = f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_ROLE_LOGIN}') THEN
                EXECUTE 'ALTER ROLE {_ROLE_LOGIN} NOLOGIN';
            END IF;
        EXCEPTION
            WHEN insufficient_privilege THEN
                RAISE NOTICE 'Sem privilegio para alterar {_ROLE_LOGIN}.';
        END $$
        """  # noqa: S608
    op.execute(sql)
