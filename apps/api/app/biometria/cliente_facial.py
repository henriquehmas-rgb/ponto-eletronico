"""Cliente HTTP do `facial-svc` a partir de `apps/api` -- o caller real que
faltava desde 08/08 (`docs/backlog.md`: "NENHUMA rota de `apps/api`/`device-gw`
foi conectada a este motor").

Por que o caller mora aqui, e nao no `device-gw`
------------------------------------------------

A pergunta natural e se o caminho correto nao seria `api` -> `device-gw` ->
`facial-svc`, ja que o unico cliente mTLS existente ate agora
(`gateway.dominio.cliente_facial`) mora no device-gw. Nao e, e o motivo esta no
contrato, nao em preferencia de desenho:

1. **A imagem crua chega em `apps/api`, nunca no device-gw.** Os dois pontos do
   sistema em que uma foto ao vivo entra sao `POST /v1/biometrias` (cadastro) e
   `MarcacaoCriar.fotoBase64` de `POST /v1/marcacoes` ("Captura ao vivo em
   base64, quando a politica exige facial"), ambos operacoes de
   `packages/contracts/openapi.yaml` servidas por `apps/api`. Nenhuma rota do
   device-gw recebe imagem: ele fala o protocolo Control iD (Push/Monitor), e o
   terminal iDFace faz o casamento facial DENTRO do proprio equipamento e emite
   um `access_log` ja resolvido.
2. **O README do device-gw proibe explicitamente o desvio.** "Template
   biometrico nao passa em claro por aqui (ADR-006). O que interessa e o fato
   'fulano cadastrou face no terminal X', nunca o vetor." Rotear a captura de um
   celular pelo device-gw so para reaproveitar o cliente mTLS colocaria imagem e
   template em claro exatamente no servico que se comprometeu a nao ve-los, e
   acrescentaria um salto de rede ao caminho quente da marcacao sem nenhum ganho.
3. **O par api <-> facial-svc ja esta previsto na infraestrutura.**
   `app/core/config.py` carrega `facial_svc_url` desde a Fase 0, os dois
   servicos compartilham a rede privada de `infra/docker-compose.yml`, e o teste
   de mTLS que prova as primitivas (`tests/f14/hardening/test_mtls_facial_svc.py`)
   ja vive dentro de `apps/api`.

O que NAO muda: a disciplina de mTLS de ADR-006. Este modulo repete, campo a
campo, a forma de `gateway.dominio.cliente_facial.montar_cliente_facial_svc` --
os dois pacotes sao distribuiveis separados (`app` vs `gateway`, ver README do
device-gw sobre `Duplicate module named "app"`), entao a duplicacao e de tres
linhas de `httpx` e deliberada, nao acidental.

Falha aberta ou fechada
-----------------------

Duas condicoes diferentes, duas respostas diferentes -- a confusao entre elas e
o erro classico deste tipo de integracao:

* **O motor respondeu e reprovou** (rosto diferente): falha FECHADA,
  `403 PONTO-SCORE-003`, sem placar nem limiar na resposta (`expoe_regra:
  false`). E evidencia real.
* **O motor nao respondeu** (timeout, conexao recusada, 5xx): e AUSENCIA de
  sinal, nao evidencia. No `/enroll` isso e falha fechada -- `503 PONTO-INT-003`,
  retentavel --, porque gravar uma credencial biometrica sem template real
  produziria um cadastro que parece pronto e nao verifica ninguem. Na MARCACAO a
  decisao e outra e esta documentada em `app.marcacao.pipeline.facial`: ADR-008
  ja decidiu que ausencia de sinal nunca vira bloqueio duro.

Nada deste modulo loga `imagemBase64` nem `template`: os dois sao biometria
(ADR-006 regra 5), e o unico lugar em que o vetor aparece e o valor de retorno.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Any, Final

import httpx

from app.core.config import Configuracao, obter_configuracao
from app.core.erros import ErroDeAplicacao
from app.core.log import obter_logger

logger = obter_logger("biometria.cliente_facial")

#: Codigos que o `facial-svc` produz e que sao repassados ao cliente da API
#: exatamente como vieram, em vez de virarem `PONTO-INT-001`. Sao decisoes do
#: motor sobre a captura, nao defeitos de integracao.
_CODIGOS_REPASSADOS: Final[frozenset[str]] = frozenset(
    {"PONTO-VAL-001", "PONTO-SCORE-002", "PONTO-SCORE-003", "PONTO-LGPD-002"}
)


class MtlsNaoConfigurado(RuntimeError):
    """Configuracao de mTLS incompleta (ou ausente em producao).

    Mesma classe de falha de `gateway.dominio.cliente_facial.MtlsNaoConfigurado`:
    um cliente que "funciona" sem apresentar certificado nunca e uma
    conveniencia aceitavel para este par de servicos.
    """


@dataclass(frozen=True, slots=True)
class ResultadoEnroll:
    """O que `/enroll` devolveu, ja pronto para `DadosBiometriaCriar`.

    `vetor` sao os bytes em claro do template (512 floats, 2048 bytes no
    `buffalo_l`); quem cifra e `app.biometria.cifra`, nunca este modulo.
    """

    vetor: bytes
    dimensao: int
    versao_modelo: str
    duracao_ms: int


def montar_cliente_facial_svc(config: Configuracao, *, timeout_s: float) -> httpx.AsyncClient:
    """`httpx.AsyncClient` apontado para `facial_svc_url`.

    Tres caminhos preenchidos -> mTLS real (certificado de cliente apresentado,
    certificado do servidor verificado contra a CA). Tres vazios -> HTTP puro,
    aceito **so fora de producao**, exatamente como o proprio `facial-svc`
    decide se sobe TLS (`facial/servidor.py`, `infra/docker-compose.yml`).
    Preenchimento parcial e sempre `MtlsNaoConfigurado`: metade de um mTLS nao
    e meio seguro, e configuracao errada silenciosa.
    """
    caminhos = (
        config.facial_mtls_cert_path,
        config.facial_mtls_key_path,
        config.facial_mtls_ca_path,
    )
    completos = all(caminhos)
    if not completos:
        if any(caminhos):
            raise MtlsNaoConfigurado(
                "facial_mtls_cert_path/facial_mtls_key_path/facial_mtls_ca_path "
                "precisam estar todos preenchidos ou todos vazios."
            )
        if config.producao:
            raise MtlsNaoConfigurado(
                "mTLS do facial-svc e obrigatorio em hml/prd: defina "
                "FACIAL_MTLS_CERT_PATH/FACIAL_MTLS_KEY_PATH/FACIAL_MTLS_CA_PATH."
            )
        return httpx.AsyncClient(base_url=config.facial_svc_url, timeout=timeout_s)
    return httpx.AsyncClient(
        base_url=config.facial_svc_url,
        timeout=timeout_s,
        cert=(config.facial_mtls_cert_path, config.facial_mtls_key_path),
        verify=config.facial_mtls_ca_path,
    )


class FacialSvcIndisponivel(Exception):
    """O motor nao respondeu (timeout, conexao recusada, 5xx, corpo ilegivel).

    Deliberadamente NAO e um `ErroDeAplicacao`: quem chama decide o que
    ausencia de sinal significa naquele fluxo -- `/enroll` traduz para
    `PONTO-INT-003`, a marcacao segue sem o sinal (ADR-008). Se esta excecao
    virasse 503 aqui dentro, o pipeline de marcacao perderia a escolha.
    """

    def __init__(self, motivo: str) -> None:
        self.motivo = motivo
        super().__init__(motivo)


def _codigo_do_corpo(resposta: httpx.Response) -> tuple[str | None, str | None]:
    """`(codigo, detalhe)` de um `problem+json` do facial-svc, se legivel."""
    try:
        corpo: Any = resposta.json()
    except ValueError:
        return None, None
    if not isinstance(corpo, dict):
        return None, None
    codigo = corpo.get("codigo")
    detalhe = corpo.get("detail")
    return (
        codigo if isinstance(codigo, str) else None,
        detalhe if isinstance(detalhe, str) else None,
    )


def _traduzir_resposta(resposta: httpx.Response, *, operacao: str) -> None:
    """Levanta o erro certo para uma resposta que nao e 2xx.

    Codigo do catalogo reconhecido -> repassa (a decisao e do motor).
    Qualquer outra coisa -> `FacialSvcIndisponivel` (defeito de integracao).
    """
    codigo, detalhe = _codigo_do_corpo(resposta)
    if codigo in _CODIGOS_REPASSADOS:
        assert codigo is not None  # noqa: S101 - estreitamento para o mypy
        # `PONTO-SCORE-*` tem `expoe_regra: false`: o `detalhe` do motor NAO e
        # repassado, so o codigo. `PONTO-VAL-001` (nenhum rosto, dois rostos)
        # tem `expoe_regra: true` e ajuda o usuario a repetir a captura.
        raise ErroDeAplicacao(
            codigo,
            detalhe=detalhe if codigo == "PONTO-VAL-001" else None,
            contexto_log={"facial_operacao": operacao, "facial_codigo": codigo},
        )
    logger.warning(
        "facial_svc_resposta_inesperada",
        extra={"facial_operacao": operacao, "http_status": resposta.status_code},
    )
    raise FacialSvcIndisponivel(f"{operacao}: HTTP {resposta.status_code}")


async def _chamar(
    *, caminho: str, corpo: dict[str, Any], timeout_s: float, operacao: str
) -> dict[str, Any]:
    config = obter_configuracao()
    try:
        cliente = montar_cliente_facial_svc(config, timeout_s=timeout_s)
    except MtlsNaoConfigurado as exc:
        # Configuracao errada NAO e indisponibilidade: nao pode ser mascarada
        # como "motor fora do ar" e seguir sem sinal. Erro interno, ruidoso.
        logger.error("facial_svc_mtls_nao_configurado", extra={"facial_operacao": operacao})
        raise ErroDeAplicacao(
            "PONTO-INT-001", contexto_log={"facial_operacao": operacao, "motivo": str(exc)}
        ) from exc

    async with cliente:
        try:
            resposta = await cliente.post(caminho, json=corpo)
        except httpx.TimeoutException as exc:
            logger.warning("facial_svc_timeout", extra={"facial_operacao": operacao})
            raise FacialSvcIndisponivel(f"{operacao}: timeout em {timeout_s}s") from exc
        except httpx.HTTPError as exc:
            logger.warning("facial_svc_inalcancavel", extra={"facial_operacao": operacao})
            raise FacialSvcIndisponivel(f"{operacao}: {type(exc).__name__}") from exc

    if resposta.status_code >= 400:
        _traduzir_resposta(resposta, operacao=operacao)

    try:
        dados: Any = resposta.json()
    except ValueError as exc:
        raise FacialSvcIndisponivel(f"{operacao}: corpo nao e JSON") from exc
    if not isinstance(dados, dict):
        raise FacialSvcIndisponivel(f"{operacao}: corpo nao e objeto JSON")
    return dados


async def enroll(
    *, imagem_base64: str, mime_type: str = "image/jpeg", referencia: str | None = None
) -> ResultadoEnroll:
    """`POST /enroll`: extrai o vetor da foto e devolve o template a persistir.

    `referencia` e um identificador OPACO da operacao (o `facial-svc` nunca
    recebe CPF, nome nem matricula -- ver docstring de `facial/esquemas.py`).
    """
    config = obter_configuracao()
    dados = await _chamar(
        caminho="/enroll",
        corpo={
            "imagemBase64": imagem_base64,
            "mimeType": mime_type,
            **({"referencia": referencia} if referencia else {}),
        },
        timeout_s=config.facial_timeout_enroll_s,
        operacao="enroll",
    )
    template = dados.get("template")
    versao_modelo = dados.get("modeloVersao")
    dimensao = dados.get("dimensao")
    if not isinstance(template, str) or not isinstance(versao_modelo, str):
        raise FacialSvcIndisponivel("enroll: resposta sem template/modeloVersao")
    try:
        vetor = base64.b64decode(template, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise FacialSvcIndisponivel("enroll: template nao e base64") from exc
    duracao = dados.get("duracaoMs")
    return ResultadoEnroll(
        vetor=vetor,
        dimensao=int(dimensao) if isinstance(dimensao, int) else len(vetor) // 4,
        versao_modelo=versao_modelo,
        duracao_ms=int(duracao) if isinstance(duracao, int) else 0,
    )


async def verificar(
    *,
    imagem_base64: str,
    templates: list[bytes],
    versao_modelo: str,
    mime_type: str = "image/jpeg",
    referencia: str | None = None,
) -> bool:
    """`POST /verificar` com `exigirAprovacao: true` (o modo do fluxo de ponto).

    Devolve `True` quando aprovou. Reprovacao NAO volta como `False`: o motor
    responde `403 PONTO-SCORE-003` sem placar, e `_traduzir_resposta` a
    transforma no `ErroDeAplicacao` de mesmo codigo -- que e o que o cliente da
    API precisa ver (`expoe_regra: false`, nem similaridade nem limiar na
    resposta). `False` fica reservado para o caso teorico de um `200` com
    `aprovado: false`, que este modo nao produz.
    """
    config = obter_configuracao()
    dados = await _chamar(
        caminho="/verificar",
        corpo={
            "imagemBase64": imagem_base64,
            "mimeType": mime_type,
            "templates": [base64.b64encode(t).decode("ascii") for t in templates],
            "modeloVersao": versao_modelo,
            "exigirAprovacao": True,
            **({"referencia": referencia} if referencia else {}),
        },
        timeout_s=config.facial_timeout_verificar_s,
        operacao="verificar",
    )
    return bool(dados.get("aprovado"))
