"""Leitura/escrita da linha de `terminais` que o `device-gw` precisa, e a
montagem do `ClienteControlID` (T1, `gateway/cliente_controlid.py`) para
falar com aquele equipamento especifico.

Consultas em SQL cru (`sqlalchemy.text`), nao ORM: `device-gw` nao depende do
pacote `ponto_contracts` (ver `apps/device-gw/pyproject.toml`) -- a mesma
decisao que ja levou `fn_resolve_terminal` a ser chamada com `text()` em
`apps/api/app/identidade/tenancy/resolucao.py`.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.cliente_controlid import ClienteControlID, ConexaoTerminal, obter_cliente
from gateway.config import Configuracao
from gateway.dominio.cifra import decifrar_senha


@dataclass(frozen=True, slots=True)
class TerminalCarregado:
    """Recorte de `terminais` (`packages/contracts/schema.sql`, secao 6) --
    so as colunas que o `device-gw` usa."""

    id: UUID
    tenant_id: UUID
    numero_serie: str
    dispositivo_id: UUID
    empresa_id: UUID
    unidade_id: UUID | None
    endereco_ip: str | None
    porta: int | None
    usuario_api: str | None
    senha_api_cifrada: bytes | None
    modo_comunicacao: str
    intervalo_push_segundos: int
    ultimo_log_externo_id: int
    ultimo_contato_em: dt.datetime | None
    status: str


_COLUNAS = (
    "id, tenant_id, numero_serie, dispositivo_id, empresa_id, unidade_id, endereco_ip, porta, "
    "usuario_api, senha_api_cifrada, modo_comunicacao, intervalo_push_segundos, "
    "ultimo_log_externo_id, ultimo_contato_em, status"
)


def _para_terminal(linha: object) -> TerminalCarregado:
    return TerminalCarregado(
        id=linha.id,  # type: ignore[attr-defined]
        tenant_id=linha.tenant_id,  # type: ignore[attr-defined]
        numero_serie=linha.numero_serie,  # type: ignore[attr-defined]
        dispositivo_id=linha.dispositivo_id,  # type: ignore[attr-defined]
        empresa_id=linha.empresa_id,  # type: ignore[attr-defined]
        unidade_id=linha.unidade_id,  # type: ignore[attr-defined]
        endereco_ip=linha.endereco_ip,  # type: ignore[attr-defined]
        porta=linha.porta,  # type: ignore[attr-defined]
        usuario_api=linha.usuario_api,  # type: ignore[attr-defined]
        senha_api_cifrada=linha.senha_api_cifrada,  # type: ignore[attr-defined]
        modo_comunicacao=linha.modo_comunicacao,  # type: ignore[attr-defined]
        intervalo_push_segundos=linha.intervalo_push_segundos,  # type: ignore[attr-defined]
        ultimo_log_externo_id=linha.ultimo_log_externo_id,  # type: ignore[attr-defined]
        ultimo_contato_em=linha.ultimo_contato_em,  # type: ignore[attr-defined]
        status=linha.status,  # type: ignore[attr-defined]
    )


async def carregar_terminal(sessao: AsyncSession, terminal_id: UUID) -> TerminalCarregado | None:
    """Sessao ja precisa ter `app.tenant_id` aplicado (RLS) -- ver
    `gateway.dominio.bd.sessao_com_tenant`."""
    linha = (
        await sessao.execute(
            text(f"SELECT {_COLUNAS} FROM terminais WHERE id = :id"),  # noqa: S608
            {"id": str(terminal_id)},
        )
    ).first()
    return _para_terminal(linha) if linha is not None else None


async def carregar_terminal_por_numero_serie(
    sessao: AsyncSession, numero_serie: str
) -> TerminalCarregado | None:
    linha = (
        await sessao.execute(
            text(f"SELECT {_COLUNAS} FROM terminais WHERE numero_serie = :numero_serie"),  # noqa: S608
            {"numero_serie": numero_serie},
        )
    ).first()
    return _para_terminal(linha) if linha is not None else None


async def atualizar_ultimo_contato(sessao: AsyncSession, terminal_id: UUID) -> None:
    """`ultimo_contato_em`: base do alerta de terminal offline (T9)."""
    await sessao.execute(
        text("UPDATE terminais SET ultimo_contato_em = now() WHERE id = :id"),
        {"id": str(terminal_id)},
    )


async def avancar_marca_dagua(sessao: AsyncSession, terminal_id: UUID, novo_valor: int) -> None:
    """Avanca `ultimo_log_externo_id` -- SO depois da gravacao confirmada
    (secao 2 do PCF, "a marca so avanca depois da gravacao confirmada").
    `GREATEST` protege contra reprocessamento fora de ordem regredir a marca."""
    await sessao.execute(
        text(
            "UPDATE terminais SET ultimo_log_externo_id = GREATEST(ultimo_log_externo_id, :novo), "
            "ultima_sincronizacao_em = now() WHERE id = :id"
        ),
        {"id": str(terminal_id), "novo": novo_valor},
    )


def montar_conexao(terminal: TerminalCarregado, *, config: Configuracao) -> ConexaoTerminal:
    """Decifra `senha_api_cifrada` (mesma chave/empacotamento de
    `apps/api/app/terminais/cifra.py`) ou cai para as credenciais globais
    (`CONTROLID_USUARIO`/`CONTROLID_SENHA`) quando o terminal ainda nao tem
    credencial propria cadastrada -- caminho comum no simulador."""
    senha = (
        decifrar_senha(terminal.senha_api_cifrada)
        if terminal.senha_api_cifrada
        else config.controlid_senha.get_secret_value()
    )
    usuario = terminal.usuario_api or config.controlid_usuario
    return ConexaoTerminal(
        numero_serie=terminal.numero_serie,
        endereco_ip=terminal.endereco_ip,
        porta=terminal.porta,
        usuario=usuario,
        senha=senha,
        timeout_s=float(config.controlid_timeout_s),
    )


def obter_cliente_do_terminal(
    terminal: TerminalCarregado, *, config: Configuracao
) -> ClienteControlID:
    """Atalho: monta a `ConexaoTerminal` e devolve o `ClienteControlID` certo
    (real ou simulado, conforme `config.controlid_simulador`) -- nunca
    instancia `ClienteControlIDHttp`/`ClienteControlIDSimulado` diretamente
    (contrato da T1)."""
    conexao = montar_conexao(terminal, config=config)
    return obter_cliente(conexao=conexao, simulador=config.controlid_simulador)
