"""Chamada a `POST /v1/marcacoes` (tag `marcacoes`, F5) -- a API interna que
o `device-gw` alimenta.

Ponto de atencao n. 2 do PCF da F6: `POST /v1/marcacoes` e implementado pela
F5, que roda em paralelo nesta mesma onda. Ate a F5 terminar, o endpoint
responde `501`. Este modulo trata esse caso explicitamente
(`MarcacaoAindaNaoDisponivel`) em vez de deixar a excecao generica de HTTP
vazar -- o chamador (`push.py`/`monitor.py`/`catchup.py`) decide se mantem o
item pendente ou propaga.

Autenticacao: `X-API-Key` (`apiKeyAuth` do contrato) -- uma "conta tecnica de
integracao" (`api_clients.tipo = 'maquina'`), nunca um usuario humano. Ver
`apps/api/app/terminais/servico.py` (T3) para a documentacao do lado que cria
essa credencial, e `docs/backlog.md` para a pendencia de semeadura.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx

from gateway.config import Configuracao
from gateway.erros import ErroDeAplicacao
from gateway.log import obter_logger

logger = obter_logger("dominio.cliente_api")

CODIGO_DEPENDENCIA_FORA = "PONTO-INT-003"
CODIGO_ERRO_INTERNO = "PONTO-INT-001"


class MarcacaoAindaNaoDisponivel(RuntimeError):
    """`POST /v1/marcacoes` respondeu `501`: a F5 ainda nao terminou (Ponto de
    Atencao n. 2 do PCF). Nao e erro do device-gw -- o chamador decide se
    mantem o item pendente para reentrega."""


async def enviar_marcacao(
    config: Configuracao,
    *,
    tenant_id: UUID | str,
    corpo: dict[str, Any],
    idempotency_key: str,
    request_id: str | None = None,
    cliente: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Envia um `MarcacaoCriar` a API interna. Devolve o corpo JSON da
    resposta (`MarcacaoCriada`) em qualquer resultado 2xx -- inclusive
    reapresentacao (`duplicada: true` no corpo, conforme o contrato).

    Levanta `MarcacaoAindaNaoDisponivel` em `501` e `ErroDeAplicacao` em
    qualquer outra falha (a API devolve `application/problem+json`; o
    `codigo` de la vira o codigo daqui quando reconhecido no catalogo deste
    servico, ou `PONTO-INT-003`/`PONTO-INT-001` como fallback).
    """
    cabecalhos = {
        "X-Tenant": str(tenant_id),
        "X-API-Key": config.api_key_marcacoes.get_secret_value(),
        "Idempotency-Key": idempotency_key,
        "Content-Type": "application/json",
    }
    if request_id:
        cabecalhos["X-Request-Id"] = request_id

    proprio_cliente = cliente is None
    if cliente is None:
        cliente = httpx.AsyncClient(
            base_url=config.api_base_url, timeout=config.api_timeout_saude_s * 3
        )
    try:
        resposta = await cliente.post("/v1/marcacoes", json=corpo, headers=cabecalhos)
    except httpx.HTTPError as exc:
        logger.warning("falha de rede ao chamar POST /v1/marcacoes", extra={"erro": str(exc)})
        raise ErroDeAplicacao(CODIGO_DEPENDENCIA_FORA, contexto_log={"erro": str(exc)}) from exc
    finally:
        if proprio_cliente:
            await cliente.aclose()

    if resposta.status_code == httpx.codes.NOT_IMPLEMENTED:
        raise MarcacaoAindaNaoDisponivel(
            "POST /v1/marcacoes respondeu 501 -- a F5 ainda nao implementou o endpoint."
        )
    if resposta.status_code // 100 == 2:
        corpo_resposta: dict[str, Any] = resposta.json()
        return corpo_resposta

    detalhe = _extrair_problema(resposta)
    logger.warning(
        "POST /v1/marcacoes recusado",
        extra={"status": resposta.status_code, "codigo": detalhe.get("codigo")},
    )
    codigo = detalhe.get("codigo") or (
        CODIGO_DEPENDENCIA_FORA if resposta.status_code >= 500 else CODIGO_ERRO_INTERNO
    )
    raise ErroDeAplicacao(
        codigo if _codigo_conhecido(codigo) else CODIGO_ERRO_INTERNO,
        contexto_log={"statusApi": resposta.status_code, "codigoApi": detalhe.get("codigo")},
    )


def _extrair_problema(resposta: httpx.Response) -> dict[str, Any]:
    try:
        corpo = resposta.json()
    except ValueError:
        return {}
    return corpo if isinstance(corpo, dict) else {}


def _codigo_conhecido(codigo: str) -> bool:
    from gateway.erros import CATALOGO

    return codigo in CATALOGO
