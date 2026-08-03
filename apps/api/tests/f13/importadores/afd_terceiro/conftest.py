"""Fixtures do subarvore `importadores/afd_terceiro` da fase F13 (A8, T19 --
ownership exclusivo, `apps/api/tests/f13/importadores/afd_terceiro/**`).

Construido SOBRE `apps/api/tests/f13/conftest.py` (compartilhada da fase, A1)
E `apps/api/tests/f13/importadores/conftest.py` (deste mesmo agente, um
nivel acima -- `criar_rep_p`/`criar_colaborador_ativo`): o pytest compoe os
tres automaticamente, nada reimportado aqui. Este arquivo so acrescenta os
montadores de linha de AFD sintetico usados pelos testes adversariais (BOM,
NSR fora de ordem, CRC corrompido, registro tipo 3 de REP-C/REP-A).
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.integracoes.importadores.afd_terceiro import leiaute

# =============================================================================
# Montadores de AFD sintetico (largura fixa, ISO-8859-1) -- funcoes puras,
# reaproveitadas por todos os testes deste subgrupo (parser, servico, rota,
# adversarial de namespace de NSR).
# =============================================================================


def montar_tipo1(
    *,
    cnpj: str = "12345678000199",
    numero_rep: str = "1",
    inicio: str = "2026-01-01",
    fim: str = "2026-01-31",
    gerado: str = "2026-02-01T08:00:00-0300",
) -> str:
    campo1 = leiaute.CONSTANTE_TIPO1
    campo2 = "1"
    campo3 = "1"
    campo4 = cnpj.rjust(14, "0")
    campo5 = "0".rjust(14, "0")
    campo6 = "Empresa Teste Ltda".ljust(150)
    campo7 = numero_rep.rjust(17, "0")
    campo8 = inicio.ljust(10)
    campo9 = fim.ljust(10)
    campo10 = gerado.ljust(24)
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
    assert len(corpo) == 298, len(corpo)
    crc = leiaute.crc16_kermit_hex(corpo.encode("iso-8859-1"))
    linha = corpo + crc
    assert len(linha) == leiaute.TAMANHO_TIPO1, len(linha)
    return linha


def montar_tipo7(
    *,
    nsr: int,
    datahora_marc: str,
    cpf: str,
    datahora_grav: str | None = None,
    coletor: str = "04",
    online: bool = True,
    hash_ant: str = "",
) -> str:
    campo1 = str(nsr).rjust(9, "0")
    campo2 = "7"
    campo3 = datahora_marc.ljust(24)
    campo4 = cpf.rjust(12, "0")
    campo5 = (datahora_grav or datahora_marc).ljust(24)
    campo6 = coletor
    campo7 = "0" if online else "1"
    base = f"{hash_ant}|{nsr}|{cpf}|{datahora_marc}"
    campo8 = hashlib.sha256(base.encode()).hexdigest()
    linha = campo1 + campo2 + campo3 + campo4 + campo5 + campo6 + campo7 + campo8
    assert len(linha) == leiaute.TAMANHO_TIPO7, len(linha)
    return linha


def montar_tipo3(*, nsr: int = 1) -> str:
    """Registro tipo 3 (marcacao REP-C/REP-A) -- usado SO no teste
    adversarial que prova a rejeicao de arquivo fora do layout REP-P."""
    campo1 = str(nsr).rjust(9, "0")
    campo2 = "3"
    campo3 = "2026-01-01T08:00:00-0300".ljust(24)
    campo4 = "123456789012"
    corpo = campo1 + campo2 + campo3 + campo4
    crc = leiaute.crc16_kermit_hex(corpo.encode("iso-8859-1"))
    linha = corpo + crc
    assert len(linha) == leiaute.TAMANHO_TIPO3, len(linha)
    return linha


def montar_trailer(qtd_tipo7: int) -> str:
    campo1 = leiaute.CONSTANTE_TIPO9
    campo2 = "0".rjust(9, "0")
    campo3 = "0".rjust(9, "0")
    campo4 = "0".rjust(9, "0")
    campo5 = "0".rjust(9, "0")
    campo6 = "0".rjust(9, "0")
    campo7 = str(qtd_tipo7).rjust(9, "0")
    campo8 = "9"
    linha = campo1 + campo2 + campo3 + campo4 + campo5 + campo6 + campo7 + campo8
    assert len(linha) == leiaute.TAMANHO_TIPO9, len(linha)
    return linha


def montar_assinatura() -> str:
    return leiaute.LITERAL_ASSINATURA_EM_ARQUIVO_SEPARADO.ljust(leiaute.TAMANHO_LINHA_ASSINATURA)


def montar_arquivo_afd(
    *,
    registros_tipo7: list[dict[str, Any]],
    cnpj_empregador: str = "12345678000199",
    incluir_trailer: bool = True,
    incluir_assinatura: bool = True,
) -> bytes:
    """Monta um AFD sintetico completo (cabecalho + N tipo 7 + trailer +
    assinatura), pronto para `leiaute.crc16_kermit`/`parser.ler_arquivo_afd`
    -- cada item de `registros_tipo7` e um kwargs de `montar_tipo7`."""
    linhas = [montar_tipo1(cnpj=cnpj_empregador)]
    linhas.extend(montar_tipo7(**kwargs) for kwargs in registros_tipo7)
    if incluir_trailer:
        linhas.append(montar_trailer(len(registros_tipo7)))
    if incluir_assinatura:
        linhas.append(montar_assinatura())
    return ("\r\n".join(linhas) + "\r\n").encode("iso-8859-1")
