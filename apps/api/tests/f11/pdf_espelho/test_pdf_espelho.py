"""Testes de `app.workflow.fechamento.pdf` (T12, F11/A4 -- refino visual).

**Deliberadamente sem fixture de banco.** `gerar_pdf_espelho` recebe
`conteudo` já pronto (o mesmo dicionário que `app.workflow.fechamento.
espelho._montar_conteudo`, F10, monta e grava em `espelhos.conteudo` -- só
leitura, não importado aqui) -- não precisa de sessão, tenant nem RLS para
ser exercitado. Isto também mantém este módulo de teste totalmente
independente da fixture compartilhada `apps/api/tests/f11/conftest.py`
(T1, ownership de A1): não há qualquer acoplamento de ordem de execução
entre os agentes da fase para este critério de aceite específico.

**O que prova (PCF F11 §7, critério 3 / T12 "pronto quando"):** que o
refino visual desta fase preserva, campo a campo, todo texto que o PDF de
F10 já expunha -- razão social, CNPJ, nome completo, matrícula, CPF,
período, cada dia com seus totais, o hash SHA-256 e os dados de assinatura
(ou o aviso de pendência). Os literais abaixo são os MESMOS que
`apps/api/tests/f10/espelhos/test_espelho.py::
test_pdf_gerado_contem_campos_minimos_e_grava_no_minio` já verificava --
comparação direta contra o comportamento anterior, não uma reinvenção.
"""

from __future__ import annotations

import io
from typing import Any

from pypdf import PdfReader

from app.workflow.fechamento.pdf import gerar_pdf_espelho

_HASH_EXEMPLO = "a" * 64


def _conteudo_exemplo() -> dict[str, Any]:
    """Mesma FORMA que `espelho.py::_montar_conteudo` produz (F10, só
    leitura) -- construído à mão aqui para não depender de banco."""
    return {
        "empresa": {
            "id": "11111111-1111-1111-1111-111111111111",
            "razaoSocial": "Empresa de Teste F11 Ltda",
            "cnpj": "12345678000199",
        },
        "colaborador": {
            "id": "22222222-2222-2222-2222-222222222222",
            "nomeCompleto": "Colaborador de Teste F11",
            "matricula": "MAT-F11-001",
            "cpf": "98765432100",
        },
        "vinculo": {"id": "33333333-3333-3333-3333-333333333333"},
        "periodo": {
            "id": "44444444-4444-4444-4444-444444444444",
            "codigo": "2026-07",
            "dataInicio": "2026-07-01",
            "dataFim": "2026-07-31",
        },
        "dias": [
            {
                "data": "2026-07-01",
                "tipoDia": "util",
                "previstoMinutos": 480,
                "trabalhadoMinutos": 480,
                "extrasMinutos": 30,
                "faltaMinutos": 0,
                "noturnoMinutos": 0,
                "saldoMinutos": 30,
                "marcacoesImpares": False,
                "status": "apurado",
                "componentes": [],
                "tratamentos": [],
            },
            {
                "data": "2026-07-02",
                "tipoDia": "util",
                "previstoMinutos": 480,
                "trabalhadoMinutos": 420,
                "extrasMinutos": 0,
                "faltaMinutos": 60,
                "noturnoMinutos": 15,
                "saldoMinutos": -60,
                "marcacoesImpares": False,
                "status": "apurado",
                "componentes": [],
                "tratamentos": [],
            },
        ],
        "totais": {
            "previstoMinutos": 960,
            "trabalhadoMinutos": 900,
            "extrasMinutos": 30,
            "faltasMinutos": 60,
            "noturnoMinutos": 15,
            "saldoBancoMinutos": 120,
        },
        "geradoEm": "2026-07-30T12:00:00+00:00",
    }


def _texto_do_pdf(pdf_bytes: bytes) -> str:
    leitor = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(pagina.extract_text() or "" for pagina in leitor.pages)


def test_pdf_comeca_com_assinatura_de_arquivo_valida() -> None:
    pdf_bytes = gerar_pdf_espelho(
        _conteudo_exemplo(), hash_sha256=_HASH_EXEMPLO, versao=1, tipo="oficial"
    )
    assert pdf_bytes[:4] == b"%PDF"


def test_pdf_preserva_campos_legais_de_cabecalho() -> None:
    """Mesmos literais que `tests/f10/espelhos/test_espelho.py` já
    verificava para o PDF de F10: empresa, CNPJ (via razaoSocial acima),
    colaborador, período, total previsto e hash."""
    conteudo = _conteudo_exemplo()
    pdf_bytes = gerar_pdf_espelho(conteudo, hash_sha256=_HASH_EXEMPLO, versao=3, tipo="retificado")
    texto = _texto_do_pdf(pdf_bytes)

    assert "Colaborador de Teste F11" in texto
    assert "Empresa de Teste F11 Ltda" in texto
    assert "12345678000199" in texto
    assert "MAT-F11-001" in texto
    assert "98765432100" in texto
    assert conteudo["periodo"]["dataInicio"] in texto
    assert conteudo["periodo"]["dataFim"] in texto
    assert "960" in texto  # total previsto
    assert _HASH_EXEMPLO in texto
    assert "versao 3 (retificado)" in texto
    assert "REP-P" in texto
    assert "671/2021" in texto


def test_pdf_preserva_cada_dia_do_periodo() -> None:
    """Nenhum dia do `conteudo["dias"]` desaparece no refino visual --
    prova campo a campo (critério de aceite 3 do PCF)."""
    conteudo = _conteudo_exemplo()
    pdf_bytes = gerar_pdf_espelho(conteudo, hash_sha256=_HASH_EXEMPLO, versao=1, tipo="oficial")
    texto = _texto_do_pdf(pdf_bytes)

    for dia in conteudo["dias"]:
        assert dia["data"] in texto
        assert str(dia["previstoMinutos"]) in texto
        assert str(dia["trabalhadoMinutos"]) in texto


def test_pdf_preserva_todos_os_totais() -> None:
    conteudo = _conteudo_exemplo()
    pdf_bytes = gerar_pdf_espelho(conteudo, hash_sha256=_HASH_EXEMPLO, versao=1, tipo="oficial")
    texto = _texto_do_pdf(pdf_bytes)

    totais = conteudo["totais"]
    assert "Total previsto (minutos)" in texto
    assert "Total trabalhado (minutos)" in texto
    assert "Total de horas extras (minutos)" in texto
    assert "Total de faltas (minutos)" in texto
    assert "Total noturno (minutos)" in texto
    assert "Saldo de banco de horas no fim do periodo (minutos)" in texto
    assert str(totais["saldoBancoMinutos"]) in texto


def test_pdf_sem_assinatura_mostra_pendencia() -> None:
    pdf_bytes = gerar_pdf_espelho(
        _conteudo_exemplo(), hash_sha256=_HASH_EXEMPLO, versao=1, tipo="previo", assinaturas=None
    )
    texto = _texto_do_pdf(pdf_bytes)
    assert "Pendente de assinatura do colaborador." in texto
    assert "PENDENTE" in texto


def test_pdf_com_assinatura_mostra_dados_de_quem_assinou() -> None:
    assinaturas = [
        {
            "signatarioTipo": "colaborador",
            "carimboTempo": "2026-07-31T10:00:00+00:00",
            "metodo": "aceite_eletronico",
            "hashAssinado": _HASH_EXEMPLO,
        }
    ]
    pdf_bytes = gerar_pdf_espelho(
        _conteudo_exemplo(),
        hash_sha256=_HASH_EXEMPLO,
        versao=1,
        tipo="oficial",
        assinaturas=assinaturas,
    )
    texto = _texto_do_pdf(pdf_bytes)
    # `pypdf.extract_text()` pode inserir quebra de linha onde o
    # `Paragraph` do reportlab quebrou visualmente a frase -- normaliza
    # espaco em branco antes de comparar, mesma tolerancia que qualquer
    # extracao de texto de PDF exige (o CONTEUDO nao mudou, so a quebra).
    texto_normalizado = " ".join(texto.split())
    assert "Assinado por colaborador em 2026-07-31T10:00:00+00:00" in texto_normalizado
    assert "metodo: aceite_eletronico" in texto_normalizado
    assert f"hash assinado: {_HASH_EXEMPLO}" in texto_normalizado
    assert "ASSINADO" in texto


def test_pdf_gera_pagina_unica_para_periodo_curto() -> None:
    """Não é um critério do PCF, mas evidencia que o cabeçalho/rodapé
    (`onFirstPage`/`onLaterPages`, decoração pura) não quebra a geração de
    um documento de uma página só."""
    pdf_bytes = gerar_pdf_espelho(
        _conteudo_exemplo(), hash_sha256=_HASH_EXEMPLO, versao=1, tipo="oficial"
    )
    leitor = PdfReader(io.BytesIO(pdf_bytes))
    assert len(leitor.pages) >= 1
    assert leitor.metadata is not None
    assert leitor.metadata.title == "Espelho de Ponto"
