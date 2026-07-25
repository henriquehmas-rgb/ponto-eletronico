"""Esqueleto do simulador de terminal Control iD. **Implementacao real na F6.**

Por que o simulador nao e luxo
------------------------------

`FASES-E-AGENTES.md` (F6, agente A2) e explicito: *"o simulador nao e luxo — sem
ele a fase fica bloqueada esperando hardware, e as fases 3, 4 e 5 do teste e2e
tambem"*. `PROJETO.md` secao 13 repete o argumento como mitigacao de risco:
"iDFace indisponivel para teste → simulador do protocolo Control iD".

O criterio de aceite da F6 depende dele de forma direta: *"com o simulador,
1.000 eventos entram sem duplicar e sem perder"* e *"derrubar a rede por 10 min e
religar recupera tudo via catch-up"*. Nenhuma das duas coisas se testa com
equipamento fisico de forma repetivel — a segunda exige derrubar a rede em cima
da hora, mil vezes, dentro do CI.

O que esta entregue aqui, e o que nao esta
------------------------------------------

Entregue: a **estrutura das respostas** dos tres endpoints `*.fcgi` que o
simulador precisa imitar, o formato do `access_log` gerado e a assinatura das
funcoes. Isso e o suficiente para a F6 comecar pela ponta do teste em vez da
ponta do transporte.

Nao entregue: servidor HTTP, estado persistente, geracao de eventos e modos de
falha. `CONTROLID_SIMULADOR=true` (ja declarado em `infra/.env.example` e no
override de desenvolvimento) nao muda comportamento nenhum na Fase 0 — a
variavel existe, e lida pela configuracao e aparece em `/ready`, e so.

Um aviso sobre fidelidade
-------------------------

Os formatos abaixo seguem a documentacao publica da Control iD e a descricao de
`PROJETO.md` secao 3.1, mas **nao foram verificados contra hardware**: a
aquisicao de um iDFace fisico e pre-requisito ainda em aberto (`PROJETO.md`
secao 2, item 3). Um simulador que imita o protocolo errado e pior do que nao
ter simulador, porque produz confianca falsa. A primeira tarefa da F6, antes de
escrever qualquer linha de simulador, e capturar o trafego real de um
equipamento e corrigir o que estiver diferente daqui.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Final

from gateway.log import obter_logger

logger = obter_logger("simulador")

#: Codigos de `access_logs.event` do fabricante. O mapeamento para o vocabulario
#: do dominio (marcacao valida, tentativa recusada, identificacao por cartao) e
#: trabalho da F6 e precisa ser conferido contra o equipamento.
EVENTOS_ACCESS_LOG: Final[dict[int, str]] = {
    1: "acesso negado",
    2: "acesso concedido",
    3: "acesso pendente",
    4: "porta nao aberta",
    5: "bloqueio de acesso",
    6: "coacao",
    7: "identificacao valida",
}

#: Tabelas do equipamento citadas em PROJETO.md secao 3.1. O simulador precisa
#: responder `load_objects.fcgi` sobre todas elas para servir a F6 (agente A2,
#: provisionamento), nao so sobre `access_logs`.
TABELAS: Final[tuple[str, ...]] = (
    "users",
    "templates",
    "groups",
    "access_rules",
    "portals",
    "time_zones",
    "access_logs",
    "alarm_logs",
)


def resposta_login(sessao: str = "sessao-simulada") -> dict[str, Any]:
    """Estrutura da resposta de `POST /login.fcgi`.

    **Requisicao que o gateway envia**::

        POST /login.fcgi
        {"login": "admin", "password": "<CONTROLID_SENHA>"}

    **Resposta do equipamento**::

        {"session": "8f3d0b714a2e4c95"}

    O token retornado acompanha **todas** as chamadas seguintes na query string
    (`?session=<token>`). Credencial errada nao devolve sessao — e o caso que
    vira `PONTO-TERM-003` ("Credenciais do terminal recusadas").

    Duas regras que a F6 nao pode esquecer: a sessao **expira** e e invalidada
    por reinicio do equipamento, entao a renovacao tem de ser transparente; e o
    token **nunca** vai para log, porque da acesso administrativo ao terminal.
    """
    return {"session": sessao}


def resposta_load_objects(
    tabela: str,
    registros: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Estrutura da resposta de `POST /load_objects.fcgi?session=<token>`.

    **Requisicao que o gateway envia** no catch-up de `access_logs`::

        {"object": "access_logs",
         "where": {"access_logs": {"id": {">": 41207}}},
         "order": ["id"],
         "limit": 1000}

    **Resposta do equipamento** — a chave do objeto de resposta e o **nome da
    tabela**, nao uma chave generica::

        {"access_logs": [
            {"id": 41208, "time": 1785062460, "event": 7,
             "user_id": 314, "portal_id": 1, "identifier_id": 0}
        ]}

    Lista vazia significa "nada novo depois da marca d'agua" — e a condicao
    normal de parada do catch-up, nao um erro.

    O simulador da F6 precisa honrar `where`, `order` e `limit` de verdade: e
    justamente a paginacao por `id` crescente que o criterio de aceite exercita
    ("1.000 eventos entram sem duplicar e sem perder").
    """
    return {tabela: registros or []}


def resposta_execute_actions(acoes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Estrutura da resposta de `POST /execute_actions.fcgi?session=<token>`.

    **Requisicao que o gateway envia**::

        {"actions": [{"action": "open_door", "parameters": "door_id=1"}]}

    Os `parameters` sao uma string de pares `chave=valor` separados por `;`, e
    nao um objeto JSON — detalhe do fabricante que costuma ser a primeira coisa
    a quebrar em quem integra pela primeira vez.

    **Resposta do equipamento**: a lista de acoes com o resultado de cada uma.

    Acoes previstas para a F6: abrir porta (`open_door`), liberar giro de
    catraca, reiniciar o equipamento e disparar sincronizacao de cadastro.
    """
    return {"actions": acoes or []}


def gerar_access_log(
    identificador: int,
    *,
    user_id: int = 1,
    evento: int = 7,
    portal_id: int = 1,
    momento: dt.datetime | None = None,
) -> dict[str, Any]:
    """Monta um `access_log` no formato que o equipamento produz.

    O campo `time` e **epoch em segundos do relogio do equipamento**. Guardar o
    horario do terminal e obrigatorio (e evidencia), mas o horario oficial da
    marcacao e o do servidor: e a regra que impede alguem adiantar o relogio da
    portaria para justificar atraso.

    O `id` e o identificador do registro **dentro daquele equipamento**: forma a
    chave de idempotencia `numero_serie + access_log_id` e a marca d'agua do
    catch-up. E por isso que ele e monotonico crescente e nunca e reaproveitado.
    """
    instante = momento or dt.datetime.now(tz=dt.UTC)
    return {
        "id": identificador,
        "time": int(instante.timestamp()),
        "event": evento,
        "user_id": user_id,
        "portal_id": portal_id,
        "identifier_id": 0,
    }


def descrever_simulador() -> dict[str, Any]:
    """Resumo do que o simulador cobre hoje. Usado pelo teste de andaime.

    Devolve dado, e nao texto solto, para que o teste consiga afirmar que os
    tres endpoints `*.fcgi` do aceite da F6 continuam descritos aqui — se
    alguem apagar um, o teste reprova em vez de a lacuna aparecer so na F6.
    """
    return {
        "implementado": False,
        "fase": "F6",
        "endpointsCobertos": ["login.fcgi", "load_objects.fcgi", "execute_actions.fcgi"],
        "tabelas": list(TABELAS),
        "eventos": dict(EVENTOS_ACCESS_LOG),
        "observacao": (
            "Estrutura de resposta documentada; servidor HTTP, estado e modos de "
            "falha ficam para a F6. Formatos ainda nao verificados contra hardware."
        ),
    }
