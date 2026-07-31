"""Fixture local de `tests/f12/cofre/**` (F12/A3).

Reaproveita o bootstrap de banco/tenant de `tests/f12/assinatura/conftest.py`
(mesmo agente, mesmo banco exclusivo `ponto_f12_a3`) por IMPORTAÇÃO --
padrão suportado pelo pytest (fixtures importadas para um `conftest.py`
ficam disponíveis para os testes daquele diretório). Evita duplicar ~150
linhas de bootstrap de engine/role/tenant já escritas e testadas em
`tests/f12/assinatura/conftest.py`.

Este arquivo acrescenta só o que é específico do cofre: `AfdArquivo`/
`AejArquivo` de exemplo, gravados de verdade no MinIO configurado
(`bucket_minio_f12` do conftest importado), para exercitar `listar_afd`/
`obter_afd`/`baixar_afd`/`listar_aej`/`obter_aej` contra "arquivos que
existem de verdade" (prompt da fase para A3) sem depender do gerador real
de AFD/AEJ (A1/A2, fora do ownership de A3 -- PCF F12 cabeçalho: "Você não
depende de A1/A2 para construir o módulo de assinatura CAdES em si").
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass

import pytest_asyncio
from ponto_contracts import AejArquivo, AfdArquivo
from sqlalchemy.ext.asyncio import AsyncSession

from app.comum.armazenamento import salvar_objeto
from tests.f12.assinatura.conftest import (  # noqa: F401 -- reexportado para o pytest descobrir
    ContextoF12A3,
    aplicar_tenant_teste_f12,
    bucket_minio_f12,
    certificado_teste,
    certificado_teste_expirado,
    contexto_f12_a3,
    engine_f12_a3,
    sessao_f12_a3,
    url_login_sessao_f12_a3,
)


@dataclass(frozen=True, slots=True)
class ContextoCofre:
    contexto: ContextoF12A3
    afd: AfdArquivo
    aej: AejArquivo
    conteudo_afd: bytes
    conteudo_aej: bytes


@pytest_asyncio.fixture
async def contexto_cofre(
    sessao_f12_a3: AsyncSession,  # noqa: F811 -- nome do parametro = nome do fixture importado
    contexto_f12_a3: ContextoF12A3,  # noqa: F811
    bucket_minio_f12: None,  # noqa: F811
) -> ContextoCofre:
    conteudo_afd = (
        b"000000000" + b"1" + b"1" + f"{'6' * 14}".encode() + b"AFD DE TESTE\r\n"
        b"000000001" + b"7" + b"conteudo de teste do registro tipo 7\r\n"
        b"999999999"
        + b"000000000"
        + b"000000000"
        + b"000000000"
        + b"000000000"
        + b"000000000"
        + b"000000001"
        + b"9\r\n"
    )
    chave_afd = f"fiscal/teste/cofre/afd/{uuid.uuid4()}.txt"
    await salvar_objeto(chave_afd, conteudo_afd, content_type="text/plain")

    afd = AfdArquivo(
        tenant_id=contexto_f12_a3.tenant_id,
        empresa_id=contexto_f12_a3.empresa_id,
        rep_p_id=contexto_f12_a3.rep_p_id,
        periodo_inicio=dt.date(2026, 7, 1),
        periodo_fim=dt.date(2026, 7, 31),
        nsr_inicial=1,
        nsr_final=1,
        total_registros=1,
        nome_arquivo="AFD_TESTE_COFRE.txt",
        conteudo_ref=chave_afd,
        tamanho_bytes=len(conteudo_afd),
        hash_sha256=hashlib.sha256(conteudo_afd).hexdigest(),
        status="gerado",
        gerado_em=dt.datetime.now(dt.UTC),
    )
    sessao_f12_a3.add(afd)

    conteudo_aej = (
        b"01|1|1|" + b"1" * 14 + b"||Empresa Teste|2026-07-01|2026-07-31|"
        b"2026-07-01T00:00:00-0300|001|\r\n"
    )
    chave_aej = f"fiscal/teste/cofre/aej/{uuid.uuid4()}.txt"
    await salvar_objeto(chave_aej, conteudo_aej, content_type="text/plain")

    aej = AejArquivo(
        tenant_id=contexto_f12_a3.tenant_id,
        empresa_id=contexto_f12_a3.empresa_id,
        periodo_inicio=dt.date(2026, 7, 1),
        periodo_fim=dt.date(2026, 7, 31),
        nome_arquivo="AEJ_TESTE_COFRE.txt",
        conteudo_ref=chave_aej,
        tamanho_bytes=len(conteudo_aej),
        hash_sha256=hashlib.sha256(conteudo_aej).hexdigest(),
        ptrp_identificacao="SEEG Ponto (fixture de teste do cofre)",
        status="gerado",
        gerado_em=dt.datetime.now(dt.UTC),
    )
    sessao_f12_a3.add(aej)

    await sessao_f12_a3.flush()

    return ContextoCofre(
        contexto=contexto_f12_a3,
        afd=afd,
        aej=aej,
        conteudo_afd=conteudo_afd,
        conteudo_aej=conteudo_aej,
    )
