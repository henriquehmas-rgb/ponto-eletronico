"""Simulador de terminal Control iD iDFace. **Implementacao real (F6, A2/T1).**

Por que o simulador nao e luxo
------------------------------

`docs/fases/F06-integracao-control-id.md` (agente A2) e explicito: sem ele a
fase fica bloqueada esperando hardware, e as fases 3, 4 e 5 do teste e2e do
produto inteiro tambem dependem dele. O criterio de aceite da F6 depende dele
de forma direta: "com o simulador, 1.000 eventos entram sem duplicar e sem
perder" e "derrubar a rede e religar recupera tudo via catch-up". Nenhuma das
duas coisas se testa com equipamento fisico de forma repetivel.

O que mudou desde a Fase 0
---------------------------

A Fase 0 entregou so a **estrutura das respostas** de tres `*.fcgi`
(`login`, `load_objects`, `execute_actions`), sem estado nenhum. A T1 da F6
(primeira tarefa da fase, antes de qualquer outra) revisa esses tres formatos
contra a documentacao publica da Control iD e acrescenta os quatro que
faltavam (`create_objects`, `modify_objects`, `destroy_objects`,
`user_set_image`), agora com **estado em memoria**: listas de usuarios,
templates, grupos, regras de acesso, portais, faixas de horario e
`access_logs` por terminal simulado -- o suficiente para T2/T5/T7/T8
exercitarem o ciclo completo (provisionar usuario, gerar evento de acesso,
recuperar por catch-up, apagar usuario desligado).

Correcoes feitas nesta revisao (fidelidade contra a documentacao publica)
--------------------------------------------------------------------------

A Fase 0 avisava, com razao, que nada aqui tinha sido conferido contra
hardware real. A T1 revisou os tres formatos originais contra a documentacao
publica da Control iD (`controlid.com.br/docs/access-api-en`) e encontrou
tres divergencias, corrigidas abaixo:

1. **`create_objects.fcgi` e `modify_objects.fcgi` nao existem como dois
   endpoints separados no equipamento real.** O fabricante expõe um unico
   `create_or_modify_objects.fcgi`: cria quando o `id` esta ausente, atualiza
   quando o `id` informado ja existe. Mantemos os dois nomes em Python
   (`SimuladorTerminal.create_objects` / `.modify_objects`,
   `ClienteControlID.create_objects` / `.modify_objects` em
   `cliente_controlid.py`) porque o PCF da F6 fixa esses dois metodos na
   interface entre A1 e A2 -- mas os dois roteiam para o mesmo comportamento
   de upsert, exatamente como o equipamento real faz por baixo de um unico
   `*.fcgi`.
2. **O `where` de `load_objects.fcgi` e uma lista de condicoes
   (`[{"object", "field", "operator", "value", "connector"}, ...]`), nao um
   dicionario aninhado.** A Fase 0 documentava
   `{"access_logs": {"id": {">": 41207}}}`; a documentacao publica mostra
   `[{"object": "access_logs", "field": "id", "operator": ">", "value": 41207}]`.
   Corrigido em `CondicaoWhere` e em `_registro_combina` abaixo.
3. **A acao de abrir porta chama-se `door` (parametro `door=<id>`), nao
   `open_door`/`door_id=<id>`.** A de catraca e `catra`
   (`allow=clockwise|anticlockwise|both` ou `relay=<n>`). Reiniciar o
   equipamento **nao** passa por `execute_actions.fcgi`: e um endpoint
   proprio, `POST /reboot.fcgi` (com sessao) -- por isso
   `SimuladorTerminal.reboot()` existe como metodo separado, nao como uma
   acao de `execute_actions`.

Estas tres correcoes vieram de pesquisa contra a documentacao publica feita
nesta tarefa (T1); nenhuma foi verificada contra hardware fisico, que
continua indisponivel (`PROJETO.md` secao 2). Ficam documentadas aqui, e nao
silenciosamente, para o proximo agente que integrar hardware de verdade saber
exatamente o que conferir primeiro.

Nota sobre `descrever_simulador()` e o andaime da Fase 0
----------------------------------------------------------

`apps/device-gw/tests/test_andaime_device_gw.py` (fora do ownership desta
fase, ver PCF F6 secao 3) tem um teste,
`test_simulador_cobre_os_tres_fcgi_do_aceite_da_f6`, que afirma por igualdade
exata que `descrever_simulador()["implementado"] is False` e que
`endpointsCobertos` e exatamente o conjunto de tres nomes da Fase 0. Depois
desta tarefa isso deixa de ser verdade -- de proposito: o simulador agora
cobre sete operacoes e esta implementado. O PCF da F6 (secao 3) ja antecipa
este caso ("mesmo tratamento de `apps/api/tests/test_andaime.py` sob
RFC-005"): a asercao especifica fica obsoleta quando a fase dona implementa
de verdade, e quem ajusta o arquivo do andaime e o orquestrador, nunca a
fase. Ver o relatorio final desta tarefa para a lista exata de asercoes que
deixam de valer.
"""

from __future__ import annotations

import datetime as dt
import secrets
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Final, TypedDict

from gateway.log import obter_logger

logger = obter_logger("simulador")

#: Codigos de `access_logs.event` do fabricante. O mapeamento para o
#: vocabulario do dominio (marcacao valida, tentativa recusada, identificacao
#: por cartao) e responsabilidade de `gateway/dominio/conversao.py` (A1, T6).
EVENTOS_ACCESS_LOG: Final[dict[int, str]] = {
    1: "acesso negado",
    2: "acesso concedido",
    3: "acesso pendente",
    4: "porta nao aberta",
    5: "bloqueio de acesso",
    6: "coacao",
    7: "identificacao valida",
}

#: Tabelas do equipamento (PROJETO.md secao 3.1). O simulador mantem estado em
#: memoria para todas elas, nao so `access_logs`.
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

#: As sete operacoes `*.fcgi` que o simulador cobre a partir da T1. Ver a nota
#: no cabecalho do modulo sobre `create_objects`/`modify_objects` mapearem
#: para o mesmo `create_or_modify_objects.fcgi` real.
_ENDPOINTS_COBERTOS: Final[tuple[str, ...]] = (
    "login.fcgi",
    "load_objects.fcgi",
    "execute_actions.fcgi",
    "create_objects.fcgi",
    "modify_objects.fcgi",
    "destroy_objects.fcgi",
    "user_set_image.fcgi",
)

_TAMANHO_MAXIMO_IMAGEM_BYTES: Final[int] = 2 * 1024 * 1024


class CondicaoWhere(TypedDict, total=False):
    """Uma condicao do `where` de `load_objects.fcgi` / `destroy_objects.fcgi`.

    Formato verificado contra a documentacao publica da Control iD (ver nota
    de correcao no cabecalho do modulo): lista de condicoes, cada uma com
    `field`/`operator`/`value`, combinadas em sequencia pelo `connector`
    ("AND" por padrao) da condicao seguinte -- nunca o dicionario aninhado
    `{tabela: {campo: {operador: valor}}}` que a Fase 0 documentava.
    """

    object: str
    field: str
    operator: str
    value: Any
    connector: str


class ErroSimulador(RuntimeError):
    """Base dos erros que o simulador levanta -- traduzidos para o catalogo
    `PONTO-TERM-*` por quem o consome (`cliente_controlid.py`), nunca aqui:
    este modulo simula o EQUIPAMENTO, que nao conhece nosso catalogo."""


class CredenciaisInvalidas(ErroSimulador):
    """`login`/`senha` nao batem com o cadastrado no terminal simulado."""


class SessaoInvalida(ErroSimulador):
    """Sessao ausente, expirada ou invalidada por um `reboot()` simulado."""


class ObjetoDesconhecido(ErroSimulador):
    """`object` fora de `TABELAS` -- equivalente a uma tabela inexistente."""


def resposta_login(sessao: str = "sessao-simulada") -> dict[str, Any]:
    """Estrutura da resposta de `POST /login.fcgi`.

    **Requisicao que o gateway envia**::

        POST /login.fcgi
        {"login": "admin", "password": "<CONTROLID_SENHA>"}

    **Resposta do equipamento**::

        {"session": "8f3d0b714a2e4c95"}

    O token retornado acompanha **todas** as chamadas seguintes na query
    string (`?session=<token>`). Credencial errada nao devolve sessao -- e o
    caso que vira `PONTO-TERM-003` ("Credenciais do terminal recusadas").

    Duas regras que a F6 nao pode esquecer: a sessao **expira** e e
    invalidada por reinicio do equipamento, entao a renovacao tem de ser
    transparente (`cliente_controlid.py` renova uma vez, silenciosamente); e
    o token **nunca** vai para log, porque da acesso administrativo ao
    terminal.
    """
    return {"session": sessao}


def resposta_load_objects(
    tabela: str,
    registros: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Estrutura da resposta de `POST /load_objects.fcgi?session=<token>`.

    A chave do objeto de resposta e o **nome da tabela**, nao uma chave
    generica::

        {"access_logs": [
            {"id": 41208, "time": 1785062460, "event": 7,
             "user_id": 314, "portal_id": 1, "identifier_id": 0}
        ]}

    Lista vazia significa "nada novo depois da marca d'agua" -- condicao
    normal de parada do catch-up, nao um erro.
    """
    return {tabela: registros or []}


def resposta_create_or_modify(mudancas: int) -> dict[str, Any]:
    """Estrutura da resposta de `POST /create_or_modify_objects.fcgi`.

    O equipamento real devolve so a contagem de linhas afetadas, nunca os
    `id`s gerados -- por isso quem cria sem informar `id` precisa depois de
    um `load_objects` para descobrir o que foi criado, ou (o caminho que esta
    fase usa) sempre informar o `id` explicitamente, atribuido por nos.
    """
    return {"changes": mudancas}


def resposta_destroy_objects(mudancas: int) -> dict[str, Any]:
    """Estrutura da resposta de `POST /destroy_objects.fcgi`."""
    return {"changes": mudancas}


def resposta_execute_actions(acoes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Estrutura da resposta de `POST /execute_actions.fcgi?session=<token>`.

    **Requisicao que o gateway envia** para abrir a porta 1::

        {"actions": [{"action": "door", "parameters": "door=1"}]}

    Para liberar o giro da catraca no sentido horario::

        {"actions": [{"action": "catra", "parameters": "allow=clockwise"}]}

    Os `parameters` sao uma string de pares `chave=valor` separados por `;`
    quando ha mais de um par, e nao um objeto JSON -- detalhe do fabricante
    que costuma ser a primeira coisa a quebrar em quem integra pela primeira
    vez. **Reiniciar o equipamento nao passa por aqui**: e o endpoint
    separado `POST /reboot.fcgi` (ver `SimuladorTerminal.reboot`).

    **Resposta do equipamento**: a lista de acoes com o resultado de cada
    uma.
    """
    return {"actions": acoes or []}


def resposta_user_set_image(
    user_id: int, *, sucesso: bool = True, erros: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Estrutura da resposta de `POST /user_set_image.fcgi`.

    Diferente dos demais `*.fcgi`, a requisicao real e **binaria**
    (`Content-Type: application/octet-stream`, corpo = bytes crus da
    imagem), com `user_id`/`timestamp`/`match`/`session` na query string --
    nunca JSON com base64 no corpo. `match=1` recusa a foto se a face ja
    estiver cadastrada em outro usuario; `match=0` permite duplicata (uso de
    excecao, diagnostico).
    """
    return {"user_id": user_id, "success": sucesso, "scores": {}, "errors": erros or []}


def gerar_access_log(
    identificador: int,
    *,
    user_id: int = 1,
    evento: int = 7,
    portal_id: int = 1,
    momento: dt.datetime | None = None,
) -> dict[str, Any]:
    """Monta um `access_log` no formato que o equipamento produz.

    O campo `time` e **epoch em segundos do relogio do equipamento**. Guardar
    o horario do terminal e obrigatorio (e evidencia), mas o horario oficial
    da marcacao e o do servidor: e a regra que impede alguem adiantar o
    relogio da portaria para justificar atraso.

    O `id` e o identificador do registro **dentro daquele equipamento**:
    forma a chave de idempotencia `numero_serie + access_log_id` e a marca
    d'agua do catch-up. E por isso que ele e monotonico crescente e nunca e
    reaproveitado.

    Funcao PURA (nao grava em nenhum estado) -- para gravar um access_log no
    terminal simulado e faze-lo aparecer em `load_objects`, use
    `SimuladorTerminal.registrar_access_log`.
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
    """Resumo do que o simulador cobre hoje.

    Devolve dado, e nao texto solto, para que testes consigam afirmar que as
    sete operacoes do aceite da F6 continuam descritas aqui.
    """
    return {
        "implementado": True,
        "fase": "F6",
        "endpointsCobertos": list(_ENDPOINTS_COBERTOS),
        "tabelas": list(TABELAS),
        "eventos": dict(EVENTOS_ACCESS_LOG),
        "observacao": (
            "Estado em memoria por terminal simulado (users, templates, groups, "
            "access_rules, portals, time_zones, access_logs, alarm_logs). "
            "create_objects/modify_objects roteiam para o mesmo upsert que o "
            "equipamento real expoe como create_or_modify_objects.fcgi; reboot e "
            "endpoint proprio, fora de execute_actions.fcgi. Formatos revisados "
            "contra a documentacao publica da Control iD nesta tarefa (T1), "
            "ainda nao verificados contra hardware fisico."
        ),
    }


def _valor_combina(atual: Any, operador: str, esperado: Any) -> bool:
    if operador == "=":
        return bool(atual == esperado)
    if operador == "!=":
        return bool(atual != esperado)
    if operador == ">":
        return bool(atual is not None and atual > esperado)
    if operador == ">=":
        return bool(atual is not None and atual >= esperado)
    if operador == "<":
        return bool(atual is not None and atual < esperado)
    if operador == "<=":
        return bool(atual is not None and atual <= esperado)
    raise ValueError(f"operador nao suportado em CondicaoWhere: {operador!r}")


def _registro_combina(registro: dict[str, Any], onde: Sequence[CondicaoWhere]) -> bool:
    """Combina as condicoes em sequencia, usando o `connector` de cada uma
    para decidir como juntar com o resultado acumulado ate ali. Sem
    `connector`, o padrao e "AND" -- mesmo comportamento de um `where` de uma
    condicao so."""
    resultado: bool | None = None
    for condicao in onde:
        parcial = _valor_combina(
            registro.get(condicao["field"]), condicao.get("operator", "="), condicao.get("value")
        )
        conector = (condicao.get("connector") or "AND").upper()
        if resultado is None:
            resultado = parcial
        elif "OR" in conector:
            resultado = resultado or parcial
        else:
            resultado = resultado and parcial
    return True if resultado is None else resultado


def _ordenar_registros(
    registros: list[dict[str, Any]], ordenar: Sequence[str]
) -> list[dict[str, Any]]:
    resultado = list(registros)
    # Aplica os criterios da direita para a esquerda: `sorted` e estavel, entao
    # o ultimo `sort` (primeiro criterio da lista) prevalece no desempate.
    for criterio in reversed(ordenar):
        campo = criterio.split()[0]
        descendente = criterio.strip().lower().endswith(("desc", "descending"))

        def _chave(registro: dict[str, Any], campo: str = campo) -> tuple[bool, Any]:
            valor = registro.get(campo)
            return (valor is None, valor)

        resultado.sort(key=_chave, reverse=descendente)
    return resultado


@dataclass(slots=True)
class SimuladorTerminal:
    """Estado em memoria de UM equipamento simulado, identificado pelo
    numero de serie. Cada instancia representa um terminal fisico: sessao,
    tabelas (`users`, `templates`, `groups`, `access_rules`, `portals`,
    `time_zones`, `access_logs`, `alarm_logs`) e contador de `id` por tabela.

    Este e o "hardware fake" que `cliente_controlid.ClienteControlIDSimulado`
    fala -- em processo, sem HTTP nenhum, para o teste poder rodar sem porta
    de rede nem thread de servidor.
    """

    numero_serie: str
    usuario_esperado: str = "admin"
    senha_esperada: str = ""
    sessao_atual: str | None = None
    reinicios: int = 0
    tabelas: dict[str, dict[int, dict[str, Any]]] = field(
        default_factory=lambda: {tabela: {} for tabela in TABELAS}
    )
    _proximo_id: dict[str, int] = field(default_factory=lambda: dict.fromkeys(TABELAS, 1))
    _faces: dict[int, bytes] = field(default_factory=dict)

    # -- sessao -----------------------------------------------------------
    def login(self, login: str, senha: str) -> dict[str, Any]:
        if login != self.usuario_esperado or senha != self.senha_esperada:
            raise CredenciaisInvalidas("login ou senha nao correspondem ao cadastro do terminal.")
        self.sessao_atual = secrets.token_hex(12)
        return resposta_login(self.sessao_atual)

    def _exigir_sessao(self, sessao: str) -> None:
        if self.sessao_atual is None or sessao != self.sessao_atual:
            raise SessaoInvalida("sessao ausente, expirada ou invalidada por reinicio.")

    def reboot(self, sessao: str) -> None:
        """`POST /reboot.fcgi` real: reinicia o equipamento e invalida a
        sessao corrente -- por isso NAO faz parte de `execute_actions`."""
        self._exigir_sessao(sessao)
        self.reinicios += 1
        self.sessao_atual = None

    # -- objetos ------------------------------------------------------------
    def _exigir_tabela(self, objeto: str) -> dict[int, dict[str, Any]]:
        if objeto not in self.tabelas:
            raise ObjetoDesconhecido(f"'{objeto}' nao e uma das tabelas do equipamento: {TABELAS}")
        return self.tabelas[objeto]

    def load_objects(
        self,
        sessao: str,
        objeto: str,
        *,
        campos: Sequence[str] | None = None,
        onde: Sequence[CondicaoWhere] | None = None,
        ordenar: Sequence[str] | None = None,
        limite: int | None = None,
        offset: int | None = None,
    ) -> dict[str, Any]:
        self._exigir_sessao(sessao)
        tabela = self._exigir_tabela(objeto)
        registros = list(tabela.values())
        if onde:
            registros = [r for r in registros if _registro_combina(r, onde)]
        if ordenar:
            registros = _ordenar_registros(registros, ordenar)
        else:
            registros = sorted(registros, key=lambda r: r.get("id", 0))
        if offset:
            registros = registros[offset:]
        if limite is not None:
            registros = registros[:limite]
        if campos:
            registros = [{c: r.get(c) for c in campos} for r in registros]
        return resposta_load_objects(objeto, registros)

    def create_or_modify_objects(
        self, sessao: str, objeto: str, valores: Sequence[dict[str, Any]]
    ) -> dict[str, Any]:
        """Um unico upsert, como o equipamento real faz por baixo de
        `create_or_modify_objects.fcgi` (ver correcao no cabecalho do
        modulo). `create_objects`/`modify_objects` (metodos abaixo) so
        existem como nomes distintos para casar com a interface fixada pela
        T1 -- o comportamento e o mesmo."""
        self._exigir_sessao(sessao)
        tabela = self._exigir_tabela(objeto)
        mudancas = 0
        for valor in valores:
            registro = dict(valor)
            id_bruto = registro.get("id")
            if id_bruto is None:
                id_ = self._proximo_id[objeto]
                self._proximo_id[objeto] = id_ + 1
                registro["id"] = id_
            else:
                id_ = int(id_bruto)
                if id_ >= self._proximo_id[objeto]:
                    self._proximo_id[objeto] = id_ + 1
            tabela[id_] = {**tabela.get(id_, {}), **registro}
            mudancas += 1
        return resposta_create_or_modify(mudancas)

    def create_objects(
        self, sessao: str, objeto: str, valores: Sequence[dict[str, Any]]
    ) -> dict[str, Any]:
        return self.create_or_modify_objects(sessao, objeto, valores)

    def modify_objects(
        self, sessao: str, objeto: str, valores: Sequence[dict[str, Any]]
    ) -> dict[str, Any]:
        return self.create_or_modify_objects(sessao, objeto, valores)

    def destroy_objects(
        self, sessao: str, objeto: str, onde: Sequence[CondicaoWhere]
    ) -> dict[str, Any]:
        self._exigir_sessao(sessao)
        tabela = self._exigir_tabela(objeto)
        alvo = [id_ for id_, registro in tabela.items() if _registro_combina(registro, onde)]
        for id_ in alvo:
            del tabela[id_]
            if objeto == "users":
                self._faces.pop(id_, None)
        return resposta_destroy_objects(len(alvo))

    # -- acoes e imagem -------------------------------------------------------
    def execute_actions(self, sessao: str, acoes: Sequence[dict[str, Any]]) -> dict[str, Any]:
        self._exigir_sessao(sessao)
        resultados: list[dict[str, Any]] = []
        for acao in acoes:
            nome = acao.get("action")
            if nome in ("door", "catra", "sec_box"):
                resultados.append({"action": nome, "success": True})
            else:
                resultados.append(
                    {"action": nome, "success": False, "message": f"acao desconhecida: {nome!r}"}
                )
        return resposta_execute_actions(resultados)

    def user_set_image(
        self,
        sessao: str,
        user_id: int,
        imagem: bytes,
        *,
        forcar_duplicata: bool = False,
    ) -> dict[str, Any]:
        self._exigir_sessao(sessao)
        if user_id not in self.tabelas["users"]:
            raise ObjetoDesconhecido(f"users.id={user_id} nao cadastrado neste terminal.")
        if len(imagem) > _TAMANHO_MAXIMO_IMAGEM_BYTES:
            return resposta_user_set_image(
                user_id,
                sucesso=False,
                erros=[{"code": 1, "message": "Imagem excede o tamanho maximo aceito (2MB)."}],
            )
        if not forcar_duplicata:
            duplicata = next(
                (uid for uid, dados in self._faces.items() if uid != user_id and dados == imagem),
                None,
            )
            if duplicata is not None:
                return resposta_user_set_image(
                    user_id,
                    sucesso=False,
                    erros=[{"code": 2, "message": "Face ja cadastrada em outro usuario."}],
                )
        # Armazenamento e do EQUIPAMENTO simulado (e o que um terminal real
        # faz: extrai o template e guarda). O device-gw, do lado de fora
        # desta classe, nunca persiste a imagem em disco (ver
        # `gateway/provisionamento/comandos.py`).
        self._faces[user_id] = bytes(imagem)
        self.tabelas["templates"][user_id] = {
            "id": user_id,
            "user_id": user_id,
            "versao_modelo": "simulador-v1",
        }
        return resposta_user_set_image(user_id)

    def tem_face_cadastrada(self, user_id: int) -> bool:
        """Usado por teste: confirma que a face foi 'gravada no equipamento'
        sem expor os bytes da imagem (o teste nao deveria precisar deles)."""
        return user_id in self._faces

    # -- geracao de eventos (uso de teste / T5 catch-up) --------------------
    def registrar_access_log(
        self,
        identificador: int,
        *,
        user_id: int = 1,
        evento: int = 7,
        portal_id: int = 1,
        momento: dt.datetime | None = None,
    ) -> dict[str, Any]:
        """Gera e ARMAZENA um `access_log`, para aparecer no proximo
        `load_objects` sobre `access_logs` -- o que `gerar_access_log` (funcao
        pura do modulo) nao faz sozinha."""
        registro = gerar_access_log(
            identificador, user_id=user_id, evento=evento, portal_id=portal_id, momento=momento
        )
        self.tabelas["access_logs"][identificador] = registro
        if identificador >= self._proximo_id["access_logs"]:
            self._proximo_id["access_logs"] = identificador + 1
        return registro


#: Registro de terminais simulados por numero de serie -- um processo
#: `device-gw` simula varios equipamentos ao mesmo tempo, cada um com seu
#: proprio estado, exatamente como aconteceria com hardware real em
#: paralelo.
_REGISTRO_SIMULADORES: dict[str, SimuladorTerminal] = {}


def obter_simulador(numero_serie: str) -> SimuladorTerminal:
    """Devolve o terminal simulado deste numero de serie, criando um novo se
    for a primeira vez que o processo o ve. `cliente_controlid.obter_cliente`
    usa esta funcao para a implementacao simulada; testes tambem, para
    semear estado antes de exercitar o cliente."""
    simulador = _REGISTRO_SIMULADORES.get(numero_serie)
    if simulador is None:
        simulador = SimuladorTerminal(numero_serie=numero_serie)
        _REGISTRO_SIMULADORES[numero_serie] = simulador
    return simulador


def reiniciar_registro_simuladores() -> None:
    """SOMENTE para teste: descarta todo estado simulado acumulado, para que
    um teste nao veja o terminal que o teste anterior deixou de pe."""
    _REGISTRO_SIMULADORES.clear()
