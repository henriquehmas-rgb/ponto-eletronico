"""Ambiente dos testes de ponta a ponta do motor facial ligado as rotas reais.

Autocontido, como toda suite deste repositorio (mesma convencao ja duplicada
por F1/F2/F5/F12/F13/F14-A2, ver `docs/backlog.md` 2026-08-03): banco proprio
apontado por `PONTO_TEST_DATABASE_URL`, migracao idempotente na primeira
fixture de sessao, autenticacao por `dependency_overrides[obter_sujeito]`.

O que estes testes exigem do ambiente, alem do Postgres
-------------------------------------------------------

``PONTO_TEST_FACIAL_SVC_URL``
    URL de um `facial-svc` **de verdade**, com os pesos ONNX carregados. Sem
    ela a suite e PULADA, nunca silenciosamente aprovada -- o ponto inteiro
    destes testes e provar que a API fala com o motor real, e um dublê de teste
    provaria so que o dublê responde.
``PONTO_BIOMETRIA_CHAVE_MESTRA``
    KEK de `app.biometria.cifra` (ADR-006). Gerada aqui mesma, descartavel, se
    o ambiente nao trouxer uma -- o template cifrado destes testes nunca sai
    deste banco efemero.

As fotos vem de `insightface.data.get_image("t1")`, a foto de grupo de seis
pessoas distribuida com o proprio pacote `insightface` (MIT) -- a mesma fonte
que `apps/facial-svc/tests/test_motor_facial.py` ja usa, pela mesma razao:
nenhum rosto entra no repositorio da SEEG, nao ha duvida de licenca, e seis
identidades reais no mesmo quadro sao o unico jeito honesto de provar que
**pessoas diferentes reprovam**.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import os
import secrets
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.seguranca import AlcanceEfetivo, Sujeito

RAIZ_API = Path(__file__).resolve().parents[3]  # apps/api

VARIAVEL_FACIAL = "PONTO_TEST_FACIAL_SVC_URL"
VARIAVEL_KEK = "PONTO_BIOMETRIA_CHAVE_MESTRA"
_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto_f14_facial"

#: Quantidade de rostos que a foto `t1` do `insightface` contem. Se um pacote
#: de modelos futuro detectar menos, a suite PULA em vez de comparar a pessoa
#: errada com ela mesma e "passar".
TOTAL_PESSOAS = 6


# ---------------------------------------------------------------------------
# Banco
# ---------------------------------------------------------------------------
def _url_banco_teste() -> URL:
    return make_url(os.environ.get("PONTO_TEST_DATABASE_URL", _URL_PADRAO_LOCAL))


def _garantir_banco_existe(url_banco: URL) -> None:
    dsn = (url_banco.set(drivername="postgresql", database="postgres")).render_as_string(
        hide_password=False
    )
    with psycopg.connect(dsn, autocommit=True) as conexao, conexao.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (url_banco.database,))
        if cursor.fetchone() is None:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(url_banco.database)))


def _aplica_migracao(url_banco: URL) -> None:
    ambiente = dict(os.environ)
    ambiente["DATABASE_URL"] = url_banco.render_as_string(hide_password=False)
    # Mesmo cuidado de `tests/f14/hardening/conftest.py`: `alembic/env.py`
    # prioriza DATABASE_URL_SYNC, e herda-lo do ambiente aplicaria a migracao
    # no banco errado em silencio.
    ambiente["DATABASE_URL_SYNC"] = url_banco.set(drivername="postgresql+psycopg").render_as_string(
        hide_password=False
    )
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
            "alembic upgrade head falhou ao preparar o banco de teste facial:\n"
            f"--- stdout ---\n{resultado.stdout}\n--- stderr ---\n{resultado.stderr}"
        )


@pytest.fixture(scope="session")
def url_banco_facial() -> URL:
    url_banco = _url_banco_teste()
    _garantir_banco_existe(url_banco)
    _aplica_migracao(url_banco)
    return url_banco


@pytest.fixture(scope="session", autouse=True)
def _chave_mestra_biometria() -> None:
    """KEK descartavel para `app.biometria.cifra` (ADR-006 regra 1).

    Definida so se o ambiente nao trouxer: quem roda contra um banco que ja tem
    templates cifrados precisa da MESMA chave, e sobrescreve-la aqui tornaria a
    base ilegivel.
    """
    os.environ.setdefault(VARIAVEL_KEK, secrets.token_hex(32))


@pytest_asyncio.fixture
async def engine_facial(url_banco_facial: URL) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(url_banco_facial, pool_pre_ping=True, pool_size=5, max_overflow=2)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def sessao_facial(engine_facial: AsyncEngine) -> AsyncIterator[AsyncSession]:
    fabrica = async_sessionmaker(engine_facial, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        yield sessao
        await sessao.rollback()


# ---------------------------------------------------------------------------
# facial-svc real
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def url_facial_svc() -> str:
    """URL do `facial-svc` real, ou PULA a suite inteira.

    O `/health` e conferido de proposito, e nao so a presenca da variavel: um
    endereco que nao responde produziria uma suite inteira "passando" pelo
    caminho de indisponibilidade, que e justamente o caminho que NAO prova
    reconhecimento nenhum.
    """
    url = os.environ.get(VARIAVEL_FACIAL, "").strip()
    if not url:
        pytest.skip(f"{VARIAVEL_FACIAL} nao definida: sem facial-svc real para exercitar.")
    try:
        resposta = httpx.get(f"{url.rstrip('/')}/health", timeout=10.0)
    except httpx.HTTPError as exc:  # pragma: no cover - so em ambiente sem o servico
        pytest.skip(f"facial-svc inalcancavel em {url}: {exc}")
    if resposta.status_code != 200:  # pragma: no cover
        pytest.skip(f"facial-svc respondeu {resposta.status_code} em {url}/health")
    return url


@pytest.fixture
def apontar_para_facial_svc(url_facial_svc: str) -> Iterator[str]:
    """Publica `FACIAL_SVC_URL` no ambiente e limpa o cache da configuracao.

    `app.core.config.obter_configuracao` e `lru_cache`; sem o `cache_clear` a
    aplicacao continuaria falando com o `http://facial-svc:8000` do compose.
    """
    yield from _apontar(url_facial_svc)


@pytest.fixture
def apontar_para_facial_svc_fora_do_ar() -> Iterator[str]:
    """Endereco de loopback numa porta fechada: `ConnectError` imediato.

    Melhor que um `mock` de `httpx` porque exercita o caminho de erro REAL do
    transporte (o mesmo que um container derrubado produz), incluindo o
    `async with cliente` e a traducao em `FacialSvcIndisponivel`.
    """
    # Porta alta reservada por IANA para uso privado; nada escuta nela.
    yield from _apontar("http://127.0.0.1:9")


def _apontar(url: str) -> Any:
    from app.core.config import obter_configuracao

    antigo = os.environ.get("FACIAL_SVC_URL")
    os.environ["FACIAL_SVC_URL"] = url
    obter_configuracao.cache_clear()
    try:
        yield url
    finally:
        if antigo is None:
            os.environ.pop("FACIAL_SVC_URL", None)
        else:
            os.environ["FACIAL_SVC_URL"] = antigo
        obter_configuracao.cache_clear()


# ---------------------------------------------------------------------------
# Fotos: seis pessoas reais, duas capturas diferentes da primeira
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Fotos:
    """Tres capturas JPEG em base64, prontas para o corpo das rotas.

    `pessoa_a_cadastro` e `pessoa_a_marcacao` sao a MESMA pessoa em dois
    recortes diferentes (margem, escala e requantizacao JPEG distintas) -- nao
    duas copias do mesmo arquivo, que provaria so que bytes iguais sao iguais.
    `pessoa_b` e outra pessoa da mesma foto de grupo.
    """

    pessoa_a_cadastro: str
    pessoa_a_marcacao: str
    pessoa_b: str


@dataclass(frozen=True, slots=True)
class Cena:
    """A foto de grupo `t1` com os seis rostos ja localizados, mais os dois
    utilitarios que recortam e codificam. Compartilhada por `fotos` (captura
    unica, para `/enroll` e `/verificar`) e por `quadros` (sequencias, para
    `/liveness`) -- carregar o motor ONNX duas vezes so para preparar fixture
    custa segundos por suite sem provar nada."""

    imagem: Any
    caixas: list[Any]
    jpeg: Any
    recorte: Any


@pytest.fixture(scope="session")
def cena() -> Cena:
    cv2 = pytest.importorskip("cv2", reason="opencv-python-headless nao instalado")
    pytest.importorskip("onnxruntime", reason="onnxruntime nao instalado")
    dados = pytest.importorskip("insightface.data", reason="insightface nao instalado")
    from facial.motor import motor

    instancia = motor()
    try:
        instancia.carregar()
    except Exception as exc:  # pragma: no cover - ambiente sem pesos
        pytest.skip(f"motor facial indisponivel para preparar as fixtures: {exc}")

    imagem = dados.get_image("t1")
    rostos = instancia.detectar(imagem)
    if len(rostos) < TOTAL_PESSOAS:  # pragma: no cover - troca de pacote de modelos
        pytest.skip(f"esperados {TOTAL_PESSOAS} rostos em t1, detectados {len(rostos)}")
    # Ordem estavel por posicao horizontal (`detectar` ordena por area, que
    # muda com o recorte) -- o mesmo criterio de `test_motor_facial.py`.
    caixas = sorted((r.bbox for r in rostos), key=lambda b: float(b[0]))

    def _jpeg(matriz: Any, qualidade: int = 90) -> str:
        ok, buffer = cv2.imencode(".jpg", matriz, [cv2.IMWRITE_JPEG_QUALITY, qualidade])
        assert ok, "falha ao codificar JPEG na fixture"
        return base64.b64encode(buffer.tobytes()).decode("ascii")

    def _recorte(
        caixa: Any,
        *,
        margem: float,
        escala: float,
        deslocamento: tuple[int, int] = (0, 0),
    ) -> Any:
        """`deslocamento` move a janela alguns pixels -- e o que produz
        MOVIMENTO entre quadros sem inventar pixel nenhum: a mesma cena,
        enquadrada um pouco diferente, que e o que uma mao segurando um celular
        faz. Mesma tecnica de `apps/facial-svc/tests/test_motor_facial.py`."""
        altura, largura = imagem.shape[:2]
        x1, y1, x2, y2 = (float(v) for v in caixa[:4])
        mx, my = (x2 - x1) * margem, (y2 - y1) * margem
        dx, dy = deslocamento
        a, b = max(0, int(x1 - mx) + dx), max(0, int(y1 - my) + dy)
        c, d = min(largura, int(x2 + mx) + dx), min(altura, int(y2 + my) + dy)
        return cv2.resize(
            imagem[b:d, a:c], None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC
        )

    return Cena(imagem=imagem, caixas=caixas, jpeg=_jpeg, recorte=_recorte)


@pytest.fixture(scope="session")
def fotos(cena: Cena) -> Fotos:
    return Fotos(
        pessoa_a_cadastro=cena.jpeg(cena.recorte(cena.caixas[0], margem=0.35, escala=2.0), 92),
        pessoa_a_marcacao=cena.jpeg(cena.recorte(cena.caixas[0], margem=0.55, escala=1.5), 74),
        pessoa_b=cena.jpeg(cena.recorte(cena.caixas[1], margem=0.35, escala=2.0), 92),
    )


# ---------------------------------------------------------------------------
# Quadros: as sequencias de prova de vida
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Quadros:
    """Quatro sequencias da MESMA pessoa (a cadastrada como `pessoa_a`).

    `vivos` e a unica que deve aprovar. As tres negativas reproduzem os ataques
    que a heuristica de `facial/motor/liveness.py` se propoe a pegar -- e sao
    **simulacoes declaradas**, nao ataques reais: a grade senoidal imita o
    batimento de uma tela fotografada, o desfoque com contraste achatado imita
    papel fosco, e o quadro repetido e literalmente uma foto parada diante da
    camera. Testar com um celular apontado para um monitor de verdade exige
    hardware na mao (F8), e a limitacao esta declarada no proprio motor.
    """

    vivos: list[str]
    tela: list[str]
    papel: list[str]
    congelado: list[str]


#: Deslocamentos aplicados entre quadros consecutivos. Poucos pixels: o
#: suficiente para passar de `MOVIMENTO_MINIMO` (1% da distancia interocular) e
#: longe de `MOVIMENTO_MAXIMO`, que caracterizaria troca de cena.
_PASSOS = ((0, 0), (4, -3), (-3, 4))


@pytest.fixture(scope="session")
def quadros(cena: Cena) -> Quadros:
    cv2 = pytest.importorskip("cv2", reason="opencv-python-headless nao instalado")
    np = pytest.importorskip("numpy", reason="numpy nao instalado")
    caixa = cena.caixas[0]

    def _bases() -> list[Any]:
        return [
            cena.recorte(caixa, margem=0.4, escala=2.0, deslocamento=passo) for passo in _PASSOS
        ]

    vivos = [cena.jpeg(base, 92) for base in _bases()]

    tela = []
    for base in _bases():
        altura, largura = base.shape[:2]
        ys, xs = np.mgrid[0:altura, 0:largura]
        # Batimento de periodo 3 px: a assinatura que a grade de subpixels de um
        # monitor produz quando fotografada por outra camera.
        grade = 12 * np.sin(2 * np.pi * xs / 3.0) + 12 * np.sin(2 * np.pi * ys / 3.0)
        borrada = cv2.GaussianBlur(base.astype(np.float32), (3, 3), 0.8)
        tela.append(cena.jpeg(np.clip(borrada + grade[..., None], 0, 255).astype(np.uint8), 88))

    # Papel fosco: some a microtextura da pele (desfoque), o contraste achata e o
    # JPEG agressivo termina o servico.
    papel = [
        cena.jpeg(cv2.convertScaleAbs(cv2.GaussianBlur(base, (5, 5), 1.6), alpha=0.85, beta=18), 60)
        for base in _bases()
    ]

    return Quadros(vivos=vivos, tela=tela, papel=papel, congelado=[vivos[0]] * 3)


# ---------------------------------------------------------------------------
# Semente: tenant, empresa, unidade, REP-P, colaborador, vinculo, consentimento
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ContextoFacial:
    tenant_id: uuid.UUID
    tenant_slug: str
    empresa_id: uuid.UUID
    colaborador_id: uuid.UUID
    consentimento_id: uuid.UUID
    usuario_id: uuid.UUID


@pytest_asyncio.fixture
async def contexto_facial(sessao_facial: AsyncSession) -> ContextoFacial:
    """Semente minima para cadastrar biometria E registrar ponto no canal
    `totem` (escolhido porque nao exige vinculo de dispositivo pessoal, como
    `mobile`, nem reautenticacao recente, como `web`).

    A politica gravada e explicita em vez de herdar os `DEFAULT` da coluna:
    `exige_facial` ligado (e o sinal em teste), geocerca/rede/attestation/
    liveness desligados (nao ha fonte real para eles nesta suite, e deixa-los
    ligados mediria o penalizador de sinal ausente, nao o facial).
    """
    sufixo = uuid.uuid4().hex[:12]
    tenant_id = uuid.uuid4()
    tenant_slug = f"facial-{sufixo}"
    hoje = dt.date.today()

    def _digitos(quantidade: int) -> str:
        return str(uuid.uuid4().int)[:quantidade].zfill(quantidade)

    await sessao_facial.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_id)}
    )
    await sessao_facial.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status, plano) "
            "VALUES (:id, :slug, 'Tenant de teste facial', 'Tenant Facial', 'ativo', 'enterprise')"
        ),
        {"id": tenant_id, "slug": tenant_slug},
    )

    empresa_id = uuid.uuid4()
    empresa_cnpj = _digitos(14)
    await sessao_facial.execute(
        text(
            "INSERT INTO empresas "
            "(id, tenant_id, tipo, cnpj, razao_social, nome_fantasia, uf, codigo_ibge_municipio) "
            "VALUES (:id, :t, 'matriz', :cnpj, 'Empresa Facial Ltda', 'Empresa Facial', "
            "        'GO', '5208707')"
        ),
        {"id": empresa_id, "t": tenant_id, "cnpj": empresa_cnpj},
    )

    unidade_id = uuid.uuid4()
    await sessao_facial.execute(
        text(
            "INSERT INTO unidades "
            "(id, tenant_id, empresa_id, codigo, nome, tipo, uf, codigo_ibge_municipio) "
            "VALUES (:id, :t, :e, 'SEDE', 'Sede facial', 'sede', 'GO', '5208707')"
        ),
        {"id": unidade_id, "t": tenant_id, "e": empresa_id},
    )

    rep_p_id = uuid.uuid4()
    await sessao_facial.execute(
        text(
            "INSERT INTO rep_ps "
            "(id, tenant_id, empresa_id, identificador, tipo, numero_inpi, cnpj_desenvolvedor, "
            " razao_social_desenvolvedor, cnpj_empregador, razao_social_empregador, "
            " versao_programa, data_inicio_operacao, status) "
            "VALUES (:id, :t, :e, :ident, 'rep_p', '12345678', '60258502000149', "
            "        'SEEG Sistemas Ltda', :cnpj, 'Empresa Facial Ltda', '1.0.0-teste', "
            "        :inicio, 'ativo')"
        ),
        {
            "id": rep_p_id,
            "t": tenant_id,
            "e": empresa_id,
            "ident": f"REP-{sufixo}",
            "cnpj": empresa_cnpj,
            "inicio": hoje,
        },
    )
    await sessao_facial.execute(
        text(
            "INSERT INTO nsr_sequencias (id, tenant_id, rep_p_id, proximo_nsr, ultimo_nsr_emitido) "
            "VALUES (:id, :t, :r, 1, 0)"
        ),
        {"id": uuid.uuid4(), "t": tenant_id, "r": rep_p_id},
    )

    colaborador_id = uuid.uuid4()
    await sessao_facial.execute(
        text(
            "INSERT INTO colaboradores "
            "(id, tenant_id, empresa_id, matricula, cpf, nome_completo, status, data_admissao) "
            "VALUES (:id, :t, :e, :mat, :cpf, 'Colaborador Facial', 'ativo', :adm)"
        ),
        {
            "id": colaborador_id,
            "t": tenant_id,
            "e": empresa_id,
            "mat": sufixo[:10],
            "cpf": _digitos(11),
            "adm": hoje - dt.timedelta(days=365),
        },
    )
    await sessao_facial.execute(
        text(
            "INSERT INTO vinculos "
            "(id, tenant_id, colaborador_id, empresa_id, matricula_esocial, tipo_vinculo, "
            " unidade_id, data_inicio, principal, apura_ponto, status) "
            "VALUES (:id, :t, :c, :e, :mat, 'empregado', :u, :inicio, TRUE, TRUE, 'ativo')"
        ),
        {
            "id": uuid.uuid4(),
            "t": tenant_id,
            "c": colaborador_id,
            "e": empresa_id,
            "mat": sufixo[:10],
            "u": unidade_id,
            "inicio": hoje - dt.timedelta(days=365),
        },
    )

    # Consentimento especifico e destacado para biometria facial: sem ele
    # `criarBiometria` recusa com PONTO-LGPD-001 (ADR-006 regra 7).
    consentimento_id = uuid.uuid4()
    await sessao_facial.execute(
        text(
            "INSERT INTO consentimentos "
            "(id, tenant_id, colaborador_id, finalidade, versao_termo, texto_termo_ref, "
            " hash_termo, status, concedido_em, canal) "
            "VALUES (:id, :t, :c, 'biometria_facial', 'v1', 'termos/biometria-facial-v1.txt', "
            "        :hash, 'concedido', now(), 'web')"
        ),
        {
            "id": consentimento_id,
            "t": tenant_id,
            "c": colaborador_id,
            # `dom_sha256`: 64 caracteres hex. Hash do texto exato que o titular
            # leu -- aqui, de um termo de teste.
            "hash": hashlib.sha256(b"termo de biometria facial, teste").hexdigest(),
        },
    )

    await sessao_facial.execute(
        text(
            "INSERT INTO politicas_registro "
            "(id, tenant_id, empresa_id, unidade_id, canal, exige_geocerca, exige_facial, "
            " exige_liveness, exige_attestation, exige_rede_permitida, exige_reautenticacao, "
            " limiar_bloqueio, limiar_revisao, politica_modo_desenvolvedor, politica_root, "
            " politica_mock_location) "
            "VALUES (:id, :t, :e, NULL, 'totem', FALSE, TRUE, FALSE, FALSE, FALSE, FALSE, "
            "        20, 70, 'permitir', 'permitir', 'permitir')"
        ),
        {"id": uuid.uuid4(), "t": tenant_id, "e": empresa_id},
    )

    # Usuario REAL, e nao um UUID inventado: `acessos_dados_sensiveis` tem FK
    # para `usuarios`, e e justamente essa tabela que ADR-006 regra 6 exige que
    # cada leitura de template alimente -- um sujeito de teste sem linha em
    # `usuarios` faria a auditoria estourar em vez de gravar.
    usuario_id = uuid.uuid4()
    await sessao_facial.execute(
        text(
            "INSERT INTO usuarios (id, tenant_id, email, nome_completo, tipo, status) "
            "VALUES (:id, :t, :email, 'Operador de teste facial', 'humano', 'ativo')"
        ),
        {"id": usuario_id, "t": tenant_id, "email": f"facial-{sufixo}@exemplo.com"},
    )

    await sessao_facial.commit()
    return ContextoFacial(
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        empresa_id=empresa_id,
        colaborador_id=colaborador_id,
        consentimento_id=consentimento_id,
        usuario_id=usuario_id,
    )


PERMISSOES_TESTE = frozenset(
    {"biometrias.criar", "biometrias.ler", "biometrias.aprovar", "marcacoes.criar"}
)


@pytest_asyncio.fixture
async def cliente_facial_http(
    url_banco_facial: URL, contexto_facial: ContextoFacial
) -> AsyncIterator[AsyncClient]:
    """Aplicacao REAL (roteador, Pydantic, RLS, middlewares) contra o banco
    desta suite. So o sujeito autenticado e sobrescrito -- mesma tecnica e
    mesma justificativa de `tests/f14/hardening/conftest.py`."""
    from app.core.config import obter_configuracao
    from app.core.seguranca import obter_sujeito
    from app.db.sessao import encerrar_engine
    from app.main import criar_aplicacao

    antigo = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url_banco_facial.render_as_string(hide_password=False)
    obter_configuracao.cache_clear()
    await encerrar_engine()
    try:
        aplicacao = criar_aplicacao()
        aplicacao.dependency_overrides[obter_sujeito] = lambda: Sujeito(
            usuario_id=contexto_facial.usuario_id,
            tenant_id=contexto_facial.tenant_id,
            email="teste-facial@exemplo.com",
            perfis=("perfil-teste-facial",),
            permissoes=PERMISSOES_TESTE,
            autenticado=True,
            alcance=AlcanceEfetivo(amplo_tenant=True),
        )
        async with AsyncClient(
            transport=ASGITransport(app=aplicacao), base_url="http://test"
        ) as cliente:
            yield cliente
    finally:
        await encerrar_engine()
        if antigo is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = antigo
        obter_configuracao.cache_clear()


def cabecalhos(tenant_slug: str) -> dict[str, str]:
    return {"X-Tenant": tenant_slug, "Idempotency-Key": f"facial-{uuid.uuid4()}"}
