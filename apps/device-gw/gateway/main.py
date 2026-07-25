"""Montagem da aplicacao FastAPI do device-gw.

Subir localmente::

    uvicorn gateway.main:app --reload

Conferir que a aplicacao carrega e quantas rotas tem (usado no aceite da F0)::

    python -c "from gateway.main import app; print(len(app.routes))"

Dentro do container, o comando e `uvicorn app.main:app`, como
`infra/docker-compose.dev.yml` declara: o `Dockerfile` instala na imagem um
alias `app.main` que reexporta o objeto desta aplicacao. Ver a explicacao do
nome em `gateway/__init__.py`.

**Estado desta versao.** Fase 0 entrega contrato e andaime. `GET /health` e
`GET /ready` sao funcionais — sem eles o container nunca ficaria `healthy` e o
`docker compose up` da stack inteira travaria no `depends_on`. Todo o resto do
protocolo Control iD responde `501` com `PONTO-INT-005` e docstring descrevendo
o formato real da chamada, para que o simulador e os testes da F6 possam ser
escritos contra alvo definido.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI

from gateway.config import Configuracao, obter_configuracao
from gateway.erros import registrar_tratadores
from gateway.log import configurar_log, obter_logger
from gateway.rotas import registrar_rotas

logger = obter_logger("main")

DESCRICAO = """
Gateway dos terminais coletores **Control iD** (iDFace / iDBlock).

Servico interno: **nao** faz parte da API publica do produto e nao aparece em
`packages/contracts/openapi.yaml`. Ele fala o protocolo do fabricante de um lado
e chama a API interna do outro.

### Quatro fatos que mudam o desenho de quem mexe aqui

1. **O terminal nao e o REP-P.** O REP-P e o nosso software. O equipamento
   identifica a pessoa e produz um `access_log`; este gateway converte e entrega
   a API, e e **o servidor** quem atribui o NSR e grava.
2. **Toda operacao sobre o terminal e assincrona.** Ele vive em LAN sem IP
   publico: quem inicia conexao e ele. Mandar trabalho significa enfileirar
   comando para o proximo ciclo de Push.
3. **A ingestao e idempotente por `numero_serie + access_log_id`.** Push,
   Monitor e catch-up podem entregar o mesmo registro; marcacao duplicada num
   sistema de ponto e problema trabalhista, nao inconveniencia.
4. **O relogio do equipamento e evidencia, nunca fonte de verdade.** O horario
   oficial da marcacao e o do servidor.

### Estado da implementacao

Fase 0 entrega **contrato e andaime**. `/health` e `/ready` funcionam; toda
operacao de protocolo responde `501` com `PONTO-INT-005` ate a **F6 —
Integracao Control iD** entrar.
"""


@contextlib.asynccontextmanager
async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
    """Inicializacao e encerramento do processo.

    Nao abre conexao com Redis, banco ou terminal na subida, de proposito — e a
    mesma decisao do `apps/api` e do `apps/worker`. O gateway precisa subir e
    responder `/health` mesmo com tudo o mais fora, para que `/ready` possa
    dizer *por que* nao esta pronto. Aqui o argumento e ainda mais forte: se
    este servico entra em *crash loop*, os terminais ficam sem para onde mandar
    marcacao, e a marcacao so nao se perde porque o equipamento guarda
    localmente — margem que ninguem quer gastar por causa de um Redis fora.
    """
    config = obter_configuracao()
    logger.info(
        "device-gw iniciado",
        extra={
            "ambiente": config.ambiente,
            "versao": config.versao,
            "commit": config.commit,
            "rotas": len(app.routes),
            "simulador": config.controlid_simulador,
            "apiBaseUrl": config.api_base_url,
        },
    )
    if config.producao and not config.push_token_configurado:
        # Aviso, e nao recusa, porque na Fase 0 nenhuma rota de protocolo faz
        # nada: elas respondem 501 antes de olhar credencial. A F6 promove isto
        # a recusa de subida — token de Push vazio em producao significa que
        # qualquer um na internet consegue postar marcacao.
        logger.warning(
            "CONTROLID_PUSH_TOKEN vazio em ambiente de producao",
            extra={"ambiente": config.ambiente, "acao": "definir antes da F6"},
        )
    try:
        yield
    finally:
        logger.info("device-gw encerrado")


def criar_aplicacao(config: Configuracao | None = None) -> FastAPI:
    """Monta a aplicacao. Funcao separada para o teste poder criar instancias."""
    config = config or obter_configuracao()
    configurar_log(config)

    app = FastAPI(
        title="Ponto Eletronico - Gateway Control iD",
        version=config.versao,
        summary="Gateway dos terminais coletores Control iD (Push, Monitor e catch-up).",
        description=DESCRICAO,
        lifespan=ciclo_de_vida,
        # A documentacao interativa fica no ar tambem aqui: quem depura um
        # terminal precisa ver o formato esperado sem abrir o codigo. Nao ha
        # dado sensivel no esquema — sao envelopes de protocolo.
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        contact={
            "name": "SEEG Servicos de Tecnologia da Informacao",
            "url": "https://docs.ponto.seeg.com.br",
            "email": "suporte@seeg.com.br",
        },
        license_info={"name": "Proprietaria - SEEG"},
    )

    registrar_tratadores(app)
    registrar_rotas(app)
    return app


app = criar_aplicacao()
