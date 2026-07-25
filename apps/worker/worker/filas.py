"""Nomes de fila e resultado padrao das tarefas ainda nao implementadas.

Por que filas separadas: geracao de AFD de 12 meses e relatorio de 1.000
colaboradores levam minutos. Se dividissem fila com `enviar_webhook`, um
fechamento de mes atrasaria toda a integracao dos clientes. A separacao existe
desde o andaime para que ninguem precise migrar fila depois -- trocar de fila
com job em voo e a receita para perder trabalho.

Na Fase 0 um unico processo consome `FILA_PADRAO`, onde tudo esta registrado. A
partir da F4 basta subir replicas apontando `ARQ_WORKER_SETTINGS` para uma
classe com `queue_name` diferente; nenhum codigo de tarefa muda.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Final

FILA_PADRAO: Final[str] = "ponto:padrao"
FILA_APURACAO: Final[str] = "ponto:apuracao"
FILA_FISCAL: Final[str] = "ponto:fiscal"
FILA_RELATORIOS: Final[str] = "ponto:relatorios"
FILA_INTEGRACOES: Final[str] = "ponto:integracoes"
FILA_MANUTENCAO: Final[str] = "ponto:manutencao"

#: Fila de destino planejada por tarefa. Documental na Fase 0.
FILA_POR_TAREFA: Final[dict[str, str]] = {
    "apurar_dia": FILA_APURACAO,
    "recalcular_periodo": FILA_APURACAO,
    "gerar_afd": FILA_FISCAL,
    "gerar_aej": FILA_FISCAL,
    "executar_relatorio": FILA_RELATORIOS,
    "enviar_webhook": FILA_INTEGRACOES,
    "sincronizar_terminal": FILA_INTEGRACOES,
    "expurgo_lgpd": FILA_MANUTENCAO,
}

#: Fase de FASES-E-AGENTES.md que implementa cada tarefa.
FASE_POR_TAREFA: Final[dict[str, str]] = {
    "apurar_dia": "F4",
    "recalcular_periodo": "F4",
    "gerar_afd": "F12",
    "gerar_aej": "F12",
    "executar_relatorio": "F11",
    "enviar_webhook": "F13",
    "sincronizar_terminal": "F6",
    "expurgo_lgpd": "F14",
}

CODIGO_NAO_IMPLEMENTADO: Final[str] = "PONTO-INT-005"


def resultado_nao_implementado(tarefa: str, **contexto: Any) -> dict[str, Any]:
    """Resultado padrao das tarefas de andaime.

    Devolve em vez de levantar excecao de proposito: uma tarefa que levanta
    entraria no ciclo de retentativa do ARQ e ficaria batendo no Redis ate
    esgotar `max_tries`, poluindo a fila e o log com falha que nao e falha. O
    dicionario devolvido diz explicitamente que nada foi feito, e o chamador
    consegue distinguir "nao implementado" de "executou e nao achou nada".
    """
    return {
        "implementado": False,
        "codigo": CODIGO_NAO_IMPLEMENTADO,
        "tarefa": tarefa,
        "fase": FASE_POR_TAREFA.get(tarefa, "?"),
        "fila": FILA_POR_TAREFA.get(tarefa, FILA_PADRAO),
        "executadoEm": dt.datetime.now(tz=dt.UTC).isoformat(),
        "contexto": contexto,
    }
