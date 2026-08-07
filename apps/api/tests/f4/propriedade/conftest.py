"""Fixture dos testes de propriedade (T12, agente A4).

Bootstrap PROPRIO deste subpacote (`apps/api/tests/f4/propriedade/**`,
ownership exclusivo de A4), no mesmo padrao de bootstrap ja estabelecido por
`tests/f3/conftest.py`/`tests/f4/banco_horas/conftest.py`/`tests/f4/
tratamento/conftest.py` (migracao + role de LOGIN nao-superusuario derivada
do nome do banco + sessao por teste sob RLS) -- nunca a logica de negocio de
outra fase, so a FORMA do bootstrap.

Diferente do golden dataset (T11, que reusa `tests/f3/conftest.py` porque os
cenarios exigem o `ContextoF3` exato), os testes de propriedade (T12)
precisam de uma jornada FIXA SIMPLES atribuida de verdade (para que
`apurar_dia`/`recalcular_periodo` tenham insumo real de calculo) mais uma
`bh_politica`/`bh_conta` (para a propriedade do saldo de banco de horas) --
uma massa diferente da do golden dataset, entao este modulo semeia a sua
propria, auto-contida, sem depender de nem colidir com nenhum outro
conftest da fase.

Semente por teste (escopo `function`):

* 1 tenant, 1 empresa, 1 unidade (`America/Sao_Paulo`), 1 colaborador com
  vinculo `apura_ponto=true`.
* 1 REP-P ativo (necessario para inserir marcacoes de teste respeitando
  `marcacoes.rep_p_id NOT NULL`).
* 1 jornada `tipo='fixa'` simples: horario 08:00-17:00 com 1h de intervalo
  (12:00-13:00), segunda a sexta util (carga 480 min/dia), sabado folga,
  domingo DSR -- o padrao mais comum do proprio golden dataset da F3
  (`tests/f3/golden/_construtores.py::criar_jornada_semana_padrao`, lido
  como referencia de FORMA, nunca importado: e ownership exclusivo e ja
  concluido da F3, e o INSERT literal aqui e propriedade deste modulo) --
  atribuida ao vinculo via `vinculo_jornadas` a partir de uma vigencia fixa
  (`2025-01-01`, sem fim).
* 1 `bh_politicas` (`individual`, `fifo`, 6 meses, sem teto configurado --
  `permite_saldo_negativo=TRUE` para a propriedade de creditos/debitos
  aleatorios de T12(c) nunca esbarrar em `PONTO-BH-002`) e 1 `bh_contas`
  (`codigo='normal'`, `status='aberta'`, periodo 2025-01-01..2025-06-30).

Nenhuma marcacao e semeada aqui: cada teste de propriedade insere as suas
proprias, via o helper `inserir_marcacao`, de acordo com o cenario que
precisa provar.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import os
import re
import secrets
import subprocess
import sys
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal
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

RAIZ_API = Path(__file__).resolve().parents[3]

_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto"


def _url_superusuario() -> URL:
    bruta = os.environ.get("PONTO_TEST_DATABASE_URL", _URL_PADRAO_LOCAL)
    return make_url(bruta)


def _nome_role_login(url_super: URL) -> str:
    base = re.sub(r"[^a-z0-9_]", "_", (url_super.database or "ponto").lower())
    return f"ponto_f4_login_{base}"


@pytest.fixture(scope="session")
def url_login_sessao_propriedade() -> URL:
    """Migra o banco de teste e devolve a `URL` de conexao da role de LOGIN.

    Mesma role de LOGIN (`ponto_f4_login_<nome_do_banco>`) que o T1 original
    do PCF descreve -- derivada do nome do banco, nunca hardcoded para um
    agente especifico, para nao colidir com outros agentes da fase rodando
    em paralelo contra bancos exclusivos distintos no mesmo cluster.
    """
    url_super = _url_superusuario()
    role_login = _nome_role_login(url_super)

    ambiente = dict(os.environ)
    ambiente["DATABASE_URL"] = url_super.render_as_string(hide_password=False)
    # alembic/env.py prioriza DATABASE_URL_SYNC sobre DATABASE_URL --
    # sem isto, o subprocess herda o DATABASE_URL_SYNC do ambiente (setado
    # pelo job do CI apontando para outro banco) e a migracao silenciosamente
    # aplica no banco ERRADO -- achado real, 2026-08-07, descoberto ao investigar
    # "relation ... does not exist" na primeira execucao real do CI.
    ambiente["DATABASE_URL_SYNC"] = url_super.set(
        drivername="postgresql+psycopg"
    ).render_as_string(hide_password=False)
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
            "alembic upgrade head falhou ao preparar o banco de teste da F4/A4 "
            f"(propriedade):\n--- stdout ---\n{resultado.stdout}\n"
            f"--- stderr ---\n{resultado.stderr}"
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
async def engine_propriedade(url_login_sessao_propriedade: URL) -> AsyncIterator[AsyncEngine]:
    ultimo_erro: Exception | None = None
    for tentativa in range(8):
        engine = create_async_engine(
            url_login_sessao_propriedade, pool_pre_ping=True, connect_args={"timeout": 8}
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
    raise RuntimeError(f"Nao foi possivel abrir a engine de teste da F4/A4: {ultimo_erro}")


@pytest_asyncio.fixture
async def sessao_propriedade(engine_propriedade: AsyncEngine) -> AsyncIterator[AsyncSession]:
    fabrica = async_sessionmaker(engine_propriedade, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        yield sessao
        await sessao.rollback()


async def aplicar_tenant_teste(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"),
        {"tenant": str(tenant_id)},
    )


@dataclass(frozen=True, slots=True)
class ContextoPropriedade:
    """IDs da semente minima usada pelos testes de propriedade (T12)."""

    tenant_id: uuid.UUID
    empresa_id: uuid.UUID
    unidade_id: uuid.UUID
    colaborador_id: uuid.UUID
    vinculo_id: uuid.UUID
    rep_p_id: uuid.UUID
    jornada_id: uuid.UUID
    horario_id: uuid.UUID
    bh_politica_id: uuid.UUID
    bh_conta_id: uuid.UUID


async def _criar_jornada_fixa_simples(
    sessao: AsyncSession, tenant_id: uuid.UUID, empresa_id: uuid.UUID, *, sufixo: str
) -> tuple[uuid.UUID, uuid.UUID]:
    """Horario 08:00-17:00 (1h de intervalo), jornada `fixa`, segunda a
    sexta util (480 min), sabado folga, domingo DSR -- mesma FORMA de
    `tests/f3/golden/_construtores.py::criar_jornada_semana_padrao`, lida
    como referencia, nunca importada (ver docstring do modulo). Devolve
    `(jornada_id, horario_id)`."""
    horario_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO horarios "
            "(id, tenant_id, empresa_id, codigo, nome, entrada, saida, "
            " intervalo_inicio, intervalo_fim, duracao_intervalo_minutos, carga_minutos) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'Horario padrao 08-17', "
            "        '08:00', '17:00', '12:00', '13:00', 60, 480)"
        ),
        {
            "id": horario_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "codigo": f"HOR-PROP-{sufixo}",
        },
    )

    jornada_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO jornadas "
            "(id, tenant_id, empresa_id, codigo, nome, tipo, vigencia_inicio, "
            " carga_diaria_minutos) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'Jornada fixa de teste', 'fixa', "
            "        :vigencia_inicio, 480)"
        ),
        {
            "id": jornada_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "codigo": f"JOR-PROP-{sufixo}",
            "vigencia_inicio": _dt.date(2025, 1, 1),
        },
    )

    for dow in range(0, 7):
        if dow == 0:
            tipo_dia, horario_dia, carga = "dsr", None, 0
        elif dow == 6:
            tipo_dia, horario_dia, carga = "folga", None, 0
        else:
            tipo_dia, horario_dia, carga = "util", horario_id, 480
        await sessao.execute(
            text(
                "INSERT INTO jornada_dias "
                "(id, tenant_id, jornada_id, dia_semana, tipo_dia, horario_id, carga_minutos) "
                "VALUES (:id, :tenant_id, :jornada_id, :dow, :tipo_dia, :horario_id, :carga)"
            ),
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "jornada_id": jornada_id,
                "dow": dow,
                "tipo_dia": tipo_dia,
                "horario_id": horario_dia,
                "carga": carga,
            },
        )

    return jornada_id, horario_id


@pytest_asyncio.fixture
async def contexto_propriedade(sessao_propriedade: AsyncSession) -> ContextoPropriedade:
    """Semeia tenant/empresa/unidade/colaborador/vinculo, 1 REP-P ativo,
    1 jornada fixa simples atribuida ao vinculo (vigente desde 2025-01-01) e
    1 `bh_politicas`/`bh_contas` -- via `INSERT` direto, nunca pela API."""
    sufixo = uuid.uuid4().hex[:10]
    tenant_id = uuid.uuid4()

    await aplicar_tenant_teste(sessao_propriedade, tenant_id)

    await sessao_propriedade.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, :razao, :nome, 'ativo')"
        ),
        {
            "id": tenant_id,
            "slug": f"f4-a4-prop-{sufixo}",
            "razao": "Tenant de teste F4/A4 (propriedade)",
            "nome": "Tenant F4 A4 Propriedade",
        },
    )

    empresa_id = uuid.uuid4()
    cnpj = f"{secrets.randbelow(10**14):014d}"
    await sessao_propriedade.execute(
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
            "razao": "Empresa de Teste F4 A4 Propriedade Ltda",
            "fantasia": "Empresa Teste F4 A4 Propriedade",
        },
    )

    unidade_id = uuid.uuid4()
    await sessao_propriedade.execute(
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
    await sessao_propriedade.execute(
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
            "nome": "Colaborador de Teste F4 A4 Propriedade",
        },
    )

    vinculo_id = uuid.uuid4()
    await sessao_propriedade.execute(
        text(
            "INSERT INTO vinculos "
            "(id, tenant_id, colaborador_id, empresa_id, unidade_id, matricula_esocial, "
            " tipo_vinculo, data_inicio, apura_ponto, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :empresa_id, :unidade_id, :esocial, "
            "        'empregado', :data_inicio, TRUE, 'ativo')"
        ),
        {
            "id": vinculo_id,
            "tenant_id": tenant_id,
            "colaborador_id": colaborador_id,
            "empresa_id": empresa_id,
            "unidade_id": unidade_id,
            "esocial": f"ESOC-{sufixo}",
            "data_inicio": _dt.date(2020, 1, 1),
        },
    )

    rep_p_id = uuid.uuid4()
    cnpj_dev = f"{secrets.randbelow(10**14):014d}"
    await sessao_propriedade.execute(
        text(
            "INSERT INTO rep_ps "
            "(id, tenant_id, empresa_id, identificador, tipo, numero_inpi, "
            " cnpj_desenvolvedor, razao_social_desenvolvedor, cnpj_empregador, "
            " razao_social_empregador, versao_programa, data_inicio_operacao, status) "
            "VALUES (:id, :tenant_id, :empresa_id, :identificador, 'rep_p', '12345678', "
            "        :cnpj_dev, 'SEEG Servicos de TI', :cnpj_empresa, 'Empresa de Teste', "
            "        '1.0.0', :data_inicio, 'ativo')"
        ),
        {
            "id": rep_p_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "identificador": f"REP-{sufixo}",
            "cnpj_dev": cnpj_dev,
            "cnpj_empresa": cnpj,
            "data_inicio": _dt.date(2020, 1, 1),
        },
    )

    jornada_id, horario_id = await _criar_jornada_fixa_simples(
        sessao_propriedade, tenant_id, empresa_id, sufixo=sufixo
    )
    await sessao_propriedade.execute(
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
            "vigencia_inicio": _dt.date(2025, 1, 1),
        },
    )

    bh_politica_id = uuid.uuid4()
    await sessao_propriedade.execute(
        text(
            "INSERT INTO bh_politicas "
            "(id, tenant_id, empresa_id, codigo, nome, regime, periodo_meses, "
            " metodo_consumo, permite_saldo_negativo, vigencia_inicio, ativo) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'Politica de teste (propriedade)', "
            "        'individual', 6, 'fifo', TRUE, :vigencia_inicio, TRUE)"
        ),
        {
            "id": bh_politica_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "codigo": f"POL-PROP-{sufixo}",
            "vigencia_inicio": _dt.date(2020, 1, 1),
        },
    )

    bh_conta_id = uuid.uuid4()
    await sessao_propriedade.execute(
        text(
            "INSERT INTO bh_contas "
            "(id, tenant_id, colaborador_id, vinculo_id, bh_politica_id, codigo, nome, "
            " periodo_inicio, periodo_fim, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :vinculo_id, :bh_politica_id, "
            "        'normal', 'Banco de horas normal (propriedade)', :periodo_inicio, "
            "        :periodo_fim, 'aberta')"
        ),
        {
            "id": bh_conta_id,
            "tenant_id": tenant_id,
            "colaborador_id": colaborador_id,
            "vinculo_id": vinculo_id,
            "bh_politica_id": bh_politica_id,
            "periodo_inicio": _dt.date(2025, 1, 1),
            "periodo_fim": _dt.date(2025, 6, 30),
        },
    )

    await sessao_propriedade.commit()
    await aplicar_tenant_teste(sessao_propriedade, tenant_id)

    return ContextoPropriedade(
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        unidade_id=unidade_id,
        colaborador_id=colaborador_id,
        vinculo_id=vinculo_id,
        rep_p_id=rep_p_id,
        jornada_id=jornada_id,
        horario_id=horario_id,
        bh_politica_id=bh_politica_id,
        bh_conta_id=bh_conta_id,
    )


async def inserir_marcacao(
    sessao: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    rep_p_id: uuid.UUID,
    empresa_id: uuid.UUID,
    colaborador_id: uuid.UUID,
    vinculo_id: uuid.UUID,
    cpf: str,
    datahora: _dt.datetime,
    nsr: int,
) -> uuid.UUID:
    """Insere uma marcacao MINIMA e valida (satisfaz todo `CHECK`/`NOT NULL`
    da tabela) diretamente via SQL -- nunca pela API de ingestao da F5 (T1
    do PCF autoriza exatamente este tipo de insercao para massa de teste).
    `hash_registro`/`crc16` sao valores sinteticos (formato valido, sem
    encadeamento real): nenhum trigger de `marcacoes` valida a cadeia de
    hash em si (so bloqueia `UPDATE`/`DELETE`), e a propriedade testada
    aqui e sobre `apuracoes_dia`/`bh_contas`, nunca sobre a cadeia de hash
    de `marcacoes` (isso e' territorio da F5, ja concluida)."""
    marcacao_id = uuid.uuid4()
    hash_sintetico = secrets.token_hex(32)
    await sessao.execute(
        text(
            "INSERT INTO marcacoes "
            "(id, tenant_id, rep_p_id, empresa_id, colaborador_id, vinculo_id, nsr, "
            " cpf, datahora_marcacao, fuso_horario, canal, crc16, hash_registro) "
            "VALUES (:id, :tenant_id, :rep_p_id, :empresa_id, :colaborador_id, :vinculo_id, "
            "        :nsr, :cpf, :datahora, 'America/Sao_Paulo', 'terminal', :crc16, :hash)"
        ),
        {
            "id": marcacao_id,
            "tenant_id": tenant_id,
            "rep_p_id": rep_p_id,
            "empresa_id": empresa_id,
            "colaborador_id": colaborador_id,
            "vinculo_id": vinculo_id,
            "nsr": nsr,
            "cpf": cpf,
            "datahora": datahora,
            "crc16": nsr % 65536,
            "hash": hash_sintetico,
        },
    )
    return marcacao_id


#: Fator neutro usado pelos lancamentos manuais de banco de horas nos testes
#: de propriedade -- mantem `minutos_equivalentes == minutos`, o que
#: simplifica a leitura das asserções sem afetar a propriedade testada (que
#: vale para qualquer fator, ver docstring de `test_banco_horas_saldo_bate_
#: com_lancamentos.py`).
FATOR_NEUTRO = Decimal("1.0")
