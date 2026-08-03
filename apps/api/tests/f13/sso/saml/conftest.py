"""Fixture de banco e de IdP falso dos testes de SSO SAML (T20-T22, A10).

Self-contained, mesmo espirito de `apps/api/tests/f1/rbac/conftest.py` e
`apps/api/tests/f6/conftest.py`: nao depende de `apps/api/tests/f13/
conftest.py` (ownership exclusivo de A1, evoluindo em paralelo nesta mesma
janela) -- os testes de SAML precisam poder rodar sozinhos, sem acoplar ao
estado de um arquivo que outro agente esta editando ao mesmo tempo.

Conecta direto com `PONTO_TEST_DATABASE_URL` (banco exclusivo desta sessao,
`ponto_f13_a10`). `tenants`/`usuarios`/`tenant_configuracoes`/`credenciais`
estao sob `FORCE ROW LEVEL SECURITY` (`schema.sql`) mesmo para o DONO da
tabela -- toda insercao de fixture publica `app.tenant_id` explicitamente
antes de tocar o banco (`set_config`), mesmo mecanismo que
`app.db.sessao.aplicar_tenant` usa em producao. Nao precisa da role de LOGIN
restrita que `tests/f1/rbac`/`tests/f6` criam: aqueles testes existem para
PROVAR isolamento entre papeis; estes testam a LOGICA de SSO, e `FORCE ROW
LEVEL SECURITY` ja garante que mesmo a conexao administrativa da instancia de
teste nao le nada sem `app.tenant_id` publicado.

O "IdP falso" (`par_chaves_idp`, `montar_saml_response`) gera um certificado
X.509 autoassinado com `cryptography` e assina a asserção com `xmlsec`
diretamente (mesma dependencia transitiva de `python3-saml`) -- e o unico
jeito de produzir um SAMLResponse assinado de verdade para o teste
adversarial (assinatura adulterada) sem depender de um IdP externo real.
"""

from __future__ import annotations

import base64
import datetime as _dt
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
import sqlalchemy as sa
import xmlsec
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from lxml import etree
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

VARIAVEL_URL = "PONTO_TEST_DATABASE_URL"
URL_PADRAO = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto"

#: Chave de teste para `app.identidade.sso.saml.estado` (HS256 -- string
#: qualquer, ao contrario das chaves hex de AES do resto do projeto).
CHAVE_ESTADO_TESTE = "chave-de-teste-relay-state-f13-a10-nao-usar-em-producao"

_NS = {
    "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
}


def url_banco() -> str:
    return os.environ.get(VARIAVEL_URL, URL_PADRAO).strip()


@pytest.fixture(scope="session", autouse=True)
def _variaveis_de_ambiente(tmp_path_factory: pytest.TempPathFactory) -> None:
    from app.core.config import obter_configuracao
    from app.identidade.tokens import chaves as jwt_chaves

    os.environ.setdefault("SSO_SAML_ESTADO_CHAVE", CHAVE_ESTADO_TESTE)
    os.environ.setdefault("API_BASE_URL", "https://api.ponto.teste.local")
    os.environ.setdefault("WEB_BASE_URL", "https://app.ponto.teste.local")

    # `emitir_sessao` (resolucao.py) emite o MESMO access token RS256 que
    # `autenticar`/`renovarSessao` (F1) -- precisa de um par de chaves de
    # teste, mesmo padrao de `tests/f1/autenticacao/conftest.py:_chaves_rs256`
    # (duplicado aqui por ser self-contained, ver docstring do modulo).
    if not os.environ.get("JWT_PRIVATE_KEY_PATH"):
        diretorio = tmp_path_factory.mktemp("jwt-f13-a10")
        chave_privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        caminho_privada = diretorio / "private.pem"
        caminho_publica = diretorio / "public.pem"
        caminho_privada.write_bytes(
            chave_privada.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        caminho_publica.write_bytes(
            chave_privada.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
        os.environ["JWT_PRIVATE_KEY_PATH"] = str(caminho_privada)
        os.environ["JWT_PUBLIC_KEY_PATH"] = str(caminho_publica)

    # `obter_configuracao()`/`chave_privada()`/`chave_publica()` sao cacheadas
    # (`functools.lru_cache`) -- limpa os tres para que os valores acima
    # sejam lidos de verdade, mesmo que outro teste ja tenha instanciado a
    # configuracao antes deste fixture rodar.
    obter_configuracao.cache_clear()
    jwt_chaves.limpar_cache()


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(url_banco(), pool_pre_ping=True)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def sessao_db(
    engine: AsyncEngine, tenant_com_usuario: TenantComUsuario
) -> AsyncIterator[AsyncSession]:
    """Sessao com `app.tenant_id` ja publicado para `tenant_com_usuario`."""
    fabrica = sa.ext.asyncio.async_sessionmaker(bind=engine, expire_on_commit=False)
    async with fabrica() as sessao:
        await sessao.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"),
            {"tenant": str(tenant_com_usuario.tenant_id)},
        )
        yield sessao
        await sessao.rollback()


@dataclass(frozen=True, slots=True)
class TenantComUsuario:
    tenant_id: uuid.UUID
    slug: str
    usuario_id: uuid.UUID
    email: str


@pytest_asyncio.fixture
async def tenant_com_usuario(engine: AsyncEngine) -> AsyncIterator[TenantComUsuario]:
    tenant_id = uuid.uuid4()
    usuario_id = uuid.uuid4()
    slug = f"f13-a10-{tenant_id.hex[:8]}"
    email = f"colaborador.{tenant_id.hex[:8]}@f13-a10.teste"
    async with engine.begin() as conexao:
        await conexao.execute(
            text(
                "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, plano, status) "
                "VALUES (:id, :slug, 'F13 A10 Teste Ltda', 'F13 A10 Teste', 'padrao', 'ativo')"
            ),
            {"id": str(tenant_id), "slug": slug},
        )
        await conexao.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"),
            {"tenant": str(tenant_id)},
        )
        await conexao.execute(
            text(
                "INSERT INTO usuarios (id, tenant_id, email, nome_completo, tipo, status) "
                "VALUES (:id, :tenant_id, :email, 'Colaborador Teste SAML', 'humano', 'ativo')"
            ),
            {"id": str(usuario_id), "tenant_id": str(tenant_id), "email": email},
        )
    yield TenantComUsuario(tenant_id=tenant_id, slug=slug, usuario_id=usuario_id, email=email)


IDP_SSO_URL_TESTE = "https://idp-teste-f13-a10.example.com/sso"
IDP_ENTITY_ID_TESTE = "https://idp-teste-f13-a10.example.com/metadata"


@pytest_asyncio.fixture
async def tenant_com_saml_configurado(
    engine: AsyncEngine, tenant_com_usuario: TenantComUsuario, idp_falso: IdpFalso
) -> TenantComUsuario:
    """`tenant_com_usuario` + as tres chaves de `tenant_configuracoes` que
    `app.identidade.sso.oidc.configuracao` (A9) le/escreve para
    `GET/PUT /v1/admin/sso/provedores` -- aqui inseridas direto, sem passar
    pelo endpoint HTTP (que exige `admin.configurar`, achado de contrato
    documentado no relatorio da fase)."""
    async with engine.begin() as conexao:
        await conexao.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"),
            {"tenant": str(tenant_com_usuario.tenant_id)},
        )
        for chave, valor in (
            ("sso.saml.entity_id", IDP_ENTITY_ID_TESTE),
            ("sso.saml.sso_url", IDP_SSO_URL_TESTE),
            ("sso.saml.certificado_x509", idp_falso.certificado_pem_sem_marcadores),
        ):
            await conexao.execute(
                text(
                    "INSERT INTO tenant_configuracoes (tenant_id, categoria, chave, valor) "
                    "VALUES (:tenant_id, 'integracao', :chave, to_jsonb(CAST(:valor AS text)))"
                ),
                {"tenant_id": str(tenant_com_usuario.tenant_id), "chave": chave, "valor": valor},
            )
    return tenant_com_usuario


@dataclass(frozen=True, slots=True)
class IdpFalso:
    chave: rsa.RSAPrivateKey
    certificado: x509.Certificate

    @property
    def certificado_pem_sem_marcadores(self) -> str:
        pem = self.certificado.public_bytes(serialization.Encoding.PEM).decode("ascii")
        return "".join(
            linha for linha in pem.splitlines() if "BEGIN" not in linha and "END" not in linha
        )


@pytest.fixture(scope="session")
def idp_falso() -> IdpFalso:
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "idp-teste-f13-a10")])
    agora = _dt.datetime.now(_dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - _dt.timedelta(days=1))
        .not_valid_after(agora + _dt.timedelta(days=3650))
        .sign(chave, hashes.SHA256())
    )
    return IdpFalso(chave=chave, certificado=cert)


def montar_saml_response(
    idp: IdpFalso,
    *,
    name_id: str,
    audience: str,
    acs_url: str,
    issuer: str,
    in_response_to: str,
    valido_desde: _dt.datetime | None = None,
    vida: _dt.timedelta = _dt.timedelta(minutes=5),
    assinar: bool = True,
) -> str:
    """Monta um SAMLResponse (base64, sem deflate -- perfil HTTP-POST) com uma
    unica asserção, assinada pelo IdP falso. `assinar=False` devolve a
    asserção sem `<Signature>` nenhuma (usado pelo teste que confirma que
    `wantAssertionsSigned` rejeita ausencia de assinatura, nao so assinatura
    incorreta)."""
    agora = valido_desde or _dt.datetime.now(_dt.UTC)
    emitido = agora.strftime("%Y-%m-%dT%H:%M:%SZ")
    nao_apos = (agora + vida).strftime("%Y-%m-%dT%H:%M:%SZ")
    response_id = "_" + uuid.uuid4().hex
    assertion_id = "_" + uuid.uuid4().hex

    xml = f"""
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                 xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                 ID="{response_id}" Version="2.0" IssueInstant="{emitido}"
                 InResponseTo="{in_response_to}" Destination="{acs_url}">
  <saml:Issuer>{issuer}</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
  <saml:Assertion ID="{assertion_id}" Version="2.0" IssueInstant="{emitido}">
    <saml:Issuer>{issuer}</saml:Issuer>
    <saml:Subject>
      <saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
        >{name_id}</saml:NameID>
      <saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData NotOnOrAfter="{nao_apos}" Recipient="{acs_url}"
          InResponseTo="{in_response_to}"/>
      </saml:SubjectConfirmation>
    </saml:Subject>
    <saml:Conditions NotBefore="{emitido}" NotOnOrAfter="{nao_apos}">
      <saml:AudienceRestriction><saml:Audience>{audience}</saml:Audience></saml:AudienceRestriction>
    </saml:Conditions>
    <saml:AuthnStatement AuthnInstant="{emitido}" SessionIndex="_sess-{assertion_id}">
      <saml:AuthnContext><saml:AuthnContextClassRef>urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport</saml:AuthnContextClassRef></saml:AuthnContext>
    </saml:AuthnStatement>
  </saml:Assertion>
</samlp:Response>
""".strip()
    # S320: `lxml.etree.fromstring` em dado "nao confiavel" -- aqui o XML e
    # 100% montado por este proprio modulo (f-string acima), nunca por
    # entrada externa: e o "IdP falso" GERANDO a resposta, nao validando uma
    # de fora.
    doc = etree.fromstring(xml.encode("utf-8"))  # noqa: S320

    if assinar:
        doc = _assinar_assertion(doc, idp.chave, idp.certificado)

    return base64.b64encode(etree.tostring(doc)).decode("ascii")


def _assinar_assertion(
    doc: etree._Element, chave: rsa.RSAPrivateKey, cert: x509.Certificate
) -> etree._Element:
    assertion = doc.find(".//saml:Assertion", namespaces=_NS)
    assert assertion is not None
    signature_node = xmlsec.template.create(
        doc, xmlsec.constants.TransformExclC14N, xmlsec.constants.TransformRsaSha256
    )
    assertion_id = assertion.get("ID")
    issuer = assertion.find("saml:Issuer", namespaces=_NS)
    issuer.addnext(signature_node)
    ref = xmlsec.template.add_reference(
        signature_node, xmlsec.constants.TransformSha256, uri="#" + assertion_id
    )
    xmlsec.template.add_transform(ref, xmlsec.constants.TransformEnveloped)
    xmlsec.template.add_transform(ref, xmlsec.constants.TransformExclC14N)
    key_info = xmlsec.template.ensure_key_info(signature_node)
    xmlsec.template.add_x509_data(key_info)
    xmlsec.tree.add_ids(assertion, ["ID"])

    chave_pem = chave.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    ctx = xmlsec.SignatureContext()
    ctx.key = xmlsec.Key.from_memory(chave_pem, xmlsec.constants.KeyDataFormatPem)
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    ctx.key.load_cert_from_memory(cert_pem, xmlsec.constants.KeyDataFormatCertPem)
    ctx.sign(signature_node)
    return doc


def adulterar_name_id(saml_response_b64: str, *, de: str, para: str) -> str:
    """Troca o `NameID` DEPOIS de assinado, sem re-assinar -- o ataque que o
    criterio de aceite do T22 exige rejeitar."""
    xml = base64.b64decode(saml_response_b64)
    xml_adulterado = xml.replace(de.encode("utf-8"), para.encode("utf-8"))
    assert xml_adulterado != xml
    return base64.b64encode(xml_adulterado).decode("ascii")
