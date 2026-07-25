"""Montagem da aplicacao FastAPI do Ponto Eletronico.

Subir localmente::

    uvicorn app.main:app --reload

Conferir que a aplicacao carrega e quantas rotas tem (usado no aceite da F0)::

    python -c "from app.main import app; print(len(app.routes))"

**Estado desta versao.** A Fase 0 entrega contrato e andaime: as 215 operacoes
de `packages/contracts/openapi.yaml` estao declaradas com a assinatura correta,
e 214 delas respondem 501 com `PONTO-INT-005`. A unica implementada e
`GET /v1/admin/saude`, por ser infraestrutura (ver `app/routers/saude.py`).
Nenhuma regra de negocio existe aqui.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Configuracao, obter_configuracao
from app.core.erros import registrar_tratadores
from app.core.log import configurar_log, obter_logger
from app.core.middleware import (
    RegistroDeAcessoMiddleware,
    RequestIdMiddleware,
    TenantMiddleware,
)
from app.db.sessao import encerrar_engine
from app.routers import registrar_routers

logger = obter_logger("main")

DESCRICAO = """
API REST do **Ponto Eletronico**, sistema REP-P multiempresa em conformidade com a
Portaria MTP 671/2021.

O contrato congelado vive em `packages/contracts/openapi.yaml` e e a fonte da verdade.
Este documento e gerado a partir das rotas realmente montadas: divergencia entre os dois
e defeito, e `python tools/conferir_rotas.py` a detecta.

### Cinco fatos que mudam o desenho do seu cliente

1. **Marcacao e imutavel.** Nao existe alteracao nem exclusao de marcacao, e nao havera.
   Correcao acontece em `POST /v1/tratamentos`, numa camada separada e auditada.
2. **O relogio e do servidor.** O horario do dispositivo e evidencia, nunca fonte de verdade.
3. **NSR sem lacunas.** O Numero Sequencial de Registro e alocado transacionalmente por
   REP-P, comeca em 1 e nunca tem buraco nem reuso.
4. **AFD e AEJ tem escopos diferentes.** O AFD deriva so das marcacoes; o AEJ enxerga
   tratamento, horario contratual, ausencia e banco de horas.
5. **Toda escrita e idempotente.** `Idempotency-Key` e obrigatoria em POST, PUT, PATCH e DELETE.

### Estado da implementacao

Fase 0 entrega **contrato e andaime**. Toda operacao declarada aqui existe e responde
`501` com o codigo `PONTO-INT-005` ate a fase correspondente entrar. O `detail` do 501
informa qual fase implementa a operacao.
"""


@contextlib.asynccontextmanager
async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
    """Inicializacao e encerramento do processo.

    Nao abre conexao com o banco na subida de proposito: a API precisa subir e
    responder `/health` mesmo com o PostgreSQL fora, para que o `/ready` possa
    dizer *por que* nao esta pronta. Subir so quando o banco existe transforma
    indisponibilidade de dependencia em crash loop, que e mais dificil de
    diagnosticar e ainda tira o endpoint de diagnostico do ar.
    """
    config = obter_configuracao()
    logger.info(
        "api iniciada",
        extra={
            "ambiente": config.ambiente,
            "versao": config.versao,
            "commit": config.commit,
            "rotas": len(app.routes),
        },
    )
    try:
        yield
    finally:
        await encerrar_engine()
        logger.info("api encerrada")


def criar_aplicacao(config: Configuracao | None = None) -> FastAPI:
    """Monta a aplicacao. Funcao separada para o teste poder criar instancias."""
    config = config or obter_configuracao()
    configurar_log(config)

    app = FastAPI(
        title="Ponto Eletronico - API v1",
        version=config.versao,
        summary="API REST do sistema de ponto eletronico REP-P multiempresa da SEEG.",
        description=DESCRICAO,
        lifespan=ciclo_de_vida,
        docs_url="/docs" if config.expor_documentacao else None,
        redoc_url="/redoc" if config.expor_documentacao else None,
        openapi_url="/openapi.json" if config.expor_documentacao else None,
        contact={
            "name": "SEEG Servicos de Tecnologia da Informacao",
            "url": "https://docs.ponto.seeg.com.br",
            "email": "suporte@seeg.com.br",
        },
        license_info={"name": "Proprietaria - SEEG"},
    )

    # A ordem importa: o ULTIMO adicionado e o PRIMEIRO a rodar. Request-id
    # precisa ser o mais externo para que qualquer falha ja saia correlacionada.
    app.add_middleware(RegistroDeAcessoMiddleware)
    app.add_middleware(TenantMiddleware, config=config)
    app.add_middleware(RequestIdMiddleware, cabecalho=config.cabecalho_request_id)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.lista_cors_origens,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=[
            config.cabecalho_request_id,
            "Idempotency-Replayed",
            "RateLimit-Limit",
            "RateLimit-Remaining",
            "RateLimit-Reset",
            "RateLimit-Policy",
            "Retry-After",
        ],
        max_age=600,
    )

    registrar_tratadores(app)
    registrar_routers(app)
    return app


app = criar_aplicacao()
