"""Log estruturado JSON do device-gw.

Mesmo formato do `apps/api` e do `apps/worker` (uma linha = um objeto JSON = um
evento), para que Loki e Grafana da F15 tratem os quatro servicos Python com a
mesma consulta.

Os campos que importam aqui e nao existem nos outros servicos sao
`numeroSerie` (qual equipamento) e `ultimoIdColetado` (marca d'agua do
catch-up): sao esses dois que respondem a pergunta operacional tipica —
"a catraca da portaria parou de mandar marcacao desde quando, e de onde eu
retomo?".

**Nada de dado pessoal no log.** `access_log` do terminal carrega identificador
de usuario e, dependendo do evento, template biometrico. Nenhum dos dois entra
aqui: o log guarda o `id` do registro no equipamento, nunca o conteudo
biometrico (ADR-006).

A duplicacao com `apps/api/app/core/log.py` e `apps/worker/worker/log.py` e
consciente: extrair um pacote `packages/plataforma` na Fase 0 criaria
dependencia entre agentes que trabalham em paralelo. A consolidacao esta
anotada como pendencia para depois da Onda 1.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from typing import Any

from gateway.config import Configuracao

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
        "msecs",
        "message",
        "module",
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
        }
        for chave, valor in record.__dict__.items():
            if chave in _ATRIBUTOS_PADRAO or chave.startswith("_"):
                continue
            evento[chave] = valor
        if record.exc_info:
            evento["excecao"] = self.formatException(record.exc_info)
        return json.dumps(evento, ensure_ascii=False, default=str)


def configurar_log(config: Configuracao) -> None:
    """Instala o handler unico no logger raiz e alinha os loggers de terceiro."""
    handler = logging.StreamHandler(stream=sys.stdout)
    if config.log_formato == "json":
        handler.setFormatter(
            FormatadorJson(
                servico=config.otel_service_name,
                ambiente=config.ambiente,
                versao=config.versao,
            )
        )
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s %(name)s :: %(message)s")
        )

    raiz = logging.getLogger()
    for antigo in list(raiz.handlers):
        raiz.removeHandler(antigo)
    raiz.addHandler(handler)
    raiz.setLevel(config.log_level)

    for nome in ("uvicorn", "uvicorn.error", "uvicorn.access", "httpx", "httpcore"):
        terceiro = logging.getLogger(nome)
        terceiro.handlers.clear()
        terceiro.propagate = True
    # O acesso HTTP ja e registrado pelo middleware do proprio servico, com
    # `numeroSerie` junto. O log do uvicorn duplicaria a linha sem esse campo.
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("httpx").setLevel(logging.WARNING)


def obter_logger(nome: str) -> logging.Logger:
    """Mantem o prefixo `ponto.` em todos os loggers do servico."""
    return logging.getLogger(nome if nome.startswith("ponto") else f"ponto.{nome}")
