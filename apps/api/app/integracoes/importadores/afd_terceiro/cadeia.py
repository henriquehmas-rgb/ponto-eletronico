"""Fórmula de `crc16`/`hash_registro`/`hash_anterior` PRÓPRIA para marcações
importadas de AFD de terceiro (critério de aceite 8 do PCF F13).

`marcacoes.crc16`/`hash_anterior`/`hash_registro` são `NOT NULL` (schema.sql)
mesmo para uma linha importada, mas o PCF é explícito: esses valores "não
podem ser confundidos com os valores que F5 calcularia para uma marcação
nossa -- documente a fórmula usada, mesmo padrão de honestidade do ADR-012 se
não houver uma norma clara para isso". A norma (Portaria 671/2021) não define
CRC/hash para dado JÁ IMPORTADO de outro sistema -- só para o que O NOSSO
REP-P grava. Este módulo é essa fórmula própria, deliberadamente distinta de
`app.marcacao.dominio.nsr` em três dimensões, todas verificáveis por
inspeção:

1. **Separador diferente.** F5 usa `\\x1f` (Unit Separator). Aqui,
   `\\x1e` (Record Separator).
2. **Marcador de domínio literal.** A string `"AFD_TERCEIRO_IMPORTADO"` entra
   na concatenação -- uma string que a fórmula de F5 nunca produz (F5 nunca
   inclui uma string constante de domínio), então as duas famílias de hash
   são estruturalmente incapazes de colidir por acidente de formato.
3. **Campos diferentes.** F5 encadeia `(tenant_id, rep_p_id, nsr, cpf,
   tipo_registro, canal, datahora_marcacao)`. Aqui: `(marcador de domínio,
   importacao_id, nsr de origem, cpf, tipo_registro, datahora_marcacao,
   linha bruta original de 137 bytes)` -- nem o mesmo conjunto, nem a mesma
   ordem, e inclui o próprio conteúdo bruto do registro de origem (F5 nunca
   tem "conteúdo bruto de outro sistema" para incluir).

**A cadeia é interna à importação**, não ao REP-P: o primeiro registro
importado de cada `importacoes.id` começa com `hash_anterior=None`, e cada
registro seguinte encadeia a partir do `hash_registro` do registro importado
anterior **da mesma importação**, na ordem em que aparecem no arquivo. Isso
dá uma propriedade de integridade útil (adulterar um registro importado
depois do fato quebra a cadeia a partir dali) sem tocar nem imitar
`nsr_sequencias.ultimo_hash`/`nsr_emissoes`, que são exclusivos da cadeia do
NOSSO REP-P e nunca são lidos nem escritos por este módulo.

`crc16` reaproveita `leiaute.crc16_kermit` (o algoritmo OFICIAL do leiaute,
já distinto do CRC-16/ARC de F5 por si só) sobre os bytes ISO-8859-1 da linha
ORIGINAL do arquivo importado -- nunca sobre `linha_afd` gerado por nós
(este importador não gera `linha_afd` nenhuma: a coluna fica `NULL`, porque
a linha que de fato existe é a do arquivo de origem, guardada ali mesmo para
auditoria -- ver `servico.py`).
"""

from __future__ import annotations

import datetime as dt
import hashlib
from uuid import UUID

from app.integracoes.importadores.afd_terceiro.leiaute import crc16_kermit

#: Record Separator (0x1E) -- deliberadamente diferente do Unit Separator
#: (0x1F) usado por `app.marcacao.dominio.nsr._SEPARADOR`.
SEPARADOR = "\x1e"

#: Marcador de domínio: nunca aparece na fórmula de F5, então as duas
#: famílias de hash não podem colidir por engano de implementação.
MARCADOR_DOMINIO = "AFD_TERCEIRO_IMPORTADO"


def canonicalizar_registro_importado(
    *,
    importacao_id: UUID,
    nsr_origem: int,
    cpf: str,
    tipo_registro: str,
    datahora_marcacao: dt.datetime,
    linha_bruta: str,
) -> str:
    """Monta a string canônica de um registro importado. Ver docstring do
    módulo para a fórmula fixa e a comparação campo a campo com F5."""
    instante_utc = datahora_marcacao.astimezone(dt.UTC)
    instante_iso = instante_utc.isoformat(timespec="microseconds").replace("+00:00", "Z")
    campos = (
        MARCADOR_DOMINIO,
        str(importacao_id),
        str(nsr_origem),
        cpf,
        tipo_registro,
        instante_iso,
        linha_bruta,
    )
    return SEPARADOR.join(campos)


def calcular_hash_importado(dados_canonicos: str, hash_anterior: str | None) -> str:
    """SHA-256 hexadecimal de `(hash_anterior ou "") + SEPARADOR +
    dados_canonicos` -- mesmo princípio de encadeamento (hash anterior
    ANTES) que F5 usa, aplicado à cadeia própria desta importação."""
    base = f"{hash_anterior or ''}{SEPARADOR}{dados_canonicos}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def crc16_do_registro_importado(linha_bruta: str) -> int:
    """CRC-16/KERMIT (leiaute oficial, `leiaute.crc16_kermit`) sobre os bytes
    ISO-8859-1 da linha ORIGINAL de 137 caracteres do arquivo importado."""
    return crc16_kermit(linha_bruta.encode("iso-8859-1"))
