"""Log estruturado JSON do facial-svc.

Mesmo formato do `apps/api` e do `apps/worker` (uma linha = um objeto JSON = um
evento), para que Loki e Grafana da F15 tratem os quatro servicos Python com a
mesma consulta.

Os campos que importam aqui e nao existem nos outros servicos sao
`modeloVersao` (qual motor produziu o resultado) e `duracaoMs`: sao esses dois
que respondem as perguntas operacionais tipicas — "o reenrollment para a versao
nova ja cobriu quem?" e "a fila de captura esta lenta por causa do motor ou da
rede?".

**Nada de biometria no log. Nunca.** Nem vetor, nem imagem, nem recorte de
rosto, nem o valor bruto da similaridade, nem o limiar configurado (ADR-006 e
`errors.yaml`: `PONTO-SCORE-003` tem `expoe_regra: false`). O que se registra e
o veredito e o identificador da operacao; quem precisar auditar o caso vai a
`acessos_dados_sensiveis`, que existe exatamente para isso.

Cuidado permanente para quem editar este arquivo: log de servico biometrico e o
lugar mais provavel de um vazamento acontecer por descuido — basta alguem
acrescentar `extra={"vetor": ...}` para depurar e esquecer de tirar.

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

from facial.config import Configuracao

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

    for nome in ("uvicorn", "uvicorn.error", "uvicorn.access", "onnxruntime", "insightface"):
        terceiro = logging.getLogger(nome)
        terceiro.handlers.clear()
        terceiro.propagate = True
    # O log de acesso do uvicorn registra a URL completa de cada requisicao. Num
    # servico que recebe imagem de rosto, isso e uma linha a mais por captura
    # sem nenhuma informacao util — e uma superficie a mais para vazar caminho
    # ou identificador. O evento estruturado da propria rota basta.
    logging.getLogger("uvicorn.access").disabled = True


def obter_logger(nome: str) -> logging.Logger:
    """Mantem o prefixo `ponto.` em todos os loggers do servico."""
    return logging.getLogger(nome if nome.startswith("ponto") else f"ponto.{nome}")
