"""T2 -- alocacao de NSR, CRC-16 e hash encadeado.

Cobre os dois "Pronto quando" da T2: (1) alocacoes concorrentes do mesmo
REP-P nunca colidem nem pulam valor (aqui com 50 alocacoes -- a prova
completa com 10.000 e a T9, em `test_concorrencia_nsr.py`); (2) as funcoes
puras `crc16`/`calcular_hash`/`canonicalizar_registro` sao deterministicas e
sensiveis a qualquer mudanca de entrada (o que torna a cadeia detectavel a
adulteracao).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import uuid

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.marcacao.dominio.nsr import alocar_nsr, calcular_hash, canonicalizar_registro, crc16
from tests.f5.conftest import ContextoF5, aplicar_tenant_teste


def test_crc16_e_deterministico_e_sensivel_a_mudanca() -> None:
    dado = b"7 000000001 12345678909 20260725 080213 api"
    assert crc16(dado) == crc16(dado)
    assert crc16(dado) != crc16(dado + b"x")
    # Faixa valida de um CRC-16 (16 bits).
    assert 0 <= crc16(dado) <= 0xFFFF


def test_canonicalizar_registro_e_hash_sao_deterministicos_e_sensiveis() -> None:
    tenant_id = uuid.uuid4()
    rep_p_id = uuid.uuid4()
    instante = dt.datetime(2026, 7, 25, 8, 2, 13, tzinfo=dt.UTC)

    canonico_1 = canonicalizar_registro(
        tenant_id=tenant_id,
        rep_p_id=rep_p_id,
        nsr=1842,
        cpf="12345678909",
        tipo_registro="7",
        canal="api",
        datahora_marcacao=instante,
    )
    canonico_2 = canonicalizar_registro(
        tenant_id=tenant_id,
        rep_p_id=rep_p_id,
        nsr=1842,
        cpf="12345678909",
        tipo_registro="7",
        canal="api",
        datahora_marcacao=instante,
    )
    assert canonico_1 == canonico_2

    hash_1 = calcular_hash(canonico_1, None)
    hash_2 = calcular_hash(canonico_1, None)
    assert hash_1 == hash_2
    assert len(hash_1) == 64
    assert all(caractere in "0123456789abcdef" for caractere in hash_1)

    # Mudar o NSR muda o canonico e, portanto, o hash.
    canonico_outro_nsr = canonicalizar_registro(
        tenant_id=tenant_id,
        rep_p_id=rep_p_id,
        nsr=1843,
        cpf="12345678909",
        tipo_registro="7",
        canal="api",
        datahora_marcacao=instante,
    )
    assert canonico_outro_nsr != canonico_1
    assert calcular_hash(canonico_outro_nsr, None) != hash_1

    # Mudar so o hash_anterior muda a saida (cadeia sensivel ao elo anterior).
    assert calcular_hash(canonico_1, "a" * 64) != hash_1


async def test_alocar_nsr_concorrente_sem_lacuna_sem_repeticao(
    engine_f5: AsyncEngine, contexto_f5: ContextoF5
) -> None:
    """50 alocacoes concorrentes (conexoes distintas, mesma linha de
    `nsr_sequencias`) para o MESMO REP-P produzem exatamente `{1..50}`, sem
    lacuna e sem repeticao. Concorrencia efetiva limitada por semaforo do
    lado do teste (a corretude vem do bloqueio de linha no banco, nao do
    grau de paralelismo do teste -- ver docstring de `engine_f5`)."""
    tenant_id = contexto_f5.tenant_id
    rep_p_id = contexto_f5.rep_p_id
    quantidade = 50
    semaforo = asyncio.Semaphore(8)
    fabrica = async_sessionmaker(engine_f5, expire_on_commit=False, autoflush=False)

    async def _aloca_um() -> int:
        async with semaforo, fabrica() as sessao:
            await aplicar_tenant_teste(sessao, tenant_id)
            alocado = await alocar_nsr(sessao, tenant_id=tenant_id, rep_p_id=rep_p_id)
            await sessao.commit()
            return alocado.nsr

    resultados = await asyncio.gather(*[_aloca_um() for _ in range(quantidade)])

    assert len(resultados) == quantidade
    assert len(set(resultados)) == quantidade, "NSR repetido sob concorrencia"
    assert sorted(resultados) == list(range(1, quantidade + 1)), "lacuna na sequencia de NSR"
