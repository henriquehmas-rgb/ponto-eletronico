"""Gestão de chaves de API (F13/A1, T2 — RFC-016).

`api_clients` já tem CRUD completo desde F1 (`listarApiClients`/`criarApiClient`
em `app/routers/admin.py`, implementados por `app.identidade.rbac.servico` —
não duplicado aqui: este módulo é só a parte NOVA que RFC-016 decidiu,
`api_keys`. Reaproveita `oauth.gerar_api_key` (F1, primitiva pronta) para o
segredo em claro; nunca reimplementa geração/hash.

**Regra de aplicação (RFC-016, decisão do orquestrador item 1): `ambiente` de
uma `ApiKey` nunca excede o `ambiente` do `ApiClient` pai.** Não é `CHECK` de
banco (tabelas distintas) — validado aqui, `PONTO-VAL-001` com `erros_campo`
quando uma chave `producao` é pedida para um cliente `sandbox`.

**Escopos da chave nunca excedem os do cliente pai** (extensão desta
implementação, não literal do texto da RFC — mesma decisão de design que já
existe para o próprio token OAuth: reaproveita
`oauth.calcular_escopo_efetivo`, a MESMA função que `POST /v1/auth/token`
usa para a interseção requerido×concedido, incluindo o mesmo código de erro
`PONTO-PERM-003` quando um escopo pedido não está entre os do cliente).

**Prefixo de ambiente da chave em claro.** `oauth.gerar_api_key` já usa
`prd` para produção (visto no exemplo do contrato, `ApiClientCriado.
apiKeyPrefixo`); não havia convenção estabelecida para sandbox em nenhum
lugar do código — escolhido `sbx` aqui (paralelo óbvio de `prd`/`sandbox`,
sem precedente para contradizer).
"""

from __future__ import annotations

import datetime as _dt
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import ApiClient, ApiKey
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.core.seguranca import Sujeito
from app.identidade.rbac.paginacao import paginar
from app.identidade.tokens import oauth as oauth_mod

__all__ = ["criar_api_key", "listar_api_keys", "revogar_api_key"]

_PREFIXO_POR_AMBIENTE = {"producao": "prd", "sandbox": "sbx"}


async def _carregar_api_client(
    sessao: AsyncSession, *, tenant_id: UUID, api_client_id: UUID
) -> ApiClient:
    cliente = (
        await sessao.execute(
            sa.select(ApiClient).where(
                ApiClient.tenant_id == tenant_id,
                ApiClient.id == api_client_id,
                ApiClient.excluido_em.is_(None),
            )
        )
    ).scalar_one_or_none()
    if cliente is None:
        raise ErroDeAplicacao("PONTO-REC-001", contexto_log={"apiClientId": str(api_client_id)})
    return cliente


async def listar_api_keys(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    api_client_id: UUID,
    cursor: str | None,
    limite: int | None,
) -> tuple[list[ApiKey], dict[str, Any]]:
    """`PONTO-REC-001` quando `api_client_id` não existe (ou é de outro tenant
    — RLS já garante isolamento, o `SELECT` simplesmente não acha a linha)."""
    await _carregar_api_client(sessao, tenant_id=tenant_id, api_client_id=api_client_id)
    consulta = sa.select(ApiKey).where(
        ApiKey.tenant_id == tenant_id, ApiKey.api_client_id == api_client_id
    )
    return await paginar(
        sessao,
        consulta,
        coluna_criado_em=ApiKey.criado_em,
        coluna_id=ApiKey.id,
        cursor=cursor,
        limite=limite,
    )


async def criar_api_key(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    api_client_id: UUID,
    dados: Any,
    sujeito: Sujeito,
) -> tuple[ApiKey, str]:
    """Cria a `ApiKey`. Devolve `(chave, chave_em_claro)` — o valor em claro
    aparece só aqui, uma única vez (o que fica gravado é `hash`, SHA-256).

    `PONTO-REC-001` quando `api_client_id` não existe; `PONTO-VAL-001` quando
    `ambiente` pedido excede o do cliente; `PONTO-PERM-003` quando algum
    escopo pedido não está entre os concedidos ao cliente.
    """
    cliente = await _carregar_api_client(sessao, tenant_id=tenant_id, api_client_id=api_client_id)

    ambiente_pedido = dados.ambiente.value if dados.ambiente else cliente.ambiente
    if ambiente_pedido == "producao" and cliente.ambiente != "producao":
        raise ErroDeAplicacao(
            "PONTO-VAL-001",
            erros_campo=[
                {
                    "campo": "ambiente",
                    "mensagem": "nao pode exceder o ambiente do ApiClient pai (cliente sandbox "
                    "so emite chave sandbox)",
                }
            ],
        )

    escopos_pedidos = " ".join(dados.escopos or [])
    escopos_efetivos = oauth_mod.calcular_escopo_efetivo(
        escopos_pedidos or None, list(cliente.escopos or [])
    )

    prefixo_ambiente = _PREFIXO_POR_AMBIENTE.get(ambiente_pedido, "sbx")
    chave_bruta, prefixo, hash_ = oauth_mod.gerar_api_key(prefixo_ambiente=prefixo_ambiente)

    registro = ApiKey(
        tenant_id=tenant_id,
        api_client_id=api_client_id,
        prefixo=prefixo,
        hash=hash_,
        rotulo=dados.rotulo,
        ambiente=ambiente_pedido,
        escopos=escopos_efetivos,
        expira_em=dados.expira_em,
        criado_por=sujeito.usuario_id,
    )
    sessao.add(registro)
    await sessao.flush()
    return registro, chave_bruta


async def revogar_api_key(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    api_client_id: UUID,
    chave_id: UUID,
    motivo: str | None = None,
) -> None:
    """Idempotente por natureza (RFC-016): revogar uma chave já revogada não
    é erro, só não regrava `revogada_em`. `PONTO-REC-001` quando a chave (ou
    o cliente) não existe."""
    await _carregar_api_client(sessao, tenant_id=tenant_id, api_client_id=api_client_id)
    chave = (
        await sessao.execute(
            sa.select(ApiKey).where(
                ApiKey.tenant_id == tenant_id,
                ApiKey.api_client_id == api_client_id,
                ApiKey.id == chave_id,
            )
        )
    ).scalar_one_or_none()
    if chave is None:
        raise ErroDeAplicacao("PONTO-REC-001", contexto_log={"chaveId": str(chave_id)})
    if chave.revogada_em is None:
        chave.revogada_em = _dt.datetime.now(_dt.UTC)
        chave.motivo_revogacao = motivo
