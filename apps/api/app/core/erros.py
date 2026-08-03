"""Erros da API em `application/problem+json` (RFC 9457).

Contrato (ver `packages/contracts/errors.yaml` e o schema `Problema` do
`openapi.yaml`):

* O corpo de erro e sempre `application/problem+json`, nunca `application/json`.
* O campo `codigo` e o unico identificador estavel. `title` e `detail` sao texto
  e podem mudar sem aviso -- o cliente deriva a mensagem do usuario do `codigo`.
* O `http_status` de um codigo e fixo pelo catalogo. Nenhum ponto do sistema
  responde `PONTO-REC-001` com status diferente de 404.
* Codigo marcado com `expoe_regra: false` **nao** manda `detail` na resposta: o
  parametro interno (limiar de score, faixa CIDR, raio da geocerca) vai para o
  log e para a auditoria, nunca para a tela. Revelar a regra e entregar o mapa
  da fraude.
* Inventar codigo novo e proibido. Situacao nova exige RFC alterando
  `errors.yaml`, e so entao o codigo aparece em `app/core/catalogo_erros.py`.
"""

from __future__ import annotations

from typing import Any, Final
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core import contexto
from app.core.catalogo_erros import (
    MEDIA_TYPE_PROBLEMA,
    PREFIXO_TYPE,
    EntradaErro,
    entrada,
)
from app.core.log import obter_logger
from app.schemas.contrato import Problema

logger = obter_logger("erros")

CODIGO_NAO_IMPLEMENTADO: Final[str] = "PONTO-INT-005"
CODIGO_ERRO_INTERNO: Final[str] = "PONTO-INT-001"
CODIGO_CORPO_INVALIDO: Final[str] = "PONTO-VAL-001"
CODIGO_CONSULTA_INVALIDA: Final[str] = "PONTO-VAL-005"
CODIGO_CABECALHO_AUSENTE: Final[str] = "PONTO-VAL-011"

#: Traducao de status HTTP produzido pelo framework (404 de rota inexistente,
#: 401 de dependencia de seguranca) para o codigo do catalogo. Status ausente
#: daqui cai em `_codigo_para_status`, que registra um aviso: e sinal de que o
#: catalogo precisa de RFC.
CODIGO_POR_STATUS: Final[dict[int, str]] = {
    400: CODIGO_CORPO_INVALIDO,
    401: "PONTO-AUTH-002",
    403: "PONTO-PERM-001",
    404: "PONTO-REC-001",
    409: "PONTO-CONF-001",
    410: "PONTO-REC-002",
    413: "PONTO-VAL-008",
    415: "PONTO-VAL-009",
    423: "PONTO-AUTH-009",
    429: "PONTO-RATE-001",
    500: CODIGO_ERRO_INTERNO,
    501: CODIGO_NAO_IMPLEMENTADO,
    503: "PONTO-INT-003",
    504: "PONTO-INT-004",
}

#: Bloco `responses` anexado a toda rota gerada. Documenta no portal OpenAPI que
#: qualquer operacao pode responder com um `Problema`.
RESPOSTAS_PADRAO: Final[dict[int | str, dict[str, Any]]] = {
    400: {"model": Problema, "description": "Requisicao invalida (RFC 9457)."},
    401: {"model": Problema, "description": "Nao autenticado (RFC 9457)."},
    403: {"model": Problema, "description": "Sem permissao (RFC 9457)."},
    404: {"model": Problema, "description": "Recurso inexistente (RFC 9457)."},
    429: {"model": Problema, "description": "Limite de requisicoes (RFC 9457)."},
    500: {"model": Problema, "description": "Erro interno (RFC 9457)."},
    501: {
        "model": Problema,
        "description": (
            "Operacao declarada no contrato e ainda sem implementacao "
            "(PONTO-INT-005). Resposta padrao da Fase 0."
        ),
    },
    503: {"model": Problema, "description": "Dependencia indisponivel (RFC 9457)."},
}


class RespostaProblema(JSONResponse):
    """`JSONResponse` com o media type exigido pela RFC 9457."""

    media_type = MEDIA_TYPE_PROBLEMA


class ErroDeAplicacao(Exception):
    """Falha de negocio ou de plataforma identificada por codigo do catalogo.

    Levantar esta excecao em qualquer ponto produz a resposta correta: o status
    HTTP e o titulo vem do catalogo, nao do ponto de chamada. Isso e o que
    impede dois lugares diferentes responderem status diferente para a mesma
    condicao.
    """

    def __init__(
        self,
        codigo: str,
        *,
        detalhe: str | None = None,
        erros_campo: list[dict[str, Any]] | None = None,
        tentar_novamente_em: int | None = None,
        cabecalhos: dict[str, str] | None = None,
        contexto_log: dict[str, Any] | None = None,
    ) -> None:
        self.entrada: EntradaErro = entrada(codigo)
        self.codigo = codigo
        self.detalhe = detalhe
        self.erros_campo = erros_campo
        self.tentar_novamente_em = tentar_novamente_em
        self.cabecalhos = cabecalhos or {}
        self.contexto_log = contexto_log or {}
        super().__init__(f"{codigo}: {self.entrada.titulo}")

    @property
    def http_status(self) -> int:
        return self.entrada.http_status


class NaoImplementado(ErroDeAplicacao):
    """Resposta padrao de toda operacao do contrato durante a Fase 0.

    O `detail` informa a operacao e a fase de FASES-E-AGENTES.md que a
    implementa, para o integrador saber exatamente o que esperar e quando.
    """

    def __init__(self, operacao: str, *, fase: str = "?") -> None:
        super().__init__(
            CODIGO_NAO_IMPLEMENTADO,
            detalhe=(
                f"A operacao '{operacao}' existe no contrato e sera implementada "
                f"na fase {fase}. O contrato ja pode ser usado para gerar cliente, "
                f"levantar mock e escrever teste."
            ),
            contexto_log={"operacao": operacao, "fase": fase},
        )
        self.operacao = operacao
        self.fase = fase


def _codigo_para_status(status: int) -> str:
    codigo = CODIGO_POR_STATUS.get(status)
    if codigo is not None:
        return codigo
    # Nao inventamos codigo: usamos o mais proximo e deixamos rastro para que o
    # catalogo ganhe uma entrada por RFC (ver FASES-E-AGENTES.md secao 1.3).
    logger.warning(
        "status HTTP sem codigo no catalogo de erros",
        extra={"status": status, "acao": "abrir RFC para errors.yaml"},
    )
    return CODIGO_ERRO_INTERNO if status >= 500 else CODIGO_CONSULTA_INVALIDA


def montar_problema(
    *,
    codigo: str,
    caminho: str,
    detalhe: str | None = None,
    erros_campo: list[dict[str, Any]] | None = None,
    tentar_novamente_em: int | None = None,
    status_alternativo: int | None = None,
) -> tuple[int, dict[str, Any]]:
    """Monta o corpo `Problema` a partir do codigo. Devolve `(status, corpo)`."""
    linha = entrada(codigo)
    status = status_alternativo or linha.http_status
    corpo: dict[str, Any] = {
        "type": f"{PREFIXO_TYPE}{codigo}",
        "title": linha.titulo,
        "status": status,
        "codigo": codigo,
        # `caminho` vem de `request.url.path`, que pode conter caractere de
        # controle bruto (achado por fuzzing do schemathesis, F13/T6 -- um
        # segmento de path como "\x1f" chega ate aqui sem decodificar). Sem
        # `quote`, o `instance` viola o proprio schema `Problema` (formato
        # `uri-reference` no contrato) porque caractere de controle nao e
        # valido em URI. `quote` preserva a informacao (percent-encode) em vez
        # de descartar o caractere.
        "instance": quote(caminho, safe="/:@!$&'()*+,;="),
        "documentacao": f"{PREFIXO_TYPE}{codigo}",
    }
    # `expoe_regra: false` -> a explicacao especifica fica fora da resposta.
    if detalhe and linha.expoe_regra:
        corpo["detail"] = detalhe
    if erros_campo:
        corpo["errosCampo"] = erros_campo
    if tentar_novamente_em is not None:
        corpo["tentarNovamenteEm"] = tentar_novamente_em
    request_id = contexto.request_id_atual()
    if request_id:
        corpo["requestId"] = request_id
    return status, corpo


def _resposta(
    status: int, corpo: dict[str, Any], cabecalhos: dict[str, str] | None = None
) -> RespostaProblema:
    return RespostaProblema(status_code=status, content=corpo, headers=cabecalhos or None)


def _campos_de_validacao(erros: list[Any]) -> tuple[str, list[dict[str, Any]]]:
    """Converte os erros do pydantic em `errosCampo` e escolhe o codigo."""
    origem = ""
    campos: list[dict[str, Any]] = []
    for erro in erros:
        local = list(erro.get("loc", ()))
        if local and local[0] in ("body", "query", "path", "header", "cookie"):
            origem = origem or str(local[0])
            local = local[1:]
        campos.append(
            {
                "campo": ".".join(str(parte) for parte in local) or "(corpo)",
                "mensagem": str(erro.get("msg", "valor invalido")),
            }
        )
    codigo = {
        "body": CODIGO_CORPO_INVALIDO,
        "query": CODIGO_CONSULTA_INVALIDA,
        "path": CODIGO_CONSULTA_INVALIDA,
        "header": CODIGO_CABECALHO_AUSENTE,
        "cookie": CODIGO_CABECALHO_AUSENTE,
    }.get(origem, CODIGO_CORPO_INVALIDO)
    return codigo, campos


def registrar_tratadores(app: FastAPI) -> None:
    """Instala os tratadores de erro na aplicacao.

    Depois disto nenhum caminho de falha devolve `application/json` cru nem
    stack trace: tudo sai como `Problema`.
    """

    @app.exception_handler(ErroDeAplicacao)
    async def _erro_de_aplicacao(request: Request, exc: ErroDeAplicacao) -> RespostaProblema:
        status, corpo = montar_problema(
            codigo=exc.codigo,
            caminho=request.url.path,
            detalhe=exc.detalhe,
            erros_campo=exc.erros_campo,
            tentar_novamente_em=exc.tentar_novamente_em,
        )
        # 501 e o estado esperado da Fase 0: registrar como ERROR encheria o
        # log de ruido e escondaria falha de verdade.
        nivel = logger.error if status >= 500 and status != 501 else logger.info
        nivel(
            "erro de aplicacao",
            extra={"codigo": exc.codigo, "status": status, **exc.contexto_log},
        )
        cabecalhos = dict(exc.cabecalhos)
        if exc.tentar_novamente_em is not None:
            cabecalhos.setdefault("Retry-After", str(exc.tentar_novamente_em))
        return _resposta(status, corpo, cabecalhos)

    @app.exception_handler(RequestValidationError)
    async def _validacao_requisicao(
        request: Request, exc: RequestValidationError
    ) -> RespostaProblema:
        codigo, campos = _campos_de_validacao(list(exc.errors()))
        status, corpo = montar_problema(
            codigo=codigo,
            caminho=request.url.path,
            detalhe="A requisicao nao satisfaz o contrato desta operacao.",
            erros_campo=campos,
        )
        logger.info("requisicao invalida", extra={"codigo": codigo, "campos": campos})
        return _resposta(status, corpo)

    @app.exception_handler(ValidationError)
    async def _validacao_resposta(request: Request, exc: ValidationError) -> RespostaProblema:
        # Modelo de resposta que nao valida e defeito nosso, nunca do cliente.
        logger.exception("resposta fora do contrato", extra={"erros": exc.error_count()})
        status, corpo = montar_problema(codigo=CODIGO_ERRO_INTERNO, caminho=request.url.path)
        return _resposta(status, corpo)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> RespostaProblema:
        codigo = _codigo_para_status(exc.status_code)
        detalhe = exc.detail if isinstance(exc.detail, str) else None
        status, corpo = montar_problema(
            codigo=codigo,
            caminho=request.url.path,
            detalhe=detalhe,
            status_alternativo=exc.status_code,
        )
        cabecalhos = dict(getattr(exc, "headers", None) or {})
        return _resposta(status, corpo, cabecalhos)

    @app.exception_handler(Exception)
    async def _nao_previsto(request: Request, exc: Exception) -> RespostaProblema:
        # Detalhe tecnico vai para o log e para o Sentry, nunca para a resposta.
        logger.exception("falha nao prevista", extra={"tipo": type(exc).__name__})
        status, corpo = montar_problema(codigo=CODIGO_ERRO_INTERNO, caminho=request.url.path)
        return _resposta(status, corpo)
