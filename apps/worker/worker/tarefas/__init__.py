"""Catalogo das tarefas assincronas do sistema.

As oito tarefas abaixo sao o conjunto completo previsto para a v1. O nome de
cada uma e **contrato**: a API enfileira por nome, e renomear tarefa com job em
voo perde trabalho. Por isso os nomes ja estao definitivos no andaime.

| Tarefa | Fila | Fase que implementa | O que fara |
|---|---|---|---|
| `apurar_dia` | apuracao | F4 | apura um dia de um vinculo |
| `recalcular_periodo` | apuracao | F4 | reprocessa um intervalo afetado |
| `gerar_afd` | fiscal | F12 | gera o Arquivo Fonte de Dados |
| `gerar_aej` | fiscal | F12 | gera o Arquivo Eletronico de Jornada |
| `executar_relatorio` | relatorios | F11 | executa relatorio assincrono |
| `enviar_webhook` | integracoes | F13 | entrega evento assinado com HMAC |
| `sincronizar_terminal` | integracoes | F6 | sincroniza cadastro com o coletor |
| `expurgo_lgpd` | manutencao | F14 | aplica a politica de retencao |
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from worker.tarefas.apuracao import apurar_dia, recalcular_periodo
from worker.tarefas.fiscal import gerar_aej, gerar_afd
from worker.tarefas.integracoes import enviar_webhook, sincronizar_terminal
from worker.tarefas.lgpd import expurgo_lgpd
from worker.tarefas.relatorios import executar_relatorio

#: Registro consumido por `WorkerSettings.functions`. A ordem e a do catalogo.
TAREFAS: tuple[Callable[..., Any], ...] = (
    apurar_dia,
    recalcular_periodo,
    gerar_afd,
    gerar_aej,
    executar_relatorio,
    enviar_webhook,
    sincronizar_terminal,
    expurgo_lgpd,
)

NOMES_DAS_TAREFAS: tuple[str, ...] = tuple(tarefa.__name__ for tarefa in TAREFAS)

__all__ = [
    "NOMES_DAS_TAREFAS",
    "TAREFAS",
    "apurar_dia",
    "enviar_webhook",
    "executar_relatorio",
    "expurgo_lgpd",
    "gerar_aej",
    "gerar_afd",
    "recalcular_periodo",
    "sincronizar_terminal",
]
