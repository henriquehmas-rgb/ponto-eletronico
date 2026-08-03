"""`app.identidade.sso.oidc.protocolo`: troca de code por id_token e validacao
de assinatura/emissor/audiencia/nonce, contra um IdP FALSO local
(`httpx.MockTransport`) -- nunca rede real, mesmo padrao que ADR-013 exige
("ate la, os testes automatizados usam credenciais de teste/mock do
provedor, nunca um app real")."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx
import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from app.core.erros import ErroDeAplicacao
from app.identidade.sso.oidc import protocolo
from app.identidade.sso.oidc.provedores import ProvedorOidc

KID = "kid-teste-1"


@dataclass(frozen=True, slots=True)
class IdpFalso:
    provedor: ProvedorOidc
    emitir_id_token: Callable[..., str]
    jwks: dict[str, object]
    transporte: httpx.MockTransport


def _montar_idp_falso(
    *, nome: str = "google", issuer: str = "https://accounts.google.com"
) -> IdpFalso:
    chave_privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    chave_publica = chave_privada.public_key()
    jwk = json.loads(RSAAlgorithm.to_jwk(chave_publica))
    jwk.update({"kid": KID, "use": "sig", "alg": "RS256"})
    jwks = {"keys": [jwk]}

    provedor = ProvedorOidc(
        nome=nome,
        authorization_endpoint=f"https://idp-falso.teste/{nome}/authorize",
        token_endpoint=f"https://idp-falso.teste/{nome}/token",
        jwks_uri=f"https://idp-falso.teste/{nome}/jwks",
        issuer=issuer if nome == "google" else "",
        client_id="client-id-teste",
        client_secret="client-secret-teste",  # noqa: S106 -- valor de teste
    )

    id_token_atual: dict[str, str] = {}

    def emitir_id_token(*, chave: object = chave_privada, **claims_extra: object) -> str:
        agora = int(time.time())
        claims = {
            "iss": issuer,
            "aud": provedor.client_id,
            "sub": "usuario-externo-123",
            "email": "pessoa@empresa-teste-f13a9.com.br",
            "email_verified": True,
            "iat": agora,
            "exp": agora + 300,
            **claims_extra,
        }
        token = pyjwt.encode(claims, chave, algorithm="RS256", headers={"kid": KID})
        id_token_atual["valor"] = token
        return token

    # emite um token padrao de imediato para o handler abaixo ter algo a
    # devolver antes do teste chamar `emitir_id_token` explicitamente.
    emitir_id_token()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/jwks"):
            return httpx.Response(200, json=jwks)
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"id_token": id_token_atual["valor"]})
        return httpx.Response(404)

    return IdpFalso(
        provedor=provedor,
        emitir_id_token=emitir_id_token,
        jwks=jwks,
        transporte=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_trocar_code_por_claims_com_id_token_valido() -> None:
    idp = _montar_idp_falso()
    idp.emitir_id_token(nonce="nonce-esperado")

    async with httpx.AsyncClient(transport=idp.transporte) as cliente:
        claims = await protocolo.trocar_code_por_claims(
            idp.provedor,
            code="codigo-qualquer",
            redirect_uri="https://api.teste/v1/sso/google/callback",
            nonce_esperado="nonce-esperado",
            cliente_http=cliente,
        )

    assert claims.sub == "usuario-externo-123"
    assert claims.email == "pessoa@empresa-teste-f13a9.com.br"
    assert claims.email_verificado is True


@pytest.mark.asyncio
async def test_trocar_code_por_claims_nonce_errado_rejeita() -> None:
    idp = _montar_idp_falso()
    idp.emitir_id_token(nonce="nonce-correto")

    async with httpx.AsyncClient(transport=idp.transporte) as cliente:
        with pytest.raises(ErroDeAplicacao) as excinfo:
            await protocolo.trocar_code_por_claims(
                idp.provedor,
                code="codigo-qualquer",
                redirect_uri="https://api.teste/v1/sso/google/callback",
                nonce_esperado="nonce-diferente",
                cliente_http=cliente,
            )
    assert excinfo.value.codigo == "PONTO-AUTH-004"


@pytest.mark.asyncio
async def test_trocar_code_por_claims_assinatura_invalida_rejeita() -> None:
    idp = _montar_idp_falso()
    # Assina com uma chave DIFERENTE da publicada no JWKS real do IdP falso,
    # mas reaproveitando o mesmo `kid` -- `_selecionar_chave_de_assinatura`
    # escolhe a chave PUBLICA correta pelo `kid`, e a verificacao de
    # assinatura contra ela deve falhar porque o token foi assinado por outra
    # chave privada.
    outra_chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    idp.emitir_id_token(chave=outra_chave, nonce="n")

    async with httpx.AsyncClient(transport=idp.transporte) as cliente:
        with pytest.raises(ErroDeAplicacao) as excinfo:
            await protocolo.trocar_code_por_claims(
                idp.provedor,
                code="codigo-qualquer",
                redirect_uri="https://api.teste/v1/sso/google/callback",
                nonce_esperado="n",
                cliente_http=cliente,
            )
    assert excinfo.value.codigo == "PONTO-AUTH-004"


@pytest.mark.asyncio
async def test_trocar_code_por_claims_audiencia_errada_rejeita() -> None:
    idp = _montar_idp_falso()
    idp.emitir_id_token(nonce="n", aud="outro-client-id-qualquer")

    async with httpx.AsyncClient(transport=idp.transporte) as cliente:
        with pytest.raises(ErroDeAplicacao) as excinfo:
            await protocolo.trocar_code_por_claims(
                idp.provedor,
                code="codigo-qualquer",
                redirect_uri="https://api.teste/v1/sso/google/callback",
                nonce_esperado="n",
                cliente_http=cliente,
            )
    assert excinfo.value.codigo == "PONTO-AUTH-004"


@pytest.mark.asyncio
async def test_trocar_code_por_claims_entra_id_valida_emissor_por_tid() -> None:
    tid = "22222222-3333-4444-5555-666666666666"
    idp = _montar_idp_falso(nome="entra_id", issuer=f"https://login.microsoftonline.com/{tid}/v2.0")
    idp.emitir_id_token(nonce="n", tid=tid)

    async with httpx.AsyncClient(transport=idp.transporte) as cliente:
        claims = await protocolo.trocar_code_por_claims(
            idp.provedor,
            code="codigo-qualquer",
            redirect_uri="https://api.teste/v1/sso/entra_id/callback",
            nonce_esperado="n",
            cliente_http=cliente,
        )
    assert claims.tid == tid


@pytest.mark.asyncio
async def test_trocar_code_por_claims_entra_id_tid_nao_bate_com_issuer_rejeita() -> None:
    tid_real = "22222222-3333-4444-5555-666666666666"
    idp = _montar_idp_falso(
        nome="entra_id", issuer=f"https://login.microsoftonline.com/{tid_real}/v2.0"
    )
    # `tid` da claim diverge do diretorio que assinou (`iss`) o token.
    idp.emitir_id_token(nonce="n", tid="99999999-0000-1111-2222-333333333333")

    async with httpx.AsyncClient(transport=idp.transporte) as cliente:
        with pytest.raises(ErroDeAplicacao) as excinfo:
            await protocolo.trocar_code_por_claims(
                idp.provedor,
                code="codigo-qualquer",
                redirect_uri="https://api.teste/v1/sso/entra_id/callback",
                nonce_esperado="n",
                cliente_http=cliente,
            )
    assert excinfo.value.codigo == "PONTO-AUTH-004"


@pytest.mark.asyncio
async def test_trocar_code_por_claims_token_endpoint_fora_do_ar_e_int003() -> None:
    provedor = ProvedorOidc(
        nome="google",
        authorization_endpoint="https://idp-inalcancavel.invalido/authorize",
        token_endpoint="https://idp-inalcancavel.invalido/token",  # noqa: S106 -- URL, nao segredo
        jwks_uri="https://idp-inalcancavel.invalido/jwks",
        issuer="https://accounts.google.com",
        client_id="x",
        client_secret="y",  # noqa: S106 -- valor de teste
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("recusado (mock)", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as cliente:
        with pytest.raises(ErroDeAplicacao) as excinfo:
            await protocolo.trocar_code_por_claims(
                provedor,
                code="codigo-qualquer",
                redirect_uri="https://api.teste/v1/sso/google/callback",
                nonce_esperado="n",
                cliente_http=cliente,
            )
    assert excinfo.value.codigo == "PONTO-INT-003"
