"""Configuracao do certificado ICP-Brasil usado na assinatura CAdES (F12/A3, T11).

**Achado de contrato registrado aqui, nao "resolvido por conta propria"**
(reportado no relatorio da fase para o orquestrador decidir se abre RFC de
limpeza): o PCF da F12 (secao 2.4/T11) instrui criar duas variaveis de
ambiente NOVAS -- `FISCAL_CERTIFICADO_PFX_PATH`/`FISCAL_CERTIFICADO_SENHA` --
e acrescentar um bloco `# 7. ASSINATURA FISCAL (CAdES)` em
`infra/.env.example`. Ao ler o andaime real da Fase 0 antes de codificar,
encontramos que ele **ja** provisiona exatamente esse par de credenciais,
de ponta a ponta, com nomes diferentes:

* `infra/.env.example`, bloco "12. CONFORMIDADE REP-P" (`INPI_NUMERO`,
  `CERT_ICP_PATH`, `CERT_ICP_SENHA`), ja comentado/vazio -- o padrao exato
  que o PCF pede para o bloco novo.
* `infra/docker-compose.yml` ja repassa `CERT_ICP_PATH`/`CERT_ICP_SENHA`
  para os containers `api` e `worker` (`${CERT_ICP_PATH:-}`/
  `${CERT_ICP_SENHA:-}`).
* `app.core.config.Configuracao.cert_icp_path`/`cert_icp_senha` (este
  arquivo, campo `SecretStr`) e `apps/worker/worker/config.py` (mesmos dois
  campos) ja leem essas variaveis, no mesmo padrao de `minio_endpoint`/
  `minio_access_key` que o PCF cita como referencia de estilo.

Duas variaveis diferentes apontando para o mesmo segredo (o `.pfx` do
certificado fiscal) e exatamente o tipo de ambiguidade perigosa que uma fase
de conformidade legal deveria evitar -- um operador poderia preencher
`FISCAL_CERTIFICADO_PFX_PATH` em produção sem saber que o codigo real le
`CERT_ICP_PATH`, e a aplicacao continuaria "sem certificado configurado"
silenciosamente. Por isso este modulo **reaproveita `cert_icp_path`/
`cert_icp_senha` (ja existentes) em vez de introduzir o par novo do PCF**.
Nenhuma variavel de ambiente nova foi criada; `infra/.env.example` nao foi
tocado (o bloco que o PCF pedia ja existe, com outro nome). Ver o relatorio
da fase para a decisao registrada e a sugestao de RFC cosmetica para
alinhar o texto do PCF a esta realidade.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.primitives.serialization.pkcs7 import PKCS7PrivateKeyTypes
from cryptography.x509.oid import NameOID

from app.core.config import Configuracao, obter_configuracao
from app.core.log import obter_logger

logger = obter_logger("fiscal.assinatura.certificado")

#: `isinstance` não aceita o alias `typing.Union` `PKCS7PrivateKeyTypes`
#: diretamente sob checagem estática (mypy recusa "parameterized generics"
#: em `isinstance`, mesmo que funcione em runtime) -- a tupla de classes
#: concretas abaixo é o mesmo conjunto, mas compatível com mypy.
_TIPOS_CHAVE_PKCS7_CONCRETOS = (rsa.RSAPrivateKey, ec.EllipticCurvePrivateKey)


@dataclass(frozen=True, slots=True)
class CertificadoConfig:
    """Par certificado/chave privada carregado do `.pfx`/`.p12` configurado,
    mais os metadados que `arquivo_assinaturas` guarda como evidencia.

    `rotulo_teste`, quando preenchido, marca que este certificado **nao** e
    um e-CNPJ A1 real da ICP-Brasil -- e o certificado autoassinado que os
    testes automatizados desta fase geram (PCF F12 secao 2.4). Nunca fica
    preenchido fora de teste: `carregar_de_arquivo` (o unico caminho usado
    em producao) nunca define este campo.
    """

    certificado: x509.Certificate
    chave_privada: PKCS7PrivateKeyTypes
    titular: str
    serial: str
    emissor: str
    validade_inicio: _dt.datetime
    validade_fim: _dt.datetime
    rotulo_teste: str | None = None

    @property
    def expirado(self) -> bool:
        """Verdadeiro quando `agora` esta fora da janela de validade do
        certificado (`not_before`/`not_after` do X.509). Isto e checagem de
        DATA, nao de cadeia ICP-Brasil nem de CRL/OCSP -- ver a ressalva do
        modulo `cades.py`/do relatorio da fase sobre o que este produto
        consegue verificar sem acesso a uma Autoridade Certificadora real."""
        agora = _dt.datetime.now(_dt.UTC)
        return agora < self.validade_inicio or agora > self.validade_fim


def _nome_comum(nome: x509.Name) -> str:
    atributos = nome.get_attributes_for_oid(NameOID.COMMON_NAME)
    if atributos:
        valor = atributos[0].value
        return valor if isinstance(valor, str) else valor.decode("utf-8", errors="replace")
    return nome.rfc4514_string()


def _config_a_partir_do_certificado(
    certificado: x509.Certificate,
    chave: PKCS7PrivateKeyTypes,
    *,
    rotulo_teste: str | None = None,
) -> CertificadoConfig:
    return CertificadoConfig(
        certificado=certificado,
        chave_privada=chave,
        titular=_nome_comum(certificado.subject),
        serial=format(certificado.serial_number, "x"),
        emissor=_nome_comum(certificado.issuer),
        validade_inicio=certificado.not_valid_before_utc,
        validade_fim=certificado.not_valid_after_utc,
        rotulo_teste=rotulo_teste,
    )


def carregar_de_arquivo(caminho: str | Path, senha: str) -> CertificadoConfig | None:
    """Carrega um `.pfx`/`.p12` do disco. Devolve `None` quando o caminho
    esta vazio, o arquivo nao existe, ou o conteudo nao e um PKCS#12 valido
    com chave privada + certificado -- em todos esses casos o chamador
    responde `PONTO-FISC-004` (certificado indisponivel), nunca levanta
    excecao aqui: "indisponivel" e um estado esperado desta fase (SEEG ainda
    nao tem o e-CNPJ A1 real, PCF F12 secao 2.4), nao um erro de programa."""
    caminho_str = str(caminho)
    if not caminho_str:
        return None
    caminho_path = Path(caminho_str)
    if not caminho_path.is_file():
        return None
    try:
        dados = caminho_path.read_bytes()
        chave, certificado, _cadeia = pkcs12.load_key_and_certificates(
            dados, senha.encode("utf-8") if senha else None
        )
    except Exception:
        logger.warning(
            "falha ao carregar certificado fiscal configurado",
            extra={"caminho": caminho_str},
        )
        return None
    if chave is None or certificado is None:
        logger.warning(
            "arquivo de certificado fiscal sem chave privada ou sem certificado",
            extra={"caminho": caminho_str},
        )
        return None
    if not isinstance(chave, _TIPOS_CHAVE_PKCS7_CONCRETOS):
        logger.warning(
            "chave privada do certificado fiscal e de um tipo nao suportado pelo PKCS7",
            extra={"caminho": caminho_str, "tipo": type(chave).__name__},
        )
        return None
    return _config_a_partir_do_certificado(certificado, chave)


def obter_certificado_configurado(config: Configuracao | None = None) -> CertificadoConfig | None:
    """Certificado configurado no ambiente do PROCESSO ATUAL (API ou worker
    -- ambos leem `app.core.config.Configuracao`, ver ADR-009: o worker
    instala `apps/api` como biblioteca e importa `app.*` diretamente).

    `None` e o estado real de hoje: nao ha e-CNPJ A1 da SEEG (PCF F12 secao
    2.4, confirmado indisponivel pelo dono do produto em 30/07/2026)."""
    config = config or obter_configuracao()
    return carregar_de_arquivo(config.cert_icp_path, config.cert_icp_senha.get_secret_value())
