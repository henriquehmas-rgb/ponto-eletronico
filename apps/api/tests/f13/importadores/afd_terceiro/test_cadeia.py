"""T19 (A8) -- `app.integracoes.importadores.afd_terceiro.cadeia`: fórmula
própria de `crc16`/`hash_registro`/`hash_anterior` para marcação importada,
e prova de que é DISTINTA da fórmula de `app.marcacao.dominio.nsr` (F5) --
critério de aceite 8 do PCF F13 ("não podem ser confundidos com os valores
que F5 calcularia para uma marcação nossa")."""

from __future__ import annotations

import datetime as dt
from uuid import uuid4

from app.integracoes.importadores.afd_terceiro.cadeia import (
    MARCADOR_DOMINIO,
    SEPARADOR,
    calcular_hash_importado,
    canonicalizar_registro_importado,
    crc16_do_registro_importado,
)
from app.marcacao.dominio.nsr import (
    _SEPARADOR as SEPARADOR_F5,
)
from app.marcacao.dominio.nsr import (
    calcular_hash as calcular_hash_f5,
)
from app.marcacao.dominio.nsr import (
    canonicalizar_registro as canonicalizar_f5,
)


def test_separador_diferente_do_de_f5() -> None:
    assert SEPARADOR != SEPARADOR_F5


def test_marcador_de_dominio_nunca_aparece_na_formula_de_f5() -> None:
    """O marcador `AFD_TERCEIRO_IMPORTADO` garante que as duas famílias de
    hash não podem colidir por acidente de formato -- a canonicalização de
    F5 nunca produz essa substring."""
    canonico_f5 = canonicalizar_f5(
        tenant_id=uuid4(),
        rep_p_id=uuid4(),
        nsr=1,
        cpf="12345678901",
        tipo_registro="7",
        canal="terminal",
        datahora_marcacao=dt.datetime.now(tz=dt.UTC),
    )
    assert MARCADOR_DOMINIO not in canonico_f5


def test_hash_importado_e_diferente_do_hash_de_f5_para_entrada_equivalente() -> None:
    """Mesmo dando os "mesmos" dados de negócio às duas fórmulas, os hashes
    resultantes são diferentes -- prova por construção de que uma
    implementação não pode ser confundida com a outra."""
    tenant_id = uuid4()
    rep_p_id = uuid4()
    importacao_id = uuid4()
    nsr = 42
    cpf = "12345678901"
    momento = dt.datetime.now(tz=dt.UTC)
    linha_bruta = "x" * 137

    canonico_f5 = canonicalizar_f5(
        tenant_id=tenant_id,
        rep_p_id=rep_p_id,
        nsr=nsr,
        cpf=cpf,
        tipo_registro="7",
        canal="importacao",
        datahora_marcacao=momento,
    )
    hash_f5 = calcular_hash_f5(canonico_f5, None)

    canonico_importado = canonicalizar_registro_importado(
        importacao_id=importacao_id,
        nsr_origem=nsr,
        cpf=cpf,
        tipo_registro="7",
        datahora_marcacao=momento,
        linha_bruta=linha_bruta,
    )
    hash_importado = calcular_hash_importado(canonico_importado, None)

    assert hash_f5 != hash_importado
    assert canonico_f5 != canonico_importado


def test_hash_importado_encadeia_com_hash_anterior() -> None:
    importacao_id = uuid4()
    momento = dt.datetime.now(tz=dt.UTC)

    canonico1 = canonicalizar_registro_importado(
        importacao_id=importacao_id,
        nsr_origem=1,
        cpf="11111111111",
        tipo_registro="7",
        datahora_marcacao=momento,
        linha_bruta="a" * 137,
    )
    hash1 = calcular_hash_importado(canonico1, None)

    canonico2 = canonicalizar_registro_importado(
        importacao_id=importacao_id,
        nsr_origem=2,
        cpf="22222222222",
        tipo_registro="7",
        datahora_marcacao=momento,
        linha_bruta="b" * 137,
    )
    hash2_com_elo = calcular_hash_importado(canonico2, hash1)
    hash2_sem_elo = calcular_hash_importado(canonico2, None)

    assert hash2_com_elo != hash2_sem_elo
    assert len(hash1) == 64
    assert len(hash2_com_elo) == 64


def test_crc16_do_registro_importado_e_deterministico() -> None:
    linha = "z" * 137
    assert crc16_do_registro_importado(linha) == crc16_do_registro_importado(linha)
    assert 0 <= crc16_do_registro_importado(linha) <= 0xFFFF
