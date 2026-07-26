"""Regra de dominio da tag `terminais` (T3 do PCF da F6, agente A1).

Padrao de estrutura copiado de `app/pessoas/colaboradores.py` (CRUD, paginacao
por cursor, `traduzir_integridade`) -- nao o padrao de cifra de
`app/biometria/cifra.py` (aquele e por-tenant com AAD, ADR-006; aqui e um
segredo de equipamento, envelope mais simples, ver `app/terminais/cifra.py`).

`criarTerminal` sem `dispositivoId`: reaproveita
`app.biometria.dispositivos.criar_dispositivo` (F2, ja pronto) em vez de
duplicar a insercao de `dispositivos` -- proibicao 8 do PCF.

Credencial de servico do `device-gw` para `POST /v1/marcacoes` (T3)
---------------------------------------------------------------------

O `device-gw` nunca autentica como um usuario humano. A conta tecnica de
integracao e um `api_clients` com `tipo = 'maquina'` e uma `api_keys`
(`X-API-Key`, `apiKeyAuth` do contrato) cujo hash SHA-256 bate com o valor
configurado em `device-gw` (`CONTROLID_API_KEY`/`api_key_marcacoes`, ver
`apps/device-gw/gateway/config.py`). Esta fase NAO cria essa semeadura --
`apps/api/migrations/seed_dev.py` esta fora do ownership de F6 (secao 5 do
PCF) -- mas documenta aqui a convencao esperada, e a pendencia de semeadura
esta registrada em `docs/backlog.md`.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import Terminal, TerminalSaude
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.biometria.dispositivos import DadosDispositivoCriar, criar_dispositivo
from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from app.terminais.cifra import cifrar_senha
from app.terminais.erros_bd import traduzir_integridade
from app.terminais.paginacao import (
    CampoOrdenacao,
    codificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    montar_paginacao,
    normalizar_limite,
)

#: Escopo OAuth/api-key que o device-gw apresenta ao chamar `POST
#: /v1/marcacoes` (ver docstring do modulo). Documental -- a semeadura real
#: fica para quem tiver ownership de `seed_dev.py`.
ESCOPO_SERVICO_DEVICE_GW = "ponto:registrar"

_CAMPOS_ORDENACAO: dict[str, CampoOrdenacao] = {
    "numeroSerie": CampoOrdenacao(Terminal.numero_serie, str),
    "criadoEm": CampoOrdenacao(Terminal.criado_em, dt.datetime.fromisoformat),
    "ultimoContatoEm": CampoOrdenacao(Terminal.ultimo_contato_em, dt.datetime.fromisoformat),
}
_ATRIBUTO_POR_CAMPO: dict[str, str] = {
    "numeroSerie": "numero_serie",
    "criadoEm": "criado_em",
    "ultimoContatoEm": "ultimo_contato_em",
}

_CAMPOS_ORDENACAO_SAUDE: dict[str, CampoOrdenacao] = {
    "verificadoEm": CampoOrdenacao(TerminalSaude.verificado_em, dt.datetime.fromisoformat),
}


def _online(terminal: Terminal) -> bool:
    """`Terminal.online`: derivado, nao coluna (openapi.yaml). Um terminal
    `ativo` que fez contato dentro de 2x o seu `intervalo_push_segundos` esta
    online; sem nenhum contato ainda, ou parado ha mais que isso, nao esta."""
    if terminal.status != "ativo" or terminal.ultimo_contato_em is None:
        return False
    limite = dt.timedelta(seconds=terminal.intervalo_push_segundos * 2)
    agora = dt.datetime.now(tz=dt.UTC)
    ultimo = terminal.ultimo_contato_em
    if ultimo.tzinfo is None:
        ultimo = ultimo.replace(tzinfo=dt.UTC)
    return bool((agora - ultimo) <= limite)


def montar_resposta_terminal(terminal: Terminal) -> esquemas.Terminal:
    """`senhaApi` NUNCA aparece aqui (proibicao/criterio de aceite 9 -- o
    schema `Terminal` do contrato nem tem esse campo, so `TerminalCriar`/
    `TerminalAtualizar` tem, e so na escrita)."""
    dados = esquemas.Terminal.model_validate(terminal, from_attributes=True)
    dados.online = _online(terminal)
    return dados


async def obter_terminal(sessao: AsyncSession, tenant_id: UUID, terminal_id: UUID) -> Terminal:
    consulta = sa.select(Terminal).where(
        Terminal.id == terminal_id, Terminal.tenant_id == tenant_id, Terminal.excluido_em.is_(None)
    )
    terminal = (await sessao.execute(consulta)).scalar_one_or_none()
    if terminal is None:
        raise ErroDeAplicacao("PONTO-REC-001", detalhe="Terminal nao encontrado.")
    return terminal


async def criar_terminal(
    sessao: AsyncSession, tenant_id: UUID, dados: esquemas.TerminalCriar, usuario_id: UUID | None
) -> Terminal:
    dispositivo_id = dados.dispositivo_id
    if dispositivo_id is None:
        dispositivo = await criar_dispositivo(
            sessao,
            tenant_id=tenant_id,
            dados=DadosDispositivoCriar(
                empresa_id=dados.empresa_id,
                unidade_id=dados.unidade_id,
                tipo="terminal",
                plataforma="embarcado",
                identificador=dados.numero_serie,
                nome=dados.modelo,
                fabricante=dados.fabricante.value if dados.fabricante else None,
                modelo=dados.modelo,
                versao_so=None,
                versao_app=None,
                status="ativo",
                root_detectado=None,
                emulador_detectado=None,
                modo_desenvolvedor=None,
                depuracao_usb=None,
                observacoes=None,
            ),
            usuario_id=usuario_id,
        )
        dispositivo_id = dispositivo.id

    campos: dict[str, Any] = {
        "tenant_id": tenant_id,
        "dispositivo_id": dispositivo_id,
        "empresa_id": dados.empresa_id,
        "unidade_id": dados.unidade_id,
        "rep_p_id": dados.rep_p_id,
        "fabricante": dados.fabricante.value,
        "modelo": dados.modelo,
        "numero_serie": dados.numero_serie,
        "endereco_ip": dados.endereco_ip,
        "porta": dados.porta,
        "mac": dados.mac,
        "criado_por": usuario_id,
    }
    if dados.modo_comunicacao is not None:
        campos["modo_comunicacao"] = dados.modo_comunicacao.value
    if dados.usuario_api is not None:
        campos["usuario_api"] = dados.usuario_api
    if dados.capacidade_faces is not None:
        campos["capacidade_faces"] = dados.capacidade_faces
    if dados.intervalo_push_segundos is not None:
        campos["intervalo_push_segundos"] = dados.intervalo_push_segundos
    if dados.status is not None:
        campos["status"] = dados.status.value
    if dados.senha_api is not None:
        blob, chave_id = cifrar_senha(dados.senha_api.get_secret_value())
        campos["senha_api_cifrada"] = blob
        campos["chave_id"] = chave_id

    terminal = Terminal(**campos)
    sessao.add(terminal)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc) from exc
    return terminal


async def atualizar_terminal(
    sessao: AsyncSession,
    tenant_id: UUID,
    terminal_id: UUID,
    dados: esquemas.TerminalAtualizar,
    usuario_id: UUID | None,
) -> Terminal:
    terminal = await obter_terminal(sessao, tenant_id, terminal_id)
    campos: dict[str, Any] = dados.model_dump(
        exclude_unset=True, exclude={"senha_api"}, by_alias=False
    )
    for campo, valor in campos.items():
        if hasattr(valor, "value"):  # enums do contrato (Fabricante, ModoComunicacao, Status16)
            valor = valor.value
        setattr(terminal, campo, valor)
    if dados.senha_api is not None:
        blob, chave_id = cifrar_senha(dados.senha_api.get_secret_value())
        terminal.senha_api_cifrada = blob
        terminal.chave_id = chave_id
    terminal.atualizado_por = usuario_id
    terminal.atualizado_em = dt.datetime.now(tz=dt.UTC)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc) from exc
    return terminal


async def excluir_terminal(
    sessao: AsyncSession, tenant_id: UUID, terminal_id: UUID, usuario_id: UUID | None
) -> None:
    """Exclusao logica. Sem dependente que bloqueie hoje neste schema (o
    unico vinculo forte, `dispositivo_id`, e `ON DELETE RESTRICT` do LADO do
    dispositivo -- excluir o terminal nao encosta nele)."""
    terminal = await obter_terminal(sessao, tenant_id, terminal_id)
    terminal.excluido_em = dt.datetime.now(tz=dt.UTC)
    terminal.excluido_por = usuario_id
    await sessao.flush()


async def listar_terminais(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    empresa_id: UUID | None = None,
    unidade_id: UUID | None = None,
    fabricante: str | None = None,
    status: str | None = None,
    online: bool | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[Terminal], esquemas.Paginacao]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO), padrao="criadoEm"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = sa.select(Terminal).where(
        Terminal.tenant_id == tenant_id, Terminal.excluido_em.is_(None)
    )
    if empresa_id is not None:
        consulta = consulta.where(Terminal.empresa_id == empresa_id)
    if unidade_id is not None:
        consulta = consulta.where(Terminal.unidade_id == unidade_id)
    if fabricante is not None:
        consulta = consulta.where(Terminal.fabricante == fabricante)
    if status is not None:
        consulta = consulta.where(Terminal.status == status)

    campo = _CAMPOS_ORDENACAO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=Terminal.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    if online is not None:
        linhas = [linha for linha in linhas if _online(linha) == online]

    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        valor_ultimo = getattr(ultimo, _ATRIBUTO_POR_CAMPO[ordenacao.campo])
        proximo_cursor = codificar_cursor(ordenacao, valor_ultimo, ultimo.id)

    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao


async def listar_saude_terminal(
    sessao: AsyncSession,
    tenant_id: UUID,
    terminal_id: UUID,
    *,
    desde: dt.datetime | None = None,
    somente_offline: bool | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[TerminalSaude], esquemas.Paginacao]:
    # Confirma que o terminal existe (e pertence ao tenant) antes de listar --
    # devolve PONTO-REC-001 em vez de uma lista vazia enganosa.
    await obter_terminal(sessao, tenant_id, terminal_id)

    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO_SAUDE), padrao="verificadoEm"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = sa.select(TerminalSaude).where(
        TerminalSaude.tenant_id == tenant_id, TerminalSaude.terminal_id == terminal_id
    )
    if desde is not None:
        consulta = consulta.where(TerminalSaude.verificado_em >= desde)
    if somente_offline:
        consulta = consulta.where(~TerminalSaude.online)

    campo = _CAMPOS_ORDENACAO_SAUDE[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=TerminalSaude.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        proximo_cursor = codificar_cursor(ordenacao, ultimo.verificado_em, ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao


#: Nome de fila e de tarefa: contrato com `apps/worker/worker/filas.py` e
#: `apps/worker/worker/tarefas/__init__.py`. A tarefa em si e T7 (A2).
NOME_TAREFA_SINCRONIZAR_TERMINAL = "sincronizar_terminal"


def _escopo_de(dados: esquemas.SincronizacaoTerminalRequisicao) -> str:
    """Traduz os booleanos de `SincronizacaoTerminalRequisicao` no `escopo`
    que `sincronizar_terminal` (worker, T7/A2) aceita hoje (`completo`,
    `usuarios`, `templates`, `grupos`, `regras`, `horarios`). Mapeamento
    conservador: qualquer combinacao que nao seja exatamente "so faces" ou
    "so cadastro" vira `completo`, para nunca deixar de propagar algo que o
    chamador pediu."""
    cadastros = dados.enviar_cadastros
    faces = dados.enviar_faces
    if faces and not cadastros:
        return "templates"
    if cadastros and not faces:
        return "usuarios"
    return "completo"


async def sincronizar_terminal(
    sessao: AsyncSession,
    tenant_id: UUID,
    terminal_id: UUID,
    dados: esquemas.SincronizacaoTerminalRequisicao,
    *,
    usuario_id: UUID | None,
    redis_url: str,
) -> esquemas.ProcessamentoAssincrono:
    """Confirma o terminal e enfileira `sincronizar_terminal` (fila
    `ponto:integracoes`), no mesmo padrao de
    `app.importadores.servico.criar_importacao_colaboradores`."""
    from arq import create_pool
    from arq.connections import RedisSettings

    await obter_terminal(sessao, tenant_id, terminal_id)
    escopo = _escopo_de(dados)

    pool = await create_pool(RedisSettings.from_dsn(redis_url))
    try:
        job = await pool.enqueue_job(
            NOME_TAREFA_SINCRONIZAR_TERMINAL,
            tenant_id=str(tenant_id),
            terminal_id=str(terminal_id),
            escopo=escopo,
            solicitante_id=str(usuario_id) if usuario_id else None,
        )
    finally:
        await pool.aclose()

    job_id = job.job_id if job is not None else str(terminal_id)
    return esquemas.ProcessamentoAssincrono(
        id=UUID(job_id) if _parece_uuid(job_id) else terminal_id,
        tipo=esquemas.Tipo42.sincronizacao_terminal,
        status=esquemas.Status62.enfileirado,
        progresso=0,
        totalItens=None,
        itensProcessados=None,
        resultadoRef=None,
        iniciadoEm=dt.datetime.now(tz=dt.UTC),
        concluidoEm=None,
        erro=None,
        codigoErro=None,
    )


def _parece_uuid(valor: str) -> bool:
    try:
        UUID(valor)
    except ValueError:
        return False
    return True
