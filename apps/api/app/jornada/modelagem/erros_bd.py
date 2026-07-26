"""Traducao de violacao de integridade do banco para o catalogo de erros,
restrita as constraints das tabelas de `app.jornada.modelagem` (`horarios`,
`jornadas`, `jornada_dias`, `turnos`, `escalas`, `escala_ciclos`,
`escala_atribuicoes`, `vinculo_jornadas`).

Copia deliberada do padrao de `app.pessoas.erros_bd` (F2) -- ver docstring de
`app.jornada.modelagem.paginacao` sobre por que a copia, em vez do import
cruzado, e a escolha certa entre fases que rodam em paralelo.
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.core.erros import ErroDeAplicacao

#: Nome da constraint (identico ao de `packages/contracts/models/jornada.py`)
#: -> codigo do catalogo.
CODIGOS_POR_CONSTRAINT: dict[str, str] = {
    "uq_horarios_codigo": "PONTO-CONF-001",
    "uq_jornadas_codigo": "PONTO-CONF-001",
    "uq_jornada_dias": "PONTO-CONF-001",
    "uq_turnos_codigo": "PONTO-CONF-001",
    "uq_escalas_codigo": "PONTO-CONF-001",
    "uq_escala_ciclos": "PONTO-CONF-001",
    "ck_jornadas_vigencia": "PONTO-VAL-007",
    "ck_escala_atribuicoes_vigencia": "PONTO-VAL-007",
    "ck_vinculo_jornadas_vigencia": "PONTO-VAL-007",
    "ex_escala_atribuicoes_sobreposicao": "PONTO-VAL-010",
    "ex_vinculo_jornadas_sobreposicao": "PONTO-VAL-010",
}


def _nome_constraint(origem: BaseException) -> str | None:
    """Extrai o nome da constraint do erro nativo do driver (`asyncpg`
    preenche `constraint_name`; sem o atributo, busca textual na mensagem --
    os nomes de constraint deste projeto sao sempre explicitos)."""
    nome = getattr(origem, "constraint_name", None)
    if nome:
        return str(nome)
    texto = str(origem)
    for candidato in CODIGOS_POR_CONSTRAINT:
        if candidato in texto:
            return candidato
    return None


def traduzir_integridade(exc: IntegrityError, *, padrao: str = "PONTO-CONF-001") -> ErroDeAplicacao:
    """Converte `IntegrityError` no `ErroDeAplicacao` do codigo correspondente.

    `padrao` cobre o caso de constraint nao reconhecida (preferimos um 409
    generico de conflito a um 500); o nome real vai para `contexto_log`.
    """
    nome = _nome_constraint(exc.orig or exc)
    codigo = CODIGOS_POR_CONSTRAINT.get(nome or "", padrao)
    return ErroDeAplicacao(codigo, contexto_log={"constraint": nome})
