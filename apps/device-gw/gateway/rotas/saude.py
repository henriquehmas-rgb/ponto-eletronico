"""Sinais de vida e de prontidao do device-gw. **Funcionais na Fase 0.**

Dois endpoints, com papeis diferentes de proposito:

``GET /health`` (*liveness*)
    "O processo esta vivo?" Nao toca em Redis nem na API. E o alvo do
    `healthcheck` do container e do `loadbalancer.healthcheck.path` do Traefik
    (`infra/docker-compose.yml`, servico `device-gw`). Se dependesse de
    dependencia externa, uma queda do Redis derrubaria os containers do gateway
    em cascata — e o restart nao resolveria nada, porque o defeito nao esta
    neles. Pior: derrubaria justamente o servico que recebe marcacao de
    terminal, que e o que menos pode cair.

``GET /ready`` (*readiness*)
    "Da para mandar trafego?" Consulta Redis e a API interna com prazo curto e
    responde 503 `PONTO-INT-003` quando alguma dependencia obrigatoria esta
    fora. E o endpoint que um orquestrador usa para tirar a instancia do
    balanceador sem mata-la.

Estes dois sao os unicos endpoints funcionais do servico na Fase 0. Todo o resto
responde 501 `PONTO-INT-005` — um endpoint de saude que responde 501 seria pior
do que inutil.

Nenhum dos dois aparece em `packages/contracts/openapi.yaml`: o contrato publico
descreve a API do produto, e o device-gw nao e API de produto. Ele fala o
protocolo do fabricante de um lado e chama a API interna do outro.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from typing import Any, Final

from fastapi import APIRouter, status

from gateway.config import Configuracao, obter_configuracao
from gateway.erros import CODIGO_DEPENDENCIA_FORA, RESPOSTAS_PADRAO, ErroDeAplicacao
from gateway.log import obter_logger

logger = obter_logger("saude")

roteador = APIRouter()

#: Dependencias sem as quais a instancia nao consegue atender. O Redis guarda a
#: fila de comandos do modo Push e a marca d'agua do catch-up; a API e quem
#: atribui NSR e grava a marcacao. Sem um dos dois, receber `access_log` do
#: terminal so produziria perda silenciosa.
DEPENDENCIAS_OBRIGATORIAS: Final[tuple[str, ...]] = ("redis", "api")


async def _verificar_redis(url: str, timeout_s: float) -> tuple[bool, str]:
    """PING no Redis com prazo. Nunca levanta excecao."""
    try:
        import redis.asyncio as redis_assincrono

        async with asyncio.timeout(timeout_s):
            # `redis.asyncio.from_url` nao tem anotacao de retorno na
            # redis-py 5/6/8, e `mypy --strict` (o perfil declarado no
            # pyproject deste app) recusa chamada a funcao nao tipada. O
            # `mypy apps packages` do CI roda da raiz, sem strict, e nao ve o
            # aviso — a isencao existe para o modo estrito continuar limpo.
            cliente = redis_assincrono.from_url(url)  # type: ignore[no-untyped-call]
            try:
                await cliente.ping()
            finally:
                await cliente.aclose()
        return True, "ok"
    except TimeoutError:
        return False, f"timeout apos {timeout_s}s"
    except Exception as exc:
        return False, type(exc).__name__


async def _verificar_api(base_url: str, timeout_s: float) -> tuple[bool, str]:
    """GET /health na API interna, com prazo. Nunca levanta excecao."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout_s) as cliente:
            resposta = await cliente.get(f"{base_url.rstrip('/')}/health")
        if resposta.status_code == status.HTTP_200_OK:
            return True, "ok"
        return False, f"HTTP {resposta.status_code}"
    except Exception as exc:
        return False, type(exc).__name__


async def _coletar_dependencias(config: Configuracao) -> dict[str, dict[str, Any]]:
    """Verifica Redis e API em paralelo e devolve o mapa de estado."""
    redis_, api = await asyncio.gather(
        _verificar_redis(config.redis_url, config.redis_timeout_saude_s),
        _verificar_api(config.api_base_url, config.api_timeout_saude_s),
    )
    return {
        "redis": {"status": "ok" if redis_[0] else "indisponivel", "detalhe": redis_[1]},
        "api": {"status": "ok" if api[0] else "indisponivel", "detalhe": api[1]},
    }


def _estado_agregado(dependencias: dict[str, dict[str, Any]]) -> str:
    quebradas = [
        nome
        for nome, estado in dependencias.items()
        if estado["status"] != "ok" and nome in DEPENDENCIAS_OBRIGATORIAS
    ]
    if quebradas:
        return "indisponivel"
    if any(estado["status"] != "ok" for estado in dependencias.values()):
        return "degradado"
    return "ok"


@roteador.get(
    "/health",
    status_code=status.HTTP_200_OK,
    operation_id="verificarVida",
    summary="Sinal de vida do processo (liveness)",
    tags=["operacao"],
)
async def verificar_vida() -> dict[str, str]:
    """Responde 200 enquanto o processo consegue atender. Nao toca dependencia."""
    config = obter_configuracao()
    return {
        "status": "ok",
        "servico": config.otel_service_name,
        "versao": config.versao,
        "ambiente": config.ambiente,
    }


@roteador.get(
    "/ready",
    status_code=status.HTTP_200_OK,
    operation_id="verificarProntidao",
    summary="Prontidao para receber trafego (readiness)",
    tags=["operacao"],
    responses=RESPOSTAS_PADRAO,
)
async def verificar_prontidao() -> dict[str, Any]:
    """Verifica Redis e API interna. 200 quando pronto, 503 `PONTO-INT-003` quando nao."""
    config = obter_configuracao()
    dependencias = await _coletar_dependencias(config)
    estado = _estado_agregado(dependencias)

    if estado == "indisponivel":
        quebradas = sorted(nome for nome, dado in dependencias.items() if dado["status"] != "ok")
        logger.warning("instancia nao pronta", extra={"dependencias": quebradas})
        # Levantar (em vez de montar a resposta aqui) garante que a saida passe
        # pelo tratador padrao e saia em application/problem+json.
        raise ErroDeAplicacao(
            CODIGO_DEPENDENCIA_FORA,
            detalhe=f"Dependencia indisponivel: {', '.join(quebradas)}.",
            tentar_novamente_em=5,
            contexto_log={"dependencias": quebradas},
        )

    return {
        "status": estado,
        "servico": config.otel_service_name,
        "versao": config.versao,
        "ambiente": config.ambiente,
        "dependencias": dependencias,
        "simulador": config.controlid_simulador,
        # Informativo na Fase 0; a F6 transforma ausencia de token em recusa de
        # subida quando o ambiente e hml ou prd.
        "pushTokenConfigurado": config.push_token_configurado,
        "verificadoEm": dt.datetime.now(tz=dt.UTC).isoformat(),
    }
