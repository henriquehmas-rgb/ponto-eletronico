"""Registros de largura fixa do AFD: tipos "1" (cabeçalho), "2" (inclusão/
alteração de empresa), "4" (ajuste de relógio), "5" (inclusão/alteração/
exclusão de empregado), "6" (eventos sensíveis), "9" (trailer) e a linha
final de assinatura (`docs/leiaute-afd-aej.md` §7 — todos os campos,
posições e tamanhos vêm de lá, transcritos abaixo campo a campo).

O tipo "7" (marcação de ponto do REP-P, o registro central) mora em
`app.fiscal.afd.tipo7` — é grande e complexo o bastante (hash SHA-256
encadeado, ADR-012) para merecer módulo próprio; este módulo cobre os
demais.

**Tipos "2", "4", "5" e "6" não têm fonte de dado real nesta fase.** O
sistema hoje não tem: edição de cadastro de empresa via REP-P (tipo "2"),
ajuste manual de relógio do REP-P (tipo "4", o relógio é o do servidor,
nunca ajustado por um operador), evento de inclusão/alteração/exclusão de
empregado disparado PELO REP-P (tipo "5" — o cadastro de colaborador é de
F2/F3, um domínio diferente, e o AFD "deriva exclusivamente das marcações",
não do cadastro), nem evento de disponibilidade/indisponibilidade de
serviço do REP-P (tipo "6"). Os quatro *builders* abaixo são implementados
e testados por si só (provam tamanho de campo, CRC-16 quando aplicável) —
mas `app.fiscal.afd.gerador` (T6) NUNCA os chama: o AFD que este sistema
gera hoje contém sempre exatamente 1 registro tipo "1", N registros tipo
"7", 1 registro tipo "9" e a linha de assinatura — 0 registros dos tipos
"2"/"3"/"4"/"5"/"6" (`docs/fases/F12-conformidade-rep-p.md`, T4). Isto não é
uma lacuna escondida: é a leitura literal de "não invente uma tabela de
eventos que não existe" (mesma seção do PCF).
"""

from __future__ import annotations

import datetime as dt
from typing import Final, Literal

from app.fiscal.afd.crc16 import crc16_ccitt
from app.fiscal.comum.formatos import CODIFICACAO_LEIAUTE, formatar_data, formatar_data_hora

#: Lacuna nº 2 de `docs/leiaute-afd-aej.md` §1/§15: a regra geral 7 do Anexo
#: V ("o preenchimento dos campos deve se iniciar pela esquerda e posições
#: não utilizadas devem ser preenchidas com espaço"), lida ao pé da letra,
#: alinharia até campo numérico à ESQUERDA com espaço à direita — o que
#: quebraria a ordenação lexicográfica correta do NSR exigida pela regra 4
#: ("2" + espaços ordena DEPOIS de "10" + espaços numa comparação de string)
#: e contradiz a prática de mercado herdada da Portaria 1.510/2009 (zero à
#: esquerda, alinhado à direita, para campo N). Decisão fixada pelo PCF F12
#: §2.9: o padrão ATIVO é zero à esquerda / alinhado à direita — a única
#: leitura que preserva a ordenação correta por NSR. Os dois modos ficam
#: implementados atrás desta constante isolada e nomeada, para trocar rápido
#: se um AFD de referência real provar o contrário.
MODO_PREENCHIMENTO_NUMERICO: Literal["zero_esquerda", "espaco_direita"] = "zero_esquerda"

#: Versão do leiaute do AFD, campo nº 11 do tipo "1" — constante fixada pela
#: norma ("Preencher com '003'"), não uma versão do produto.
_VERSAO_LEIAUTE_AFD: Final[str] = "003"

#: Linha final de assinatura digital (100 caracteres, sem número de tipo,
#: `docs/leiaute-afd-aej.md` §7 "Linha final"). A assinatura real fica no
#: `.p7s` destacado (A3, T11); esta linha é sempre o mesmo texto literal.
_TEXTO_ASSINATURA_PLACEHOLDER: Final[str] = "ASSINATURA_DIGITAL_EM_ARQUIVO_P7S"


def preencher_numerico(valor: str, tamanho: int) -> str:
    """Campo tipo `N`: zero à esquerda / alinhado à direita no modo padrão
    (`MODO_PREENCHIMENTO_NUMERICO`). `valor` já deve conter só os caracteres
    do dado (sem padding prévio); levanta `ValueError` se `valor` já exceder
    `tamanho` (truncar silenciosamente esconderia um dado que não cabe no
    campo, pior que um erro explícito numa fase de conformidade legal)."""
    if len(valor) > tamanho:
        raise ValueError(f"valor {valor!r} excede o tamanho do campo numerico ({tamanho}).")
    if MODO_PREENCHIMENTO_NUMERICO == "zero_esquerda":
        return valor.rjust(tamanho, "0")
    return valor.ljust(tamanho, " ")


def preencher_alfanumerico(valor: str, tamanho: int) -> str:
    """Campo tipo `A`: sempre espaço à direita / alinhado à esquerda — não
    há ambiguidade aqui (regra 7 do Anexo V é natural para texto), ao
    contrário do campo `N` (ver `MODO_PREENCHIMENTO_NUMERICO`)."""
    if len(valor) > tamanho:
        raise ValueError(f"valor {valor!r} excede o tamanho do campo alfanumerico ({tamanho}).")
    return valor.ljust(tamanho, " ")


def _com_crc16(corpo_sem_crc: str) -> str:
    """Acrescenta os 4 caracteres hexadecimais do CRC-16 CCITT-TRUE ao final
    de `corpo_sem_crc` (`docs/leiaute-afd-aej.md` §8.1: "os 4 caracteres
    hexadecimais do CRC-16 devem ser gravados... nesta ordem"). O CRC cobre
    exatamente os bytes de `corpo_sem_crc` na codificação do leiaute — da
    posição 1 até a posição imediatamente anterior ao campo de CRC,
    excluindo o próprio campo de CRC e excluindo o terminador CR+LF (mesma
    seção, inferência documentada como razoável, não citação literal).
    Hexadecimal em MAIÚSCULAS: a fonte não declara o caso, mas é a
    convenção de leiautes fiscais brasileiros correlatos (ex.: SPED); troque
    junto com `MODO_PREENCHIMENTO_NUMERICO` se um AFD de referência real
    provar minúsculas."""
    crc = crc16_ccitt(corpo_sem_crc.encode(CODIFICACAO_LEIAUTE))
    return corpo_sem_crc + format(crc, "04X")


def montar_registro_tipo1(
    *,
    tipo_identificador_empregador: Literal["1", "2"],
    cnpj_ou_cpf_empregador: str,
    cno_ou_caepf: str | None,
    razao_social_empregador: str,
    numero_inpi: str,
    periodo_inicio: dt.date,
    periodo_fim: dt.date,
    gerado_em: dt.datetime,
    tipo_identificador_fabricante: Literal["1", "2"],
    cnpj_ou_cpf_fabricante: str,
    modelo_rep_c: str = "",
) -> str:
    """Tipo "1" — Cabeçalho (302 caracteres, `docs/leiaute-afd-aej.md` §7).
    Campo nº 7 (REP-C: nº de fabricação · REP-A: nº do processo do
    acordo/convenção · **REP-P: número de registro no INPI**) sempre recebe
    `numero_inpi` aqui — este módulo só é chamado no contexto REP-P."""
    corpo = (
        preencher_numerico("0", 9)  # 1: "000000000" constante
        + preencher_numerico("1", 1)  # 2: tipo do registro "1"
        + preencher_numerico(tipo_identificador_empregador, 1)  # 3
        + preencher_numerico(cnpj_ou_cpf_empregador, 14)  # 4
        + preencher_numerico(cno_ou_caepf or "", 14)  # 5
        + preencher_alfanumerico(razao_social_empregador, 150)  # 6
        + preencher_numerico(numero_inpi, 17)  # 7: REP-P => numero INPI
        + preencher_alfanumerico(formatar_data(periodo_inicio), 10)  # 8
        + preencher_alfanumerico(formatar_data(periodo_fim), 10)  # 9
        + preencher_alfanumerico(formatar_data_hora(gerado_em), 24)  # 10
        + preencher_numerico(_VERSAO_LEIAUTE_AFD, 3)  # 11
        + preencher_numerico(tipo_identificador_fabricante, 1)  # 12
        + preencher_numerico(cnpj_ou_cpf_fabricante, 14)  # 13
        + preencher_alfanumerico(modelo_rep_c, 30)  # 14: so REP-C, vazio aqui
    )
    linha = _com_crc16(corpo)
    if len(linha) != 302:
        raise ValueError(f"registro tipo 1 com tamanho inesperado: {len(linha)} (esperado 302).")
    return linha


def montar_registro_tipo2(
    *,
    nsr: int,
    gravado_em: dt.datetime,
    cpf_responsavel: str,
    tipo_identificador_empregador: Literal["1", "2"],
    cnpj_ou_cpf_empregador: str,
    cno_ou_caepf: str | None,
    razao_social_empregador: str,
    local_prestacao_servicos: str,
) -> str:
    """Tipo "2" — Inclusão/alteração da identificação da empresa no REP
    (331 caracteres). Não exercitado por `app.fiscal.afd.gerador` nesta fase
    (ver docstring do módulo) — *builder* puro, testado isoladamente."""
    corpo = (
        preencher_numerico(str(nsr), 9)  # 1
        + preencher_numerico("2", 1)  # 2
        + preencher_alfanumerico(formatar_data_hora(gravado_em), 24)  # 3
        + preencher_numerico(cpf_responsavel, 14)  # 4: 14 posicoes na fonte
        + preencher_numerico(tipo_identificador_empregador, 1)  # 5
        + preencher_numerico(cnpj_ou_cpf_empregador, 14)  # 6
        + preencher_numerico(cno_ou_caepf or "", 14)  # 7
        + preencher_alfanumerico(razao_social_empregador, 150)  # 8
        + preencher_alfanumerico(local_prestacao_servicos, 100)  # 9
    )
    linha = _com_crc16(corpo)
    if len(linha) != 331:
        raise ValueError(f"registro tipo 2 com tamanho inesperado: {len(linha)} (esperado 331).")
    return linha


def montar_registro_tipo4(
    *,
    nsr: int,
    antes_do_ajuste: dt.datetime,
    apos_o_ajuste: dt.datetime,
    cpf_responsavel: str,
) -> str:
    """Tipo "4" — Ajuste do relógio (73 caracteres). Não exercitado nesta
    fase (ver docstring do módulo): o relógio do REP-P é o do servidor,
    nunca ajustado manualmente por um operador."""
    corpo = (
        preencher_numerico(str(nsr), 9)  # 1
        + preencher_numerico("4", 1)  # 2
        + preencher_alfanumerico(formatar_data_hora(antes_do_ajuste), 24)  # 3
        + preencher_alfanumerico(formatar_data_hora(apos_o_ajuste), 24)  # 4
        + preencher_numerico(cpf_responsavel, 11)  # 5: 11 posicoes aqui
    )
    linha = _com_crc16(corpo)
    if len(linha) != 73:
        raise ValueError(f"registro tipo 4 com tamanho inesperado: {len(linha)} (esperado 73).")
    return linha


def montar_registro_tipo5(
    *,
    nsr: int,
    gravado_em: dt.datetime,
    tipo_operacao: Literal["I", "A", "E"],
    cpf_empregado: str,
    nome_empregado: str,
    cpf_responsavel: str,
    demais_dados_identificacao: str = "",
) -> str:
    """Tipo "5" — Inclusão/alteração/exclusão de empregado no REP
    (118 caracteres). Não exercitado nesta fase (ver docstring do módulo):
    o AFD deriva exclusivamente das marcações, não do cadastro de
    colaborador (F2/F3). Campo nº 7 ("demais dados de identificação") não
    tem conteúdo especificado pela fonte (`docs/leiaute-afd-aej.md` §7,
    NÃO CONFIRMADO) — preenchido em branco por padrão, documentado aqui em
    vez de inventado."""
    corpo = (
        preencher_numerico(str(nsr), 9)  # 1
        + preencher_numerico("5", 1)  # 2
        + preencher_alfanumerico(formatar_data_hora(gravado_em), 24)  # 3
        + preencher_alfanumerico(tipo_operacao, 1)  # 4
        + preencher_numerico(cpf_empregado, 12)  # 5
        + preencher_alfanumerico(nome_empregado, 52)  # 6
        + preencher_alfanumerico(demais_dados_identificacao, 4)  # 7: NAO CONFIRMADO
        + preencher_numerico(cpf_responsavel, 11)  # 8
    )
    linha = _com_crc16(corpo)
    if len(linha) != 118:
        raise ValueError(f"registro tipo 5 com tamanho inesperado: {len(linha)} (esperado 118).")
    return linha


#: Códigos do campo nº 4 do tipo "6" (`docs/leiaute-afd-aej.md` §7). Só
#: "07"/"08" são exclusivos de REP-P; os demais são de REP-C e nunca
#: apareceriam num REP-P de qualquer forma. Documentado aqui para quem ler
#: o código encontrar o vocabulário sem procurar na norma.
CODIGOS_EVENTO_TIPO6: Final[dict[str, str]] = {
    "01": "Abertura do REP por manutencao ou violacao (REP-C)",
    "02": "Retorno de energia (REP-C ou REP-P)",
    "03": "Introducao de dispositivo externo de memoria na Porta Fiscal (REP-C)",
    "04": "Retirada de dispositivo externo de memoria na Porta Fiscal (REP-C)",
    "05": "Emissao da Relacao Instantanea de Marcacoes (REP-C)",
    "06": "Erro de impressao (REP-C)",
    "07": "Disponibilidade de servico (REP-P)",
    "08": "Indisponibilidade de servico (REP-P)",
}


def montar_registro_tipo6(*, nsr: int, gravado_em: dt.datetime, tipo_evento: str) -> str:
    """Tipo "6" — Eventos sensíveis do REP (36 caracteres, SEM CRC-16 —
    regra 8 do Anexo V limita o CRC-16 aos tipos "1" a "5",
    `docs/leiaute-afd-aej.md` §6 regra 8). Não exercitado nesta fase (ver
    docstring do módulo): não há fonte de dado real para disponibilidade/
    indisponibilidade de serviço do REP-P ainda."""
    if tipo_evento not in CODIGOS_EVENTO_TIPO6:
        raise ValueError(f"tipo_evento desconhecido: {tipo_evento!r}.")
    linha = (
        preencher_numerico(str(nsr), 9)  # 1
        + preencher_numerico("6", 1)  # 2
        + preencher_alfanumerico(formatar_data_hora(gravado_em), 24)  # 3
        + preencher_numerico(tipo_evento, 2)  # 4
    )
    if len(linha) != 36:
        raise ValueError(f"registro tipo 6 com tamanho inesperado: {len(linha)} (esperado 36).")
    return linha


def montar_trailer_tipo9(
    *,
    qtd_tipo2: int = 0,
    qtd_tipo3: int = 0,
    qtd_tipo4: int = 0,
    qtd_tipo5: int = 0,
    qtd_tipo6: int = 0,
    qtd_tipo7: int = 0,
) -> str:
    """Tipo "9" — Trailer (64 caracteres, SEM CRC-16). Não conta os
    registros do tipo "1" (cabeçalho, sempre exatamente 1) nem de si mesmo
    (tipo "9", sempre exatamente 1) — nota da tabela do leiaute,
    `docs/leiaute-afd-aej.md` §7."""
    linha = (
        preencher_numerico("999999999", 9)  # 1: constante
        + preencher_numerico(str(qtd_tipo2), 9)  # 2
        + preencher_numerico(str(qtd_tipo3), 9)  # 3
        + preencher_numerico(str(qtd_tipo4), 9)  # 4
        + preencher_numerico(str(qtd_tipo5), 9)  # 5
        + preencher_numerico(str(qtd_tipo6), 9)  # 6
        + preencher_numerico(str(qtd_tipo7), 9)  # 7
        + preencher_numerico("9", 1)  # 8: tipo do registro "9"
    )
    if len(linha) != 64:
        raise ValueError(f"trailer tipo 9 com tamanho inesperado: {len(linha)} (esperado 64).")
    return linha


def montar_linha_assinatura() -> str:
    """Linha final de assinatura digital (100 caracteres, sem número de
    tipo — não entra na contagem do trailer). Texto literal
    `"ASSINATURA_DIGITAL_EM_ARQUIVO_P7S"` + espaços à direita até 100
    caracteres; a assinatura CAdES real fica no `.p7s` destacado (A3, T11),
    nunca embutida no AFD."""
    linha = preencher_alfanumerico(_TEXTO_ASSINATURA_PLACEHOLDER, 100)
    if len(linha) != 100:
        raise ValueError(f"linha de assinatura com tamanho inesperado: {len(linha)}.")
    return linha
