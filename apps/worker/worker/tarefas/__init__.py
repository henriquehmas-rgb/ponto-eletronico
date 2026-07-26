"""Catalogo das tarefas assincronas do sistema.

**Nove tarefas.** A docstring original desta fase (Fase 0) descrevia oito como
"o conjunto completo previsto para a v1" -- divergia de
`packages/contracts/events.yaml`, que declara `importacao.concluida` com
`origem: worker` sem nenhuma tarefa capaz de produzi-lo. O PCF da F2 (secao 2)
ja decidiu isso a favor do contrato congelado: esta fase acrescenta
`importar_colaboradores`, a nona. Registrado em `docs/backlog.md` para que
ninguem trate o acrescimo como invencao de escopo. O nome de cada tarefa
continua **contrato**: a API enfileira por nome, e renomear tarefa com job em
voo perde trabalho.

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
| `importar_colaboradores` | integracoes | F2 | processa CSV/XLSX de colaboradores linha a linha |
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from worker.tarefas.apuracao import apurar_dia, recalcular_periodo
from worker.tarefas.fiscal import gerar_aej, gerar_afd
from worker.tarefas.importacoes import importar_colaboradores
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
    importar_colaboradores,
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
    "importar_colaboradores",
    "recalcular_periodo",
    "sincronizar_terminal",
]
