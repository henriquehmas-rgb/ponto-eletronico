"""Sinais de vida e de prontidao do facial-svc. **Funcionais na Fase 0.**

``GET /health`` (*liveness*)
    "O processo esta vivo?" Nao carrega modelo, nao le disco, nao mede nada. E
    o alvo do `healthcheck` do container (`infra/docker-compose.yml` usa o
    ancora `x-healthcheck-http-py`, que bate em `http://127.0.0.1:8000/health`)
    e, por consequencia, o que libera o `depends_on: service_healthy` da `api`.
    Se ele dependesse dos pesos ONNX, um volume `facial-models` vazio deixaria a
    **stack inteira** presa no `depends_on` — a API nem subiria para dizer o
    que esta errado.

``GET /ready`` (*readiness*)
    "Da para mandar captura?" Confere se ha peso `.onnx` no diretorio de modelos
    e responde 503 `PONTO-INT-003` quando nao ha. E a distincao que importa
    aqui: sem modelo o servico esta **vivo e inutil**, e essa e exatamente a
    situacao que um readiness existe para descrever.

Estes dois sao os unicos endpoints funcionais do servico na Fase 0. As tres
operacoes biometricas respondem 501 `PONTO-INT-005`.
"""

from __future__ import annotations

import datetime as dt
import pathlib
from typing import Any

from fastapi import APIRouter, status

from facial.config import Configuracao, obter_configuracao
from facial.erros import CODIGO_DEPENDENCIA_FORA, RESPOSTAS_PADRAO, ErroDeAplicacao
from facial.log import obter_logger

logger = obter_logger("saude")

roteador = APIRouter()


def _inventario_de_modelos(config: Configuracao) -> dict[str, Any]:
    """Descreve o diretorio de pesos sem revelar caminho absoluto na resposta.

    O nome dos arquivos e util para diagnostico ("o volume tem o detector mas
    nao o reconhecedor"); o caminho completo dentro do container nao acrescenta
    nada a quem depura e e informacao de topologia.
    """
    diretorio = pathlib.Path(config.facial_model_dir)
    if not diretorio.is_dir():
        return {"presentes": False, "arquivos": [], "detalhe": "diretorio inexistente"}
    arquivos = sorted(caminho.name for caminho in diretorio.glob("**/*.onnx"))
    return {
        "presentes": bool(arquivos),
        "arquivos": arquivos,
        "detalhe": "ok" if arquivos else "nenhum arquivo .onnx encontrado",
    }


@roteador.get(
    "/health",
    status_code=status.HTTP_200_OK,
    operation_id="verificarVida",
    summary="Sinal de vida do processo (liveness)",
    tags=["operacao"],
)
async def verificar_vida() -> dict[str, str]:
    """Responde 200 enquanto o processo consegue atender. Nao toca disco."""
    config = obter_configuracao()
    return {
        "status": "ok",
        "servico": config.otel_service_name,
        "versao": config.versao,
        "ambiente": config.ambiente,
        "modeloVersao": config.facial_model_versao,
    }


@roteador.get(
    "/ready",
    status_code=status.HTTP_200_OK,
    operation_id="verificarProntidao",
    summary="Prontidao para receber captura (readiness)",
    tags=["operacao"],
    responses=RESPOSTAS_PADRAO,
)
async def verificar_prontidao() -> dict[str, Any]:
    """Verifica os pesos do motor. 200 quando pronto, 503 `PONTO-INT-003` quando nao."""
    config = obter_configuracao()
    modelos = _inventario_de_modelos(config)

    if not modelos["presentes"]:
        logger.warning(
            "instancia nao pronta: pesos do motor facial ausentes",
            extra={"detalhe": modelos["detalhe"], "modeloVersao": config.facial_model_versao},
        )
        raise ErroDeAplicacao(
            CODIGO_DEPENDENCIA_FORA,
            detalhe=(
                "Pesos do motor facial ausentes. Confira o volume `facial-models` "
                "e a variavel FACIAL_MODEL_DIR."
            ),
            tentar_novamente_em=15,
            contexto_log={"modelos": modelos["detalhe"]},
        )

    return {
        "status": "ok",
        "servico": config.otel_service_name,
        "versao": config.versao,
        "ambiente": config.ambiente,
        "modeloVersao": config.facial_model_versao,
        "modelos": modelos,
        # O limiar NAO aparece aqui de proposito, mesmo sendo endpoint interno:
        # `PONTO-SCORE-003` tem `expoe_regra: false`, e um `/ready` e o tipo de
        # rota que acaba exposta em painel por descuido.
        "mtlsConfigurado": bool(config.facial_mtls_ca_path),
        "verificadoEm": dt.datetime.now(tz=dt.UTC).isoformat(),
    }
