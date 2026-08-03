"""T19 (A8) -- `app.integracoes.importadores.afd_terceiro.parser`: leitura
estrutural de um AFD de terceiro, incluindo os quatro casos adversariais que
`PONTO-IMP-001`/`PONTO-IMP-003` cobrem (layout não reconhecido, BOM UTF-8,
sequência de NSR inconsistente, CRC de registro divergente) mais o registro
tipo 3 (REP-C/REP-A, fora do escopo deste importador de REP-P).
"""

from __future__ import annotations

import pytest

from app.integracoes.importadores.afd_terceiro import leiaute
from app.integracoes.importadores.afd_terceiro.parser import (
    ArquivoAfdInvalido,
    ler_arquivo_afd,
)
from tests.f13.importadores.afd_terceiro.conftest import (
    montar_arquivo_afd,
    montar_assinatura,
    montar_tipo1,
    montar_tipo3,
    montar_tipo7,
    montar_trailer,
)


def test_arquivo_bem_formado_le_cabecalho_e_registros() -> None:
    conteudo = montar_arquivo_afd(
        registros_tipo7=[
            {"nsr": 1, "datahora_marc": "2026-01-01T08:00:00-0300", "cpf": "11111111111"},
            {"nsr": 2, "datahora_marc": "2026-01-01T12:00:00-0300", "cpf": "22222222222"},
            {"nsr": 3, "datahora_marc": "2026-01-01T18:00:00-0300", "cpf": "11111111111"},
        ]
    )
    resultado = ler_arquivo_afd(conteudo)

    assert resultado.cabecalho.cnpj_ou_cpf_empregador == "12345678000199"
    assert len(resultado.registros_tipo7) == 3
    assert [r.nsr_origem_bruto.lstrip("0") or "0" for r in resultado.registros_tipo7] == [
        "1",
        "2",
        "3",
    ]
    assert resultado.total_tipo7_no_trailer == 3
    # A linha de assinatura digital foi reconhecida e nao virou erro nem
    # registro tipo 7 espurio.
    assert any("assinatura" in ignorada.motivo for ignorada in resultado.linhas_ignoradas)


def test_arquivo_sem_trailer_nem_assinatura_ainda_funciona() -> None:
    """Trailer/assinatura sao verificacoes de robustez, nao pre-requisito:
    um arquivo so com cabecalho + registros tipo 7 ainda e lido."""
    conteudo = montar_arquivo_afd(
        registros_tipo7=[
            {"nsr": 1, "datahora_marc": "2026-01-01T08:00:00-0300", "cpf": "11111111111"}
        ],
        incluir_trailer=False,
        incluir_assinatura=False,
    )
    resultado = ler_arquivo_afd(conteudo)
    assert len(resultado.registros_tipo7) == 1
    assert resultado.total_tipo7_no_trailer is None


def test_arquivo_vazio_rejeitado_com_imp001() -> None:
    with pytest.raises(ArquivoAfdInvalido) as excinfo:
        ler_arquivo_afd(b"")
    assert excinfo.value.codigo == "PONTO-IMP-001"


def test_primeira_linha_nao_e_cabecalho_rejeitado_com_imp001() -> None:
    conteudo = ("linha qualquer que nao e um cabecalho tipo 1\r\n").encode("iso-8859-1")
    with pytest.raises(ArquivoAfdInvalido) as excinfo:
        ler_arquivo_afd(conteudo)
    assert excinfo.value.codigo == "PONTO-IMP-001"


def test_arquivo_sem_nenhum_registro_tipo7_rejeitado_com_imp001() -> None:
    conteudo = (montar_tipo1() + "\r\n" + montar_trailer(0) + "\r\n").encode("iso-8859-1")
    with pytest.raises(ArquivoAfdInvalido) as excinfo:
        ler_arquivo_afd(conteudo)
    assert excinfo.value.codigo == "PONTO-IMP-001"


def test_bom_utf8_rejeitado_com_imp003() -> None:
    """docs/fases/F13 T19: 'Rejeita (nao trunca, nao converte) arquivo que
    nao esteja em ISO-8859-1 original'."""
    conteudo = montar_arquivo_afd(
        registros_tipo7=[
            {"nsr": 1, "datahora_marc": "2026-01-01T08:00:00-0300", "cpf": "11111111111"}
        ]
    )
    conteudo_com_bom = b"\xef\xbb\xbf" + conteudo
    with pytest.raises(ArquivoAfdInvalido) as excinfo:
        ler_arquivo_afd(conteudo_com_bom)
    assert excinfo.value.codigo == "PONTO-IMP-003"


def test_crc_do_cabecalho_divergente_rejeitado_com_imp003() -> None:
    linha_corrompida = montar_tipo1()[:-4] + "FFFF"
    conteudo = (
        linha_corrompida
        + "\r\n"
        + montar_tipo7(nsr=1, datahora_marc="2026-01-01T08:00:00-0300", cpf="11111111111")
        + "\r\n"
    ).encode("iso-8859-1")
    with pytest.raises(ArquivoAfdInvalido) as excinfo:
        ler_arquivo_afd(conteudo)
    assert excinfo.value.codigo == "PONTO-IMP-003"


def test_nsr_fora_de_ordem_rejeitado_com_imp003() -> None:
    """Regra 3 do leiaute oficial: registros ordenados por NSR. Um arquivo
    com NSR decrescente e estruturalmente inconsistente."""
    conteudo = montar_arquivo_afd(
        registros_tipo7=[
            {"nsr": 5, "datahora_marc": "2026-01-01T08:00:00-0300", "cpf": "11111111111"},
            {"nsr": 3, "datahora_marc": "2026-01-02T08:00:00-0300", "cpf": "11111111111"},
        ]
    )
    with pytest.raises(ArquivoAfdInvalido) as excinfo:
        ler_arquivo_afd(conteudo)
    assert excinfo.value.codigo == "PONTO-IMP-003"


def test_nsr_repetido_rejeitado_com_imp003() -> None:
    """NSR igual ao anterior tambem viola "estritamente crescente"."""
    conteudo = montar_arquivo_afd(
        registros_tipo7=[
            {"nsr": 5, "datahora_marc": "2026-01-01T08:00:00-0300", "cpf": "11111111111"},
            {"nsr": 5, "datahora_marc": "2026-01-02T08:00:00-0300", "cpf": "11111111111"},
        ]
    )
    with pytest.raises(ArquivoAfdInvalido) as excinfo:
        ler_arquivo_afd(conteudo)
    assert excinfo.value.codigo == "PONTO-IMP-003"


def test_registro_tipo3_rejeitado_com_imp001() -> None:
    """Tipo 3 e marcacao de REP-C/REP-A -- 'nao se aplica ao REP-P' (docs/
    leiaute-afd-aej.md §7). Um arquivo com esse registro nao e um AFD de
    REP-P valido para este importador."""
    conteudo = (
        montar_tipo1()
        + "\r\n"
        + montar_tipo3(nsr=1)
        + "\r\n"
        + montar_tipo7(nsr=2, datahora_marc="2026-01-01T08:00:00-0300", cpf="11111111111")
        + "\r\n"
    ).encode("iso-8859-1")
    with pytest.raises(ArquivoAfdInvalido) as excinfo:
        ler_arquivo_afd(conteudo)
    assert excinfo.value.codigo == "PONTO-IMP-001"


def test_trailer_com_contagem_divergente_rejeitado_com_imp003() -> None:
    conteudo = (
        montar_tipo1()
        + "\r\n"
        + montar_tipo7(nsr=1, datahora_marc="2026-01-01T08:00:00-0300", cpf="11111111111")
        + "\r\n"
        + montar_trailer(99)  # deveria ser 1
        + "\r\n"
        + montar_assinatura()
        + "\r\n"
    ).encode("iso-8859-1")
    with pytest.raises(ArquivoAfdInvalido) as excinfo:
        ler_arquivo_afd(conteudo)
    assert excinfo.value.codigo == "PONTO-IMP-003"


def test_linhas_de_tipo_ignorado_nao_viram_marcacao() -> None:
    """Registros tipo 2/4/5/6 (nao sao marcacao de ponto) sao contados como
    ignorados, nunca colecionados como tipo 7."""

    def _tipo6(nsr: int) -> str:
        campo1 = str(nsr).rjust(9, "0")
        campo2 = "6"
        campo3 = "2026-01-01T08:00:00-0300".ljust(24)
        campo4 = "07"
        linha = campo1 + campo2 + campo3 + campo4
        assert len(linha) == leiaute.TAMANHO_TIPO6
        return linha

    conteudo = (
        montar_tipo1()
        + "\r\n"
        + _tipo6(1)
        + "\r\n"
        + montar_tipo7(nsr=2, datahora_marc="2026-01-01T08:00:00-0300", cpf="11111111111")
        + "\r\n"
        + montar_trailer(1)
        + "\r\n"
    ).encode("iso-8859-1")
    resultado = ler_arquivo_afd(conteudo)
    assert len(resultado.registros_tipo7) == 1
    assert any("tipo 6" in ignorada.motivo for ignorada in resultado.linhas_ignoradas)
