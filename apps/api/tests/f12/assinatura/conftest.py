"""Fixture da fase F12/A3 para os testes de `app.fiscal.assinatura.**`.

Ownership: `apps/api/tests/f12/assinatura/**` (PCF F12 §5, linha "A3"). Este
conftest NÃO é `apps/api/tests/f12/conftest.py` (esse é ownership exclusivo
de A1, T1) -- é um conftest local, escopado só a este subdiretório e a
`tests/f12/cofre/` (que importa os fixtures daqui, ver o conftest de lá),
com bootstrap de banco próprio e independente. Cada agente da fase roda
contra o PRÓPRIO banco exclusivo (`ponto_f12_a1`/`a2`/`a3`), então não há
risco de colisão de dado entre A1/A2/A3 rodando em paralelo -- mesma forma
de bootstrap que `tests/f10/conftest.py` já estabeleceu (migração + role de
LOGIN derivada do nome do banco de `PONTO_TEST_DATABASE_URL` + sessão por
teste sob RLS, nunca superusuário).

Este arquivo entrega:

* Bootstrap de banco (`engine_f12_a3`/`sessao_f12_a3`) -- role de LOGIN real
  (`IN ROLE ponto_app`, nunca superusuário), para que os testes de
  imutabilidade (`test_imutabilidade.py`) provem `ERRCODE 42501` de
  verdade, não um `GRANT` de conveniência.
* `contexto_f12_a3` -- 1 tenant, 1 empresa, 1 REP-P ativo (INPI preenchido),
  1 colaborador/CPF, 1 marcação real (via `INSERT` mínimo, só o suficiente
  para a FK composta de `comprovantes`) e 1 comprovante -- o mínimo comum
  que `app.fiscal.assinatura.servico`/`app.fiscal.cofre.consulta` precisam
  para ter "arquivos que existem de verdade" para assinar/consultar (PCF
  F12, texto de A3 no cabeçalho do prompt da fase).
* `certificado_teste`/`certificado_teste_expirado` -- certificados
  AUTOASSINADOS gerados nesta própria fixture (`cryptography.x509`), cujo
  titular é rotulado `"TESTE SEEG..."` em todo lugar -- nunca apresentados
  como um e-CNPJ A1 real (PCF F12 §2.4/proibição 8).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
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
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.comum.armazenamento import garantir_bucket
from app.fiscal.assinatura.certificado import CertificadoConfig, _config_a_partir_do_certificado

RAIZ_API = Path(__file__).resolve().parents[3]

_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto"


def _url_superusuario() -> URL:
    bruta = os.environ.get("PONTO_TEST_DATABASE_URL", _URL_PADRAO_LOCAL)
    return make_url(bruta)


def _nome_role_login(url_super: URL) -> str:
    base = re.sub(r"[^a-z0-9_]", "_", (url_super.database or "ponto").lower())
    return f"ponto_f12_login_{base}"


@pytest.fixture(scope="session")
def url_login_sessao_f12_a3() -> URL:
    """Migra o banco de teste (`ponto_f12_a3`) e devolve a `URL` de conexão
    da role de LOGIN (nunca superusuário -- é o que faz os testes de
    imutabilidade valerem alguma coisa)."""
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
            "alembic upgrade head falhou ao preparar o banco de teste da F12/A3:\n"
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
async def engine_f12_a3(url_login_sessao_f12_a3: URL) -> AsyncIterator[AsyncEngine]:
    ultimo_erro: Exception | None = None
    for tentativa in range(8):
        engine = create_async_engine(
            url_login_sessao_f12_a3, pool_pre_ping=True, connect_args={"timeout": 8}
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
    raise RuntimeError(f"Nao foi possivel abrir a engine de teste da F12/A3: {ultimo_erro}")


@pytest_asyncio.fixture
async def sessao_f12_a3(engine_f12_a3: AsyncEngine) -> AsyncIterator[AsyncSession]:
    fabrica = async_sessionmaker(engine_f12_a3, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        yield sessao
        await sessao.rollback()


async def aplicar_tenant_teste_f12(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"),
        {"tenant": str(tenant_id)},
    )


@dataclass(frozen=True, slots=True)
class ContextoF12A3:
    """IDs da semente mínima usada pelos testes de A3 (assinatura + cofre)."""

    tenant_id: uuid.UUID
    tenant_slug: str
    empresa_id: uuid.UUID
    rep_p_id: uuid.UUID
    colaborador_id: uuid.UUID
    cpf: str
    marcacao_id: uuid.UUID
    marcacao_datahora: dt.datetime
    comprovante_id: uuid.UUID
    usuario_id: uuid.UUID


@pytest_asyncio.fixture
async def contexto_f12_a3(sessao_f12_a3: AsyncSession) -> ContextoF12A3:
    """Semeia tenant + empresa + REP-P + 1 marcação real (INSERT mínimo,
    suficiente para a FK composta de `comprovantes` -- esta fixture NÃO
    reimplementa o pipeline de ingestão de F5, só grava a linha que a FK
    exige) + 1 comprovante, para exercitar `assinar_arquivo_fiscal(tipo=
    'comprovante')` e servir de base a `tests/f12/cofre` (que cria seus
    próprios `afd_arquivos`/`aej_arquivos` em cima deste mesmo tenant)."""
    sufixo = uuid.uuid4().hex[:10]
    tenant_id = uuid.uuid4()
    tenant_slug = f"f12a3-{sufixo}"

    await aplicar_tenant_teste_f12(sessao_f12_a3, tenant_id)

    await sessao_f12_a3.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, :razao, :nome, 'ativo')"
        ),
        {
            "id": tenant_id,
            "slug": tenant_slug,
            "razao": "Tenant de teste F12/A3",
            "nome": "Tenant F12 A3",
        },
    )

    empresa_id = uuid.uuid4()
    cnpj = f"{secrets.randbelow(10**14):014d}"
    await sessao_f12_a3.execute(
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
            "razao": "Empresa de Teste F12/A3 Ltda",
            "fantasia": "Empresa Teste F12 A3",
        },
    )

    rep_p_id = uuid.uuid4()
    await sessao_f12_a3.execute(
        text(
            "INSERT INTO rep_ps "
            "(id, tenant_id, empresa_id, identificador, tipo, numero_inpi, "
            " cnpj_desenvolvedor, razao_social_desenvolvedor, cnpj_empregador, "
            " razao_social_empregador, versao_programa, status, data_inicio_operacao) "
            "VALUES (:id, :tenant_id, :empresa_id, :identificador, 'rep_p', :inpi, "
            "        :cnpj_dev, 'SEEG Servicos de Tecnologia da Informacao', :cnpj, "
            "        'Empresa de Teste F12/A3 Ltda', '1.0.0-teste', 'ativo', now())"
        ),
        {
            "id": rep_p_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "identificador": f"REPP-{sufixo}",
            "inpi": f"{secrets.randbelow(10**10):010d}",
            "cnpj_dev": f"{secrets.randbelow(10**14):014d}",
            "cnpj": cnpj,
        },
    )
    # `proximo_nsr`/`ultimo_nsr_emitido` default 1/0 (CHECK proximo = ultimo + 1)
    # -- sem necessidade de INSERT explicito, a linha default ja fica correta
    # depois do INSERT abaixo (que so declara o REP-P; a sequencia nasce
    # implicita por FK, entao criamos a linha aqui mesmo, com os DEFAULTs).
    await sessao_f12_a3.execute(
        text("INSERT INTO nsr_sequencias (tenant_id, rep_p_id) VALUES (:tenant_id, :rep_p_id)"),
        {"tenant_id": tenant_id, "rep_p_id": rep_p_id},
    )

    colaborador_id = uuid.uuid4()
    cpf = f"{secrets.randbelow(10**11):011d}"
    await sessao_f12_a3.execute(
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
            "nome": "Colaborador de Teste F12/A3",
        },
    )

    usuario_id = uuid.uuid4()
    await sessao_f12_a3.execute(
        text(
            "INSERT INTO usuarios (id, tenant_id, colaborador_id, email, nome_completo, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :email, :nome, 'ativo')"
        ),
        {
            "id": usuario_id,
            "tenant_id": tenant_id,
            "colaborador_id": colaborador_id,
            "email": f"usuario-{sufixo}@f12a3.teste",
            "nome": "Usuario de Teste F12/A3",
        },
    )

    marcacao_id = uuid.uuid4()
    marcacao_datahora = dt.datetime.now(dt.UTC).replace(microsecond=0)
    hash_marcacao_fixture = "0" * 64  # dom_sha256 exige 64 hex; valor de fixture, nao verificado
    await sessao_f12_a3.execute(
        text(
            "INSERT INTO marcacoes "
            "(id, tenant_id, rep_p_id, empresa_id, colaborador_id, cpf, nsr, "
            " tipo_registro, datahora_marcacao, canal, crc16, hash_registro, "
            " coletada_offline) "
            "VALUES (:id, :tenant_id, :rep_p_id, :empresa_id, :colaborador_id, :cpf, 1, "
            "        '7', :dh, 'web', 0, :hash, FALSE)"
        ),
        {
            "id": marcacao_id,
            "tenant_id": tenant_id,
            "rep_p_id": rep_p_id,
            "empresa_id": empresa_id,
            "colaborador_id": colaborador_id,
            "cpf": cpf,
            "dh": marcacao_datahora,
            "hash": hash_marcacao_fixture,
        },
    )
    await sessao_f12_a3.execute(
        text(
            "UPDATE nsr_sequencias SET proximo_nsr = 2, ultimo_nsr_emitido = 1, "
            "       ultima_emissao_em = :dh "
            "WHERE tenant_id = :tenant_id AND rep_p_id = :rep_p_id"
        ),
        {"tenant_id": tenant_id, "rep_p_id": rep_p_id, "dh": marcacao_datahora},
    )
    await sessao_f12_a3.execute(
        text(
            "INSERT INTO nsr_emissoes "
            "(tenant_id, rep_p_id, nsr, marcacao_id, datahora_marcacao, hash_registro) "
            "VALUES (:tenant_id, :rep_p_id, 1, :marcacao_id, :dh, :hash)"
        ),
        {
            "tenant_id": tenant_id,
            "rep_p_id": rep_p_id,
            "marcacao_id": marcacao_id,
            "dh": marcacao_datahora,
            "hash": hash_marcacao_fixture,
        },
    )

    comprovante_id = uuid.uuid4()
    conteudo_texto = (
        f"COMPROVANTE DE REGISTRO DE PONTO\nNSR: 1\nCPF: {cpf}\n"
        f"Data/hora: {marcacao_datahora.isoformat()}\n"
    )
    hash_sha256 = hashlib.sha256(conteudo_texto.encode("utf-8")).hexdigest()
    await sessao_f12_a3.execute(
        text(
            "INSERT INTO comprovantes "
            "(id, tenant_id, marcacao_id, marcacao_datahora, colaborador_id, cpf, "
            " numero, nsr, conteudo_texto, hash_sha256) "
            "VALUES (:id, :tenant_id, :marcacao_id, :marcacao_dh, :colaborador_id, :cpf, "
            "        :numero, 1, :conteudo, :hash)"
        ),
        {
            "id": comprovante_id,
            "tenant_id": tenant_id,
            "marcacao_id": marcacao_id,
            "marcacao_dh": marcacao_datahora,
            "colaborador_id": colaborador_id,
            "cpf": cpf,
            "numero": f"CMP-{sufixo}",
            "conteudo": conteudo_texto,
            "hash": hash_sha256,
        },
    )

    await sessao_f12_a3.commit()
    await aplicar_tenant_teste_f12(sessao_f12_a3, tenant_id)

    return ContextoF12A3(
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        empresa_id=empresa_id,
        rep_p_id=rep_p_id,
        colaborador_id=colaborador_id,
        cpf=cpf,
        marcacao_id=marcacao_id,
        marcacao_datahora=marcacao_datahora,
        comprovante_id=comprovante_id,
        usuario_id=usuario_id,
    )


@pytest_asyncio.fixture
async def bucket_minio_f12() -> None:
    """Garante que o bucket configurado (`MINIO_BUCKET`, padrão `ponto`)
    existe antes de qualquer teste que grave objeto real."""
    await garantir_bucket()


def _gerar_certificado_teste(
    *, titular: str, dias_validade_inicio: int, dias_validade_fim: int
) -> CertificadoConfig:
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, titular)])
    agora = dt.datetime.now(dt.UTC)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora + dt.timedelta(days=dias_validade_inicio))
        .not_valid_after(agora + dt.timedelta(days=dias_validade_fim))
        .sign(chave, hashes.SHA256())
    )
    return _config_a_partir_do_certificado(certificado, chave, rotulo_teste=titular)


#: `CommonName` do X.509 tem limite de 64 bytes (`cryptography`, verificado
#: em runtime) -- os titulares abaixo são deliberadamente curtos, mas
#: continuam rotulados sem ambiguidade como certificado de TESTE, nunca um
#: e-CNPJ A1 ICP-Brasil real (PCF F12 §2.4/proibição 8).
TITULAR_TESTE = "SEEG TESTE - CERT AUTOASSINADO (NAO E ICP-BRASIL)"
TITULAR_TESTE_EXPIRADO = "SEEG TESTE - CERT EXPIRADO (NAO E ICP-BRASIL)"


@pytest.fixture
def certificado_teste() -> CertificadoConfig:
    """Certificado AUTOASSINADO gerado NESTA fixture, válido por 1 ano --
    prova que o mecanismo de assinatura CAdES é real e completo (PCF F12
    §2.4), sem fingir ser um e-CNPJ A1 ICP-Brasil de verdade. Titular
    rotulado explicitamente como certificado de teste."""
    return _gerar_certificado_teste(
        titular=TITULAR_TESTE,
        dias_validade_inicio=-1,
        dias_validade_fim=365,
    )


@pytest.fixture
def certificado_teste_expirado() -> CertificadoConfig:
    """Mesmo tipo de certificado de teste, mas com a janela de validade já
    encerrada -- usado para provar `PONTO-FISC-005`."""
    return _gerar_certificado_teste(
        titular=TITULAR_TESTE_EXPIRADO,
        dias_validade_inicio=-400,
        dias_validade_fim=-30,
    )
