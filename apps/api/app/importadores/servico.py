"""Lado API do importador de colaboradores: registra e enfileira.

`criar_importacao_colaboradores` e o unico ponto de entrada. Ele:

1. valida o formato aceito por este endpoint (`csv`/`xlsx` -- `origem: afd`,
   `api` e `manual` sao de outros importadores fora do escopo de
   `POST /v1/colaboradores/importar`);
2. recusa uma segunda importacao de colaboradores enquanto a anterior do
   mesmo par tenant+empresa ainda nao terminou (`PONTO-IMP-002`);
3. grava a linha em `importacoes` (status `recebido`);
4. enfileira a tarefa `importar_colaboradores` (fila `ponto:integracoes`) com
   o `importacao_id` -- o processamento linha a linha e do worker (T10, `apps
   /worker/worker/tarefas/importacoes.py`), nunca do request.

**Fronteira de ownership.** O roteador que expõe `POST
/v1/colaboradores/importar` (`app/routers/colaboradores.py`) e do agente A2
(tabela da secao 5 do PCF). Esta funcao e o ponto de integracao que aquele
roteador deve chamar; nao editamos o arquivo do router porque nao e nosso
ownership -- ver `docs/backlog.md`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from arq import create_pool
from arq.connections import RedisSettings
from ponto_contracts import Importacao
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.core.filas import FILA_PADRAO

__all__ = ["criar_importacao_colaboradores"]

#: Formatos que ESTE endpoint aceita. `afd`, `api` e `manual` sao de outros
#: importadores (`tipo` != colaboradores ou fluxo diferente).
_ORIGENS_ACEITAS = frozenset({"csv", "xlsx"})

#: Status que significam "ainda em voo" para o par tenant+empresa+tipo.
_STATUS_EM_ANDAMENTO = ("recebido", "validando", "processando")

#: Nome de fila e de tarefa: contrato com `apps/worker/worker/filas.py` e
#: `apps/worker/worker/tarefas/__init__.py`. Renomear um dos dois lados sem o
#: outro faz o job cair num buraco.
NOME_TAREFA_IMPORTAR_COLABORADORES = "importar_colaboradores"


async def criar_importacao_colaboradores(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    empresa_id: UUID | None,
    nome_arquivo: str | None,
    origem: str,
    conteudo_ref: str | None,
    parametros: dict[str, Any] | None,
    usuario_id: UUID | None,
    redis_url: str,
) -> Importacao:
    if origem not in _ORIGENS_ACEITAS:
        raise ErroDeAplicacao(
            "PONTO-VAL-009",
            detalhe=f"Formato '{origem}' nao suportado por este importador (aceita csv, xlsx).",
        )

    em_andamento = (
        (
            await sessao.execute(
                sa.select(Importacao.id).where(
                    Importacao.tenant_id == tenant_id,
                    Importacao.tipo == "colaboradores",
                    Importacao.empresa_id == empresa_id,
                    Importacao.status.in_(_STATUS_EM_ANDAMENTO),
                )
            )
        )
        .scalars()
        .first()
    )
    if em_andamento is not None:
        raise ErroDeAplicacao(
            "PONTO-IMP-002", detalhe="Ja existe uma importacao de colaboradores em andamento."
        )

    importacao = Importacao(
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        tipo="colaboradores",
        origem=origem,
        nome_arquivo=nome_arquivo,
        conteudo_ref=conteudo_ref,
        parametros=parametros,
        status="recebido",
        criado_por=usuario_id,
    )
    sessao.add(importacao)
    await sessao.flush()

    pool = await create_pool(RedisSettings.from_dsn(redis_url), default_queue_name=FILA_PADRAO)
    try:
        await pool.enqueue_job(
            NOME_TAREFA_IMPORTAR_COLABORADORES,
            tenant_id=str(tenant_id),
            importacao_id=str(importacao.id),
        )
    finally:
        await pool.aclose()

    return importacao
