"""Formatação de data/hora e montagem de arquivo texto, comuns ao AFD e ao
AEJ (`docs/fases/F12-conformidade-rep-p.md` §2.9; `docs/leiaute-afd-aej.md`
§6 regras 2/6, §9 regras 2/5).

Por que este módulo existe (e por que os dois leiautes, apesar de tudo mais
serem diferentes entre si — largura fixa vs. delimitado por `|` — compartilham
exatamente estas três funções): o formato de data/hora é a MESMA string nos
dois arquivos (mesma exigência de segundos fixados em `"00"`, mesmo formato
de fuso) e a montagem do arquivo (linhas terminadas em CR+LF, sem linha em
branco, ISO-8859-1) também é idêntica — só o que vai DENTRO de cada linha
diverge. Duplicar isso em `app.fiscal.afd`/`app.fiscal.aej` é o tipo exato de
risco que colocar A1 como "T1-first" evita: se um lado corrigir um bug de
formatação e o outro não, os dois arquivos divergem silenciosamente perante
o mesmo fiscal.

Dono: A1 (T1). `app.fiscal.aej` (A2) importa este módulo; não o edita.
"""

from __future__ import annotations

import datetime as dt
from typing import Final

#: Codificação exigida pelos dois leiautes (`docs/leiaute-afd-aej.md` §6
#: regra 1, §9 regra 1). Nome canônico do Python para ISO 8859-1/Latin-1.
CODIFICACAO_LEIAUTE: Final[str] = "iso-8859-1"

#: Terminador de linha exigido pelos dois leiautes: os caracteres ASCII 13
#: (CR) e 10 (LF), NESTA ordem (`docs/leiaute-afd-aej.md` §6 regra 2, §9
#: regra 2) — nunca `\n` sozinho (LF, comportamento padrão do Python em
#: texto) nem `\r\n` dependente de plataforma (`os.linesep`): o terminador é
#: uma exigência do LEIAUTE, não do sistema operacional que gera o arquivo.
TERMINADOR_LINHA: Final[bytes] = b"\r\n"


def formatar_data(data: dt.date) -> str:
    """`AAAA-MM-dd` — tipo `D` dos dois leiautes (`docs/leiaute-afd-aej.md`
    §6 regra 6, §9 regra 5). `dt.date.isoformat()` já produz exatamente este
    formato; a função existe mesmo assim para que os dois geradores nunca
    chamem `.isoformat()` diretamente e percam a garantia de que os dois
    leiautes usam a mesma função no dia em que algo mudar."""
    return data.strftime("%Y-%m-%d")


def formatar_data_hora(momento: dt.datetime) -> str:
    """`AAAA-MM-ddThh:mm:00ZZZZZ` — tipo `DH` dos dois leiautes
    (`docs/leiaute-afd-aej.md` §6 regra 6, §9 regra 5). `T` é literal,
    `hh`=00-23, `mm`=00-59, os SEGUNDOS SÃO SEMPRE FIXADOS em `"00"`
    (mesmo quando `momento.second != 0` — a norma não pede o segundo real,
    pede o literal `"00"`; truncar em vez de arredondar, para não empurrar
    um evento para o minuto seguinte), e `ZZZZZ` é 1 dígito de sinal + 4
    dígitos de hora/minuto do fuso, sem separador (`"-0300"`, nunca
    `"-03:00"`). Exemplo da própria fonte: `2021-04-27T16:44:00-0300`
    (24 caracteres — todo campo `DH` dos dois leiautes tem exatamente 24
    posições, e esta função sempre produz 24 caracteres).

    Exige um `datetime` com fuso horário definido (`tzinfo` presente e
    `utcoffset()` resolvível) — um `datetime` ingênuo não tem `ZZZZZ` para
    relatar, e silenciosamente assumir UTC seria inventar um dado que a
    norma exige ser explícito.
    """
    deslocamento = momento.utcoffset()
    if momento.tzinfo is None or deslocamento is None:
        raise ValueError(
            "formatar_data_hora exige um datetime com fuso horario definido "
            "(tzinfo presente); recebido um datetime ingenuo."
        )
    total_minutos = int(deslocamento.total_seconds() // 60)
    sinal = "+" if total_minutos >= 0 else "-"
    total_minutos_abs = abs(total_minutos)
    horas_fuso, minutos_fuso = divmod(total_minutos_abs, 60)
    sufixo_fuso = f"{sinal}{horas_fuso:02d}{minutos_fuso:02d}"
    return f"{momento:%Y-%m-%dT%H:%M}:00{sufixo_fuso}"


def montar_arquivo_texto(linhas: list[str]) -> bytes:
    """Monta o arquivo completo a partir das linhas já formatadas (uma por
    registro, sem terminador): junta com `TERMINADOR_LINHA` entre cada par
    e acrescenta um terminador final (regra 2 dos dois leiautes: TODA linha,
    inclusive a última, termina em CR+LF — não é separador entre linhas, é
    terminador de cada linha), codifica em `CODIFICACAO_LEIAUTE`.

    Levanta `ValueError` (não faz *mangling* silencioso) se algum caractere
    de alguma linha não for representável em ISO-8859-1 — nomes de pessoas
    em português usam só Latin-1 na prática, mas isto não é presumido, é
    verificado: um caractere fora do Latin-1 em razão social/nome viraria
    byte errado ou seria descartado por um `.encode(..., errors="replace")`
    silencioso, e um AFD/AEJ com um byte errado é pior que um erro explícito
    na geração (`docs/fases/F12-conformidade-rep-p.md` §2.9). Quem chama
    (o gerador de AFD/AEJ) traduz este `ValueError` para `PONTO-FISC-006`
    ("falha na geração do arquivo fiscal") — não é um código de erro novo.
    """
    partes: list[bytes] = []
    for indice, linha in enumerate(linhas):
        try:
            partes.append(linha.encode(CODIFICACAO_LEIAUTE))
        except UnicodeEncodeError as exc:
            raise ValueError(
                f"linha {indice + 1} contem caractere nao representavel em "
                f"{CODIFICACAO_LEIAUTE}: {exc}"
            ) from exc
    if not partes:
        return b""
    return TERMINADOR_LINHA.join(partes) + TERMINADOR_LINHA
