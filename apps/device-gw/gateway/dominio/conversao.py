"""T6 -- conversao `access_log` (formato do fabricante) -> marcacao canonica
(`MarcacaoCriar`, tag `marcacoes` do contrato).

Este e o unico ponto do `device-gw` que traduz o vocabulario da Control iD
para o nosso: todo `access_log` recebido -- por Push, por Monitor ou por
catch-up -- passa por aqui antes de chegar em `POST /v1/marcacoes`
(`gateway.dominio.cliente_api`).

Duas regras que nao se negociam (secao 2 do PCF, "a idempotencia real e um
par de UUID"):

1. `datahoraDispositivo` vem do relogio do EQUIPAMENTO (`access_log["time"]`,
   epoch em segundos) -- e evidencia, nunca o horario oficial: quem carimba a
   hora real e o servidor da F5.
2. `logExternoId` e o `access_log["id"]` (inteiro, local ao equipamento).
   Combinado com `dispositivoId` (o UUID de `terminais.dispositivo_id`), essa
   dupla e a chave de deduplicacao real -- nao a string do fabricante. A
   `Idempotency-Key` do cabecalho e so o SEGUNDO mecanismo de idempotencia
   (dos quatro que `MarcacaoCriar` suporta); ela precisa ser deterministica
   para que reapresentar o mesmo `access_log` (Push reenviando resultado,
   Monitor reentregando, catch-up reprocessando o mesmo intervalo) produza a
   MESMA chave nos dois mecanismos ao mesmo tempo.

Sobre `sentidoInformado`: o formato do `access_log` documentado em
`gateway/simulador.py` (`id`, `time`, `event`, `user_id`, `portal_id`,
`identifier_id`) NAO tem campo de sentido (entrada/saida) -- so o *tipo* de
identificacao (concedida, negada, coacao, ...). Por isso todo `access_log`
converte com `sentidoInformado="indefinido"`: e o valor honesto quando o
coletor nao informa, e o contrato documenta exatamente esse comportamento
("Nao substitui o pareamento feito na apuracao"). Se um modelo futuro de
terminal informar sentido de verdade, este e o unico lugar que muda.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TerminalParaConversao:
    """Os campos do terminal que a conversao precisa. Um recorte deliberado
    (nao a linha inteira de `terminais`) para que o chamador nao precise
    reconstruir um objeto ORM so para converter um `access_log`."""

    id: UUID
    dispositivo_id: UUID
    empresa_id: UUID
    unidade_id: UUID | None
    numero_serie: str


def montar_idempotency_key(numero_serie: str, access_log_id: int) -> str:
    """Chave deterministica: o MESMO `access_log` produz sempre a MESMA
    chave, em Push, Monitor ou catch-up, e em qualquer reapresentacao."""
    return f"device-gw:{numero_serie}:{access_log_id}"


def converter_access_log(
    access_log: dict[str, Any],
    *,
    terminal: TerminalParaConversao,
    matricula: str,
    coletada_offline: bool = False,
) -> dict[str, Any]:
    """Converte um `access_log` do fabricante no corpo de `MarcacaoCriar`.

    `access_log` precisa ter, no minimo, `id` e `time` (epoch em segundos) --
    o formato exato que `gateway/simulador.py::gerar_access_log` produz e que
    a Control iD documenta para `load_objects.fcgi`/notificacao Monitor.
    `matricula` e resolvida pelo CHAMADOR a partir de `access_log["user_id"]`
    (o `user_id` e interno ao equipamento; a traducao para a matricula do
    colaborador usa o campo `registration` que o provisionamento grava --
    T7/A2 -- via cache local ou `load_objects.fcgi` sob demanda).
    """
    datahora_dispositivo = dt.datetime.fromtimestamp(int(access_log["time"]), tz=dt.UTC)
    log_externo_id = int(access_log["id"])
    corpo: dict[str, Any] = {
        "canal": "terminal",
        "matricula": matricula,
        "empresaId": str(terminal.empresa_id),
        "terminalId": str(terminal.id),
        "dispositivoId": str(terminal.dispositivo_id),
        "datahoraDispositivo": datahora_dispositivo.isoformat(),
        "coletadaOffline": coletada_offline,
        "sentidoInformado": "indefinido",
        "logExternoId": log_externo_id,
    }
    if terminal.unidade_id is not None:
        corpo["unidadeId"] = str(terminal.unidade_id)
    return corpo
