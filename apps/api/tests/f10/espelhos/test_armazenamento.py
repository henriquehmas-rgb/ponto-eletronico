"""Testes DIRETOS de `app.comum.armazenamento` (F10/A2, PCF §2.5) -- antes
deste arquivo, o módulo só era exercitado indiretamente pelo caminho feliz
de `salvar_objeto`/`obter_objeto` via `test_espelho.py::
test_pdf_gerado_contem_campos_minimos_e_grava_no_minio`. Este arquivo cobre
o que faltava: `resetar_cliente`, os três caminhos de erro (`_traduzir_falha`
via `salvar_objeto`/`obter_objeto`/`garantir_bucket`, todos traduzidos para
`PONTO-INT-003`) e o caminho feliz de `obter_url_assinada`/`garantir_bucket`
(nunca chamados por nenhum teste antes deste).

Os testes de erro MONKEYPATCHAM `obter_cliente` para devolver um cliente
falso que sempre levanta `OSError` -- um dos três tipos que
`_traduzir_falha` já captura (`S3Error, MaxRetryError, OSError`) -- em vez
de depender de derrubar o MinIO real do ambiente de verificação (que
afetaria os demais testes rodando contra o mesmo MinIO)."""

from __future__ import annotations

import uuid

import pytest

from app.comum import armazenamento
from app.core.erros import ErroDeAplicacao

CODIGO_DEPENDENCIA_INDISPONIVEL = "PONTO-INT-003"


class _ClienteMinioFalho:
    """Dublê que imita a interface do `minio.Minio` usada por este módulo,
    sempre falhando com `OSError` -- estável e rápido, sem depender de
    derrubar o MinIO real."""

    def put_object(self, *args: object, **kwargs: object) -> None:
        raise OSError("falha de rede simulada (put_object)")

    def get_object(self, *args: object, **kwargs: object) -> None:
        raise OSError("falha de rede simulada (get_object)")

    def presigned_get_object(self, *args: object, **kwargs: object) -> str:
        raise OSError("falha de rede simulada (presigned_get_object)")

    def bucket_exists(self, *args: object, **kwargs: object) -> bool:
        raise OSError("falha de rede simulada (bucket_exists)")


def test_resetar_cliente_permite_recriar(monkeypatch: pytest.MonkeyPatch) -> None:
    """`resetar_cliente` descarta o cliente memorizado -- a próxima chamada a
    `obter_cliente` precisa criar um novo (sem levantar nada)."""
    armazenamento.obter_cliente()
    assert armazenamento._cliente is not None

    armazenamento.resetar_cliente()
    assert armazenamento._cliente is None
    assert armazenamento._cliente_endpoint is None

    novo = armazenamento.obter_cliente()
    assert novo is not None


@pytest.mark.asyncio
async def test_salvar_objeto_com_falha_de_rede_e_int_003(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(armazenamento, "obter_cliente", lambda config=None: _ClienteMinioFalho())
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await armazenamento.salvar_objeto(f"teste/{uuid.uuid4()}.bin", b"conteudo")
    assert excinfo.value.codigo == CODIGO_DEPENDENCIA_INDISPONIVEL


@pytest.mark.asyncio
async def test_obter_objeto_com_falha_de_rede_e_int_003(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(armazenamento, "obter_cliente", lambda config=None: _ClienteMinioFalho())
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await armazenamento.obter_objeto(f"teste/{uuid.uuid4()}.bin")
    assert excinfo.value.codigo == CODIGO_DEPENDENCIA_INDISPONIVEL


@pytest.mark.asyncio
async def test_obter_url_assinada_com_falha_de_rede_e_int_003(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(armazenamento, "obter_cliente", lambda config=None: _ClienteMinioFalho())
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await armazenamento.obter_url_assinada(f"teste/{uuid.uuid4()}.bin")
    assert excinfo.value.codigo == CODIGO_DEPENDENCIA_INDISPONIVEL


@pytest.mark.asyncio
async def test_garantir_bucket_com_falha_de_rede_e_int_003(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(armazenamento, "obter_cliente", lambda config=None: _ClienteMinioFalho())
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await armazenamento.garantir_bucket(bucket="ponto-teste-falho")
    assert excinfo.value.codigo == CODIGO_DEPENDENCIA_INDISPONIVEL


# ---------------------------------------------------------------------------
# Caminho feliz de `obter_url_assinada`/`garantir_bucket` -- MinIO real do
# ambiente de verificação (mesmas variaveis `MINIO_*` que `test_espelho.py`
# já usa).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_obter_url_assinada_devolve_url_com_a_chave() -> None:
    chave = f"teste-armazenamento/{uuid.uuid4()}.bin"
    await armazenamento.salvar_objeto(chave, b"conteudo de teste do armazenamento")

    url = await armazenamento.obter_url_assinada(chave)
    assert url.startswith("http")
    assert chave in url

    conteudo = await armazenamento.obter_objeto(chave)
    assert conteudo == b"conteudo de teste do armazenamento"


@pytest.mark.asyncio
async def test_garantir_bucket_cria_bucket_novo_e_e_idempotente() -> None:
    bucket_novo = f"ponto-teste-{uuid.uuid4().hex[:16]}"
    cliente = armazenamento.obter_cliente()
    assert cliente.bucket_exists(bucket_novo) is False

    await armazenamento.garantir_bucket(bucket=bucket_novo)
    assert cliente.bucket_exists(bucket_novo) is True

    # Chamar de novo com o bucket ja existente e' o ramo "nao recria" --
    # idempotente, nunca levanta.
    await armazenamento.garantir_bucket(bucket=bucket_novo)
    assert cliente.bucket_exists(bucket_novo) is True


@pytest.mark.asyncio
async def test_garantir_bucket_padrao_ja_existe() -> None:
    """O bucket padrao (`MINIO_BUCKET`, ja provisionado pelo ambiente de
    verificacao) ja existe -- `garantir_bucket()` sem argumento e' um no-op
    que nao levanta."""
    await armazenamento.garantir_bucket()
