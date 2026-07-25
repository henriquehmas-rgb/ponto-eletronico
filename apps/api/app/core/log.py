"""Log estruturado em JSON, com contexto de requisicao embutido.

Uma linha = um objeto JSON = um evento. E o formato que o Loki e o Grafana da
F15 esperam, e o unico que permite filtrar por `requestId` ou por `tenant` sem
expressao regular fragil.

Decisoes:

* Sem dependencia externa. `python-json-logger` resolveria o mesmo, e um
  formatter de 40 linhas evita mais uma dependencia na imagem.
* O contexto (`requestId`, `tenant`, `usuario`) e injetado pelo formatter lendo
  `app.core.contexto`, e nao por `LoggerAdapter`: assim qualquer biblioteca de
  terceiro que use `logging` sai correlacionada, sem alterar o codigo dela.
* `uvicorn` e `sqlalchemy` sao reconfigurados para escrever no mesmo handler.
  O access log do uvicorn e DESLIGADO: quem registra requisicao e o middleware
  `RegistroDeAcessoMiddleware`, que enxerga o contexto e a duracao.
* Em `dev` o formato pode virar `texto` (`LOG_FORMATO=texto`), porque JSON puro
  no terminal atrapalha mais do que ajuda.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from typing import Any

from app.core import contexto
from app.core.config import Configuracao

#: Atributos que o `logging` ja coloca em todo `LogRecord`. Tudo que sobrar em
#: `record.__dict__` foi passado pelo chamador em `extra=` e vira campo do JSON.
_ATRIBUTOS_PADRAO = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


class FormatadorJson(logging.Formatter):
    """Serializa o `LogRecord` como um unico objeto JSON por linha."""

    def __init__(self, *, servico: str, ambiente: str, versao: str) -> None:
        super().__init__()
        self._base = {"servico": servico, "ambiente": ambiente, "versao": versao}

    def format(self, record: logging.LogRecord) -> str:
        evento: dict[str, Any] = {
            "ts": dt.datetime.fromtimestamp(record.created, tz=dt.UTC).isoformat(),
            "nivel": record.levelname,
            "logger": record.name,
            "mensagem": record.getMessage(),
            **self._base,
            **contexto.instantaneo(),
        }

        for chave, valor in record.__dict__.items():
            if chave in _ATRIBUTOS_PADRAO or chave.startswith("_"):
                continue
            evento[chave] = valor

        if record.exc_info:
            evento["excecao"] = self.formatException(record.exc_info)
        if record.stack_info:
            evento["pilha"] = self.formatStack(record.stack_info)

        # `default=str` garante que UUID, Decimal e datetime nunca derrubem o log:
        # perder observabilidade por causa de um tipo exotico seria pior.
        return json.dumps(evento, ensure_ascii=False, default=str)


class FormatadorTexto(logging.Formatter):
    """Formato legivel para terminal, usado somente em desenvolvimento."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)-8s %(name)s :: %(message)s",
            datefmt="%H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        linha = super().format(record)
        marcas = contexto.instantaneo()
        if marcas:
            linha += "  " + " ".join(f"{c}={v}" for c, v in marcas.items())
        return linha


def configurar_log(config: Configuracao) -> None:
    """Instala o handler unico no logger raiz e alinha os loggers de terceiros."""
    formatador: logging.Formatter
    if config.log_formato == "json":
        formatador = FormatadorJson(
            servico=config.otel_service_name,
            ambiente=config.ambiente,
            versao=config.versao,
        )
    else:
        formatador = FormatadorTexto()

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(formatador)

    raiz = logging.getLogger()
    for antigo in list(raiz.handlers):
        raiz.removeHandler(antigo)
    raiz.addHandler(handler)
    raiz.setLevel(config.log_level)

    # Loggers de terceiros: sem handler proprio, para tudo cair no raiz.
    for nome in ("uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy.engine", "arq"):
        terceiro = logging.getLogger(nome)
        terceiro.handlers.clear()
        terceiro.propagate = True

    # O access log do uvicorn duplicaria o do middleware, sem o contexto.
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if config.database_echo else logging.WARNING
    )


def obter_logger(nome: str) -> logging.Logger:
    """Atalho para manter o prefixo `ponto.` em todos os loggers da aplicacao."""
    return logging.getLogger(nome if nome.startswith("ponto") else f"ponto.{nome}")
