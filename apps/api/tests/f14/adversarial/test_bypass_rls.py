"""F14/A4 -- vetor 5: bypass de RLS por consulta direta ou funcao SECURITY
DEFINER mal escopada.

## O achado central desta suite

`ADR-001` regra 4 e uma frase curta e absoluta: **"A aplicacao conecta com
uma role SEM `BYPASSRLS`. Migrations e rotinas de plataforma usam outra
role, com credencial separada."** Toda a arquitetura de isolamento
multi-tenant do sistema (RLS forcada em toda tabela `tenant_id`, auditada
estruturalmente por `tests/f1/tenancy/test_catalogo_rls.py` e de novo por
`tests/f14/hardening/test_auditoria_rls.py`) depende desta unica premissa:
que a conexao de banco que a API/worker usam EM PRODUCAO nao e a mesma
conexao administrativa usada para migrar o schema.

Lendo `infra/docker-compose.yml` (nao codigo Python -- infraestrutura
declarada, a fonte de verdade de como o sistema roda de fato):

```yaml
x-python-env: &python-env
  ...
  DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:?defina POSTGRES_USER}:
    ${POSTGRES_PASSWORD:?defina POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:?defina POSTGRES_DB}
  ...
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER:?defina POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?defina POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB:?defina POSTGRES_DB}
```

`x-python-env` e o bloco de ambiente comum a `api`, `worker`, `scheduler` e
`device-gw` (confirmar por `grep -n "python-env" infra/docker-compose.yml`).
`POSTGRES_USER` e a MESMA variavel usada para o bootstrap do container
`postgres` oficial -- e a imagem `postgres:16-alpine` SEMPRE cria esse nome
como role SUPERUSUARIO (e assim que a imagem oficial do Postgres funciona,
nao ha flag para mudar isso). Ou seja: **o `DATABASE_URL` que a aplicacao usa
em producao e o mesmo usuario administrativo que criou o banco.**

Superusuario do PostgreSQL **nunca** e sujeito a Row Level Security, mesmo
com `FORCE ROW LEVEL SECURITY` na tabela (documentacao oficial do Postgres:
"the table owner is normally exempt from row security policies... row
security is always applied for superusers" -- na verdade e o INVERSO: RLS
**nunca** se aplica a superusuario, ponto final, `FORCE` inclusive). Isto
nao e uma configuracao de policy incorreta -- as policies em si estao
perfeitas (ver `test_confirmacao_policies_sao_identicas_ao_padrao_correto`
abaixo). E uma ausencia total de separacao de credencial entre "role de
migracao" e "role de aplicacao", o requisito EXPLICITO da regra 4 do ADR-001.

`grep -rln "ponto_app" infra/` (rodado antes de escrever este arquivo)
devolve ZERO arquivos -- nenhum lugar em `infra/` cria ou usa a role
`ponto_app` (criada `NOLOGIN` por `0001_inicial`, pensada para ser herdada
por uma role de LOGIN separada, exatamente como
`tests/f1/conftest.py`/`tests/f14/lgpd/conftest.py` fazem para os PROPRIOS
testes). O `row_security=on` que `postgres.command` define no compose
tambem nao ajuda aqui: aquela flag so impede a APLICACAO de desligar RLS
para si mesma via `SET row_security = off` -- irrelevante para uma role que
ja e superusuario e nunca passa pela checagem de RLS.

## O que este arquivo prova, de forma reproduzivel

1. `test_confirmacao_policies_sao_identicas_ao_padrao_correto`: a policy
   `pol_isolamento_tenant` das tabelas testadas esta ESCRITA corretamente
   (mesma expressao usada em toda tabela do sistema desde F1) -- elimina a
   hipotese "a policy tem um bug".
2. `test_rls_isola_tenants_quando_conectado_pela_role_correta_sem_bypassrls`:
   conectando pela role que o `ponto_app` (`NOLOGIN`, GRANT-avel) representa
   -- exatamente como ADR-001 regra 4 manda -- RLS FUNCIONA, isolamento
   perfeito. Confirma que a arquitetura, ONDE CORRETAMENTE ligada, cumpre a
   promessa.
3. `test_mesma_query_vaza_cross_tenant_quando_conectado_como_o_role_de_producao`:
   a MESMA consulta, os MESMOS dados, conectando com o role/credencial que
   `infra/docker-compose.yml` efetivamente entrega para `DATABASE_URL` da
   aplicacao (`POSTGRES_USER`, superusuario por construcao da imagem oficial)
   -- vaza cross-tenant. Isto reproduz, no melhor grau possivel sem subir o
   compose completo, o comportamento real de producao tal como configurado
   HOJE no repositorio.
4. `test_security_definer_cross_tenant_nao_e_alcancavel_por_rota_http`: as
   quatro funcoes `SECURITY DEFINER` que deliberadamente atravessam tenants
   (`fn_resolve_tenant`, `fn_tenants_ativos`, `fn_terminais_para_verificacao_
   saude`, `fn_bh_contas_para_verificacao_vencimento`) sao code-audited: NENHUM
   router HTTP as chama -- so `apps/worker/**` e os pontos de bootstrap de
   tenant documentados. Isto quer dizer que, MESMO com o achado 1-3 acima
   (RLS inerte na conexao de producao), a superficie CONCRETA de exploracao
   hoje continua sendo "qualquer consulta sem filtro explicito de
   `tenant_id`" -- nao uma SECURITY DEFINER adicional mal escopada.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.seguranca import Sujeito
from app.marcacao.pipeline import ingestao
from app.schemas import contrato
from tests.f14.adversarial.conftest import (
    GEOCERCA_LATITUDE,
    GEOCERCA_LONGITUDE,
    ContextoDoisTenants,
    ContextoTenant,
    aplicar_tenant_teste,
    gerar_idempotency_key,
)

RAIZ_REPO = Path(__file__).resolve().parents[5]


async def _registrar_marcacao_valida(
    sessao: AsyncSession, contexto: ContextoTenant
) -> contrato.MarcacaoCriada:
    """Registra uma marcacao REAL (nunca uma linha `marcacoes_meta` forjada a
    mao): `marcacoes_meta.marcacao_id` tem FK composta para `marcacoes (id,
    datahora_marcacao)` -- so o pipeline de verdade produz um par valido."""
    corpo = contrato.MarcacaoCriar.model_validate(
        {
            "colaboradorId": str(contexto.colaborador_id),
            "empresaId": str(contexto.empresa_id),
            "unidadeId": str(contexto.unidade_id),
            "canal": "mobile",
            "dispositivoId": str(contexto.dispositivo_id),
            "latitude": GEOCERCA_LATITUDE,
            "longitude": GEOCERCA_LONGITUDE,
            "precisaoMetros": 5.0,
        }
    )
    resultado = await ingestao.registrar_marcacao(
        sessao,
        tenant_id=contexto.tenant_id,
        corpo=corpo,
        idempotency_key=gerar_idempotency_key(),
        sujeito=Sujeito(
            usuario_id=contexto.usuario_id,
            tenant_id=contexto.tenant_id,
            autenticado=True,
            permissoes=frozenset({"marcacoes.criar"}),
        ),
        ip_origem="203.0.113.50",
    )
    return resultado.resposta


# -----------------------------------------------------------------------------
# 1. As policies em si estao corretas (elimina a hipotese "bug de policy")
# -----------------------------------------------------------------------------
async def test_confirmacao_policies_sao_identicas_ao_padrao_correto(
    sessao_f14a4: AsyncSession,
) -> None:
    linhas = (
        await sessao_f14a4.execute(
            text(
                "SELECT tablename, qual, with_check FROM pg_policies "
                "WHERE policyname = 'pol_isolamento_tenant' "
                "AND tablename IN ('marcacoes_meta', 'biometria_templates', "
                "                  'consentimentos', 'solicitacoes_titular', "
                "                  'acessos_dados_sensiveis')"
            )
        )
    ).all()
    esperado = (
        "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
    )
    assert len(linhas) == 5, f"esperava 5 tabelas com a policy, achei {len(linhas)}"
    for tabela, qual, with_check in linhas:
        assert qual == esperado, f"{tabela}: USING inesperado: {qual}"
        assert with_check == esperado, f"{tabela}: WITH CHECK inesperado: {with_check}"


# -----------------------------------------------------------------------------
# 2. RLS funciona quando a conexao segue ADR-001 regra 4 (role sem BYPASSRLS)
# -----------------------------------------------------------------------------
async def test_rls_isola_tenants_quando_conectado_pela_role_correta_sem_bypassrls(
    sessao_f14a4: AsyncSession,
    sessao_role_f14a4: AsyncSession,
    contexto_dois_tenants: ContextoDoisTenants,
) -> None:
    tenant_a = contexto_dois_tenants.tenant_a
    tenant_b = contexto_dois_tenants.tenant_b

    await aplicar_tenant_teste(sessao_f14a4, tenant_b.tenant_id)
    resposta_b = await _registrar_marcacao_valida(sessao_f14a4, tenant_b)
    marcacao_meta_id_b = resposta_b.marcacao.id
    assert marcacao_meta_id_b is not None
    await sessao_f14a4.commit()

    await aplicar_tenant_teste(sessao_role_f14a4, tenant_a.tenant_id)
    linha = (
        await sessao_role_f14a4.execute(
            text("SELECT marcacao_id FROM marcacoes_meta WHERE marcacao_id = :id"),
            {"id": str(marcacao_meta_id_b)},
        )
    ).first()
    assert linha is None, (
        "Se isto falhar, a role sem BYPASSRLS deixou de estar corretamente "
        "provisionada (ver conftest) -- os achados 3/4 abaixo perderiam a "
        "base de comparacao."
    )

    # E o proprio tenant continua vendo a propria linha (RLS nao fecha tudo).
    await aplicar_tenant_teste(sessao_role_f14a4, tenant_b.tenant_id)
    linha_propria = (
        await sessao_role_f14a4.execute(
            text("SELECT marcacao_id FROM marcacoes_meta WHERE marcacao_id = :id"),
            {"id": str(marcacao_meta_id_b)},
        )
    ).first()
    assert linha_propria is not None


# -----------------------------------------------------------------------------
# 3. O ACHADO: a mesma consulta vaza cross-tenant com o role que producao usa
# -----------------------------------------------------------------------------
async def test_mesma_query_vaza_cross_tenant_quando_conectado_como_o_role_de_producao(
    sessao_f14a4: AsyncSession,
    contexto_dois_tenants: ContextoDoisTenants,
) -> None:
    """`sessao_f14a4` conecta com a MESMA credencial que
    `PONTO_TEST_DATABASE_URL` fornece (usuario `ponto`) -- por construcao da
    imagem oficial `postgres:16-alpine`, e o EXATO papel que `POSTGRES_USER`
    assume no `docker-compose.yml` de producao, herdado sem alteracao pelo
    `DATABASE_URL` de `x-python-env` (bloco usado por `api`, `worker`,
    `scheduler`, `device-gw`). Primeiro confirma que a role corrente e de
    fato superusuario/BYPASSRLS (documenta a premissa, nao assume), depois
    prova o vazamento com a MESMA query do teste anterior."""
    rolsuper, rolbypassrls = (
        await sessao_f14a4.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles " "WHERE rolname = current_user")
        )
    ).one()
    assert rolsuper or rolbypassrls, (
        "Premissa do achado nao se sustenta neste ambiente: a role de "
        "PONTO_TEST_DATABASE_URL nao e superusuario/BYPASSRLS aqui -- "
        "revisar o texto deste teste antes de reportar o achado."
    )

    tenant_a = contexto_dois_tenants.tenant_a
    tenant_b = contexto_dois_tenants.tenant_b

    await aplicar_tenant_teste(sessao_f14a4, tenant_b.tenant_id)
    resposta_b = await _registrar_marcacao_valida(sessao_f14a4, tenant_b)
    marcacao_meta_id_b = resposta_b.marcacao.id
    assert marcacao_meta_id_b is not None

    await aplicar_tenant_teste(sessao_f14a4, tenant_a.tenant_id)
    linha = (
        await sessao_f14a4.execute(
            text("SELECT marcacao_id FROM marcacoes_meta WHERE marcacao_id = :id"),
            {"id": str(marcacao_meta_id_b)},
        )
    ).first()
    assert linha is not None, (
        "Esperava reproduzir o vazamento (achado real) -- se isto falhar, "
        "ou a role deixou de ser superusuario/BYPASSRLS neste ambiente, ou "
        "o achado foi corrigido em producao (docker-compose.yml passou a "
        "usar credencial separada, ADR-001 regra 4)."
    )


def test_docker_compose_separa_credencial_de_app_da_credencial_administrativa() -> None:
    """Regressao do achado original (F14/A4, corrigido no mesmo fechamento):
    `DATABASE_URL` do bloco `x-python-env` (compartilhado por api/worker/
    scheduler/device-gw) usava `POSTGRES_USER`/`POSTGRES_PASSWORD` -- as
    MESMAS variaveis que provisionam a role administrativa do container
    `postgres`, violando ADR-001 regra 4. Corrigido: `DATABASE_URL` agora usa
    `ponto_app_runtime` (role de LOGIN sem BYPASSRLS, criada pela migration
    `0004_role_login_app`), nunca mais `POSTGRES_USER`. NAO se chama
    `ponto_app_login`: esse nome ja pertence a uma role de teste isolada em
    `tests/f1/rbac/conftest.py`, com senha propria -- reusa-lo quebraria a
    suite de RBAC/RLS de F1 sobrescrevendo a senha esperada (achado real,
    encontrado rodando a regressao apos a primeira versao desta correcao).
    Prova estatica (le o arquivo de infraestrutura de verdade, nao infere).
    `test_mesma_query_vaza_cross_tenant_quando_conectado_como_o_role_de_
    producao` (mesmo arquivo) continua deliberadamente conectando com a
    credencial superusuario -- documenta que ESSA credencial especifica
    sempre vaza, independente do fix aqui (POSTGRES_USER continua superuser
    por construcao da imagem oficial do Postgres); o fix e a aplicacao ter
    PARADO de usar essa credencial, nao a credencial ter deixado de ser
    perigosa.
    """
    caminho_compose = RAIZ_REPO / "infra" / "docker-compose.yml"
    assert caminho_compose.is_file(), f"arquivo nao encontrado: {caminho_compose}"
    conteudo = caminho_compose.read_text(encoding="utf-8").replace("\r\n", "\n")

    assert "ponto_app_runtime" in conteudo, (
        "A role de LOGIN de privilegio minimo deveria estar referenciada em "
        "infra/docker-compose.yml -- se isto falhar, o achado original "
        "voltou a existir."
    )
    assert (
        "DATABASE_URL: postgresql+asyncpg://ponto_app_runtime:${POSTGRES_APP_PASSWORD" in conteudo
    ), (
        "DATABASE_URL dos servicos api/worker/scheduler/device-gw deveria "
        "usar ponto_app_runtime, nunca POSTGRES_USER (a credencial "
        "administrativa) -- RLS nao se aplica a superusuario (ADR-001)."
    )


# -----------------------------------------------------------------------------
# 4. SECURITY DEFINER cross-tenant: auditoria estatica de alcancabilidade HTTP
# -----------------------------------------------------------------------------
_FUNCOES_SECURITY_DEFINER_CROSS_TENANT = (
    "fn_resolve_tenant",
    "fn_resolve_terminal",
    "fn_tenants_ativos",
    "fn_terminais_para_verificacao_saude",
    "fn_bh_contas_para_verificacao_vencimento",
)


def test_security_definer_cross_tenant_nao_e_alcancavel_por_rota_http() -> None:
    """Para cada funcao `SECURITY DEFINER` que deliberadamente atravessa
    tenants (todas documentadas em `schema.sql`, RFC-004/009/010/013/014),
    confirma por grep que NENHUMA chamada existe em `apps/api/app/routers/**`
    -- a unica superficie que um usuario autenticado (nao superusuario de
    banco) conseguiria acionar. Chamadas legitimas ficam confinadas a
    `apps/worker/**` (cron sem tenant) e `apps/api/app/identidade/**`/
    `apps/api/app/integracoes/sandbox/**` (bootstrap de tenant, ANTES de
    qualquer sessao de usuario existir)."""
    raiz_api = RAIZ_REPO / "apps" / "api" / "app"
    raiz_routers = raiz_api / "routers"
    assert raiz_routers.is_dir()

    arquivos_routers = list(raiz_routers.rglob("*.py"))
    assert arquivos_routers, "nenhum router encontrado -- caminho errado?"

    achados: list[str] = []
    for funcao in _FUNCOES_SECURITY_DEFINER_CROSS_TENANT:
        for arquivo in arquivos_routers:
            texto = arquivo.read_text(encoding="utf-8")
            if funcao in texto:
                achados.append(f"{funcao} referenciada em {arquivo.relative_to(RAIZ_REPO)}")

    assert achados == [], (
        "VULNERAVEL se nao vazio: uma funcao SECURITY DEFINER cross-tenant "
        f"e referenciada direto por um router HTTP: {achados}"
    )
