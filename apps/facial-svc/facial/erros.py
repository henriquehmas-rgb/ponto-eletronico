"""Erros do facial-svc em `application/problem+json` (RFC 9457).

O contrato de erro e o mesmo da API — `packages/contracts/errors.yaml`, com o
schema `Problema` do `openapi.yaml`. Vale aqui tudo o que vale la, e uma coisa
com peso extra:

* O corpo de erro e sempre `application/problem+json`, nunca `application/json`.
* O campo `codigo` e o unico identificador estavel.
* O `http_status` de um codigo e fixo pelo catalogo.
* Inventar codigo novo e proibido; situacao nova exige RFC em `errors.yaml`.
* **Codigo com `expoe_regra: false` nao manda `detail`.** Neste servico isso
  deixa de ser higiene e vira controle de seguranca: os quatro `PONTO-SCORE-*`
  sao todos `expoe_regra: false`. Responder "similaridade 0,39, limiar 0,42" a
  quem esta testando mascara impressa entrega o mapa da fraude — a pessoa passa
  a saber exatamente quanto falta e itera ate acertar. A causa completa vai para
  a auditoria, nunca para a tela.

Por que a tabela abaixo e um recorte, e nao o catalogo inteiro
--------------------------------------------------------------

`apps/api` carrega os 112 codigos porque expoe as 215 operacoes do contrato.
Este servico faz tres coisas: extrai vetor, compara vetor e julga prova de vida.
Copiar os 112 criaria um segundo lugar para o catalogo divergir sem ninguem
perceber. O recorte abaixo e **copia literal** das linhas correspondentes de
`errors.yaml`, e o teste `test_andaime_facial_svc.py` confere campo a campo
contra o arquivo de contrato.
"""

from __future__ import annotations

from typing import Any, Final, NamedTuple

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from facial.log import obter_logger

logger = obter_logger("erros")

MEDIA_TYPE_PROBLEMA: Final[str] = "application/problem+json"
PREFIXO_TYPE: Final[str] = "https://docs.ponto.seeg.com.br/erros/"


class EntradaErro(NamedTuple):
    """Uma linha do catalogo de erros (recorte de `errors.yaml`)."""

    codigo: str
    categoria: str
    http_status: int
    titulo: str
    retentavel: bool
    expoe_regra: bool


CODIGO_NAO_IMPLEMENTADO: Final[str] = "PONTO-INT-005"
CODIGO_ERRO_INTERNO: Final[str] = "PONTO-INT-001"
CODIGO_DEPENDENCIA_FORA: Final[str] = "PONTO-INT-003"
CODIGO_CORPO_INVALIDO: Final[str] = "PONTO-VAL-001"

#: Recorte de `packages/contracts/errors.yaml` com os codigos que este servico
#: emite. Os `PONTO-SCORE-*` sao a razao de o recorte existir: sao os codigos que
#: descrevem julgamento biometrico, e e o facial-svc quem os produz a partir da
#: F2 (enrollment) e da F7 (captura no app).
CATALOGO: Final[dict[str, EntradaErro]] = {
    "PONTO-VAL-001": EntradaErro(
        "PONTO-VAL-001", "VAL", 400, "Corpo da requisicao invalido", False, True
    ),
    "PONTO-VAL-008": EntradaErro(
        "PONTO-VAL-008", "VAL", 413, "Arquivo acima do tamanho maximo", False, True
    ),
    "PONTO-VAL-009": EntradaErro(
        "PONTO-VAL-009", "VAL", 415, "Tipo de conteudo nao suportado", False, True
    ),
    "PONTO-REC-001": EntradaErro(
        "PONTO-REC-001", "REC", 404, "Recurso nao encontrado", False, False
    ),
    "PONTO-SCORE-002": EntradaErro(
        "PONTO-SCORE-002", "SCORE", 403, "Prova de vida reprovada", True, False
    ),
    "PONTO-SCORE-003": EntradaErro(
        "PONTO-SCORE-003", "SCORE", 403, "Similaridade facial abaixo do limiar", True, False
    ),
    "PONTO-SCORE-004": EntradaErro(
        "PONTO-SCORE-004", "SCORE", 403, "Camera virtual detectada", True, True
    ),
    "PONTO-LGPD-001": EntradaErro(
        "PONTO-LGPD-001", "LGPD", 403, "Consentimento biometrico ausente ou revogado", False, True
    ),
    "PONTO-LGPD-002": EntradaErro(
        "PONTO-LGPD-002", "LGPD", 403, "Acesso ao template biometrico vedado", False, True
    ),
    "PONTO-INT-001": EntradaErro("PONTO-INT-001", "INT", 500, "Erro interno", True, False),
    "PONTO-INT-003": EntradaErro(
        "PONTO-INT-003", "INT", 503, "Dependencia indisponivel", True, True
    ),
    "PONTO-INT-004": EntradaErro(
        "PONTO-INT-004", "INT", 504, "Tempo de processamento esgotado", True, True
    ),
    "PONTO-INT-005": EntradaErro(
        "PONTO-INT-005", "INT", 501, "Operacao ainda nao implementada", False, True
    ),
}

#: Traducao de status HTTP produzido pelo framework para o codigo do catalogo.
CODIGO_POR_STATUS: Final[dict[int, str]] = {
    400: CODIGO_CORPO_INVALIDO,
    404: "PONTO-REC-001",
    413: "PONTO-VAL-008",
    415: "PONTO-VAL-009",
    500: CODIGO_ERRO_INTERNO,
    501: CODIGO_NAO_IMPLEMENTADO,
    503: CODIGO_DEPENDENCIA_FORA,
    504: "PONTO-INT-004",
}

#: Bloco `responses` anexado as rotas: documenta que qualquer operacao pode
#: responder com um `Problema`.
RESPOSTAS_PADRAO: Final[dict[int | str, dict[str, Any]]] = {
    400: {"description": "Requisicao invalida (RFC 9457)."},
    403: {"description": "Reprovado por score, prova de vida ou consentimento (RFC 9457)."},
    413: {"description": "Imagem acima do tamanho maximo (RFC 9457)."},
    415: {"description": "Tipo de imagem nao suportado (RFC 9457)."},
    500: {"description": "Erro interno (RFC 9457)."},
    501: {
        "description": (
            "Operacao prevista e ainda sem implementacao (PONTO-INT-005). "
            "Resposta padrao da Fase 0; a implementacao chega na F2 e na F7."
        )
    },
    503: {"description": "Motor facial indisponivel (RFC 9457)."},
}


def entrada(codigo: str) -> EntradaErro:
    """Devolve a entrada do catalogo, ou levanta `KeyError`.

    `KeyError` aqui e proposital: codigo fora do catalogo e defeito de
    programacao, nao condicao de execucao.
    """
    return CATALOGO[codigo]


class RespostaProblema(JSONResponse):
    """`JSONResponse` com o media type exigido pela RFC 9457."""

    media_type = MEDIA_TYPE_PROBLEMA


class ErroDeAplicacao(Exception):
    """Falha identificada por codigo do catalogo."""

    def __init__(
        self,
        codigo: str,
        *,
        detalhe: str | None = None,
        tentar_novamente_em: int | None = None,
        contexto_log: dict[str, Any] | None = None,
    ) -> None:
        self.entrada: EntradaErro = entrada(codigo)
        self.codigo = codigo
        self.detalhe = detalhe
        self.tentar_novamente_em = tentar_novamente_em
        self.contexto_log = contexto_log or {}
        super().__init__(f"{codigo}: {self.entrada.titulo}")

    @property
    def http_status(self) -> int:
        return self.entrada.http_status


class NaoImplementado(ErroDeAplicacao):
    """Resposta padrao de toda operacao biometrica durante a Fase 0."""

    def __init__(self, operacao: str, *, fase: str = "F2") -> None:
        super().__init__(
            CODIGO_NAO_IMPLEMENTADO,
            detalhe=(
                f"A operacao '{operacao}' sera implementada na fase {fase}, "
                f"reaproveitando o motor analise-facial-edge (decisao D4). O contrato "
                f"de entrada e de saida ja esta definido para que o chamador possa ser "
                f"escrito e testado com dublê."
            ),
            contexto_log={"operacao": operacao, "fase": fase},
        )
        self.operacao = operacao
        self.fase = fase


def montar_problema(
    *,
    codigo: str,
    caminho: str,
    detalhe: str | None = None,
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
        "instance": caminho,
        "documentacao": f"{PREFIXO_TYPE}{codigo}",
    }
    # Ver o cabecalho do modulo: com `expoe_regra: false` o detalhe fica fora da
    # resposta. Nos `PONTO-SCORE-*` isso e controle de seguranca, nao estilo.
    if detalhe and linha.expoe_regra:
        corpo["detail"] = detalhe
    if tentar_novamente_em is not None:
        corpo["tentarNovamenteEm"] = tentar_novamente_em
    return status, corpo


def _resposta(status: int, corpo: dict[str, Any]) -> RespostaProblema:
    cabecalhos = (
        {"Retry-After": str(corpo["tentarNovamenteEm"])} if "tentarNovamenteEm" in corpo else None
    )
    return RespostaProblema(status_code=status, content=corpo, headers=cabecalhos)


def _codigo_para_status(status: int) -> str:
    codigo = CODIGO_POR_STATUS.get(status)
    if codigo is not None:
        return codigo
    logger.warning(
        "status HTTP sem codigo no recorte do catalogo",
        extra={"status": status, "acao": "conferir errors.yaml e ampliar o recorte"},
    )
    return CODIGO_ERRO_INTERNO if status >= 500 else CODIGO_CORPO_INVALIDO


def registrar_tratadores(app: FastAPI) -> None:
    """Instala os tratadores de erro na aplicacao.

    Depois disto nenhum caminho de falha devolve `application/json` cru nem
    *stack trace* — o que, num servico que recebe imagem de rosto, tambem evita
    que um traceback carregue nome de arquivo temporario ou dimensao de imagem
    para a resposta.
    """

    @app.exception_handler(ErroDeAplicacao)
    async def _erro_de_aplicacao(request: Request, exc: ErroDeAplicacao) -> RespostaProblema:
        status, corpo = montar_problema(
            codigo=exc.codigo,
            caminho=request.url.path,
            detalhe=exc.detalhe,
            tentar_novamente_em=exc.tentar_novamente_em,
        )
        nivel = logger.error if status >= 500 and status != 501 else logger.info
        nivel(
            "erro de aplicacao",
            extra={"codigo": exc.codigo, "status": status, **exc.contexto_log},
        )
        return _resposta(status, corpo)

    @app.exception_handler(RequestValidationError)
    async def _validacao(request: Request, exc: RequestValidationError) -> RespostaProblema:
        campos = [
            {
                "campo": ".".join(str(parte) for parte in erro.get("loc", ())) or "(corpo)",
                "mensagem": str(erro.get("msg", "valor invalido")),
            }
            for erro in exc.errors()
        ]
        status, corpo = montar_problema(
            codigo=CODIGO_CORPO_INVALIDO,
            caminho=request.url.path,
            detalhe="A requisicao nao satisfaz o formato esperado para esta operacao.",
        )
        corpo["errosCampo"] = campos
        logger.info("requisicao invalida", extra={"campos": campos})
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
        return _resposta(status, corpo)

    @app.exception_handler(Exception)
    async def _nao_previsto(request: Request, exc: Exception) -> RespostaProblema:
        logger.exception("falha nao prevista", extra={"tipo": type(exc).__name__})
        status, corpo = montar_problema(codigo=CODIGO_ERRO_INTERNO, caminho=request.url.path)
        return _resposta(status, corpo)
