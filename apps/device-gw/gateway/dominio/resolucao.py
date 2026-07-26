"""Resolucao de terminal ANTES de existir tenant (RFC-010, Ponto de Atencao
n. 1 do PCF da F6).

O terminal se identifica pelo `numero_serie` mais o segredo de Push -- nao ha
`X-Tenant`, porque o firmware nao sabe o que e um tenant. `terminais` esta sob
`FORCE ROW LEVEL SECURITY` e `uq_terminais_serie` e unico **por tenant**, nao
globalmente: o mesmo problema que `fn_resolve_tenant` resolve para login,
`fn_resolve_terminal` resolve aqui (RFC-010,
`packages/contracts/schema.sql`). Nunca desabilite RLS nem conecte com role
`BYPASSRLS` para contornar isto -- e a proibicao explicita da secao 9.3 do PCF.

Duas defesas deliberadas:

1. **Ambiguidade nunca escolhe a primeira linha.** `fn_resolve_terminal`
   devolve ate 2 linhas *de proposito* -- ver o comentario da funcao no
   schema. Duas linhas e um estado que nao deveria acontecer (o `numero_serie`
   e unico por tenant, nao globalmente, mas dois tenants diferentes PODEM
   cadastrar o mesmo numero de serie por engano de digitacao do instalador).
   Tratamos como erro interno, nunca como "pegue a primeira".
2. **A mensagem nao revela qual parte falhou.** `numero_serie` inexistente,
   terminal `excluido_em` preenchido (a funcao ja filtra), terminal `inativo`
   e token errado respondem exatamente o mesmo `PONTO-TERM-003` sem `detail`
   especifico -- o codigo tem `expoe_regra: true`, mas a UNICA distincao entre
   "nao existe" e "existe mas esta inativo" seria util para alguem varrendo
   numeros de serie.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from gateway.config import Configuracao
from gateway.dominio.bd import conexao_sem_tenant
from gateway.erros import ErroDeAplicacao

CODIGO_TERMINAL_RECUSADO = "PONTO-TERM-003"


class AmbiguidadeDeTerminal(RuntimeError):
    """`fn_resolve_terminal` devolveu mais de uma linha para o mesmo numero de
    serie. Nao deveria acontecer na pratica (ver docstring do modulo); quando
    acontece, e erro interno -- nunca escolha a primeira linha em silencio."""


@dataclass(frozen=True, slots=True)
class TerminalResolvido:
    """As tres colunas devolvidas por `fn_resolve_terminal`."""

    id: UUID
    tenant_id: UUID
    status: str


async def _linhas_fn_resolve_terminal(
    conexao: AsyncConnection, numero_serie: str
) -> list[TerminalResolvido]:
    resultado = await conexao.execute(
        text("SELECT id, tenant_id, status FROM fn_resolve_terminal(:numero_serie)"),
        {"numero_serie": numero_serie},
    )
    return [
        TerminalResolvido(id=linha.id, tenant_id=linha.tenant_id, status=linha.status)
        for linha in resultado.all()
    ]


async def resolver_terminal(
    numero_serie: str, *, config: Configuracao | None = None
) -> TerminalResolvido:
    """Resolve `numero_serie` -> `(id, tenant_id, status)` via
    `fn_resolve_terminal`. `PONTO-TERM-003` quando nao existe ou nao esta
    `ativo`. Levanta `AmbiguidadeDeTerminal` (500, nunca 502) quando a funcao
    devolve 2 linhas -- ver docstring do modulo."""
    async with conexao_sem_tenant(config=config) as conexao:
        linhas = await _linhas_fn_resolve_terminal(conexao, numero_serie)
    if not linhas:
        raise ErroDeAplicacao(CODIGO_TERMINAL_RECUSADO)
    if len(linhas) > 1:
        raise AmbiguidadeDeTerminal(
            f"numero_serie {numero_serie!r} resolveu para {len(linhas)} terminais distintos."
        )
    resolvido = linhas[0]
    if resolvido.status != "ativo":
        raise ErroDeAplicacao(CODIGO_TERMINAL_RECUSADO)
    return resolvido


async def token_esperado(sessao: AsyncSession, terminal_id: UUID) -> str | None:
    """`terminais.token_push` do terminal (sessao ja com `app.tenant_id`
    aplicado -- ver `gateway.dominio.bd.sessao_com_tenant`)."""
    linha = (
        await sessao.execute(
            text("SELECT token_push FROM terminais WHERE id = :id"), {"id": str(terminal_id)}
        )
    ).first()
    return linha.token_push if linha is not None else None


def token_confere(apresentado: str, esperado: str) -> bool:
    """Comparacao em tempo constante -- nunca `==` de string (secao 9.3 /
    T2 do PCF). `hmac.compare_digest` sempre percorre os dois operandos por
    inteiro, independente de onde a primeira diferenca de byte aparece."""
    return hmac.compare_digest(apresentado.encode("utf-8"), esperado.encode("utf-8"))


def extrair_identificacao(corpo: dict[str, Any]) -> tuple[str, str]:
    """Extrai `numeroSerie`/`token` do corpo enviado pelo equipamento (Push
    ou Monitor -- os dois usam a mesma convencao de identificacao, T2).
    Aceita algumas variantes de nome de campo porque o formato exato do
    firmware real nao foi verificado contra hardware (secao 2 do PCF)."""
    numero_serie = str(
        corpo.get("numeroSerie") or corpo.get("numero_serie") or corpo.get("deviceId") or ""
    )
    token = str(corpo.get("token") or corpo.get("pushToken") or "")
    if not numero_serie or not token:
        raise ErroDeAplicacao(
            "PONTO-VAL-001", detalhe="Corpo precisa informar numeroSerie e token."
        )
    return numero_serie, token


async def autenticar_terminal(
    numero_serie: str,
    token_apresentado: str,
    *,
    config: Configuracao,
) -> TerminalResolvido:
    """Fluxo completo de T2: resolve o terminal, confirma o token em tempo
    constante e devolve `(id, tenant_id, status)` pronto para
    `sessao_com_tenant`.

    Quando o terminal nao tem `token_push` proprio cadastrado (provisionamento
    ainda nao rodou, ou ambiente de simulador), cai para
    `CONTROLID_PUSH_TOKEN` (o segredo global de instalacao) como padrao de
    desenvolvimento -- nunca em producao, onde `push_token_configurado` exige
    o valor.
    """
    from gateway.dominio.bd import sessao_com_tenant

    resolvido = await resolver_terminal(numero_serie, config=config)
    async with sessao_com_tenant(str(resolvido.tenant_id), config=config) as sessao:
        esperado = await token_esperado(sessao, resolvido.id)
    if not esperado:
        esperado = config.controlid_push_token.get_secret_value()
    if not esperado or not token_confere(token_apresentado, esperado):
        raise ErroDeAplicacao(CODIGO_TERMINAL_RECUSADO)
    return resolvido
