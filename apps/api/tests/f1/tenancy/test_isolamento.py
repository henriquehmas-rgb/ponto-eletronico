"""T3 -- prova de isolamento entre tenants (criterio central da fase).

Autenticado (ou apenas com o tenant resolvido) no tenant A, tentar ler dado do
tenant B por TRES caminhos, nenhum deles devolvendo dado do tenant B:

(a) pela API, informando o id de um recurso do tenant B;
(b) por consulta ORM SEM filtro explicito de tenant_id;
(c) por SQL DIRETO (`text("SELECT ... FROM <tabela>")`) na mesma sessao,
    repetido para uma amostra de pelo menos 10 tabelas de dominio distintas.

Critério de aceite 1 do PCF. A cobertura de RLS por catalogo (critério 2) esta
em `test_catalogo_rls.py`; a prova de que a policy, se removida, faz este
arquivo FALHAR esta documentada (nao automatizada -- o PCF pede uma prova
unica, colada no relatorio) em `docs/fases/F01-A2-prova-quebra-policy.md`.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from ponto_contracts import Usuario
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.f1.conftest import AbrirSessaoTenant, ContextoF1, cabecalhos

MEDIA_TYPE_PROBLEMA = "application/problem+json"

#: >= 10 tabelas de dominio distintas, todas semeadas para os dois tenants
#: por `_semear_tenant` (ver `tests/f1/conftest.py:TenantSemeado.ids_por_tabela`).
TABELAS_DE_DOMINIO = (
    "usuarios",
    "credenciais",
    "sessoes",
    "mfa_dispositivos",
    "perfis",
    "perfil_permissoes",
    "usuario_perfis",
    "delegacoes",
    "empresas",
    "unidades",
    "departamentos",
    "tenant_configuracoes",
)


def test_lista_de_tabelas_cobre_pelo_menos_dez(contexto_f1: ContextoF1) -> None:
    """Guarda de sanidade do proprio teste: se alguem reduzir a lista abaixo
    de 10 tabelas, o PCF (T3) deixa de estar satisfeito -- falhar aqui e mais
    claro do que falhar silenciosamente por engano na contagem."""
    assert len(TABELAS_DE_DOMINIO) >= 10
    ids_a = contexto_f1.tenant_a.ids_por_tabela()
    ids_b = contexto_f1.tenant_b.ids_por_tabela()
    assert set(TABELAS_DE_DOMINIO) <= set(ids_a) == set(ids_b)


# -----------------------------------------------------------------------------
# (c) SQL DIRETO, em pelo menos 10 tabelas
# -----------------------------------------------------------------------------
async def test_sql_direto_nao_ve_linha_do_outro_tenant_em_10_tabelas(
    contexto_f1: ContextoF1, abrir_sessao_tenant: AbrirSessaoTenant
) -> None:
    """Conectado como tenant A (role `ponto_app`, sem BYPASSRLS), buscar pela
    CHAVE PRIMARIA de uma linha que existe -- mas pertence ao tenant B -- em
    cada uma das tabelas. RLS filtra por `tenant_id`, nao pela PK: se a
    policy estiver correta, a linha e invisivel mesmo sabendo o id exato."""
    ids_b = contexto_f1.tenant_b.ids_por_tabela()

    async with abrir_sessao_tenant(contexto_f1.tenant_a.id) as sessao:
        vazamentos: list[str] = []
        for tabela in TABELAS_DE_DOMINIO:
            linha = (
                await sessao.execute(
                    text(f"SELECT id FROM {tabela} WHERE id = :id"),  # noqa: S608
                    {"id": str(ids_b[tabela])},
                )
            ).first()
            if linha is not None:
                vazamentos.append(tabela)
        assert vazamentos == [], f"tenant A enxergou linha do tenant B em: {vazamentos}"


async def test_sql_direto_so_ve_as_proprias_linhas_por_tabela(
    contexto_f1: ContextoF1, abrir_sessao_tenant: AbrirSessaoTenant
) -> None:
    """Complemento do teste acima: nao so a linha do tenant B e invisivel --
    a linha do PROPRIO tenant A continua visivel (RLS nao esta fechando tudo
    por engano, so o que nao pertence ao tenant corrente)."""
    ids_a = contexto_f1.tenant_a.ids_por_tabela()

    async with abrir_sessao_tenant(contexto_f1.tenant_a.id) as sessao:
        ausentes: list[str] = []
        for tabela in TABELAS_DE_DOMINIO:
            linha = (
                await sessao.execute(
                    text(f"SELECT id FROM {tabela} WHERE id = :id"),  # noqa: S608
                    {"id": str(ids_a[tabela])},
                )
            ).first()
            if linha is None:
                ausentes.append(tabela)
        assert ausentes == [], f"tenant A deixou de ver a PROPRIA linha em: {ausentes}"


async def test_sql_direto_sem_filtro_de_tenant_id_devolve_so_o_proprio_tenant(
    contexto_f1: ContextoF1, abrir_sessao_tenant: AbrirSessaoTenant
) -> None:
    """`SELECT * FROM usuarios` (sem NENHUM WHERE) conectado como tenant A: a
    policy filtra sozinha. Nenhuma linha de tenant_id != tenant_a.id pode
    aparecer, nem por acidente de um SELECT completo."""
    async with abrir_sessao_tenant(contexto_f1.tenant_a.id) as sessao:
        linhas = (await sessao.execute(text("SELECT tenant_id FROM usuarios"))).scalars().all()
        assert linhas, "esperava ao menos os usuarios do proprio tenant A"
        assert all(str(tid) == str(contexto_f1.tenant_a.id) for tid in linhas)


# -----------------------------------------------------------------------------
# (b) ORM SEM filtro explicito de tenant_id
# -----------------------------------------------------------------------------
async def test_orm_sem_filtro_explicito_nao_ve_usuario_do_outro_tenant(
    contexto_f1: ContextoF1, abrir_sessao_tenant: AbrirSessaoTenant
) -> None:
    async with abrir_sessao_tenant(contexto_f1.tenant_a.id) as sessao:
        todos = (await sessao.execute(sa.select(Usuario))).scalars().all()
        ids_vistos = {u.id for u in todos}

    assert contexto_f1.tenant_b.admin.id not in ids_vistos
    assert contexto_f1.tenant_b.colaborador.id not in ids_vistos
    assert contexto_f1.tenant_a.admin.id in ids_vistos


async def test_orm_filtrar_por_email_do_outro_tenant_devolve_vazio(
    contexto_f1: ContextoF1, abrir_sessao_tenant: AbrirSessaoTenant
) -> None:
    """Mesmo com um filtro de aplicacao explicito (mas SEM `tenant_id`) que
    deveria bater exatamente com o usuario do tenant B, a RLS ainda nega:
    defesa em profundidade, nao dependente de ninguem esquecer o `WHERE`."""
    async with abrir_sessao_tenant(contexto_f1.tenant_a.id) as sessao:
        consulta = sa.select(Usuario).where(Usuario.email == contexto_f1.tenant_b.admin.email)
        resultado = (await sessao.execute(consulta)).scalar_one_or_none()
        assert resultado is None


# -----------------------------------------------------------------------------
# (a) Pela API, informando o id de um recurso do tenant B
# -----------------------------------------------------------------------------
def test_api_obter_tenant_de_outro_tenant_nao_vaza_dado(
    cliente: TestClient, contexto_f1: ContextoF1
) -> None:
    """Autenticado (resolvido) no tenant A, pedir `GET /v1/tenants/{tenantId}`
    informando o id do tenant B. `_exigir_mesmo_tenant`
    (`app/routers/tenants.py`) recusa explicitamente com `PONTO-TEN-004`
    ANTES de consultar o banco -- e a RLS barraria de qualquer forma."""
    resposta = cliente.get(
        f"/v1/tenants/{contexto_f1.tenant_b.id}",
        headers=cabecalhos(contexto_f1.tenant_a.slug),
    )
    assert resposta.status_code in (403, 404)
    assert resposta.headers["content-type"].startswith(MEDIA_TYPE_PROBLEMA)
    assert resposta.json()["codigo"] in ("PONTO-TEN-004", "PONTO-REC-001")
    # Nunca o corpo do tenant B, seja qual for o codigo de erro escolhido.
    assert "nomeExibicao" not in resposta.json()


def test_api_obter_tenant_atual_nunca_devolve_dado_do_outro_tenant(
    cliente: TestClient, contexto_f1: ContextoF1
) -> None:
    """`obterTenantAtual` roda `SELECT * FROM tenants` sem NENHUM filtro no
    codigo -- a RLS (policy por `id`, a excecao documentada da tabela
    `tenants`) e a UNICA coisa restringindo a resposta a linha certa."""
    resposta_a = cliente.get("/v1/tenants/atual", headers=cabecalhos(contexto_f1.tenant_a.slug))
    resposta_b = cliente.get("/v1/tenants/atual", headers=cabecalhos(contexto_f1.tenant_b.slug))

    assert resposta_a.status_code == 200
    assert resposta_b.status_code == 200
    assert resposta_a.json()["id"] == str(contexto_f1.tenant_a.id)
    assert resposta_b.json()["id"] == str(contexto_f1.tenant_b.id)
    assert resposta_a.json()["id"] != resposta_b.json()["id"]


def test_api_atualizar_tenant_de_outro_tenant_e_recusado_sem_escrever(
    cliente: TestClient, contexto_f1: ContextoF1
) -> None:
    """Tentativa de ESCRITA cross-tenant (nao so leitura): tambem barrada
    antes de qualquer `UPDATE` chegar ao banco."""
    resposta = cliente.patch(
        f"/v1/tenants/{contexto_f1.tenant_b.id}",
        json={"nomeExibicao": "Nome adulterado pelo tenant A"},
        headers={
            **cabecalhos(contexto_f1.tenant_a.slug),
            "Idempotency-Key": f"teste-escrita-cross-tenant-{uuid.uuid4()}",
        },
    )
    assert resposta.status_code in (403, 404)
    assert resposta.json()["codigo"] in ("PONTO-TEN-004", "PONTO-REC-001")

    # Confirma que o nome do tenant B genuinamente nao mudou.
    resposta_b = cliente.get("/v1/tenants/atual", headers=cabecalhos(contexto_f1.tenant_b.slug))
    assert resposta_b.json()["nomeExibicao"] == contexto_f1.tenant_b.nome_exibicao


# -----------------------------------------------------------------------------
# Reforco: escrita cross-tenant tambem e barrada pela policy WITH CHECK,
# nao so pela leitura (USING). Prova que INSERT/UPDATE fora do tenant
# corrente e rejeitado pelo proprio Postgres, nao so pelo filtro de aplicacao.
# -----------------------------------------------------------------------------
async def test_insert_com_tenant_id_de_outro_tenant_e_rejeitado_pela_policy(
    contexto_f1: ContextoF1, abrir_sessao_tenant: AbrirSessaoTenant
) -> None:
    """Conectado (SET LOCAL) como tenant A, tentar INSERIR uma linha em
    `tenant_configuracoes` com `tenant_id` do tenant B. A policy `WITH CHECK`
    rejeita antes mesmo de existir chance de o dado ficar orfao/inconsistente."""
    async with abrir_sessao_tenant(contexto_f1.tenant_a.id) as sessao:
        with pytest.raises(DBAPIError) as excinfo:
            await sessao.execute(
                text(
                    "INSERT INTO tenant_configuracoes (tenant_id, categoria, chave, valor) "
                    "VALUES (:tenant_id, 'geral', 'ataque.cross.tenant', '{}'::jsonb)"
                ),
                {"tenant_id": str(contexto_f1.tenant_b.id)},
            )
            await sessao.commit()
        assert "row-level security" in str(excinfo.value).lower()
