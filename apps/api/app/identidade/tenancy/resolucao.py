"""Resolucao do tenant contra `fn_resolve_tenant` (unica porta antes da sessao).

`fn_resolve_tenant(p_slug TEXT)` (`packages/contracts/schema.sql`, secao 2) e
`SECURITY DEFINER`: e a unica maneira permitida de descobrir um tenant antes de
`app.tenant_id` existir na sessao, sem desabilitar RLS e sem conectar como uma
role com `BYPASSRLS` (proibicao explicita do PCF da fase, secao 9.3). Ela expoe
apenas quatro colunas -- nao ha como enumerar a base de clientes por aqui.

Resolve por **slug OU UUID** (ver `docs/rfc/RFC-004-resolucao-de-tenant-por-uuid.md`,
decidida e implementada -- opcao (a)): quando o valor recebido casa com o
formato de UUID, a funcao compara por `t.id`; caso contrario, por `t.slug`. A
mesma assinatura (`TEXT` -> 4 colunas) e o mesmo comportamento para slug de
antes, sem migration nova nesta fase (o corpo da funcao mudou dentro de
`0001_inicial.py`, que ainda e a UNICA migration da Fase 1 -- ver RFC-004).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

#: Status de `tenants.status` (ver `packages/contracts/models/tenancy.py`) que
#: barram acesso: `PONTO-TEN-003`. `trial` e `ativo` passam.
STATUS_BLOQUEADOS: frozenset[str] = frozenset({"suspenso", "cancelado"})


@dataclass(frozen=True, slots=True)
class TenantResolvido:
    """As quatro colunas devolvidas por `fn_resolve_tenant`."""

    id: uuid.UUID
    slug: str
    nome_exibicao: str
    status: str

    @property
    def bloqueado(self) -> bool:
        """Verdadeiro quando o tenant esta `suspenso` ou `cancelado` (PONTO-TEN-003)."""
        return self.status in STATUS_BLOQUEADOS


async def resolver_tenant(engine: AsyncEngine, identificador: str) -> TenantResolvido | None:
    """Resolve o identificador do `X-Tenant`/subdominio via `fn_resolve_tenant`.

    Devolve `None` quando nao ha tenant com este slug (ou quando
    `identificador` e um UUID -- ver RFC-004 no docstring do modulo). Nao abre
    nenhuma transacao de aplicacao nem publica `app.tenant_id`: e uma consulta
    isolada, curta, devolvida ao pool assim que termina.
    """
    async with engine.connect() as conexao:
        linha = (
            await conexao.execute(
                text("SELECT id, slug, nome_exibicao, status FROM fn_resolve_tenant(:slug)"),
                {"slug": identificador},
            )
        ).first()
    if linha is None:
        return None
    return TenantResolvido(
        id=linha.id, slug=linha.slug, nome_exibicao=linha.nome_exibicao, status=linha.status
    )
