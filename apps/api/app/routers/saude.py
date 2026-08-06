"""Sinais de vida e de prontidao. ESCRITO A MAO -- nao e gerado.

Tres endpoints, com papeis diferentes de proposito:

``GET /health`` (*liveness*)
    "O processo esta vivo?" Nao toca em banco, Redis nem MinIO. E o alvo do
    `healthcheck` do Docker e do `loadbalancer.healthcheck.path` do Traefik
    (ver `infra/docker-compose.yml`). Se dependesse do banco, uma queda de
    PostgreSQL derrubaria os containers da API em cascata -- e o restart nao
    resolveria nada, porque o defeito nao esta neles.

``GET /ready`` (*readiness*)
    "Da para mandar trafego?" Consulta banco e Redis com prazo curto. Responde
    503 com `PONTO-INT-003` quando alguma dependencia obrigatoria esta fora.
    E o endpoint que um orquestrador usa para tirar a instancia do balanceador
    sem mata-la.

``GET /v1/admin/saude`` (`obterSaude`, do contrato)
    Mesma informacao de `/ready`, no formato `Saude` do OpenAPI, para o painel
    de operacao. **Unica operacao do contrato implementada na Fase 0**: e
    infraestrutura, nao regra de negocio, e um endpoint de saude que responde
    501 seria pior do que inutil. As outras 214 respondem `PONTO-INT-005`.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from typing import Any, Final

from fastapi import APIRouter, status

from app.core.config import Configuracao, obter_configuracao
from app.core.erros import RESPOSTAS_PADRAO, ErroDeAplicacao
from app.core.log import obter_logger
from app.db.sessao import verificar_banco
from app.schemas import contrato

logger = obter_logger("saude")

roteador = APIRouter()

#: Dependencias sem as quais a instancia nao consegue atender: a ausencia
#: delas reprova o /ready. `minio` e `facial-svc` sao verificados a partir da
#: F5 e da F7, quando passam a ser exercitados de fato.
DEPENDENCIAS_OBRIGATORIAS: Final[tuple[str, ...]] = ("banco", "redis")


async def _verificar_redis(url: str, timeout_s: float) -> tuple[bool, str]:
    """PING no Redis com prazo. Nunca levanta excecao."""
    try:
        import redis.asyncio as redis_assincrono

        async with asyncio.timeout(timeout_s):
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


async def _coletar_dependencias(config: Configuracao) -> dict[str, dict[str, Any]]:
    """Verifica banco e Redis em paralelo e devolve o mapa de estado."""
    banco, redis_ = await asyncio.gather(
        verificar_banco(config.database_timeout_saude_s),
        _verificar_redis(config.redis_url, config.redis_timeout_saude_s),
    )
    return {
        "banco": {"status": "ok" if banco[0] else "indisponivel", "detalhe": banco[1]},
        "redis": {"status": "ok" if redis_[0] else "indisponivel", "detalhe": redis_[1]},
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
    include_in_schema=False,
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
    include_in_schema=False,
)
async def verificar_prontidao() -> dict[str, Any]:
    """Verifica banco e Redis. 200 quando pronto, 503 `PONTO-INT-003` quando nao."""
    config = obter_configuracao()
    dependencias = await _coletar_dependencias(config)
    estado = _estado_agregado(dependencias)

    if estado == "indisponivel":
        quebradas = sorted(nome for nome, dado in dependencias.items() if dado["status"] != "ok")
        logger.warning("instancia nao pronta", extra={"dependencias": quebradas})
        # Levantar (em vez de montar a resposta aqui) garante que a saida passe
        # pelo tratador padrao e saia em application/problem+json.
        raise ErroDeAplicacao(
            "PONTO-INT-003",
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
        "verificadoEm": dt.datetime.now(tz=dt.UTC).isoformat(),
    }


@roteador.get(
    "/v1/admin/saude",
    status_code=status.HTTP_200_OK,
    operation_id="obterSaude",
    summary="Saude da API e das dependencias",
    tags=["admin"],
    responses=RESPOSTAS_PADRAO,
)
async def obter_saude() -> contrato.Saude:
    """Estado operacional da instancia, no formato `Saude` do contrato."""
    config = obter_configuracao()
    dependencias = await _coletar_dependencias(config)
    ambiente = config.ambiente if config.ambiente in ("dev", "hml", "prd") else "dev"
    return contrato.Saude.model_validate(
        {
            "status": _estado_agregado(dependencias),
            "versao": config.versao,
            "commit": config.commit or None,
            "ambiente": ambiente,
            "dependencias": dependencias,
            "verificadoEm": dt.datetime.now(tz=dt.UTC),
        }
    )
