"""Montagem da aplicacao FastAPI do facial-svc.

Subir localmente::

    uvicorn facial.main:app --reload

Conferir que a aplicacao carrega e quantas rotas tem (usado no aceite da F0)::

    python -c "from facial.main import app; print(len(app.routes))"

Dentro do container, o comando e `uvicorn app.main:app`, como
`infra/docker-compose.dev.yml` declara: o `Dockerfile` instala na imagem um
alias `app.main` que reexporta o objeto desta aplicacao. Ver a explicacao do
nome em `facial/__init__.py`.

**Estado desta versao.** Fase 0 entrega contrato e andaime. `GET /health` e
`GET /ready` sao funcionais — sem `/health` o container nunca ficaria `healthy`,
e como a `api` declara `depends_on: facial-svc: service_healthy`, a stack
inteira ficaria presa. As tres operacoes biometricas respondem `501` com
`PONTO-INT-005` e docstring descrevendo o contrato de entrada e de saida, para
que o chamador da F2 e da F7 possa ser escrito e testado com dublê.

O motor **nao e carregado** neste estado: nao ha `import onnxruntime`, nem
dependencia de `insightface` no `pyproject.toml`. Declarar bibliotecas pesadas
antes de existir codigo que as use so faria a imagem crescer e o build do CI
demorar sem entregar nada. Elas entram na F2, junto com o codigo que as chama.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI

from facial.config import Configuracao, obter_configuracao
from facial.erros import registrar_tratadores
from facial.log import configurar_log, obter_logger
from facial.rotas import registrar_rotas

logger = obter_logger("main")

DESCRICAO = """
Servico facial self-hosted do **Ponto Eletronico**.

Wrapper HTTP do motor `analise-facial-edge` (InsightFace / ArcFace ONNX),
reaproveitado conforme a decisao **D4** de `PROJETO.md`.

**Servico interno.** Nao tem rota no Traefik, vive so na rede `ponto-interna` e
nao aparece em `packages/contracts/openapi.yaml`. Biometria nao sai da
infraestrutura da SEEG (LGPD art. 5, II, e ADR-006).

### Cinco regras que este servico existe para cumprir

1. **Imagem crua nunca e persistida.** Entra, vira vetor, e descartada.
2. **O vetor e versionado pelo modelo.** Trocar de motor nao invalida o
   historico: convivem versoes, e o reenrollment e gradual e rastreavel.
3. **O vetor nunca vaza em log nem em mensagem de erro.**
4. **O limiar de similaridade nunca aparece em resposta.** Os codigos
   `PONTO-SCORE-*` tem `expoe_regra: false` — revelar o placar da tentativa
   entrega o mapa da fraude.
5. **Este servico nao tem credencial de banco.** Quem persiste (cifrado) e a
   API. Servico que nao tem credencial nao vaza credencial.

### Estado da implementacao

Fase 0 entrega **contrato e andaime**. `/health` e `/ready` funcionam;
`/enroll`, `/verificar` e `/liveness` respondem `501` com `PONTO-INT-005` ate a
**F2 — Cadastro e biometria** e a **F7 — App mobile** entrarem.
"""


@contextlib.asynccontextmanager
async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
    """Inicializacao e encerramento do processo.

    Nao carrega modelo na subida, de proposito — e a mesma decisao dos outros
    servicos, com um agravante proprio: a `api` declara
    `depends_on: facial-svc: condition: service_healthy`. Se este processo
    entrasse em *crash loop* por falta de peso `.onnx` no volume, a stack
    inteira ficaria presa sem subir, e ninguem veria a causa. Do jeito que esta,
    ele sobe, responde `/health`, reprova em `/ready` e **diz** que faltam os
    pesos.

    Na F2, quando o motor for carregado de fato, o carregamento continua fora do
    caminho de `/health`: preguicoso na primeira captura, ou em segundo plano
    com `/ready` refletindo o progresso.
    """
    config = obter_configuracao()
    logger.info(
        "facial-svc iniciado",
        extra={
            "ambiente": config.ambiente,
            "versao": config.versao,
            "commit": config.commit,
            "rotas": len(app.routes),
            "modeloVersao": config.facial_model_versao,
            "modelosPresentes": config.modelos_presentes,
            # O limiar NAO entra aqui. Ver a regra 4 na descricao.
        },
    )
    if not config.modelos_presentes:
        logger.warning(
            "nenhum peso .onnx encontrado no diretorio de modelos",
            extra={
                "facialModelDir": config.facial_model_dir,
                "acao": "conferir o volume facial-models",
            },
        )
    if config.producao and not config.facial_mtls_ca_path:
        # PROJETO.md secao 7.3: mTLS entre os chamadores internos e o servico
        # facial. Aviso na Fase 0 (nenhuma rota faz trabalho ainda), recusa na F7.
        logger.warning(
            "FACIAL_MTLS_CA_PATH vazio em ambiente de producao",
            extra={"ambiente": config.ambiente, "acao": "definir antes da F7"},
        )
    try:
        yield
    finally:
        logger.info("facial-svc encerrado")


def criar_aplicacao(config: Configuracao | None = None) -> FastAPI:
    """Monta a aplicacao. Funcao separada para o teste poder criar instancias."""
    config = config or obter_configuracao()
    configurar_log(config)

    app = FastAPI(
        title="Ponto Eletronico - Servico Facial",
        version=config.versao,
        summary="Wrapper do motor facial self-hosted (InsightFace / ArcFace ONNX).",
        description=DESCRICAO,
        lifespan=ciclo_de_vida,
        # Documentacao interativa somente fora de producao. Aqui a regra e mais
        # dura que na API: o portal publico da API e um produto, este seria um
        # mapa das rotas biometricas num servico que nao deveria receber visita.
        docs_url=None if config.producao else "/docs",
        redoc_url=None if config.producao else "/redoc",
        openapi_url=None if config.producao else "/openapi.json",
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
