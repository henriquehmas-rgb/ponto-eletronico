"""Traducao de violacao de integridade do banco para o catalogo de erros.

Mesmo padrao de `app/pessoas/erros_bd.py` (F2): o Postgres e a ultima linha
de defesa (unicidade, `EXCLUDE`, `CHECK`), este modulo so traduz o nome da
constraint violada para o codigo do catalogo, para a resposta HTTP sair
correta em vez de um 500 generico.
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.core.erros import ErroDeAplicacao

#: Nome da constraint (identico a `packages/contracts/models/jornada.py`) ->
#: codigo do catalogo. So as constraints que as tabelas de calendario
#: (`feriado_conjuntos`, `feriados`, `unidade_feriado_conjuntos`,
#: `tipos_afastamento`, `afastamentos`) podem violar em tempo de escrita.
CODIGOS_POR_CONSTRAINT: dict[str, str] = {
    "uq_feriado_conjuntos_codigo": "PONTO-CONF-001",
    "ck_feriado_conjuntos_abrangencia": "PONTO-VAL-001",
    "uq_feriados_fixos": "PONTO-CONF-001",
    "ck_feriados_definicao": "PONTO-VAL-001",
    "ck_feriados_parcial": "PONTO-VAL-001",
    "uq_tipos_afastamento_codigo": "PONTO-CONF-001",
    "tipos_afastamento_categoria_check": "PONTO-VAL-001",
    "tipos_afastamento_limite_dias_check": "PONTO-VAL-001",
    "ck_afastamentos_periodo": "PONTO-VAL-007",
    "ck_afastamentos_parcial": "PONTO-VAL-001",
    "ex_afastamentos_sobreposicao": "PONTO-VAL-010",
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

    `padrao` cobre uma constraint nao reconhecida (migration futura sem
    atualizar este mapa): preferimos um 409 generico de conflito a um 500,
    e o nome real vai para `contexto_log`.
    """
    nome = _nome_constraint(exc.orig or exc)
    codigo = CODIGOS_POR_CONSTRAINT.get(nome or "", padrao)
    return ErroDeAplicacao(codigo, contexto_log={"constraint": nome})
