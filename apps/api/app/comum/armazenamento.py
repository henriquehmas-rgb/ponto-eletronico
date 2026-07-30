"""Cliente de armazenamento de objetos (MinIO/S3), F10 §2.5.

**Primeira integração real de `apps/api` com o MinIO.** Até esta fase nenhum
código da aplicação fala com o `MINIO_*` já provisionado em
`infra/.env.example` (bloco 6) e já lido por `app.core.config.Configuracao`
(`minio_endpoint`/`minio_access_key`/`minio_secret_key`/`minio_bucket`/
`minio_secure`) -- os campos existiam desde o andaime da Fase 0, mas sem
nenhum consumidor até agora.

**Biblioteca escolhida: `minio` (SDK oficial, compatível S3), não `boto3`**
(documentado também em `apps/api/pyproject.toml`, bloco F10): dependência
menor para o uso estreito desta fase (`put_object`/`get_object`/
`presigned_get_object`), sem carregar o SDK inteiro da AWS.

**Ownership:** `apps/api/app/comum/armazenamento.py` é de A2 (F10, PCF §5,
"cliente MinIO novo, reaproveitável por A4") -- primeiro consumidor real é
`app.workflow.fechamento.espelho` (T7, grava o PDF do espelho), e o módulo é
deliberadamente genérico (nenhuma referência a `espelho`/`fechamento` aqui)
para que A4 reaproveite em `salvar_anexo` (T14) sem duplicar o cliente.

**Chave, nunca URL completa.** `salvar_objeto` devolve a *chave* do objeto
(`conteudo_ref` de `espelhos`, mesmo padrão documentado no comentário da
coluna do schema: "Chave do PDF no MinIO"), nunca a URL assinada -- a URL é
efêmera (expira) e é resolvida sob demanda por `obter_url_assinada`, não
persistida.

**Síncrono por baixo, assíncrono por fora.** O SDK `minio` é bloqueante (I/O
de rede síncrono); cada operação roda em `asyncio.to_thread` para não travar
o event loop da API/worker -- mesmo padrão que qualquer chamada bloqueante
precisa neste projeto assíncrono.

**Erros de conectividade viram `PONTO-INT-003`** ("Dependência indisponível
... armazenamento de objetos", `errors.yaml`) -- o único código do catálogo
que descreve exatamente esta falha, e está entre os transversais que o PCF
desta fase autoriza usar (INT). Nenhum código novo é inventado.
"""

from __future__ import annotations

import asyncio
import io
from datetime import timedelta
from typing import Final

from minio import Minio
from minio.error import S3Error
from urllib3.exceptions import MaxRetryError

from app.core.config import Configuracao, obter_configuracao
from app.core.erros import ErroDeAplicacao
from app.core.log import obter_logger

logger = obter_logger("comum.armazenamento")

CODIGO_DEPENDENCIA_INDISPONIVEL: Final[str] = "PONTO-INT-003"

_cliente: Minio | None = None
_cliente_endpoint: str | None = None


def obter_cliente(config: Configuracao | None = None) -> Minio:
    """Cliente MinIO do processo, criado uma única vez (ou recriado se o
    endpoint configurado mudou -- relevante em teste, que troca variável de
    ambiente entre casos)."""
    global _cliente, _cliente_endpoint
    config = config or obter_configuracao()
    if _cliente is None or _cliente_endpoint != config.minio_endpoint:
        _cliente = Minio(
            config.minio_endpoint,
            access_key=config.minio_access_key.get_secret_value(),
            secret_key=config.minio_secret_key.get_secret_value(),
            secure=config.minio_secure,
        )
        _cliente_endpoint = config.minio_endpoint
    return _cliente


def resetar_cliente() -> None:
    """Descarta o cliente memorizado. Uso exclusivo de teste, entre casos que
    trocam `MINIO_*` em `os.environ`."""
    global _cliente, _cliente_endpoint
    _cliente = None
    _cliente_endpoint = None


def _traduzir_falha(exc: Exception, *, operacao: str, chave: str) -> ErroDeAplicacao:
    logger.error(
        "falha ao falar com o armazenamento de objetos",
        extra={"operacao": operacao, "chave": chave, "tipo": type(exc).__name__},
    )
    return ErroDeAplicacao(
        CODIGO_DEPENDENCIA_INDISPONIVEL,
        detalhe="Armazenamento de objetos indisponivel no momento.",
        contexto_log={"operacao": operacao, "chave": chave},
    )


async def salvar_objeto(
    chave: str,
    conteudo: bytes,
    *,
    content_type: str = "application/octet-stream",
    bucket: str | None = None,
    config: Configuracao | None = None,
) -> str:
    """Grava `conteudo` sob `chave` no bucket configurado. Devolve a própria
    `chave` (nunca a URL completa -- ver docstring do módulo)."""
    config = config or obter_configuracao()
    bucket_alvo = bucket or config.minio_bucket
    cliente = obter_cliente(config)

    def _gravar() -> None:
        cliente.put_object(
            bucket_alvo,
            chave,
            io.BytesIO(conteudo),
            length=len(conteudo),
            content_type=content_type,
        )

    try:
        await asyncio.to_thread(_gravar)
    except (S3Error, MaxRetryError, OSError) as exc:
        raise _traduzir_falha(exc, operacao="salvar_objeto", chave=chave) from exc
    logger.info(
        "objeto gravado no armazenamento",
        extra={"bucket": bucket_alvo, "chave": chave, "bytes": len(conteudo)},
    )
    return chave


async def obter_objeto(
    chave: str, *, bucket: str | None = None, config: Configuracao | None = None
) -> bytes:
    """Lê o conteúdo bruto de `chave`. Usado para servir o PDF de volta ao
    cliente (`baixarEspelhoPdf`) sem depender de URL assinada."""
    config = config or obter_configuracao()
    bucket_alvo = bucket or config.minio_bucket
    cliente = obter_cliente(config)

    def _ler() -> bytes:
        resposta = cliente.get_object(bucket_alvo, chave)
        try:
            return resposta.read()
        finally:
            resposta.close()
            resposta.release_conn()

    try:
        return await asyncio.to_thread(_ler)
    except (S3Error, MaxRetryError, OSError) as exc:
        raise _traduzir_falha(exc, operacao="obter_objeto", chave=chave) from exc


async def obter_url_assinada(
    chave: str,
    *,
    bucket: str | None = None,
    expira_em: timedelta = timedelta(minutes=15),
    config: Configuracao | None = None,
) -> str:
    """URL temporária e assinada para download direto, sem expor credencial.
    `conteudo_ref` grava só a chave (ver docstring do módulo); esta função
    resolve a URL sob demanda, no momento em que alguém precisa de fato
    baixar o objeto."""
    config = config or obter_configuracao()
    bucket_alvo = bucket or config.minio_bucket
    cliente = obter_cliente(config)

    def _url() -> str:
        return cliente.presigned_get_object(bucket_alvo, chave, expires=expira_em)

    try:
        return await asyncio.to_thread(_url)
    except (S3Error, MaxRetryError, OSError) as exc:
        raise _traduzir_falha(exc, operacao="obter_url_assinada", chave=chave) from exc


async def garantir_bucket(*, bucket: str | None = None, config: Configuracao | None = None) -> None:
    """Cria o bucket se ainda não existir. O bucket `ponto` já é provisionado
    pelo bootstrap de `infra/` em ambiente real (`infra/.env.example`,
    `MINIO_BUCKET=ponto`); esta função existe para que testes de integração
    contra um MinIO limpo (ou um ambiente de desenvolvimento novo) não
    precisem de um passo manual antes de rodar."""
    config = config or obter_configuracao()
    bucket_alvo = bucket or config.minio_bucket
    cliente = obter_cliente(config)

    def _garantir() -> None:
        if not cliente.bucket_exists(bucket_alvo):
            cliente.make_bucket(bucket_alvo)

    try:
        await asyncio.to_thread(_garantir)
    except (S3Error, MaxRetryError, OSError) as exc:
        raise _traduzir_falha(exc, operacao="garantir_bucket", chave=bucket_alvo) from exc
