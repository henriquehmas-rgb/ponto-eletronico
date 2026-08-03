"""T19 (A8) -- `worker.tarefas.integracoes.importar_arquivo_generico`, o
ponto de entrada REAL de produção (o mesmo que `arq` chama a partir da fila
`FILA_INTEGRACOES`). Chama a tarefa DIRETAMENTE (função `async` simples,
sem subir um worker `arq` de verdade) contra o banco e o MinIO reais -- o
mesmo padrão que `apps/api/tests/f13/nucleo/test_autenticacao_cliente.py`
usa para `exigir_escopo`.

Sobe o conteúdo do AFD sintético no MinIO real via `app.comum.armazenamento
.salvar_objeto` (biblioteca `apps/api` instalada no venv do worker, ADR-009)
-- nunca um segundo cliente MinIO, mesma instância que a tarefa usa em
produção para ler de volta.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.f13.importadores.afd_terceiro.conftest import ContextoWorkerF13
from worker.tarefas.integracoes import importar_arquivo_generico, reiniciar_engine_para_testes

# =============================================================================
# Montador de AFD sintetico minimo -- copia deliberada, reduzida, do mesmo
# padrao ja usado por `apps/api/tests/f13/importadores/afd_terceiro/
# conftest.py::montar_arquivo_afd` (nao importavel daqui: `apps/worker`
# instala so `app/` de `apps/api` como biblioteca, ADR-009 -- `tests/` fica
# de fora da imagem/pacote de proposito, ver `apps/worker/Dockerfile`).
# =============================================================================


def _crc16_kermit_hex(dados: bytes) -> str:
    from app.integracoes.importadores.afd_terceiro.leiaute import crc16_kermit_hex

    return crc16_kermit_hex(dados)


def _montar_tipo1(cnpj: str) -> str:
    campo1 = "000000000"
    campo2 = "1"
    campo3 = "1"
    campo4 = cnpj.rjust(14, "0")
    campo5 = "0".rjust(14, "0")
    campo6 = "Empresa Teste Ltda".ljust(150)
    campo7 = "1".rjust(17, "0")
    campo8 = "2026-01-01".ljust(10)
    campo9 = "2026-01-31".ljust(10)
    campo10 = "2026-02-01T08:00:00-0300".ljust(24)
    campo11 = "003"
    campo12 = "1"
    campo13 = cnpj.rjust(14, "0")
    campo14 = "".ljust(30)
    corpo = (
        campo1
        + campo2
        + campo3
        + campo4
        + campo5
        + campo6
        + campo7
        + campo8
        + campo9
        + campo10
        + campo11
        + campo12
        + campo13
        + campo14
    )
    return corpo + _crc16_kermit_hex(corpo.encode("iso-8859-1"))


def _montar_tipo7(*, nsr: int, datahora: str, cpf: str) -> str:
    campo1 = str(nsr).rjust(9, "0")
    campo2 = "7"
    campo3 = datahora.ljust(24)
    campo4 = cpf.rjust(12, "0")
    campo5 = datahora.ljust(24)
    campo6 = "04"
    campo7 = "0"
    campo8 = hashlib.sha256(f"{nsr}|{cpf}|{datahora}".encode()).hexdigest()
    return campo1 + campo2 + campo3 + campo4 + campo5 + campo6 + campo7 + campo8


def _montar_trailer(qtd_tipo7: int) -> str:
    return (
        "999999999"
        + "0".rjust(9, "0")
        + "0".rjust(9, "0")
        + "0".rjust(9, "0")
        + "0".rjust(9, "0")
        + "0".rjust(9, "0")
        + str(qtd_tipo7).rjust(9, "0")
        + "9"
    )


def _montar_afd(*, cnpj: str, registros: list[tuple[int, str, str]]) -> bytes:
    linhas = [_montar_tipo1(cnpj)]
    linhas.extend(_montar_tipo7(nsr=nsr, datahora=dh, cpf=cpf) for nsr, dh, cpf in registros)
    linhas.append(_montar_trailer(len(registros)))
    return ("\r\n".join(linhas) + "\r\n").encode("iso-8859-1")


@pytest_asyncio.fixture(autouse=True)
async def _engine_worker_isolada() -> AsyncIterator[None]:
    await reiniciar_engine_para_testes()
    yield
    await reiniciar_engine_para_testes()


async def test_importar_arquivo_generico_afd_terceiro_de_ponta_a_ponta(
    sessao_worker_f13: AsyncSession, contexto_worker_f13: ContextoWorkerF13
) -> None:
    import json

    from app.comum.armazenamento import salvar_objeto  # biblioteca apps/api, ADR-009

    conteudo = _montar_afd(
        cnpj="12345678000199",
        registros=[
            (1, "2026-01-05T08:00:00-0300", "52998224725"),
            (2, "2026-01-05T17:00:00-0300", "12345678909"),
        ],
    )
    chave = f"importacoes/teste-worker-f13-a8/{uuid.uuid4().hex}.txt"
    await salvar_objeto(chave, conteudo, content_type="text/plain; charset=iso-8859-1")

    importacao_id = uuid.uuid4()
    parametros_json = json.dumps({"repPId": str(contexto_worker_f13.rep_p_id)})
    await sessao_worker_f13.execute(
        text(
            "INSERT INTO importacoes "
            "(id, tenant_id, empresa_id, tipo, origem, nome_arquivo, conteudo_ref, parametros, "
            " status) "
            "VALUES (:id, :tenant_id, :empresa_id, 'afd_terceiro', 'afd', 'teste.txt', :chave, "
            "        CAST(:parametros AS jsonb), 'recebido')"
        ),
        {
            "id": importacao_id,
            "tenant_id": contexto_worker_f13.tenant_id,
            "empresa_id": contexto_worker_f13.empresa_id,
            "chave": chave,
            "parametros": parametros_json,
        },
    )
    await sessao_worker_f13.commit()

    resultado = await importar_arquivo_generico(
        {},
        tenant_id=str(contexto_worker_f13.tenant_id),
        importacao_id=str(importacao_id),
    )

    assert resultado["implementado"] is True
    assert resultado["status"] == "concluido"
    assert resultado["linhasSucesso"] == 2
    assert resultado["linhasErro"] == 0

    await _aplicar_tenant_de_novo(sessao_worker_f13, contexto_worker_f13.tenant_id)
    linha = (
        (
            await sessao_worker_f13.execute(
                text("SELECT status, linhas_sucesso, linhas_erro FROM importacoes WHERE id = :id"),
                {"id": importacao_id},
            )
        )
        .mappings()
        .one()
    )
    assert linha["status"] == "concluido"
    assert linha["linhas_sucesso"] == 2

    total_marcacoes = (
        await sessao_worker_f13.execute(
            text(
                "SELECT count(*) FROM marcacoes WHERE origem_importacao_id = :id "
                "AND canal = 'importacao'"
            ),
            {"id": importacao_id},
        )
    ).scalar_one()
    assert total_marcacoes == 2


async def _aplicar_tenant_de_novo(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant_id)}
    )
