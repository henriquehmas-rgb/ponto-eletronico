"""Geração do PDF do espelho de ponto -- layout funcional por F10/A2 (T7),
identidade visual refinada por F11/A4 (T12).

**Este arquivo é a única exceção de ownership de F11 sobre um pacote
congelado de F10** (PCF F11 §5): só `pdf.py` muda, `espelho.py` e o resto do
pacote `app/workflow/fechamento/**` continuam intocados. A assinatura de
`gerar_pdf_espelho(conteudo, *, hash_sha256, versao, tipo, assinaturas=None)`
**não muda** -- é o contrato com `espelho.py::gerar_espelho_do_vinculo`, que
você não edita.

**O que muda nesta fase: só apresentação, nunca conteúdo.** Todo campo
textual que o PDF de F10 já expunha (razão social, CNPJ, nome completo,
matrícula, CPF, período, um item por dia do período com todos os totais,
hash SHA-256, dados de assinatura ou o aviso de pendência) continua presente
com o MESMO texto/rótulo -- só a apresentação visual muda (cor, tipografia,
grade, cabeçalho/rodapé de página, selo de status). O teste desta fase
(`apps/api/tests/f11/pdf_espelho/`) prova isto por extração de texto via
`pypdf`, comparando contra os mesmos literais que o teste de F10
(`apps/api/tests/f10/espelhos/test_espelho.py`) já verificava.

**Biblioteca: continua `reportlab`** (nenhuma dependência nova -- PCF F11
§2.5 só pede `openpyxl` na API e `croniter`/`httpx` no worker, nada para
PDF).

**Identidade visual aplicada, fonte por fonte (PCF F11 §2.6/T12 -- "tipografia
do design system de F9a, cores da paleta oficial"):**

* **Cor:** os hex abaixo são copiados de `packages/contracts/design-tokens.
  json` (`cores.paletas.marca`/`sucesso`/`erro`/`neutro`) e conferidos contra
  `apps/web/src/estilos/tokens.gerado.css` (tema claro -- um PDF não tem modo
  escuro) -- os MESMOS valores que a interface usa, nunca um hex inventado.
  **Achado registrado, não escondido:** `docs/marca/identidade-visual.md`
  (RFC-003) transcreve uma escala de "marca" com valores diferentes destes a
  partir do tom 700 (ex.: `700 #3D4DAF` no documento vs. `#3948A7` em
  `design-tokens.json`/`tokens.gerado.css`) -- o próprio documento afirma
  "paleta idêntica, tom a tom" ao contrato, mas na prática só o tom 600 (base,
  `#4C5FCA`) bate; os demais tons divergem. Como `design-tokens.json` é o
  contrato que a interface real consome (fonte de verdade operacional), este
  módulo usa os valores de `design-tokens.json`, não os do documento
  markdown. Registrado em `docs/backlog.md` como divergência de documentação
  a corrigir (não é um bug de código, é o texto do manual desatualizado
  frente ao contrato).
* **Tipografia:** o manual de marca (`docs/marca/identidade-visual.md` §5)
  fixa três vozes -- Schibsted Grotesk (display), IBM Plex Sans (texto/UI) e
  IBM Plex Mono (tabular: horas, hash, documento legal) -- carregadas via
  `next/font/google` só em `apps/web`. **Nenhum arquivo `.ttf`/`.otf` dessas
  três famílias existe no repositório** (`next/font` as baixa e as
  autohospeda no build do Next, num formato `.woff2` com nome de arquivo
  hasheado -- `reportlab` não lê `.woff2`, só `.ttf`/`.otf`/Type1) e baixar um
  arquivo de fonte de fora do repositório para embutir no PDF está fora do
  escopo desta tarefa (proibição geral de baixar/executar arquivo de fonte
  não confiável). **Substituição documentada, não escondida:** o corpo do
  documento usa `Helvetica`/`Helvetica-Bold` (Type1 embutida no leitor de PDF,
  sem necessidade de arquivo externo) como voz de texto/título -- a família
  sans mais próxima disponível nativamente -- e `Courier` (monoespaçada,
  largura fixa por dígito) para toda coluna numérica/tabular e para o hash,
  preservando a intenção funcional do manual ("cada dígito tem a mesma
  largura, colunas não dançam entre linhas") mesmo sem a fonte de marca
  exata. Se uma fase futura tiver os `.ttf` da licença OFL das três famílias
  disponíveis em `apps/api` (ou um pipeline de conversão `.woff2` -> `.ttf`),
  é troca de duas constantes de nome de fonte aqui, não uma reescrita.
* **Símbolo:** o traço de confirmação sobre a linha de base
  (`docs/marca/identidade-visual.md` §3, mesmo path SVG usado por
  `apps/web/src/componentes/marca/simbolo.tsx`) é desenhado vetorialmente no
  cabeçalho de cada página com os primitivos de linha do `reportlab.pdfgen.
  canvas.Canvas` -- mesma geometria do SVG fonte (`M8.6 18.6 13.6 24.1 24.2
  7.6` + `M6.4 26 H25.6`, viewBox 32x32), nunca uma imagem rasterizada.
"""

from __future__ import annotations

import datetime as dt
import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# --- Paleta (copiada de packages/contracts/design-tokens.json, tema claro --
# ver docstring do módulo para o achado de divergência com docs/marca/) ---
_COR_MARCA_600 = colors.HexColor("#4C5FCA")  # acao primaria / cabecalho de tabela
_COR_MARCA_700 = colors.HexColor("#3948A7")  # simbolo, texto de enfase sobre branco
_COR_MARCA_800 = colors.HexColor("#273281")  # wordmark, titulo
_COR_MARCA_100 = colors.HexColor("#EDF1FF")  # fundo sutil de cartao/faixa
_COR_NEUTRO_900 = colors.HexColor("#262B31")  # texto primario
_COR_NEUTRO_700 = colors.HexColor("#4D555F")  # texto secundario
_COR_NEUTRO_500 = colors.HexColor("#838D9A")  # texto terciario / rotulo de rodape
_COR_NEUTRO_200 = colors.HexColor("#E2E7ED")  # grade / regua
_COR_NEUTRO_100 = colors.HexColor("#EFF2F6")  # zebra de linha
_COR_NEUTRO_50 = colors.HexColor("#F8FAFC")  # fundo de pagina (nao usado no PDF, so referencia)
_COR_SUCESSO_FUNDO = colors.HexColor("#DDFAE7")  # selo "assinado"
_COR_SUCESSO_TEXTO = colors.HexColor("#004A2A")
_COR_ERRO_FUNDO = colors.HexColor("#FFEDEB")  # selo "recusado"
_COR_ERRO_TEXTO = colors.HexColor("#760614")
_COR_BRANCO = colors.white

# --- Tipografia: Helvetica/Courier como substitutos documentados de
# Schibsted Grotesk/IBM Plex Sans/IBM Plex Mono (ver docstring do modulo) ---
_FONTE_TITULO = "Helvetica-Bold"
_FONTE_TEXTO = "Helvetica"
_FONTE_TEXTO_NEGRITO = "Helvetica-Bold"
_FONTE_TABULAR = "Courier"  # substituto de IBM Plex Mono: horas, hash, NSR

_MARGEM = 1.8 * cm
_ALTURA_CABECALHO = 1.6 * cm
_ALTURA_RODAPE = 1.2 * cm

_ESTILO_TABELA_DIAS = TableStyle(
    [
        ("FONTNAME", (0, 0), (-1, 0), _FONTE_TEXTO_NEGRITO),
        ("FONTNAME", (0, 1), (-1, -1), _FONTE_TABULAR),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("TEXTCOLOR", (0, 0), (-1, 0), _COR_BRANCO),
        ("BACKGROUND", (0, 0), (-1, 0), _COR_MARCA_600),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_COR_BRANCO, _COR_NEUTRO_100]),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, _COR_MARCA_700),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, _COR_NEUTRO_200),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
)

_ESTILO_TABELA_SIMPLES = TableStyle(
    [
        ("FONTNAME", (0, 0), (0, -1), _FONTE_TEXTO_NEGRITO),
        ("FONTNAME", (1, 0), (1, -1), _FONTE_TEXTO),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), _COR_NEUTRO_700),
        ("TEXTCOLOR", (1, 0), (1, -1), _COR_NEUTRO_900),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]
)

_ESTILO_TABELA_TOTAIS = TableStyle(
    [
        ("FONTNAME", (0, 0), (0, -1), _FONTE_TEXTO),
        ("FONTNAME", (1, 0), (1, -1), _FONTE_TABULAR),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), _COR_NEUTRO_700),
        ("TEXTCOLOR", (1, 0), (1, -1), _COR_MARCA_800),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BACKGROUND", (0, 0), (-1, -1), _COR_MARCA_100),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, _COR_NEUTRO_200),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]
)


def _desenhar_simbolo(canvas_: Canvas, x: float, y: float, tamanho: float) -> None:
    """Desenha o simbolo da marca (traco de confirmacao sobre a linha de
    base) com primitivos vetoriais -- mesma geometria do SVG fonte
    (`docs/marca/identidade-visual.md` §3, viewBox 0 0 32 32), nunca uma
    imagem. `(x, y)` e o canto inferior-esquerdo da caixa `tamanho x tamanho`
    (unidades do canvas, ex.: `mm`)."""
    escala = tamanho / 32.0

    def _p(sx: float, sy: float) -> tuple[float, float]:
        # SVG cresce para baixo; o canvas do reportlab cresce para cima.
        return (x + sx * escala, y + (32.0 - sy) * escala)

    canvas_.saveState()
    canvas_.setStrokeColor(_COR_MARCA_700)
    canvas_.setLineWidth(max(2.6 * escala, 0.4))
    canvas_.setLineCap(1)  # round
    canvas_.setLineJoin(1)  # round

    p1 = _p(8.6, 18.6)
    p2 = _p(13.6, 24.1)
    p3 = _p(24.2, 7.6)
    caminho = canvas_.beginPath()
    caminho.moveTo(*p1)
    caminho.lineTo(*p2)
    caminho.lineTo(*p3)
    canvas_.drawPath(caminho, stroke=1, fill=0)

    base_ini = _p(6.4, 26.0)
    base_fim = _p(25.6, 26.0)
    canvas_.line(base_ini[0], base_ini[1], base_fim[0], base_fim[1])
    canvas_.restoreState()


def _moldura_pagina(
    canvas_: Canvas,
    documento: Any,
    *,
    versao: int,
    tipo: str,
    gerado_em: str,
) -> None:
    """Cabecalho/rodape desenhados em toda pagina (`onFirstPage`/
    `onLaterPages` do `SimpleDocTemplate`): faixa de marca, simbolo,
    numeracao de pagina e referencia legal -- decoracao pura, nenhum campo de
    conteudo do espelho mora aqui (todo dado fica no corpo, ver docstring do
    modulo)."""
    largura, altura = A4
    canvas_.saveState()

    _desenhar_simbolo(canvas_, _MARGEM, altura - _MARGEM - 4 * mm, 6 * mm)
    canvas_.setFont(_FONTE_TITULO, 11)
    canvas_.setFillColor(_COR_MARCA_800)
    canvas_.drawString(_MARGEM + 9 * mm, altura - _MARGEM - 2.2 * mm, "SEEG Ponto")
    canvas_.setFont(_FONTE_TEXTO, 7.5)
    canvas_.setFillColor(_COR_NEUTRO_500)
    canvas_.drawRightString(
        largura - _MARGEM, altura - _MARGEM - 2.2 * mm, f"Pagina {canvas_.getPageNumber()}"
    )
    canvas_.setStrokeColor(_COR_MARCA_600)
    canvas_.setLineWidth(0.8)
    canvas_.line(_MARGEM, altura - _MARGEM - 6 * mm, largura - _MARGEM, altura - _MARGEM - 6 * mm)

    canvas_.setStrokeColor(_COR_NEUTRO_200)
    canvas_.setLineWidth(0.5)
    canvas_.line(_MARGEM, _MARGEM, largura - _MARGEM, _MARGEM)
    canvas_.setFont(_FONTE_TEXTO, 7)
    canvas_.setFillColor(_COR_NEUTRO_500)
    canvas_.drawString(_MARGEM, _MARGEM - 3.5 * mm, f"Espelho de Ponto v{versao} ({tipo}) - REP-P")
    canvas_.drawRightString(largura - _MARGEM, _MARGEM - 3.5 * mm, f"Gerado em {gerado_em}")

    canvas_.restoreState()


def _selo_status(texto: str, *, positivo: bool) -> Table:
    """Selo colorido de status (assinado/pendente) -- cor NUNCA e o unico
    canal (o texto do selo ja diz o estado por extenso, a cor so reforca,
    mesma regra do manual de marca §2/§4)."""
    fundo = _COR_SUCESSO_FUNDO if positivo else _COR_ERRO_FUNDO
    texto_cor = _COR_SUCESSO_TEXTO if positivo else _COR_ERRO_TEXTO
    tabela = Table([[texto]], colWidths=[None])
    tabela.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), fundo),
                ("TEXTCOLOR", (0, 0), (0, 0), texto_cor),
                ("FONTNAME", (0, 0), (0, 0), _FONTE_TEXTO_NEGRITO),
                ("FONTSIZE", (0, 0), (0, 0), 8),
                ("TOPPADDING", (0, 0), (0, 0), 3),
                ("BOTTOMPADDING", (0, 0), (0, 0), 3),
                ("LEFTPADDING", (0, 0), (0, 0), 8),
                ("RIGHTPADDING", (0, 0), (0, 0), 8),
            ]
        )
    )
    return tabela


def gerar_pdf_espelho(
    conteudo: dict[str, Any],
    *,
    hash_sha256: str,
    versao: int,
    tipo: str,
    assinaturas: list[dict[str, Any]] | None = None,
) -> bytes:
    """Monta o PDF do espelho a partir do `conteudo` já congelado. Devolve
    os bytes do arquivo -- quem chama decide se grava no MinIO.

    Assinatura idêntica à de F10 (`app.workflow.fechamento.espelho::
    gerar_espelho_do_vinculo` continua chamando exatamente assim, PCF F11
    §5) -- só o corpo muda, refinando a apresentação (T12)."""
    buffer = io.BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=_MARGEM + _ALTURA_CABECALHO,
        bottomMargin=_MARGEM + _ALTURA_RODAPE,
        leftMargin=_MARGEM,
        rightMargin=_MARGEM,
        title="Espelho de Ponto",
        author="SEEG Ponto",
    )
    estilos = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle(
        "TituloEspelho",
        parent=estilos["Title"],
        fontName=_FONTE_TITULO,
        textColor=_COR_MARCA_800,
        spaceAfter=2,
    )
    estilo_subtitulo = ParagraphStyle(
        "SubtituloEspelho",
        parent=estilos["Normal"],
        fontName=_FONTE_TEXTO,
        textColor=_COR_NEUTRO_700,
        fontSize=9,
    )
    estilo_secao = ParagraphStyle(
        "SecaoEspelho",
        parent=estilos["Heading3"],
        fontName=_FONTE_TITULO,
        textColor=_COR_MARCA_800,
        spaceBefore=6,
        spaceAfter=4,
    )
    estilo_corpo = ParagraphStyle(
        "CorpoEspelho",
        parent=estilos["Normal"],
        fontName=_FONTE_TEXTO,
        textColor=_COR_NEUTRO_900,
        fontSize=9,
    )
    estilo_hash = ParagraphStyle(
        "HashEspelho",
        parent=estilos["Normal"],
        fontName=_FONTE_TABULAR,
        textColor=_COR_NEUTRO_700,
        fontSize=8,
    )
    elementos: list[Any] = []

    empresa = conteudo.get("empresa", {}) or {}
    colaborador = conteudo.get("colaborador", {}) or {}
    periodo = conteudo.get("periodo", {}) or {}
    totais = conteudo.get("totais", {}) or {}
    gerado_em = str(conteudo.get("geradoEm") or dt.datetime.now(tz=dt.UTC).isoformat())

    elementos.append(Paragraph("Espelho de Ponto", estilo_titulo))
    elementos.append(
        Paragraph(
            f"REP-P &ndash; Portaria MTP 671/2021 &ndash; versao {versao} ({tipo})",
            estilo_subtitulo,
        )
    )
    elementos.append(Spacer(1, 0.4 * cm))

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
    tabela_cabecalho = Table(cabecalho, colWidths=[3.2 * cm, 12.8 * cm])
    tabela_cabecalho.setStyle(_ESTILO_TABELA_SIMPLES)
    elementos.append(tabela_cabecalho)
    elementos.append(Spacer(1, 0.5 * cm))

    elementos.append(Paragraph("Dias do periodo", estilo_secao))
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
    estilo_dias = TableStyle(_ESTILO_TABELA_DIAS.getCommands())
    # Realca o saldo do dia (ultima coluna): negativo em vermelho-erro,
    # positivo em verde-sucesso -- reforco visual, o sinal numerico ja diz o
    # estado por extenso (cor nunca e o unico canal, manual de marca §4).
    for indice_linha, dia in enumerate(conteudo.get("dias", []) or [], start=1):
        saldo = dia.get("saldoMinutos", 0) or 0
        if saldo < 0:
            estilo_dias.add("TEXTCOLOR", (7, indice_linha), (7, indice_linha), _COR_ERRO_TEXTO)
        elif saldo > 0:
            estilo_dias.add("TEXTCOLOR", (7, indice_linha), (7, indice_linha), _COR_SUCESSO_TEXTO)
    tabela_dias.setStyle(estilo_dias)
    elementos.append(tabela_dias)
    elementos.append(Spacer(1, 0.5 * cm))

    elementos.append(Paragraph("Totais do periodo", estilo_secao))
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
    tabela_totais = Table(linhas_totais, colWidths=[11.5 * cm, 4.5 * cm])
    tabela_totais.setStyle(_ESTILO_TABELA_TOTAIS)
    elementos.append(tabela_totais)
    elementos.append(Spacer(1, 0.5 * cm))

    elementos.append(Paragraph("Verificacao e assinatura", estilo_secao))
    elementos.append(Paragraph(f"Hash SHA-256 do conteudo: {hash_sha256}", estilo_hash))
    elementos.append(Spacer(1, 0.2 * cm))
    if assinaturas:
        elementos.append(_selo_status("ASSINADO", positivo=True))
        elementos.append(Spacer(1, 0.15 * cm))
        for assinatura in assinaturas:
            elementos.append(
                Paragraph(
                    "Assinado por "
                    f"{assinatura.get('signatarioTipo', '')} em "
                    f"{assinatura.get('carimboTempo', '')} "
                    f"(metodo: {assinatura.get('metodo', '')}, "
                    f"hash assinado: {assinatura.get('hashAssinado', '')})",
                    estilo_corpo,
                )
            )
    else:
        elementos.append(_selo_status("PENDENTE", positivo=False))
        elementos.append(Spacer(1, 0.15 * cm))
        elementos.append(Paragraph("Pendente de assinatura do colaborador.", estilo_corpo))

    def _aplicar_moldura(canvas_: Canvas, doc: Any) -> None:
        _moldura_pagina(canvas_, doc, versao=versao, tipo=tipo, gerado_em=gerado_em)

    documento.build(elementos, onFirstPage=_aplicar_moldura, onLaterPages=_aplicar_moldura)
    return buffer.getvalue()
