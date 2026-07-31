"""Builders de registro do AEJ, um por tipo (01 a 08, 99, linha final).

Fonte de verdade: `docs/leiaute-afd-aej.md`, secao 9 (regras gerais) e secao
10 (leiaute completo por tipo). **Delimitado por `"|"`, nunca largura fixa**
(isso e exclusivo do AFD, `app.fiscal.afd.registros`, A1) -- regra 3 da
secao 9: cada campo e terminado por `"|"`, exceto o ultimo campo do
registro, que vai direto seguido do terminador de linha (CR+LF, aplicado por
`app.fiscal.comum.formatos.montar_arquivo_texto`, nao por este modulo).

Como os campos sao delimitados (nao posicionais), **nao ha padding** aqui:
um campo `N` e escrito na sua representacao decimal literal, sem zero a
esquerda; um campo `A` e escrito como texto puro. A unica formatacao real
que estes builders aplicam e a dos tipos `D`/`DH`/`H` (que tem um formato de
apresentacao fixo, independente do delimitador) e a omissao de campos
opcionais ausentes (string vazia entre dois `"|"`, nunca `None`/`"None"`).

Este modulo e **puro**: nenhuma consulta a banco, nenhuma decisao de negocio
sobre QUAIS linhas emitir (isso e do orquestrador, `gerador.py`, T9) -- so
"dados resolvidos entram, uma linha de texto sai". Cada builder recebe um
dataclass imutavel espelhando os nomes de campo da norma (coluna "Campo" das
tabelas do leiaute), para que o codigo seja rastreavel ate a fonte sem
precisar reler o PDF.

**Nunca implementa CRC-16** (nao existe no AEJ -- PCF da fase, secao 2.9,
confirmado por leitura integral de `docs/leiaute-afd-aej.md` secao 9/10, que
nao menciona CRC-16 em lugar nenhum).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal

from app.fiscal.comum.formatos import formatar_data, formatar_data_hora

#: Texto literal da linha final de assinatura (identico ao padrao do AFD,
#: `docs/leiaute-afd-aej.md` secao 10, "Linha final"): a assinatura real
#: fica no `.p7s` destacado (`app.fiscal.assinatura`, A3), nunca embutida no
#: arquivo. Preenchido com espaco a direita ate 100 caracteres.
_TEXTO_ASSINATURA_PENDENTE = "ASSINATURA_DIGITAL_EM_ARQUIVO_P7S"
_TAMANHO_LINHA_ASSINATURA = 100

TipoIdentificador = Literal["1", "2"]  # "1"=CNPJ, "2"=CPF
TipoRep = Literal["1", "2", "3"]  # "1"=REP-C, "2"=REP-A, "3"=REP-P
TipoMarcacao = Literal["E", "S", "D"]
FonteMarcacao = Literal["O", "I", "P", "X", "T"]
TipoAusenciaOuComp = Literal["1", "2", "3", "4"]
TipoMovimentoBancoHoras = Literal["1", "2"]


def _juntar(*campos: str) -> str:
    """Junta os campos de um registro com `"|"`, sem `"|"` apos o ultimo
    campo (regra 3 da secao 9) -- o terminador CR+LF vem depois, de
    `montar_arquivo_texto`, nunca deste modulo."""
    return "|".join(campos)


def _opt(valor: str | None) -> str:
    """Campo textual opcional ausente vira string vazia (nunca `"None"`)."""
    return valor if valor is not None else ""


def _opt_int(valor: int | None) -> str:
    """Campo numerico opcional ausente vira string vazia."""
    return "" if valor is None else str(valor)


def _hora(valor: dt.time | None) -> str:
    """Campo tipo `H`: `hhmm`, 4 digitos, sem separador (secao 9, regra 5).
    Ausente (par de entrada/saida condicional que nao existe) vira string
    vazia -- o campo aceita `0 ou 4` caracteres."""
    if valor is None:
        return ""
    return f"{valor.hour:02d}{valor.minute:02d}"


# =============================================================================
# Tipo "01" -- Cabecalho
# =============================================================================


@dataclass(frozen=True, slots=True)
class Cabecalho:
    tp_idt_empregador: TipoIdentificador
    idt_empregador: str
    razao_ou_nome: str
    data_inicial_aej: dt.date
    data_final_aej: dt.date
    data_hora_ger_aej: dt.datetime
    caepf: str | None = None
    cno: str | None = None
    versao_aej: str = "001"


def montar_registro_01(dados: Cabecalho) -> str:
    return _juntar(
        "01",
        dados.tp_idt_empregador,
        dados.idt_empregador,
        _opt(dados.caepf),
        _opt(dados.cno),
        dados.razao_ou_nome,
        formatar_data(dados.data_inicial_aej),
        formatar_data(dados.data_final_aej),
        formatar_data_hora(dados.data_hora_ger_aej),
        dados.versao_aej,
    )


# =============================================================================
# Tipo "02" -- REPs utilizados
# =============================================================================


@dataclass(frozen=True, slots=True)
class RepUtilizado:
    id_rep_aej: int
    tp_rep: TipoRep
    nr_rep: str


def montar_registro_02(dados: RepUtilizado) -> str:
    return _juntar("02", str(dados.id_rep_aej), dados.tp_rep, dados.nr_rep)


# =============================================================================
# Tipo "03" -- Vinculos
# =============================================================================


@dataclass(frozen=True, slots=True)
class VinculoAej:
    idt_vinculo_aej: int
    cpf: str
    nome_emp: str


def montar_registro_03(dados: VinculoAej) -> str:
    return _juntar("03", str(dados.idt_vinculo_aej), dados.cpf, dados.nome_emp)


# =============================================================================
# Tipo "04" -- Horario contratual
# =============================================================================


@dataclass(frozen=True, slots=True)
class HorarioContratual:
    cod_hor_contratual: str
    dur_jornada: int
    hr_entrada_01: dt.time
    hr_saida_01: dt.time
    hr_entrada_02: dt.time | None = None
    hr_saida_02: dt.time | None = None


def montar_registro_04(dados: HorarioContratual) -> str:
    return _juntar(
        "04",
        dados.cod_hor_contratual,
        str(dados.dur_jornada),
        _hora(dados.hr_entrada_01),
        _hora(dados.hr_saida_01),
        _hora(dados.hr_entrada_02),
        _hora(dados.hr_saida_02),
    )


# =============================================================================
# Tipo "05" -- Marcacoes (registro-chave)
# =============================================================================


@dataclass(frozen=True, slots=True)
class MarcacaoAej:
    idt_vinculo_aej: int
    data_hora_marc: dt.datetime
    id_rep_aej: int
    tp_marc: TipoMarcacao
    seq_ent_saida: int
    fonte_marc: FonteMarcacao
    cod_hor_contratual: str | None = None
    motivo: str | None = None


def montar_registro_05(dados: MarcacaoAej) -> str:
    return _juntar(
        "05",
        str(dados.idt_vinculo_aej),
        formatar_data_hora(dados.data_hora_marc),
        str(dados.id_rep_aej),
        dados.tp_marc,
        str(dados.seq_ent_saida),
        dados.fonte_marc,
        _opt(dados.cod_hor_contratual),
        _opt(dados.motivo),
    )


# =============================================================================
# Tipo "06" -- Matricula eSocial (colaborador com mais de um vinculo)
# =============================================================================


@dataclass(frozen=True, slots=True)
class MatriculaEsocial:
    idt_vinculo_aej: int
    mat_esocial: str


def montar_registro_06(dados: MatriculaEsocial) -> str:
    return _juntar("06", str(dados.idt_vinculo_aej), dados.mat_esocial)


# =============================================================================
# Tipo "07" -- Ausencias e Banco de Horas
# =============================================================================


@dataclass(frozen=True, slots=True)
class AusenciaOuBancoHoras:
    idt_vinculo_aej: int
    tipo_ausen_ou_comp: TipoAusenciaOuComp
    data: dt.date
    qt_minutos: int | None = None
    tipo_mov_bh: TipoMovimentoBancoHoras | None = None


def montar_registro_07(dados: AusenciaOuBancoHoras) -> str:
    return _juntar(
        "07",
        str(dados.idt_vinculo_aej),
        dados.tipo_ausen_ou_comp,
        formatar_data(dados.data),
        _opt_int(dados.qt_minutos),
        _opt(dados.tipo_mov_bh),
    )


# =============================================================================
# Tipo "08" -- Identificacao do PTRP
# =============================================================================


@dataclass(frozen=True, slots=True)
class IdentificacaoPtrp:
    nome_prog: str
    versao_prog: str
    tp_idt_desenv: TipoIdentificador
    idt_desenv: str
    razao_nome_desenv: str
    #: Tipada `N` (numerica) no leiaute oficial para um campo de e-mail --
    #: provavel erro de digitacao da norma (um e-mail nao e numerico).
    #: Tratado aqui como texto livre, SEM "corrigir" a observacao: o valor e
    #: escrito exatamente como veio, documentado tambem em
    #: `docs/leiaute-afd-aej.md` secao 10, tipo "08".
    email_desenv: str


def montar_registro_08(dados: IdentificacaoPtrp) -> str:
    return _juntar(
        "08",
        dados.nome_prog,
        dados.versao_prog,
        dados.tp_idt_desenv,
        dados.idt_desenv,
        dados.razao_nome_desenv,
        dados.email_desenv,
    )


# =============================================================================
# Tipo "99" -- Trailer
# =============================================================================


@dataclass(frozen=True, slots=True)
class TrailerAej:
    """Contagens por tipo de registro do arquivo.

    Leitura literal da tabela de `docs/leiaute-afd-aej.md` secao 10 (tipo
    "99"): os 8 campos de contagem cobrem os tipos "01" a "08" -- **inclui**
    `qtRegistrosTipo01` (o cabecalho), diferente do trailer do AFD (que
    omite o cabecalho e o proprio trailer). O trailer do AEJ so omite a
    contagem de si mesmo (tipo "99"); a contagem do tipo "01" existe como
    campo, so que e trivialmente sempre "1" (ha exatamente um cabecalho por
    arquivo). Decisao de leitura documentada aqui porque a paráfrase do PCF
    da fase ("sem contar a si mesmo nem o tipo '01'") e ambigua lida
    isoladamente -- a tabela literal (fonte primaria, extraida do PDF oficial
    pela T0 com checagem de consistencia de tamanho) e quem decide.
    """

    qt_registros_tipo_01: int
    qt_registros_tipo_02: int
    qt_registros_tipo_03: int
    qt_registros_tipo_04: int
    qt_registros_tipo_05: int
    qt_registros_tipo_06: int
    qt_registros_tipo_07: int
    qt_registros_tipo_08: int


def montar_registro_99(dados: TrailerAej) -> str:
    return _juntar(
        "99",
        str(dados.qt_registros_tipo_01),
        str(dados.qt_registros_tipo_02),
        str(dados.qt_registros_tipo_03),
        str(dados.qt_registros_tipo_04),
        str(dados.qt_registros_tipo_05),
        str(dados.qt_registros_tipo_06),
        str(dados.qt_registros_tipo_07),
        str(dados.qt_registros_tipo_08),
    )


def montar_linha_assinatura() -> str:
    """Linha final do arquivo (sem numero de tipo, sem `"|"` -- e um unico
    campo de 100 caracteres): texto literal `ASSINATURA_DIGITAL_EM_ARQUIVO_
    P7S` com espaco a direita ate completar 100 caracteres, identico ao
    padrao do AFD (`docs/leiaute-afd-aej.md` secao 10, "Linha final")."""
    return _TEXTO_ASSINATURA_PENDENTE.ljust(_TAMANHO_LINHA_ASSINATURA)
