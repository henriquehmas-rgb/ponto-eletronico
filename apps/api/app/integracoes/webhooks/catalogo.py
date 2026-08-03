"""Catalogo de eventos assinaveis por webhook, duplicado deliberadamente de
`packages/contracts/events.yaml` (19 eventos publicos, de 22 no catalogo
inteiro -- os 3 internos, `ocorrencia.aberta`/`comprovante.emitido`/
`webhook.desabilitado`, nunca podem ser assinados).

Por que duplicar em vez de fazer parse de `events.yaml` em tempo de execucao
------------------------------------------------------------------------------
`packages/contracts` e copiado para `/contratos` so no estagio de BUILD da
imagem da API (`apps/api/Dockerfile`, usado para instalar o pacote
`ponto_contracts`) -- o estagio final de runtime so copia `apps/api/app` e
`apps/api/migrations`. O arquivo YAML bruto pode nao existir no container em
producao. Mesmo padrao ja estabelecido pelo projeto para constantes pequenas
e estaveis (`FILA_PADRAO` duplicada entre `app/core/filas.py` e
`worker/filas.py`, validadores de CPF/PIS duplicados em
`worker/tarefas/importacoes.py`): o catalogo de eventos so muda por RFC
alterando `events.yaml`, e mudar aqui junto e um `grep` de checklist, nao um
risco estrutural.
"""

from __future__ import annotations

#: Nome -> versao corrente (`events.yaml`, campo `versao`). Todos os 19
#: eventos publicos hoje estao na versao 1.
EVENTOS_PUBLICOS: dict[str, int] = {
    "marcacao.criada": 1,
    "marcacao.suspeita": 1,
    "marcacao.sincronizada_offline": 1,
    "ajuste.solicitado": 1,
    "ajuste.aprovado": 1,
    "ajuste.reprovado": 1,
    "apuracao.recalculada": 1,
    "periodo.fechado": 1,
    "periodo.reaberto": 1,
    "banco_horas.vencendo": 1,
    "banco_horas.quitado": 1,
    "colaborador.admitido": 1,
    "colaborador.demitido": 1,
    "terminal.offline": 1,
    "terminal.online": 1,
    "afd.gerado": 1,
    "aej.gerado": 1,
    "espelho.assinado": 1,
    "importacao.concluida": 1,
}

#: Os 3 eventos internos do catalogo -- nunca assinaveis. So aqui para dar
#: uma mensagem de erro mais precisa (evento existe mas nao e publico) do
#: que "evento desconhecido".
EVENTOS_INTERNOS: frozenset[str] = frozenset(
    {"ocorrencia.aberta", "comprovante.emitido", "webhook.desabilitado"}
)


def evento_e_assinavel(nome: str) -> bool:
    return nome in EVENTOS_PUBLICOS
