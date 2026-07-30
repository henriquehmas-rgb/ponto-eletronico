"""Geração do PDF do espelho de ponto (T7, F10/A2).

**Biblioteca escolhida: `reportlab`** (documentado em `apps/api/pyproject.
toml`, bloco F10), não `weasyprint` -- puro Python, sem dependência de
sistema (GTK/Pango/Cairo), o que mantém a imagem `runtime` leve. O layout
aqui é **funcional e juridicamente correto** (cabeçalho com identificação
da empresa/período/colaborador, corpo com os dias e totais, rodapé com hash
e dados da assinatura quando houver) -- **não** é "layout de designer"
(proibição 9 do PCF): a F11 refina a identidade visual depois, sobre os
mesmos dados (`Espelho.conteudo`/`hashSha256`), sem mudar o contrato.

Recebe `conteudo` já pronto (o mesmo dicionário gravado em `espelhos.
conteudo`, ver `espelho.py::_montar_conteudo`) para nunca duplicar a lógica
de montagem de dados entre o PDF e o JSON congelado -- o PDF é só outra
representação do mesmo `conteudo`.
"""

from __future__ import annotations

import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_ESTILO_TABELA_DIAS = TableStyle(
    [
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dddddd")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
)

_ESTILO_TABELA_SIMPLES = TableStyle(
    [
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
)


def gerar_pdf_espelho(
    conteudo: dict[str, Any],
    *,
    hash_sha256: str,
    versao: int,
    tipo: str,
    assinaturas: list[dict[str, Any]] | None = None,
) -> bytes:
    """Monta o PDF do espelho a partir do `conteudo` já congelado. Devolve
    os bytes do arquivo -- quem chama decide se grava no MinIO."""
    buffer = io.BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        title="Espelho de Ponto",
    )
    estilos = getSampleStyleSheet()
    elementos: list[Any] = []

    empresa = conteudo.get("empresa", {}) or {}
    colaborador = conteudo.get("colaborador", {}) or {}
    periodo = conteudo.get("periodo", {}) or {}
    totais = conteudo.get("totais", {}) or {}

    elementos.append(Paragraph("Espelho de Ponto", estilos["Title"]))
    elementos.append(
        Paragraph(
            f"REP-P &ndash; Portaria MTP 671/2021 &ndash; versao {versao} ({tipo})",
            estilos["Normal"],
        )
    )
    elementos.append(Spacer(1, 0.5 * cm))

    cabecalho = [
        ["Empresa", str(empresa.get("razaoSocial", ""))],
        ["CNPJ", str(empresa.get("cnpj", ""))],
        ["Colaborador", str(colaborador.get("nomeCompleto", ""))],
        ["Matricula", str(colaborador.get("matricula", ""))],
        ["CPF", str(colaborador.get("cpf", ""))],
        [
            "Periodo",
            f"{periodo.get('dataInicio', '')} a {periodo.get('dataFim', '')} "
            f"({periodo.get('codigo', '')})",
        ],
    ]
    tabela_cabecalho = Table(cabecalho, colWidths=[4 * cm, 12 * cm])
    tabela_cabecalho.setStyle(_ESTILO_TABELA_SIMPLES)
    elementos.append(tabela_cabecalho)
    elementos.append(Spacer(1, 0.5 * cm))

    elementos.append(Paragraph("Dias do periodo", estilos["Heading3"]))
    cabecalho_dias = [
        "Data",
        "Tipo",
        "Previsto",
        "Trabalhado",
        "Extras",
        "Falta",
        "Noturno",
        "Saldo",
    ]
    linhas_dias: list[list[str]] = [cabecalho_dias]
    for dia in conteudo.get("dias", []) or []:
        linhas_dias.append(
            [
                str(dia.get("data", "")),
                str(dia.get("tipoDia", "")),
                str(dia.get("previstoMinutos", 0)),
                str(dia.get("trabalhadoMinutos", 0)),
                str(dia.get("extrasMinutos", 0)),
                str(dia.get("faltaMinutos", 0)),
                str(dia.get("noturnoMinutos", 0)),
                str(dia.get("saldoMinutos", 0)),
            ]
        )
    tabela_dias = Table(linhas_dias, repeatRows=1)
    tabela_dias.setStyle(_ESTILO_TABELA_DIAS)
    elementos.append(tabela_dias)
    elementos.append(Spacer(1, 0.5 * cm))

    elementos.append(Paragraph("Totais do periodo", estilos["Heading3"]))
    linhas_totais = [
        ["Total previsto (minutos)", str(totais.get("previstoMinutos", 0))],
        ["Total trabalhado (minutos)", str(totais.get("trabalhadoMinutos", 0))],
        ["Total de horas extras (minutos)", str(totais.get("extrasMinutos", 0))],
        ["Total de faltas (minutos)", str(totais.get("faltasMinutos", 0))],
        ["Total noturno (minutos)", str(totais.get("noturnoMinutos", 0))],
        [
            "Saldo de banco de horas no fim do periodo (minutos)",
            str(totais.get("saldoBancoMinutos", 0)),
        ],
    ]
    tabela_totais = Table(linhas_totais, colWidths=[10 * cm, 4 * cm])
    tabela_totais.setStyle(_ESTILO_TABELA_SIMPLES)
    elementos.append(tabela_totais)
    elementos.append(Spacer(1, 0.5 * cm))

    elementos.append(Paragraph("Verificacao e assinatura", estilos["Heading3"]))
    elementos.append(Paragraph(f"Hash SHA-256 do conteudo: {hash_sha256}", estilos["Normal"]))
    if assinaturas:
        for assinatura in assinaturas:
            elementos.append(
                Paragraph(
                    "Assinado por "
                    f"{assinatura.get('signatarioTipo', '')} em "
                    f"{assinatura.get('carimboTempo', '')} "
                    f"(metodo: {assinatura.get('metodo', '')}, "
                    f"hash assinado: {assinatura.get('hashAssinado', '')})",
                    estilos["Normal"],
                )
            )
    else:
        elementos.append(Paragraph("Pendente de assinatura do colaborador.", estilos["Normal"]))

    documento.build(elementos)
    return buffer.getvalue()
