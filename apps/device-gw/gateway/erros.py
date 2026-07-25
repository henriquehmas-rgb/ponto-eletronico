"""Erros do device-gw em `application/problem+json` (RFC 9457).

O contrato de erro e o mesmo da API — `packages/contracts/errors.yaml`, com o
schema `Problema` do `openapi.yaml`. Vale aqui tudo o que vale la:

* O corpo de erro e sempre `application/problem+json`, nunca `application/json`.
* O campo `codigo` e o unico identificador estavel. `title` e `detail` sao texto
  e podem mudar sem aviso.
* O `http_status` de um codigo e fixo pelo catalogo.
* Codigo marcado com `expoe_regra: false` **nao** manda `detail` na resposta.
* Inventar codigo novo e proibido. Situacao nova exige RFC alterando
  `errors.yaml`.

Por que a tabela abaixo e um recorte, e nao o catalogo inteiro
--------------------------------------------------------------

`apps/api` carrega os 112 codigos porque expoe as 215 operacoes do contrato.
Este servico fala com terminal: emite um punhado deles. Copiar os 112 criaria um
segundo lugar para o catalogo divergir sem ninguem perceber. O recorte abaixo e
**copia literal** das linhas correspondentes de `errors.yaml` (codigo,
categoria, status, titulo, retentavel, expoe_regra) e o teste
`test_andaime_device_gw.py` confere cada campo contra o arquivo de contrato — se
alguem alterar o catalogo, o teste reprova aqui.
"""

from __future__ import annotations

from typing import Any, Final, NamedTuple

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from gateway.log import obter_logger

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
#: emite. Os `PONTO-TERM-*` sao a razao de o recorte existir: sao os unicos
#: codigos do catalogo que descrevem falha de *equipamento*, e e o device-gw
#: quem os produz a partir da F6.
CATALOGO: Final[dict[str, EntradaErro]] = {
    "PONTO-AUTH-013": EntradaErro(
        "PONTO-AUTH-013", "AUTH", 401, "Chave de API invalida ou revogada", False, False
    ),
    "PONTO-VAL-001": EntradaErro(
        "PONTO-VAL-001", "VAL", 400, "Corpo da requisicao invalido", False, True
    ),
    "PONTO-VAL-011": EntradaErro(
        "PONTO-VAL-011", "VAL", 400, "Cabecalho obrigatorio ausente", False, True
    ),
    "PONTO-REC-001": EntradaErro(
        "PONTO-REC-001", "REC", 404, "Recurso nao encontrado", False, False
    ),
    "PONTO-MARC-003": EntradaErro("PONTO-MARC-003", "MARC", 409, "Marcacao duplicada", False, True),
    "PONTO-TERM-001": EntradaErro(
        "PONTO-TERM-001", "TERM", 502, "Terminal inacessivel", True, True
    ),
    "PONTO-TERM-002": EntradaErro(
        "PONTO-TERM-002", "TERM", 504, "Tempo esgotado na comunicacao com o terminal", True, True
    ),
    "PONTO-TERM-003": EntradaErro(
        "PONTO-TERM-003", "TERM", 502, "Credenciais do terminal recusadas", False, True
    ),
    "PONTO-TERM-004": EntradaErro(
        "PONTO-TERM-004", "TERM", 409, "Terminal offline, comando enfileirado", False, True
    ),
    "PONTO-TERM-005": EntradaErro(
        "PONTO-TERM-005", "TERM", 502, "Resposta invalida do terminal", True, True
    ),
    "PONTO-INT-001": EntradaErro("PONTO-INT-001", "INT", 500, "Erro interno", True, False),
    "PONTO-INT-003": EntradaErro(
        "PONTO-INT-003", "INT", 503, "Dependencia indisponivel", True, True
    ),
    "PONTO-INT-005": EntradaErro(
        "PONTO-INT-005", "INT", 501, "Operacao ainda nao implementada", False, True
    ),
}

#: Traducao de status HTTP produzido pelo framework para o codigo do catalogo.
CODIGO_POR_STATUS: Final[dict[int, str]] = {
    400: CODIGO_CORPO_INVALIDO,
    401: "PONTO-AUTH-013",
    404: "PONTO-REC-001",
    500: CODIGO_ERRO_INTERNO,
    501: CODIGO_NAO_IMPLEMENTADO,
    503: CODIGO_DEPENDENCIA_FORA,
}

#: Bloco `responses` anexado as rotas: documenta que qualquer operacao pode
#: responder com um `Problema`.
RESPOSTAS_PADRAO: Final[dict[int | str, dict[str, Any]]] = {
    400: {"description": "Requisicao invalida (RFC 9457)."},
    401: {"description": "Terminal nao autenticado (RFC 9457)."},
    404: {"description": "Terminal ou recurso inexistente (RFC 9457)."},
    500: {"description": "Erro interno (RFC 9457)."},
    501: {
        "description": (
            "Operacao prevista e ainda sem implementacao (PONTO-INT-005). "
            "Resposta padrao da Fase 0; a implementacao chega na F6."
        )
    },
    503: {"description": "Dependencia indisponivel (RFC 9457)."},
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
    """Falha identificada por codigo do catalogo.

    Levantar esta excecao em qualquer ponto produz a resposta correta: o status
    HTTP e o titulo vem do catalogo, nao do ponto de chamada. E o que impede
    dois lugares diferentes responderem status diferente para a mesma condicao.
    """

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
    """Resposta padrao de toda operacao de protocolo durante a Fase 0.

    O `detail` informa a operacao e a fase de FASES-E-AGENTES.md que a
    implementa, para quem estiver integrando saber exatamente o que esperar.
    """

    def __init__(self, operacao: str, *, fase: str = "F6") -> None:
        super().__init__(
            CODIGO_NAO_IMPLEMENTADO,
            detalhe=(
                f"A operacao '{operacao}' faz parte do protocolo Control iD e sera "
                f"implementada na fase {fase}. O caminho, o metodo e o formato ja "
                f"estao definidos para que o simulador e os testes possam ser escritos."
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
    # `expoe_regra: false` -> a explicacao especifica fica fora da resposta. No
    # device-gw isso importa mais do que parece: o terminal e um cliente nao
    # confiavel na borda da rede, e detalhar por que a credencial foi recusada
    # e entregar meio caminho para quem esta tentando forjar equipamento.
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
    *stack trace*: tudo sai como `Problema`.
    """

    @app.exception_handler(ErroDeAplicacao)
    async def _erro_de_aplicacao(request: Request, exc: ErroDeAplicacao) -> RespostaProblema:
        status, corpo = montar_problema(
            codigo=exc.codigo,
            caminho=request.url.path,
            detalhe=exc.detalhe,
            tentar_novamente_em=exc.tentar_novamente_em,
        )
        # 501 e o estado esperado da Fase 0: registrar como ERROR encheria o log
        # de ruido e esconderia falha de verdade.
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
        # Detalhe tecnico vai para o log e para o Sentry, nunca para a resposta:
        # o cliente desta rota esta na borda da rede.
        logger.exception("falha nao prevista", extra={"tipo": type(exc).__name__})
        status, corpo = montar_problema(codigo=CODIGO_ERRO_INTERNO, caminho=request.url.path)
        return _resposta(status, corpo)
