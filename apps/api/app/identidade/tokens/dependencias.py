"""Dependencia FastAPI de autenticacao para as proprias rotas da tag `auth`.

`app/core/seguranca.py` e o contrato de autorizacao ENTRE fases (F1 e F2). O
corpo real (agente A3, T8) resolve RBAC a partir de `contexto.usuario_atual()`
-- ver `app.identidade.tokens.middleware.AutenticacaoMiddleware`, que publica
esse valor para TODAS as rotas da API. As rotas desta fase que exigem sessao
(`logout`, `reautenticar`, `listarSessoes`, `revogarSessao`, `obterSessaoAtual`)
usam, alem disso, a dependencia abaixo: ela reconfirma a sessao referenciada no
token contra o banco (o middleware, por design, nao consulta banco -- ver sua
docstring), o que fecha a janela entre "token assinado valido" e "sessao ja
revogada" para estas rotas especificas.

Note que esta dependencia NAO abre a sessao de banco que o handler usa para o
resto do trabalho (listar sessoes, revogar, etc.) -- cada handler abre a
propria, com `app.identidade.autenticacao.tenant.sessao_com_tenant_id`, para
manter uma unica responsabilidade por dependencia.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Header
from ponto_contracts import Sessao
from sqlalchemy import select

from app.core.erros import ErroDeAplicacao
from app.identidade.autenticacao.tenant import (
    sessao_com_tenant_id,
    verificar_tenant_do_cabecalho,
)
from app.identidade.tokens.jwt import decodificar_access_token


@dataclass(frozen=True, slots=True)
class SujeitoAutenticado:
    """Identidade decodificada do access token, com a sessao ja confirmada ativa."""

    usuario_id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    sessao_id: uuid.UUID


def _extrair_bearer(cabecalho_authorization: str | None) -> str:
    if not cabecalho_authorization or not cabecalho_authorization.lower().startswith("bearer "):
        raise ErroDeAplicacao("PONTO-AUTH-002")
    token = cabecalho_authorization.split(" ", 1)[1].strip()
    if not token:
        raise ErroDeAplicacao("PONTO-AUTH-002")
    return token


async def obter_sujeito_autenticado(
    authorization: Annotated[str | None, Header()] = None,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
) -> SujeitoAutenticado:
    """Dependencia: exige `Authorization: Bearer <access token>` valido e sessao ativa."""
    token = _extrair_bearer(authorization)
    claims = decodificar_access_token(token)

    tenant_id = uuid.UUID(claims["tenant"])
    sessao_id = uuid.UUID(claims["sid"])
    usuario_id = uuid.UUID(claims["sub"])

    async with sessao_com_tenant_id(tenant_id) as sessao_db:
        await verificar_tenant_do_cabecalho(sessao_db, x_tenant=x_tenant, tenant_esperado=tenant_id)
        registro = (
            await sessao_db.execute(
                select(Sessao).where(Sessao.tenant_id == tenant_id, Sessao.id == sessao_id)
            )
        ).scalar_one_or_none()
        if registro is None or registro.encerrada_em is not None:
            raise ErroDeAplicacao("PONTO-AUTH-006")

    return SujeitoAutenticado(
        usuario_id=usuario_id,
        tenant_id=tenant_id,
        email=claims["email"],
        sessao_id=sessao_id,
    )
