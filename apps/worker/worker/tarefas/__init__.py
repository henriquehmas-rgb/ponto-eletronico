"""Catalogo das tarefas assincronas do sistema.

**Doze tarefas** (era "Nove" ate a F10/A2 acrescentar `processar_fechamento`
e `gerar_espelhos`; a F10/A3 acrescenta `processar_fila_notificacoes` logo
abaixo, fechando o total desta fase -- ver tabela abaixo). A docstring
original da Fase 0 descrevia oito como "o conjunto completo previsto para a
v1" -- divergia de `packages/contracts/events.yaml`, que declara
`importacao.concluida` com `origem: worker` sem nenhuma tarefa capaz de
produzi-lo. O PCF da F2 (secao 2) ja decidiu isso a favor do contrato
congelado: aquela fase acrescentou `importar_colaboradores`, a nona.
Registrado em `docs/backlog.md` para que ninguem trate o acrescimo como
invencao de escopo. O nome de cada tarefa continua **contrato**: a API
enfileira por nome, e renomear tarefa com job em voo perde trabalho.

| Tarefa | Fila | Fase que implementa | O que fara |
|---|---|---|---|
| `apurar_dia` | apuracao | F4 | apura um dia de um vinculo |
| `recalcular_periodo` | apuracao | F4 | reprocessa um intervalo afetado |
| `processar_fechamento` | fechamento | F10 | trava a apuracao do escopo e gera espelhos se pedido |
| `gerar_espelhos` | fechamento | F10 | gera o espelho de ponto de cada vinculo do escopo pedido |
| `gerar_afd` | fiscal | F12 | gera o Arquivo Fonte de Dados |
| `gerar_aej` | fiscal | F12 | gera o Arquivo Eletronico de Jornada |
| `executar_relatorio` | relatorios | F11 | executa relatorio assincrono |
| `enviar_webhook` | integracoes | F13 | entrega evento assinado com HMAC |
| `sincronizar_terminal` | integracoes | F6 | sincroniza cadastro com o coletor |
| `expurgo_lgpd` | manutencao | F14 | aplica a politica de retencao |
| `importar_colaboradores` | integracoes | F2 | processa CSV/XLSX de colaboradores linha a linha |
| `processar_fila_notificacoes` | notificacoes | F10 | drena notificacoes pendentes de um tenant |
| `importar_arquivo_generico` | integracoes | F13 | importacao generica (hoje: AFD de terceiro) |
| `exportar_folha` | integracoes | F13 | gera o arquivo de exportacao de folha do parceiro |

**Catorze tarefas a partir da F13/A5** (`exportar_folha`, acima -- ver
`worker/tarefas/integracoes.py` para o corpo completo, e `app.integracoes.
folha.comum.execucao.executar_exportacao_folha` para o trabalho pesado).
Mesmo precedente ja registrado para `importar_colaboradores` (F2) e
`importar_arquivo_generico` (F13/A8): acrescimo autorizado pelo PCF da
fase (`docs/fases/F13-api-publica-webhooks-integracoes.md` §5.3), nao
invencao de escopo.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from worker.tarefas.apuracao import apurar_dia, recalcular_periodo
from worker.tarefas.fechamento import gerar_espelhos, processar_fechamento
from worker.tarefas.fiscal import gerar_aej, gerar_afd
from worker.tarefas.importacoes import importar_colaboradores
from worker.tarefas.integracoes import (
    enviar_webhook,
    exportar_folha,
    importar_arquivo_generico,
    sincronizar_terminal,
)
from worker.tarefas.lgpd import expurgo_lgpd
from worker.tarefas.notificacoes import processar_fila_notificacoes
from worker.tarefas.relatorios import executar_relatorio

#: Registro consumido por `WorkerSettings.functions`. A ordem e a do catalogo.
TAREFAS: tuple[Callable[..., Any], ...] = (
    apurar_dia,
    recalcular_periodo,
    processar_fechamento,
    gerar_espelhos,
    gerar_afd,
    gerar_aej,
    executar_relatorio,
    enviar_webhook,
    sincronizar_terminal,
    expurgo_lgpd,
    importar_colaboradores,
    processar_fila_notificacoes,
    importar_arquivo_generico,
    exportar_folha,
)

NOMES_DAS_TAREFAS: tuple[str, ...] = tuple(tarefa.__name__ for tarefa in TAREFAS)

__all__ = [
    "NOMES_DAS_TAREFAS",
    "TAREFAS",
    "apurar_dia",
    "enviar_webhook",
    "executar_relatorio",
    "exportar_folha",
    "expurgo_lgpd",
    "gerar_aej",
    "gerar_afd",
    "gerar_espelhos",
    "importar_arquivo_generico",
    "importar_colaboradores",
    "processar_fechamento",
    "processar_fila_notificacoes",
    "recalcular_periodo",
    "sincronizar_terminal",
]
