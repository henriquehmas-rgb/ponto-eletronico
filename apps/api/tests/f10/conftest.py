"""Fixture compartilhada da fase F10 (T1, ownership exclusivo de A1 -- PCF
§5, linha "`apps/api/tests/f10/conftest.py`"). Todos os demais agentes da
fase (A2, A3, A4) **usam** esta fixture; não a editam -- se precisarem de um
dado a mais, pedem no relatório em vez de editar aqui (mesma regra de
convivência que `tests/f3/conftest.py` já estabeleceu para aquela fase).

Mesma FORMA de bootstrap já estabelecida por `tests/f3/conftest.py` e
`tests/f4/tratamento/conftest.py` (migração + role de LOGIN derivada do nome
do banco de `PONTO_TEST_DATABASE_URL` + sessão por teste sob RLS, nunca
superusuário): cada agente desta fase roda contra seu próprio banco
exclusivo (`ponto_f10_a1`, `ponto_f10_a2`, `ponto_f10_a3`, `ponto_f10_a4`),
e o nome da role deriva do banco para não colidir entre agentes rodando em
paralelo contra o mesmo cluster.

O que esta fixture entrega, por teste (`contexto_f10`, escopo `function` --
cada teste semeia seu PRÓPRIO tenant, nunca reaproveita nem limpa dado de
outro teste):

* 1 tenant, 1 empresa, 1 unidade.
* 1 colaborador com vínculo `apura_ponto=true`, `status='ativo'`.
* 3 usuários: o do próprio colaborador (solicitante), um "gestor" e um "rh"
  -- nenhum RBAC real é semeado aqui (não é escopo de F10; a fila de
  aprovação desta fase é resolvida por `aprovacoes.aprovador_usuario_id`,
  nunca por perfil/permissão), são só os `usuarios.id` que os testes usam
  como autor da decisão.
* 1 jornada SIMPLES fixa (`tipo='fixa'`), 08:00-17:00 com 1h de intervalo
  (480 min de carga líquida), útil de segunda a sexta, DSR no domingo e
  folga no sábado -- atribuída ao vínculo via `vinculo_jornadas` desde
  `2020-01-01`, sem fim de vigência. O suficiente para
  `app.jornada.resolvedor.servico.resolver_jornada_do_dia` (F3, consumido
  read-only por `app.workflow.solicitacoes.afastamentos`, A4) resolver um
  dia útil de verdade sem precisar de escala/turno.
* 1 `TipoTratamento` de exemplo (`codigo` único por execução, categoria
  `inclusao_marcacao`, mesmos parâmetros de `inclusao_manual` de
  `seed_dev.py::TIPOS_TRATAMENTO` -- reaproveita a FORMA/convenção do dado
  de fábrica, nunca a linha em si, porque o tenant desta fixture é sempre
  novo e RLS-isolado do tenant de `seed_dev.py`).
* 1 `TipoSolicitacao` de exemplo (`codigo` único, categoria `ajuste_ponto`,
  cadeia de duas etapas gestor→rh, `tipo_tratamento_id` apontando para o
  `TipoTratamento` acima) -- mesma forma de `seed_dev.py::TIPOS_SOLICITACAO`
  linha `ajuste_ponto`.
* 1 `TipoAfastamento` de exemplo (`codigo` único, categoria `ferias`) --
  necessário para o ramo `ferias` de A4 (`_resolver_tipo_afastamento_ferias`
  exige exatamente um tipo ativo dessa categoria por tenant).
* 1 `Periodo` aberto (`status='aberto'`, `tipo='mensal'`) cobrindo o mês
  corrente (primeiro ao último dia), para os testes de A2 e para o e2e (T15)
  que precisam de um período existente antes do fechamento.

Cada teste que precisar de tipos adicionais (outras categorias da tabela do
PCF §2.2, outros tipos de tratamento/afastamento) cria a própria linha extra
localmente, no seu módulo de teste -- esta fixture só entrega "um exemplo de
cada", como o PCF pediu, não o catálogo inteiro.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import re
import secrets
import subprocess
import sys
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import psycopg
import pytest
import pytest_asyncio
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

RAIZ_API = Path(__file__).resolve().parents[2]

#: Default de desenvolvimento local. So usado quando `PONTO_TEST_DATABASE_URL`
#: nao esta definida -- nunca aponta para banco de ambiente real.
_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto"


def _url_superusuario() -> URL:
    bruta = os.environ.get("PONTO_TEST_DATABASE_URL", _URL_PADRAO_LOCAL)
    return make_url(bruta)


def _nome_role_login(url_super: URL) -> str:
    """Deriva o nome da role de LOGIN do nome do banco -- evita colisao entre
    os quatro agentes de F10 rodando contra bancos exclusivos distintos no
    mesmo cluster (mesmo padrao de `tests/f3/conftest.py`/`tests/f4/
    tratamento/conftest.py`)."""
    base = re.sub(r"[^a-z0-9_]", "_", (url_super.database or "ponto").lower())
    return f"ponto_f10_login_{base}"


@pytest.fixture(scope="session")
def url_login_sessao_f10() -> URL:
    """Migra o banco de teste e devolve a `URL` de conexao da role de LOGIN."""
    url_super = _url_superusuario()
    role_login = _nome_role_login(url_super)

    ambiente = dict(os.environ)
    ambiente["DATABASE_URL"] = url_super.render_as_string(hide_password=False)
    resultado = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(RAIZ_API),
        env=ambiente,
        capture_output=True,
        text=True,
        check=False,
    )
    if resultado.returncode != 0:
        raise RuntimeError(
            "alembic upgrade head falhou ao preparar o banco de teste da F10:\n"
            f"--- stdout ---\n{resultado.stdout}\n--- stderr ---\n{resultado.stderr}"
        )

    senha = secrets.token_urlsafe(24)
    dsn_super = url_super.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn_super, autocommit=True) as conexao, conexao.cursor() as cursor:
        cursor.execute(sql.SQL("SELECT 1 FROM pg_roles WHERE rolname = %s"), (role_login,))
        if cursor.fetchone():
            cursor.execute(
                sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                    sql.Identifier(role_login), sql.Literal(senha)
                )
            )
        else:
            cursor.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} IN ROLE ponto_app").format(
                    sql.Identifier(role_login), sql.Literal(senha)
                )
            )

    url_login = url_super.set(drivername="postgresql+asyncpg", username=role_login, password=senha)
    dsn_login = url_login.set(drivername="postgresql").render_as_string(hide_password=False)

    ultimo_erro: Exception | None = None
    for tentativa in range(5):
        try:
            with psycopg.connect(dsn_login, connect_timeout=5):
                pass
            break
        except Exception as exc:  # pragma: no cover - so em falha real de rede
            ultimo_erro = exc
            time.sleep(0.3 * (tentativa + 1))
    else:
        raise RuntimeError(
            f"Nao foi possivel validar a role de LOGIN apos 5 tentativas: {ultimo_erro}"
        )

    return url_login


@pytest_asyncio.fixture
async def engine_f10(url_login_sessao_f10: URL) -> AsyncIterator[AsyncEngine]:
    ultimo_erro: Exception | None = None
    for tentativa in range(8):
        engine = create_async_engine(
            url_login_sessao_f10, pool_pre_ping=True, connect_args={"timeout": 8}
        )
        try:
            async with asyncio.timeout(10):
                async with engine.connect():
                    pass
        except Exception as exc:  # pragma: no cover - so em falha real de rede
            ultimo_erro = exc
            await engine.dispose()
            await asyncio.sleep(min(0.5 * (tentativa + 1), 3.0))
            continue
        try:
            yield engine
        finally:
            await engine.dispose()
        return
    raise RuntimeError(f"Nao foi possivel abrir a engine de teste da F10: {ultimo_erro}")


@pytest_asyncio.fixture
async def sessao_f10(engine_f10: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Sessao assincrona por teste. O teste decide quando commitar.

    Cuidado com `SET LOCAL` + `commit()`: `aplicar_tenant_teste` usa
    `SET LOCAL`, valido so ate o fim da transacao corrente. Commitar no meio
    do teste e continuar operando exige chamar `aplicar_tenant_teste` de
    novo (mesmo aviso de `tests/f3/conftest.py`).
    """
    fabrica = async_sessionmaker(engine_f10, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        yield sessao
        await sessao.rollback()


async def aplicar_tenant_teste(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"),
        {"tenant": str(tenant_id)},
    )


@dataclass(frozen=True, slots=True)
class ContextoF10:
    """IDs da semente mínima da fase F10, comuns aos quatro agentes."""

    tenant_id: uuid.UUID
    tenant_slug: str
    empresa_id: uuid.UUID
    unidade_id: uuid.UUID
    colaborador_id: uuid.UUID
    vinculo_id: uuid.UUID
    colaborador_usuario_id: uuid.UUID
    gestor_usuario_id: uuid.UUID
    rh_usuario_id: uuid.UUID
    horario_id: uuid.UUID
    jornada_id: uuid.UUID
    tipo_tratamento_id: uuid.UUID
    tipo_tratamento_codigo: str
    tipo_solicitacao_id: uuid.UUID
    tipo_solicitacao_codigo: str
    tipo_afastamento_ferias_id: uuid.UUID
    periodo_id: uuid.UUID
    periodo_data_inicio: dt.date
    periodo_data_fim: dt.date


@pytest_asyncio.fixture
async def contexto_f10(sessao_f10: AsyncSession) -> ContextoF10:
    """Semeia a base comum da fase (ver docstring do módulo). Cada chamada
    gera tenant, CNPJ, CPFs, matrículas e códigos novos -- nenhum teste
    compartilha semente com outro (mesma isolação de `tests/f3/conftest.py`
    e `tests/f4/tratamento/conftest.py`)."""
    sufixo = uuid.uuid4().hex[:10]
    tenant_id = uuid.uuid4()
    tenant_slug = f"f10-{sufixo}"

    await aplicar_tenant_teste(sessao_f10, tenant_id)

    await sessao_f10.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, :razao, :nome, 'ativo')"
        ),
        {
            "id": tenant_id,
            "slug": tenant_slug,
            "razao": "Tenant de teste da fase F10",
            "nome": "Tenant F10",
        },
    )

    empresa_id = uuid.uuid4()
    cnpj = f"{secrets.randbelow(10**14):014d}"
    await sessao_f10.execute(
        text(
            "INSERT INTO empresas "
            "(id, tenant_id, tipo, cnpj, razao_social, nome_fantasia, uf, "
            " codigo_ibge_municipio, fuso_horario) "
            "VALUES (:id, :tenant_id, 'matriz', :cnpj, :razao, :fantasia, 'SP', "
            "        '3550308', 'America/Sao_Paulo')"
        ),
        {
            "id": empresa_id,
            "tenant_id": tenant_id,
            "cnpj": cnpj,
            "razao": "Empresa de Teste F10 Ltda",
            "fantasia": "Empresa Teste F10",
        },
    )

    unidade_id = uuid.uuid4()
    await sessao_f10.execute(
        text(
            "INSERT INTO unidades "
            "(id, tenant_id, empresa_id, codigo, nome, tipo, uf, codigo_ibge_municipio, "
            " fuso_horario, geocerca_obrigatoria) "
            "VALUES (:id, :tenant_id, :empresa_id, 'SEDE', 'Sede de Teste', 'sede', "
            "        'SP', '3550308', 'America/Sao_Paulo', FALSE)"
        ),
        {"id": unidade_id, "tenant_id": tenant_id, "empresa_id": empresa_id},
    )

    colaborador_id = uuid.uuid4()
    cpf = f"{secrets.randbelow(10**11):011d}"
    await sessao_f10.execute(
        text(
            "INSERT INTO colaboradores "
            "(id, tenant_id, empresa_id, matricula, cpf, nome_completo, status) "
            "VALUES (:id, :tenant_id, :empresa_id, :matricula, :cpf, :nome, 'ativo')"
        ),
        {
            "id": colaborador_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "matricula": f"MAT-{sufixo}",
            "cpf": cpf,
            "nome": "Colaborador de Teste F10",
        },
    )

    vinculo_id = uuid.uuid4()
    data_inicio_vinculo = dt.date(2020, 1, 1)
    await sessao_f10.execute(
        text(
            "INSERT INTO vinculos "
            "(id, tenant_id, colaborador_id, empresa_id, unidade_id, matricula_esocial, "
            " tipo_vinculo, data_inicio, apura_ponto, principal, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :empresa_id, :unidade_id, :esocial, "
            "        'empregado', :data_inicio, TRUE, TRUE, 'ativo')"
        ),
        {
            "id": vinculo_id,
            "tenant_id": tenant_id,
            "colaborador_id": colaborador_id,
            "empresa_id": empresa_id,
            "unidade_id": unidade_id,
            "esocial": f"ESOC-{sufixo}",
            "data_inicio": data_inicio_vinculo,
        },
    )

    colaborador_usuario_id = uuid.uuid4()
    gestor_usuario_id = uuid.uuid4()
    rh_usuario_id = uuid.uuid4()
    for usuario_id, papel_rotulo, email_local in (
        (colaborador_usuario_id, "colaborador", "colaborador"),
        (gestor_usuario_id, "gestor", "gestor"),
        (rh_usuario_id, "rh", "rh"),
    ):
        await sessao_f10.execute(
            text(
                "INSERT INTO usuarios "
                "(id, tenant_id, colaborador_id, email, nome_completo, status) "
                "VALUES (:id, :tenant_id, :colaborador_id, :email, :nome, 'ativo')"
            ),
            {
                "id": usuario_id,
                "tenant_id": tenant_id,
                # so o usuario "colaborador" e a propria pessoa que bate ponto;
                # gestor/rh sao contas distintas, sem vinculo com este colaborador.
                "colaborador_id": colaborador_id if papel_rotulo == "colaborador" else None,
                "email": f"{email_local}-{sufixo}@f10.teste",
                "nome": f"Usuario {papel_rotulo.capitalize()} de Teste F10",
            },
        )

    # Jornada simples fixa: util seg-sex (08:00-17:00, 1h de intervalo, 480
    # min de carga liquida), DSR no domingo, folga no sabado.
    horario_id = uuid.uuid4()
    await sessao_f10.execute(
        text(
            "INSERT INTO horarios "
            "(id, tenant_id, empresa_id, codigo, nome, entrada, saida, intervalo_inicio, "
            " intervalo_fim, duracao_intervalo_minutos, carga_minutos, ativo) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'Horario padrao 08-17', "
            "        '08:00', '17:00', '12:00', '13:00', 60, 480, TRUE)"
        ),
        {
            "id": horario_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "codigo": f"HOR-{sufixo}",
        },
    )

    jornada_id = uuid.uuid4()
    await sessao_f10.execute(
        text(
            "INSERT INTO jornadas "
            "(id, tenant_id, empresa_id, codigo, nome, tipo, carga_diaria_minutos, "
            " carga_semanal_minutos, vigencia_inicio, ativo) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'Jornada simples de teste', "
            "        'fixa', 480, 2400, :vigencia_inicio, TRUE)"
        ),
        {
            "id": jornada_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "codigo": f"JOR-{sufixo}",
            "vigencia_inicio": data_inicio_vinculo,
        },
    )

    for dia_semana, tipo_dia, horario_do_dia, carga in (
        (0, "dsr", None, 0),
        (1, "util", horario_id, 480),
        (2, "util", horario_id, 480),
        (3, "util", horario_id, 480),
        (4, "util", horario_id, 480),
        (5, "util", horario_id, 480),
        (6, "folga", None, 0),
    ):
        await sessao_f10.execute(
            text(
                "INSERT INTO jornada_dias "
                "(id, tenant_id, jornada_id, dia_semana, tipo_dia, horario_id, carga_minutos) "
                "VALUES (:id, :tenant_id, :jornada_id, :dia_semana, :tipo_dia, :horario_id, "
                "        :carga)"
            ),
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "jornada_id": jornada_id,
                "dia_semana": dia_semana,
                "tipo_dia": tipo_dia,
                "horario_id": horario_do_dia,
                "carga": carga,
            },
        )

    await sessao_f10.execute(
        text(
            "INSERT INTO vinculo_jornadas "
            "(id, tenant_id, vinculo_id, jornada_id, vigencia_inicio) "
            "VALUES (:id, :tenant_id, :vinculo_id, :jornada_id, :vigencia_inicio)"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "vinculo_id": vinculo_id,
            "jornada_id": jornada_id,
            "vigencia_inicio": data_inicio_vinculo,
        },
    )

    # Tipo de tratamento de exemplo -- mesma forma de `seed_dev.py::
    # TIPOS_TRATAMENTO` linha `inclusao_manual` (categoria
    # `inclusao_marcacao`), tenant proprio desta fixture.
    tipo_tratamento_id = uuid.uuid4()
    tipo_tratamento_codigo = f"INCL-{sufixo}"
    await sessao_f10.execute(
        text(
            "INSERT INTO tipos_tratamento "
            "(id, tenant_id, codigo, nome, categoria, exige_aprovacao, exige_anexo, "
            " exige_motivo, permite_retroativo_dias, ativo) "
            "VALUES (:id, :tenant_id, :codigo, 'Inclusao manual de teste', "
            "        'inclusao_marcacao', TRUE, FALSE, TRUE, 60, TRUE)"
        ),
        {"id": tipo_tratamento_id, "tenant_id": tenant_id, "codigo": tipo_tratamento_codigo},
    )

    # Tipo de solicitacao de exemplo -- mesma forma de `seed_dev.py::
    # TIPOS_SOLICITACAO` linha `ajuste_ponto` (cadeia gestor -> rh),
    # apontando para o tipo de tratamento acima.
    tipo_solicitacao_id = uuid.uuid4()
    tipo_solicitacao_codigo = f"AJUSTE-{sufixo}"
    await sessao_f10.execute(
        text(
            "INSERT INTO tipos_solicitacao "
            "(id, tenant_id, codigo, nome, categoria, etapas, prazo_resposta_horas, "
            " escalonar_apos_horas, exige_anexo, exige_justificativa, "
            " permite_retroativo_dias, tipo_tratamento_id, ativo) "
            "VALUES (:id, :tenant_id, :codigo, 'Ajuste de ponto de teste', 'ajuste_ponto', "
            "        :etapas, 48, 72, FALSE, TRUE, 30, :tipo_tratamento_id, TRUE)"
        ),
        {
            "id": tipo_solicitacao_id,
            "tenant_id": tenant_id,
            "codigo": tipo_solicitacao_codigo,
            "etapas": '[{"etapa": 1, "papel": "gestor"}, {"etapa": 2, "papel": "rh"}]',
            "tipo_tratamento_id": tipo_tratamento_id,
        },
    )

    # Tipo de afastamento de exemplo, categoria `ferias` -- exigido pelo ramo
    # `ferias` do despachante de A4 (`_resolver_tipo_afastamento_ferias`).
    tipo_afastamento_ferias_id = uuid.uuid4()
    await sessao_f10.execute(
        text(
            "INSERT INTO tipos_afastamento "
            "(id, tenant_id, codigo, nome, categoria, abona_dia, remunerado, ativo) "
            "VALUES (:id, :tenant_id, :codigo, 'Ferias de teste', 'ferias', TRUE, TRUE, TRUE)"
        ),
        {
            "id": tipo_afastamento_ferias_id,
            "tenant_id": tenant_id,
            "codigo": f"FERIAS-{sufixo}",
        },
    )

    # Periodo aberto cobrindo o mes corrente.
    hoje = dt.date.today()
    periodo_data_inicio = hoje.replace(day=1)
    if hoje.month == 12:
        periodo_data_fim = dt.date(hoje.year, 12, 31)
    else:
        periodo_data_fim = dt.date(hoje.year, hoje.month + 1, 1) - dt.timedelta(days=1)
    periodo_id = uuid.uuid4()
    await sessao_f10.execute(
        text(
            "INSERT INTO periodos "
            "(id, tenant_id, empresa_id, codigo, tipo, data_inicio, data_fim, status) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'mensal', :data_inicio, :data_fim, "
            "        'aberto')"
        ),
        {
            "id": periodo_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "codigo": f"{hoje.year:04d}-{hoje.month:02d}-{sufixo}",
            "data_inicio": periodo_data_inicio,
            "data_fim": periodo_data_fim,
        },
    )

    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, tenant_id)

    return ContextoF10(
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        empresa_id=empresa_id,
        unidade_id=unidade_id,
        colaborador_id=colaborador_id,
        vinculo_id=vinculo_id,
        colaborador_usuario_id=colaborador_usuario_id,
        gestor_usuario_id=gestor_usuario_id,
        rh_usuario_id=rh_usuario_id,
        horario_id=horario_id,
        jornada_id=jornada_id,
        tipo_tratamento_id=tipo_tratamento_id,
        tipo_tratamento_codigo=tipo_tratamento_codigo,
        tipo_solicitacao_id=tipo_solicitacao_id,
        tipo_solicitacao_codigo=tipo_solicitacao_codigo,
        tipo_afastamento_ferias_id=tipo_afastamento_ferias_id,
        periodo_id=periodo_id,
        periodo_data_inicio=periodo_data_inicio,
        periodo_data_fim=periodo_data_fim,
    )
