"""Interface unica de fala com o equipamento Control iD (T1 do PCF da F6).

**Contrato entre A1 e A2, fixado por esta tarefa.** T1 e a primeira tarefa da
fase (PCF F6 secao 6): nada do catch-up de A1 (T5) comeca antes deste arquivo
existir, porque e daqui que A1 importa e chama a interface -- nunca fala HTTP
com o terminal por conta propria, nunca instancia
`ClienteControlIDHttp`/`ClienteControlIDSimulado` diretamente. Os sete metodos
de `ClienteControlID` (`login`, `load_objects`, `create_objects`,
`modify_objects`, `destroy_objects`, `execute_actions`, `user_set_image`) sao
a assinatura publica: mudar depois da T1 exige combinar com o outro agente da
fase (PCF F6 secao 5, tabela "compartilhado dentro da fase").

Duas implementacoes
--------------------

* `ClienteControlIDHttp` -- fala HTTP de verdade contra `endereco_ip`/`porta`
  do terminal. Usada quando `modo_comunicacao` e `polling` ou `direto`.
* `ClienteControlIDSimulado` -- delega a um `gateway.simulador.SimuladorTerminal`
  em processo (sem HTTP, sem thread). Usada quando `CONTROLID_SIMULADOR=true`
  (padrao em dev e em todo teste desta fase, dado que o iDFace fisico
  continua indisponivel -- `PROJETO.md` secao 2).

`obter_cliente()` e a unica forma de conseguir um `ClienteControlID`: ela
escolhe a implementacao certa a partir da configuracao, para que trocar de
simulador para hardware real seja so uma variavel de ambiente, nunca uma
mudanca de codigo em quem consome.

Correcoes de protocolo aplicadas nesta tarefa (fidelidade contra a
documentacao publica da Control iD) estao documentadas no cabecalho de
`gateway/simulador.py` -- em particular, `create_objects`/`modify_objects`
aqui sao dois nomes Python para o mesmo `create_or_modify_objects.fcgi` real,
e `execute_actions` nunca reinicia o equipamento (isso e `POST /reboot.fcgi`,
exposto aqui como o metodo separado `reiniciar`).
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, TypedDict, runtime_checkable

import httpx

from gateway.erros import ErroDeAplicacao
from gateway.log import obter_logger
from gateway.simulador import (
    CondicaoWhere,
    CredenciaisInvalidas,
    ObjetoDesconhecido,
    SessaoInvalida,
    SimuladorTerminal,
    obter_simulador,
)

logger = obter_logger("cliente_controlid")

__all__ = [
    "AcaoExecutar",
    "ClienteControlID",
    "ClienteControlIDHttp",
    "ClienteControlIDSimulado",
    "ConexaoTerminal",
    "obter_cliente",
]


class AcaoExecutar(TypedDict):
    """Um elemento do array `actions` de `execute_actions.fcgi`.

    `parameters` e sempre uma string `chave=valor` (ou `chave1=v1;chave2=v2`
    com mais de um par) -- nunca um objeto JSON. Exemplos verificados contra
    a documentacao publica: `{"action": "door", "parameters": "door=1"}`,
    `{"action": "catra", "parameters": "allow=clockwise"}`.
    """

    action: str
    parameters: str


@dataclass(frozen=True, slots=True)
class ConexaoTerminal:
    """Dados de conexao de UM terminal, desacoplados do modelo SQLAlchemy
    `Terminal` (`packages/contracts/models/biometria.py`) de proposito: este
    modulo nao abre sessao de banco, e quem monta `ConexaoTerminal` (A1 ou
    A2, a partir de uma linha de `terminais` ja carregada) decide como
    resolver `senha_api_cifrada` para texto claro antes de chegar aqui."""

    numero_serie: str
    endereco_ip: str | None
    porta: int | None
    usuario: str
    senha: str
    timeout_s: float = 10.0


@runtime_checkable
class ClienteControlID(Protocol):
    """Interface unica de fala com o equipamento. Ver docstring do modulo."""

    async def login(self) -> str:
        """Abre sessao (`login.fcgi`) e devolve o token. Chamado
        implicitamente pelos demais metodos quando ainda nao ha sessao ou
        quando a sessao foi invalidada -- nao costuma precisar ser chamado
        diretamente."""
        ...

    async def load_objects(
        self,
        objeto: str,
        *,
        campos: Sequence[str] | None = None,
        onde: Sequence[CondicaoWhere] | None = None,
        ordenar: Sequence[str] | None = None,
        limite: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """`load_objects.fcgi`. Devolve a LISTA de registros da tabela (o
        gateway ja desembrulha a chave `{objeto: [...]}` da resposta)."""
        ...

    async def create_objects(self, objeto: str, valores: Sequence[dict[str, Any]]) -> int:
        """Cria registros novos. Sem `id` em um `valor`, o servidor (real ou
        simulado) atribui um; com `id`, vira upsert -- o equipamento real nao
        distingue create de modify por baixo (ver nota do modulo). Devolve
        quantos registros foram afetados (`changes`)."""
        ...

    async def modify_objects(self, objeto: str, valores: Sequence[dict[str, Any]]) -> int:
        """Atualiza registros existentes (`valores` deve informar `id`).
        Mesmo comportamento de `create_objects` por baixo -- dois nomes
        Python para o mesmo upsert do equipamento real."""
        ...

    async def destroy_objects(self, objeto: str, onde: Sequence[CondicaoWhere]) -> int:
        """`destroy_objects.fcgi`. Devolve quantos registros foram
        removidos."""
        ...

    async def execute_actions(self, acoes: Sequence[AcaoExecutar]) -> list[dict[str, Any]]:
        """`execute_actions.fcgi`: abrir porta (`door`), liberar giro de
        catraca (`catra`), acionar drive externo (`sec_box`). **Nao**
        reinicia o equipamento -- ver `reiniciar`."""
        ...

    async def user_set_image(
        self,
        user_id: int,
        imagem: bytes,
        *,
        timestamp: int | None = None,
        forcar_duplicata: bool = False,
    ) -> dict[str, Any]:
        """`user_set_image.fcgi`. `imagem` e sempre `bytes` em memoria --
        nenhuma implementacao deste metodo grava a imagem em arquivo, nem
        temporario (ADR-006 + proibicao 6 do PCF da F6)."""
        ...


def _url_base(conexao: ConexaoTerminal) -> str:
    if not conexao.endereco_ip:
        raise ErroDeAplicacao(
            "PONTO-TERM-001", detalhe="Terminal sem endereco IP cadastrado para conexao direta."
        )
    porta = conexao.porta or 80
    return f"http://{conexao.endereco_ip}:{porta}"


def _corpo_json(resposta: httpx.Response, *, operacao: str) -> dict[str, Any]:
    try:
        corpo = resposta.json()
    except ValueError as exc:
        raise ErroDeAplicacao(
            "PONTO-TERM-005", detalhe=f"{operacao}: resposta do terminal nao e JSON valido."
        ) from exc
    if not isinstance(corpo, dict):
        raise ErroDeAplicacao(
            "PONTO-TERM-005", detalhe=f"{operacao}: resposta do terminal nao e um objeto JSON."
        )
    return corpo


class ClienteControlIDHttp:
    """Implementacao real: HTTP contra `endereco_ip`/`porta` do terminal.

    Usada quando `modo_comunicacao` do terminal e `polling` ou `direto` (PCF
    F6 secao 5) -- em push/monitor quem inicia a conexao e sempre o
    equipamento, entao este cliente nao se aplica la.

    A sessao e mantida em memoria por instancia e renovada de forma
    transparente uma vez em caso de 401 (sessao expirada ou invalidada por
    reinicio do equipamento) -- nunca propagada em log (da acesso
    administrativo ao terminal).
    """

    def __init__(
        self, conexao: ConexaoTerminal, *, transporte: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._conexao = conexao
        self._sessao: str | None = None
        #: Injecao de transporte para teste (`httpx.MockTransport`), sem
        #: precisar de um servidor HTTP real escutando porta nenhuma. `None`
        #: em producao: o httpx usa o transporte de rede padrao.
        self._transporte = transporte

    def _url(self, endpoint: str) -> str:
        return f"{_url_base(self._conexao)}/{endpoint}"

    def _cliente(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self._conexao.timeout_s, transport=self._transporte)

    async def login(self) -> str:
        try:
            async with self._cliente() as cliente:
                resposta = await cliente.post(
                    self._url("login.fcgi"),
                    json={"login": self._conexao.usuario, "password": self._conexao.senha},
                )
        except httpx.TimeoutException as exc:
            raise ErroDeAplicacao("PONTO-TERM-002", detalhe="login.fcgi: tempo esgotado.") from exc
        except httpx.HTTPError as exc:
            raise ErroDeAplicacao(
                "PONTO-TERM-001", detalhe=f"login.fcgi: terminal inacessivel ({exc})."
            ) from exc
        if resposta.status_code != 200:
            raise ErroDeAplicacao("PONTO-TERM-003")
        corpo = _corpo_json(resposta, operacao="login.fcgi")
        sessao = corpo.get("session")
        if not isinstance(sessao, str) or not sessao:
            raise ErroDeAplicacao("PONTO-TERM-005", detalhe="login.fcgi: resposta sem 'session'.")
        self._sessao = sessao
        return sessao

    async def _sessao_atual(self) -> str:
        if self._sessao is None:
            return await self.login()
        return self._sessao

    async def _chamar(
        self, endpoint: str, corpo: dict[str, Any], *, tentar_login: bool = True
    ) -> dict[str, Any]:
        sessao = await self._sessao_atual()
        try:
            async with self._cliente() as cliente:
                resposta = await cliente.post(
                    self._url(endpoint), params={"session": sessao}, json=corpo
                )
        except httpx.TimeoutException as exc:
            raise ErroDeAplicacao("PONTO-TERM-002", detalhe=f"{endpoint}: tempo esgotado.") from exc
        except httpx.HTTPError as exc:
            raise ErroDeAplicacao(
                "PONTO-TERM-001", detalhe=f"{endpoint}: terminal inacessivel ({exc})."
            ) from exc
        if resposta.status_code == 401 and tentar_login:
            # Sessao expirada ou invalidada por reinicio: renova uma vez, de
            # forma transparente (nunca propaga o token antigo para o log).
            self._sessao = None
            return await self._chamar(endpoint, corpo, tentar_login=False)
        if resposta.status_code >= 400:
            raise ErroDeAplicacao(
                "PONTO-TERM-005", detalhe=f"{endpoint}: HTTP {resposta.status_code}."
            )
        return _corpo_json(resposta, operacao=endpoint)

    async def load_objects(
        self,
        objeto: str,
        *,
        campos: Sequence[str] | None = None,
        onde: Sequence[CondicaoWhere] | None = None,
        ordenar: Sequence[str] | None = None,
        limite: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        corpo: dict[str, Any] = {"object": objeto}
        if campos:
            corpo["fields"] = list(campos)
        if onde:
            corpo["where"] = list(onde)
        if ordenar:
            corpo["order"] = list(ordenar)
        if limite is not None:
            corpo["limit"] = limite
        if offset is not None:
            corpo["offset"] = offset
        resultado = await self._chamar("load_objects.fcgi", corpo)
        registros = resultado.get(objeto)
        if not isinstance(registros, list):
            raise ErroDeAplicacao(
                "PONTO-TERM-005", detalhe=f"load_objects.fcgi: resposta sem a chave '{objeto}'."
            )
        return registros

    async def _criar_ou_modificar(self, objeto: str, valores: Sequence[dict[str, Any]]) -> int:
        resultado = await self._chamar(
            "create_or_modify_objects.fcgi", {"object": objeto, "values": list(valores)}
        )
        mudancas = resultado.get("changes")
        if not isinstance(mudancas, int):
            raise ErroDeAplicacao(
                "PONTO-TERM-005", detalhe="create_or_modify_objects.fcgi: resposta sem 'changes'."
            )
        return mudancas

    async def create_objects(self, objeto: str, valores: Sequence[dict[str, Any]]) -> int:
        return await self._criar_ou_modificar(objeto, valores)

    async def modify_objects(self, objeto: str, valores: Sequence[dict[str, Any]]) -> int:
        return await self._criar_ou_modificar(objeto, valores)

    async def destroy_objects(self, objeto: str, onde: Sequence[CondicaoWhere]) -> int:
        resultado = await self._chamar(
            "destroy_objects.fcgi", {"object": objeto, "where": list(onde)}
        )
        mudancas = resultado.get("changes")
        if not isinstance(mudancas, int):
            raise ErroDeAplicacao(
                "PONTO-TERM-005", detalhe="destroy_objects.fcgi: resposta sem 'changes'."
            )
        return mudancas

    async def execute_actions(self, acoes: Sequence[AcaoExecutar]) -> list[dict[str, Any]]:
        resultado = await self._chamar("execute_actions.fcgi", {"actions": list(acoes)})
        lista = resultado.get("actions")
        if not isinstance(lista, list):
            raise ErroDeAplicacao(
                "PONTO-TERM-005", detalhe="execute_actions.fcgi: resposta sem 'actions'."
            )
        return lista

    async def reiniciar(self) -> None:
        """`POST /reboot.fcgi`: reinicia o equipamento. Fora do Protocol
        `ClienteControlID` de proposito -- nao e um dos sete metodos que a
        T1 fixou, mas T8 (execute_actions) precisa da rota real, entao fica
        exposta aqui como extensao da implementacao HTTP."""
        sessao = await self._sessao_atual()
        try:
            async with self._cliente() as cliente:
                resposta = await cliente.post(self._url("reboot.fcgi"), params={"session": sessao})
        except httpx.TimeoutException as exc:
            raise ErroDeAplicacao("PONTO-TERM-002", detalhe="reboot.fcgi: tempo esgotado.") from exc
        except httpx.HTTPError as exc:
            raise ErroDeAplicacao(
                "PONTO-TERM-001", detalhe=f"reboot.fcgi: terminal inacessivel ({exc})."
            ) from exc
        if resposta.status_code >= 400:
            raise ErroDeAplicacao(
                "PONTO-TERM-005", detalhe=f"reboot.fcgi: HTTP {resposta.status_code}."
            )
        self._sessao = None

    async def user_set_image(
        self,
        user_id: int,
        imagem: bytes,
        *,
        timestamp: int | None = None,
        forcar_duplicata: bool = False,
    ) -> dict[str, Any]:
        sessao = await self._sessao_atual()
        parametros: dict[str, Any] = {
            "user_id": user_id,
            "session": sessao,
            "timestamp": timestamp if timestamp is not None else int(time.time()),
            "match": 0 if forcar_duplicata else 1,
        }
        try:
            async with self._cliente() as cliente:
                resposta = await cliente.post(
                    self._url("user_set_image.fcgi"),
                    params=parametros,
                    content=imagem,
                    headers={"Content-Type": "application/octet-stream"},
                )
        except httpx.TimeoutException as exc:
            raise ErroDeAplicacao(
                "PONTO-TERM-002", detalhe="user_set_image.fcgi: tempo esgotado."
            ) from exc
        except httpx.HTTPError as exc:
            raise ErroDeAplicacao(
                "PONTO-TERM-001", detalhe=f"user_set_image.fcgi: terminal inacessivel ({exc})."
            ) from exc
        if resposta.status_code >= 400:
            raise ErroDeAplicacao(
                "PONTO-TERM-005", detalhe=f"user_set_image.fcgi: HTTP {resposta.status_code}."
            )
        if not resposta.content:
            return {"user_id": user_id, "success": True}
        return _corpo_json(resposta, operacao="user_set_image.fcgi")


class ClienteControlIDSimulado:
    """Implementacao simulada: fala com um `SimuladorTerminal` em processo
    (sem HTTP, sem thread, sem porta de rede). Usada quando
    `CONTROLID_SIMULADOR=true` -- padrao em dev e em todo teste desta fase.
    """

    def __init__(self, simulador: SimuladorTerminal, *, usuario: str, senha: str) -> None:
        self._simulador = simulador
        #: Credencial que ESTE CLIENTE apresenta ao terminal simulado --
        #: independente do que `simulador.usuario_esperado`/`senha_esperada`
        #: guardam (o cadastro do lado do "equipamento"). Confundir os dois
        #: faria a checagem de credencial ser sempre verdadeira contra si
        #: mesma, o que anularia o proposito de `CredenciaisInvalidas`.
        self._usuario = usuario
        self._senha = senha
        self._sessao: str | None = None

    async def login(self) -> str:
        try:
            resposta = self._simulador.login(self._usuario, self._senha)
        except CredenciaisInvalidas as exc:
            raise ErroDeAplicacao("PONTO-TERM-003") from exc
        sessao = resposta["session"]
        if not isinstance(sessao, str):
            raise ErroDeAplicacao("PONTO-TERM-005", detalhe="login simulado sem 'session' string.")
        self._sessao = sessao
        return sessao

    async def _sessao_atual(self) -> str:
        if self._sessao is None:
            return await self.login()
        return self._sessao

    async def _com_renovacao(self, chamada: Any, *args: Any, **kwargs: Any) -> Any:
        sessao = await self._sessao_atual()
        try:
            return chamada(sessao, *args, **kwargs)
        except SessaoInvalida:
            self._sessao = None
            sessao = await self._sessao_atual()
            return chamada(sessao, *args, **kwargs)
        except ObjetoDesconhecido as exc:
            raise ErroDeAplicacao("PONTO-TERM-005", detalhe=str(exc)) from exc

    async def load_objects(
        self,
        objeto: str,
        *,
        campos: Sequence[str] | None = None,
        onde: Sequence[CondicaoWhere] | None = None,
        ordenar: Sequence[str] | None = None,
        limite: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        resultado = await self._com_renovacao(
            self._simulador.load_objects,
            objeto,
            campos=campos,
            onde=onde,
            ordenar=ordenar,
            limite=limite,
            offset=offset,
        )
        return list(resultado[objeto])

    async def create_objects(self, objeto: str, valores: Sequence[dict[str, Any]]) -> int:
        resultado = await self._com_renovacao(self._simulador.create_objects, objeto, valores)
        return int(resultado["changes"])

    async def modify_objects(self, objeto: str, valores: Sequence[dict[str, Any]]) -> int:
        resultado = await self._com_renovacao(self._simulador.modify_objects, objeto, valores)
        return int(resultado["changes"])

    async def destroy_objects(self, objeto: str, onde: Sequence[CondicaoWhere]) -> int:
        resultado = await self._com_renovacao(self._simulador.destroy_objects, objeto, onde)
        return int(resultado["changes"])

    async def execute_actions(self, acoes: Sequence[AcaoExecutar]) -> list[dict[str, Any]]:
        resultado = await self._com_renovacao(self._simulador.execute_actions, list(acoes))
        return list(resultado["actions"])

    async def reiniciar(self) -> None:
        sessao = await self._sessao_atual()
        self._simulador.reboot(sessao)
        self._sessao = None

    async def user_set_image(
        self,
        user_id: int,
        imagem: bytes,
        *,
        timestamp: int | None = None,
        forcar_duplicata: bool = False,
    ) -> dict[str, Any]:
        return dict(
            await self._com_renovacao(
                self._simulador.user_set_image,
                user_id,
                imagem,
                forcar_duplicata=forcar_duplicata,
            )
        )


def obter_cliente(
    *,
    conexao: ConexaoTerminal,
    simulador: bool,
    transporte: httpx.AsyncBaseTransport | None = None,
) -> ClienteControlID:
    """Escolhe a implementacao real ou simulada.

    `simulador=True` corresponde a `Configuracao.controlid_simulador` (padrao
    em dev/teste); `simulador=False` usa `ClienteControlIDHttp` contra
    `conexao.endereco_ip`/`conexao.porta`. A1 (T5, catch-up) e A2 (T7, T8)
    chamam esta funcao -- nenhum dos dois instancia as classes diretamente,
    para que trocar de simulador para hardware real seja so uma variavel de
    ambiente.

    `transporte` e so para teste (`httpx.MockTransport`): ignorado quando
    `simulador=True`, porque a implementacao simulada nunca abre um cliente
    HTTP.

    No caminho simulado, o "cadastro" do terminal simulado (a credencial que
    `SimuladorTerminal` exige em `login`) e sincronizado com `conexao` --
    equivalente ao provisionamento inicial de um equipamento real, que so
    aceita a senha que foi configurada nele. Isso e so o registro deste
    processo em memoria (`gateway.simulador.obter_simulador`); nao persiste
    em lugar nenhum.
    """
    if simulador:
        instancia = obter_simulador(conexao.numero_serie)
        instancia.usuario_esperado = conexao.usuario
        instancia.senha_esperada = conexao.senha
        return ClienteControlIDSimulado(instancia, usuario=conexao.usuario, senha=conexao.senha)
    return ClienteControlIDHttp(conexao, transporte=transporte)
