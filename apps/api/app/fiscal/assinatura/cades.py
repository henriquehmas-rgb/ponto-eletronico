"""Assinatura e verificacao CAdES-BES em CMS/PKCS#7 destacado (F12/A3, T11).

Modulo generico sobre bytes/certificado -- nao sabe o que e um AFD, um AEJ
ou um comprovante, nao toca banco nem MinIO (isso e `servico.py`). PCF F12
secao 2.4: o mecanismo de assinatura e REAL e COMPLETO, funciona com
QUALQUER par certificado/chave privada (inclusive autoassinado) -- o que
falta sem o e-CNPJ A1 real da SEEG nao e a capacidade de assinar, e a cadeia
de confianca ate uma Autoridade Certificadora da ICP-Brasil.

`assinar_cades`
    Usa `cryptography.hazmat.primitives.serialization.pkcs7`, ja dependencia
    de `apps/api` (nenhuma dependencia nova). Confirmado por inspecao direta
    (nao presumido): o builder da `cryptography`, por padrao (sem passar
    `PKCS7Options.NoAttributes`), inclui os atributos assinados
    `content-type`, `signing-time` e `message-digest` -- exatamente o minimo
    exigido pelo perfil **CAdES-BES** (RFC 5126 / ETSI TS 101 733). Com
    `PKCS7Options.DetachedSignature`, o conteudo original NAO fica embutido
    no CMS (`.p7s` destacado, formato exigido para o AFD pelo leiaute --
    `docs/leiaute-afd-aej.md` secao 11).

`validar_cades`
    A API `pkcs7` da `cryptography` so contrutor (assinar), nao expoe leitura/
    verificacao de uma estrutura CMS `SignedData` arbitraria. Para uma
    verificacao **de verdade independente** (nao reaproveitar nenhum estado
    interno de quem assinou -- exigencia do PCF, T11), este modulo usa
    `asn1crypto` (biblioteca pura Python, sem binding nativo, BSD-licenciada,
    dependencia mediana usada por `certvalidator`/`oscrypto` no ecossistema
    Python de PKI) para: (1) desserializar o `ContentInfo`/`SignedData` em
    ASN.1 DER: (2) conferir que o atributo assinado `message-digest` bate com
    SHA-256 do conteudo; (3) re-serializar o conjunto de atributos assinados
    como `SET OF` (a estrutura ASN.1 universal, RFC 5652 secao 5.4 -- o CMS
    grava esse mesmo conjunto com a tag `[0] IMPLICIT` dentro do
    `SignerInfo`, mas o que e efetivamente assinado/verificado e a
    codificação DER do `SET OF` universal, no ORDINAL original dos
    atributos) e verificar a assinatura RSA-PKCS#1v1.5/SHA-256 contra a
    chave publica do certificado embutido no CMS. Nenhuma chamada de rede,
    nenhuma consulta a CRL/OCSP, nenhuma validacao de cadeia ate uma raiz
    ICP-Brasil -- essa parte fica documentada como NAO VERIFICAVEL (PCF F12
    secao 2.4/ criterio de aceite 3), porque nao ha acesso a uma Autoridade
    Certificadora real nesta fase.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
from dataclasses import dataclass, field
from typing import Any

from asn1crypto import cms as _asn1_cms
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs7

from app.fiscal.assinatura.certificado import CertificadoConfig

#: Perfil CAdES-BES minimo (RFC 5126): estes tres atributos assinados
#: precisam estar presentes. `signing-time` e o "S" de BES (a marca de
#: quando a assinatura foi produzida -- nao e o carimbo de tempo de uma TSA,
#: que exigiria um servico de carimbo credenciado, proibicao 9 do PCF).
ATRIBUTOS_CADES_BES_MINIMOS: frozenset[str] = frozenset(
    {"content_type", "signing_time", "message_digest"}
)


def assinar_cades(conteudo: bytes, certificado: CertificadoConfig) -> bytes:
    """Produz a assinatura CMS/PKCS#7 destacada (DER) de `conteudo`, perfil
    CAdES-BES, com o certificado/chave de `certificado`.

    `certificado` nunca e `None` aqui -- a checagem de "certificado ausente"
    (que vira `PONTO-FISC-004`) acontece no chamador (`servico.py`), antes de
    esta funcao ser invocada.

    **`PKCS7Options.Binary` e OBRIGATORIO, achado por teste, nao por leitura
    da documentacao.** Sem essa opcao, a `cryptography.pkcs7` aplica a
    "formatacao canonica MIME" que o S/MIME classico exige (RFC 5751) ANTES
    de calcular o `message-digest`: todo `\\n` isolado (sem `\\r` antes) vira
    `\\r\\n`. Isso e invisivel quando o conteudo ja usa só `\\r\\n` OU não tem
    quebra de linha nenhuma -- e por isso o primeiro teste manual deste
    modulo (uma unica linha, sem `\\n`) não pegou o problema. Descoberto ao
    testar contra `comprovantes.conteudo_texto` (que usa `\\n` puro, como
    todo texto Python): o `message-digest` gravado no CMS divergia do
    SHA-256 recalculado sobre os bytes originais em
    `validar_cades`. Para um arquivo de conformidade legal (AFD/AEJ/
    comprovante), qualquer transformacao implicita do conteudo antes de
    assinar é inaceitável -- `Binary` garante que os bytes assinados são
    EXATAMENTE os bytes recebidos, sem excecao. (O AFD/AEJ já usam CR+LF
    puro pelo leiaute, então o efeito prático nesses dois é nulo -- mas
    depender disso silenciosamente seria frágil; `Binary` remove a
    ambiguidade para os três tipos de arquivo que este módulo assina.)"""
    construtor = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(conteudo)
        .add_signer(certificado.certificado, certificado.chave_privada, hashes.SHA256())
    )
    return construtor.sign(
        serialization.Encoding.DER,
        [pkcs7.PKCS7Options.DetachedSignature, pkcs7.PKCS7Options.Binary],
    )


@dataclass(frozen=True, slots=True)
class ResultadoValidacao:
    """Evidencia da verificacao independente de uma assinatura CAdES.

    Grava-se literalmente este dicionario (via `dataclasses.asdict`) em
    `arquivo_assinaturas.validacao_resultado` -- rotulado em todo lugar como
    o que realmente e: verificacao ESTRUTURAL e de INTEGRIDADE (o `.p7s` e
    um CMS/PKCS#7 bem formado, o `message-digest` bate, a assinatura
    criptografica confere contra a chave publica do certificado embutido, o
    certificado esta dentro da janela de validade), nunca uma prova de
    cadeia de confianca ICP-Brasil (essa parte fica declarada como nao
    verificada, nunca omitida silenciosamente)."""

    estruturalmente_valido: bool
    message_digest_confere: bool
    assinatura_criptografica_valida: bool
    certificado_dentro_da_validade: bool
    algoritmo_digest: str | None
    algoritmo_assinatura: str | None
    instante_assinatura: str | None
    certificado_titular: str | None
    certificado_serial: str | None
    cadeia_confianca_icp_brasil_verificada: bool = field(default=False)
    motivo_falha: str | None = None

    @property
    def valido(self) -> bool:
        """Verdadeiro somente quando TODAS as checagens que este produto
        consegue fazer sem uma Autoridade Certificadora real passaram.
        Deliberadamente NAO inclui `cadeia_confianca_icp_brasil_verificada`
        na conta -- essa checagem nunca roda nesta fase (ver docstring da
        classe), entao exigi-la aqui tornaria `valido` sempre falso, o que
        esconderia a distincao que este relatorio precisa preservar entre
        "estruturalmente invalido" e "cadeia nao verificada"."""
        return (
            self.estruturalmente_valido
            and self.message_digest_confere
            and self.assinatura_criptografica_valida
            and self.certificado_dentro_da_validade
        )


def _resultado_invalido(motivo: str) -> ResultadoValidacao:
    return ResultadoValidacao(
        estruturalmente_valido=False,
        message_digest_confere=False,
        assinatura_criptografica_valida=False,
        certificado_dentro_da_validade=False,
        algoritmo_digest=None,
        algoritmo_assinatura=None,
        instante_assinatura=None,
        certificado_titular=None,
        certificado_serial=None,
        motivo_falha=motivo,
    )


#: Mapa de OID/nome legivel (asn1crypto) do algoritmo de digest para a
#: primitiva de `cryptography`. Só os algoritmos que `assinar_cades` produz
#: (SHA-256) precisam ser suportados de verdade; qualquer outro reprova a
#: verificacao em vez de assumir compatibilidade.
_DIGESTOS: dict[str, Any] = {"sha256": hashes.SHA256}

#: Idem, para o algoritmo de assinatura. `cryptography.pkcs7` so produz
#: RSASSA-PKCS1-v1_5 para chave RSA (confirmado por inspecao -- ver
#: docstring do modulo); EC nao e suportado por este verificador ainda
#: porque nao ha necessidade real nesta fase (certificado e-CNPJ A1 e RSA).
_ASSINATURAS_SUPORTADAS: frozenset[str] = frozenset({"rsassa_pkcs1v15"})


def validar_cades(
    conteudo: bytes,
    assinatura: bytes,
    *,
    certificado_esperado: bytes | None = None,
) -> ResultadoValidacao:
    """Verificacao independente: desserializa `assinatura` (CMS/PKCS#7 DER),
    confere `message-digest` contra SHA-256(`conteudo`), reconstroi os
    atributos assinados como `SET OF` e verifica a assinatura RSA contra a
    chave publica do certificado embutido no proprio CMS.

    `certificado_esperado`, quando informado (DER do certificado que
    deveria ter assinado), e comparado byte a byte contra o certificado
    embutido no CMS -- defesa contra substituicao do certificado sem
    invalidar a assinatura estruturalmente (o CMS em si nao amarra "este e
    o certificado autorizado", so "este certificado assinou isto")."""
    try:
        info = _asn1_cms.ContentInfo.load(assinatura)
    except Exception as exc:
        return _resultado_invalido(f"CMS ilegivel: {exc!r}")

    if info["content_type"].native != "signed_data":
        return _resultado_invalido(
            f"ContentInfo nao e SignedData (contentType={info['content_type'].native!r})"
        )
    assinado = info["content"]
    infos_assinantes = assinado["signer_infos"]
    if len(infos_assinantes) != 1:
        return _resultado_invalido(
            f"esperado exatamente 1 SignerInfo, encontrado {len(infos_assinantes)}"
        )
    signer_info = infos_assinantes[0]

    atributos_assinados = signer_info["signed_attrs"]
    if atributos_assinados.native is None:
        return _resultado_invalido("SignerInfo sem atributos assinados (nao e CAdES-BES)")
    tipos_presentes = {a["type"].native for a in atributos_assinados}
    faltando = ATRIBUTOS_CADES_BES_MINIMOS - tipos_presentes
    if faltando:
        return _resultado_invalido(f"atributos CAdES-BES ausentes: {sorted(faltando)}")

    message_digest_atributo = next(
        (
            a["values"][0].native
            for a in atributos_assinados
            if a["type"].native == "message_digest"
        ),
        None,
    )
    digest_esperado = hashlib.sha256(conteudo).digest()
    message_digest_confere = message_digest_atributo == digest_esperado

    instante_assinatura = next(
        (a["values"][0].native for a in atributos_assinados if a["type"].native == "signing_time"),
        None,
    )

    certificados = list(assinado["certificates"])
    if len(certificados) != 1:
        return _resultado_invalido(
            f"esperado exatamente 1 certificado embutido, encontrado {len(certificados)}"
        )
    certificado_asn1 = certificados[0].chosen
    certificado_der = certificado_asn1.dump()

    if certificado_esperado is not None and certificado_der != certificado_esperado:
        return _resultado_invalido(
            "certificado embutido no CMS difere do certificado esperado (possivel substituicao)"
        )

    from cryptography import x509 as _x509  # import local: evita ciclo com certificado.py

    certificado_cripto = _x509.load_der_x509_certificate(certificado_der)
    agora = _dt.datetime.now(_dt.UTC)
    certificado_dentro_da_validade = (
        certificado_cripto.not_valid_before_utc <= agora <= certificado_cripto.not_valid_after_utc
    )

    algoritmo_digest_nome = signer_info["digest_algorithm"]["algorithm"].native
    algoritmo_assinatura_nome = signer_info["signature_algorithm"]["algorithm"].native

    assinatura_criptografica_valida = False
    chave_publica = certificado_cripto.public_key()
    # `assinar_cades` (T11) so produz RSA-PKCS1v15/SHA-256 (unico algoritmo
    # que `_ASSINATURAS_SUPORTADAS` cobre) -- a checagem de tipo abaixo narra
    # isso estaticamente para o mypy (o retorno de `public_key()` e uma Union
    # de ~10 tipos de chave publica, a maioria sem um `.verify()` compativel
    # com `padding.PKCS1v15`) e, em runtime, recusa (nao verificado) qualquer
    # outro algoritmo em vez de tentar adivinhar a assinatura certa.
    if (
        algoritmo_digest_nome in _DIGESTOS
        and algoritmo_assinatura_nome in _ASSINATURAS_SUPORTADAS
        and isinstance(chave_publica, rsa.RSAPublicKey)
    ):
        # O que e efetivamente assinado num CMS nao e a codificacao "como
        # veio" do campo `signedAttrs` (tag de contexto `[0] IMPLICIT`), e
        # sim a codificacao DER do MESMO conteudo como `SET OF` universal
        # (RFC 5652 secao 5.4, paragrafo final) -- por isso a retag antes de
        # verificar.
        reetiquetado = atributos_assinados.copy()
        reetiquetado.class_ = 0  # UNIVERSAL
        reetiquetado.tag = 17  # SET OF
        bytes_assinados = reetiquetado.dump(force=True)
        try:
            chave_publica.verify(
                signer_info["signature"].native,
                bytes_assinados,
                padding.PKCS1v15(),
                _DIGESTOS[algoritmo_digest_nome](),
            )
            assinatura_criptografica_valida = True
        except InvalidSignature:
            assinatura_criptografica_valida = False

    return ResultadoValidacao(
        estruturalmente_valido=True,
        message_digest_confere=message_digest_confere,
        assinatura_criptografica_valida=assinatura_criptografica_valida,
        certificado_dentro_da_validade=certificado_dentro_da_validade,
        algoritmo_digest=algoritmo_digest_nome,
        algoritmo_assinatura=algoritmo_assinatura_nome,
        instante_assinatura=instante_assinatura.isoformat() if instante_assinatura else None,
        certificado_titular=certificado_cripto.subject.rfc4514_string(),
        certificado_serial=format(certificado_cripto.serial_number, "x"),
        cadeia_confianca_icp_brasil_verificada=False,
        motivo_falha=(
            None
            if (
                message_digest_confere
                and assinatura_criptografica_valida
                and certificado_dentro_da_validade
            )
            else (
                "ver campos individuais: message_digest_confere/"
                "assinatura_criptografica_valida/certificado_dentro_da_validade"
            )
        ),
    )
