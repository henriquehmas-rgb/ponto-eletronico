"""Combinador de autenticacao para a tag `webhooks`: o contrato declara TRES
esquemas alternativos por operacao (`packages/contracts/openapi.yaml`,
`security: [bearerAuth: [], oauth2: [...], apiKeyAuth: []]`) -- sessao humana
(JWT, usada pelo painel de RH/gestor, A4/T14) OU cliente de integracao
(token OAuth client-credentials ou `X-API-Key`, T1 de A1). As duas rotas de
autenticacao continuam SEPARADAS (nenhuma mistura de conceito):

* Sessao humana: `app.core.seguranca.exigir_permissao` (F1, INTOCAVEL nesta
  fase -- so leitura/uso, nunca edicao, ver PCF §2.3/§9.1). Devolve `Sujeito`.
* Cliente de integracao: `app.comum.autenticacao_cliente.exigir_escopo` (A1,
  T1, "leve" -- so a assinatura e necessaria aqui). Devolve `ClienteAutenticado`.

Este modulo NAO duplica a logica de nenhum dos dois: chama
`exigir_permissao(permissao)` primeiro (reaproveitando TODA a logica de
`perfis_somente_leitura`/registro de acesso sensivel que aquele modulo ja
implementa), e so cai para `exigir_escopo(escopo)` quando nao ha sessao
humana autenticada (`sujeito.autenticado is False` -- nunca um erro
"talvez"; `obter_sujeito()` sempre devolve o sujeito anonimo em vez de
levantar, entao a checagem e direta).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import Depends, Request

from app.core.seguranca import Sujeito, exigir_permissao, obter_sujeito, tenant_id_ou_erro

if TYPE_CHECKING:
    from app.comum.autenticacao_cliente import ClienteAutenticado


@dataclass(frozen=True, slots=True)
class ContextoAcesso:
    """Uniao das duas formas de acesso valido a um endpoint de `webhooks`.
    Exatamente um de `sujeito`/`cliente` e nao-nulo."""

    tenant_id: UUID
    sujeito: Sujeito | None = None
    cliente: ClienteAutenticado | None = None

    @property
    def api_client_id(self) -> UUID | None:
        cliente = self.cliente
        if cliente is None:
            return None
        return cliente.api_client_id


def exigir_permissao_ou_escopo(
    *, permissao: str, escopo: str
) -> Callable[..., Awaitable[ContextoAcesso]]:
    """Fabrica de dependencia FastAPI: sessao humana com `permissao`
    concedida OU cliente de integracao com `escopo` concedido.

    Tenta sessao humana primeiro (reaproveitando `exigir_permissao` por
    inteiro -- inclusive o veto de `perfis_somente_leitura` e o registro de
    `acessos_dados_sensiveis`). Sem sessao humana autenticada, cai para
    `exigir_escopo` (A1). As duas falhas possiveis desta segunda etapa
    (`PONTO-AUTH-002` sem credencial nenhuma, `PONTO-PERM-003` escopo
    insuficiente) sao as que a dependencia de A1 ja produz -- nao
    reimplementadas aqui.
    """

    async def _resolver(
        request: Request,
        sujeito: Annotated[Sujeito, Depends(obter_sujeito)],
    ) -> ContextoAcesso:
        if sujeito.autenticado:
            verificador = exigir_permissao(permissao)
            confirmado = await verificador(sujeito=sujeito)
            return ContextoAcesso(tenant_id=tenant_id_ou_erro(confirmado), sujeito=confirmado)

        # Import tardio: `app.comum.autenticacao_cliente` e de A1 (T1). Import
        # no corpo da funcao (nao no topo do modulo) para que este arquivo
        # continue importavel mesmo antes daquele modulo existir, durante o
        # desenvolvimento em paralelo dos dois agentes.
        from app.comum.autenticacao_cliente import exigir_escopo

        # `exigir_escopo` devolve uma dependencia cujos tres parametros de
        # cabecalho tem DEFAULT `Header()` (marcador do FastAPI, resolvido
        # so quando chamado via `Depends()` de verdade) -- chamando-a
        # manualmente aqui (para poder tentar sessao humana primeiro), os
        # cabecalhos precisam ser extraidos e passados explicitamente, mesmo
        # valor que o FastAPI leria.
        cliente = await exigir_escopo(escopo)(
            request,
            authorization=request.headers.get("authorization"),
            x_api_key=request.headers.get("x-api-key"),
            x_tenant=request.headers.get("x-tenant"),
        )
        return ContextoAcesso(tenant_id=cliente.tenant_id, cliente=cliente)

    return _resolver
