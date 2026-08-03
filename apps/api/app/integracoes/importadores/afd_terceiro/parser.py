"""Leitura estrutural de um AFD de terceiro (largura fixa, ISO-8859-1).

`ler_arquivo_afd` é o único ponto de entrada: recebe os BYTES brutos do
arquivo (como vieram do armazenamento de objetos, sem decodificar) e devolve
`ArquivoAfdTerceiro` ou levanta `ArquivoAfdInvalido` -- uma falha
ESTRUTURAL, do arquivo inteiro (mapeia para `PONTO-IMP-001`/`PONTO-IMP-003`,
ver `servico.py`). Falha de UM registro tipo "7" isolado (data ilegível, CPF
com dígito não numérico) não aborta o arquivo inteiro: vira um item da lista
`erros_linha`, no mesmo padrão de "relatório linha a linha, sem abortar o
resto" que `worker/tarefas/importacoes.py` (F2) já estabeleceu.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from app.integracoes.importadores.afd_terceiro import leiaute

#: BOM UTF-8: sinal inequívoco de que o arquivo foi reencodado (ISO-8859-1
#: nunca produz estes três bytes como prefixo de um arquivo texto real).
_BOM_UTF8 = b"\xef\xbb\xbf"


class ArquivoAfdInvalido(RuntimeError):
    """Falha estrutural do arquivo inteiro. `codigo` é o código do catálogo
    (`PONTO-IMP-001` layout não reconhecido, `PONTO-IMP-003` verificação
    estrutural: CRC divergente, sequência de NSR inconsistente ou
    codificação fora do leiaute) que `servico.py` usa para levantar
    `ErroDeAplicacao`."""

    def __init__(self, mensagem: str, *, codigo: str) -> None:
        super().__init__(mensagem)
        self.codigo = codigo


@dataclass(frozen=True, slots=True)
class Cabecalho:
    """Registro tipo "1" do arquivo importado (posições, docs/leiaute-afd-aej
    .md §7)."""

    cnpj_ou_cpf_empregador: str
    numero_registro: str
    periodo_inicio: dt.date
    periodo_fim: dt.date
    gerado_em: dt.datetime


@dataclass(frozen=True, slots=True)
class RegistroTipo7Bruto:
    """Um registro tipo "7" (marcação REP-P) já com os campos separados, mas
    AINDA não validados linha a linha (isso é trabalho de `servico.py`, que
    tem acesso ao contexto de tenant/empresa para validar CPF/data contra
    regras de negócio, não deste módulo, que só sabe ler posição de
    coluna)."""

    numero_linha: int
    nsr_origem_bruto: str
    datahora_marcacao_bruta: str
    cpf_bruto: str
    datahora_gravacao_bruta: str
    identificador_coletor: str
    online: bool
    hash_origem: str
    linha_bruta: str


@dataclass(frozen=True, slots=True)
class LinhaIgnorada:
    """Linha reconhecida mas que não vira marcação (tipos "2"/"4"/"5"/"6"/
    trailer/assinatura) ou não reconhecida (largura/tipo fora da tabela)."""

    numero_linha: int
    motivo: str


@dataclass(frozen=True, slots=True)
class ArquivoAfdTerceiro:
    cabecalho: Cabecalho
    registros_tipo7: list[RegistroTipo7Bruto]
    linhas_ignoradas: list[LinhaIgnorada] = field(default_factory=list)
    total_tipo7_no_trailer: int | None = None


def _validar_sem_bom(conteudo: bytes) -> None:
    if conteudo.startswith(_BOM_UTF8):
        raise ArquivoAfdInvalido(
            "Arquivo comeca com BOM UTF-8: sinal de que foi reencodado a partir do "
            "ISO-8859-1 original. Reobtenha o arquivo original, sem reencodar.",
            codigo="PONTO-IMP-003",
        )


def _dividir_em_linhas(conteudo: bytes) -> list[bytes]:
    """Divide pelo terminador oficial `CR LF` (docs/leiaute-afd-aej.md §6
    regra 2). Descarta uma última linha vazia resultante de um CRLF final
    (comum em arquivo bem formado), mas preserva linhas vazias no MEIO do
    arquivo (a regra 4 -- "sem linhas em branco" -- é validada explicitamente
    abaixo, não silenciosamente descartada)."""
    partes = conteudo.split(b"\r\n")
    if partes and partes[-1] == b"":
        partes = partes[:-1]
    return partes


def _decodificar_linha(bruta: bytes, *, numero_linha: int) -> str:
    # ISO-8859-1 mapeia todo byte 0-255 para um caractere: nunca levanta
    # UnicodeDecodeError. A verificação de "arquivo não é ISO-8859-1
    # original" é feita por sinais estruturais (BOM, largura de linha,
    # CRC do cabeçalho) em vez de exceção de decodificação, que aqui nunca
    # dispara -- ver docstring do módulo e de `servico.py`.
    return bruta.decode("iso-8859-1")


def _parsear_cabecalho(linha: str) -> Cabecalho:
    if len(linha) != leiaute.TAMANHO_TIPO1:
        raise ArquivoAfdInvalido(
            f"Primeira linha tem {len(linha)} caracteres; um cabecalho tipo 1 de AFD "
            f"tem {leiaute.TAMANHO_TIPO1}. Arquivo nao parece um AFD (layout nao "
            "reconhecido).",
            codigo="PONTO-IMP-001",
        )
    if linha[leiaute.POS_TIPO1_CONSTANTE] != leiaute.CONSTANTE_TIPO1:
        raise ArquivoAfdInvalido(
            "Primeira linha nao comeca com a constante de cabecalho "
            f"{leiaute.CONSTANTE_TIPO1!r}. Arquivo nao parece um AFD (layout nao "
            "reconhecido).",
            codigo="PONTO-IMP-001",
        )
    if linha[leiaute.POS_TIPO1_TIPO_REGISTRO] != "1":
        raise ArquivoAfdInvalido(
            "Primeira linha nao e um registro tipo 1 (cabecalho). Arquivo nao parece "
            "um AFD (layout nao reconhecido).",
            codigo="PONTO-IMP-001",
        )

    crc_informado = linha[leiaute.POS_TIPO1_CRC16]
    crc_calculado = leiaute.crc16_kermit_hex(
        linha[leiaute.POS_TIPO1_COBERTO_PELO_CRC].encode("iso-8859-1")
    )
    if crc_informado.strip().upper() != crc_calculado:
        raise ArquivoAfdInvalido(
            f"CRC-16 do cabecalho nao confere (informado {crc_informado!r}, calculado "
            f"{crc_calculado!r}). Arquivo truncado ou corrompido -- verificacao "
            "estrutural falhou.",
            codigo="PONTO-IMP-003",
        )

    try:
        periodo_inicio = leiaute.parsear_data(linha[leiaute.POS_TIPO1_DATA_INICIAL])
        periodo_fim = leiaute.parsear_data(linha[leiaute.POS_TIPO1_DATA_FINAL])
        gerado_em = leiaute.parsear_dh(linha[leiaute.POS_TIPO1_GERACAO])
    except leiaute.CampoDhInvalido as exc:
        raise ArquivoAfdInvalido(
            f"Campo de data/hora do cabecalho ilegivel: {exc}. Verificacao estrutural " "falhou.",
            codigo="PONTO-IMP-003",
        ) from exc

    return Cabecalho(
        cnpj_ou_cpf_empregador=linha[leiaute.POS_TIPO1_CNPJ_CPF_EMPREGADOR].strip(),
        numero_registro=linha[leiaute.POS_TIPO1_NUMERO_REP].strip(),
        periodo_inicio=periodo_inicio,
        periodo_fim=periodo_fim,
        gerado_em=gerado_em,
    )


def _e_linha_tipo7(linha: str) -> bool:
    return len(linha) == leiaute.TAMANHO_TIPO7 and linha[leiaute.POS_TIPO7_TIPO_REGISTRO] == "7"


def _e_linha_trailer(linha: str) -> bool:
    return (
        len(linha) == leiaute.TAMANHO_TIPO9
        and linha[leiaute.POS_TIPO9_CONSTANTE] == leiaute.CONSTANTE_TIPO9
        and linha[leiaute.POS_TIPO9_TIPO_REGISTRO] == "9"
    )


def _e_linha_tipo3(linha: str) -> bool:
    return len(linha) == leiaute.TAMANHO_TIPO3


def _parsear_tipo7(linha: str, *, numero_linha: int) -> RegistroTipo7Bruto:
    return RegistroTipo7Bruto(
        numero_linha=numero_linha,
        nsr_origem_bruto=linha[leiaute.POS_TIPO7_NSR],
        datahora_marcacao_bruta=linha[leiaute.POS_TIPO7_DATAHORA_MARCACAO],
        cpf_bruto=linha[leiaute.POS_TIPO7_CPF],
        datahora_gravacao_bruta=linha[leiaute.POS_TIPO7_DATAHORA_GRAVACAO],
        identificador_coletor=linha[leiaute.POS_TIPO7_IDENTIFICADOR_COLETOR],
        online=linha[leiaute.POS_TIPO7_ONLINE_OFFLINE] == "0",
        hash_origem=linha[leiaute.POS_TIPO7_HASH].strip(),
        linha_bruta=linha,
    )


def ler_arquivo_afd(conteudo: bytes) -> ArquivoAfdTerceiro:
    """Lê e valida a estrutura de um AFD de terceiro. Levanta
    `ArquivoAfdInvalido` para qualquer falha que comprometa o arquivo
    INTEIRO; registros tipo 7 individualmente malformados (fora deste
    módulo -- aqui só a largura/tipo da linha já classifica) não chegam a
    este ponto como falha fatal, porque a validação de CONTEÚDO de cada
    campo (CPF, datas) é responsabilidade de `servico.py`, linha a linha.
    """
    _validar_sem_bom(conteudo)

    linhas_bytes = _dividir_em_linhas(conteudo)
    if not linhas_bytes:
        raise ArquivoAfdInvalido("Arquivo vazio.", codigo="PONTO-IMP-001")

    linhas = [_decodificar_linha(bruta, numero_linha=i + 1) for i, bruta in enumerate(linhas_bytes)]

    cabecalho = _parsear_cabecalho(linhas[0])

    registros_tipo7: list[RegistroTipo7Bruto] = []
    linhas_ignoradas: list[LinhaIgnorada] = []
    total_trailer: int | None = None
    ultimo_nsr: int | None = None
    trailer_encontrado_na_linha: int | None = None

    for indice in range(1, len(linhas)):
        numero_linha = indice + 1
        linha = linhas[indice]

        if _e_linha_tipo3(linha) and linha[9:10] == "3":
            raise ArquivoAfdInvalido(
                f"Linha {numero_linha}: registro tipo 3 encontrado (marcacao de REP-C/"
                "REP-A). Este importador so aceita AFD de REP-P -- arquivo tem layout "
                "de outro tipo de REP.",
                codigo="PONTO-IMP-001",
            )

        if _e_linha_tipo7(linha):
            registro = _parsear_tipo7(linha, numero_linha=numero_linha)
            try:
                nsr_atual = int(registro.nsr_origem_bruto)
            except ValueError:
                # NSR ilegivel: nao da para checar ordem, mas o registro
                # ainda e coletado -- `servico.py` rejeita esta linha
                # especifica no relatorio de erro (nao aborta o arquivo).
                registros_tipo7.append(registro)
                continue
            if ultimo_nsr is not None and nsr_atual <= ultimo_nsr:
                raise ArquivoAfdInvalido(
                    f"Linha {numero_linha}: NSR {nsr_atual} nao e maior que o NSR "
                    f"anterior ({ultimo_nsr}). O leiaute exige registros ordenados "
                    "por NSR (regra 3, docs/leiaute-afd-aej.md) -- sequencia de NSR "
                    "inconsistente no arquivo importado.",
                    codigo="PONTO-IMP-003",
                )
            ultimo_nsr = nsr_atual
            registros_tipo7.append(registro)
            continue

        if _e_linha_trailer(linha):
            total_trailer = int(linha[leiaute.POS_TIPO9_QTD_TIPO7])
            trailer_encontrado_na_linha = numero_linha
            continue

        e_linha_apos_trailer = (
            trailer_encontrado_na_linha is not None
            and numero_linha == trailer_encontrado_na_linha + 1
        )
        if e_linha_apos_trailer:
            # Linha logo apos o trailer: assinatura digital (100 chars, sem
            # numero de tipo). Nao valida o conteudo literal -- so registra.
            linhas_ignoradas.append(
                LinhaIgnorada(numero_linha=numero_linha, motivo="linha de assinatura digital")
            )
            continue

        for tamanho, tipo in (
            (leiaute.TAMANHO_TIPO2, "2"),
            (leiaute.TAMANHO_TIPO4, "4"),
            (leiaute.TAMANHO_TIPO5, "5"),
            (leiaute.TAMANHO_TIPO6, "6"),
        ):
            if len(linha) == tamanho and linha[9:10] == tipo:
                linhas_ignoradas.append(
                    LinhaIgnorada(
                        numero_linha=numero_linha,
                        motivo=f"registro tipo {tipo} (nao e marcacao, ignorado)",
                    )
                )
                break
        else:
            linhas_ignoradas.append(
                LinhaIgnorada(
                    numero_linha=numero_linha,
                    motivo=f"linha nao reconhecida ({len(linha)} caracteres)",
                )
            )

    if not registros_tipo7:
        raise ArquivoAfdInvalido(
            "Nenhum registro tipo 7 (marcacao de ponto REP-P) encontrado no arquivo.",
            codigo="PONTO-IMP-001",
        )

    if total_trailer is not None and total_trailer != len(registros_tipo7):
        raise ArquivoAfdInvalido(
            f"Trailer informa {total_trailer} registros tipo 7, mas o arquivo tem "
            f"{len(registros_tipo7)}. Arquivo pode estar truncado -- verificacao "
            "estrutural falhou.",
            codigo="PONTO-IMP-003",
        )

    return ArquivoAfdTerceiro(
        cabecalho=cabecalho,
        registros_tipo7=registros_tipo7,
        linhas_ignoradas=linhas_ignoradas,
        total_tipo7_no_trailer=total_trailer,
    )
