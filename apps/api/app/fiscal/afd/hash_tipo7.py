"""Hash SHA-256 encadeado do registro tipo "7" do AFD (campo nº 8, "código
hash") — fórmula de melhor esforço fixada por
`docs/adr/ADR-012-formula-hash-registro-tipo-7-afd-nao-confirmada.md`.

**Leia o ADR-012 antes de mexer neste arquivo.** A norma (Portaria MTP
671/2021, Anexo V) lista os 8 insumos do hash mas não especifica o formato
de concatenação — nem se os campos entram com o *padding* de largura fixa
do próprio registro ou "crus", nem se há separador, nem a codificação de
bytes exata (`docs/leiaute-afd-aej.md` §8.2, Lacuna nº 1). O ADR-012
**já decidiu** (dono do produto, 30/07/2026) que esta fase prossegue com a
interpretação abaixo, isolada nesta função para trocar rápido se uma
referência externa (AFD de fabricante homologado, ou resposta formal da
SIT/MTE) fechar a lacuna — não é uma escolha desta função, é a fórmula
fixada:

1. Os 8 insumos entram na concatenação na representação de **largura fixa
   que cada campo teria no próprio registro tipo "7" do AFD** (mesmo
   *padding* de `app.fiscal.afd.registros`/`app.fiscal.afd.tipo7`), **sem
   separador** entre eles, codificados em **ISO-8859-1**.
2. O primeiro registro tipo "7" da sequência do REP-P (sem hash anterior)
   **omite o 8º insumo inteiramente** — string vazia, não 64 espaços/zeros.

**Nunca reutilize `marcacoes.hash_anterior`/`hash_registro` como entrada ou
saída desta função** — são uma cadeia INDEPENDENTE, calculada por F5 com uma
fórmula diferente (7 campos com separador `0x1F`, sem os insumos de
data/hora de gravação, coletor e indicador on-line/off-line que o ADR-012
exige) e com outro propósito (detectar adulteração/remoção silenciosa em
`marcacoes`, não o campo nº 8 do AFD — `docs/fases/F12-conformidade-rep-p.md`
§2.5).

**Critério de aceite "comparação byte a byte contra AFD de sistema já
aceito" fica marcado como NÃO VERIFICÁVEL especificamente para o registro
tipo "7"** (ADR-012, seção "Decisão", item 3) — os testes deste módulo
provam determinismo e sensibilidade ao encadeamento, nunca conformidade
byte a byte contra uma referência externa que não existe.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass

from app.fiscal.afd.registros import preencher_alfanumerico, preencher_numerico
from app.fiscal.comum.formatos import CODIFICACAO_LEIAUTE, formatar_data_hora


@dataclass(frozen=True, slots=True)
class InsumosHashTipo7:
    """Os 7 primeiros insumos do hash (o 8º, hash do registro anterior, é
    passado separadamente a `calcular_hash_tipo7` porque é o elo da cadeia,
    não um dado do próprio registro)."""

    nsr: int
    tipo_registro: str  # sempre "7" no REP-P; campo aceito para nao hardcodear
    datahora_marcacao: dt.datetime
    cpf: str  # 11 digitos, sem pontuacao
    datahora_gravacao: dt.datetime
    identificador_coletor: str  # "01".."05", ja no formato de 2 digitos
    indicador_offline: str  # "0" (on-line) ou "1" (off-line)


def calcular_hash_tipo7(insumos: InsumosHashTipo7, hash_anterior: str | None) -> str:
    """SHA-256 hexadecimal (minúsculo, 64 caracteres) dos 8 insumos
    concatenados conforme a fórmula do ADR-012 (ver docstring do módulo).

    `hash_anterior`: hash SHA-256 hexadecimal do registro tipo "7" anterior
    da MESMA sequência de REP-P, ou `None`/string vazia para o primeiro
    registro da cadeia (omite o 8º insumo inteiramente, não o preenche com
    espaço/zero).
    """
    campo_nsr = preencher_numerico(str(insumos.nsr), 9)
    campo_tipo = preencher_alfanumerico(insumos.tipo_registro, 1)
    campo_data_marcacao = formatar_data_hora(insumos.datahora_marcacao)
    campo_cpf = preencher_numerico(insumos.cpf, 12)
    campo_data_gravacao = formatar_data_hora(insumos.datahora_gravacao)
    campo_coletor = preencher_numerico(insumos.identificador_coletor, 2)
    campo_offline = preencher_numerico(insumos.indicador_offline, 1)

    concatenado = (
        campo_nsr
        + campo_tipo
        + campo_data_marcacao
        + campo_cpf
        + campo_data_gravacao
        + campo_coletor
        + campo_offline
    )
    if hash_anterior:
        concatenado += hash_anterior

    return hashlib.sha256(concatenado.encode(CODIFICACAO_LEIAUTE)).hexdigest()
