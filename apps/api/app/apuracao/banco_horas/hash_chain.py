"""Cadeia de hash do extrato de banco de horas (`bh_lancamentos`) e a
formula de arredondamento do motor (ADR-004, ponto 2).

CONTRATO ENTRE MODULOS desta fase: qualquer codigo que grave `bh_lancamentos`
(este pacote) ou que precise reconstruir/conferir a cadeia (testes desta
fase) importa daqui -- a formula e fixada e documentada neste modulo porque
mudar `_SEPARADOR`, a lista de campos canonicos ou a normalizacao de
qualquer um deles invalidaria toda cadeia ja gravada. Se algum dia for
preciso mudar, e RFC, nunca ajuste silencioso.

Cadeia PROPRIA desta fase -- mesmo padrao estrutural de
`app.marcacao.dominio.nsr` (F5: SHA-256 hexadecimal de
`(hash_anterior ou "") + SEPARADOR + dados_canonicos`, hash anterior ANTES
dos dados canonicos, para que qualquer alteracao retroativa mude a entrada
de todo elo seguinte -- glossario, "Hash chain"), mas NAO a mesma cadeia:
cada extrato imutavel do sistema (`marcacoes`, `auditoria`, `bh_lancamentos`)
tem a sua propria formula, documentada em seu proprio modulo.

Campos canonicos, NESTA ordem, cada um normalizado antes de entrar:

1. ``tenant_id`` -- ``str(UUID)``, minusculo, com hifens.
2. ``bh_conta_id`` -- ``str(UUID)``.
3. ``sequencia`` -- ``str(int)`` decimal.
4. ``data_competencia`` -- ISO 8601 (``AAAA-MM-DD``).
5. ``tipo`` -- exatamente como armazenado (``credito``, ``debito``, ...).
6. ``origem`` -- idem.
7. ``minutos`` -- ``str(int)`` decimal, com sinal.
8. ``fator`` -- ``Decimal`` normalizado a 4 casas (``NUMERIC(6,4)`` da
   coluna), nunca a representacao de ponto flutuante do Python.
9. ``minutos_equivalentes`` -- ``str(int)``.
10. ``saldo_apos_minutos`` -- ``str(int)``.
11. ``descricao`` -- exatamente como armazenada.

Concatenados com o separador ASCII "Unit Separator" (0x1F) -- a mesma
escolha de `app.marcacao.dominio.nsr`: nunca aparece em UUID, inteiro
decimal ou texto livre de descricao com controle, o que evita ambiguidade de
concatenacao.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

#: Separador ASCII "Unit Separator" (0x1F). Ver docstring do modulo.
_SEPARADOR = "\x1f"

#: Quantizacao de `fator` para a cadeia de hash: sempre 4 casas decimais,
#: identico a escala de `NUMERIC(6,4)` no banco -- assim `Decimal("1.5")` e
#: `Decimal("1.5000")` produzem exatamente a mesma entrada canonica.
_QUANTUM_FATOR = Decimal("1.0000")


def aplicar_fator(minutos: int, fator: Decimal) -> int:
    """``minutos_equivalentes = arredondamento_half_up(minutos * fator)``.

    Aritmetica exclusivamente em `Decimal` -- ADR-004, ponto 2: ponto
    flutuante e proibido no motor de calculo, inclusive em fatores
    intermediarios. `fator` chega como `Decimal` (coluna `NUMERIC(6,4)`);
    `minutos` e sempre `int`. Este e o UNICO ponto de arredondamento deste
    modulo: half-up (0.5 arredonda para cima), nunca truncamento silencioso
    nem `round()` do Python (que arredonda para o par mais proximo,
    "banker's rounding" -- divergiria silenciosamente de half-up para
    valores ``x.5``).
    """
    resultado = (Decimal(minutos) * fator).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(resultado)


def canonicalizar_lancamento(
    *,
    tenant_id: UUID,
    bh_conta_id: UUID,
    sequencia: int,
    data_competencia: dt.date,
    tipo: str,
    origem: str,
    minutos: int,
    fator: Decimal,
    minutos_equivalentes: int,
    saldo_apos_minutos: int,
    descricao: str,
) -> str:
    """Monta a string canonica que entra em `calcular_hash`. Ver docstring
    do modulo para a lista fixa de campos e a ordem."""
    campos = (
        str(tenant_id),
        str(bh_conta_id),
        str(sequencia),
        data_competencia.isoformat(),
        tipo,
        origem,
        str(minutos),
        str(fator.quantize(_QUANTUM_FATOR)),
        str(minutos_equivalentes),
        str(saldo_apos_minutos),
        descricao,
    )
    return _SEPARADOR.join(campos)


def calcular_hash(dados_canonicos: str, hash_anterior: str | None) -> str:
    """SHA-256 hexadecimal (minusculo, 64 caracteres, formato `dom_sha256`)
    de ``(hash_anterior ou "") + _SEPARADOR + dados_canonicos``.

    Encadear o hash anterior ANTES dos dados canonicos (em vez de depois) e
    deliberado: torna a cadeia sensivel a qualquer alteracao retroativa --
    trocar um hash no meio da cadeia muda a entrada de todo elo seguinte
    (glossario, "Hash chain").
    """
    base = f"{hash_anterior or ''}{_SEPARADOR}{dados_canonicos}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()
