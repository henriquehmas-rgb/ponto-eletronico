"""Role de LOGIN do SUPORTE da SEEG (`ponto_app_suporte`) e a permissao
`tenants.suporte` que a governa -- escape hatch de RLS, deliberadamente
estreito, para `listarTenants`/`criarTenant`.

Revisao: 0005_role_suporte_bypassrls
Revisao anterior: 0004_role_login_app
Alvo: PostgreSQL 16

------------------------------------------------------------------------------
POR QUE ESTA ROLE EXISTE (e por que ela e diferente das outras tres)
------------------------------------------------------------------------------
O sistema tem, ate aqui, tres roles no cluster:

* `ponto` (ou o `POSTGRES_USER` da instancia) -- SUPERUSER, usado SOMENTE por
  quem roda migration (Alembic, humano ou CI). Nunca pela aplicacao.
* `ponto_app` -- role de GRUPO, NOLOGIN, dona dos privilegios de tabela da
  aplicacao (0001_inicial.py, secao 11). Sem `BYPASSRLS`.
* `ponto_app_runtime` -- role de LOGIN, membro de `ponto_app`, usada por TODA
  requisicao HTTP normal desde `0004_role_login_app`. Sem `BYPASSRLS`, e assim
  deve continuar (ADR-001: RLS e a fronteira real entre tenants).
* (`ponto_leitura`/`ponto_suporte`, criadas por 0001, sao NOLOGIN e nao estao
  ligadas a nenhum ciclo de requisicao -- `ponto_suporte` e uma role de
  consulta manual/DBA, so `SELECT`, nunca usada pela API.)

`GET /v1/tenants` (`listarTenants`) e `POST /v1/tenants` (`criarTenant`) sao,
por desenho, operacoes CROSS-tenant: a primeira lista TODOS os tenants do SaaS
(a policy `pol_isolamento_tenant` de `tenants` compara `id` com
`app.tenant_id`, entao uma sessao normal enxerga exatamente UMA linha); a
segunda insere a linha de um tenant que ainda nao existe (nao ha
`app.tenant_id` para publicar antes do INSERT, e o `WITH CHECK` da policy
recusaria). Por isso as duas responderam `501 PONTO-INT-005` desde a F1.

`ponto_app_suporte` e a resposta a isso, e NAO uma quarta role "geral":

1. **Tem `BYPASSRLS`** -- e a unica role de LOGIN do sistema que tem. Sem isso
   nao existe operacao cross-tenant nenhuma (RLS nao e contornavel por SQL da
   aplicacao; so pelo atributo da role, que o Postgres le direto de
   `pg_authid.rolbypassrls` -- membership em outra role NAO transmite o
   atributo, por isso ele precisa estar nesta role, e so nela).
2. **NAO e membro de `ponto_app`.** Deliberado: heranca daria a ela
   `SELECT/INSERT/UPDATE/DELETE` em TODAS as ~92 tabelas do schema -- somado ao
   `BYPASSRLS`, isso seria uma credencial capaz de ler biometria, marcacao e
   folha de todos os clientes. Em vez disso ela recebe, explicitamente, o
   MINIMO que as duas rotas usam:
       - `SELECT, INSERT` em `tenants`   (listar e criar)
       - `SELECT, INSERT` em `auditoria` (a trilha obrigatoria da operacao;
         `SELECT` porque a cadeia de hash precisa ler `MAX(sequencia)` e o
         `hash_registro` anterior antes de inserir)
   Nada mais. Mesmo com `BYPASSRLS`, um `SELECT * FROM colaboradores` com esta
   credencial responde `permission denied for table colaboradores`. O bypass e
   real, mas o alcance dele e de duas tabelas.
3. **So e usada por essas duas rotas.** `app/db/sessao_suporte.py` abre uma
   engine PROPRIA com esta credencial; `app/db/sessao.py` (`SessaoDb`,
   compartilhada por todo o resto do sistema) continua conectando como
   `ponto_app_runtime`, sem `BYPASSRLS`, exatamente como antes.

A senha vem de `POSTGRES_SUPORTE_PASSWORD` -- mesmo padrao (e mesmo fallback
de desenvolvimento explicito, publico e marcado como tal) de
`0004_role_login_app` com `POSTGRES_APP_PASSWORD`. Nenhum segredo real e
gravado neste arquivo.

------------------------------------------------------------------------------
A PERMISSAO `tenants.suporte`
------------------------------------------------------------------------------
O `openapi.yaml` declara `x-permissao: tenants.ler` para `listarTenants` e
`tenants.criar` para `criarTenant`. As duas sao insuficientes como portao:
`MATRIZ_PERFIS` (`migrations/seed_dev.py`) concede `"*": _TODAS_AS_ACOES` ao
perfil `admin_empresa` -- ou seja, o administrador de QUALQUER tenant cliente
ja tem `tenants.ler` e `tenants.criar` hoje. Usar so o codigo do contrato
transformaria cada admin de cliente num super admin do SaaS.

Por isso esta migration acrescenta uma acao nova ao `CHECK` de
`permissoes.acao` -- `suporte` -- e semeia a permissao `tenants.suporte`. A
escolha da acao NOVA (em vez de reusar `administrar`, que ja passa no CHECK) e
uma decisao de seguranca, nao de estetica: `_TODAS_AS_ACOES` do
`seed_dev.MATRIZ_PERFIS` contem `administrar`, entao `tenants.administrar`
seria concedida automaticamente ao `admin_empresa` de todo tenant pelo
curinga `"*"` -- exatamente o defeito que este portao existe para evitar.
`suporte` NAO esta em `_TODAS_AS_ACOES`: nenhum curinga existente a concede, e
toda concessao dela e necessariamente explicita (falha fechada).

A permissao e inserida aqui, na migration, e nao so no `seed_dev.py`, porque
`permissoes` e o catalogo GLOBAL do produto (sem `tenant_id`, sem RLS,
somente leitura para a aplicacao -- a role da aplicacao teve `INSERT/UPDATE/
DELETE` revogados nela por 0001) e porque nem todo banco passa por
`seed_dev.py` (o banco de teste da F1, por exemplo, so roda `alembic upgrade
head`).

`downgrade()` desfaz na ordem inversa e remove a linha do catalogo ANTES de
restaurar o `CHECK` antigo -- restaurar primeiro falharia a validacao da
constraint contra a propria linha que esta migration inseriu.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from alembic import op

revision: str = "0005_role_suporte_bypassrls"
down_revision: str | None = "0004_role_login_app"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLE_SUPORTE = "ponto_app_suporte"

#: Tabelas (e privilegios) que a role de suporte recebe -- a lista INTEIRA.
#: Qualquer acrescimo aqui aumenta o alcance de uma credencial com BYPASSRLS:
#: nao mexa sem revisao humana explicita.
_GRANTS: tuple[tuple[str, str], ...] = (
    ("tenants", "SELECT, INSERT"),
    ("auditoria", "SELECT, INSERT"),
)

#: So usado quando POSTGRES_SUPORTE_PASSWORD nao esta definida. Publico e
#: documentado de proposito -- mesmo espirito de `_SENHA_PADRAO_DEV` em
#: `0004_role_login_app`: um fallback escondido pareceria seguranca onde nao ha.
_SENHA_PADRAO_DEV = "ponto-suporte-dev-nao-use-em-producao"

_ACOES_ANTES = (
    "'ler','criar','editar','excluir','aprovar','exportar','executar',"
    "'assinar','administrar','configurar','reabrir','ler_sensivel'"
)
_ACOES_DEPOIS = _ACOES_ANTES + ",'suporte'"

_CODIGO_PERMISSAO = "tenants.suporte"


def _senha_escapada() -> str:
    senha = os.environ.get("POSTGRES_SUPORTE_PASSWORD", _SENHA_PADRAO_DEV)
    # Escape de literal SQL (dobra aspas simples): o valor vem do operador da
    # migration, nunca de requisicao HTTP, mas nunca e interpolado sem escape.
    return senha.replace("'", "''")


def _sql_role(criar: bool) -> str:
    """Bloco `DO $$` que cria/atualiza (ou desativa) a role de suporte.

    Supressao de S608 abaixo justificada: `_ROLE_SUPORTE` e constante Python
    fixa neste modulo (nunca vem de requisicao HTTP nem de input externo) e a
    senha passa por `_senha_escapada()` antes de entrar na string -- mesmo
    padrao ja usado em `0004_role_login_app.py`.
    """
    if criar:
        # LOGIN e BYPASSRLS explicitos no ramo ELSE (nao so a senha): um
        # downgrade anterior deixa a role NOLOGIN NOBYPASSRLS, e o upgrade
        # precisa restaurar os tres atributos, nunca so um deles.
        acao = (
            f"IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_ROLE_SUPORTE}') THEN "  # noqa: S608
            f"EXECUTE 'CREATE ROLE {_ROLE_SUPORTE} LOGIN BYPASSRLS "
            f"PASSWORD ''{_senha_escapada()}'''; "
            f"ELSE "
            f"EXECUTE 'ALTER ROLE {_ROLE_SUPORTE} LOGIN BYPASSRLS "
            f"PASSWORD ''{_senha_escapada()}'''; "
            f"END IF;"
        )
        aviso = (
            f"Sem privilegio para criar/alterar {_ROLE_SUPORTE}. Crie manualmente "
            f"(ver infra/): LOGIN, BYPASSRLS, SEM membership em ponto_app."
        )
    else:
        acao = (
            f"IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_ROLE_SUPORTE}') THEN "  # noqa: S608
            f"EXECUTE 'ALTER ROLE {_ROLE_SUPORTE} NOLOGIN NOBYPASSRLS'; "
            f"END IF;"
        )
        aviso = f"Sem privilegio para alterar {_ROLE_SUPORTE}."
    return f"""
        DO $$
        BEGIN
            {acao}
        EXCEPTION
            WHEN insufficient_privilege THEN
                RAISE NOTICE '{aviso}';
        END $$
        """


def _sql_grants(conceder: bool) -> str:
    linhas = []
    for tabela, privilegios in _GRANTS:
        if conceder:
            linhas.append(f"EXECUTE 'GRANT {privilegios} ON {tabela} TO {_ROLE_SUPORTE}';")
        else:
            linhas.append(f"EXECUTE 'REVOKE {privilegios} ON {tabela} FROM {_ROLE_SUPORTE}';")
    if conceder:
        linhas.insert(0, f"EXECUTE 'GRANT USAGE ON SCHEMA public TO {_ROLE_SUPORTE}';")
    else:
        linhas.append(f"EXECUTE 'REVOKE USAGE ON SCHEMA public FROM {_ROLE_SUPORTE}';")
    corpo = "\n            ".join(linhas)
    # Supressao de S608: mesma justificativa de `_sql_role` acima -- so
    # constantes/valores fixos deste modulo entram no literal SQL.
    return f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_ROLE_SUPORTE}') THEN
            {corpo}
            END IF;
        EXCEPTION
            WHEN insufficient_privilege THEN
                RAISE NOTICE 'Sem privilegio para ajustar os GRANTs de {_ROLE_SUPORTE}.';
        END $$
        """  # noqa: S608


def upgrade() -> None:
    op.execute(_sql_role(criar=True))
    op.execute(_sql_grants(conceder=True))

    # --- acao `suporte` no CHECK do catalogo de permissoes -------------------
    op.execute("ALTER TABLE permissoes DROP CONSTRAINT IF EXISTS permissoes_acao_check")
    op.execute(
        f"ALTER TABLE permissoes ADD CONSTRAINT permissoes_acao_check "
        f"CHECK (acao IN ({_ACOES_DEPOIS}))"
    )

    # --- a permissao em si (catalogo global, idempotente) -------------------
    op.execute(
        f"""
        INSERT INTO permissoes (codigo, recurso, acao, descricao, sensivel, modulo)
        VALUES (
            '{_CODIGO_PERMISSAO}', 'tenants', 'suporte',
            'Acesso CROSS-tenant do suporte da SEEG a listagem e criacao de tenants '
            '(bypass de RLS via role ponto_app_suporte). Nunca conceder a perfil de '
            'tenant cliente.',
            TRUE, 'tenancy'
        )
        ON CONFLICT (codigo) DO NOTHING
        """  # noqa: S608
    )


def downgrade() -> None:
    # Ordem inversa. A linha do catalogo sai ANTES do CHECK voltar ao conjunto
    # antigo: o Postgres valida a constraint nova contra as linhas existentes,
    # e `acao = 'suporte'` violaria o CHECK restaurado.
    op.execute(f"DELETE FROM permissoes WHERE codigo = '{_CODIGO_PERMISSAO}'")  # noqa: S608
    op.execute("ALTER TABLE permissoes DROP CONSTRAINT IF EXISTS permissoes_acao_check")
    op.execute(
        f"ALTER TABLE permissoes ADD CONSTRAINT permissoes_acao_check "
        f"CHECK (acao IN ({_ACOES_ANTES}))"
    )
    op.execute(_sql_grants(conceder=False))
    op.execute(_sql_role(criar=False))
