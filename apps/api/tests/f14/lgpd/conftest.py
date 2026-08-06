"""Fixtures dos testes de `app.lgpd.*` (F14/A3).

Mesmo padrao de duas camadas que `tests/f2/conftest.py` ja usa (T1 da F2):

1. `url_login_sessao` (escopo `session`, sincrona): migra o banco de teste e
   cria a role de LOGIN sob a qual todo teste desta pasta roda (Row Level
   Security so tem sentido testado por uma role que nao seja superusuario).
2. `sessao_f14` / `contexto_organizacional` (escopo `function`, assincronas):
   cada teste ganha sua propria sessao SQLAlchemy assincrona, ligada ao
   event loop daquele teste.

Self-contained de proposito -- nao importa `tests.f2.conftest` nem qualquer
outro modulo de outro agente/fase: ownership de arquivo desta fase e
mutuamente exclusivo (PCF F14 secao 3), e o padrao de fixture de banco ja e
duplicado dessa mesma forma em toda fase anterior (F2, F13, ...).

Variavel de ambiente lida: `PONTO_TEST_DATABASE_URL` (string de conexao
`postgresql+asyncpg://usuario:senha@host:porta/base` de um Postgres 16 **ja
existente e vazio**, sob superusuario ou usuario com privilegio de criar
roles). Sem a variavel, cai no default de desenvolvimento local -- nunca o
banco de nenhum ambiente real.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import secrets
import subprocess
import sys
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import psycopg
import pytest
import pytest_asyncio
from ponto_contracts import (
    Biometria,
    BiometriaTemplate,
    Colaborador,
    Consentimento,
    PoliticaRetencao,
)
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

#: Default de desenvolvimento local. So usado quando `PONTO_TEST_DATABASE_URL`
#: nao esta definida -- nunca aponta para banco de ambiente real.
_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto"

#: Role de LOGIN criada para os testes desta fase/agente. Membra de
#: `ponto_app` (criada por `0001_inicial`, NOLOGIN por si so) para herdar
#: exatamente os privilegios de tabela que a aplicacao usa em producao.
_ROLE_LOGIN = "ponto_f14_a3_teste_login"


def _url_superusuario() -> URL:
    bruta = os.environ.get("PONTO_TEST_DATABASE_URL", _URL_PADRAO_LOCAL)
    return make_url(bruta)


@pytest.fixture(scope="session")
def url_login_sessao() -> URL:
    """Migra o banco de teste e devolve a `URL` de conexao da role de LOGIN."""
    url_super = _url_superusuario()

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
            "alembic upgrade head falhou ao preparar o banco de teste da F14/A3:\n"
            f"--- stdout ---\n{resultado.stdout}\n--- stderr ---\n{resultado.stderr}"
        )

    senha = secrets.token_urlsafe(24)
    dsn_super = url_super.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn_super, autocommit=True) as conexao, conexao.cursor() as cursor:
        cursor.execute(sql.SQL("SELECT 1 FROM pg_roles WHERE rolname = %s"), (_ROLE_LOGIN,))
        if cursor.fetchone():
            cursor.execute(
                sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                    sql.Identifier(_ROLE_LOGIN), sql.Literal(senha)
                )
            )
        else:
            cursor.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} IN ROLE ponto_app").format(
                    sql.Identifier(_ROLE_LOGIN), sql.Literal(senha)
                )
            )

    url_login = url_super.set(drivername="postgresql+asyncpg", username=_ROLE_LOGIN, password=senha)
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
async def engine_f14(url_login_sessao: URL) -> AsyncIterator[AsyncEngine]:
    """Engine assincrona por teste, autenticada como a role de LOGIN da fase.

    Recria e tenta de novo algumas vezes: a primeira conexao de uma engine
    nova atraves do tunel SSH ate a VPS falha ocasionalmente por
    instabilidade de rede sob carga concorrente de varios agentes de fase,
    nao por credencial errada (mesmo padrao ja documentado em
    `tests/f2/conftest.py`).
    """
    ultimo_erro: Exception | None = None
    for tentativa in range(8):
        engine = create_async_engine(
            url_login_sessao, pool_pre_ping=True, connect_args={"timeout": 8}
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
    raise RuntimeError(f"Nao foi possivel abrir a engine de teste da F14/A3: {ultimo_erro}")


@pytest_asyncio.fixture
async def sessao_f14(engine_f14: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Sessao assincrona por teste. O teste decide quando commitar.

    Cuidado com `SET LOCAL` + `commit()` no meio do teste: reaplique
    `aplicar_tenant_teste` logo depois de qualquer `sessao.commit()`
    intermediario (mesmo alerta ja documentado em `docs/backlog.md`,
    2026-08-03, achado de F13/A3).
    """
    fabrica = async_sessionmaker(engine_f14, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        yield sessao
        await sessao.rollback()


async def aplicar_tenant_teste(sessao: AsyncSession, tenant_id: UUID) -> None:
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"),
        {"tenant": str(tenant_id)},
    )


@dataclass(frozen=True, slots=True)
class ContextoOrganizacional:
    tenant_id: UUID
    tenant_slug: str
    empresa_id: UUID


@pytest_asyncio.fixture
async def contexto_organizacional(sessao_f14: AsyncSession) -> ContextoOrganizacional:
    """Semeia 1 tenant e 1 empresa. Cada chamada gera tenant/CNPJ novos --
    nenhum teste compartilha semente com outro."""
    sufixo = uuid.uuid4().hex[:12]
    tenant_id = uuid.uuid4()
    tenant_slug = f"f14-lgpd-{sufixo}"

    await aplicar_tenant_teste(sessao_f14, tenant_id)

    await sessao_f14.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, :razao, :nome, 'ativo')"
        ),
        {
            "id": tenant_id,
            "slug": tenant_slug,
            "razao": "Tenant de teste da fase F14 (A3/LGPD)",
            "nome": "Tenant F14 LGPD",
        },
    )

    empresa_id = uuid.uuid4()
    # `dom_cnpj` so exige 14 digitos (CHECK de formato, sem digito
    # verificador -- `packages/contracts/schema.sql`); unicidade e por
    # `(tenant_id, cnpj)`, e cada teste semeia um tenant novo, entao um
    # numero derivado do sufixo aleatorio do tenant basta.
    cnpj = str(int(sufixo, 16))[:14].ljust(14, "1")
    await sessao_f14.execute(
        text(
            "INSERT INTO empresas "
            "(id, tenant_id, tipo, cnpj, razao_social, nome_fantasia, uf, codigo_ibge_municipio) "
            "VALUES (:id, :tenant_id, 'matriz', :cnpj, :razao, :fantasia, 'SP', '3550308')"
        ),
        {
            "id": empresa_id,
            "tenant_id": tenant_id,
            "cnpj": cnpj,
            "razao": "Empresa de Teste F14 LGPD Ltda",
            "fantasia": "Teste F14 LGPD",
        },
    )

    await sessao_f14.commit()
    await aplicar_tenant_teste(sessao_f14, tenant_id)

    return ContextoOrganizacional(
        tenant_id=tenant_id, tenant_slug=tenant_slug, empresa_id=empresa_id
    )


def _cpf_valido_para_indice(indice: int) -> str:
    """Mesmo algoritmo (modulo 11) reimplementado em varios `conftest.py`
    desta base (ver `tests/f2/biometria/conftest.py`), duplicado aqui de
    proposito pelo mesmo motivo (self-contained por fase/agente)."""
    base = str(400_000_000 + indice)[-9:]
    pesos1 = list(range(10, 1, -1))
    pesos2 = list(range(11, 1, -1))

    def _dv(digitos: str, pesos: list[int]) -> int:
        soma = sum(int(d) * p for d, p in zip(digitos, pesos, strict=True))
        resto = soma % 11
        return 0 if resto < 2 else 11 - resto

    dv1 = _dv(base, pesos1)
    dv2 = _dv(base + str(dv1), pesos2)
    return f"{base}{dv1}{dv2}"


@pytest_asyncio.fixture
async def criar_colaborador(
    sessao_f14: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> Callable[..., Awaitable[UUID]]:
    contador = {"n": 0}

    async def _fabrica(*, status: str = "ativo") -> UUID:
        contador["n"] += 1
        indice = contador["n"]
        colaborador = Colaborador(
            tenant_id=contexto_organizacional.tenant_id,
            empresa_id=contexto_organizacional.empresa_id,
            matricula=f"LGPD{indice:05d}",
            cpf=_cpf_valido_para_indice(indice),
            nome_completo=f"Colaborador LGPD Teste {indice}",
            status=status,
        )
        sessao_f14.add(colaborador)
        await sessao_f14.flush()
        return colaborador.id

    return _fabrica


@pytest_asyncio.fixture
async def criar_consentimento(
    sessao_f14: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> Callable[..., Awaitable[UUID]]:
    async def _fabrica(
        *,
        colaborador_id: UUID,
        finalidade: str = "biometria_facial",
        status: str = "concedido",
        versao_termo: str = "v1",
    ) -> UUID:
        consentimento = Consentimento(
            tenant_id=contexto_organizacional.tenant_id,
            colaborador_id=colaborador_id,
            finalidade=finalidade,
            versao_termo=versao_termo,
            texto_termo_ref=f"termos/{uuid.uuid4()}.pdf",
            hash_termo="a" * 64,
            status=status,
            canal="app",
        )
        sessao_f14.add(consentimento)
        await sessao_f14.flush()
        return consentimento.id

    return _fabrica


@pytest_asyncio.fixture
async def criar_biometria_com_template(
    sessao_f14: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> Callable[..., Awaitable[UUID]]:
    """Insere `Biometria` + `BiometriaTemplate` diretamente via ORM, com
    bytes falsos (nao passa por `app.biometria.cifra`) -- suficiente para
    testar contagem/remocao, nao decifragem."""

    async def _fabrica(
        *,
        colaborador_id: UUID,
        modalidade: str = "facial",
        status: str = "ativa",
        consentimento_id: UUID | None = None,
    ) -> UUID:
        biometria = Biometria(
            tenant_id=contexto_organizacional.tenant_id,
            colaborador_id=colaborador_id,
            modalidade=modalidade,
            status=status,
            origem_cadastro="app",
            consentimento_id=consentimento_id,
            cadastrada_em=None,
        )
        sessao_f14.add(biometria)
        await sessao_f14.flush()

        template = BiometriaTemplate(
            tenant_id=contexto_organizacional.tenant_id,
            biometria_id=biometria.id,
            versao_modelo="arcface-r100-v1",
            provedor="facial-svc",
            dimensao=512,
            template_cifrado=b"\x00\x01falso-cifrado-suficiente-para-teste",
            iv=b"\x00" * 12,
            tag_autenticacao=b"\x00" * 16,
            algoritmo_cifra="AES-256-GCM",
            chave_id="kek-v1-teste",
        )
        sessao_f14.add(template)
        await sessao_f14.flush()
        return biometria.id

    return _fabrica


@pytest_asyncio.fixture
async def criar_vinculo(
    sessao_f14: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> Callable[..., Awaitable[UUID]]:
    """Minimo necessario para uma marcacao apontar para um vinculo real
    (mesmo padrao de `tests/f4/propriedade/conftest.py`)."""

    async def _fabrica(*, colaborador_id: UUID) -> UUID:
        vinculo_id = uuid.uuid4()
        sufixo = uuid.uuid4().hex[:10]
        await sessao_f14.execute(
            text(
                "INSERT INTO vinculos "
                "(id, tenant_id, colaborador_id, empresa_id, matricula_esocial, "
                " tipo_vinculo, data_inicio, apura_ponto, status) "
                "VALUES (:id, :tenant_id, :colaborador_id, :empresa_id, :esocial, "
                "        'empregado', :data_inicio, TRUE, 'ativo')"
            ),
            {
                "id": vinculo_id,
                "tenant_id": contexto_organizacional.tenant_id,
                "colaborador_id": colaborador_id,
                "empresa_id": contexto_organizacional.empresa_id,
                "esocial": f"ESOC-{sufixo}",
                "data_inicio": dt.date(2020, 1, 1),
            },
        )
        await sessao_f14.flush()
        return vinculo_id

    return _fabrica


@pytest_asyncio.fixture
async def criar_rep_p(
    sessao_f14: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> Callable[..., Awaitable[UUID]]:
    """Mesmo padrao minimo de `tests/f11/datasets_gerenciais/conftest.py`."""

    async def _fabrica() -> UUID:
        rep_p_id = uuid.uuid4()
        sufixo = uuid.uuid4().hex[:8]
        cnpj = f"{secrets.randbelow(10**14):014d}"
        await sessao_f14.execute(
            text(
                "INSERT INTO rep_ps "
                "(id, tenant_id, empresa_id, identificador, numero_inpi, cnpj_desenvolvedor, "
                " razao_social_desenvolvedor, cnpj_empregador, razao_social_empregador, "
                " versao_programa, data_inicio_operacao, status) "
                "VALUES (:id, :tenant_id, :empresa_id, :identificador, '12345678', :cnpj_dev, "
                "        'SEEG Servicos de TI', :cnpj_emp, 'Empresa de Teste F14 Ltda', '1.0.0', "
                "        '2020-01-01', 'ativo')"
            ),
            {
                "id": rep_p_id,
                "tenant_id": contexto_organizacional.tenant_id,
                "empresa_id": contexto_organizacional.empresa_id,
                "identificador": f"REP-{sufixo}",
                "cnpj_dev": cnpj,
                "cnpj_emp": cnpj,
            },
        )
        await sessao_f14.flush()
        return rep_p_id

    return _fabrica


@pytest_asyncio.fixture
async def criar_marcacao(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_rep_p: Callable[..., Awaitable[UUID]],
) -> Callable[..., Awaitable[UUID]]:
    """Insere uma linha em `marcacoes` diretamente (mesmo padrao de
    `tests/f11/datasets_gerenciais/test_datasets_gerenciais.py`) -- NSR
    sintetico, nao passa pelo pipeline real de ingestao (fora do escopo
    desta fase/agente: F5 e quem possui `app.marcacao.pipeline`)."""

    contador = {"n": 0}
    rep_p_id_cache: dict[str, UUID] = {}

    async def _fabrica(*, colaborador_id: UUID, vinculo_id: UUID, cpf: str) -> UUID:
        if "id" not in rep_p_id_cache:
            rep_p_id_cache["id"] = await criar_rep_p()
        contador["n"] += 1
        nsr = contador["n"]
        marcacao_id = uuid.uuid4()
        agora = dt.datetime.now(tz=dt.UTC) - dt.timedelta(days=nsr)
        await sessao_f14.execute(
            text(
                "INSERT INTO marcacoes "
                "(id, tenant_id, rep_p_id, empresa_id, colaborador_id, vinculo_id, nsr, cpf, "
                " datahora_marcacao, canal, crc16, hash_registro) "
                "VALUES (:id, :tenant_id, :rep_p_id, :empresa_id, :colaborador_id, :vinculo_id, "
                "        :nsr, :cpf, :datahora_marcacao, 'terminal', 1, :hash_registro)"
            ),
            {
                "id": marcacao_id,
                "tenant_id": contexto_organizacional.tenant_id,
                "rep_p_id": rep_p_id_cache["id"],
                "empresa_id": contexto_organizacional.empresa_id,
                "colaborador_id": colaborador_id,
                "vinculo_id": vinculo_id,
                "nsr": nsr,
                "cpf": cpf,
                "datahora_marcacao": agora,
                "hash_registro": f"{nsr:064d}",
            },
        )
        await sessao_f14.flush()
        return marcacao_id

    return _fabrica


@pytest_asyncio.fixture
async def criar_politica_retencao(
    sessao_f14: AsyncSession, contexto_organizacional: ContextoOrganizacional
) -> Callable[..., Awaitable[UUID]]:
    async def _fabrica(
        *,
        entidade: str,
        prazo_dias: int,
        acao: str = "eliminar",
        ativo: bool = True,
        proxima_execucao_em: dt.datetime | None = None,
    ) -> UUID:
        politica = PoliticaRetencao(
            tenant_id=contexto_organizacional.tenant_id,
            entidade=entidade,
            prazo_dias=prazo_dias,
            base_legal="politica interna de teste",
            acao=acao,
            ativo=ativo,
            proxima_execucao_em=proxima_execucao_em,
        )
        sessao_f14.add(politica)
        await sessao_f14.flush()
        return politica.id

    return _fabrica
