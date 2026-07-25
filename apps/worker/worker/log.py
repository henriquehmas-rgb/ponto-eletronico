"""Log estruturado JSON dos workers.

Mesmo formato do `apps/api` (uma linha = um objeto JSON = um evento), para que
Loki e Grafana da F15 tratem API e worker com a mesma consulta. Cada evento de
job carrega `job_id`, `tarefa` e `tentativa`, que sao os campos usados para
investigar fila travada.

A duplicacao com `apps/api/app/core/log.py` e consciente: extrair um pacote
`packages/plataforma` na Fase 0 criaria dependencia entre dois agentes que
trabalham em paralelo. A consolidacao esta anotada como pendencia para depois
da Onda 1.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from typing import Any

from worker.config import Configuracao

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
        "module",
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
    """Instala o handler unico no logger raiz e alinha os loggers do ARQ."""
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

    for nome in ("arq", "arq.worker", "arq.jobs", "sqlalchemy.engine"):
        terceiro = logging.getLogger(nome)
        terceiro.handlers.clear()
        terceiro.propagate = True
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def obter_logger(nome: str) -> logging.Logger:
    """Mantem o prefixo `ponto.` em todos os loggers do worker."""
    return logging.getLogger(nome if nome.startswith("ponto") else f"ponto.{nome}")
